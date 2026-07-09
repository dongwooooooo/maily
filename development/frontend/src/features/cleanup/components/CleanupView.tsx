import {
  appliedToday,
  proposalColumns,
  type Proposal,
  type ProposalColumn,
} from '@/features/cleanup/data/cleanup.mock'

function accDotClassName(kind: ProposalColumn['accountKind']) {
  return kind === 'personal' ? 'acc-dot' : `acc-dot ${kind}`
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  return (
    <article className="proposal">
      <div className="prop-top">
        <span className="prop-title">{proposal.title}</span>
        <span className="prop-count">{proposal.count}</span>
      </div>
      <p className="prop-desc">{proposal.desc}</p>
      <div className="state-flow">
        {proposal.fromState} → <b>{proposal.toState}</b>
      </div>
      <div className="prop-foot">
        <span />
        <div className="prop-actions">
          <button className="icon-action" type="button" aria-label="승인" title="승인 — Gmail에 적용합니다">
            <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 4 4L19 6"></path>
            </svg>
          </button>
          <button
            className="more-action"
            type="button"
            aria-label="제외"
            title="제외 — 이 제안을 적용하지 않습니다"
          >
            <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M18 6 6 18"></path>
              <path d="m6 6 12 12"></path>
            </svg>
          </button>
        </div>
      </div>
    </article>
  )
}

interface CleanupViewProps {
  onUndoApplied: () => void
}

/** 10 정리 검토 — 계정별 제안 칼럼 + 개별 승인 게이트, ported from 10-cleanup-review.html. */
function CleanupView({ onUndoApplied }: CleanupViewProps) {
  const totalCount = proposalColumns.reduce((sum, column) => sum + column.proposals.length, 0)

  return (
    <main className="list-pane" id="cleanup" aria-label="정리 검토">
      <div className="trust-note">
        <h2>정리 검토 {totalCount}건</h2>
        <p>승인 전에는 Gmail을 변경하지 않습니다.</p>
      </div>

      <div className="cleanup-grid">
        {proposalColumns.map((column) => (
          <section className="acc-col" aria-label={`${column.label} 제안`} key={column.label}>
            <div className="col-head">
              <span className={accDotClassName(column.accountKind)} />
              {column.label}
              <span className="cnt">제안 {column.proposals.length}건</span>
            </div>
            {column.proposals.map((proposal) => (
              <ProposalCard key={proposal.id} proposal={proposal} />
            ))}
          </section>
        ))}
      </div>

      <section className="section" style={{ marginTop: 30, maxWidth: 'none' }}>
        <div className="section-head">
          <div className="section-title">
            <h2>오늘 적용됨</h2>
            <span>{appliedToday.length}</span>
          </div>
        </div>
        <div className="mail-list" style={{ gap: 8 }}>
          {appliedToday.map((item) => (
            <div className="applied-row" key={item.id}>
              <span className="txt">
                <span className="ok">✓</span> {item.text}
                <span className="when">{item.when}</span>
              </span>
              <button
                className="icon-action"
                type="button"
                aria-label="되돌리기"
                title="되돌리기 — Gmail 변경을 원복합니다"
                onClick={onUndoApplied}
              >
                <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
                  <path d="M3 3v5h5"></path>
                </svg>
              </button>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

export default CleanupView
