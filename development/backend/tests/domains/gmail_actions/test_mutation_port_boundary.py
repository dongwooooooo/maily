"""gmail_actions boundary test — docs/goals/backend-plans/gmail_actions.md
"경계 계약: GmailMutationPort".

Static(ast-based) check는 물리적 분리 invariant를 강제한다. read/sync
(`mail_intake.gmail_reader` / `GmailReaderPort`)와 write(`GmailMutationPort`)가
같은 module에서 import 가능하면 안 된다. Runtime check는 command ledger row 없이
Gmail write가 일어나지 않음을 강제한다.
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
    """gmail_actions는 mail_intake의 read/sync port를 import하지 않는다.
    write path와 read path는 물리적으로 분리된 package다."""
    for source_file in _all_source_files():
        imported = _imported_module_names(source_file)
        offenders = {name for name in imported if "mail_intake" in name or "gmail_reader" in name}
        assert not offenders, f"{source_file} imports read-path module(s): {offenders}"


def test_no_oauth_token_direct_read() -> None:
    """gmail_actions는 connected_gmail_accounts만 읽는다(workspace/status scoping
    전용, repository.py 참고). gmail_oauth_credentials는 절대 읽지 않으며 encrypted token
    table은 mail_sources 안에 남는다.
    """
    forbidden_tokens = {"gmail_oauth_credentials", "access_token_ciphertext", "refresh_token_ciphertext"}
    for source_file in _all_source_files():
        text = source_file.read_text()
        offenders = {token for token in forbidden_tokens if token in text}
        assert not offenders, f"{source_file} references OAuth token internals: {offenders}"


def test_write_only_through_mutation_port() -> None:
    """gmail_mutator.py/fake_mutator.py/live_mutator.py 밖의 module은 raw Gmail API
    client를 참조하지 않는다. 모든 write는 port를 거친다."""
    port_files = {"gmail_mutator.py", "fake_mutator.py", "live_mutator.py"}
    forbidden_tokens = {"googleapiclient", "messages().modify", "gmail_v1"}
    for source_file in _all_source_files():
        if source_file.name in port_files:
            continue
        text = source_file.read_text()
        offenders = {token for token in forbidden_tokens if token in text}
        assert not offenders, f"{source_file} bypasses GmailMutationPort: {offenders}"


async def test_all_writes_pass_command_ledger() -> None:
    """port의 유일한 method는 command_id를 받는다. raw action_type/payload로 호출할 수
    없고, ledger row가 없는 command_id에 대해서는 어떤 것도 mutate하지 않는다
    (structural + runtime enforcement)."""
    signature = inspect.signature(GmailMutationPort.apply)
    assert list(signature.parameters) == ["self", "connection", "command_id"]
    assert signature.parameters["command_id"].kind == inspect.Parameter.KEYWORD_ONLY

    mutator = FakeGmailMutationPort()
    with pytest.raises(NotFoundError):
        async with engine.begin() as connection:
            await mutator.apply(connection, command_id=uuid.uuid4())
