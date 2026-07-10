/*
 * 09 설정 화면의 뷰모델 타입·고정 카피.
 * 서비스 계정·연결 계정 데이터는 F6에서 실제 API(settings/api.ts +
 * adapters.ts)로 교체되어 삭제됐다.
 */

import type { AccountKind } from '@/features/briefing/types'

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

export const reconnectBannerCopy = '이 계정의 Gmail 권한을 다시 연결해야 합니다.'

export const notificationPermission = {
  title: '브라우저 알림 권한',
  hint: '허용됨 · 중요 메일과 정리 검토 요청만 알립니다',
  actionLabel: '브라우저 설정 열기',
}
