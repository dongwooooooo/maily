from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_mail_sources_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        account_indexes = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("connected_gmail_accounts")
        )
        credentials_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("gmail_oauth_credentials")
        )
        settings_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("gmail_source_settings")
        )

    assert {
        "connected_gmail_accounts",
        "gmail_oauth_credentials",
        "gmail_source_settings",
    } <= set(table_names)

    active_address_index = next(
        idx
        for idx in account_indexes
        if idx["name"] == "uq_connected_gmail_accounts_active_workspace_address"
    )
    assert active_address_index["unique"] is True
    assert set(active_address_index["column_names"]) == {"workspace_id", "gmail_address"}

    assert {fk["referred_table"] for fk in credentials_fks} == {"connected_gmail_accounts"}
    assert {fk["referred_table"] for fk in settings_fks} == {"connected_gmail_accounts"}
