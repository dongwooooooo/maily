"""`purge_disconnected_source` job — _integration-contract.md §2/§4, Task 13.

payload `{source_id}`, triggered by `gmail_source_disconnected`. Calls
every domain's PURGE_HANDLER(source_id) — module-boundaries.md §8's
disconnect/purge flow — in one transaction, in an EXPLICIT order that
respects the gmail_messages.id foreign-key graph across domains
(app.core.discovery.collect_purge_handlers's dict iteration order is
alphabetical by domain name, not FK-safe, so this job hardcodes the real
order instead of looping over that generic collection):

1. gmail_actions  — nulls gmail_action_commands.message_id (nullable FK;
   releases the reference while keeping the row — "minimal audit").
2. assistant_decisions — deletes rule_suggestions (its own NOT NULL FK
   into labels.label_correction_signals must clear before step 3) plus
   every other message-scoped ◆ table it owns.
3. labels — deletes label_correction_signals (now safe: nothing
   references them anymore).
4. briefing — deletes briefing_items/briefing_item_states/reminders.
5. mail_intake — deletes message_excerpts/gmail_message_labels, then
   gmail_messages itself (every other domain's FK into gmail_messages
   is already cleared by steps 1-4, so this is always safe now).
6. mail_sources — its own domain, last: purges the ◆ credential
   ciphertext and flips the account to its terminal `disconnected`
   status (disconnect_gmail_source already set `disconnecting` +
   revoked_at synchronously; this finishes the async half).

[멱등] every step below is naturally idempotent: deletes/updates filtered
by source_id/message_id simply affect zero rows on a re-run once their
target content is already gone. mail_sources.purge_source's explicit
`status == "disconnected"` guard (not the `account is None` check —
connected_gmail_accounts rows are never deleted) stops the last step
from re-bumping the account's version on every retry. Running this job
twice does not touch unrelated workspace data or error on missing rows.
"""

import uuid

import structlog

from app.core.database import engine

logger = structlog.get_logger()


async def run_purge_disconnected_source(connection, *, source_id: uuid.UUID) -> None:
    # Local imports — this job is imported from mail_sources/__init__.py
    # itself (JOB_HANDLERS registration), so top-level imports of every
    # other domain's purge module here would recreate the same
    # __init__.py-time circular import each purge.py's own local-import
    # comment avoids. Deferring until call time (well after every
    # domain has finished its own module init) sidesteps it entirely.
    from app.domains.assistant_decisions.purge import purge_source as purge_assistant_decisions
    from app.domains.briefing import purge_source as purge_briefing
    from app.domains.gmail_actions.purge import purge_source as purge_gmail_actions
    from app.domains.labels.purge import purge_source as purge_labels
    from app.domains.mail_intake.purge import purge_source as purge_mail_intake
    from app.domains.mail_sources.purge import purge_source as purge_mail_sources

    await purge_gmail_actions(connection, source_id=source_id)
    await purge_assistant_decisions(connection, source_id=source_id)
    await purge_labels(connection, source_id=source_id)
    await purge_briefing(connection, source_id=source_id)
    await purge_mail_intake(connection, source_id=source_id)
    await purge_mail_sources(connection, source_id=source_id)
    logger.info("연결 해제 계정 purge 완료", source_id=str(source_id))


async def purge_disconnected_source_job(payload: dict) -> None:
    """JOB_HANDLERS["purge_disconnected_source"] entry point — see __init__.py."""
    source_id = uuid.UUID(str(payload["source_id"]))
    async with engine.begin() as connection:
        await run_purge_disconnected_source(connection, source_id=source_id)
