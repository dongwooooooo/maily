# 카피 원칙

작성일: 2026-07-06. Phase 0-3에서 UI 문구를 흔들림 없이 쓰기 위한 작업 문서다. 최종 하이파이 목업의 기본 UI 언어는 **한국어**로 확정한다. 영어 문구는 추후 i18n 후보와 구조 참고용으로만 보관한다.

## 상태

| 항목 | 상태 | 메모 |
|---|---:|---|
| UI 언어 정책 | Accepted | 한국어 UI 기준. 영어는 참고 후보로만 보관 |
| 톤 | Accepted | 진지 82, 격식 62, 공손 78, 객관 88 |
| 금지 인상 | Accepted | 마법 같은, 말 많은, 귀여운, 미래적인, 과잉 확신 |
| 신뢰 문구 | Accepted | Gmail 변경 여부를 항상 명시 |

## 기본 원칙

- 사용자가 지금 판단할 정보만 짧게 쓴다.
- AI가 안에서 똑똑하게 판단한다는 식의 의인화 문구를 쓰지 않는다.
- Gmail을 실제로 바꿨는지, 브리핑만 만든 것인지 분명히 말한다.
- 낮은 확신의 정리 제안은 승인 전제로 말한다.
- 규칙 학습은 평문으로 확인한다.
- 경고, 성공, 오류는 감정 표현보다 상태와 다음 행동을 먼저 쓴다.

## 내비게이션 문구

| 의미 | 확정 한국어 | 영어 참고 |
|---|---|---|
| Main briefing | 오늘 브리핑 | Today's Briefing |
| Storage (upcoming + my sections) | 보관함 | Storage |
| Cleanup review | 정리 검토 | Cleanup Review |
| Activity log | 활동 로그 | Activity Log |
| Connected accounts | 연결 계정 | Connected Accounts |
| Settings | 설정 | Settings |

## 액션 문구

| 의미 | 확정 한국어 | 영어 참고 | 메모 |
|---|---|---|---|
| Open source mail | Gmail에서 열기 | Open in Gmail | 개별 메일을 Gmail에서 확인 |
| Open synced Gmail label | Gmail 라벨 보기 | View Gmail label | 서비스가 관리하는 Gmail 라벨로 이동 |
| View in service | 서비스에서 열람 | Viewed in service | Gmail 읽음 상태는 변경하지 않음 |
| Mark read in Gmail | Gmail도 읽음 처리 | Mark read in Gmail | Gmail `UNREAD` 제거. 실제 Gmail 변경. 완료 상태의 명시 액션 |
| Archive after read | 읽음 처리 후 아카이브 | Mark read and archive | Gmail 읽음 처리와 아카이브를 함께 실행 |
| Move to label | 이동 | Move | 라벨 재분류. UI에서 "섹션"이라는 단어는 노출하지 않는다 — 사용자 분류함은 **라벨**(Gmail `Maily/` 라벨과 동기화되므로 이름이 실체와 일치) |
| Approve cleanup | 승인 | Approve | 낮은 확신 묶음에서는 T1로 쓰지 않음 |
| Undo | 되돌리기 | Undo | 활동 로그와 토스트에서 동일 표현 |

## 신뢰 문구

| 상황 | 확정 한국어 | 영어 참고 |
|---|---|---|
| Gmail 변경 없음 | 브리핑만 생성했습니다. Gmail 변경은 없습니다. | Briefing only. Gmail was not changed. |
| 자동 처리 완료 | 8분 전 Gmail에서 Newsletter 라벨을 적용하고 아카이브했습니다. | Applied the Newsletter label and archived in Gmail 8 minutes ago. |
| Gmail 라벨 동기화 | Maily/오늘 브리핑 라벨에 동기화했습니다. | Synced to the Maily/Today Briefing label. |
| 서비스 열람 | 서비스에서 본문을 열람했습니다. Gmail 읽음 상태는 변경하지 않았습니다. | Viewed in service. Gmail read state was not changed. |
| Gmail 읽음 처리 | Gmail에서도 읽음 처리했습니다. | Marked as read in Gmail. |
| Gmail에서 읽음 감지 | Gmail에서 읽은 상태가 동기화되었습니다. | Read state synced from Gmail. |
| 완료 처리 | 완료로 표시했습니다. Gmail에서도 읽음 처리했습니다. | Marked as done and read in Gmail. |
| 대기 유지 | 읽음 처리하지 않았습니다. 필요하면 다시 알려드립니다. | Kept pending. Reminder remains available. |
| 읽음 변경 없음 | Gmail 읽음 상태는 변경하지 않았습니다. | Gmail read state was not changed. |
| 규칙 확인 | 앞으로 이 발신자의 계약·결제 알림은 Payments에 표시합니다. | Future contract and payment updates from this sender will appear in Payments. |
| 낮은 확신 | 확신이 낮아 승인 후 적용합니다. | Low confidence. Apply after approval. |
| 권한 필요 | 이 계정의 Gmail 권한을 다시 연결해야 합니다. | Reconnect Gmail permission for this account. |

## 화면 카피 기준

- 화면 제목, 내비게이션, 버튼, 상태, 토스트, 확인문은 한국어로 쓴다.
- `Gmail`, `Inbox`, `Label`, `Newsletter`, 이메일 주소, 외부 서비스명은 원문을 유지한다.
- `All accounts`는 하이파이 목업에서 `전체 계정`으로 번역한다.
- `PR Review`처럼 사용자가 만든 라벨이나 실제 Gmail 라벨은 원문 유지 가능하다.
- `Maily/오늘 브리핑`처럼 서비스가 만든 Gmail 라벨은 실제 라벨명으로 보여준다.
- 버튼은 2-5글자 중심으로 짧게 둔다. 길어지면 버튼 대신 상세 설명 영역에 둔다.
- `완료`와 `나중에`는 기본 버튼으로 쓰지 않는다. `완료`는 Gmail에서 읽혔거나 `Gmail도 읽음 처리`를 실행한 결과 상태이고, `나중에`는 읽음 확정이 없는 대기 상태다.
- Gmail 읽음 상태가 바뀌는 액션은 버튼 주변, 확인문, 토스트 중 한 곳에 반드시 `Gmail도 읽음 처리` 또는 `읽음 처리 포함`을 드러낸다.
- `이동`, `Gmail 라벨 보기`, `Gmail에서 열기`, 상세 열람은 읽음 처리하지 않는다. 필요한 경우 `대기 유지` 또는 `읽음 변경 없음`을 짧게 보조 표기한다.
- 자동 처리 설명은 과거형으로 쓴다. 예: `8분 전 Gmail에서 Newsletter 라벨을 적용하고 아카이브했습니다.`
- 미적용 상태는 부정확한 안심 표현보다 변경 여부를 먼저 말한다. 예: `브리핑만 생성했습니다. Gmail 변경은 없습니다.`

## 결정 기록

Q0-3. 최종 하이파이 목업의 기본 UI 언어: **한국어 UI 채택**.

- 한국어 UI: 채택. 국내 기획/검토와 실카피 판단이 빠르다.
- 영어 UI: 기각. 기존 와이어프레임과 맞지만, 한국어 기획 문서와 실카피 검토가 분리된다.
- i18n 전제: 기각. 추후 확장은 가능하지만 Phase 0 목업 결정 단계에서는 과하다.
