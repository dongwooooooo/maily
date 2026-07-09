'use client'

import { useEffect, useRef, useState } from 'react'

interface ScopeOption {
  key: string
  dotClassName: string
  label: string
  state: React.ReactNode
  current?: boolean
}

/** Account scope rows — copy and states ported verbatim from 03-keystone.html scope-menu. */
const scopeOptions: ScopeOption[] = [
  { key: 'all', dotClassName: 'acc-dot all', label: '전체 메일 계정', state: '6개 항목', current: true },
  {
    key: 'personal',
    dotClassName: 'acc-dot',
    label: '개인 계정',
    state: (
      <>
        <span className="ok">✓</span> 8분 전 동기화
      </>
    ),
  },
  { key: 'work', dotClassName: 'acc-dot work', label: '업무 계정', state: '동기화 중 62%' },
  {
    key: 'school',
    dotClassName: 'acc-dot school',
    label: 'school@gmail.com',
    state: (
      <>
        <span className="warn-dot" aria-hidden="true" /> 권한 필요
      </>
    ),
  },
]

/** Top bar: account scope selector with dropdown menu + notification bell — ported from 03-keystone.html. */
function Topbar() {
  const [open, setOpen] = useState(false)
  const scopeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    function handlePointerDown(event: MouseEvent) {
      if (scopeRef.current && !scopeRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <header className="topbar" aria-label="브리핑 대상 계정">
      <div className="mail-scope" ref={scopeRef}>
        <button
          className="scope-control"
          type="button"
          id="scope-toggle"
          aria-expanded={open ? 'true' : 'false'}
          aria-controls="scope-menu"
          onClick={() => setOpen((value) => !value)}
        >
          <span className="scope-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <rect x="3" y="5" width="18" height="14" rx="2"></rect>
              <path d="m3 7 9 6 9-6"></path>
            </svg>
          </span>
          <span>전체 메일 계정</span>
          <span className="sync-spinner" aria-hidden="true" title="업무 계정 동기화 중" />
          <span className="scope-caret" aria-hidden="true">
            ▾
          </span>
        </button>

        <div
          className="scope-menu"
          id="scope-menu"
          data-open={open ? 'true' : 'false'}
          role="menu"
          aria-label="브리핑 대상 메일 계정"
        >
          <div className="scope-menu-label">브리핑 대상 메일 계정</div>
          {scopeOptions.map((option) => (
            <button
              key={option.key}
              className="scope-row"
              type="button"
              role="menuitemradio"
              aria-checked={Boolean(option.current)}
              aria-current={option.current ? 'true' : undefined}
            >
              <span className={option.dotClassName} aria-hidden="true" />
              <span>{option.label}</span>
              <span className="row-state">{option.state}</span>
            </button>
          ))}
          <div className="scope-menu-foot">
            <a href="#">계정 연결 관리…</a>
          </div>
        </div>

        <button className="notification-button" type="button" aria-label="알림">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path>
            <path d="M10 21h4"></path>
          </svg>
          <span className="unread-dot" aria-hidden="true" />
        </button>
      </div>
    </header>
  )
}

export default Topbar
