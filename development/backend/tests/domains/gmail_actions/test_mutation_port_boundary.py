"""Boundary tests for gmail_actions — docs/goals/backend-plans/gmail_actions.md
"경계 계약: GmailMutationPort".

Static (ast-based) checks enforce the physical separation invariant: read/sync
(`mail_intake.gmail_reader` / `GmailReaderPort`) and write (`GmailMutationPort`)
must never be importable from the same module. Runtime checks enforce that
Gmail writes cannot happen without a command ledger row.
"""

import ast
import inspect
import uuid
from pathlib import Path

import pytest

from app.core.database import engine
from app.core.errors import NotFoundError
from app.domains import gmail_actions
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.gmail_mutator import GmailMutationPort

DOMAIN_DIR = Path(gmail_actions.__file__).resolve().parent


def _all_source_files() -> list[Path]:
    return sorted(DOMAIN_DIR.rglob("*.py"))


def _imported_module_names(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_mail_intake_reader_import() -> None:
    """gmail_actions never imports mail_intake's read/sync port — write and
    read paths are physically separate packages."""
    for source_file in _all_source_files():
        imported = _imported_module_names(source_file)
        offenders = {name for name in imported if "mail_intake" in name or "gmail_reader" in name}
        assert not offenders, f"{source_file} imports read-path module(s): {offenders}"


def test_no_oauth_token_direct_read() -> None:
    """gmail_actions reads connected_gmail_accounts (workspace/status scoping
    only, see repository.py) but never gmail_oauth_credentials — the
    encrypted token table stays inside mail_sources.
    """
    forbidden_tokens = {"gmail_oauth_credentials", "access_token_ciphertext", "refresh_token_ciphertext"}
    for source_file in _all_source_files():
        text = source_file.read_text()
        offenders = {token for token in forbidden_tokens if token in text}
        assert not offenders, f"{source_file} references OAuth token internals: {offenders}"


def test_write_only_through_mutation_port() -> None:
    """No module outside gmail_mutator.py/fake_mutator.py/live_mutator.py
    references a raw Gmail API client — every write goes through the port."""
    port_files = {"gmail_mutator.py", "fake_mutator.py", "live_mutator.py"}
    forbidden_tokens = {"googleapiclient", "messages().modify", "gmail_v1"}
    for source_file in _all_source_files():
        if source_file.name in port_files:
            continue
        text = source_file.read_text()
        offenders = {token for token in forbidden_tokens if token in text}
        assert not offenders, f"{source_file} bypasses GmailMutationPort: {offenders}"


async def test_all_writes_pass_command_ledger() -> None:
    """The port's only method takes a command_id — it cannot be invoked with
    a raw action_type/payload, and it refuses to mutate anything for a
    command_id that has no ledger row (structural + runtime enforcement)."""
    signature = inspect.signature(GmailMutationPort.apply)
    assert list(signature.parameters) == ["self", "connection", "command_id"]
    assert signature.parameters["command_id"].kind == inspect.Parameter.KEYWORD_ONLY

    mutator = FakeGmailMutationPort()
    with pytest.raises(NotFoundError):
        async with engine.begin() as connection:
            await mutator.apply(connection, command_id=uuid.uuid4())
