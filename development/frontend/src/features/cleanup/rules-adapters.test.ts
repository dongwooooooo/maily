import { describe, expect, it } from 'vitest'

import type { RuleSuggestion } from './api'
import { toRuleProposals } from './adapters'

function suggestion(overrides: Partial<RuleSuggestion> = {}): RuleSuggestion {
  return {
    id: 'sug-1',
    workspace_id: 'ws-1',
    correction_signal_id: 'sig-1',
    suggested_condition: { sender: '매일경제' },
    status: 'pending',
    decided_at: null,
    ...overrides,
  }
}

describe('toRuleProposals', () => {
  it('maps a pending suggestion with the sender condition', () => {
    const proposals = toRuleProposals([suggestion()])

    expect(proposals).toHaveLength(1)
    expect(proposals[0].title).toBe('규칙 제안: 매일경제 자동 정리')
    expect(proposals[0].fromState).toBe('지금은 변경 없음')
    expect(proposals[0].toState).toBe('승인 시 자동 정리 규칙 생성 · 활동 로그와 되돌리기 제공')
  })

  it('skips approved/rejected suggestions', () => {
    expect(
      toRuleProposals([
        suggestion({ status: 'approved' }),
        suggestion({ id: 'sug-2', status: 'rejected' }),
      ]),
    ).toEqual([])
  })

  it('falls back safely when the condition shape is unknown', () => {
    const proposals = toRuleProposals([
      suggestion({ suggested_condition: { rule: ['weird'] } as never }),
    ])

    expect(proposals[0].title.startsWith('[미확정')).toBe(true)
  })
})
