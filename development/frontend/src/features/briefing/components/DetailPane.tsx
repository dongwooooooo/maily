'use client'

import { useEffect, useRef, useState } from 'react'
import { detail } from '@/features/briefing/data/briefing.mock'
import { addLabelCopy, labelGroups } from '@/features/archive/data/archive.mock'

interface DetailPaneProps {
  onMarkRead: () => void
}

type OverlayView = 'none' | 'menu' | 'move'

function BriefcaseIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M4 8h16v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8Z" />
      <path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

function PersonIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5 20c1.2-3.6 4-5.4 7-5.4S17.8 16.4 19 20" />
    </svg>
  )
}

function MoveIcon() {
  return (
    <svg className="mi" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path>
      <path d="M9 16l3-3-3-3"></path>
    </svg>
  )
}

function ArchiveIcon() {
  return (
    <svg className="mi" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2" y="3" width="20" height="5" rx="1"></rect>
      <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"></path>
      <path d="M10 12h4"></path>
    </svg>
  )
}

/** Right pane: detail header (account + primary actions), summary tint box, serif original body. */
function DetailPane({ onMarkRead }: DetailPaneProps) {
  const [overlayView, setOverlayView] = useState<OverlayView>('none')
  const [selectedLabel, setSelectedLabel] = useState(labelGroups[0]?.heading ?? '')
  const [ruleBannerShown, setRuleBannerShown] = useState(false)
  const actionsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (overlayView === 'none') return

    function handlePointerDown(event: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(event.target as Node)) {
        setOverlayView('none')
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOverlayView('none')
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [overlayView])

  function toggleMenu() {
    setOverlayView((view) => (view === 'none' ? 'menu' : 'none'))
  }

  function confirmMoveOnce() {
    setOverlayView('none')
  }

  function confirmMoveAlways() {
    setOverlayView('none')
    setRuleBannerShown(true)
  }

  return (
    <aside className="detail-pane" aria-label="선택한 메일">
      <header className="detail-head">
        <div className="detail-account">
          <span className="avatar icon" aria-hidden="true">
            {detail.accountKind === 'school' ? <PersonIcon /> : <BriefcaseIcon />}
          </span>
          <span>{detail.account}</span>
        </div>

        <div className="message-header">
          <div className="message-title-row">
            <h2 className="detail-title">{detail.title}</h2>
            <div className="detail-actions-top" aria-label="주요 처리" ref={actionsRef}>
              <button className="icon-action" type="button" aria-label="Gmail에서 열기">
                <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 19 19 5"></path>
                  <path d="M11 5h8v8"></path>
                </svg>
              </button>
              <button
                className="icon-action"
                type="button"
                onClick={onMarkRead}
                aria-label="Gmail도 읽음 처리"
              >
                <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m5 12 4 4L19 6"></path>
                </svg>
              </button>
              <button
                className="more-action"
                type="button"
                aria-label="이동 및 아카이브 더보기"
                aria-expanded={overlayView !== 'none'}
                title="이동 또는 읽음 처리 후 아카이브 중 선택"
                onClick={toggleMenu}
              >
                <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="5" cy="12" r="1.4"></circle>
                  <circle cx="12" cy="12" r="1.4"></circle>
                  <circle cx="19" cy="12" r="1.4"></circle>
                </svg>
              </button>

              <div
                className="action-menu"
                data-open={overlayView === 'menu' ? 'true' : 'false'}
                role="menu"
                aria-label="추가 처리"
              >
                <button
                  className="menu-row"
                  type="button"
                  role="menuitem"
                  onClick={() => setOverlayView('move')}
                >
                  <MoveIcon />
                  이동
                </button>
                <button className="menu-row" type="button" role="menuitem">
                  <ArchiveIcon />
                  읽음 처리 후 아카이브
                </button>
              </div>

              <div
                className="move-popover"
                data-open={overlayView === 'move' ? 'true' : 'false'}
                role="dialog"
                aria-label="브리핑 이동"
              >
                <div className="move-label">이동할 라벨</div>
                {labelGroups.map((group) => (
                  <button
                    key={group.id}
                    className="move-row"
                    type="button"
                    role="radio"
                    aria-checked={selectedLabel === group.heading}
                    onClick={() => setSelectedLabel(group.heading)}
                  >
                    <span>{group.heading}</span>
                  </button>
                ))}
                <button
                  className="move-row"
                  type="button"
                  role="radio"
                  aria-checked={false}
                  onClick={() => setSelectedLabel(addLabelCopy)}
                >
                  <span>{addLabelCopy}</span>
                </button>
                <div className="move-foot">
                  <button className="btn-t3" type="button" onClick={confirmMoveAlways}>
                    다음부터도 여기로
                  </button>
                  <button className="btn-t2" type="button" onClick={confirmMoveOnce}>
                    이동
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="detail-meta">{detail.fromLine}</div>
        </div>
      </header>

      <section className="detail-body" aria-label="선택한 메일 내용">
        <div
          className="banner banner--info"
          data-show={ruleBannerShown ? 'true' : 'false'}
          role="status"
          aria-live="polite"
        >
          <span className="banner-text">
            앞으로 현대카드의 결제 알림은 <b>{selectedLabel}</b>에 표시합니다.
          </span>
          <button className="banner-action" type="button" onClick={() => setRuleBannerShown(false)}>
            되돌리기
          </button>
        </div>

        <div className="summary-quote">
          <span className="q-label">요약</span>
          <p>{detail.summary}</p>
        </div>

        <div className="mail-body-copy">
          {detail.paragraphs.map((para) => (
            <p key={para}>{para}</p>
          ))}
        </div>
      </section>
    </aside>
  )
}

export default DetailPane
