from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_gmail_actions_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        command_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("gmail_action_commands")
        )
        command_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("gmail_action_commands")
        )
        activity_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("activity_logs")
        )
        undo_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("undo_actions")
        )

    assert {"gmail_action_commands", "activity_logs", "undo_actions"} <= set(table_names)

    assert {fk["referred_table"] for fk in command_fks} == {
        "connected_gmail_accounts",
        "users",
        "gmail_messages",
    }
    assert any(
        set(c["column_names"]) == {"idempotency_key"} for c in command_unique
    )
    assert {fk["referred_table"] for fk in activity_fks} == {"workspaces", "gmail_action_commands", "users"}
    assert {fk["referred_table"] for fk in undo_fks} == {"activity_logs", "gmail_action_commands"}
