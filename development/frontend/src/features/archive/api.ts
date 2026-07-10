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

// sources 호출은 여러 feature가 소비해 shared로 승격됐다 — 기존 소비처 호환 재노출.
export { fetchSources, type ConnectedSource } from '@/shared/api/sources'
