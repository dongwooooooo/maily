/**
 * 설정(09 settings) API 호출 — README "호출 규약" 형태.
 */

import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'
import type { components } from '@/shared/api/schema'

export type SourceSettings = components['schemas']['SourceSettingsResult']
export type UpdateSourceSettingsInput = components['schemas']['UpdateSourceSettingsRequest']
export type SessionSummary = components['schemas']['SessionSummaryResponse']

export async function fetchSourceSettings(sourceId: string): Promise<SourceSettings> {
  const { data, error, response } = await apiClient.GET('/sources/{source_id}/settings', {
    params: { path: { source_id: sourceId } },
  })
  if (error) throw toApiError(response.status, error)
  return data
}

export async function updateSourceSettings(
  sourceId: string,
  changes: UpdateSourceSettingsInput,
): Promise<SourceSettings> {
  const { data, error, response } = await apiClient.PATCH('/sources/{source_id}', {
    params: { path: { source_id: sourceId } },
    body: changes,
  })
  if (error) throw toApiError(response.status, error)
  return data
}

export async function disconnectSource(sourceId: string): Promise<void> {
  const { error, response } = await apiClient.DELETE('/sources/{source_id}', {
    params: { path: { source_id: sourceId } },
  })
  if (error) throw toApiError(response.status, error)
}

export async function fetchSessionSummary(): Promise<SessionSummary> {
  const { data, error, response } = await apiClient.GET('/auth/session')
  if (error) throw toApiError(response.status, error)
  return data
}
