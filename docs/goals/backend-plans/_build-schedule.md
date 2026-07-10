# Maily Backend Build Schedule (병렬·순차 실행 순서)

기준: `backend-implementation-plan.md`(Task·Gate), `_integration-contract.md`(충돌 규약·event wiring), 도메인별 세부 플랜(`<domain>.md`).
정리일: 2026-07-09

## 진행 현황 (2026-07-10)

- W0–W4 전 웨이브 코딩 완료. IC1–IC8 통합 통과(전체 321 passed). 상세 갭은 `backend-implementation-plan.md` "구현 상태" 참조.
- IC6은 dispatcher 배선 대신 직접 동기 호출(module-boundaries F10 설계) — 전용 `test_ic6_*.py` 없이 `test_cleanup_review.py`로 커버.
- 잔여: Task 14(Live Gmail Watch, IG1), Task 15(Operations Handoff), `ACTIVE_EVENT_CONSUMERS` 누락 배선 2건(`gmail_snapshot_changed→prepare_cleanup_proposals`, `cleanup_proposal_created→build_briefing`), 런타임 dispatcher 폴러.

## 문서 역할

`backend-implementation-plan.md`는 Task를 번호순으로 나열하지만, 실제 선후관계는 두 축으로 갈린다. 이 문서는 **어디서 병렬로 치고 어디서 순차로 배선·검증하는지**를 고정한다. 세부 동작·엣지는 `<domain>.md`가 소유하고, 여기서는 실행 순서만 다룬다.

## 의존성 2종 — 섞지 않는다

| 종류 | 무엇 | 언제 강제되나 | 근거 |
|---|---|---|---|
| **스키마/FK 의존** | 테이블·FK·마이그레이션 순서 | `alembic upgrade` / 머지 시점 | `_integration-contract §1` 선형 revision 체인 |
| **플로우 의존** | outbox 이벤트 producer→consumer 배선 | 통합·크로스 도메인 테스트 시점 | `_integration-contract §3` event→consumer wiring |

핵심: core가 outbox/job 그릇을 먼저 줘도, 이벤트 하나가 **의미 있게 닫히려면 producer와 consumer 도메인이 둘 다 구현돼야 한다**. 그래서 코딩은 병렬로 최대한 벌리고, 배선·검증은 플로우 체인 따라 순차로 좁힌다.

핵심 원칙:
- **코딩 단계** — 각 도메인은 fake adapter + seed row로 남의 도메인 없이 자기 단위테스트 green까지 간다. 여기서 병렬 최대.
- **통합 단계** — producer·consumer 둘 다 코딩 완료된 뒤에만 dispatcher 배선 + 크로스 테스트. 여기서 순차(플로우 체인 순).

---

## 도메인 의존 표

각 도메인이 무엇을 produce/consume하고, 언제 착수 가능하며, 코딩 완료·통합 검증 기준이 무엇인지.

