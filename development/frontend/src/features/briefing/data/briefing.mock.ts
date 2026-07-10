/*
 * 03 keystone 화면의 고정 카피·정적 구조 상수.
 * 브리핑 목록·상세 샘플 데이터는 F4에서 실제 API(briefing/api.ts +
 * adapters.ts)로 교체되어 삭제됐다. 남은 것은 아직 API 소스가 없는
 * 정적 구조(내비게이션)와 보드 확정 카피뿐이다.
 */

export type NavKey = 'briefing' | 'storage' | 'cleanup' | 'log' | 'settings'

export interface NavItem {
  key: NavKey
  label: string
  href: string
  count?: number
}

export interface SubNavItem {
  label: string
  target: string
  count?: number
  current?: boolean
}

// 내비 카운트는 아직 정적 — 데이터 연결은 후속(F5~F8) 화면 작업에서.
export const primaryNav: NavItem[] = [
  { key: 'briefing', label: '오늘 브리핑', href: '/', count: 8 },
  { key: 'storage', label: '보관함', href: '/storage' },
  { key: 'cleanup', label: '정리 검토', href: '/cleanup-review', count: 3 },
  { key: 'log', label: '활동 로그', href: '#activity-log' },
  { key: 'settings', label: '설정', href: '/settings' },
]

export const subNav: SubNavItem[] = [
  { label: '새 중요 항목', target: '#section-important', count: 4, current: true },
  { label: '답장 필요', target: '#section-reply', count: 1 },
  { label: '나중에 봐도 됨', target: '#section-later', count: 1 },
  { label: '정리됨', target: '#section-organized' },
  { label: '승인 필요', target: '#section-approval', count: 1 },
]

export const userName = 'dongwoo'

export interface DigestItem {
  value: string
  label: string
  warn?: boolean
}

export const emptyBriefingCopy = {
  heading: '오늘 급하게 확인할 메일은 없습니다',
  lede: '새 중요한 메일은 이곳에 표시되거나 알림으로 알려드립니다.',
}

export const emptyDigest: DigestItem[] = [
  { value: '18건', label: '오늘 정리됨' },
  { value: '09:24', label: '최근 동기화' },
  { value: '12:00', label: '다음 확인 예정' },
  { value: '3개', label: '연결 계정 · 권한 필요 1', warn: true },
]

export interface EmptyLink {
  label: string
  href: string
}

export const emptyLinks: EmptyLink[] = [
  { label: '보관함 보기', href: '/storage' },
  { label: '알림 설정 확인', href: '/settings' },
]

export const toastCopy = {
  message: 'Gmail에서도 읽음 처리했습니다.',
  undo: '되돌리기',
  close: '닫기',
}
