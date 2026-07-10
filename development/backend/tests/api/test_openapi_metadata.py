"""PR B1 — OpenAPI 메타데이터 계약.

프론트 codegen(openapi-typescript)이 소비할 스키마 품질을 고정한다:
version 명시, operationId = 라우트 함수명(전 operation 유일),
response_model 없는 라우트 0건.
"""

from app.main import app


def _operations() -> list[tuple[str, str, dict]]:
    schema = app.openapi()
    methods = {"get", "post", "put", "patch", "delete"}
    return [
        (path, method, operation)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method in methods
    ]


def test_openapi_version_is_set() -> None:
    assert app.openapi()["info"]["version"] == "0.1.0"


def test_operation_ids_are_route_names_and_unique() -> None:
    operation_ids = [operation["operationId"] for _, _, operation in _operations()]
    assert len(operation_ids) == len(set(operation_ids)), (
        "duplicate operationId — route function names must be unique across domains"
    )
    # generate_unique_id_function=route.name — 자동 생성 접미사(경로+메서드)가
    # 붙은 장황한 이름이 하나라도 남아 있으면 실패해야 한다.
    # 실패 원인은 둘 중 하나: (a) 커스텀 generate_unique_id_function이 제거돼
    # FastAPI 기본 fallback(경로 치환으로 "__" 생성)이 샜거나, (b) 라우트
    # 함수명 자체에 "__"가 들어감 — 후자는 함수명을 고치면 된다.
    for path, method, operation in _operations():
        assert "__" not in operation["operationId"], (path, method, operation["operationId"])


def test_pubsub_ack_response_has_schema() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/intake/pubsub"]["post"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    component = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert "deduped" in component["properties"]


def test_rule_approve_response_has_schema() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/rules/{suggestion_id}/approve"]["post"]
    ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/RuleSuggestion")


def test_every_operation_declares_json_response_schema() -> None:
    """2xx 응답에 스키마 없는 operation이 새로 생기는 것을 막는 회귀 가드."""
    for path, method, operation in _operations():
        success = [
            body
            for status, response in operation["responses"].items()
            if status.startswith("2") and (body := response.get("content", {}).get("application/json"))
        ]
        if not success:
            continue
        for body in success:
            assert body.get("schema"), (path, method, "2xx response missing schema")
