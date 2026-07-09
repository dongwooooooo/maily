# AI 메일 비서 — 제품 기획·와이어프레임 최종 통합본

작성일: 2026-07-06. 기존 product-plan.md · mail-assistant-wireframe-direction.md · wireframe-generation-brief.md 3종을 중복 제거해 통합하고, 이번 브랜드 컬러 라운드의 확정 사항을 반영한 최종본이다. 색·톤 상세는 `design/brand-color-final.md` 참조.

---

## 1. 제품 정의

AI 메일 비서는 여러 Gmail 계정에서 중요한 메일을 선별해 브리핑하고, 필요한 메일만 빠르게 처리하도록 돕는 웹 서비스다.

- Gmail을 대체하는 메일 클라이언트가 아니다. 원문 확인·답장·발송은 Gmail에서 한다
- 이 서비스는 Gmail 위에 얹히는 **브리핑 / 우선순위 / 정리 보조 레이어**다
- 제품의 중심은 메일 목록이 아니라 **브리핑**이다

사용자가 브리핑에서 알아야 할 것: 자리 비운 사이 온 중요 메일 / 지금 행동이 필요한 것 / 미뤄도 되는 것 / 비서가 이미 정리한 것 / 승인·수정이 필요한 것.

## 2. 대상 사용자와 문제

대표 페르소나: **중요한 메일을 놓치지 않으면서 반복 확인·판단·정리 시간을 줄이고 싶은 멀티계정 Gmail 사용자.** 새 메일함이 아니라 조용한 브리핑 레이어가 필요한 사람.

주요 문제:

- 여러 계정에 메일이 흩어져 중요한 메일을 놓친다
- 안 읽은 메일은 많지만 지금 처리할 메일이 무엇인지 모른다
- 라벨/아카이브/뉴스레터 정리를 직접 관리하기 번거롭다
- 알림이 많을수록 중요한 신호를 무시하게 된다
- 자동화가 Gmail에서 무엇을 바꿨는지 안 보이면 신뢰할 수 없다

## 3. 제품 범위

**포함:** Google 로그인 · Gmail 계정 연결(복수) · 전체 계정 브리핑 · 계정별 우선순위 상세 · 메일 요약 · Gmail 상태 표시 · 라벨/아카이브 제안과 적용 상태 · 브리핑 섹션 사용자화 · 브라우저 알림 · 정리 제안 승인 · 활동 로그와 Undo

**제외:** 자체 메일 작성/발송 · Gmail 전체 대체 UI · 모바일 앱 · 전체 메일 탐색용 inbox · 긴 온보딩 튜토리얼 · 상세한 AI 판단 이유 노출

## 4. 계정 모델

서비스 로그인 계정과 연결된 Gmail 계정을 분리한다.

- 서비스 로그인: 사용자를 식별하는 대표 계정 1개 (Google 로그인)
- 연결 Gmail 계정: 브리핑·분석·알림·정리 대상 **메일 소스** (설정에서 OAuth로 추가)
- 이미 연결된 이메일로 재로그인하면 중복 워크스페이스를 만들지 않고 기존 워크스페이스로 안내

표시 규칙:

- 계정별 사용자 지정 표시 이름, 없으면 이메일 주소, 이름 충돌 시 짧은 이메일 힌트 (`Work · partner@`)
- 전체 보기의 모든 메일 카드에 계정 배지 필수
- 연결 계정은 사이드바 1차 내비가 아니라 상단 컨텍스트 셀렉터·설정·배지로만 노출

```text
[All accounts v]
All accounts
Personal                      synced
work@company.com              syncing 62%
school@gmail.com              permission needed
```

계정 행에는 Finder/iCloud식 컴팩트 상태 아이콘: synced / syncing / permission needed / error / paused.

## 5. 정보 구조

```text
좌측 사이드바                     상단 바                          본문
- (최상단) Maily 로고            - [전체 메일 계정 v] 컨트롤       - 메인: 브리핑 섹션 + 메일 카드
- 오늘 브리핑 (+섹션 앵커 서브내비)   (브리핑 대상 Gmail 범위 단일 제어,  - 우측: 선택 항목 상세 패널
- 우선순위                        동기화 상태 포함)
- 정리 검토                     - 알림 벨 (알림 진입 전용)
- 활동 로그                     ※ 페이지 제목은 상단바에 반복하지 않음
- 설정
- (최하단) 서비스 계정/워크스페이스
```

