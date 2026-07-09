from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_labels_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        service_label_indexes = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("service_labels")
        )
        mapping_columns = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("gmail_label_mappings")
        )
        mapping_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("gmail_label_mappings")
        )
        signal_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("label_correction_signals")
        )

    assert {
        "service_labels",
        "gmail_label_mappings",
        "label_correction_signals",
    } <= set(table_names)

    name_uniques = next(
        uc for uc in service_label_indexes if uc["name"] == "uq_service_labels_workspace_id_name"
    )
    assert set(name_uniques["column_names"]) == {"workspace_id", "name"}

    mapping_column_names = {col["name"] for col in mapping_columns}
    assert {
        "id",
        "service_label_id",
        "connected_account_id",
        "gmail_label_id",
        "gmail_label_name",
    } <= mapping_column_names

    assert {fk["referred_table"] for fk in mapping_fks} == {
        "service_labels",
        "connected_gmail_accounts",
    }
    assert {fk["referred_table"] for fk in signal_fks} == {
        "gmail_messages",
        "service_labels",
        "users",
    }
