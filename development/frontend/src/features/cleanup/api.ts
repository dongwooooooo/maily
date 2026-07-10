/**
 * 정리 검토(10 cleanup) API 호출 — README "호출 규약" 형태.
 */

import { apiClient } from '@/shared/api/client'
import { toApiError } from '@/shared/api/errors'
import type { components } from '@/shared/api/schema'

export type CleanupProposal = components['schemas']['CleanupProposal']
export type ActivityLogEntry = components['schemas']['ActivityLogEntry']

export async function fetchCleanupQueue(): Promise<CleanupProposal[]> {
  const { data, error, response } = await apiClient.GET('/cleanup')
  if (error) throw toApiError(response.status, error)
  return data
}

export async function approveCleanupProposal(proposalId: string): Promise<CleanupProposal> {
  const { data, error, response } = await apiClient.POST('/cleanup/{proposal_id}/approve', {
    params: { path: { proposal_id: proposalId } },
  })
  if (error) throw toApiError(response.status, error)
  return data
}

export async function fetchActivityLog(): Promise<ActivityLogEntry[]> {
  const { data, error, response } = await apiClient.GET('/actions/activity')
  if (error) throw toApiError(response.status, error)
  return data
}

export async function undoActivity(activityId: string): Promise<void> {
  const { error, response } = await apiClient.POST('/actions/{activity_id}/undo', {
    params: { path: { activity_id: activityId } },
  })
  if (error) throw toApiError(response.status, error)
}

export type RulesView = components['schemas']['RulesView']
export type RuleSuggestion = components['schemas']['RuleSuggestion']

export async function fetchRules(): Promise<RulesView> {
  const { data, error, response } = await apiClient.GET('/rules')
  if (error) throw toApiError(response.status, error)
  return data
}

export async function approveRuleSuggestion(suggestionId: string): Promise<void> {
  const { error, response } = await apiClient.POST('/rules/{suggestion_id}/approve', {
    params: { path: { suggestion_id: suggestionId } },
  })
  if (error) throw toApiError(response.status, error)
}
