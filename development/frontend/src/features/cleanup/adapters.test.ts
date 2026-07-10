import { describe, expect, it } from 'vitest'

import type { ActivityLogEntry, CleanupProposal } from './api'
import { toAppliedItems, toProposalColumns } from './adapters'

function proposal(overrides: Partial<CleanupProposal> = {}): CleanupProposal {
  return {
    id: 'prop-1',
    workspace_id: 'ws-1',
    message_id: 'msg-1',
    proposed_action: 'read_and_archive',
    before_state: { is_read: false, is_archived: false, labels: ['INBOX', 'UNREAD'] },
    after_state: { is_read: true, is_archived: true, labels: [] },
    confidence_band: 'fake_band',
    status: 'pending',
    gmail_action_command_id: null,
    decided_at: null,
    ...overrides,
  }
}

describe('toProposalColumns', () => {
  it('groups pending proposals under the account column with subject title', () => {
    const columns = toProposalColumns(
      [proposal()],
      new Map([['msg-1', { subject: '매일경제 뉴스레터', accountLabel: 'personal@gmail.com' }]]),
    )

    expect(columns).toHaveLength(1)
    expect(columns[0].label).toBe('personal@gmail.com')
    expect(columns[0].proposals[0].title).toBe('매일경제 뉴스레터')
    expect(columns[0].proposals[0].fromState).toContain('Inbox')
    expect(columns[0].proposals[0].toState).toContain('Archived')
  })

  it('skips non-pending proposals', () => {
    const columns = toProposalColumns([proposal({ status: 'approved' })], new Map())
    expect(columns).toEqual([])
  })

  it('survives malformed before/after state without throwing', () => {
    const columns = toProposalColumns(
      [
        proposal({
          before_state: { labels: 'not-an-array', is_archived: 'yes' } as never,
          after_state: null as never,
        }),
      ],
      new Map(),
    )

    expect(columns[0].proposals[0].fromState).toBe('Inbox')
    expect(columns[0].proposals[0].toState).toBe('')
  })

  it('describes mark_read without archive', () => {
    const columns = toProposalColumns(
      [
        proposal({
          proposed_action: 'mark_read',
          after_state: { is_read: true, is_archived: false, labels: ['INBOX'] },
        }),
      ],
      new Map(),
    )

    expect(columns[0].proposals[0].toState).toContain('Inbox')
    expect(columns[0].proposals[0].toState).not.toContain('Archived')
  })
})

describe('toAppliedItems', () => {
  it('maps undoable activity entries with time', () => {
    const entries: ActivityLogEntry[] = [
      {
        id: 'act-1',
        workspace_id: 'ws-1',
        command_id: 'cmd-1',
        actor_id: null,
        action_summary: '뉴스레터 18통에 Newsletter 라벨을 적용하고 아카이브했습니다.',
        occurred_at: '2026-07-10T08:12:00+09:00',
        undo_available: true,
        undone_at: null,
      },
    ]

    const items = toAppliedItems(entries)

    expect(items).toHaveLength(1)
    expect(items[0].text).toContain('뉴스레터')
    expect(items[0].when).toMatch(/08:12/)
    expect(items[0].undoAvailable).toBe(true)
  })

  it('drops already-undone entries', () => {
    const entries: ActivityLogEntry[] = [
      {
        id: 'act-2',
        workspace_id: 'ws-1',
        command_id: 'cmd-2',
        actor_id: null,
        action_summary: 'x',
        occurred_at: '2026-07-10T08:12:00+09:00',
        undo_available: false,
        undone_at: '2026-07-10T09:00:00+09:00',
      },
    ]

    expect(toAppliedItems(entries)).toEqual([])
  })
})
