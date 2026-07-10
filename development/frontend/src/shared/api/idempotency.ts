/**
 * Idempotency-Key 생성 — POST /actions, POST /messages/{id}/move 가 요구하는
 * 필수 헤더 값. 같은 사용자 액션의 재시도에는 같은 키를 재사용해야 하므로,
 * 호출부가 액션 시점에 한 번 생성해 재시도 간 보관한다.
 */

export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
