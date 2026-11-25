import shutil
from datetime import date
from decimal import Decimal

import pytest

from cip.config import Settings
from cip.data import ingest as ing
from cip.data.schemas import CUSTOMERS_SCHEMA, FULL_YEAR_COLUMN_NAMES, TRANSACTIONS_SCHEMA
from tests.conftest import FIXTURES

CUSTOMERS, TRANSACTIONS = ing.SOURCES


def test_customer_schema_matches_csv_header_exactly():
    header = (FIXTURES / "customer_data.csv").read_text().splitlines()[0].split(",")
    assert CUSTOMERS_SCHEMA.fieldNames() == header


def test_transactions_schema_matches_csv_header_exactly():
    header = (FIXTURES / "transactions_data.csv").read_text().splitlines()[0].split(",")
    assert TRANSACTIONS_SCHEMA.fieldNames() == header


def test_provided_target_columns_are_classified_as_full_year():
    assert {"churn_probability", "customer_lifetime_value", "clv_segment"} <= FULL_YEAR_COLUMN_NAMES


@pytest.mark.spark
def test_reads_customers_with_declared_types(spark):
    df = ing.read_source(spark, str(FIXTURES / "customer_data.csv"), CUSTOMERS_SCHEMA)
    row = df.where("customer_id = 93716481").first()

    assert row.location == "Pereira, Risaralda"  # quoted comma survives
    assert row.savings_account is True and row.personal_loan is False  # "True"/"False" parsed
    assert row.last_survey_date == date(2023, 12, 16)
    assert row._source_file.endswith("customer_data.csv")
    assert row._ingested_at is not None


@pytest.mark.spark
def test_reads_transactions_with_declared_types(spark):
    df = ing.read_source(spark, str(FIXTURES / "transactions_data.csv"), TRANSACTIONS_SCHEMA)
    row = df.where("customer_id = 93716481 AND date = '2023-11-23'").first()
    assert row.amount == Decimal("1262800.00")


@pytest.mark.spark
@pytest.mark.parametrize("source", [CUSTOMERS, TRANSACTIONS], ids=lambda s: s.table)
def test_clean_fixture_passes_validation(spark, source):
    path = str(FIXTURES / source.file_name)
    report = ing.validate(ing.read_source(spark, path, source.schema), source, "t", path)
    assert report.ok, report
    assert report.rows == len((FIXTURES / source.file_name).read_text().splitlines()) - 1


@pytest.mark.spark
def test_unparseable_value_is_counted_as_corrupt(spark, tmp_path):
    bad = tmp_path / "transactions_data.csv"
    lines = (FIXTURES / "transactions_data.csv").read_text().splitlines()
    lines.append("93716481,2023-13-45,not-a-number,Transfer")
    bad.write_text("\n".join(lines) + "\n")

    report = ing.validate(
        ing.read_source(spark, str(bad), TRANSACTIONS_SCHEMA), TRANSACTIONS, "t", str(bad)
    )
    assert report.corrupt_rows == 1
    assert not report.ok


@pytest.mark.spark
def test_duplicate_customer_is_detected(spark, tmp_path):
    bad = tmp_path / "customer_data.csv"
    lines = (FIXTURES / "customer_data.csv").read_text().splitlines()
    bad.write_text("\n".join([*lines, lines[1]]) + "\n")

    report = ing.validate(
        ing.read_source(spark, str(bad), CUSTOMERS_SCHEMA), CUSTOMERS, "t", str(bad)
    )
    assert report.duplicate_key_rows == 1
    assert not report.ok


@pytest.mark.spark
def test_header_matches_for_clean_fixtures(spark):
    for source in ing.SOURCES:
        ing.check_header(spark, str(FIXTURES / source.file_name), source.schema)


@pytest.mark.spark
@pytest.mark.parametrize(
    "mutate",
    [
        lambda h: h.replace("amount", "amount_cop", 1),  # renamed
        lambda h: h.replace("date,amount", "amount,date", 1),  # reordered
        lambda h: h.replace(",type", "", 1),  # dropped
    ],
    ids=["renamed", "reordered", "dropped"],
)
def test_header_mismatch_fails_before_reading(spark, tmp_path, mutate):
    lines = (FIXTURES / "transactions_data.csv").read_text().splitlines()
    bad = tmp_path / "transactions_data.csv"
    bad.write_text("\n".join([mutate(lines[0]), *lines[1:]]) + "\n")

    with pytest.raises(ing.SchemaMismatchError):
        ing.check_header(spark, str(bad), TRANSACTIONS_SCHEMA)


@pytest.mark.spark
def test_ingest_writes_nothing_when_validation_fails(spark, tmp_path, monkeypatch):
    src = tmp_path / "src"
    shutil.copytree(FIXTURES, src)
    customers = src / "customer_data.csv"
    lines = customers.read_text().splitlines()
    customers.write_text("\n".join([*lines, lines[1]]) + "\n")  # duplicate customer

    written = []
    monkeypatch.setattr(ing, "write_bronze", lambda df, name: written.append(name))

    with pytest.raises(ing.IngestValidationError):
        ing.ingest(spark, Settings(catalog="test"), str(src))
    assert written == []


@pytest.mark.spark
def test_ingest_writes_both_tables_to_bronze(spark, monkeypatch):
    written = []
    monkeypatch.setattr(ing, "write_bronze", lambda df, name: written.append(name))

    reports = ing.ingest(spark, Settings(catalog="test"), str(FIXTURES))
    assert written == ["test.bronze.customers", "test.bronze.transactions"]
    assert all(r.ok for r in reports)
