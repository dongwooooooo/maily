/*
 * 설정(09 settings) 응답 → 계정 카드 뷰모델 순수 변환.
 *
 * - 계정 kind는 백엔드에 없어 일괄 'work' (briefing/archive와 동일 갭).
 * - 동기화 시각('8분 전 동기화')·진행률('62%')은 API에 없어 상태 라벨만
 *   표기한다. 확정 카피가 있는 상태(권한 필요/동기화 중) 외에는 [미확정].
 */

import type { AccountToggle, ConnectedAccount } from './data/settings.mock'
import type { SessionSummary, SourceSettings } from './api'

// 토글 key ↔ PATCH 필드 매핑 — SettingsView가 변경 시 이 필드명으로 보낸다.
export const TOGGLE_FIELDS = {
  'ai-summary': 'summary_enabled',
  briefing: 'briefing_enabled',
  notify: 'notification_enabled',
} as const

export type ToggleKey = keyof typeof TOGGLE_FIELDS

const TOGGLE_COPY: Record<ToggleKey, { label: string; hint: string }> = {
  'ai-summary': { label: 'AI 요약', hint: '메일 내용을 처리해 짧은 요약을 만듭니다' },
  briefing: { label: '브리핑 포함', hint: '오늘 브리핑과 우선순위에 이 계정을 포함합니다' },
  notify: { label: '브라우저 알림', hint: '이 계정의 중요 메일을 알림으로 보냅니다' },
}

function toToggles(settings: SourceSettings): AccountToggle[] {
  return (Object.keys(TOGGLE_FIELDS) as ToggleKey[]).map((key) => ({
    key,
    label: TOGGLE_COPY[key].label,
    hint: TOGGLE_COPY[key].hint,
    checked: settings[TOGGLE_FIELDS[key]],
  }))
}

export function toConnectedAccount(settings: SourceSettings): ConnectedAccount {
  const status = settings.status
  const ok = status === 'connected' || status === 'synced'
  const syncing = status === 'syncing'
  const permissionNeeded = status === 'permission_needed'
  return {
    id: settings.connected_account_id,
    accountKind: 'work',
    name: settings.effective_display_name,
    mail: settings.gmail_address,
    syncKind: ok ? 'ok' : syncing ? 'syncing' : 'warn',
    syncLabel: ok
      ? ''
      : syncing
        ? '동기화 중'
        : permissionNeeded
          ? '권한 필요'
          : '[미확정: 계정 상태 표시 문구]',
    headAction: permissionNeeded ? '다시 연결' : '이름 변경',
    headActionVariant: permissionNeeded ? 't2' : 't3',
    toggles: toToggles(settings),
  }
}

export function toServiceAccount(session: SessionSummary): { name: string; authLine: string } {
  return {
    name: session.display_name ?? session.email,
    authLine: `Google로 로그인 · ${session.email}`,
  }
}
