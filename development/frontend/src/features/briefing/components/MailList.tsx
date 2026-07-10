import type {
  AccountLine as AccountLineType,
  CompactItem,
  MailCardItem,
  Section as SectionType,
} from '@/features/briefing/types'
import { computeHasUrgentItems } from '@/features/briefing/adapters'
import EmptyBriefing from '@/features/briefing/components/EmptyBriefing'

function BriefcaseIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M4 8h16v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" />
      <path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

function PersonIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5 20c1.2-3.6 4-5.4 7-5.4S17.8 16.4 19 20" />
    </svg>
  )
}

/** Account avatar — photo (gradient) for personal, neutral icon for work/school. No color-coded badges. */
function AccountAvatar({ kind }: { kind: AccountLineType['kind'] }) {
  if (kind === 'personal') {
    return <span className="avatar photo" aria-hidden="true" />
  }
  return (
    <span className="avatar icon" aria-hidden="true">
      {kind === 'work' ? <BriefcaseIcon /> : <PersonIcon />}
    </span>
  )
}

function AccountLine({ account }: { account: AccountLineType }) {
  return (
    <div className="account-line">
      <AccountAvatar kind={account.kind} />
      <span>{account.label}</span>
    </div>
  )
}

interface MailCardProps {
  item: MailCardItem
  selected: boolean
  onSelect: (id: string) => void
}

function MailCard({ item, selected, onSelect }: MailCardProps) {
  return (
    <article
      className={`mail-card${item.seen ? ' seen' : ''}${selected ? ' selected' : ''}`}
      tabIndex={0}
      role="button"
      aria-pressed={selected}
      aria-label={
        selected
          ? `선택됨: ${item.title}`
          : item.seenLabel
            ? `${item.seenLabel}: ${item.title}`
            : undefined
      }
      onClick={() => onSelect(item.id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect(item.id)
        }
      }}
    >
      <div className="card-content">
        <div className="card-top">
          <h3 className="card-title">{item.title}</h3>
          <span className="card-sender">{item.sender}</span>
        </div>
        <p className="card-summary">
          {!item.noSummaryTag && <span className="sum-tag">요약</span>}
          {item.summary}
        </p>
        {item.stateMeta && <span className="state-meta">{item.stateMeta}</span>}
      </div>
    </article>
  )
}

function CompactRow({ item }: { item: CompactItem }) {
  return (
    <article className="mail-card compact">
      <span className="compact-title">{item.title}</span>
      <span className="compact-meta">
        {item.metaOk ? (
          <>
            <span className="ok">✓</span> {item.meta}
          </>
        ) : (
          item.meta
        )}
      </span>
    </article>
  )
}

function SectionMenu({ sectionLabel }: { sectionLabel: string }) {
  return (
    <button
      className="section-menu"
      type="button"
      onClick={(event) => event.preventDefault()}
      aria-label={`${sectionLabel} 섹션 메뉴`}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="5" cy="12" r="1"></circle>
        <circle cx="12" cy="12" r="1"></circle>
        <circle cx="19" cy="12" r="1"></circle>
      </svg>
    </button>
  )
}

interface SectionProps {
  section: SectionType
  selectedId: string
  onSelect: (id: string) => void
}

/** One collapsible list section (details/summary, default open) — account lines, cards, compact rows. */
function Section({ section, selectedId, onSelect }: SectionProps) {
  const headingId = `section-${section.id}`

  return (
    <details className="section" aria-labelledby={headingId} open>
      <summary className="section-head">
        <div className="section-title">
          <svg className="section-chevron" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 6l6 6-6 6" />
          </svg>
          <h2 id={headingId}>{section.heading}</h2>
          {section.count !== undefined && <span>{section.count}</span>}
        </div>
        <SectionMenu sectionLabel={section.heading} />
      </summary>

      <div className="mail-list">
        {section.cardGroups?.map((group) => (
          <div key={group.account.label}>
            <AccountLine account={group.account} />
            {group.cards.map((card) => (
              <MailCard
                key={card.id}
                item={card}
                selected={card.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </div>
        ))}

        {section.compactGroups?.map((group) => (
          <div key={group.account.label}>
            <AccountLine account={group.account} />
            {group.items.map((item) => (
              <CompactRow key={item.id} item={item} />
            ))}
          </div>
        ))}

        {section.showAddSection && (
          <button className="add-section" type="button">
            섹션 추가
          </button>
        )}
      </div>
    </details>
  )
}

interface MailListProps {
  sections: SectionType[]
  selectedId: string
  onSelect: (id: string) => void
}

/** Center pane: 오늘 브리핑 sections, each collapsible.
 *
 * 내 섹션(사용자 분류함)은 데이터 소스(라벨 API 연결)가 아직 없어 표시하지
 * 않는다 — F8(rules/labels 연결)에서 복원. */
function MailList({ sections, selectedId, onSelect }: MailListProps) {
  if (!computeHasUrgentItems(sections)) {
    const passiveSections = sections.filter((section) => section.id === 'done')
    return (
      <main className="list-pane" id="today-briefing" aria-label="오늘 브리핑 — 빈 상태">
        <EmptyBriefing />
        {passiveSections.map((section) => (
          <Section key={section.id} section={section} selectedId={selectedId} onSelect={onSelect} />
        ))}
      </main>
    )
  }

  return (
    <main className="list-pane" id="today-briefing" aria-label="오늘 브리핑 목록">
      {sections.map((section) => (
        <Section key={section.id} section={section} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </main>
  )
}

export default MailList
