import { describe, expect, it } from 'vitest'

import type { SessionSummary, SourceSettings } from './api'
import { toConnectedAccount, toServiceAccount } from './adapters'

function settings(overrides: Partial<SourceSettings> = {}): SourceSettings {
  return {
    connected_account_id: 'acc-1',
    gmail_address: 'work@gmail.com',
    display_name: null,
    effective_display_name: 'work@gmail.com',
    status: 'connected',
    briefing_enabled: true,
    summary_enabled: true,
    notification_enabled: false,
    paused: false,
    ...overrides,
  }
}

describe('toConnectedAccount', () => {
  it('maps settings to the account card view model', () => {
    const account = toConnectedAccount(settings())

    expect(account.id).toBe('acc-1')
    expect(account.name).toBe('work@gmail.com')
    expect(account.mail).toBe('work@gmail.com')
    expect(account.syncKind).toBe('ok')
    expect(account.toggles.map((toggle) => [toggle.key, toggle.checked])).toEqual([
      ['ai-summary', true],
      ['briefing', true],
      ['notify', false],
    ])
  })

  it('maps permission_needed to warn with 권한 필요 label and 다시 연결 action', () => {
    const account = toConnectedAccount(settings({ status: 'permission_needed' }))

    expect(account.syncKind).toBe('warn')
    expect(account.syncLabel).toBe('권한 필요')
    expect(account.headAction).toBe('다시 연결')
    expect(account.headActionVariant).toBe('t2')
  })

  it('maps syncing status to the 동기화 중 label', () => {
    const account = toConnectedAccount(settings({ status: 'syncing' }))

    expect(account.syncKind).toBe('syncing')
    expect(account.syncLabel).toBe('동기화 중')
  })

  it('keeps unknown-ish statuses visible without leaking the raw value', () => {
    const account = toConnectedAccount(settings({ status: 'error' }))

    expect(account.syncKind).toBe('warn')
    expect(account.syncLabel.startsWith('[미확정')).toBe(true)
  })
})

describe('toServiceAccount', () => {
  it('maps the session summary to the service account row', () => {
    const session: SessionSummary = {
      user_id: 'user-1',
      workspace_id: 'ws-1',
      email: 'woomacho@gmail.com',
      display_name: 'dongwoo',
      workspace_name: null,
    }

    const account = toServiceAccount(session)

    expect(account.name).toBe('dongwoo')
    expect(account.authLine).toBe('Google로 로그인 · woomacho@gmail.com')
  })

  it('falls back to email when display_name is null', () => {
    const session: SessionSummary = {
      user_id: 'user-1',
      workspace_id: 'ws-1',
      email: 'woomacho@gmail.com',
      display_name: null,
      workspace_name: null,
    }

    expect(toServiceAccount(session).name).toBe('woomacho@gmail.com')
  })
})
