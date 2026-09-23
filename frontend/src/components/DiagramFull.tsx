/** UI-002 1.7 그림 전체보기 — 유저용 본문 안 그림(mermaid 렌더 결과 · UC 패키지 그림 · SEQ 시퀀스)마다
 *  「전체보기」를 붙이고, 누르면 UI-8 전체보기와 같은 층(--z-graph-full)에 화면 전체로 띄운다.
 *  UI-5는 7.5(버튼)·7.6(층)이고 UI-9는 번호가 없다 — 번호는 부르는 쪽이 붙인다.
 *  그림은 원본 SVG를 **복제**한다. 옮기면 닫을 때 제자리에 돌려놔야 하고 mermaid가 붙인 id가 겹친다. */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { SANDBOX } from '../view/frame'
import { useEscape } from './ui'

export type FullDiagram = { title: string; w: number; h: number } & ({ svg: string; srcdoc?: undefined } | { srcdoc: string; svg?: undefined })

/** 배치 iframe이 쏘는 이벤트(view/frame.ts wf:full)의 짐 — 같은 층에 같은 srcdoc을 띄운다 (카드 AC) */
export type WfFullDetail = { srcdoc: string; title: string; w: number; h: number }

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
      // 이름 — 문서 순서로 이 그림 **앞에** 있는 마지막 헤딩(항목 ID면 그것). 가장 가까운 조상의 첫 헤딩을
      // 쓰면 SEQ에서 「생명선 표」 제목이 잡힌다 — 앞선 형제의 제목이지 이 그림의 제목이 아니다
      let title = '그림'
      for (const h of root.querySelectorAll<HTMLElement>('h1, h2, h3, h4, [data-item] .iid')) {
        if (h.compareDocumentPosition(host) & Node.DOCUMENT_POSITION_FOLLOWING) title = h.textContent?.trim() || title
        else break
      }
      // 「흐름」 같은 소제목만으로는 어느 시퀀스인지 모른다 — 그 절의 h2를 앞에 붙인다
      const h2 = host.closest('details, section, .ms-card')?.querySelector('h2')
      // h2 안의 <span class=k>SEQ-1</span> 뒤에 띄어쓰기가 없어 붙어 나온다 — 자식 노드마다 끊어 잇는다
      const sec = h2 ? [...h2.childNodes].map((n) => n.textContent?.trim() ?? '').filter(Boolean).join(' ') : ''
      if (sec && sec !== title) title = `${sec} · ${title}`
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
  const stage = useRef<HTMLDivElement>(null)
  // 열릴 때는 무대 폭에 맞춘다(100% 이하) — 시퀀스 하나가 3천px이라 100%로 열면 가로 스크롤부터 만난다 (1.7)
  useEffect(() => {
    const s = stage.current
    if (s) setZ(Math.max(0.25, Math.min(1, Math.floor(((s.clientWidth - 48) / d.w) * 100) / 100))) // 여백 22×2 + 테두리. 내림 — 올리면 10px가 넘쳐 가로 스크롤이 생긴다
  }, [d])
  useEscape(onClose) // 1.7 — 다이얼로그와 같은 스택. 다이얼로그 위에서 열렸으면 이것이 먼저 닫힌다
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
      <div className="stage" ref={stage} onClick={(e) => e.target === e.currentTarget && onClose()}>
        {/* 그림은 SVG를 복제하고, 배치는 같은 srcdoc의 iframe을 scale한다 (카드 AC) */}
        {d.srcdoc !== undefined ? (
          <div className="pic frame" style={{ width: d.w * z, height: d.h * z }}>
            <iframe
              className="wffull-if"
              sandbox={SANDBOX}
              srcDoc={d.srcdoc}
              style={{ width: d.w, height: d.h, transform: `scale(${z})`, transformOrigin: '0 0' }}
            />
          </div>
        ) : (
          <div className="pic" style={{ width: d.w * z, height: d.h * z }} dangerouslySetInnerHTML={{ __html: d.svg }} />
        )}
      </div>
    </div>,
    document.body,
  )
}
