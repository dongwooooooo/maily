'use client'

import { useState } from 'react'
import {
  connectedAccounts,
  notificationPermission,
  reconnectBannerCopy,
  serviceAccount,
  type AccountToggle,
  type ConnectedAccount,
} from '@/features/settings/data/settings.mock'

function accDotClassName(kind: ConnectedAccount['accountKind']) {
  return kind === 'personal' ? 'acc-dot' : `acc-dot ${kind}`
}

function AccountToggleRow({ toggle }: { toggle: AccountToggle }) {
  const [checked, setChecked] = useState(toggle.checked)

  return (
    <div className="tg-row">
      <span className="tg-label">
        <b>{toggle.label}</b>
        <span>{toggle.hint}</span>
      </span>
      <span className="toggle">
        <input
          type="checkbox"
          checked={checked}
          aria-label={toggle.label}
          onChange={() => setChecked((value) => !value)}
        />
        <span className="track" aria-hidden="true" />
        <span className="knob" aria-hidden="true" />
      </span>
    </div>
  )
}

function AccountCard({ account }: { account: ConnectedAccount }) {
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
        <button className={`btn-${account.headActionVariant}`} type="button">
          {account.headAction}
        </button>
      </div>
      <div className="acct-toggles">
        {account.toggles.map((toggle) => (
          <AccountToggleRow key={toggle.key} toggle={toggle} />
        ))}
      </div>
      <div className="acct-foot">
        <button className="btn-t3 danger" type="button">
          연결 해제
        </button>
      </div>
    </article>
  )
}

/** 09 설정 — 서비스 계정 · 연결 메일 계정, ported from 09-settings.html. */
function SettingsView() {
  const needsReconnect = connectedAccounts.some((account) => account.syncKind === 'warn')

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
          <button className="banner-action" type="button">
            다시 연결
          </button>
        </div>

        <section className="set-section" aria-label="서비스 계정">
          <div className="set-info">
            <h2>서비스 계정</h2>
          </div>
          <div className="set-body">
            <div className="svc-row">
              <span className="svc-avatar" aria-hidden="true" />
              <span className="svc-main">
                <span className="svc-name">{serviceAccount.name}</span>
                <span className="svc-mail">{serviceAccount.authLine}</span>
              </span>
              <button className="btn-t3" type="button">
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
            {connectedAccounts.map((account) => (
              <AccountCard key={account.id} account={account} />
            ))}
            <div>
              <button className="btn-t2" type="button">
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
