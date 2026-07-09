# 개발 기반

기준 문서: `docs/current/product-wireframe-final.md`, `design/brand-color-final.md`, 현재 구현

## 버전 선정 원칙

- 메인 런타임은 2026-07-08 기준 LTS 또는 최신 안정 라인을 사용한다.
- 프레임워크와 라이브러리는 해당 런타임과 호환되는 최신 안정 버전으로 고정한다.
- 초기에는 exact version으로 잠근다. 업그레이드는 별도 라운드에서 한 번에 검증한다.

## 전체 구조

```text
development/
  frontend/     웹 프론트엔드
  backend/      API, 인증, Gmail 연동, 요약/정리 작업
  infra/        배포, 환경, 스케줄러, 시크릿, 모니터링
```

## 프론트엔드 스택

| 항목 | 버전 | 기준 |
|---|---:|---|
| Node.js | 24.18.x LTS | Next.js 16과 pnpm 11 기준 런타임 |
| pnpm | 11.10.x | workspace/package manager |
| Next.js | 16.2.10 | 메인 웹 앱 프레임워크 |
| React | 19.2.7 | Next.js와 호환되는 UI 런타임 |
| TypeScript | 6.0.3 | 타입 시스템 |
| Zustand | 5.0.14 | 클라이언트 상태 관리 |
| Tailwind CSS | 4.3.2 | 유틸리티 CSS. 기존 design token CSS와 병행 |
| ESLint | 9.39.4 | Next eslint plugin 체인과 호환되는 최신 9.x |
| Prettier | 3.9.4 | format |
| lucide-react | 1.23.0 | 공용 UI 아이콘 |

Next.js가 메인 앱 프레임워크다.

## 백엔드 스택

| 항목 | 버전 | 기준 |
|---|---:|---|
| Python | 3.14.x | Python 최신 안정 라인. Python에는 Node식 LTS가 없으므로 최신 안정판 기준 |
| FastAPI | 0.139.0 | API framework |
| Uvicorn | 0.50.2 | ASGI server |
| Pydantic | 2.13.4 | schema/settings |
| PostgreSQL | 18.4 | 주 데이터베이스 |
| Redis | 8.8.x | 캐시, rate limit, 작업 큐 보조 |
| SQLAlchemy | 2.0.51 | DB access |
| Alembic | 1.18.5 | migration |
| asyncpg | 0.31.0 | PostgreSQL async driver |
| PyJWT | 2.13.0 | JWT |
| Authlib | 1.7.2 | OAuth2 flow |
| google-auth-oauthlib | 1.4.0 | Gmail OAuth helper |
| Docker Engine | 29.x | 컨테이너 런타임 기준 |

현재 로컬 Mac에는 Python 3.12와 Docker 24가 있을 수 있다. 백엔드 실제 실행은 Python 3.14와 최신 Docker 환경에서 맞춘다.

## 프론트엔드 디렉토리

```text
development/frontend/
  src/
    app/                       Next.js App Router (/, /storage, /login, /first-application, /settings, /cleanup-review)
    app-shell/                 Maily 앱 셸 조립 (페이지별 MailyApp/ArchivePage/SettingsPage/CleanupPage)
    features/
      briefing/                오늘 브리핑, 카드, 상세 패널, mock data
      navigation/               사이드바, 상단바
      auth/                    로그인/첫 Gmail 적용 확인
      archive/                 보관함(예정 타임라인/라벨)
      settings/                서비스 계정 + 연결 메일 계정 + 알림 권한 (계정 스코프와 별도 도메인으로 분리하지 않음)
      cleanup/                 정리 검토/제안 승인
      notifications/           향후 알림 진입 라우팅 (Gmail 연동 전까지 보류)
      activity-log/            향후 활동 로그/Undo
    shared/
      ui/                      공용 UI
      hooks/                   공용 훅 (useAutoHideToast 등)
    styles/
      tokens.css               구현용 디자인 토큰
```

현재 구현된 영역은 `briefing`, `navigation`, `auth`, `archive`, `settings`, `cleanup`, `shared/ui`, `shared/hooks`, `app-shell`이다. `notifications`, `activity-log`는 아직 없음.

## 백엔드 경계

백엔드 모듈의 상세 경계는 `docs/areas/backend/module-boundaries.md`를 기준으로 한다.

