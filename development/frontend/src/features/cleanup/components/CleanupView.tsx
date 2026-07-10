'use client'

import { useEffect, useState } from 'react'

import type { AppliedItem, Proposal, ProposalColumn } from '@/features/cleanup/data/cleanup.mock'
import {
  approveCleanupProposal,
  approveRuleSuggestion,
  fetchActivityLog,
  fetchCleanupQueue,
  fetchRules,
  undoActivity,
} from '@/features/cleanup/api'
import { toAppliedItems, toProposalColumns, toRuleProposals } from '@/features/cleanup/adapters'
import { fetchMessageDetail } from '@/features/briefing/api'
import { fetchSources } from '@/shared/api/sources'
import type { ApiError } from '@/shared/api/errors'
import { errorMessageFor } from '@/shared/api/errorMessages'

function accDotClassName(kind: ProposalColumn['accountKind']) {
  return kind === 'personal' ? 'acc-dot' : `acc-dot ${kind}`
}

interface ProposalCardProps {
  kind: 'cleanup' | 'rule'
  proposal: Proposal
  onApprove: (proposalId: string) => void
}

function ProposalCard({ kind, proposal, onApprove }: ProposalCardProps) {
  const isRule = kind === 'rule'

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
          <button
            className="icon-action"
            type="button"
            aria-label="승인"
            title={isRule ? '승인 — 자동 정리 규칙을 만듭니다' : '승인 — Gmail에 적용합니다'}
            onClick={() => onApprove(proposal.id)}
          >
            <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 4 4L19 6"></path>
            </svg>
          </button>
          {/* 제외(reject)는 백엔드 엔드포인트 부재 — 배선 보류, 후속 작업. */}
          <button
            className="more-action"
            type="button"
            aria-label="제외"
            title={
              isRule ? '제외 — 계속 개별 승인으로 둡니다' : '제외 — 이 제안을 적용하지 않습니다'
            }
            disabled
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
  const [columns, setColumns] = useState<ProposalColumn[] | null>(null)
  const [ruleProposals, setRuleProposals] = useState<Proposal[]>([])
  const [applied, setApplied] = useState<AppliedItem[]>([])
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchRules()
      .then((rules) => {
        if (!cancelled) setRuleProposals(toRuleProposals(rules.suggestions))
      })
      .catch((error: ApiError) => {
        if (!cancelled) setLoadError(error)
      })

    Promise.all([fetchCleanupQueue(), fetchActivityLog(), fetchSources()])
      .then(async ([proposals, activity, sources]) => {
        const accountBysource = new Map(
          sources.map((source) => [source.id, source.gmail_address]),
        )
        // 제안 카드 제목은 메시지 상세로 보강 — CleanupProposal엔 message_id뿐.
        const lookup = new Map<string, { subject: string; accountLabel: string }>()
        await Promise.all(
          [...new Set(proposals.map((item) => item.message_id))].map(async (messageId) => {
            try {
              const detail = await fetchMessageDetail(messageId)
              lookup.set(messageId, {
                subject: detail.subject ?? '[미확정: 제목 없는 메일 표시 문구]',
                accountLabel: accountBysource.get(detail.connected_account_id) ?? '',
              })
            } catch {
              // 보강 실패 — 어댑터 폴백 문구로 렌더.
            }
          }),
        )
        if (cancelled) return
        setColumns(toProposalColumns(proposals, lookup))
        setApplied(toAppliedItems(activity))
      })
      .catch((error: ApiError) => {
        if (!cancelled) setLoadError(error)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleApprove(proposalId: string) {
    approveCleanupProposal(proposalId)
      .then(() => {
        setActionError(null)
        setColumns(
          (current) =>
            current
              ?.map((column) => ({
                ...column,
                proposals: column.proposals.filter((item) => item.id !== proposalId),
              }))
              .filter((column) => column.proposals.length > 0) ?? null,
        )
        // 승인 → execute_action job이 비동기 적용 — 활동 로그를 재조회해
        // '오늘 적용됨'을 갱신한다(적용 완료 전이면 다음 방문 때 표시).
        fetchActivityLog()
          .then((activity) => setApplied(toAppliedItems(activity)))
          .catch(() => {})
      })
      .catch((error: ApiError) => {
        console.error('제안 승인 실패', error)
        setActionError(error)
      })
  }

  function handleApproveRule(suggestionId: string) {
    approveRuleSuggestion(suggestionId)
      .then(() => {
        setActionError(null)
        setRuleProposals((current) => current.filter((item) => item.id !== suggestionId))
      })
      .catch((error: ApiError) => {
        console.error('규칙 제안 승인 실패', error)
        setActionError(error)
      })
  }

  function handleUndo(activityId: string) {
    undoActivity(activityId)
      .then(() => {
        setActionError(null)
        setApplied((current) => current.filter((item) => item.id !== activityId))
        onUndoApplied()
      })
      .catch((error: ApiError) => {
        console.error('되돌리기 실패', error)
        setActionError(error)
      })
  }

  const totalCount =
    (columns ?? []).reduce((sum, column) => sum + column.proposals.length, 0) +
    ruleProposals.length

  return (
    <main className="list-pane" id="cleanup" aria-label="정리 검토">
      <div className="trust-note">
        <h2>정리 검토 {totalCount}건</h2>
        <p>승인 전에는 Gmail을 변경하지 않습니다.</p>
      </div>

      {(loadError || actionError) && (
        <p className="list-error" role="alert">
          {errorMessageFor((loadError ?? actionError)!)}
        </p>
      )}

      <div className="cleanup-grid">
        {columns?.map((column) => (
          <section className="acc-col" aria-label={`${column.label} 제안`} key={column.label}>
            <div className="col-head">
              <span className={accDotClassName(column.accountKind)} />
              {column.label}
              <span className="cnt">제안 {column.proposals.length}건</span>
            </div>
            {column.proposals.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                kind="cleanup"
                proposal={proposal}
                onApprove={handleApprove}
              />
            ))}
          </section>
        ))}

        {/* RuleSuggestion에 계정 필드가 없어 보드처럼 계정 칼럼에 섞지 못하고
            별도 칼럼으로 묶는다 — adapters.toRuleProposals 참조. */}
        {ruleProposals.length > 0 && (
          <section className="acc-col" aria-label="규칙 제안">
            <div className="col-head">
              규칙 제안
              <span className="cnt">제안 {ruleProposals.length}건</span>
            </div>
            {ruleProposals.map((proposal) => (
              <ProposalCard
                key={proposal.id}
                kind="rule"
                proposal={proposal}
                onApprove={handleApproveRule}
              />
            ))}
          </section>
        )}
      </div>

      <section className="section" style={{ marginTop: 30, maxWidth: 'none' }}>
        <div className="section-head">
          <div className="section-title">
            <h2>오늘 적용됨</h2>
            <span>{applied.length}</span>
          </div>
        </div>
        <div className="mail-list" style={{ gap: 8 }}>
          {applied.map((item) => (
            <div className="applied-row" key={item.id}>
              <span className="txt">
                <span className="ok">✓</span> {item.text}
                <span className="when">{item.when}</span>
              </span>
              {item.undoAvailable && (
                <button
                  className="icon-action"
                  type="button"
                  aria-label="되돌리기"
                  title="되돌리기 — Gmail 변경을 원복합니다"
                  onClick={() => handleUndo(item.id)}
                >
                  <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
                    <path d="M3 3v5h5"></path>
                  </svg>
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

export default CleanupView
