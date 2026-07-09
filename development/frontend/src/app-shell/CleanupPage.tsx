'use client'

import CleanupView from '@/features/cleanup/components/CleanupView'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'
import Toast from '@/shared/ui/Toast'
import { useAutoHideToast } from '@/shared/hooks/useAutoHideToast'
import { undoAppliedToastCopy } from '@/features/cleanup/data/cleanup.mock'

/** 10 정리 검토 — 상세 패널 미노출 2열 레이아웃, ported from 10-cleanup-review.html. */
function CleanupPage() {
  const { shown: toastShown, show: showToast, hide: hideToast } = useAutoHideToast()

  return (
    <>
      <div className="app app-no-detail">
        <Sidebar />
        <Topbar />
        <CleanupView onUndoApplied={showToast} />
      </div>
      <Toast show={toastShown} onClose={hideToast} message={undoAppliedToastCopy} />
    </>
  )
}

export default CleanupPage
