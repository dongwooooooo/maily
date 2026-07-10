'use client'

import { useEffect, useMemo, useState } from 'react'
import MailList from '@/features/briefing/components/MailList'
import DetailPane from '@/features/briefing/components/DetailPane'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'
import Toast from '@/shared/ui/Toast'
import { useAutoHideToast } from '@/shared/hooks/useAutoHideToast'
import {
  fetchMessageDetail,
  fetchTodayBriefing,
  markItemSeen,
  type AccountBriefingGroup,
} from '@/features/briefing/api'
import { computeHasUrgentItems, toDetailBody, toSections } from '@/features/briefing/adapters'
import type { ApiError } from '@/shared/api/errors'
import { errorMessageFor } from '@/shared/api/errorMessages'
import type { DetailBody } from '@/features/briefing/types'

/** 03 keystone "오늘 브리핑" — editorial 3-pane layout with Undo toast. */
function MailyApp() {
  const [groups, setGroups] = useState<AccountBriefingGroup[] | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [selectedId, setSelectedId] = useState('')
  // 카드 전환 중에는 직전 상세를 유지한다(stale-while-revalidate) — 매 클릭마다
  // 상세 패널이 사라졌다 나타나며 3-pane 그리드가 재배치되는 깜빡임 방지.
  const [detailState, setDetailState] = useState<{
    messageId: string
    body: DetailBody
  } | null>(null)
  const [detailError, setDetailError] = useState<ApiError | null>(null)
  const { shown: toastShown, show: showToast, hide: hideToast } = useAutoHideToast()

  useEffect(() => {
    let cancelled = false
    fetchTodayBriefing()
      .then((data) => {
        if (cancelled) return
        setGroups(data)
        const firstCard = data.flatMap((group) => group.items).find((item) => !item.done)
        if (firstCard) setSelectedId(firstCard.id)
      })
      .catch((error: ApiError) => {
        if (!cancelled) setLoadError(error)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const sections = useMemo(() => (groups ? toSections(groups) : []), [groups])

  let selectedMessageId: string | null = null
  let selectedAccountLabel: string | null = null
  for (const group of groups ?? []) {
    const item = group.items.find((candidate) => candidate.id === selectedId)
    if (item) {
      selectedMessageId = item.message_id
      selectedAccountLabel = group.gmail_address
      break
    }
  }

  useEffect(() => {
    if (!selectedMessageId || !selectedAccountLabel) return
    let cancelled = false
    fetchMessageDetail(selectedMessageId)
      .then((data) => {
        if (!cancelled) {
          setDetailState({
            messageId: selectedMessageId,
            body: toDetailBody(data, selectedAccountLabel),
          })
          setDetailError(null)
        }
      })
      .catch((error: ApiError) => {
        // 상세 로드 실패 — 목록은 유지하고 상세 자리에 안내를 띄운다.
        if (!cancelled) setDetailError(error)
      })
    return () => {
      cancelled = true
    }
  }, [selectedMessageId, selectedAccountLabel])

  const detail = detailState?.body ?? null

  function setItemSeen(id: string, seen: boolean) {
    setGroups(
      (current) =>
        current?.map((group) => ({
          ...group,
          items: group.items.map((item) => (item.id === id ? { ...item, seen } : item)),
        })) ?? null,
    )
  }

  function handleSelect(id: string) {
    setSelectedId(id)
    // 카드 열람 = 서비스 확인함(seen). Gmail 읽음과는 무관. 낙관 업데이트 후
    // 실패하면 되돌린다 — 백엔드에 기록 안 된 확인함이 세션 내내 남지 않게.
    setItemSeen(id, true)
    markItemSeen(id).catch((error) => {
      console.error('seen 처리 실패', error)
      setItemSeen(id, false)
    })
  }

  const hasUrgent = computeHasUrgentItems(sections)

  return (
    <>
      <a className="skip-link" href="#today-briefing">
        오늘 브리핑 목록으로 이동
      </a>
      {/* 그리드 열 구성은 긴급 항목 유무로만 정한다 — 상세 로딩 중 열이
          접혔다 펴지는 reflow 금지 (코드리뷰 Major). */}
      <div className={`app${hasUrgent ? '' : ' app-no-detail'}`}>
        <Sidebar />
        <Topbar />
        {loadError ? (
          <main className="list-pane" id="today-briefing" aria-label="오늘 브리핑 — 오류">
            <p className="list-error" role="alert">
              {errorMessageFor(loadError)}
            </p>
          </main>
        ) : (
          groups && <MailList sections={sections} selectedId={selectedId} onSelect={handleSelect} />
        )}
        {hasUrgent &&
          (detail ? (
            <DetailPane detail={detail} onMarkRead={showToast} />
          ) : detailError ? (
            <aside className="detail-pane" aria-label="선택한 메일 — 오류">
              <p className="list-error" role="alert">
                {errorMessageFor(detailError)}
              </p>
            </aside>
          ) : (
            <aside className="detail-pane" aria-label="선택한 메일 — 로딩 중" />
          ))}
      </div>
      <Toast show={toastShown} onUndo={hideToast} onClose={hideToast} />
    </>
  )
}

export default MailyApp
