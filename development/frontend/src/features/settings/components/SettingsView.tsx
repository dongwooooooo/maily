'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import {
  notificationPermission,
  reconnectBannerCopy,
  type AccountToggle,
  type ConnectedAccount,
} from '@/features/settings/data/settings.mock'
import {
  disconnectSource,
  fetchSessionSummary,
  fetchSourceSettings,
  updateSourceSettings,
} from '@/features/settings/api'
import { TOGGLE_FIELDS, toConnectedAccount, toServiceAccount, type ToggleKey } from '@/features/settings/adapters'
import { fetchSources } from '@/shared/api/sources'
import { useSessionStore } from '@/features/auth/store'
import type { ApiError } from '@/shared/api/errors'
import { errorMessageFor } from '@/shared/api/errorMessages'

function accDotClassName(kind: ConnectedAccount['accountKind']) {
  return kind === 'personal' ? 'acc-dot' : `acc-dot ${kind}`
}

interface AccountToggleRowProps {
  toggle: AccountToggle
  onChange: (key: ToggleKey, checked: boolean) => void
}

function AccountToggleRow({ toggle, onChange }: AccountToggleRowProps) {
  return (
    <div className="tg-row">
      <span className="tg-label">
        <b>{toggle.label}</b>
        <span>{toggle.hint}</span>
      </span>
      <span className="toggle">
        <input
          type="checkbox"
          checked={toggle.checked}
          aria-label={toggle.label}
          onChange={(event) => onChange(toggle.key as ToggleKey, event.target.checked)}
        />
        <span className="track" aria-hidden="true" />
        <span className="knob" aria-hidden="true" />
      </span>
    </div>
  )
}

interface AccountCardProps {
  account: ConnectedAccount
  onToggle: (accountId: string, key: ToggleKey, checked: boolean) => void
  onDisconnect: (accountId: string) => void
}

function AccountCard({ account, onToggle, onDisconnect }: AccountCardProps) {
  // 연결 해제는 자격증명 폐기 + 데이터 삭제로 이어지는 비가역 액션 —
  // 반드시 2단계 확인을 거친다(1클릭 즉시 DELETE 금지, 코드리뷰 Critical).
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false)

  return (
    <article className="acct-card">
      <div className="acct-head">
        <span className={accDotClassName(account.accountKind)} aria-hidden="true" />
        <span className="acct-main">
          <span className="acct-name">{account.name}</span>
          <span className="acct-mail">{account.mail}</span>
        </span>
        <span className="acct-state">
          {account.syncKind === 'ok' && <span className="ok">✓</span>}
          {account.syncKind === 'warn' && <span className="warn-dot" aria-hidden="true" />}
          {account.syncLabel}
        </span>
        {/* 다시 연결(OAuth 재동의)·이름 변경 UI는 미배선 — 후속 작업. */}
        <button className={`btn-${account.headActionVariant}`} type="button" disabled>
          {account.headAction}
        </button>
      </div>
      <div className="acct-toggles">
        {account.toggles.map((toggle) => (
          <AccountToggleRow
            key={toggle.key}
            toggle={toggle}
            onChange={(key, checked) => onToggle(account.id, key, checked)}
          />
        ))}
      </div>
      <div className="acct-foot">
        {confirmingDisconnect ? (
          <>
            <span className="acct-confirm-text">[미확정: 연결 해제 확인 문구]</span>
            <button
              className="btn-t3 danger"
              type="button"
              onClick={() => onDisconnect(account.id)}
            >
              해제 확정
            </button>
            <button
              className="btn-t3"
              type="button"
              onClick={() => setConfirmingDisconnect(false)}
            >
              취소
            </button>
          </>
        ) : (
          <button
            className="btn-t3 danger"
            type="button"
            onClick={() => setConfirmingDisconnect(true)}
          >
            연결 해제
          </button>
        )}
      </div>
    </article>
  )
}

