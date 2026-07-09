import Link from 'next/link'
import { emptyBriefingCopy, emptyDigest, emptyLinks } from '@/features/briefing/data/briefing.mock'

/** 04 오늘 브리핑 — 빈 상태: 안심 다이제스트 + 바로가기, ported from 04-empty-state.html. */
function EmptyBriefing() {
  return (
    <>
      <section className="empty-hero">
        <h2>{emptyBriefingCopy.heading}</h2>
        <p>{emptyBriefingCopy.lede}</p>
      </section>

      <section className="digest" aria-label="확인 다이제스트">
        {emptyDigest.map((item) => (
          <div className="digest-item" key={item.label}>
            <span className="digest-value">
              {item.value}
              {item.warn && <span className="warn-dot" aria-hidden="true" />}
            </span>
            <span className="digest-label">{item.label}</span>
          </div>
        ))}
      </section>

      <div className="empty-links">
        {emptyLinks.map((link) =>
          link.href.startsWith('/') ? (
            <Link key={link.label} href={link.href}>
              {link.label}
            </Link>
          ) : (
            <a key={link.label} href={link.href}>
              {link.label}
            </a>
          ),
        )}
      </div>
    </>
  )
}

export default EmptyBriefing
