# Maily Backend Integration Contract (워크트리 충돌 규약)

기준 문서: `docs/areas/backend/module-boundaries.md`, `docs/areas/backend/db-schema.md`, `docs/goals/backend-implementation-plan.md`
정리일: 2026-07-09

## 문서 역할

도메인 9개를 각자 워크트리에서 병렬 구현할 때 **머지 시점에 충돌하는 3개 공유점**을 사전 고정한다. 각 도메인 세부 플랜(`docs/goals/backend-plans/<domain>.md`)은 이 규약을 근거로 작성한다. 이 파일에 없는 값을 도메인 워크트리가 임의로 정하지 않는다 — 필요하면 이 파일을 먼저 갱신하고 진행한다.

충돌점 3개:
1. Alembic 마이그레이션 체인 (선형 revision 순서)
2. Job registry (job_type → 도메인 handler 매핑)
3. `main.py` 라우터 include + outbox event → consumer wiring

공유 규약 2개(코드 컨벤션):
4. 도메인 패키지 노출 인터페이스 (core가 도메인을 자동 발견하는 규칙)
5. status enum 값 집합 (테이블별 상태값 divergence 방지)

---

## 1. Alembic 마이그레이션 체인

### 전략

**선형 pre-assigned chain + 문서화된 머지 순서.** 각 마이그레이션 파일은 autogenerate 해시 대신 아래 표의 고정 `revision` 슬러그를 쓴다. `down_revision`도 표대로 고정한다. 워크트리는 배정된 revision/down_revision만 사용 → 머지 시 체인 충돌 0.

FK 의존성 때문에 upgrade는 반드시 이 순서로 적용돼야 한다. 워크트리 **머지 순서 = 이 표의 순서**. 앞 도메인이 머지되기 전 뒤 도메인을 머지하면 `alembic upgrade head`가 FK 대상 부재로 실패한다(정상 — 순서 강제 장치).

> 대안(각 도메인 독립 branch + `alembic merge heads`)은 FK upgrade 순서를 보장하지 못해 POC에서는 채택하지 않는다. 도메인 수가 늘어 병렬 머지 압박이 커지면 그때 재검토.

### Revision 배정표

| # | revision 슬러그 | down_revision | 도메인 | Task | 생성 테이블 |
|---:|---|---|---|---|---|
| 1 | `0001_core` | (base) | core | 1 | `outbox_events`, `job_runs`, `idempotency_keys` |
| 2 | `0002_identity` | `0001_core` | identity | 2 | `users`, `workspaces`, `workspace_members`, `sessions` |
| 3 | `0003_mail_sources` | `0002_identity` | mail_sources | 3 | `connected_gmail_accounts`, `gmail_oauth_credentials`, `gmail_source_settings` |
| 4 | `0004_mail_intake_snapshot` | `0003_mail_sources` | mail_intake | 4 | `gmail_messages`, `message_excerpts`, `gmail_message_labels` |
| 5 | `0005_mail_intake_sync` | `0004_mail_intake_snapshot` | mail_intake | 5 | `gmail_sync_cursors`, `gmail_watch_registrations`, `gmail_notification_events`, `sync_runs` |
| 6 | `0006_labels` | `0005_mail_intake_sync` | labels | 8 | `service_labels`, `gmail_label_mappings`, `label_correction_signals` |
| 7 | `0007_gmail_actions` | `0006_labels` | gmail_actions | 9 | `gmail_action_commands`, `activity_logs`, `undo_actions` |
| 8 | `0008_briefing_items` | `0007_gmail_actions` | briefing | 6 | `briefing_items` |
| 9 | `0009_briefing_state` | `0008_briefing_items` | briefing | 7 | `briefing_item_states`, `reminders` |
| 10 | `0010_assistant_eval` | `0009_briefing_state` | assistant_decisions | 10 | `summary_jobs`, `message_summaries`, `importance_jobs`, `message_importance_classifications` |
| 11 | `0011_assistant_rules` | `0010_assistant_eval` | assistant_decisions | 11 | `classification_rules`, `rule_suggestions`, `cleanup_proposals` |
| 12 | `0012_notifications` | `0011_assistant_rules` | notifications | 12 | `notification_subscriptions`, `notification_events` |

