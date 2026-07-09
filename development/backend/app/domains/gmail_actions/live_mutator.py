"""Live GmailMutationPort — real Gmail `messages.modify` calls.

Out of scope for Task 9 (POC gate G4 only requires the fake port — see
docs/goals/backend-implementation-plan.md Task 9 and module-boundaries.md
"모듈별 차단 조건: gmail_actions | Gmail write live 검증 지연"). This is a
placeholder so the file exists per the Task 9 file list; Task 14 implements
it for real, resolving the connected account's OAuth credential via
mail_sources (decrypting only inside this file, never in the domain
service/job layer — see gmail_mutator.py's module docstring) and calling the
Gmail API.
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
