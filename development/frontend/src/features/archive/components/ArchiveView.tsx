'use client'

import { useEffect, useRef, useState } from 'react'
import type { AccountKind } from '@/features/briefing/types'
import { addLabelCopy, type TimelineGroup } from '@/features/archive/data/archive.mock'
import { fetchLabels, fetchUpcomingStorage } from '@/features/archive/api'
import { toLabelGroups, toUpcomingGroups } from '@/features/archive/adapters'
import { fetchMessageDetail } from '@/features/briefing/api'
import { errorMessageFor } from '@/shared/api/errorMessages'
import type { ApiError } from '@/shared/api/errors'

type ArchiveTab = 'upcoming' | 'labels'

const TABS: { key: ArchiveTab; label: string }[] = [
  { key: 'upcoming', label: '예정' },
  { key: 'labels', label: '라벨' },
]

function accDotClassName(kind: AccountKind) {
  return kind === 'personal' ? 'acc-dot' : `acc-dot ${kind}`
}

function accDotTitle(kind: AccountKind) {
  if (kind === 'work') return '업무 계정'
  if (kind === 'school') return 'school@gmail.com'
  return '개인 계정'
}

function TimelineList({
  group,
  onSelectMessage,
}: {
  group: TimelineGroup
  onSelectMessage?: (messageId: string) => void
}) {
  return (
    <div className="tl-group">
      <div className="tl-head">
        <b>{group.heading}</b>
        <span>{group.meta}</span>
      </div>
      <div className="tl-list">
        {group.items.map((item) => (
          <button
            key={item.id}
            className="tl-row"
            type="button"
            onClick={() => {
              if (item.messageId && onSelectMessage) onSelectMessage(item.messageId)
            }}
          >
            <span
              className={accDotClassName(item.accountKind)}
              title={accDotTitle(item.accountKind)}
            />
            <span className="tl-title">{item.title}</span>
            <span className="tl-state">{item.state}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

interface ArchiveViewProps {
  /** 예정 항목 클릭 → 상세 패널에 해당 메시지 로드 (ArchivePage가 fetch). */
  onSelectMessage: (messageId: string) => void
}

/** Center pane: 보관함 — 예정 타임라인 / 라벨 탭, sliding indicator — ported from 07-storage.html. */
function ArchiveView({ onSelectMessage }: ArchiveViewProps) {
  const [activeTab, setActiveTab] = useState<ArchiveTab>('upcoming')
  const [upcomingGroups, setUpcomingGroups] = useState<TimelineGroup[] | null>(null)
  const [labelGroups, setLabelGroups] = useState<TimelineGroup[] | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchUpcomingStorage(), fetchLabels()])
      .then(async ([upcoming, labels]) => {
        // upcoming 항목에는 제목이 없어(message_id만) 상세를 조회해 보강한다.
        const messageIds = [
          ...new Set(
            [...upcoming.today, ...upcoming.tomorrow, ...upcoming.this_week].map(
              (entry) => entry.message_id,
            ),
          ),
        ]
        const titles = new Map<string, string>()
        await Promise.all(
          messageIds.map(async (messageId) => {
            try {
              const detail = await fetchMessageDetail(messageId)
              if (detail.subject) titles.set(messageId, detail.subject)
            } catch {
              // 제목 보강 실패는 폴백 문구로 처리 — 목록 자체는 유지.
            }
          }),
        )
        if (cancelled) return
        setUpcomingGroups(toUpcomingGroups(upcoming, titles))
        setLabelGroups(toLabelGroups(labels))
      })
      .catch((error: ApiError) => {
        if (!cancelled) setLoadError(error)
      })
    return () => {
      cancelled = true
    }
  }, [])
  const tabRefs = useRef<Record<ArchiveTab, HTMLButtonElement | null>>({
    upcoming: null,
    labels: null,
  })
  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, width: 0 })

  useEffect(() => {
    function moveIndicator() {
      const node = tabRefs.current[activeTab]
      if (node) {
        setIndicatorStyle({ left: node.offsetLeft, width: node.offsetWidth })
      }
    }
    moveIndicator()
    window.addEventListener('resize', moveIndicator)
    return () => window.removeEventListener('resize', moveIndicator)
  }, [activeTab])

  function handleKeyDown(event: React.KeyboardEvent, index: number) {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!delta) return
    event.preventDefault()
    const next = TABS[(index + delta + TABS.length) % TABS.length]
    setActiveTab(next.key)
    tabRefs.current[next.key]?.focus()
  }

  return (
    <main className="list-pane" id="storage" aria-label="보관함">
      <div className="view-tabs" role="tablist" aria-label="보관함 보기">
        <span
          className="tab-indicator"
          aria-hidden="true"
          style={{ left: indicatorStyle.left, width: indicatorStyle.width }}
        />
        {TABS.map((tab, index) => (
          <button
            key={tab.key}
            ref={(node) => {
              tabRefs.current[tab.key] = node
            }}
            className="view-tab"
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            tabIndex={activeTab === tab.key ? 0 : -1}
            onClick={() => setActiveTab(tab.key)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loadError && (
        <p className="list-error" role="alert">
          {errorMessageFor(loadError)}
        </p>
      )}

      {activeTab === 'upcoming' &&
        upcomingGroups?.map((group) => (
          <TimelineList key={group.id} group={group} onSelectMessage={onSelectMessage} />
        ))}

      {activeTab === 'labels' && labelGroups && (
        <>
          {labelGroups.map((group) => (
            <TimelineList key={group.id} group={group} />
          ))}
          <button className="add-section" type="button">
            {addLabelCopy}
          </button>
        </>
      )}
    </main>
  )
}

export default ArchiveView