계층 규칙(Phase 0-5 확정): 좌측 최상단 = 제품 로고 / 좌측 최하단 = 서비스 로그인 계정(dongwoo 등) / 상단 컨트롤 = 브리핑 대상 메일 계정 범위 / 벨 = 알림함(서비스 알림·메일 알림 그룹 구분). 사이드바 서브내비는 필터가 아니라 같은 목록 안의 섹션 앵커다.

절제된 데스크톱 SaaS 셸. 밀도는 있되 읽기 쉬운 위계.

## 6. 핵심 화면 (와이어프레임 10종, 제작 순서)

1. **로그인** — `Google로 로그인하기`만. 마케팅 카피 최소화
2. **첫 Gmail 적용 확인** — 대상 계정 / 권한 요약 / "언제든 해제 가능" 통제 문구 / 낮은 확신 정리는 승인 필요 / `적용 시작`. 멀티스텝 위저드 금지, 시작 후 바로 메인으로 (큰 분석 진행 화면에 가두지 않기)
3. **메인 브리핑 — 기본 상태** — 전체 계정 브리핑, 섹션, 카드, 우측 상세 패널, 컴팩트 업데이트 표시
4. **메인 브리핑 — 빈 상태** — "오늘 급하게 확인할 메일은 없습니다" + 전체 우선순위 보기 / 알림 설정 확인. 안심으로 읽혀야 하고 비어 보이면 안 됨
5. **메인 브리핑 — 확인함/완료/나중에 상태**
6. **메일 카드 + 우측 상세 패널**
7. **보관함** — 우선순위 화면 폐지 후 대체(2026-07-06 확정). 두 보기: **예정**(재알림·기한 타임라인 — 오늘/내일/이번 주) + **내 섹션**(사용자 분류함 허브: 결제·읽어볼 것 + 새 섹션 만들기). 지나간 보고는 쌓아두지 않는다 — 놓침·누적은 since-last-visit 브리핑이 받는다. 브리핑=지금까지(스냅샷), 보관함=앞으로(예정)+주제(분류)로 축 분리
8. **알림 진입 상태** — 종류별 직행: 누락 중요 메일→오늘 브리핑 놓침 섹션 / 단일 리마인드→해당 상세 패널 / 전체 브리핑→오늘 브리핑 / 정리 승인→정리 검토 / 권한·동기화 오류→연결 계정. 일반 알림 랜딩 페이지 금지
9. **연결 계정 설정** — 계정 목록, 표시 이름 수정, 배지, 동기화·권한 상태, 계정별 AI 요약/브리핑 포함/알림 ON-OFF, 연결 해제
10. **정리 검토 / 승인** — 승인이 필요한 제안만 모이는 큐. 확신 임계값 2단: 자동 실행 기준 이상은 자동 적용(활동 로그+Undo), 제안 기준 미달은 제안하지 않음(침묵). 개별 확인/제외만(`Approve all` 등 다건 확정 없음 — 0-5h), 전후 Gmail 상태 텍스트 표기. 규칙 생성은 승인 옵션이 아니라 **별도 `규칙 제안` 카드**(반복 승인 이력 등 근거 명시, 승인 시 평문 확인+Undo)

## 7. 브리핑 섹션

기본: **중요 · 답장 필요 · 나중에 봐도 됨 · 정리됨 · 승인 필요**
사용자 섹션 예: 채용 · 결제 · GitHub · 학교 · 읽어볼 것

사용자화: 이름 변경 / 숨김·표시 / 순서 변경 / 새 섹션 생성 / 메일 이동 / **`다음부터 비슷한 메일은 여기로`**

섹션 이원화(확정): 기본 섹션은 상태/판단에서 파생되는 목록이고, 사용자 분류함은 **라벨**이다(UI 용어 확정 — "섹션"은 내부 문서 용어로만 쓰고 화면에 노출하지 않는다. 라벨은 Gmail `Maily/` 라벨과 동기화되므로 이름이 실체와 일치). `이동`의 목적지는 **라벨(+새 라벨)만** — 기본 섹션 간 이동은 액션의 결과(읽음 처리→완료 등)로만 일어난다.

