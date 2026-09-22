/** 배치 html의 iframe(srcdoc) 격리 — STD-002 V-UI·1장(카드 Z). tools/wf_build.py frame_html·FRAME_CSS·WF_JS 포트.
 *  문서가 넣은 html은 페이지 DOM이 아니라 **자기 문서**(srcdoc) 안에서 그려진다 — 사이트 CSS가 한 줄도 안 스며들고,
 *  문서의 <style>·<link>·인라인 스타일이 그대로 산다. sandbox는 allow-same-origin 하나 — 스크립트는 못 돌고(그림이지 동작이 아니다),
 *  같은 출처라 세션 쿠키로 `/api/projects/{code}/files/…` 이미지가 뜨고 부모가 contentDocument를 직접 만진다.
 *  높이·축소(scale)·클릭·강조는 전부 **부모** 스크립트가 한다. iframe 안에는 뷰도 스크립트를 넣지 않는다.
 *  FRAME_CSS·SANDBOX는 wf_build.py와 바이트 단위로 같아야 한다(check_view_css 둘째 쌍). */

export const SANDBOX = 'allow-same-origin'

export const FRAME_CSS = `html,body{margin:0}
[data-el]{position:relative}
[data-el]::before{content:attr(data-el);position:absolute;top:-8px;left:5px;font:600 9.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;background:#ffe58a;border:1px solid #c9a800;color:#222;padding:2px 4px;border-radius:2px;z-index:2147483000;pointer-events:none}
[data-el].hi{outline:2px solid #c9a800;outline-offset:1px}
a{cursor:default}`

export interface CommonParts {
  /** <link …>·<style>…</style> — srcdoc <head>로 */
  head: string
  /** 나머지 마크업 — srcdoc <body> 맨 앞으로 */
  body: string
}
export const NO_COMMON: CommonParts = { head: '', body: '' }

/** 배치 HTML을 넣기 전에 다듬는다 — SYNC-STD-002 1장(#19).
 *  <script>·on*=·javascript:·<iframe|object|embed|form>·<meta http-equiv>는 지운다. 나머지 태그·속성은 그대로 —
 *  와이어프레임은 자기 완결 html이라 <style>·<link>·인라인 style이 필요하다. data-el은 그대로 둔다(iframe이라 부모와 안 섞인다) */
