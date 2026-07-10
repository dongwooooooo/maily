"""PR B3 — openapi.json 커밋본 drift 가드.

프론트 codegen(openapi-typescript)은 커밋된 openapi.json을 입력으로 쓴다.
계약(라우트·스키마)을 바꾸고 export를 다시 안 돌리면 이 테스트가 빨간불 —
CI 없이 로컬 스위트만으로 계약 파일 신선도를 강제한다.

갱신 방법: `python scripts/export_openapi.py`
"""

import json
from pathlib import Path

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[2]
OPENAPI_PATH = BACKEND_DIR / "openapi.json"


def test_committed_openapi_json_matches_app() -> None:
    assert OPENAPI_PATH.exists(), "openapi.json 없음 — python scripts/export_openapi.py 실행"
    committed = json.loads(OPENAPI_PATH.read_text())
    assert committed == app.openapi(), (
        "openapi.json이 앱 스키마와 다름 — python scripts/export_openapi.py로 갱신 후 커밋"
    )
