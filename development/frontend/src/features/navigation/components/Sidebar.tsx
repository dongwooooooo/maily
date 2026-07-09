'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { primaryNav, subNav, userName } from '@/features/briefing/data/briefing.mock'

/** Settings gear (계정 설정) — ported from 03-keystone.html; a gear, not a kebab menu. */
function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3"></circle>
      <path d="M12 3v2.5M12 18.5V21M21 12h-2.5M5.5 12H3M18.02 5.98l-1.77 1.77M7.75 16.27l-1.77 1.77M18.02 18.02l-1.77-1.77M7.75 7.73 5.98 5.98"></path>
    </svg>
  )
}

/**
 * Left navigation pane — ported from design/boards/v1/current/03-keystone.html.
 * "오늘 브리핑" collapses its sub-sections via native <details>/<summary> (default open).
 * Only the sub-nav rows show counts; the "오늘 브리핑" row itself shows no total.
 */
function Sidebar() {
  const pathname = usePathname()
  const [today, ...restNav] = primaryNav
  const isBriefingPage = pathname === today.href

  return (
    <aside className="sidebar" aria-label="메일 브리핑 내비게이션">
      <div className="identity">
        <a className="brand-home" href="#" aria-label="Maily 홈으로 이동">
          <span className="brand-mark">M</span>
        </a>
      </div>

      <nav className="side-nav" aria-label="주요 화면">
        {isBriefingPage ? (
          <details className="nav-details" open>
            <summary>
              <div className="nav-row active">
                <svg className="nav-chev" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M9 6l6 6-6 6" />
                </svg>
                <span>{today.label}</span>
              </div>
            </summary>
            <div className="sub-nav" aria-label="오늘 브리핑 섹션">
              {subNav.map((sub) => (
                <a
                  key={sub.label}
                  className="sub-row"
                  href={sub.target}
                  aria-current={sub.current ? 'true' : undefined}
                >
                  <span>{sub.label}</span>
                  <span>{sub.count ?? ''}</span>
                </a>
              ))}
            </div>
          </details>
        ) : (
          <Link className="nav-row" href={today.href}>
            <span>{today.label}</span>
            <span className="nav-count">{today.count ?? ''}</span>
          </Link>
        )}

        {restNav.map((item) => {
          const active = pathname === item.href
          const isRoute = item.href.startsWith('/')
          const content = (
            <>
              <span>{item.label}</span>
              <span className="nav-count">{item.count ?? ''}</span>
            </>
          )
          return isRoute ? (
            <Link
              key={item.key}
              className={`nav-row${active ? ' active' : ''}`}
              href={item.href}
              aria-current={active ? 'page' : undefined}
            >
              {content}
            </Link>
          ) : (
            <a key={item.key} className="nav-row" href={item.href}>
              {content}
            </a>
          )
        })}
      </nav>

      <div className="service-footer" aria-label="서비스 계정">
        <div className="service-strip">
          <span className="service-avatar" aria-hidden="true" />
          <span className="service-name">{userName}</span>
          <button className="icon-button" type="button" aria-label="계정 설정">
            <GearIcon />
          </button>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
