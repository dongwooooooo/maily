"""openapi.json 내보내기 — 프론트 codegen(openapi-typescript) 입력 파일.

서버를 띄우지 않고 app.openapi()를 그대로 덤프한다. 산출물은 레포에
커밋한다(development/backend/openapi.json) — diff 리뷰가 곧 API 계약
변경 리뷰다. 커밋본 신선도는 tests/api/test_openapi_export.py가 강제.

사용: (development/backend에서) .venv/bin/python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
# 스크립트 실행 시 sys.path[0]은 scripts/ 라서, site-packages에 설치된
# (오래된) app 복사본이 레포 코드를 가릴 수 있다 — 실제로 stale 스키마가
# export되는 사고가 있었다. 레포 경로를 항상 최우선으로 둔다.
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    target = BACKEND_DIR / "openapi.json"
    target.write_text(json.dumps(app.openapi(), sort_keys=True, indent=2) + "\n")
    print(f"exported: {target}")


if __name__ == "__main__":
    main()
