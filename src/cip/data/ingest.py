"""Raw COFINFAD CSVs in the UC volume -> bronze Delta tables.

Bronze = typed, otherwise untouched, plus lineage columns. The job validates each file *before*
writing, so a malformed upload never replaces a good bronze table.

Run on Databricks via the `ingest` job, or locally: `cip-ingest --catalog cip`.
"""

import argparse
import csv
import json
import logging
import operator
from dataclasses import asdict, dataclass
from functools import reduce

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from cip.config import Settings
from cip.data.schemas import (
    CORRUPT_RECORD_COL,
    CUSTOMERS_SCHEMA,
    TRANSACTIONS_SCHEMA,
    with_corrupt_record,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    file_name: str
    table: str
    schema: StructType
    key_columns: tuple[str, ...]
    unique_key: bool


SOURCES = (
    Source("customer_data.csv", "customers", CUSTOMERS_SCHEMA, ("customer_id",), unique_key=True),
    Source(
        "transactions_data.csv",
        "transactions",
        TRANSACTIONS_SCHEMA,
        ("customer_id", "date"),
        unique_key=False,
    ),
)


@dataclass
class IngestReport:
    table: str
    source_path: str
    rows: int
    corrupt_rows: int
    null_key_rows: int
    duplicate_key_rows: int

    @property
    def ok(self) -> bool:
        return (
            self.rows > 0
            and self.corrupt_rows == 0
            and self.null_key_rows == 0
            and self.duplicate_key_rows == 0
        )


class IngestValidationError(RuntimeError):
    pass


class SchemaMismatchError(IngestValidationError):
    pass


def check_header(spark: SparkSession, path: str, schema: StructType) -> None:
    """CSV columns bind by position, so a renamed/reordered column would load silently into the
    wrong field. Spark's own header check is skipped when a query prunes columns, so do it here."""
    first_line = spark.read.text(path).limit(1).first()
    header = next(csv.reader([first_line[0] if first_line else ""]))
    if header != schema.fieldNames():
        expected, got = schema.fieldNames(), header
        diff = [(i, e, g) for i, (e, g) in enumerate(zip(expected, got, strict=False)) if e != g]
        raise SchemaMismatchError(
            f"{path}: header does not match schema "
            f"(expected {len(expected)} cols, got {len(got)}; first diffs: {diff[:5]})"
        )


def read_source(spark: SparkSession, path: str, schema: StructType) -> DataFrame:
    """Read a CSV with an explicit schema; unparseable rows land in `_corrupt_record`."""
    return (
        spark.read.format("csv")
        .schema(with_corrupt_record(schema))
        .option("header", True)
        .option("mode", "PERMISSIVE")
        .option("columnNameOfCorruptRecord", CORRUPT_RECORD_COL)
        .load(path)
        .select(
            "*",
            F.col("_metadata.file_path").alias("_source_file"),
            F.current_timestamp().alias("_ingested_at"),
        )
    )


def validate(df: DataFrame, source: Source, table_name: str, path: str) -> IngestReport:
    """Single aggregation pass. References real columns alongside `_corrupt_record`, which Spark
    requires when querying the corrupt-record column of a raw CSV without caching."""
    keys = list(source.key_columns)
    any_null_key = reduce(operator.or_, [F.col(k).isNull() for k in keys])
    agg = df.agg(
        F.count(F.lit(1)).alias("rows"),
        F.sum(F.col(CORRUPT_RECORD_COL).isNotNull().cast("int")).alias("corrupt_rows"),
        F.sum(any_null_key.cast("int")).alias("null_key_rows"),
    ).first()

    duplicates = 0
    if source.unique_key:
        duplicates = (
            df.where(~any_null_key).groupBy(*keys).count().where(F.col("count") > 1).count()
        )

    return IngestReport(
        table=table_name,
        source_path=path,
        rows=agg["rows"],
        corrupt_rows=agg["corrupt_rows"] or 0,
        null_key_rows=agg["null_key_rows"] or 0,
        duplicate_key_rows=duplicates,
    )


def write_bronze(df: DataFrame, table_name: str) -> None:
    (
        df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table_name)
    )


def ingest(spark: SparkSession, settings: Settings, source_dir: str) -> list[IngestReport]:
    reports = []
    for source in SOURCES:
        path = f"{source_dir.rstrip('/')}/{source.file_name}"
        table_name = settings.table("bronze", source.table)
        check_header(spark, path, source.schema)
        df = read_source(spark, path, source.schema)

        report = validate(df, source, table_name, path)
        reports.append(report)
        log.info("validated %s", json.dumps(asdict(report)))
        if not report.ok:
            raise IngestValidationError(f"{path} failed validation: {asdict(report)}")

        write_bronze(df, table_name)
        log.info("wrote %s (%d rows)", table_name, report.rows)
    return reports


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source-dir", help="Defaults to the raw COFINFAD volume.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings(catalog=args.catalog)
    spark = SparkSession.builder.getOrCreate()

    reports = ingest(spark, settings, args.source_dir or settings.raw_volume_path)
    print(json.dumps([asdict(r) for r in reports], indent=2))


if __name__ == "__main__":
    main()
