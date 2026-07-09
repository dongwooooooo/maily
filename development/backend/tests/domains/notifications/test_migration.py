from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_notifications_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        subscription_columns = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("notification_subscriptions")
        )
        subscription_uniques = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints(
                "notification_subscriptions"
            )
        )
        subscription_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("notification_subscriptions")
        )
        event_columns = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("notification_events")
        )
        event_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("notification_events")
        )

    assert {"notification_subscriptions", "notification_events"} <= set(table_names)

    subscription_column_names = {col["name"] for col in subscription_columns}
    assert {"id", "user_id", "endpoint", "keys", "revoked_at"} <= subscription_column_names

    endpoint_unique = next(
        uc
        for uc in subscription_uniques
        if uc["name"] == "uq_notification_subscriptions_endpoint"
    )
    assert set(endpoint_unique["column_names"]) == {"endpoint"}
    assert {fk["referred_table"] for fk in subscription_fks} == {"users"}

    event_column_names = {col["name"] for col in event_columns}
    assert {
        "id",
        "workspace_id",
        "notification_type",
        "route_target",
        "read_at",
        "created_at",
    } <= event_column_names
    assert {fk["referred_table"] for fk in event_fks} == {"workspaces"}
