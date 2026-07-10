'use client'

import { useEffect, useState } from 'react'
import ArchiveView from '@/features/archive/components/ArchiveView'
import DetailPane from '@/features/briefing/components/DetailPane'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'
import Toast from '@/shared/ui/Toast'
import { useAutoHideToast } from '@/shared/hooks/useAutoHideToast'
import { storageDetail } from '@/features/archive/data/archive.mock'
import { fetchSources } from '@/features/archive/api'
import { fetchMessageDetail } from '@/features/briefing/api'
import { toDetailBody } from '@/features/briefing/adapters'
import type { DetailBody } from '@/features/briefing/types'

/** 07 storage "보관함" — editorial 3-pane layout, ported from 07-storage.html.
 *
 * 예정 항목을 클릭하면 해당 메시지 상세를 로드한다. 아무것도 선택하기 전에는
 * 정적 샘플(storageDetail)을 보여준다 — 초기 상세의 실데이터화는 후속. */
function ArchivePage() {
  const { shown: toastShown, show: showToast, hide: hideToast } = useAutoHideToast()
  const [detail, setDetail] = useState<DetailBody | null>(null)
  const [accountLabels, setAccountLabels] = useState<Map<string, string>>(new Map())

  useEffect(() => {
    let cancelled = false
    fetchSources()
      .then((sources) => {
        if (cancelled) return
        setAccountLabels(new Map(sources.map((source) => [source.id, source.gmail_address])))
      })
      .catch((error) => console.error('연결 계정 목록 로드 실패', error))
    return () => {
      cancelled = true
    }
  }, [])

  function handleSelectMessage(messageId: string) {
    fetchMessageDetail(messageId)
      .then((data) => {
        const label = accountLabels.get(data.connected_account_id) ?? ''
        setDetail(toDetailBody(data, label))
      })
      .catch((error) => console.error('메시지 상세 로드 실패', error))
  }

  return (
    <>
      <div className="app">
        <Sidebar />
        <Topbar />
        <ArchiveView onSelectMessage={handleSelectMessage} />
        <DetailPane detail={detail ?? storageDetail} onMarkRead={showToast} />
      </div>
      <Toast show={toastShown} onUndo={hideToast} onClose={hideToast} />
    </>
  )
}

export default ArchivePage
