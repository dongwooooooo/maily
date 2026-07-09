"""In-memory GmailMutationPort for TDD (docs/goals/backend-plans/gmail_actions.md §경계 계약).

Tracks a per-message set of "currently applied" Gmail label ids. `apply()`
reads the command row's `add_label_ids`/`remove_label_ids` payload, computes
the new label set, and reports `changed` based on whether the set actually
moved — this is what makes the "already read" / "already archived" no-op
scenario (`changed=False`) deterministically testable without a live Gmail
account. State is keyed by `message_id` when present, falling back to the
command's own id for message-independent actions (e.g. a future
message-less label action) so every command still has a stable mutation
target to track.
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
        """Test helper: set a message's starting Gmail label state."""
        self._label_state[message_id] = set(label_ids)

    def current_labels(self, message_id: uuid.UUID) -> set[str]:
        """Test helper: inspect a message's current (fake) Gmail label state."""
        return set(self._label_state.get(message_id, set()))

    def fail_next(self, command_id: uuid.UUID) -> None:
        """Test helper: make `apply()` raise for a specific command_id, to
        exercise the [부분실패]/failed-status path deterministically."""
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
