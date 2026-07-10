"""수동 Gmail API POC — 앱에 포함되지 않는 일회용 스크립트.

docs/areas/backend/db-schema.md에 남은 열린 질문을 확인한다:
- `format=metadata` 응답에 `snippet` 필드가 포함되는가?
- 설정된 Pub/Sub topic으로 `users.watch` 등록이 성공하는가?
- `Maily/{name}` 라벨이 Gmail UI에서 실제로 `Maily` 아래에 중첩되는가?

OAuth가 PKCE를 쓰므로 authorization code는 auth URL을 생성한 것과 같은
프로세스(같은 code_verifier)가 교환해야 한다. 사람의 동의 단계가 별도
턴의 실제 브라우저에서 일어나므로, scratch 파일로 상태를 넘기는 두 단계로
나눈다:

  # 1단계 — 브라우저에서 열 URL을 출력하고 flow 상태를 저장
  python scripts/gmail_poc.py start

  # 2단계 — 동의 후 리다이렉트된 URL을 교환하고 확인 항목 실행
  python scripts/gmail_poc.py finish "<redirected url>"

두 단계 모두 필요: cd development/backend && set -a && source .env && set +a
"""

import json
import os
import sys

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
STATE_FILE = "/tmp/maily_gmail_poc_flow_state.json"
TOKEN_FILE = "/tmp/maily_gmail_poc_token.json"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"missing env var: {name} (source .env 했는지 확인)")
    return value


def build_flow(code_verifier: str | None = None) -> Flow:
    client_id = require_env("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = require_env("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = require_env("GOOGLE_OAUTH_REDIRECT_URI")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def cmd_start() -> None:
    flow = build_flow()
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    with open(STATE_FILE, "w") as f:
        json.dump({"code_verifier": flow.code_verifier}, f)
    print(f"1. 브라우저에서 이 URL 열어서 로그인/동의:\n{auth_url}\n")
    print("2. 동의 후 리다이렉트된 전체 URL을 복사해서:")
    print('   python scripts/gmail_poc.py finish "<그 URL>"')


def cmd_finish(redirected_url: str) -> None:
    with open(STATE_FILE) as f:
        state = json.load(f)
    flow = build_flow(code_verifier=state["code_verifier"])
    flow.fetch_token(authorization_response=redirected_url)
    creds = flow.credentials
    print(f"토큰 발급 성공. 부여된 scope: {creds.scopes}")
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    run_checks(creds.token)


def load_cached_token() -> str:
    with open(TOKEN_FILE) as f:
        info = json.load(f)
    creds = Credentials.from_authorized_user_info(info, scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds.token


def cmd_retest_label_nesting() -> None:
    token = load_cached_token()

    print("\n=== 부모 라벨 'Maily' 먼저 생성 ===")
    parent = call(
        "POST",
        f"{GMAIL_API}/labels",
        token,
        json={
            "name": "Maily",
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    )
    print(json.dumps(parent, indent=2, ensure_ascii=False))

    print("\n=== 자식 라벨 'Maily/POC테스트2' 생성 ===")
    child = call(
        "POST",
        f"{GMAIL_API}/labels",
        token,
        json={
            "name": "Maily/POC테스트2",
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    )
    print(json.dumps(child, indent=2, ensure_ascii=False))
    print("\n>>> Gmail 웹 새로고침 후 왼쪽 라벨 목록에서 'Maily' 아래 'POC테스트2'로 중첩됐는지 육안 확인")


def call(method: str, url: str, token: str, **kwargs) -> dict:
    resp = httpx.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
    print(f"{method} {url} -> {resp.status_code}")
    resp.raise_for_status()
    return resp.json()


def run_checks(token: str) -> None:
    topic = require_env("GMAIL_PUBSUB_TOPIC")

    print("\n=== users.watch ===")
    watch = call(
        "POST", f"{GMAIL_API}/watch", token, json={"topicName": topic, "labelIds": ["INBOX"]}
    )
    print(json.dumps(watch, indent=2))

    print("\n=== 최근 메시지 1건 조회 ===")
    listed = call("GET", f"{GMAIL_API}/messages", token, params={"maxResults": 1})
    if not listed.get("messages"):
        print("받은편지함에 메시지가 없음 — 테스트 계정에 메일 하나 보내고 재실행")
        return
    message_id = listed["messages"][0]["id"]

    print("\n=== format=metadata (snippet 포함 여부 확인) ===")
    metadata = call(
        "GET",
        f"{GMAIL_API}/messages/{message_id}",
        token,
        params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"\n>>> snippet 필드 존재: {'snippet' in metadata}")

    print("\n=== Maily/POC테스트 라벨 생성 ===")
    label = call(
        "POST",
        f"{GMAIL_API}/labels",
        token,
        json={
            "name": "Maily/POC테스트",
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    )
    print(json.dumps(label, indent=2, ensure_ascii=False))
    print("\n>>> Gmail 웹 UI 왼쪽 라벨 목록에서 'Maily' 아래 'POC테스트'로 중첩됐는지 육안 확인")


if __name__ == "__main__":
    commands = ("start", "finish", "retest-label-nesting")
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.exit(
            "usage: gmail_poc.py start | gmail_poc.py finish <redirected_url> "
            "| gmail_poc.py retest-label-nesting"
        )
    if sys.argv[1] == "start":
        cmd_start()
    elif sys.argv[1] == "finish":
        if len(sys.argv) < 3:
            sys.exit("usage: gmail_poc.py finish <redirected_url>")
        cmd_finish(sys.argv[2])
    else:
        cmd_retest_label_nesting()
