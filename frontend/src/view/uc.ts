/** tools/build.py + tools/parse.py 포트 — V-UC (STD-002 2장). view_build.py:v_uc()가 둘을 엮는 방식을 그대로 옮겼다.
 *  1 액터 식별(원본 1장 그대로) → 2 좌 액터별 목록 / 우 Cockburn 12행 표 + 기본 흐름 + 확장
 *  → 3 패키지 탭 + UML 유스케이스 다이어그램(SVG, 항목 표의 주 액터·포함·확장점·일반화에서 그림) → 4 대응표 둘.
 *  CSS는 build.py <style>을 `.v-uc` 아래로 스코프해 ucCss로 내보낸다. 페이지가 한 번만 넣는다. */
import { esc, renderBlocks, secName, splitSections, type RenderCtx } from './md'
import type { ViewFn } from './types'

// ───────────────────────── 데이터 (parse.py) ─────────────────────────
export type UcActor = 'agent' | 'human' | 'github' | 'system'

export interface UcExt {
  on: string
  steps: string[]
}

export interface Uc {
  id: string
  short: string
  name: string
  actor: UcActor
  scope: string
  level: string
  primary: string
  stakeholders: string
  pre: string
  minGuarantee: string
  successGuarantee: string
  trigger: string
  package: string
  include: string
  extPoint: string
  general: string
  flow: string[]
  ext: UcExt[]
  note: string
  links: string
}

export interface UcData {
  ucs: Uc[]
  scenarioMap: string[][]
  reqMap: string[][]
}

const ACTOR_OF: Record<string, UcActor> = { A: 'agent', H: 'human', G: 'github', S: 'system' }
const UC_ID = /UC-[AHGS]\d+/g
const UC_ID1 = /UC-[AHGS]\d+/

/** | 항목 | 내용 | 형식의 표를 dict로 */
function parseTable(block: string): Record<string, string> {
  const rows: Record<string, string> = {}
  for (const line of block.split('\n')) {
    const m = /^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$/.exec(line)
    if (!m) continue
    const k = m[1].trim()
    const v = m[2].trim()
    if (k === '항목' || k === '---' || /^[-: ]*$/.test(k)) continue
    rows[k] = v
  }
  return rows
}

/** 번호 매긴 기본 흐름 */
function parseFlow(block: string): string[] {
  return block
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^\d+\./.test(l))
    .map((l) => l.replace(/^\d+\.\s*/, '').trim())
}

/** 확장: - **2a. 제목** / - 2a1. 내용 */
function parseExt(block: string): UcExt[] {
  const items: UcExt[] = []
  let cur: UcExt | null = null
  for (const line of block.split('\n')) {
    const s = line.trim()
    const head = /^-\s*\*\*(.+?)\*\*\s*$/.exec(s)
    if (head) {
      cur = { on: head[1].trim(), steps: [] }
      items.push(cur)
      continue
    }
    const step = /^-\s*(\d+[a-z]\d+\.\s*.+)$/.exec(s)
    if (step && cur) cur.steps.push(step[1].replace(/^\d+[a-z]\d+\.\s*/, '').trim())
  }
  return items
}

/** `### 4.x …` 헤딩 다음 표(헤더·구분선 건너뜀)를 행 배열로 */
function grabTable(body: string, headingPrefix: string): string[][] {
  const re = new RegExp(`^### ${headingPrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[^\\n]*\\n`, 'm')
  const m = re.exec(body)
  if (!m) return []
  const lines = body.slice(m.index + m[0].length).trim().split('\n')
  const out: string[][] = []
  for (const l of lines.slice(2)) {
    if (!l.startsWith('|')) break
    out.push(
      l
        .replace(/^\||\|$/g, '')
        .split('|')
        .map((c) => c.trim()),
    )
  }
  return out
}