- `C0 Backend Core`: API 실행 기반, DB session/transaction, Redis client, outbox, idempotency, job dispatch, logging, health.
- `D1 Identity & Workspace`: 서비스 로그인 사용자, workspace, session, membership.
- `D2 Connected Gmail Sources`: 연결 Gmail 계정, OAuth credential, 계정별 설정, pause/disconnect, account status.
- `D3 Gmail Intake & Snapshot`: Gmail watch/history/polling, `GmailReaderPort`, message snapshot, limited excerpt.
- `D4 Briefing & Item State`: 오늘 브리핑, 메일 상세 조회, seen/remind_later, 보관함 예정 타임라인.
- `D5 Labels & Classification`: 사용자 라벨, Gmail `Maily/` 라벨 매핑, 이동/수정 신호.
- `D6 Gmail Actions & Activity`: Gmail 변경 command, `GmailMutationPort`, 활동 로그, Undo 가능 여부.
- `D7 Assistant Decisions`: 메일 요약, 규칙 후보, 정리 제안, 승인/제외 큐, 자동 적용 기준.
- `D8 Notifications & Recovery`: browser push, 알림 route target, 권한/동기화 오류 복구 안내.

## 백엔드 디렉토리 원칙

백엔드 코드는 비즈니스 도메인을 최상위 구현 단위로 둔다. 개발 모델, repository,
service, router, event schema, job handler, 외부 adapter는 해당 도메인 내부에 배치한다.
공통 실행 기반만 `core/`에 둔다.

```text
development/backend/app/
  api/                  FastAPI router composition, request dependency
  core/                 config, DB, Redis, outbox, idempotency, logging
    jobs/               dispatcher, lock, retry, registry only
  db/                   SQLAlchemy base, Alembic migration env
  domains/
    identity/
    mail_sources/
    mail_intake/
      jobs/
    briefing/
      jobs/
    labels/
    gmail_actions/
      jobs/
    assistant_decisions/
      jobs/
    notifications/
      jobs/
```

전역 `app/jobs/`는 만들지 않는다. 예를 들어 Gmail sync worker는
`domains/mail_intake/jobs/`, Gmail 변경 실행은 `domains/gmail_actions/jobs/`,
요약 생성은 `domains/assistant_decisions/jobs/`가 소유한다.

## 인프라 경계

- 환경 변수와 시크릿
- OAuth redirect 환경
- worker/scheduler 실행 환경
- 데이터베이스와 migration
- 배포 파이프라인
- 로그, 모니터링, 알림

## 명령

```bash
corepack prepare pnpm@11.10.0 --activate
pnpm install
pnpm frontend:dev
pnpm frontend:lint
pnpm frontend:build
```

백엔드 로컬 데이터 서비스:

```bash
docker compose -f development/infra/docker/docker-compose.yml up -d
```

## 테스트 방침

현재 테스트 0개 (POC 단계). 설정값·규칙만 여기 적는다 — 무엇을 검증할지(엣지 케이스, 공유 컴포넌트 영향 범위, 시크릿 등)는 문서화하지 않고 `/code-review`·`/verify` 스킬 실행으로 처리한다.

- 프레임워크: Vitest + React Testing Library. E2E는 필요해지는 시점에 별도 결정 (지금은 범위 아님)
- 파일 위치: 대상 파일 옆에 co-location (`Foo.tsx` → `Foo.test.tsx`). `__tests__/` 디렉토리 금지
- 실행 명령: `pnpm test` — 테스트 첫 추가 시 devDependency와 함께 `package.json`에 스크립트 등록
- 우선순위: 순수 로직(상태 파생 — `hasUrgentItems` 같은 것, 향후 정리 제안 확신도 계산 등) 우선. 목업을 그대로 옮긴 프레젠테이션 컴포넌트는 후순위
- mock data는 `features/*/data/*.mock.ts` 기존 fixture 재사용, 테스트 전용 fixture 새로 만들지 않는다
- lint(`pnpm lint`)는 커밋 전 훅으로 자동 실행됨 (`.claude/settings.json` 참조)

## UI 구현 규칙

- 첫 화면은 앱 화면이다. 마케팅 landing page를 만들지 않는다.
- 카드는 액션 버튼, New 배지, 판단 라벨, 컬러 바 없이 스캔/선택만 담당한다.
- Gmail 변경 액션은 상세 패널 또는 정리 검토에서 처리한다.
- Gmail 변경이 발생하면 변경 결과와 Undo 가능 여부를 보여준다.
- 색상과 간격은 `development/frontend/src/styles/tokens.css`를 사용한다.
- 읽어야 하는 텍스트를 흐리게 만들기 위해 opacity를 낮추지 않는다.
- 카피는 `design/copy-principles.md`를 우선한다. 확정 카피가 없으면 `[미확정: ...]` placeholder를 둔다.
