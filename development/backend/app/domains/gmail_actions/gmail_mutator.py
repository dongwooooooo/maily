"""GmailMutationPort — gmail_actions가 Gmail에 write할 수 있는 유일한 방법.

See docs/goals/backend-plans/gmail_actions.md "경계 계약: GmailMutationPort":
interface는 단일 `apply(command_id)` method다. port는 ledger에서 command row 자체
(connected_account_id, action_type, payload)를 읽는다. 이미 존재하는 command 없이 호출할 수
없으므로, "no Gmail write without a command row" invariant가 method signature로 표현된다.
mark_read/archive/read_and_archive/label_apply는 별도 port method가 아니다. Gmail의
`messages.modify` 자체가 이를 모두 하나의 add/remove label id call로 접고,
`gmail_action_commands.payload`는 port가 보기 전에 이미 모든 action_type을
`{add_label_ids, remove_label_ids}`로 normalize한다(schemas.py / service.py 참고).
"Reverse mutation when supported"는 별도 port method가 아니라 ledger-level concept이다
(undo.py가 reverse payload를 계산하고 새 command를 insert). port는 forward든 reverse든
전달받은 command만 apply한다.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class MutationResult:
    changed: bool


class GmailMutationPort(ABC):
    @abstractmethod
    async def apply(
        self, connection: AsyncConnection, *, command_id: uuid.UUID
    ) -> MutationResult:
        """command row가 설명하는 Gmail mutation을 apply한다.

        implementation은 id로 command를 lookup하고(caller의 bare action_type/payload를 받지
        않음), connected account의 credential을 resolve한 뒤(live_mutator 전용이며 fake_mutator는
        credential access가 전혀 없음), `payload["add_label_ids"]` /
        `payload["remove_label_ids"]`로 Gmail의 `messages.modify` equivalent를 호출한다.
        idempotent해야 한다. 이미 applied된 command를 다시 apply해도 안전하며, 이 호출 자체가
        무엇을 바꿨는지만 보고한다.
        """
        raise NotImplementedError
