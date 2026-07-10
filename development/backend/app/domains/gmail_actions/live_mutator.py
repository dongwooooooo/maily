"""Live GmailMutationPort — 실제 Gmail `messages.modify` call.

Task 9 범위 밖이다(POC gate G4는 fake port만 요구 — docs/goals/backend-implementation-plan.md
Task 9 및 module-boundaries.md "모듈별 차단 조건: gmail_actions | Gmail write live 검증 지연"
참고). Task 9 file list에 맞춰 file이 존재하도록 둔 placeholder다. Task 14가 이를 실제로
구현하며, mail_sources를 통해 connected account의 OAuth credential을 resolve하고(복호화는 이
file 내부에서만 수행하며 domain service/job layer에서는 절대 수행하지 않음 — gmail_mutator.py
module docstring 참고) Gmail API를 호출한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.gmail_actions.gmail_mutator import GmailMutationPort, MutationResult


class LiveGmailMutationPort(GmailMutationPort):
    async def apply(
        self, connection: AsyncConnection, *, command_id: uuid.UUID
    ) -> MutationResult:
        raise NotImplementedError(
            "LiveGmailMutationPort is implemented in Task 14 (live Gmail API integration)"
        )
