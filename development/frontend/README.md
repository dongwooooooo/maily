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
  shared/ui/           공용 UI
  styles/tokens.css    구현용 디자인 토큰
```

소스 import는 `@/*` alias를 사용한다. Gmail 인증, Gmail API, LLM 호출, 저장소 작업은 백엔드 계약이 확정될 때 시작한다.
