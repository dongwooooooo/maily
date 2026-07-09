const infoItems = [
  {
    label: '읽는 것',
    body: '메일 메타데이터와 요약에 필요한 최소 내용만 처리합니다. AI 요약은 설정에서 계정별로 끌 수 있습니다.',
  },
  {
    label: '바꾸는 것',
    body: '승인 전에는 Gmail을 변경하지 않습니다. 자동 정리는 활동 로그에 남고 언제든 되돌릴 수 있습니다.',
  },
  {
    label: '사용자 통제',
    body: '언제든 이 계정의 연결을 해제할 수 있습니다.',
  },
]

/** 02 첫 Gmail 적용 확인 — standalone screen (no app shell), ported from 02-first-application.html. */
function FirstApplicationScreen() {
  return (
    <main className="apply-stage">
      <div className="apply-card">
        <span className="apply-mark" aria-hidden="true">
          M
        </span>

        <span className="apply-account">
          <span className="apply-dot" aria-hidden="true" />
          jiwon@company.com
        </span>
        <h1 className="apply-title">이 계정에 메일 비서를 적용합니다</h1>
        <p className="apply-lede">이 계정의 중요한 메일을 선별해 브리핑과 리마인드를 준비합니다.</p>

        <div className="apply-info">
          {infoItems.map((item) => (
            <div className="apply-info-item" key={item.label}>
              <b>{item.label}</b>
              <p>{item.body}</p>
            </div>
          ))}
        </div>

        <button className="start-btn" type="button">
          적용 시작
        </button>
        <button className="later-link" type="button">
          나중에 설정에서 연결하기
        </button>
      </div>
    </main>
  )
}

export default FirstApplicationScreen