주의:
- `labels`(6) 를 `gmail_actions`(7) 앞에 둔다 — `gmail_actions`는 label FK가 없지만, `assistant_decisions`가 `label_correction_signals`(labels) + `gmail_action_commands`(gmail_actions) 둘 다 참조하므로 두 도메인이 assistant보다 먼저 와야 한다. labels↔gmail_actions 간 FK는 없어 상호 순서는 무관하나 표대로 고정한다.
- `briefing`(8,9) 은 `gmail_messages`(4) 만 있으면 되지만, 선형 체인이라 gmail_actions 뒤에 배치. briefing 워크트리는 `0004`까지만 있으면 개발·테스트 가능(자기 down_revision은 `0007`이지만 로컬 테스트는 필요한 상위 테이블만 있으면 됨 — 머지 순서만 표를 따르면 됨).
- Task 13(purge) 은 새 테이블을 만들지 않는다. 필요 시 컬럼 추가 마이그레이션은 `0013_purge_markers`로 예약, down_revision `0012_notifications`.

### 규칙

- 마이그레이션 파일명: `development/backend/app/db/migrations/versions/<revision>.py`.
- 한 도메인이 위 배정 외 테이블/컬럼을 추가해야 하면 이 표에 행을 먼저 추가하고 revision 번호를 이어붙인다.
- `alembic revision --autogenerate` 사용 금지(해시 revision 생성). 수동으로 슬러그 revision 작성.

---

## 2. Job Registry

`app/core/jobs/registry.py`는 core 슬라이스가 소유한다. 도메인은 registry.py를 직접 수정하지 않는다. 각 도메인은 `jobs/` 아래 handler를 구현하고 아래 표의 계약(`job_type` 문자열 + handler 경로)을 지킨다. core는 이 표를 근거로 registry를 한 번에 wiring한다(§4의 자동 발견 규칙으로 import).

| job_type | 도메인 | handler 모듈 | payload shape | 트리거 |
|---|---|---|---|---|
| `register_watch` | mail_intake | `mail_intake/jobs/register_watch.py` | `{source_id}` | `gmail_source_connected` |
| `renew_watch` | mail_intake | `mail_intake/jobs/renew_watch.py` | `{source_id}` | 스케줄(만료 전) |
| `process_notification` | mail_intake | `mail_intake/jobs/process_notification.py` | `{email_address, history_id, notification_id}` | Pub/Sub 수신 |
| `poll_history` | mail_intake | `mail_intake/jobs/poll_history.py` | `{source_id}` | 스케줄(fallback) |
| `sync_delta` | mail_intake | `mail_intake/jobs/sync_delta.py` | `{source_id, start_history_id}` | notification/poll |
| `sync_full` | mail_intake | `mail_intake/jobs/sync_full.py` | `{source_id, reason}` | cursor invalid / 초기 |
| `build_briefing` | briefing | `briefing/jobs/build_briefing.py` | `{workspace_id, source_id?, message_ids?}` | `gmail_snapshot_changed`, `summary_completed`, `importance_classified`, `gmail_action_applied`, `gmail_action_undone` |
| `reactivate_reminders` | briefing | `briefing/jobs/reactivate_reminders.py` | `{}`(due 스캔) | 스케줄 |
| `execute_action` | gmail_actions | `gmail_actions/jobs/execute_action.py` | `{command_id}` | `gmail_action_requested` |
| `generate_summary` | assistant_decisions | `assistant_decisions/jobs/generate_summary.py` | `{message_id}` | `gmail_snapshot_changed` (summary_enabled 시) |
| `classify_importance` | assistant_decisions | `assistant_decisions/jobs/classify_importance.py` | `{message_id}` | `gmail_snapshot_changed` |
| `create_rule_suggestions` | assistant_decisions | `assistant_decisions/jobs/create_rule_suggestions.py` | `{correction_signal_id}` | `label_correction_recorded` |
| `prepare_cleanup_proposals` | assistant_decisions | `assistant_decisions/jobs/prepare_cleanup_proposals.py` | `{workspace_id, message_ids?}` | `gmail_snapshot_changed` |
| `emit_notification` | notifications | `notifications/jobs/emit_notification.py` | `{notification_type, route_target, workspace_id}` | 다수(§3) |
| `purge_disconnected_source` | mail_sources | `mail_sources/jobs/purge_disconnected_source.py` | `{source_id}` | `gmail_source_disconnected` |

