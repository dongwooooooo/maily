"""openapi.json 내보내기 — 프론트 codegen(openapi-typescript) 입력 파일.

서버를 띄우지 않고 app.openapi()를 그대로 덤프한다. 산출물은 레포에
커밋한다(development/backend/openapi.json) — diff 리뷰가 곧 API 계약
변경 리뷰다. 커밋본 신선도는 tests/api/test_openapi_export.py가 강제.

사용: (development/backend에서) .venv/bin/python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    target = BACKEND_DIR / "openapi.json"
    target.write_text(json.dumps(app.openapi(), sort_keys=True, indent=2) + "\n")
    print(f"exported: {target}")


if __name__ == "__main__":
    main()
