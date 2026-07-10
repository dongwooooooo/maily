'use client'

import { useCallback, useRef } from 'react'
import Script from 'next/script'

import { useGoogleLogin, GIS_SCRIPT_SRC } from '../useGoogleLogin'

/** 01 로그인 — standalone entry screen (no app shell), ported from 01-login.html.
 *
 * 로그인 버튼은 GIS 공식 renderButton — 목업의 자체 버튼과 시각이 다르다
 * (커스텀 버튼으로는 id_token 획득 불가, useGoogleLogin.ts 참조). */
function LoginScreen() {
  const buttonContainerRef = useRef<HTMLDivElement>(null)
  const { renderGoogleButton, error } = useGoogleLogin()

  const handleGisReady = useCallback(() => {
    if (buttonContainerRef.current) {
      renderGoogleButton(buttonContainerRef.current)
    }
  }, [renderGoogleButton])

  return (
    <main className="login-stage">
      <Script src={GIS_SCRIPT_SRC} strategy="afterInteractive" onReady={handleGisReady} />
      <div className="login-card">
        <span className="login-mark" aria-hidden="true">
          M
        </span>
        <h1 className="login-title">Maily</h1>
        <p className="login-tagline">여러 Gmail 계정의 중요한 메일을 선별해 브리핑합니다.</p>

        <div ref={buttonContainerRef} className="google-btn-slot" />
        {error ? (
          <p className="login-error" role="alert">
            [미확정: 로그인 실패 안내 문구]
          </p>
        ) : null}

        <p className="login-note">원문 확인·답장·발송은 계속 Gmail에서 합니다.</p>
      </div>
    </main>
  )
}

export default LoginScreen