`lock_key` 규칙(동시 실행 방지):
- source 대상 job(`sync_delta`, `sync_full`, `register_watch`, `renew_watch`, `poll_history`, `purge_disconnected_source`) 은 `lock_key = "source:{source_id}"` — 같은 계정 동시 sync 금지.
- `execute_action` 은 `lock_key = "command:{command_id}"`.
- message 단위 평가(`generate_summary`, `classify_importance`) 는 lock 불필요(idempotency_key로 충분). `lock_key = null`.

---

## 3. 라우터 Include + Event → Consumer Wiring

### Router prefix

`app/api/router.py`(core 소유)가 각 도메인 `router`를 include한다. prefix 고정:

| 도메인 | prefix | 대표 엔드포인트 |
|---|---|---|
| identity | `/auth` | `POST /auth/google/callback`, `GET /auth/session` |
| mail_sources | `/sources` | `POST /sources`, `GET /sources`, `PATCH /sources/{id}`, `DELETE /sources/{id}` |
| mail_intake | `/intake` | `POST /intake/pubsub`(webhook), `POST /sources/{id}/sync`(manual) |
| briefing | `/briefing`, `/messages`, `/storage` | `GET /briefing/today`, `GET /messages/{id}`, `GET /storage/upcoming` |
| labels | `/labels` | `GET/POST /labels`, `PATCH /labels/{id}`, `POST /messages/{id}/move` |
| gmail_actions | `/actions` | `POST /actions`, `GET /actions/activity`, `POST /actions/{id}/undo` |
| assistant_decisions | `/rules`, `/cleanup` | `GET /rules`, `POST /rules/{id}/approve`, `GET /cleanup`, `POST /cleanup/{id}/approve` |
| notifications | `/notifications` | `GET /notifications`, `POST /notifications/subscribe` |

### Event → Consumer 매핑 (outbox dispatcher가 큐잉할 job)

dispatcher는 outbox event를 읽어 아래 consumer job을 `job_runs`에 큐잉한다. **producer는 직접 consumer를 호출하지 않는다** (경계 invariant). 각 소비 도메인은 자기 job이 이 event로 트리거된다는 사실만 알면 된다.

| event_type | producer | 큐잉되는 consumer job | 비고 |
|---|---|---|---|
| `gmail_source_connected` | mail_sources | `register_watch`(intake) | + 초기 `sync_full` |
| `gmail_source_settings_changed` | mail_sources | (구독자: briefing/assistant/notifications가 다음 조회 시 반영) | job 없이 read 시점 반영 |
| `gmail_source_disconnected` | mail_sources | `purge_disconnected_source`(mail_sources) | 각 도메인 purge는 §mail_sources 플랜 참조 |
| `gmail_source_recovery_needed` | mail_sources/mail_intake | `emit_notification`(notifications) | route_target=계정 설정 |
| `gmail_notification_received` | mail_intake | `sync_delta`(intake) | dedupe 후 |
| `gmail_snapshot_changed` | mail_intake | `build_briefing`(briefing), `generate_summary`+`classify_importance`(assistant), `prepare_cleanup_proposals`(assistant), route(notifications) | summary는 `summary_enabled` 시만 |
| `briefing_item_state_changed` | briefing | (assistant 구독) | |
| `reminder_reactivated` | briefing | `build_briefing`(briefing), `emit_notification`(notifications) | |
| `label_correction_recorded` | labels | `create_rule_suggestions`(assistant) | |
| `gmail_action_requested` | gmail_actions | `execute_action`(gmail_actions) | |
| `gmail_action_applied` | gmail_actions | `build_briefing`(briefing) | + intake snapshot reconcile |
| `gmail_action_failed` | gmail_actions | `emit_notification`(notifications) | |
| `gmail_action_undone` | gmail_actions | `build_briefing`(briefing), `emit_notification`(notifications) | |
| `summary_completed` | assistant_decisions | `build_briefing`(briefing, message_id 단위) | |
| `importance_classified` | assistant_decisions | `build_briefing`(briefing, message_id 단위) | |
| `cleanup_proposal_created` | assistant_decisions | `build_briefing`(briefing), `emit_notification`(notifications) | |
| `rule_suggestion_created` | assistant_decisions | (briefing 구독) | |
| `notification_event_created` | notifications | browser push worker | |