규칙 확정은 평문으로 확인한다:

```text
앞으로 이 발신자의 계약·결제 알림은 Payments에 표시합니다. [Undo]
```

## 8. 메일 카드 원칙 (Phase 0-4·0-5 확정 반영)

목록은 탐색/선택만, 상세는 열람/처리 확정을 담당한다. 카드는 내용 스캔에 필요한 정보만 담는다: **제목 / 보낸 사람·시간 / 짧은 요약**. 계정 맥락은 카드 내부가 아니라 계정 그룹 소제목(계정 라인)으로 전달한다.

```text
업무 계정                        ← 계정 그룹 라인
┌────────────────────────────┐
│ PR 리뷰 요청   김지현 · 오늘 09:12  │
│ 요약: 금요일까지 결제 플로우 PR      │
│ 리뷰를 요청합니다.                │
└────────────────────────────┘
```

카드에 넣지 않는 것(전부 기각됨):

- `답장 필요`·`확인 필요` 같은 판단 라벨 — 섹션·필터·알림으로 전달
- `New` 배지, 좌측 컬러 바 — 새 항목 여부는 섹션 제목+카운트로만
- `[완료]`·`[나중에]` 버튼 — 완료는 Gmail 읽음의 파생 결과, 나중에는 읽음 확정 없음의 파생 상태
- 액션 버튼 일체 — 카드 클릭은 우측 상세 패널 열기

상세 패널의 즉시 액션은 제목 행 오른쪽에 icon-only 3개: `Gmail에서 열기` · `Gmail도 읽음 처리` · `…`(이동, 읽음 처리 후 아카이브). AI 판단 이유는 기본 비노출 — 틀렸으면 `이동`·`다음부터 여기로`로 고치게 한다.

## 9. 브리핑 상태

클릭했다고 사라지지 않는다. 상태: **새 항목 → 확인함 → 완료 / 나중에 다시 알림**

- 새 항목: 섹션 제목과 카운트(`새 중요 항목 2`)로만 전달 — 카드 내부 컬러 마커·배지 금지(0-5e)
- 확인함: 연하게 — *단, 이번 컬러 라운드 확정 규칙: 텍스트는 잉크 64% 이상 유지(AA), 요소 opacity·38% 금지. 낮춤은 보더·굵기로*
- 완료: 접힌 완료 영역 이동 또는 Undo와 함께 제거
- 나중에: 지정 시각까지 우선순위 하향 후 재활성화

## 10. Gmail 상태와 신뢰

상태 표기: Inbox / Archived / Label / Assistant-created label / Pending approval / Rule applied / Rule suggested.

- Gmail 변경은 절대 숨기지 않는다. 자동 처리는 상세와 활동 로그에 항상 표시
- 실제로 바꾼 경우: `8분 전 Gmail에서 Newsletter 라벨을 적용하고 아카이브했습니다. [Undo]`
- 안 바꾼 경우: `브리핑만 생성했습니다. Gmail 변경은 없습니다.`
- 낮은 확신 제안은 승인 대기 큐로. 최근 비서 행동은 가능한 한 Undo 제공

상세 패널의 Gmail handling 영역:

```text
Gmail handling
- 현재 상태: Inbox · Label: PR Review
- 비서 처리: 브리핑만 생성. Gmail 변경 없음
[라벨 적용] [아카이브] [마지막 비서 행동 취소]
```

## 11. LLM 요약과 개인정보

- Gmail 접근 + AI 요약을 허용한 계정에만 요약 제공, 계정별 ON/OFF
- 비즈니스/API 구성 사용, 보이는 기능에 필요한 최소 내용만 전송 (제목·발신자·스니펫·라벨·발췌 우선)
- 판단 근거·랭킹 신호 비노출, 원시 프롬프트 장기 보관 금지
- 요약 OFF 시 메타데이터 카드 + `Gmail 열기`만:

```text
[회사 업무] PR 리뷰 요청
답장 필요 · Inbox · Label: PR Review
AI 요약 꺼짐. Gmail에서 내용을 확인하세요.
```

## 12. 동기화·업데이트 상태

백그라운드 작업은 컴팩트하게. 진행률 풀스크린 금지(첫 연결 순간 제외).

