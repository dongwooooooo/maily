function GoogleIcon() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.7 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.2C12.4 13.4 17.7 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6c4.5-4.2 6.9-10.4 6.9-17.7z"
      />
      <path
        fill="#FBBC05"
        d="M10.5 28.6c-.5-1.5-.8-3-.8-4.6s.3-3.1.8-4.6l-7.9-6.2C.9 16.5 0 20.1 0 24s.9 7.5 2.6 10.8l7.9-6.2z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.2 0 11.4-2 15.2-5.6l-7.7-6c-2.1 1.4-4.7 2.3-7.5 2.3-6.3 0-11.6-3.9-13.5-9.3l-7.9 6.2C6.5 42.6 14.6 48 24 48z"
      />
    </svg>
  )
}

/** 01 로그인 — standalone entry screen (no app shell), ported from 01-login.html. */
function LoginScreen() {
  return (
    <main className="login-stage">
      <div className="login-card">
        <span className="login-mark" aria-hidden="true">
          M
        </span>
        <h1 className="login-title">Maily</h1>
        <p className="login-tagline">여러 Gmail 계정의 중요한 메일을 선별해 브리핑합니다.</p>

        <button className="google-btn" type="button">
          <GoogleIcon />
          Google로 로그인하기
        </button>

        <p className="login-note">원문 확인·답장·발송은 계속 Gmail에서 합니다.</p>
      </div>
    </main>
  )
}

export default LoginScreen
