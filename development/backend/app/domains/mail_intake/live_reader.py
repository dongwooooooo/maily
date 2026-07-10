"""Live Gmail API reader — Task 4/5 범위 밖(Task 14).

실제 Gmail HTTP call을 wiring하려면 mail_sources의 credential injection handle, Gmail API
client library, OAuth refresh handling이 필요하다. 이 worktree에는 아직 어느 것도 build되지
않았다. 이 class는 docs/goals/backend-implementation-plan.md Task 4가 요구하는 file list를
만족하고, Task 14가 wiring한 뒤 `GmailReaderPort`의 concrete production implementation이
import할 이름을 제공하기 위해서만 존재한다. 모든 method는 NotImplementedError를 raise한다.
"""

import uuid

from app.domains.mail_intake.gmail_reader import (
    GmailReaderPort,
    HistoryResult,
    MessageIdList,
    MessageMetadata,
    WatchRegistration,
)


class LiveGmailReader(GmailReaderPort):
    async def register_watch(self, connected_account_id: uuid.UUID) -> WatchRegistration:
        raise NotImplementedError("live Gmail watch registration is Task 14 scope")

    async def history(
        self, connected_account_id: uuid.UUID, start_history_id: int | None
    ) -> HistoryResult:
        raise NotImplementedError("live Gmail history sync is Task 14 scope")

    async def get_message_metadata(
        self, connected_account_id: uuid.UUID, gmail_message_id: str
    ) -> MessageMetadata:
        raise NotImplementedError("live Gmail message metadata read is Task 14 scope")

    async def list_message_ids(self, connected_account_id: uuid.UUID) -> MessageIdList:
        raise NotImplementedError("live Gmail message enumeration is Task 14 scope")
