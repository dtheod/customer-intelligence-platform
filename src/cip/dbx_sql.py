"""Query Unity Catalog tables through the SQL warehouse (used by notebooks now, the gateway later).

Auth reuses the Databricks CLI profile (DATABRICKS_CONFIG_PROFILE) or DATABRICKS_HOST/_CLIENT_ID
env vars via databricks-sdk unified auth, so no tokens are handled here.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from cip.config import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pandas as pd


def open_connection(settings: Settings | None = None) -> Any:
    """Open a warehouse connection; caller must `.close()` it (notebooks). Prefer `connect()`."""
    from databricks import sql
    from databricks.sdk.core import Config

    settings = settings or get_settings()
    if not settings.warehouse_id:
        raise RuntimeError("CIP_WAREHOUSE_ID is not set (see .env.example)")

    cfg = Config(profile=settings.databricks_profile)
    return sql.connect(
        server_hostname=cfg.host.removeprefix("https://"),
        http_path=f"/sql/1.0/warehouses/{settings.warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
        catalog=settings.catalog,
    )


@contextmanager
def connect(settings: Settings | None = None) -> Iterator[Any]:
    conn = open_connection(settings)
    try:
        yield conn
    finally:
        conn.close()


def query_df(sql_text: str, params: dict[str, Any] | None = None, conn: Any = None) -> pd.DataFrame:
    """Run a query and return a pandas DataFrame. Pass `conn` to reuse a connection."""
    if conn is None:
        with connect() as c:
            return query_df(sql_text, params, c)
    with conn.cursor() as cur:
        cur.execute(sql_text, params or {})
        return cur.fetchall_arrow().to_pandas()
