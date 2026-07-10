'use client'

import ArchiveView from '@/features/archive/components/ArchiveView'
import DetailPane from '@/features/briefing/components/DetailPane'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'
import Toast from '@/shared/ui/Toast'
import { useAutoHideToast } from '@/shared/hooks/useAutoHideToast'
import { storageDetail } from '@/features/archive/data/archive.mock'

/** 07 storage "보관함" — editorial 3-pane layout, ported from 07-storage.html. */
function ArchivePage() {
  const { shown: toastShown, show: showToast, hide: hideToast } = useAutoHideToast()

  return (
    <>
      <div className="app">
        <Sidebar />
        <Topbar />
        <ArchiveView />
        <DetailPane detail={storageDetail} onMarkRead={showToast} />
      </div>
      <Toast show={toastShown} onUndo={hideToast} onClose={hideToast} />
    </>
  )
}

export default ArchivePage
