/**
 * 오늘 브리핑 API 호출 — README "호출 규약" 형태.
 * 타입은 전부 openapi.json 생성물(schema.d.ts)에서 온다.
 */

import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'

import type { components } from '@/shared/api/schema'

export type AccountBriefingGroup = components['schemas']['AccountBriefingGroup']
export type BriefingCard = components['schemas']['BriefingCard']
export type MessageDetailResponse = components['schemas']['MessageDetail']

export async function fetchTodayBriefing(): Promise<AccountBriefingGroup[]> {
  const { data, error, response } = await apiClient.GET('/briefing/today')
  if (error) throw toApiError(response.status, error)
  return data
}

export async function fetchMessageDetail(messageId: string): Promise<MessageDetailResponse> {
  const { data, error, response } = await apiClient.GET('/messages/{message_id}', {
    params: { path: { message_id: messageId } },
  })
  if (error) throw toApiError(response.status, error)
  return data
}

export async function markItemSeen(briefingItemId: string): Promise<void> {
  const { error, response } = await apiClient.POST('/briefing/items/{briefing_item_id}/seen', {
    params: { path: { briefing_item_id: briefingItemId } },
  })
  if (error) throw toApiError(response.status, error)
}

export async function moveMessageToLabel(
  messageId: string,
  labelId: string,
  idempotencyKey: string,
): Promise<void> {
  // 키는 호출부가 액션 단위로 보관한다 — 같은 이동의 재시도는 같은 키를
  // 재사용해야 응답 유실 후 재시도가 중복 적용되지 않는다(README 계약).
  const { error, response } = await apiClient.POST('/messages/{message_id}/move', {
    params: {
      path: { message_id: messageId },
      header: { 'Idempotency-Key': idempotencyKey },
    },
    body: { label_id: labelId },
  })
  if (error) throw toApiError(response.status, error)
}
