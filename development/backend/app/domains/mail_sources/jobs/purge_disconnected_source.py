"""`purge_disconnected_source` job — _integration-contract.md §2/§4, Task 13.

payload `{source_id}`이며 `gmail_source_disconnected`가 trigger한다. 모든 domain의
PURGE_HANDLER(source_id)를 module-boundaries.md §8의 disconnect/purge flow에 따라 하나의
transaction에서 호출한다. 호출 순서는 domain 간 gmail_messages.id foreign-key graph를 존중하는
EXPLICIT order다(app.core.discovery.collect_purge_handlers의 dict iteration order는 domain name
alphabetical이며 FK-safe가 아니므로, 이 job은 generic collection을 loop하지 않고 실제 순서를
hardcode한다):

1. gmail_actions — gmail_action_commands.message_id를 null 처리한다(nullable FK; row를
   유지하면서 reference release — "minimal audit").
2. assistant_decisions — rule_suggestions(labels.label_correction_signals로 향하는 자체
   NOT NULL FK를 step 3 전에 clear해야 함)와 자신이 소유한 다른 모든 message-scoped ◆ table을
   delete한다.
3. labels — label_correction_signals를 delete한다(이제 아무것도 이를 reference하지 않아 safe).
4. briefing — briefing_items/briefing_item_states/reminders를 delete한다.
5. mail_intake — message_excerpts/gmail_message_labels를 delete한 뒤 gmail_messages 자체를
   delete한다(다른 모든 domain의 gmail_messages FK는 step 1-4에서 이미 clear되었으므로 이제 항상 safe).
6. mail_sources — 자기 domain이며 마지막이다. ◆ credential ciphertext를 purge하고 account를
   terminal `disconnected` status로 전환한다(disconnect_gmail_source가 이미 `disconnecting` +
   revoked_at을 synchronously 설정했고, 여기서 async half를 마무리한다).

[멱등] 아래 모든 step은 자연스럽게 idempotent하다. source_id/message_id로 filter한
delete/update는 target content가 이미 사라진 뒤 재실행되면 단순히 0 row에 영향만 준다.
mail_sources.purge_source의 명시적 `status == "disconnected"` guard(`account is None` check가
아님 — connected_gmail_accounts row는 절대 delete되지 않음)가 마지막 step이 retry마다 account
version을 다시 bump하지 않도록 막는다. 이 job을 두 번 실행해도 unrelated workspace data를
건드리지 않고, missing row에서 error도 내지 않는다.
"""

import uuid

import structlog

from app.core.database import engine

logger = structlog.get_logger()


async def run_purge_disconnected_source(connection, *, source_id: uuid.UUID) -> None:
    # local import를 사용한다. 이 job 자체가 mail_sources/__init__.py에서 import되므로
    # (JOB_HANDLERS registration), 여기서 다른 모든 domain의 purge module을 top-level import하면
    # 각 purge.py의 local-import comment가 피하려는 __init__.py-time circular import가 재현된다.
    # 모든 domain의 module init이 끝난 뒤인 call time까지 미루면 이를 완전히 피할 수 있다.
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
    """JOB_HANDLERS["purge_disconnected_source"] entry point — __init__.py 참고."""
    source_id = uuid.UUID(str(payload["source_id"]))
    async with engine.begin() as connection:
        await run_purge_disconnected_source(connection, source_id=source_id)