| 도메인 | produces (event) | consumes (event→job) | 착수 가능 조건 | 코딩 완료 체크 (단위, fake/seed) | 통합 검증 조건 (cross) |
|---|---|---|---|---|---|
| **core** | — | (dispatcher가 전 이벤트 라우팅) | 없음(최초) | health/ready, outbox dedupe, job lock, idempotency 단위 green | §4 도메인 자동 발견이 빈 registry로 부팅됨 |
| **identity** | — | — | core | google_login·session·workspace isolation green | 인증 의존성이 타 도메인 라우터에 주입됨 |
| **mail_sources** | source_connected/settings_changed/disconnected/recovery | — | core (+identity: seed workspace) | 연결·설정·credential 암호화·상태전이 green | connected 이벤트가 outbox 적재(payload 검증) |
| **mail_intake** | notification_received, snapshot_changed, recovery | source_connected→register_watch/sync | core (+mail_sources: seed source) | fake_reader snapshot upsert, cursor, dedupe, sync job green | IC1(연결→sync), IC2 producer측 |
| **briefing** | item_state_changed, reminder_reactivated | snapshot_changed / summary_completed / importance_classified / action_applied / action_undone / reminder_reactivated → build_briefing | core (+seed gmail_messages) | today/detail shape, 부분 rebuild, seen durable green | IC2·IC3·IC4 consumer측 |
| **labels** | label_correction_recorded | — | core (+seed workspace·gmail_messages) | label 카탈로그, mapping intent, move signal green | IC5 producer측 |
| **gmail_actions** | action_requested/applied/failed/undone | action_requested→execute_action | core (+seed connected_account·gmail_messages) | command ledger 상태전이, fake_mutator, undo, boundary green | IC4·IC5·IC6 |
| **assistant_decisions** | summary_completed, importance_classified, cleanup_proposal_created, rule_suggestion_created | snapshot_changed→summary/importance/cleanup, label_correction→rule | core (+seed gmail_messages·service_labels·correction_signals·gmail_action_commands) | summary/importance 독립 실행, privacy, approve-one green | IC3·IC5·IC6 |
| **notifications** | notification_event_created | recovery/action_failed/cleanup_created/reminder_reactivated 등 → emit_notification | core (+seed workspace) | route_target 매핑, generic landing negative, recovery view green | IC7(전 producer로부터) |
| **purge** (Task 13) | — | source_disconnected→purge_disconnected_source | 전 도메인 PURGE_HANDLER 존재 | 도메인별 purge handler 단위 green | IC8(전 도메인 오케스트레이션) |

seed = 테스트 픽스처로 상위 테이블 row를 직접 심음(남의 도메인 서비스 호출 없이). fake = 외부 어댑터(GmailReaderPort/MutationPort/LLM) 대역.

---

## 코딩 웨이브 (병렬 최대화)

각 웨이브 안 도메인은 서로 독립 워크트리로 **동시** 진행. 웨이브 경계는 스키마 착수 조건이지 통합 조건이 아니다(통합은 §통합 체크포인트).

| 웨이브 | 도메인 | 병렬성 | 격리 수단 | 배리어(다음 웨이브 진입 조건) |
|---|---|---|---|---|
| **W0** | core | 단독 | — | core 단위 green + §4 자동 발견 부팅. **전 도메인의 하드 배리어** |
| **W1** | identity, mail_sources | 2 병렬 | mail_sources는 seed workspace | 각자 단위 green. mail_sources는 identity 머지 후 마이그레이션 순서(`0003` down `0002`) |
| **W2** | mail_intake, labels, gmail_actions | 3 병렬 | seed source/account/messages, fake reader·mutator | 각자 단위 green |
| **W3** | briefing, assistant_decisions, notifications | 3 병렬 | seed messages/labels/signals/commands, fake LLM | 각자 단위 green |
| **W4** | purge | 단독(cross-cutting) | 각 도메인 PURGE_HANDLER 완성 후 | IC8 |

W0만 진짜 하드 배리어(모두가 core import). W1~W3은 스키마 착수 조건상 느슨한 순서지만, seed로 격리하면 **W1~W3을 거의 동시에도 벌릴 수 있다** — 제약은 워크트리 머지 순서(마이그레이션 체인)일 뿐 코딩 착수는 아니다.

착수 병목 정리:
- core = 절대 선행. 나머지 8개는 core 머지 전엔 시작 못 함.
- identity = mail_sources의 seed 대상(workspace). 실제 코딩은 seed로 병렬 가능, 머지만 순서.
- W2·W3 도메인은 전부 seed로 상위 테이블 없이 단위 진행 가능 → 코딩 병렬성 높음.

---

## 통합 체크포인트 (순차, 플로우 체인 순)

producer·consumer 둘 다 **코딩 완료 체크** 통과한 뒤에만 진행. 각 IC = dispatcher 배선 + 크로스 도메인 테스트. G gate와 매핑.

