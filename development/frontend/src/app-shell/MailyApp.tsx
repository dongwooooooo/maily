'use client'

import { useState } from 'react'
import MailList from '@/features/briefing/components/MailList'
import DetailPane from '@/features/briefing/components/DetailPane'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'
import Toast from '@/shared/ui/Toast'
import { useAutoHideToast } from '@/shared/hooks/useAutoHideToast'
import { hasUrgentItems } from '@/features/briefing/data/briefing.mock'

/** 03 keystone "오늘 브리핑" — editorial 3-pane layout with Undo toast. */
function MailyApp() {
  const [selectedId, setSelectedId] = useState('pr-review')
  const { shown: toastShown, show: showToast, hide: hideToast } = useAutoHideToast()

  return (
    <>
      <a className="skip-link" href="#today-briefing">
        오늘 브리핑 목록으로 이동
      </a>
      <div className={`app${hasUrgentItems ? '' : ' app-no-detail'}`}>
        <Sidebar />
        <Topbar />
        <MailList selectedId={selectedId} onSelect={setSelectedId} />
        {hasUrgentItems && <DetailPane onMarkRead={showToast} />}
      </div>
      <Toast show={toastShown} onUndo={hideToast} onClose={hideToast} />
    </>
  )
}

export default MailyApp
