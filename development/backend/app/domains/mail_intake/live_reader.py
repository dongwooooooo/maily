"""Live Gmail API reader — out of scope for Task 4/5 (Task 14).

Wiring real Gmail HTTP calls requires: mail_sources' credential injection
handle, the Gmail API client library, and OAuth refresh handling — none of
that is built yet in this worktree. This class exists only so the file list
required by docs/goals/backend-implementation-plan.md Task 4 is satisfied
and so `GmailReaderPort`'s concrete production implementation has a name to
import once Task 14 wires it in. Every method raises NotImplementedError.
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
