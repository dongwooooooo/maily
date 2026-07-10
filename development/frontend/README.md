# Maily Frontend

Maily 웹 프론트엔드다. 현재 단계는 `docs/current/product-wireframe-final.md`의 기획을 기준으로 가짜 데이터 기반 제품 화면을 먼저 고정한다.

## 스택

- Next.js 16.2.10
- React 19
- TypeScript
- Zustand
- Tailwind CSS
- ESLint
- Prettier
- pnpm
- CSS design tokens
- lucide-react

## 명령

```bash
corepack prepare pnpm@11.10.0 --activate
pnpm install
pnpm dev
pnpm lint
pnpm build
```

## 소스 구조

```text
src/
  app/                 Next.js App Router
  app-shell/           앱 조립과 셸 CSS
  features/            제품 기능 단위 코드
  shared/api/          API 클라이언트 (openapi-fetch + 생성 타입)
  shared/ui/           공용 UI
  styles/tokens.css    구현용 디자인 토큰
```

소스 import는 `@/*` alias를 사용한다.

## API 클라이언트

백엔드 계약은 `development/backend/openapi.json`이 단일 근거다 (`_integration-contract.md` §6).

- 타입 재생성: 백엔드에서 `python scripts/export_openapi.py` 후 여기서 `pnpm codegen:api`
- `src/shared/api/schema.d.ts`는 생성물이지만 커밋 대상 — 수동 편집 금지
- 에러는 `{"error":{code,message,request_id,details?}}` 봉투 단일 형식, `errors.ts::toApiError`로 정규화
- `POST /actions`, `POST /messages/{id}/move`는 `Idempotency-Key` 헤더 필수 — `idempotency.ts::newIdempotencyKey()` 사용, 재시도 시 같은 키 재사용
- `client.ts`는 `import 'client-only'` 가드 — 서버 컴포넌트에서 import하면 빌드 에러(의도된 것)

호출 규약 (모든 feature `api.ts`가 이 형태를 따른다):

```ts
import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'

const { data, error, response } = await apiClient.GET('/briefing/today')
if (error) throw toApiError(response.status, error)
// data는 생성 타입으로 좁혀져 있음
```

## 환경변수 (.env.local)

`.env.local`을 직접 만들어 아래 값을 넣는다:

```bash
# 백엔드 dev 서버 주소 (uvicorn 기본 포트)
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
# Google Identity Services 클라이언트 ID (백엔드 .env의 GOOGLE_OAUTH_CLIENT_ID와 동일 값)
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
```
