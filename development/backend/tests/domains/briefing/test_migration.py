from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_briefing_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        items_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("briefing_items")
        )
        items_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("briefing_items")
        )
        states_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("briefing_item_states")
        )
        states_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("briefing_item_states")
        )
        reminders_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("reminders")
        )

    assert {"briefing_items", "briefing_item_states", "reminders"} <= set(table_names)

    assert {fk["referred_table"] for fk in items_fks} == {
        "workspaces",
        "connected_gmail_accounts",
        "gmail_messages",
    }
    assert any(
        set(c["column_names"]) == {"connected_account_id", "message_id"} for c in items_unique
    )

    assert {fk["referred_table"] for fk in states_fks} == {"workspaces", "gmail_messages"}
    assert any(set(c["column_names"]) == {"message_id"} for c in states_unique)

    assert {fk["referred_table"] for fk in reminders_fks} == {"briefing_item_states"}
