import SettingsView from '@/features/settings/components/SettingsView'
import Sidebar from '@/features/navigation/components/Sidebar'
import Topbar from '@/features/navigation/components/Topbar'

/** 09 설정 — 상세 패널 미노출 2열 레이아웃, ported from 09-settings.html. */
function SettingsPage() {
  return (
    <div className="app app-no-detail">
      <Sidebar />
      <Topbar />
      <SettingsView />
    </div>
  )
}

export default SettingsPage
