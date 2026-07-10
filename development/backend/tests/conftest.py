from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    """test run마다 local dev DB를 깨끗한 head migration 상태로 reset한다."""
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