export function safeLayout(html: string): string {
  return html
    .replace(/<script\b[\s\S]*?<\/script\s*>/gi, '')
    .replace(/<(iframe|object|embed|form)\b[\s\S]*?<\/\1\s*>/gi, '')
    .replace(/<\/?(iframe|object|embed|form)\b[^>]*>/gi, '')
    .replace(/<meta\b[^>]*http-equiv[^>]*>/gi, '')
    .replace(/\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/\s(href|src)\s*=\s*(["']?)\s*javascript:[^"'>]*\2/gi, '')
}

/** 공통 틀 블록 → head(<link>·<style>) / body(나머지) */
export function splitCommon(html: string): CommonParts {
  const head: string[] = []
  const body = html
    .replace(/<style\b[\s\S]*?<\/style\s*>/gi, (m) => {
      head.push(m)
      return ''
    })
    .replace(/<link\b[^>]*>/gi, (m) => {
      head.push(m)
      return ''
    })
  return { head: head.join('\n'), body: body.trim() }
}

/** 코드 펜스 안 줄을 같은 길이의 공백으로(길이·줄 수 유지 — index가 원문 index다) */
function maskFences(text: string): string {
  let inFence = false
  return text
    .split('\n')
    .map((l) => {
      if (/^\s*```/.test(l)) {
        inFence = !inFence
        return ' '.repeat(l.length)
      }
      return inFence ? ' '.repeat(l.length) : l
    })
    .join('\n')
}

/** 「공통 틀」 절(번호 접두 허용, 단계 무관)의 첫 ```html 블록. 없으면 ''.
 *  절은 그 헤딩부터 같은 단계 이상의 다음 헤딩 전까지 */
export function commonBlock(body: string): string {
  const masked = maskFences(body)
  const m = /^(#{1,6}) (?:\d+(?:\.\d+)*\.?\s+)?공통 틀\s*$/m.exec(masked)
  if (!m) return ''
  const lvl = m[1].length
  const from = m.index + m[0].length
  const rest = masked.slice(from)
  const re = /^(#{1,6}) /gm
  let end: number | undefined
  let h: RegExpExecArray | null
  while ((h = re.exec(rest))) {
    if (h[1].length <= lvl) {
      end = from + h.index
      break
    }
  }
  const sec = body.slice(from, end)
  const b = /```html\n([\s\S]*?)\n```/.exec(sec)
  return b ? safeLayout(b[1]) : ''
}

/** 공통 틀이 스타일·링크뿐인가(마크업 없음) — 산문 자리에서 빈 iframe 대신 코드로 보이려고 */
export function isStyleOnly(html: string): boolean {
  return splitCommon(html).body === ''
}

const attr = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;')

/** srcdoc 문서 한 벌. wf_build.frame_html과 같은 구조 */
export function frameDoc(layout: string, common: CommonParts, base: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><base href="${attr(base)}">${common.head}<style>${FRAME_CSS}</style></head><body>${common.body}${layout}</body></html>`
}

/** iframe 하나 = 배치 하나. .wfframe이 감싸고 부모(mountFrames)가 높이·축소를 잡는다 */
export function frameHtml(layout: string, common: CommonParts, base: string): string {
  return `<div class="wfframe"><iframe class="wfframe-if" sandbox="${SANDBOX}" srcdoc="${attr(frameDoc(layout, common, base))}"></iframe></div>`
}

// ───────────────────────── 동작 (부모 쪽) ─────────────────────────

interface FrameState {
  scale: number
  fit: boolean
  natW: number
  natH: number
  measure: () => void
  cleanup: () => void
}
const STATE = new WeakMap<HTMLIFrameElement, FrameState>()

/** 배치 안 요소 강조 — 이 iframe의 [data-el] 중 no만 .hi */
export function hiIn(frame: HTMLIFrameElement, no: string): HTMLElement | null {
  const doc = frame.contentDocument
  if (!doc) return null
  doc.querySelectorAll('[data-el].hi').forEach((n) => n.classList.remove('hi'))
  const el = doc.querySelector<HTMLElement>(`[data-el="${no.replace(/["\\]/g, '\\$&')}"]`)
  if (!el) return null
  el.classList.add('hi')
  // iframe 자체는 내용만큼 커서 스크롤이 없다 — 감싸는 .left(overflow:auto)를 요소 위치(축소 비율 반영)로 옮긴다
  const st = STATE.get(frame)
  const k = st?.scale ?? 1
  const box = frame.parentElement?.closest<HTMLElement>('.left, .wfbox')
  if (box) {
    const y = el.getBoundingClientRect().top * k + (frame.parentElement?.offsetTop ?? 0)
    if (y < box.scrollTop || y > box.scrollTop + box.clientHeight - 40) box.scrollTop = Math.max(0, y - 24)
  }
  return el
}

/** 같은 iframe을 두 번 재지 않게 — 탭 전환 뒤 다시 재려고 */
export function remeasure(root: HTMLElement): void {
  for (const f of root.querySelectorAll<HTMLIFrameElement>('iframe.wfframe-if')) STATE.get(f)?.measure()
}

function setup(f: HTMLIFrameElement, onPick?: (no: string, frame: HTMLIFrameElement) => void): void {
  const doc = f.contentDocument
  const wrap = f.parentElement
  if (!doc || !doc.body || !wrap) return
  if (STATE.has(f)) STATE.get(f)?.cleanup()
  const st: FrameState = { scale: 1, fit: true, natW: 0, natH: 0, measure: () => undefined, cleanup: () => undefined }
  let lastH = -1
  let btn: HTMLButtonElement | null = null

  const apply = () => {
    const avail = wrap.clientWidth
    const wide = st.natW > avail + 1 && avail > 0
    if (wide && st.fit) {
      st.scale = avail / st.natW
      f.style.width = `${st.natW}px`
      f.style.transform = `scale(${st.scale})`
      f.style.transformOrigin = '0 0'
      f.style.height = `${st.natH}px`
      wrap.style.height = `${Math.ceil(st.natH * st.scale)}px`
      wrap.classList.add('scaled')
    } else {
      st.scale = 1
      f.style.width = wide ? `${st.natW}px` : ''
      f.style.transform = ''
      f.style.height = `${st.natH}px`
      wrap.style.height = ''
      wrap.classList.remove('scaled')
    }
    // 「원래 크기」 토글은 넓을 때만
    if (wide && !btn) {
      btn = document.createElement('button')
      btn.type = 'button'
      btn.className = 'wfframe-fit btn sm'
      btn.addEventListener('click', () => {
        st.fit = !st.fit
        apply()
      })
      wrap.appendChild(btn)
    }
    if (btn) {
      btn.textContent = st.fit ? '원래 크기' : '맞춤'
      btn.style.display = wide ? '' : 'none'
    }
  }

  st.measure = () => {
    const de = doc.documentElement
    const b = doc.body
    if (!de || !b) return
    const first = b.firstElementChild
    const fb = first ? first.getBoundingClientRect() : null
    // html,body{height:100%} 같은 문서는 scrollHeight가 iframe 높이에 묶여 순환한다 — 첫 자식의 바닥과 견줘 큰 값, 같으면 갱신 안 함
    const h = Math.ceil(Math.max(de.scrollHeight, b.scrollHeight, fb ? fb.bottom + (doc.defaultView?.scrollY ?? 0) : 0))
    const w = Math.ceil(Math.max(de.scrollWidth, b.scrollWidth, fb ? fb.right : 0))
    if (h <= 0 && w <= 0) return
    if (h === lastH && w === st.natW) return
    lastH = h
    st.natH = h
    st.natW = w
    apply()
  }

  const onClick = (e: Event) => {
    // iframe 문서의 노드는 다른 realm이라 instanceof Element가 거짓이다 (#122)
    const t = e.target as Element | null
    if (!t || t.nodeType !== 1 || typeof t.closest !== 'function') return
    // <base>가 있어 #x도 밖으로 나간다 — 배치 안 링크는 누를 것이 아니다
    if (t.closest('a[href]')) e.preventDefault()
    const el = t.closest<HTMLElement>('[data-el]')
    if (el) {
      const no = el.dataset.el ?? ''
      hiIn(f, no)
      onPick?.(no, f)
    }
  }
  doc.addEventListener('click', onClick)

  const ro = new ResizeObserver(() => st.measure())
  ro.observe(doc.documentElement)
  ro.observe(doc.body)
  const wro = new ResizeObserver(() => apply())
  wro.observe(wrap)

  st.cleanup = () => {
    ro.disconnect()
    wro.disconnect()
    doc.removeEventListener('click', onClick)
    STATE.delete(f)
  }
  STATE.set(f, st)
  st.measure()
}

/** root 안 모든 .wfframe-if를 산다. 이미 산 것은 건너뛴다(타입별 onMount가 먼저 불렀을 수 있다).
 *  load 뒤에 붙는다 — srcdoc은 innerHTML 삽입 뒤 비동기로 로드된다 */
export function mountFrames(root: HTMLElement, onPick?: (no: string, frame: HTMLIFrameElement) => void): () => void {
  const frames = Array.from(root.querySelectorAll<HTMLIFrameElement>('iframe.wfframe-if')).filter((f) => !STATE.has(f) && !f.dataset.mounted)
  const offs: (() => void)[] = []
  for (const f of frames) {
    f.dataset.mounted = '1'
    const onLoad = () => setup(f, onPick)
    f.addEventListener('load', onLoad)
    // 이미 로드돼 있으면(같은 문서를 다시 그릴 때) 바로
    const d = f.contentDocument
    if (d && d.readyState === 'complete' && d.body && d.body.childNodes.length) setup(f, onPick)
    offs.push(() => {
      f.removeEventListener('load', onLoad)
      STATE.get(f)?.cleanup()
      delete f.dataset.mounted
    })
  }
  return () => offs.forEach((o) => o())
}