이 표는 `module-boundaries.md` Event Catalog의 consumer를 "실제 큐잉되는 job"으로 구체화한 것이다. 충돌 시 Event Catalog가 상위 근거.

---

## 4. 도메인 패키지 노출 인터페이스

core가 도메인을 자동 발견하려면 각 도메인 패키지가 동일한 심볼을 노출해야 한다. `app/domains/<domain>/__init__.py`:

```python
router = ...            # APIRouter (없으면 None)
JOB_HANDLERS = {...}    # {job_type: callable}, §2 표와 일치
EVENT_CONSUMERS = {...} # {event_type: [job_type]}, §3 표와 일치 (선택 — dispatcher가 이 값으로 큐잉)
PURGE_HANDLER = ...     # callable(source_id) 또는 None (Task 13)
```

- 구현: `app/core/discovery.py`(`discover_domain_modules`, `collect_routers`, `collect_job_handlers`, `collect_event_consumers`, `collect_purge_handlers`, `register_discovered_jobs`). `app/api/router.py`가 `collect_routers`로 라우터를 자동 수집하고, `app/main.py`의 FastAPI `lifespan`이 서버 기동 시점에 `register_discovered_jobs()`를 호출해 `app/core/jobs/registry.py`에 등록한다(모듈 import 시점이 아니라 실제 서버 기동 시점 — `TestClient(app)`을 `with` 없이 쓰는 기존 라우터 테스트가 전역 registry를 오염시키지 않는다).
- `collect_job_handlers`가 수집 단계에서 중복 `job_type`을 감지해 `DuplicateJobTypeError`를 던진다(마지막 값으로 조용히 덮어쓰지 않는다). `registry.register()`도 동일 예외로 한 번 더 방어한다.
- 라우터 prefix(§3 표)는 도메인 코드에서 유도할 수 없는 값이라 `app/api/router.py`의 `_PREFIX_BY_DOMAIN` 딕셔너리 한 줄만 여전히 수동이다 — "도메인 추가 시 core 코드 수정 없이 등록된다"는 이 prefix 매핑 한 줄만 예외.

---

## 5. Status Enum 값 집합

테이블별 status 값을 여기서 고정한다. 도메인 워크트리는 이 집합만 사용한다.

| 테이블.컬럼 | 허용 값 |
|---|---|
| `connected_gmail_accounts.status` | `connected`, `syncing`, `synced`, `permission_needed`, `error`, `paused`, `disconnecting`, `disconnected` |
| `gmail_sync_cursors.cursor_status` | `valid`, `invalid` |
| `gmail_watch_registrations.status` | `active`, `expired`, `failed` |
| `sync_runs.status` | `running`, `succeeded`, `failed` |
| `outbox_events.status` | `pending`, `dispatched`, `failed` |
| `job_runs.status` | `queued`, `running`, `retrying`, `succeeded`, `failed` |
| `gmail_action_commands.status` | `pending`, `applied`, `failed`, `compensating`, `undone` |
| `reminders.status` | `pending`, `reactivated`, `cancelled` |
| `rule_suggestions.status` | `pending`, `approved`, `rejected` |
| `cleanup_proposals.status` | `pending`, `approved`, `rejected`, `applied` |
| `summary_jobs.status` / `importance_jobs.status` | `queued`, `running`, `succeeded`, `failed` |

`[미정]` 값 집합(schema §열린 결정): `briefing_items.section`, `importance_band`, `confidence_band` — 이 파일이 아니라 db-schema.md의 [미정] 해소 시 반영. 그 전까지 각 도메인은 `fake_*` 계약 상수로만 참조.
