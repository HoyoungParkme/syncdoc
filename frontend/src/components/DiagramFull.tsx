/** UI-002 1.7 그림 전체보기 — 유저용 본문 안 그림(mermaid 렌더 결과 · UC 패키지 그림 · SEQ 시퀀스)마다
 *  「전체보기」를 붙이고, 누르면 UI-8 전체보기와 같은 층(--z-graph-full)에 화면 전체로 띄운다.
 *  UI-5는 7.5(버튼)·7.6(층)이고 UI-9는 번호가 없다 — 번호는 부르는 쪽이 붙인다.
 *  그림은 원본 SVG를 **복제**한다. 옮기면 닫을 때 제자리에 돌려놔야 하고 mermaid가 붙인 id가 겹친다. */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

export type FullDiagram = { svg: string; title: string; w: number; h: number }

/** svg가 드는 상자들. 뷰 모듈이 만드는 클래스 이름 그대로(md.ts .mer · seq.ts .dia · uc.ts .canvas) */
const HOSTS = '.mer, .seqv .dia, .v-uc .canvas'

/** 본문 안 그림마다 버튼을 붙인다. mermaid.run이 끝난 뒤 불러야 svg가 있다. 이미 붙은 상자는 건너뛴다 */
export function attachDiagramButtons(root: HTMLElement, open: (d: FullDiagram) => void): HTMLButtonElement[] {
  const made: HTMLButtonElement[] = []
  for (const host of root.querySelectorAll<HTMLElement>(HOSTS)) {
    const svg = host.querySelector('svg')
    if (!svg || host.querySelector('.dfull-btn')) continue
    host.classList.add('dhost')
    const b = document.createElement('button')
    b.type = 'button'
    b.className = 'btn sm dfull-btn'
    b.textContent = '전체보기'
    b.addEventListener('click', (ev) => {
      ev.preventDefault()
      ev.stopPropagation()
      const vb = svg.viewBox?.baseVal
      const box = svg.getBoundingClientRect()
      const w = vb?.width || box.width || 800
      const h = vb?.height || box.height || 600
      // 이름 — 항목 안이면 항목 ID, 아니면 가장 가까운 소제목
      const title =
        host.closest('[data-item]')?.querySelector('.iid')?.textContent?.trim() ||
        host.closest('section, .ms-card, details, .seq-body')?.querySelector('h2, h3, h4')?.textContent?.trim() ||
        '그림'
      open({ svg: svg.outerHTML, title, w, h })
    })
    host.appendChild(b)
    made.push(b)
  }
  return made
}

const STEP = 0.25

export function DiagramFull({ d, onClose, el }: { d: FullDiagram; onClose: () => void; el?: string }) {
  const [z, setZ] = useState(1)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return createPortal(
    <div className="dfull" data-el={el}>
      <div className="gbar">
        <b>{d.title}</b>
        <span className="lbl">전체보기</span>
        <span className="grow" />
        <button className="btn sm" type="button" onClick={() => setZ((v) => Math.max(0.25, +(v - STEP).toFixed(2)))}>
          －
        </button>
        <span className="mono zv">{Math.round(z * 100)}%</span>
        <button className="btn sm" type="button" onClick={() => setZ((v) => Math.min(4, +(v + STEP).toFixed(2)))}>
          ＋
        </button>
        <button className="btn sm" type="button" onClick={() => setZ(1)}>
          100%
        </button>
        <span className="sep" />
        <button className="btn sm" type="button" onClick={onClose}>
          닫기
        </button>
      </div>
      {/* 바깥(빈 무대) 클릭은 닫는다. 그림 위 클릭은 아니다 */}
      <div className="stage" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="pic" style={{ width: d.w * z, height: d.h * z }} dangerouslySetInnerHTML={{ __html: d.svg }} />
      </div>
    </div>,
    document.body,
  )
}
