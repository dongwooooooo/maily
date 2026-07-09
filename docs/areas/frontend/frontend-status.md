# 프론트엔드 진행 상태

`development/frontend/`가 `design/boards/v1/current/*.html` 하이파이 목업을 React 컴포넌트로 옮기는 작업. 이 문서는 진행 중 상태와 열린 이슈만 다룬다 — 확정 IA/화면 정의는 `docs/current/product-wireframe-final.md`, 디자인 원칙은 `DESIGN.md`가 근거.

## 포팅 진행

- 색상 토큰(`tokens.css`), 아코디언·아바타·배너·요약 태그 컴포넌트 스타일(`app-shell/App.css`) 반영됨
- 라우트 6개 실화면: `/`(오늘 브리핑), `/storage`, `/login`, `/first-application`, `/settings`, `/cleanup-review`. 08(알림 진입)은 UI 화면이 아니라 라우팅 스펙 문서라 보류
- 유닛테스트 시작(Vitest + React Testing Library) — 순수 로직(`computeHasUrgentItems`, `useAutoHideToast`)만, 컴포넌트 렌더 테스트는 아직 범위 밖. 방침은 `docs/current/technical-foundation.md`의 "테스트 방침" 참조

## IA 확정 요약 (재논의 금지, 변경 시 `docs/current/product-wireframe-final.md`도 갱신)

- 목록=탐색/선택, 상세=열람/처리 확정
- 카드에 New 배지·컬러 바·판단 라벨·완료/나중에 버튼 없음
- 상세 제목 행 icon-only 액션 3개(기본 배경 없음, hover 시 틸 fill 반전)
- 상단 `전체 메일 계정`이 유일한 계정 범위 제어, 벨은 알림 진입
- 낮은 확신 정리 제안은 개별 확인만
- 우선순위 화면 폐지 → **보관함**(예정 타임라인 + 라벨 탭). 오늘 브리핑 = since-last-visit 스냅샷(놓침은 별도 섹션 없이 시간 내림차순 흡수)
- 섹션 이원화: 기본 섹션=상태 파생(내부 용어, UI 비노출), 사용자 분류함=**라벨**(UI 용어 — Gmail `Maily/` 라벨과 동기화, 이동 목적지는 라벨만)
- 정리 검토 = 확신 임계값 2단(임계 미달은 침묵), 규칙 생성은 별도 `규칙 제안` 카드
- 사이드바 5항목: 오늘 브리핑/보관함/정리 검토/활동 로그/설정

## 열린 이슈

- 리스트 hover shortcut 노출 방식, 처리 후 다음 항목 자동 선택 여부 — 미결정
- pressed(10–12%) 상태 레이어 미구현 — `:active` 정의 자체가 없음
- 미확정 카피 부채: 02 정보 라벨·04 다이제스트 라벨·10 신뢰 문구 → `design/copy-principles.md` 확정 필요