- 계정별 동기화 상태 → 상단 `전체 메일 계정` 컨트롤 안 (스피너·상태 포함)
- 개별 계정 선택 시 상단 바 아래 얇은 동기화 스트립 허용
- 상단 `새 브리핑 n` 버튼은 두지 않는다(0-5 카운트 정리). 새 항목 카운트는 사이드바 내비와 섹션 헤더에서만, 알림성 업데이트는 벨에서

## 13. 레퍼런스 매핑

| 참조 | 차용 패턴 |
|---|---|
| Vercel | 상단 스코프(계정) 스위처, 크로스 컨텍스트 검색 |
| Notion Mail | 리스트+우측 상세 패널, 그룹 뷰, 호버 액션, 평문 자동 라벨 규칙 |
| Linear | 포커스 큐, 알림→상세 직행, 리마인드 preset(1h/2h/오늘 17시) |
| OneSignal / Chrome | 권한 사전 설명 프롬프트, 거부 시 "알림 꺼짐" 상태 + 재설정 안내, 첫 분석 완료 후 권한 요청 |
| Make / Zapier | 연결 계정 리스트 관리(상태·액션 분리) |
| HEY / Superhuman / Shortwave | 스플릿 인박스, 중요 영역 개념화, 번들 일괄 정리+Undo toast, Screener식 승인 큐 |

시각 디자인 복제 금지 — 인터랙션 패턴만 차용.

## 14. 시각 방향 (이번 라운드 확정 반영)

와이어프레임은 로우파이 그레이스케일로 진행하되, 하이파이 전환 시 `design/brand-color-final.md`의 확정 팔레트를 따른다.

- 배경 화이트 `#FFFFFF` + 선택면·보조면 클린 아이보리 `#F6F4EF` (진한 크림 금지)
- 잉크 중성 2단 `#26282B`/`#43464A` — 순흑·웜 잉크·다크 대면적 금지
- 유채색은 시맨틱 3색(`#218358`/`#A16207`/`#CE2C31`) + CTA 틸 `#14807A` 뿐
- 상태 표현은 알파 시스템(M3 상태 레이어 + Radix 알파), 접근성은 AA 목표 체제(측정·보고)
- 금지: AI 그라디언트, 글로우 오브, 마스코트, 의인화 카피, 인디고~퍼플 대역

## 15. 복붙용 실행 프롬프트 (컬러 확정 반영 갱신판)

```text
Create low-fidelity desktop web wireframes for an AI mail assistant.

Read and follow:
- docs/current/product-wireframe-final.md
- reference-boards/mail-assistant-reference-board.html
- design/brand-color-final.md (final color tokens and rules)

The product is web-first, not a mobile app, not a Gmail replacement. Gmail remains
where users read, reply, and send. This service is a briefing and triage layer.

Core direction:
- The main screen is a briefing screen, not an inbox.
- One service login; additional Gmail accounts are connected mail sources.
- Connected accounts appear in the top context selector and settings, not the sidebar.
- Every all-account mail card shows an account badge.
- Account selector rows show compact sync state (synced / syncing / permission needed).
- Background sync stays compact; updates appear top-right.

Create wireframes for (in order):
1. Login with Google
2. First Gmail application confirmation
3. Main briefing default state
4. Main briefing empty state
5. Main briefing with seen/done/remind-later states
6. Mail card and right-side detail panel
7. Priority detail screen
8. Notification entry states (route by type, no generic landing)
9. Connected accounts settings
10. Cleanup review / approval

Layout: left sidebar (product logo on top; Today's Briefing with section anchors,
Priority, Cleanup Review, Activity Log, Settings; service account at the bottom) ·
top bar (mail-account scope control with sync state + notification bell only — no
page title, no new-briefing button) · body (briefing sections + right detail panel).

Sections: New important / Needs reply / Can wait / Organized by assistant /
Needs approval, plus custom sections (Recruiting, Payments, GitHub, School, Read later).
Sections support rename, hide, reorder, add, move mail, "Next time, put similar mail here."

Mail card grammar (list = browse/select only; detail = read/commit):
Account group line above cards, then card: Subject + sender/time + short summary.
No action-type labels, no New badge, no color bar, no buttons inside cards.
Clicking a card opens the right detail panel. Detail title row has icon-only
actions: Open in Gmail · Mark read in Gmail · overflow(Move, Mark read + archive).
No [Done]/[Remind later] buttons anywhere — done derives from Gmail read state.
Never show assistant reasoning by default. Never imply Gmail changed unless it did.

Brand and tone:
- Quiet mail steward: precise, transparent, organized, private, non-intrusive.
- Copy is short and objective. No anthropomorphized assistant voice.
- Use grayscale for wireframes. For any hi-fi pass: white background + clean ivory
  #F6F4EF fills, neutral ink #26282B/#43464A (no pure black, no warm/brown grays),
  chromatic color limited to semantic states (green/amber/red) and one CTA color:
  steward teal #14807A.
- Interaction states use fixed alpha layers (hover 8%, pressed 10-12%, disabled 38%
  for controls only); readable content stays at 64%+ ink. No element opacity.
- Never use indigo-purple gradients, glowing orbs, mascots, or marketing hero sections.
```

