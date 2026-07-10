/**
 * 연결 메일 계정(sources) 공용 호출 — 설정·보관함 등 여러 feature가 소비한다.
 */

import { apiClient } from './client'
import { toApiError } from './errors'
import type { components } from './schema'

export type ConnectedSource = components['schemas']['ConnectedSource']

export async function fetchSources(): Promise<ConnectedSource[]> {
  const { data, error, response } = await apiClient.GET('/sources')
  if (error) throw toApiError(response.status, error)
  return data
}
