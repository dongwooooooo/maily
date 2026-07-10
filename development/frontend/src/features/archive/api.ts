/**
 * 보관함(07 storage) API 호출 — README "호출 규약" 형태.
 */

import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'
import type { components } from '@/shared/api/schema'

export type UpcomingStorage = components['schemas']['UpcomingStorage']
export type UpcomingReminderEntry = components['schemas']['UpcomingReminderEntry']
export type ServiceLabel = components['schemas']['ServiceLabel']

export async function fetchUpcomingStorage(): Promise<UpcomingStorage> {
  const { data, error, response } = await apiClient.GET('/storage/upcoming')
  if (error) throw toApiError(response.status, error)
  return data
}

export async function fetchLabels(): Promise<ServiceLabel[]> {
  const { data, error, response } = await apiClient.GET('/labels')
  if (error) throw toApiError(response.status, error)
  return data
}

export type ConnectedSource = components['schemas']['ConnectedSource']

/** 상세 패널 계정 라벨(gmail 주소) 매핑용 — 설정 화면 연결(F6)과 공유. */
export async function fetchSources(): Promise<ConnectedSource[]> {
  const { data, error, response } = await apiClient.GET('/sources')
  if (error) throw toApiError(response.status, error)
  return data
}
