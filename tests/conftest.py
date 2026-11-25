import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Homebrew's openjdk@17 is keg-only (not on PATH / java_home); use it when nothing else is set.
_BREW_JDK17 = Path("/opt/homebrew/opt/openjdk@17")
if "JAVA_HOME" not in os.environ and _BREW_JDK17.exists():
    os.environ["JAVA_HOME"] = str(_BREW_JDK17)


@pytest.fixture(scope="session")
def spark():
    """Local SparkSession for transformation tests. Requires Java 17."""
    from pyspark.sql import SparkSession

    session = (
        SparkSession.builder.master("local[2]")
        .appName("cip-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()
