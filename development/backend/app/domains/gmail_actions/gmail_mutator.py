"""GmailMutationPort — the only way gmail_actions is allowed to write to Gmail.

See docs/goals/backend-plans/gmail_actions.md "경계 계약: GmailMutationPort":
the interface is a single `apply(command_id)` method. The port reads the
command row itself (connected_account_id, action_type, payload) from the
ledger — it cannot be called without a command already existing, which is
exactly the "no Gmail write without a command row" invariant expressed as a
method signature. mark_read/archive/read_and_archive/label_apply are not
separate port methods: Gmail's own `messages.modify` collapses all of them
into one add/remove label id call, and `gmail_action_commands.payload`
already normalizes every action_type into `{add_label_ids, remove_label_ids}`
before the port ever sees it (see schemas.py / service.py). "Reverse mutation
when supported" is a ledger-level concept (undo.py computes the reverse
payload and inserts a new command) rather than a distinct port method — the
port only ever applies whatever command it's given, forward or reverse.
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
        """Apply the Gmail mutation described by the command row.

        Implementations look up the command by id (never accept a bare
        action_type/payload from a caller), resolve the connected
        account's credential (live_mutator only — fake_mutator has no
        credential access at all), and call Gmail's `messages.modify`
        equivalent with `payload["add_label_ids"]` /
        `payload["remove_label_ids"]`. Must be idempotent: re-applying an
        already-applied command is safe and simply reports whether this
        call itself changed anything.
        """
        raise NotImplementedError
