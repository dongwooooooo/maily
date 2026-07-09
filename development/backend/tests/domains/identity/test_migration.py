from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_identity_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        users_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("users")
        )
        members_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("workspace_members")
        )
        members_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("workspace_members")
        )
        sessions_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("sessions")
        )

    assert {"users", "workspaces", "workspace_members", "sessions"} <= set(table_names)
    assert any(c["column_names"] == ["google_subject"] for c in users_unique)
    assert any(
        set(c["column_names"]) == {"workspace_id", "user_id"} for c in members_unique
    )
    assert {fk["referred_table"] for fk in members_fks} == {"workspaces", "users"}
    assert {fk["referred_table"] for fk in sessions_fks} == {"users", "workspaces"}
