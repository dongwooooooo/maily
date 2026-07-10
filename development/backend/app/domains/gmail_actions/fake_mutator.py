"""TDD용 in-memory GmailMutationPort(docs/goals/backend-plans/gmail_actions.md §경계 계약).

message별 "currently applied" Gmail label id set을 추적한다. `apply()`는 command row의
`add_label_ids`/`remove_label_ids` payload를 읽고 새 label set을 계산한 뒤, set이 실제로
움직였는지에 따라 `changed`를 보고한다. 이 덕분에 live Gmail account 없이도 "already read" /
"already archived" no-op scenario(`changed=False`)를 deterministic하게 test할 수 있다.
state는 `message_id`가 있으면 이를 key로 삼고, message-independent action(예: 미래의
message-less label action)에서는 command 자체 id로 fallback한다. 그래서 모든 command에
추적 가능한 stable mutation target이 있다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ExternalServiceError, NotFoundError
from app.domains.gmail_actions import repository
from app.domains.gmail_actions.gmail_mutator import GmailMutationPort, MutationResult


class FakeGmailMutationPort(GmailMutationPort):
    def __init__(self) -> None:
        self._label_state: dict[uuid.UUID, set[str]] = {}
        self._fail_command_ids: set[uuid.UUID] = set()

    def seed_labels(self, message_id: uuid.UUID, label_ids: set[str]) -> None:
        """test helper: message의 시작 Gmail label state를 설정한다."""
        self._label_state[message_id] = set(label_ids)

    def current_labels(self, message_id: uuid.UUID) -> set[str]:
        """test helper: message의 현재(fake) Gmail label state를 확인한다."""
        return set(self._label_state.get(message_id, set()))

    def fail_next(self, command_id: uuid.UUID) -> None:
        """test helper: 특정 command_id에서 `apply()`가 raise하게 한다.

        [부분실패]/failed-status path를 deterministic하게 검증하기 위한 helper다.
        """
        self._fail_command_ids.add(command_id)

    async def apply(
        self, connection: AsyncConnection, *, command_id: uuid.UUID
    ) -> MutationResult:
        command = await repository.get_command(connection, command_id=command_id)
        if command is None:
            raise NotFoundError(f"gmail_action_commands row not found: {command_id}")
        if command_id in self._fail_command_ids:
            raise ExternalServiceError("simulated Gmail API failure")

        mutation_key = command["message_id"] or command["id"]
        current = set(self._label_state.get(mutation_key, set()))
        add_ids = set(command["payload"].get("add_label_ids") or [])
        remove_ids = set(command["payload"].get("remove_label_ids") or [])

        new_state = (current - remove_ids) | add_ids
        changed = new_state != current
        self._label_state[mutation_key] = new_state
        return MutationResult(changed=changed)