| IC | 플로우 | 선행 freeze/체크 | 배선 | G gate |
|---|---|---|---|---|
| **IC1** | 연결 → sync | mail_sources connected 이벤트 payload green + mail_intake register_watch/sync_full이 fake 이벤트로 동작 green | source_connected → register_watch/sync_full | G2 일부 |
| **IC2** | sync → briefing | mail_intake snapshot_changed payload(source_id/sync_run_id/message_ids) green + briefing build_briefing이 fake 이벤트로 projection green | snapshot_changed → build_briefing | G3 일부 |
| **IC3** | sync → assistant → briefing 부분재생성 | assistant summary/importance 독립 실행 green + summary_completed/importance_classified payload green + briefing message_id 단위 부분 rebuild green | snapshot_changed → summary/importance; summary_completed·importance_classified → build_briefing(부분) | G3·G6 |
| **IC4** | action ledger | gmail_actions command 상태전이·fake_mutator green + action_applied payload green + briefing action_applied→rebuild green + mail_intake snapshot reconcile green | action_requested → execute_action; action_applied/undone → build_briefing(+intake reconcile) | G4 |
| **IC5** | labels 이동 → action·rule | labels move signal green + gmail_actions label apply command green + assistant label_correction→rule green | move → label apply command; label_correction_recorded → create_rule_suggestions | G5 일부 |
| **IC6** | cleanup 승인 → action | assistant approve-one green + gmail_actions command green | approve_cleanup → gmail_actions command | G5 일부 |
| **IC7** | 알림 라우팅 | notifications route_target·recovery view green + 각 producer 이벤트 green | recovery/action_failed/cleanup_created/reminder_reactivated → emit_notification | G7 |
| **IC8** | disconnect → purge | 전 도메인 PURGE_HANDLER green + source_disconnected payload green | source_disconnected → purge_disconnected_source(오케스트레이션) | G8 |

IC 순서는 플로우 의존이라 원칙적으로 순차지만, **서로 다른 플로우는 병렬 배선 가능**:
- IC2와 IC3은 둘 다 snapshot_changed 소비 → 함께 배선(같은 producer).
- IC4는 gmail_actions 완성 후 독립적으로 배선(IC5·IC6 전에 가능).
- IC7은 각 producer가 준비되는 대로 부분 배선(recovery부터 → action_failed → cleanup 순 점증).

---

## 병렬 vs 순차 한눈 요약

```
[W0] core ───────────────────────── (하드 배리어)
        │
[W1]  identity ║ mail_sources ────── (2 병렬, seed)
        │
[W2]  mail_intake ║ labels ║ gmail_actions ── (3 병렬, seed+fake)
        │
[W3]  briefing ║ assistant ║ notifications ── (3 병렬, seed+fake)
        │
── 코딩 배리어: 관련 producer/consumer 단위 green ──
        │
[IC1] 연결→sync
[IC2] sync→briefing        ┐ snapshot_changed 공통 → 함께 배선
[IC3] sync→assistant→briefing ┘
[IC4] action ledger        (gmail_actions 준비 후 독립)
[IC5] labels→action·rule
[IC6] cleanup→action
[IC7] 알림 (producer별 점증 배선)
        │
[W4/IC8] disconnect→purge  (전 도메인 handler 후, 최후)
```

- **병렬 구간**: W1~W3 코딩(최대 3 워크트리 동시), 서로 다른 플로우의 IC 배선.
- **순차 배리어**: W0(core) 진입, 각 IC의 "producer·consumer 둘 다 단위 green" 조건, IC8(전 도메인 후).
- **머지 순서 제약(코딩 병렬과 별개)**: 마이그레이션 체인 `0001`→`0012` 순서로만 머지(`_integration-contract §1`).

## 진행 규칙

1. W0 core 먼저, 단독. green + 부팅 확인 후 워크트리 팬아웃.
2. W1~W3은 seed/fake로 병렬 코딩. 각 도메인 세부 플랜(`<domain>.md`)의 6축 테스트를 red→green.
3. 도메인 단위 green = 해당 도메인 "코딩 완료 체크"(위 표) 충족.
4. IC는 관여 도메인이 전부 코딩 완료된 뒤 배선. IC 통과 = 대응 G gate 통과.
5. 마이그레이션은 코딩과 무관하게 `0001`→`0012` 순서로만 머지.
6. IC8(purge)는 전 도메인 handler 완성 후 최후.