## 16. 와이어프레임 파일 (피그마용 SVG 11장)

`design/wireframes/`에 최종 구조 반영본 수록. 전부 선택해 피그마 캔버스에 드래그하면 각 화면이 편집 가능한 프레임으로 들어간다. 화면 9는 `09-settings.svg` 교체본(구버전 삭제됨).

| 파일 | 화면 |
|---|---|
| `00-flow-map.svg` | 전체 플로우 맵 |
| `01-login.svg` | 로그인 |
| `02-first-application.svg` | 첫 Gmail 적용 확인 |
| `03-main-briefing-default.svg` | 메인 브리핑 — 기본 |
| `04-main-briefing-empty.svg` | 메인 브리핑 — 빈 상태 |
| `05-item-states.svg` | 확인함/완료/나중에 상태 |
| `06-card-and-detail.svg` | 메일 카드 + 상세 패널 |
| `07-priority-detail.svg` | 우선순위 상세 |
| `08-notification-entry.svg` | 알림 진입 상태 |
| `09-settings.svg` | 연결 계정·설정 (교체본) |
| `10-cleanup-review.svg` | 정리 검토/승인 |

## 17. 완료 판정 체크리스트

- 전체 메일함 없이 오늘 중요한 내용을 이해할 수 있는가?
- 항목마다 어느 Gmail 계정인지 보이는가?
- Gmail 상태 변경 여부가 보이는가?
- Gmail 열기 전에 완료/나중에/이동 판단이 가능한가?
- 브리핑 섹션을 내 방식으로 바꿀 수 있는가?
- 잘못 분류된 메일을 다음부터 원하는 섹션으로 보낼 수 있는가?
- 동기화/권한/알림 상태가 보이되 메인을 방해하지 않는가?
- 알림 클릭이 올바른 맥락에 착지하는가?
- 계정과 AI 요약 설정을 관리할 수 있는가?

## 18. 원본 문서와의 차이 (변경 로그)

- §9 확인함 상태: "연하게"의 구현 규칙 구체화 — 잉크 64% 이상, opacity/38% 금지 (컬러 라운드 확정)
- §14 시각 방향: persona-brand-tone.md의 구 팔레트(웜 배경·블루·틸·올리브) 폐기, 신규 팔레트로 대체
- §15 프롬프트: 원본 브리프의 "muted blue-gray, warm off-white, quiet teal/olive" 2줄을 신규 규칙으로 교체
- 그 외 제품 구조·화면·기능·신뢰 원칙은 원본 3종과 동일

Phase 0 결정 반영 (2026-07-06, 루트 `DESIGN.md` 기준):

- §5 정보 구조: 로고 최상단 / 서비스 계정 최하단 / 상단 = 메일 계정 컨트롤 + 벨, 페이지 제목·새 브리핑 버튼 제거 (0-5a·0-5b)
- §6 화면 10: 낮은 확신 일괄 승인 제거, 개별 확인만 (0-5h)
- §8 카드 문법 전면 교체: 판단 라벨·New 배지·컬러 바·완료/나중에 버튼 기각, 목록=탐색/선택·상세=열람/처리 (0-4, 0-5c·0-5e)
- §9 새 항목 강조: 카드 마커 → 섹션 카운트 (0-5e)
- §12: 상단 `새 브리핑 n` 제거 (0-5 카운트 정리)
- §15 프롬프트: 위 변경 전부 반영
