from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import engine


async def _inspect_migrated_schema(async_engine: AsyncEngine) -> tuple[list[str], dict[str, list]]:
    async with async_engine.connect() as connection:
        table_names = await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        unique_constraints = await connection.run_sync(
            lambda sync_conn: {
                table: inspect(sync_conn).get_unique_constraints(table)
                for table in ("outbox_events", "job_runs", "idempotency_keys")
            }
        )
    return table_names, unique_constraints


async def test_migration_head_creates_core_tables_with_unique_constraints() -> None:
    table_names, unique_constraints = await _inspect_migrated_schema(engine)

    assert {"outbox_events", "job_runs", "idempotency_keys"} <= set(table_names)
    assert any(
        set(c["column_names"]) == {"event_type", "idempotency_key"}
        for c in unique_constraints["outbox_events"]
    )
    assert any(
        set(c["column_names"]) == {"job_type", "idempotency_key"}
        for c in unique_constraints["job_runs"]
    )
    assert any(
        set(c["column_names"]) == {"scope", "key"}
        for c in unique_constraints["idempotency_keys"]
    )
