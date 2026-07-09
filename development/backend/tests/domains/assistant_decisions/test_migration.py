from sqlalchemy import inspect

from app.core.database import engine


async def test_migration_head_creates_assistant_eval_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        summary_job_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("summary_jobs")
        )
        message_summary_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("message_summaries")
        )
        importance_job_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("importance_jobs")
        )
        classification_unique = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints(
                "message_importance_classifications"
            )
        )

    assert {
        "summary_jobs",
        "message_summaries",
        "importance_jobs",
        "message_importance_classifications",
    } <= set(table_names)

    assert {fk["referred_table"] for fk in summary_job_fks} == {"gmail_messages"}
    assert any(set(c["column_names"]) == {"message_id"} for c in message_summary_unique)
    assert {fk["referred_table"] for fk in importance_job_fks} == {"gmail_messages"}
    assert any(set(c["column_names"]) == {"message_id"} for c in classification_unique)


async def test_migration_head_creates_assistant_rules_tables_with_constraints() -> None:
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
        rule_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("classification_rules")
        )
        suggestion_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("rule_suggestions")
        )
        cleanup_fks = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_foreign_keys("cleanup_proposals")
        )

    assert {"classification_rules", "rule_suggestions", "cleanup_proposals"} <= set(table_names)
    assert {fk["referred_table"] for fk in rule_fks} == {"workspaces", "service_labels"}
    assert {fk["referred_table"] for fk in suggestion_fks} == {
        "workspaces",
        "label_correction_signals",
    }
    assert {fk["referred_table"] for fk in cleanup_fks} == {
        "workspaces",
        "gmail_messages",
        "gmail_action_commands",
    }