/** 09 설정 — 서비스 계정 · 연결 메일 계정, ported from 09-settings.html. */
function SettingsView() {
  const router = useRouter()
  const clearSession = useSessionStore((state) => state.clearSession)
  const [accounts, setAccounts] = useState<ConnectedAccount[] | null>(null)
  const [serviceAccount, setServiceAccount] = useState<{ name: string; authLine: string } | null>(
    null,
  )
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchSessionSummary(),
      fetchSources().then((sources) =>
        Promise.all(
          sources
            .filter((source) => !['disconnecting', 'disconnected'].includes(source.status))
            .map((source) => fetchSourceSettings(source.id)),
        ),
      ),
    ])
      .then(([session, settingsList]) => {
        if (cancelled) return
        setServiceAccount(toServiceAccount(session))
        setAccounts(settingsList.map(toConnectedAccount))
      })
      .catch((error: ApiError) => {
        if (!cancelled) setLoadError(error)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function applyToggle(accountId: string, key: ToggleKey, checked: boolean) {
    setAccounts(
      (current) =>
        current?.map((account) =>
          account.id === accountId
            ? {
                ...account,
                toggles: account.toggles.map((toggle) =>
                  toggle.key === key ? { ...toggle, checked } : toggle,
                ),
              }
            : account,
        ) ?? null,
    )
  }

  function handleToggle(accountId: string, key: ToggleKey, checked: boolean) {
    // 낙관 업데이트. 실패 시 이전 값으로 무조건 되돌리면 연속 클릭에서
    // 나중에 성공한 요청의 상태를 덮어쓸 수 있어(경쟁 조건, 코드리뷰 Major)
    // 서버 재조회로 진실 소스를 복원한다.
    applyToggle(accountId, key, checked)
    updateSourceSettings(accountId, { [TOGGLE_FIELDS[key]]: checked })
      .then(() => setActionError(null))
      .catch(async (error: ApiError) => {
        console.error('설정 변경 실패', error)
        setActionError(error)
        try {
          const fresh = await fetchSourceSettings(accountId)
          setAccounts(
            (current) =>
              current?.map((account) =>
                account.id === accountId ? toConnectedAccount(fresh) : account,
              ) ?? null,
          )
        } catch {
          // 재조회도 실패 — 화면 상태는 그대로 두고 에러 안내만 남긴다.
        }
      })
  }

  function handleDisconnect(accountId: string) {
    disconnectSource(accountId)
      .then(() => {
        setActionError(null)
        setAccounts((current) => current?.filter((account) => account.id !== accountId) ?? null)
      })
      .catch((error: ApiError) => {
        console.error('연결 해제 실패', error)
        setActionError(error)
      })
  }

  function handleLogout() {
    clearSession()
    router.replace('/login')
  }

  const needsReconnect = (accounts ?? []).some((account) => account.syncKind === 'warn')

  return (
    <main className="list-pane" id="settings" aria-label="설정">
      <div className="settings-wrap">
        <div
          className="banner banner--warning"
          data-show={needsReconnect ? 'true' : 'false'}
          role="status"
          aria-live="polite"
        >
          <span className="banner-text">
            <span className="banner-dot" aria-hidden="true" />
            {reconnectBannerCopy}
          </span>
          {/* OAuth 재동의 흐름 미배선 — 후속 작업. */}
          <button className="banner-action" type="button" disabled>
            다시 연결
          </button>
        </div>

        {(loadError || actionError) && (
          <p className="list-error" role="alert">
            {errorMessageFor((loadError ?? actionError)!)}
          </p>
        )}

        <section className="set-section" aria-label="서비스 계정">
          <div className="set-info">
            <h2>서비스 계정</h2>
          </div>
          <div className="set-body">
            <div className="svc-row">
              <span className="svc-avatar" aria-hidden="true" />
              <span className="svc-main">
                <span className="svc-name">{serviceAccount?.name ?? ''}</span>
                <span className="svc-mail">{serviceAccount?.authLine ?? ''}</span>
              </span>
              <button className="btn-t3" type="button" onClick={handleLogout}>
                로그아웃
              </button>
            </div>
          </div>
        </section>

        <section className="set-section" aria-label="연결된 메일 계정">
          <div className="set-info">
            <h2>연결된 메일 계정</h2>
            <p className="hint">
              연결된 Gmail 계정은 브리핑·분석·알림의 메일 소스입니다. 서비스 로그인 계정과는 별개입니다.
            </p>
          </div>
          <div className="set-body">
            {accounts?.map((account) => (
              <AccountCard
                key={account.id}
                account={account}
                onToggle={handleToggle}
                onDisconnect={handleDisconnect}
              />
            ))}
            <div>
              {/* 신규 계정 연결(OAuth 동의 → POST /sources)은 Task14 라이브 경로에서 배선. */}
              <button className="btn-t2" type="button" disabled>
                + 메일 계정 연결
              </button>
            </div>
          </div>
        </section>

        <section className="set-section" aria-label="알림">
          <div className="set-info">
            <h2>알림</h2>
          </div>
          <div className="set-body">
            <div className="svc-row">
              <span className="svc-main">
                <span className="svc-name">{notificationPermission.title}</span>
                <span className="svc-mail">{notificationPermission.hint}</span>
              </span>
              <button className="btn-t3" type="button">
                {notificationPermission.actionLabel}
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}

export default SettingsView