/** parse.py 포트. body는 frontmatter 없는 본문 */
export function parseUc(body: string): UcData {
  const ucs: Uc[] = []
  for (const ch of body.split('\n#### ').slice(1)) {
    const nl = ch.indexOf('\n')
    const head = (nl < 0 ? ch : ch.slice(0, nl)).trim()
    const m = /^(UC-([AHGS])\d+)\s+(.+)$/.exec(head)
    if (!m) continue
    const text = nl < 0 ? '' : ch.slice(nl + 1)

    const FLOW = '**기본 흐름**'
    const EXT = '**확장**'
    const hasFlow = text.includes(FLOW)
    const tbl = parseTable(text.split(FLOW)[0])
    const flowBlock = hasFlow ? text.split(FLOW)[1].split(EXT)[0] : ''
    const afterExt = text.includes(EXT) ? text.split(EXT)[1] : ''
    const extBlock = afterExt.split(/\n\*\*(?:사후조건 참고|연관)\*\*/)[0]
    const note = /\*\*사후조건 참고\*\*:\s*(.+)/.exec(text)?.[1].trim() ?? ''
    const links = /\*\*연관\*\*:\s*(.+)/.exec(text)?.[1].trim() ?? ''

    ucs.push({
      id: m[1],
      short: m[1].replace('UC-', ''),
      name: m[3],
      actor: ACTOR_OF[m[2]],
      scope: tbl['범위'] ?? '',
      level: tbl['수준'] ?? '',
      primary: tbl['주 액터'] ?? '',
      stakeholders: tbl['이해관계자와 관심사'] ?? '',
      pre: tbl['사전조건'] ?? '',
      minGuarantee: tbl['최소 보장'] ?? '',
      successGuarantee: tbl['성공 보장'] ?? '',
      trigger: tbl['트리거'] ?? '',
      package: tbl['패키지'] ?? '',
      include: tbl['포함(include)'] ?? '',
      extPoint: tbl['확장점(extension point)'] ?? '',
      general: tbl['일반화'] ?? '',
      flow: parseFlow(flowBlock),
      ext: parseExt(extBlock),
      note,
      links,
    })
  }
  return { ucs, scenarioMap: grabTable(body, '4.1'), reqMap: grabTable(body, '4.2') }
}

// ───────────────────────── 액터 상수 (build.py ACT) ─────────────────────────
interface ActorInfo {
  label: string
  sub: string
  hex: string
}
const ACT_DEFAULT: Record<UcActor, ActorInfo> = {
  agent: { label: '에이전트', sub: 'Claude Code · Codex · Gemini', hex: '#12776A' },
  human: { label: '사람', sub: '박호영 · 김민준', hex: '#3A5BA0' },
  github: { label: 'GitHub', sub: '코드 저장소', hex: '#6B4A9E' },
  system: { label: '하위기능', sub: '저장 후 자동 실행', hex: '#8A6D1F' },
}
const ACTOR_ORDER: UcActor[] = ['agent', 'human', 'github', 'system']

/** 1장 액터 표(| 액터 | 코드 | 설명 | 접근 경로 |)에서 이름을 읽어 기본값을 덮는다 */
function actorsFrom(actorSec: string): Record<UcActor, ActorInfo> {
  const act: Record<UcActor, ActorInfo> = {
    agent: { ...ACT_DEFAULT.agent },
    human: { ...ACT_DEFAULT.human },
    github: { ...ACT_DEFAULT.github },
    system: { ...ACT_DEFAULT.system },
  }
  for (const line of actorSec.split('\n')) {
    const m = /^\|\s*([^|]+?)\s*\|\s*([AHGS])\s*\|/.exec(line)
    if (m) act[ACTOR_OF[m[2]]].label = m[1]
  }
  return act
}

