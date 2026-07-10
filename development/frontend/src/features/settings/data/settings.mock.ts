import type { AccountKind } from '@/features/briefing/types'

export const serviceAccount = {
  name: 'dongwoo',
  authLine: 'Google로 로그인 · woomacho@gmail.com',
}

export interface AccountToggle {
  key: string
  label: string
  hint: string
  checked: boolean
}

export type SyncKind = 'ok' | 'syncing' | 'warn'

export interface ConnectedAccount {
  id: string
  accountKind: AccountKind
  name: string
  mail: string
  syncKind: SyncKind
  syncLabel: string
  headAction: string
  headActionVariant: 't2' | 't3'
  toggles: AccountToggle[]
}

export const connectedAccounts: ConnectedAccount[] = [
  {
    id: 'personal',
    accountKind: 'personal',
    name: '개인 계정',
    mail: 'woomacho@gmail.com',
    syncKind: 'ok',
    syncLabel: '8분 전 동기화',
    headAction: '이름 변경',
    headActionVariant: 't3',
    toggles: [
      {
        key: 'ai-summary',
        label: 'AI 요약',
        hint: '메일 내용을 처리해 짧은 요약을 만듭니다',
        checked: true,
      },
      {
        key: 'briefing',
        label: '브리핑 포함',
        hint: '오늘 브리핑과 우선순위에 이 계정을 포함합니다',
        checked: true,
      },
      {
        key: 'notify',
        label: '브라우저 알림',
        hint: '이 계정의 중요 메일을 알림으로 보냅니다',
        checked: true,
      },
    ],
  },
  {
    id: 'work',
    accountKind: 'work',
    name: '업무 계정',
    mail: 'dongwoo@company.com',
    syncKind: 'syncing',
    syncLabel: '동기화 중 62%',
    headAction: '이름 변경',
    headActionVariant: 't3',
    toggles: [
      {
        key: 'ai-summary',
        label: 'AI 요약',
        hint: '메일 내용을 처리해 짧은 요약을 만듭니다',
        checked: true,
      },
      {
        key: 'briefing',
        label: '브리핑 포함',
        hint: '오늘 브리핑과 우선순위에 이 계정을 포함합니다',
        checked: true,
      },
      {
        key: 'notify',
        label: '브라우저 알림',
        hint: '이 계정의 중요 메일을 알림으로 보냅니다',
        checked: false,
      },
    ],
  },
  {
    id: 'school',
    accountKind: 'school',
    name: 'school@gmail.com',
    mail: '표시 이름 없음',
    syncKind: 'warn',
    syncLabel: '권한 필요',
    headAction: '다시 연결',
    headActionVariant: 't2',
    toggles: [
      {
        key: 'ai-summary',
        label: 'AI 요약',
        hint: '요약이 꺼져 있습니다. 카드에는 메타데이터만 표시됩니다',
        checked: false,
      },
      {
        key: 'briefing',
        label: '브리핑 포함',
        hint: '오늘 브리핑과 우선순위에 이 계정을 포함합니다',
        checked: true,
      },
      {
        key: 'notify',
        label: '브라우저 알림',
        hint: '이 계정의 중요 메일을 알림으로 보냅니다',
        checked: false,
      },
    ],
  },
]

export const reconnectBannerCopy = '이 계정의 Gmail 권한을 다시 연결해야 합니다.'

export const notificationPermission = {
  title: '브라우저 알림 권한',
  hint: '허용됨 · 중요 메일과 정리 검토 요청만 알립니다',
  actionLabel: '브라우저 설정 열기',
}