// ───────────────────────── 인라인 (build.py md · linkUC) ─────────────────────────
/** build.py md(): 이스케이프 후 `<br>` 복원, **강조**, `코드` */
const md = (s: string | null | undefined): string =>
  esc(s)
    .replace(/&lt;br&gt;/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')

const jump = (id: string) => `<span class="jump" data-jump="${id}">${id}</span>`

/** view_build.py가 바꿔 끼운 linkUC: [[#UC-xx]] → 문서 안 이동, [[DOC#ITEM]]·[[DOC]] → 참조 링크, 맨몸 UC-xx → 이동.
 *  한 번에 훑어 이미 만든 태그 안을 다시 감싸지 않는다. */
function linkUC(s: string | null | undefined, ctx: RenderCtx): string {
  return md(s).replace(
    /\[\[#(UC-[AHGS]\d+)\]\]|\[\[([A-Z]+-[A-Z]+-\d+)(?:#([^\]]+))?\]\]|(?<![\w#-])(UC-[AHGS]\d+)(?![\w"])/g,
    (_m, self: string | undefined, doc: string | undefined, item: string | undefined, bare: string | undefined) => {
      if (self) return jump(self)
      if (doc) {
        const ok = ctx.exists(doc, item || undefined)
        const label = item ? `${doc}#${item}` : doc
        return `<a class="${ok ? 'ref' : 'ref missing'}" href="${esc(ctx.href(doc, item || undefined))}" data-ref="${esc(label)}">${esc(label)}</a>`
      }
      return jump(bare ?? '')
    },
  )
}

// ───────────────────────── 뷰 ─────────────────────────
const LEGEND = `<div class="key">
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#5C6B73" stroke-width="1.2"/></svg>연결</span>
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="27" y2="5" stroke="#5C6B73" stroke-width="1.2" stroke-dasharray="6 4"/><path d="M27,1 L34,5 L27,9" fill="none" stroke="#5C6B73" stroke-width="1.2"/></svg>«include» / «extend»</span>
  <span><svg width="34" height="12"><line x1="0" y1="6" x2="24" y2="6" stroke="#5C6B73" stroke-width="1.2"/><path d="M24,1 L34,6 L24,11 Z" fill="#fff" stroke="#5C6B73" stroke-width="1.2"/></svg>일반화</span>
  <span><svg width="30" height="14"><ellipse cx="15" cy="7" rx="13" ry="6" fill="#F8F9F7" stroke="#5C6B73" stroke-width="1.4" stroke-dasharray="6 4"/></svg>추상·다른 패키지</span>
</div>`

export const vUc: ViewFn = ({ body, ctx }) => {
  const data = parseUc(body)
  const actorSec = splitSections(body).find(([t]) => secName(t).startsWith('액터'))?.[1] ?? ''
  const html = `<div class="v-uc">
<h2><span class="n">1</span>액터 식별</h2>
${renderBlocks(actorSec, ctx)}

<h2><span class="n">2</span>유스케이스 발견·명세</h2>
<p class="soft">왼쪽에서 고르면 오른쪽에 Cockburn 12행 표 + 기본 흐름 + 확장. 흐름 안 <span class="jump">UC-xx</span>를 누르면 그리로.</p>
<div class="spec" id="spec">
  <nav class="nav" id="nav" aria-label="유스케이스 목록"></nav>
  <article class="detail" id="detail" aria-live="polite"></article>
</div>

<h2><span class="n">3</span>패키지</h2>
<p class="soft">유스케이스를 기능 영역으로 묶은 것. 다이어그램의 관계선은 원본 표의 <code>포함</code>·<code>확장점</code>·<code>일반화</code>에서 그려진다. 타원을 누르면 2번 명세로.</p>
<div class="tabs" id="tabs" role="tablist"></div>
<div class="canvas"><svg id="dg" xmlns="http://www.w3.org/2000/svg"></svg></div>
${LEGEND}

<h2><span class="n">4</span>대응표</h2>
<table class="matrix" id="mx1"></table>
<div style="height:18px"></div>
<table class="matrix" id="mx2"></table>
</div>`
  return { html, onMount: (root) => mount(root, data, actorsFrom(actorSec), ctx) }
}

// ───────────────────────── 동작 (build.py <script>) ─────────────────────────
const NS = 'http://www.w3.org/2000/svg'
const RX = 94
const RY = 30

type Attrs = Record<string, string | number>
const el = (t: string, a: Attrs = {}): SVGElement => {
  const n = document.createElementNS(NS, t)
  for (const k in a) n.setAttribute(k, String(a[k]))
  return n
}
const parseIds = (s: string | undefined): string[] => (!s || s === '—' ? [] : (s.match(UC_ID) ?? []))
const firstId = (s: string | undefined): string | undefined => UC_ID1.exec(s ?? '')?.[0]

function edgePt(cx: number, cy: number, tx: number, ty: number, ry: number = RY): [number, number] {
  const a = Math.atan2((ty - cy) * RX, (tx - cx) * ry)
  return [cx + RX * Math.cos(a), cy + ry * Math.sin(a)]
}

function wrap(text: string, max: number): string[] {
  const lines: string[] = []
  let cur = ''
  for (const w of text.split(' ')) {
    if ((cur + ' ' + w).trim().length > max) {
      if (cur.trim()) lines.push(cur.trim())
      cur = w
    } else cur += ' ' + w
  }
  if (cur.trim()) lines.push(cur.trim())
  return lines.length ? lines : [text]
}

function buildDefs(): SVGElement {
  const defs = el('defs')
  const m = el('marker', { id: 'open', viewBox: '0 0 10 10', refX: '9.5', refY: '5', markerWidth: '9', markerHeight: '9', orient: 'auto-start-reverse' })
  m.appendChild(el('path', { d: 'M0,0 L10,5 L0,10', fill: 'none', stroke: '#5C6B73', 'stroke-width': '1.3' }))
  defs.appendChild(m)
  const g = el('marker', { id: 'tri', viewBox: '0 0 12 12', refX: '11', refY: '6', markerWidth: '13', markerHeight: '13', orient: 'auto-start-reverse' })
  g.appendChild(el('path', { d: 'M0,0.5 L11,6 L0,11.5 Z', fill: '#fff', stroke: '#5C6B73', 'stroke-width': '1.2' }))
  defs.appendChild(g)
  return defs
}

interface Pos {
  x: number
  y: number
  abstract?: boolean
  outside?: boolean
}

function mount(root: HTMLElement, D: UcData, ACT: Record<UcActor, ActorInfo>, ctx: RenderCtx): () => void {
  const q = <T extends Element>(sel: string): T | null => root.querySelector<T>(sel)
  const svg = q<SVGSVGElement>('#dg')
  const tabs = q<HTMLElement>('#tabs')
  const nav = q<HTMLElement>('#nav')
  const detail = q<HTMLElement>('#detail')
  const spec = q<HTMLElement>('#spec')
  const mx1 = q<HTMLTableElement>('#mx1')
  const mx2 = q<HTMLTableElement>('#mx2')
  if (!svg || !tabs || !nav || !detail || !spec || !mx1 || !mx2) return () => {}

  const UCMAP: Record<string, Uc> = Object.fromEntries(D.ucs.map((u) => [u.id, u]))
  const PKGS: string[] = []
  for (const u of D.ucs) if (!PKGS.includes(u.package)) PKGS.push(u.package)

  let curPkg = PKGS[0] ?? ''
  let curId: string | null = null

  // ── 다이어그램 ──
  function drawPackage(pkg: string) {
    if (!svg) return
    svg.innerHTML = ''
    svg.appendChild(buildDefs())
    const ucs = D.ucs.filter((u) => u.package === pkg)
    const inPkg = new Set(ucs.map((u) => u.id))
    const outside: string[] = []
    ucs.forEach((u) =>
      [...parseIds(u.include), ...parseIds(u.extPoint)].forEach((id) => {
        if (!inPkg.has(id) && !outside.includes(id)) outside.push(id)
      }),
    )
    const abstracts = [...new Set(ucs.map((u) => firstId(u.general)).filter((x): x is string => !!x))]

    const actors = [...new Set(ucs.map((u) => u.actor))].filter((a) => a !== 'system')
    const main = ucs.filter((u) => u.actor !== 'system')
    const sub = ucs.filter((u) => u.actor === 'system')
    const rowH = 88
    const colMid = 530
    const colRight = 890
    const P: Record<string, Pos> = {}
    const RYs: Record<string, number> = {}
    const ryOf = (u: Uc | undefined) => (u && u.extPoint && u.extPoint !== '—' ? RY + 16 : RY)
    main.forEach((u, i) => {
      P[u.id] = { x: colMid, y: 110 + i * rowH }
      RYs[u.id] = ryOf(u)
    })
    const ry0 = 110 + main.length * rowH
    abstracts.forEach((id, i) => {
      P[id] = { x: colMid, y: ry0 + i * rowH, abstract: true }
      RYs[id] = RY
    })
    const rightAll = [...sub.map((u) => u.id), ...outside]
    rightAll.forEach((id, i) => {
      P[id] = { x: colRight, y: 110 + i * 82, outside: !inPkg.has(id) }
      RYs[id] = ryOf(UCMAP[id])
    })

    const maxY = Math.max(...Object.values(P).map((p) => p.y), 260) + 100
    const W = 1150
    svg.setAttribute('viewBox', `0 0 ${W} ${maxY}`)
    svg.setAttribute('style', `min-width:${W}px;height:${maxY}px`)

    svg.appendChild(el('rect', { x: 300, y: 56, width: 790, height: maxY - 100, fill: 'none', stroke: '#1E2A30', 'stroke-width': '1.5' }))
    const title = el('text', { x: 316, y: 79, 'font-size': '13.5', 'font-weight': '600', fill: '#1E2A30' })
    title.textContent = pkg
    svg.appendChild(title)

    const anchors: Partial<Record<UcActor, { x: number; y: number }>> = {}
    actors.forEach((k, i) => {
      const a = ACT[k]
      const x = 155
      const y = 150 + i * (maxY > 420 ? 190 : 150)
      const s: Attrs = { stroke: a.hex, 'stroke-width': 1.8, fill: 'none' }
      const g = el('g')
      g.appendChild(el('circle', { cx: x, cy: y, r: 10, ...s, fill: '#fff' }))
      g.appendChild(el('line', { x1: x, y1: y + 10, x2: x, y2: y + 36, ...s }))
      g.appendChild(el('line', { x1: x - 16, y1: y + 19, x2: x + 16, y2: y + 19, ...s }))
      g.appendChild(el('line', { x1: x, y1: y + 36, x2: x - 13, y2: y + 55, ...s }))
      g.appendChild(el('line', { x1: x, y1: y + 36, x2: x + 13, y2: y + 55, ...s }))
      let n = el('text', { x, y: y + 74, class: 'a-name', fill: a.hex })
      n.textContent = a.label
      g.appendChild(n)
      n = el('text', { x, y: y + 89, class: 'a-sub' })
      n.textContent = a.sub
      g.appendChild(n)
      svg.appendChild(g)
      anchors[k] = { x, y: y + 22 }
    })

    main.forEach((u) => {
      const a = anchors[u.actor]
      const p = P[u.id]
      if (!a) return
      const [ex, ey] = edgePt(p.x, p.y, a.x, a.y, RYs[u.id])
      svg.appendChild(el('line', { x1: a.x, y1: a.y, x2: ex, y2: ey, class: 'assoc', stroke: ACT[u.actor].hex }))
    })

    const dep = (from: string, to: string, label: string) => {
      const f = P[from]
      const g = P[to]
      if (!f || !g) return
      const [sx, sy] = edgePt(f.x, f.y, g.x, g.y, RYs[from])
      const [tx, ty] = edgePt(g.x, g.y, f.x, f.y, RYs[to])
      svg.appendChild(el('line', { x1: sx, y1: sy, x2: tx, y2: ty, class: 'dep', stroke: '#5C6B73', 'marker-end': 'url(#open)' }))
      const l = el('text', { x: (sx + tx) / 2, y: (sy + ty) / 2 - 6, class: 'stereo' })
      l.textContent = label
      svg.appendChild(l)
    }
    ucs.forEach((u) => {
      parseIds(u.include).forEach((id) => dep(u.id, id, '«include»'))
      parseIds(u.extPoint).forEach((id) => dep(u.id, id, '«extend»'))
      const gi = firstId(u.general)
      if (gi && P[gi]) {
        const f = P[u.id]
        const g = P[gi]
        const [sx, sy] = edgePt(f.x, f.y, g.x, g.y, RYs[u.id])
        const [tx, ty] = edgePt(g.x, g.y, f.x, f.y, RYs[gi])
        svg.appendChild(el('line', { x1: sx, y1: sy, x2: tx, y2: ty, class: 'gen', stroke: '#5C6B73', 'marker-end': 'url(#tri)' }))
      }
    })

    Object.entries(P).forEach(([id, p]) => {
      const u: Uc | undefined = UCMAP[id]
      const isAbs = !!p.abstract
      const isOut = !!p.outside
      const name = u ? u.name : id
      const color = u ? ACT[u.actor].hex : '#5C6B73'
      const xp = !!(u && u.extPoint && u.extPoint !== '—')
      const g = el('g', { class: 'uc', ...(u ? { 'data-uc': id, tabindex: '0', role: 'button', 'aria-label': id + ' ' + name } : {}) })
      g.appendChild(
        el('ellipse', {
          cx: p.x,
          cy: p.y,
          rx: RX,
          ry: RYs[id],
          class: 'uc-el' + (isAbs ? ' abstract' : ''),
          stroke: color,
          ...(isOut ? { 'stroke-dasharray': '3 3' } : {}),
        }),
      )
      const k = el('text', { x: p.x, y: p.y - (xp ? 18 : 13), class: 'uc-k' })
      k.textContent = isAbs ? '추상' : id.replace('UC-', '')
      g.appendChild(k)
      const lines = wrap(name, 13)
      lines.forEach((ln, i) => {
        const y = p.y + (xp ? -1 : 5) + i * 15 - (lines.length - 1) * 7
        const tn = el('text', { x: p.x, y, class: 'uc-t' })
        tn.textContent = ln
        g.appendChild(tn)
      })
      if (xp && u) {
        const h = el('text', { x: p.x, y: p.y + 24, class: 'uc-xp-h' })
        h.textContent = 'Extension Points'
        g.appendChild(h)
        const c = el('text', { x: p.x, y: p.y + 36, class: 'uc-xp' })
        c.textContent = /`(.+?)`/.exec(u.extPoint)?.[1] ?? ''
        g.appendChild(c)
      }
      svg.appendChild(g)
    })

    if (outside.length) {
      const n = el('text', { x: colRight, y: maxY - 46, class: 'ext-only', 'text-anchor': 'middle' })
      n.textContent = '점선 타원은 다른 패키지의 유스케이스'
      svg.appendChild(n)
    }
    refreshSel()
  }

  // ── 탭 ──
  PKGS.forEach((p, i) => {
    const b = document.createElement('button')
    b.type = 'button'
    b.setAttribute('role', 'tab')
    b.dataset.pkg = p
    b.setAttribute('aria-selected', String(i === 0))
    b.innerHTML = esc(p) + `<span class="cnt">${D.ucs.filter((u) => u.package === p).length}</span>`
    tabs.appendChild(b)
  })
  const setTab = (p: string) => {
    curPkg = p
    tabs.querySelectorAll<HTMLButtonElement>('button').forEach((x) => x.setAttribute('aria-selected', String(x.dataset.pkg === p)))
    drawPackage(p)
  }

  // ── 좌 목록 ──
  ACTOR_ORDER.forEach((k) => {
    const list = D.ucs.filter((u) => u.actor === k)
    if (!list.length) return
    const h = document.createElement('div')
    h.className = 'nav-grp'
    h.style.color = ACT[k].hex
    h.textContent = ACT[k].label + ' · ' + list.length
    nav.appendChild(h)
    list.forEach((u) => {
      const a = document.createElement('a')
      a.href = `#item-${u.id}`
      a.id = `item-${u.id}`
      a.dataset.uc = u.id
      a.dataset.item = u.id
      a.style.color = ACT[k].hex
      a.innerHTML = `<span class="k">${esc(u.short)}</span><span style="color:var(--ink)">${esc(u.name)}</span>`
      nav.appendChild(a)
    })
  })

  // ── 우 상세 ──
  function render(u: Uc) {
    if (!detail) return
    const c = ACT[u.actor].hex
    const base: [string, string][] = [
      ['범위', md(u.scope)],
      ['수준', `<span class="lv">${md(u.level)}</span>`],
      ['주 액터', linkUC(u.primary, ctx)],
      ['이해관계자와 관심사', md(u.stakeholders)],
      ['사전조건', md(u.pre)],
      ['최소 보장', md(u.minGuarantee)],
      ['성공 보장', md(u.successGuarantee)],
      ['트리거', md(u.trigger)],
    ]
    const rel: [string, string][] = [
      ['패키지', md(u.package)],
      ['포함(include)', linkUC(u.include, ctx)],
      ['확장점', linkUC(u.extPoint, ctx)],
      ['일반화', linkUC(u.general, ctx)],
    ]
    const baseHtml = base.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join('')
    const relHtml = rel.map(([k, v]) => `<tr class="rel"><th>${k}</th><td>${v}</td></tr>`).join('')
    const flow = u.flow.map((s) => `<li>${linkUC(s, ctx)}</li>`).join('')
    const ext = u.ext
      .map((e) => {
        const m = /^(\d+[a-z])\.\s*(.+)$/.exec(e.on)
        const br = m ? m[1] : ''
        const ti = m ? m[2] : e.on
        const steps = e.steps.map((s) => `<li>${linkUC(s, ctx)}</li>`).join('')
        return `<div class="ext-item" style="border-left-color:${c}">
      <div class="ext-on"><span class="br">${br}</span>${md(ti)}</div>
      ${steps ? `<ul>${steps}</ul>` : ''}</div>`
      })
      .join('')
    detail.innerHTML = `
    <div class="d-head" style="color:${c}">
      <span class="d-id">${esc(u.id)}</span>
      <h3 class="d-name" style="color:var(--ink)">${esc(u.name)}</h3></div>
    <p class="d-links">연관 요구사항·시나리오 &nbsp;<span class="mono">${linkUC(u.links, ctx)}</span></p>
    <table class="attrs">${baseHtml}${relHtml}</table>
    <p class="sec-t">기본 흐름</p><ol class="flow">${flow}</ol>
    <p class="sec-t">확장</p><div class="ext">${ext}</div>
    ${u.note ? `<p class="sec-t">사후조건 참고</p><div class="note">${linkUC(u.note, ctx)}</div>` : ''}`
  }
  function refreshSel() {
    svg?.querySelectorAll<SVGGElement>('g.uc').forEach((g) => g.classList.toggle('sel', g.dataset.uc === curId))
  }
  function select(id: string, scroll: boolean) {
    const u = UCMAP[id]
    if (!u || !nav || !spec) return
    curId = id
    render(u)
    nav.querySelectorAll<HTMLAnchorElement>('a').forEach((a) => a.classList.toggle('sel', a.dataset.uc === id))
    nav.querySelector('a.sel')?.scrollIntoView({ block: 'nearest' })
    if (u.package !== curPkg) setTab(u.package)
    else refreshSel()
    if (scroll) spec.scrollIntoView({ block: 'start' })
  }

  // ── 대응표 ──
  function matrix(elm: HTMLTableElement, head: [string, string], rows: string[][]) {
    const chips = (s: string) =>
      s
        .split(',')
        .map((x) => {
          const k = x.trim()
          return UCMAP['UC-' + k] ? `<span class="chip" data-jump="UC-${esc(k)}">${esc(k)}</span>` : `<span class="chip">${esc(k)}</span>`
        })
        .join('')
    elm.innerHTML =
      `<thead><tr><th>${esc(head[0])}</th><th>${esc(head[1])}</th></tr></thead><tbody>` +
      rows.map((r) => `<tr><td>${md(r[0] ?? '')}</td><td>${chips(r[1] ?? '')}</td></tr>`).join('') +
      `</tbody>`
  }
  matrix(mx1, ['시나리오', '유스케이스'], D.scenarioMap)
  matrix(mx2, ['요구사항', '유스케이스'], D.reqMap)

  // ── 이벤트 (root에 위임 — 정리 함수에서 한 번에 뗀다) ──
  const onClick = (e: Event) => {
    const t = e.target
    if (!(t instanceof Element)) return
    const chip = t.closest<HTMLElement>('table.matrix [data-jump]')
    if (chip && chip.dataset.jump) {
      select(chip.dataset.jump, true)
      return
    }
    const j = t.closest<HTMLElement>('[data-jump]')
    if (j && j.dataset.jump) {
      select(j.dataset.jump, false)
      return
    }
    const a = t.closest<HTMLAnchorElement>('.nav a[data-uc]')
    if (a && a.dataset.uc) {
      e.preventDefault()
      select(a.dataset.uc, false)
      return
    }
    const b = t.closest<HTMLButtonElement>('.tabs button[data-pkg]')
    if (b && b.dataset.pkg !== undefined) {
      setTab(b.dataset.pkg)
      return
    }
    const g = t.closest<SVGGElement>('g.uc[data-uc]')
    if (g && g.dataset.uc) select(g.dataset.uc, false)
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    const t = e.target
    if (!(t instanceof Element)) return
    const g = t.closest<SVGGElement>('g.uc[data-uc]')
    if (g && g.dataset.uc) {
      e.preventDefault()
      select(g.dataset.uc, false)
    }
  }
  root.addEventListener('click', onClick)
  root.addEventListener('keydown', onKey)

  // ── 초기 상태: URL 해시 #item-UC-xx가 있으면 그것, 아니면 첫 패키지의 첫 항목 ──
  if (D.ucs.length) {
    drawPackage(curPkg)
    const hashId = /^#item-(UC-[AHGS]\d+)$/.exec(root.ownerDocument.location.hash)?.[1]
    const first = D.ucs.find((u) => u.package === curPkg) ?? D.ucs[0]
    select(hashId && UCMAP[hashId] ? hashId : first.id, false)
  }

  return () => {
    root.removeEventListener('click', onClick)
    root.removeEventListener('keydown', onKey)
  }
}

// ───────────────────────── CSS (build.py <style>, .v-uc 스코프) ─────────────────────────
export const ucCss = `
.v-uc{
  --paper:#EDEFEC; --panel:#F8F9F7; --card:#fff;
  --ink:#1E2A30; --soft:#5C6B73; --faint:#8A969C;
  --rule:#C9CFCB; --hair:#E1E5E1;
  --agent:#12776A; --human:#3A5BA0; --github:#6B4A9E; --system:#8A6D1F;
  color:var(--ink); font-feature-settings:"tnum"; line-height:1.65}
.v-uc *{box-sizing:border-box}
.v-uc code,.v-uc .mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.v-uc code{font-size:.88em; background:#E4E8E4; padding:1px 5px; border-radius:2px}

.v-uc h2{font-size:19px; font-weight:700; margin:44px 0 8px; letter-spacing:-.01em}
.v-uc h2 .n{color:var(--faint); font-weight:500; margin-right:9px}
.v-uc .lead{margin:0 0 16px; color:var(--soft); font-size:14px; max-width:76ch}

.v-uc .tabs{display:flex; flex-wrap:wrap; border:1.5px solid var(--ink); border-bottom:none; background:var(--panel)}
.v-uc .tabs button{font:inherit; font-size:14px; padding:11px 18px; background:none; border:none;
  border-right:1px solid var(--rule); cursor:pointer; color:var(--soft); position:relative}
.v-uc .tabs button:last-child{border-right:none}
.v-uc .tabs button[aria-selected="true"]{background:var(--card); color:var(--ink); font-weight:700}
.v-uc .tabs button[aria-selected="true"]::after{content:""; position:absolute; left:0; right:0; bottom:-1.5px; height:3px; background:var(--ink)}
.v-uc .tabs button:focus-visible{outline:2px solid var(--ink); outline-offset:-4px}
.v-uc .tabs .cnt{color:var(--faint); font-size:12px; margin-left:6px; font-weight:400}
.v-uc .canvas{border:1.5px solid var(--ink); background:var(--card); overflow-x:auto}
.v-uc .canvas svg{display:block}

.v-uc .uc-el{fill:#fff; stroke-width:1.6; transition:fill .12s}
.v-uc .uc-el.abstract{stroke-dasharray:6 4; fill:var(--panel)}
.v-uc .uc-t{font-size:12.5px; fill:var(--ink); text-anchor:middle; pointer-events:none}
.v-uc .uc-k{font-size:10px; font-family:ui-monospace,Menlo,monospace; fill:var(--faint); text-anchor:middle; pointer-events:none}
.v-uc .uc-xp{font-size:9.5px; fill:var(--soft); text-anchor:middle; pointer-events:none}
.v-uc .uc-xp-h{font-size:9px; fill:var(--faint); text-anchor:middle; font-weight:600; pointer-events:none}
.v-uc g.uc{cursor:pointer}
.v-uc g.uc:hover .uc-el{fill:#F0F4F0}
.v-uc g.uc.sel .uc-el{fill:#FFF6D9; stroke-width:2.6}
.v-uc .assoc{stroke-width:1.2; fill:none}
.v-uc .dep{stroke-dasharray:6 4; stroke-width:1.2; fill:none}
.v-uc .gen{stroke-width:1.2; fill:none}
.v-uc .stereo{font-size:10px; fill:var(--soft); font-style:italic; text-anchor:middle}
.v-uc .a-name{font-size:13px; font-weight:600; text-anchor:middle}
.v-uc .a-sub{font-size:10.5px; fill:var(--soft); text-anchor:middle}
.v-uc .ext-only{font-size:11px; fill:var(--faint); font-style:italic}

.v-uc .key{display:flex; flex-wrap:wrap; gap:20px; margin-top:10px; font-size:12.5px; color:var(--soft); align-items:center}
.v-uc .key span{display:inline-flex; align-items:center; gap:7px}
.v-uc .key svg{display:inline-block}

.v-uc .spec{display:grid; grid-template-columns:250px 1fr; border:1.5px solid var(--ink); background:var(--card)}
.v-uc .nav{border-right:1.5px solid var(--ink); background:var(--panel); max-height:78vh; overflow-y:auto}
.v-uc .nav-grp{padding:13px 16px 5px; font-size:11.5px; font-weight:700; color:var(--soft); position:sticky; top:0; background:var(--panel)}
.v-uc .nav a{display:block; padding:7px 16px; text-decoration:none; color:var(--ink); font-size:13.5px;
  border-left:3px solid transparent; line-height:1.4}
.v-uc .nav a:hover{background:#EAEEEA}
.v-uc .nav a.sel{border-left-color:currentColor; background:#fff; font-weight:600}
.v-uc .nav a .k{font-family:ui-monospace,Menlo,monospace; font-size:11px; color:var(--faint); margin-right:7px}
.v-uc .nav a.sel .k{color:inherit}
.v-uc .detail{padding:28px 32px 34px; max-height:78vh; overflow-y:auto}
.v-uc .d-head{display:flex; align-items:baseline; gap:11px; flex-wrap:wrap; margin-bottom:4px}
.v-uc .d-id{font-family:ui-monospace,Menlo,monospace; font-size:14px; padding:2px 9px; border:1.5px solid currentColor}
.v-uc .d-name{font-size:23px; font-weight:700; letter-spacing:-.02em; margin:0}
.v-uc .d-links{font-size:12.5px; color:var(--soft); margin:0 0 20px}
.v-uc table.attrs{border-collapse:collapse; width:100%; margin-bottom:26px; font-size:14px}
.v-uc table.attrs th{text-align:left; vertical-align:top; width:158px; font-weight:600; color:var(--soft);
  padding:9px 14px 9px 0; border-bottom:1px solid var(--hair); white-space:nowrap}
.v-uc table.attrs td{vertical-align:top; padding:9px 0; border-bottom:1px solid var(--hair)}
.v-uc table.attrs tr:last-child th,.v-uc table.attrs tr:last-child td{border-bottom:none}
.v-uc table.attrs tr.rel th{background:#F4F7F3; padding-left:10px}
.v-uc table.attrs tr.rel td{background:#F4F7F3; padding-right:10px}
.v-uc .lv{display:inline-block; font-size:12px; padding:1px 9px; border:1px solid var(--rule); background:var(--panel)}
.v-uc .sec-t{font-size:13px; font-weight:700; margin:0 0 11px; padding-bottom:7px; border-bottom:1.5px solid var(--ink)}
.v-uc ol.flow{margin:0 0 26px; padding-left:0; list-style:none; counter-reset:f}
.v-uc ol.flow li{counter-increment:f; position:relative; padding:6px 0 6px 38px; border-bottom:1px solid var(--hair)}
.v-uc ol.flow li:last-child{border-bottom:none}
.v-uc ol.flow li::before{content:counter(f); position:absolute; left:0; top:6px;
  font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--faint); width:24px; text-align:right}
.v-uc .ext{margin-bottom:24px}
.v-uc .ext-item{border-left:2.5px solid var(--rule); padding:2px 0 2px 15px; margin-bottom:14px}
.v-uc .ext-on{font-weight:600; font-size:14px}
.v-uc .ext-on .br{font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:var(--soft); margin-right:7px}
.v-uc .ext-item ul{margin:5px 0 0; padding-left:17px; color:var(--soft); font-size:14px}
.v-uc .note{background:var(--panel); border-left:2.5px solid var(--rule); padding:11px 15px; font-size:13.5px; color:var(--soft)}
.v-uc .jump{cursor:pointer; border-bottom:1px dashed currentColor}

.v-uc table.matrix{border-collapse:collapse; width:100%; font-size:13.5px; background:var(--card); border:1.5px solid var(--ink)}
.v-uc table.matrix th,.v-uc table.matrix td{padding:9px 13px; border-bottom:1px solid var(--hair); text-align:left; vertical-align:top}
.v-uc table.matrix thead th{background:var(--panel); font-weight:700; border-bottom:1.5px solid var(--ink)}
.v-uc table.matrix tr:last-child td{border-bottom:none}
.v-uc table.matrix td:first-child{white-space:nowrap; font-weight:600; width:1%}
.v-uc .chip{display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:11.5px;
  padding:1px 7px; margin:2px 3px 2px 0; border:1px solid var(--rule); background:var(--panel); cursor:pointer}
.v-uc .chip:hover{border-color:var(--ink)}
@media (max-width:900px){
  .v-uc .spec{grid-template-columns:1fr}
  .v-uc .nav{border-right:none; border-bottom:1.5px solid var(--ink); max-height:220px}
  .v-uc .detail{max-height:none}
}
@media (prefers-reduced-motion:reduce){.v-uc *{transition:none!important}}
`
