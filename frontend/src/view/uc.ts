/** V-UC — 유스케이스 문서 (STD-002 V-UC, 카드 AM). tools/view_build.py v_uc와 한 쌍.
 *  원본 순서로 펼친다 — 절·소절 머리는 그대로, 유스케이스는 제자리에 카드(항목 표 → 기본 흐름 → 확장 → 사후조건 참고 → 연관 →
 *  「그 밖」). 대응표는 원본 표 + 「유스케이스」 열 칩. 패키지 그림(UML 유스케이스 다이어그램)은 뷰 끝 — 원본에 없고 항목 표에서 그린다.
 *  CSS는 ucCss(`.v-uc` 스코프) — view_build.py UC_CSS와 바이트 같다(check_view_css 다섯째 쌍). */
import { esc, etcBlock, h2, inline, itemBlocks, leadRest, renderBlocks, secName, splitItems, splitSections, type RenderCtx } from './md'
import type { ViewFn } from './types'
import { itemCard } from './views'
import { fences, firstTable } from './wireframe'

// ───────────────────────── 파싱 (view_build.uc_parts) ─────────────────────────
export type UcActor = 'agent' | 'human' | 'github' | 'system'
const ACTOR_OF: Record<string, UcActor> = { A: 'agent', H: 'human', G: 'github', S: 'system' }
const UC_ITEM = /UC-[AHGS]\d+/
const REL = ['패키지', '포함', '확장점', '일반화']
const FLOW_H = /^\*\*(기본 흐름[^*]*)\*\*(.*)$/
const EXT_H = /^\*\*(확장(?!점)[^*]*)\*\*(.*)$/
const NOTE_H = /^\*\*(사후조건 참고[^*]*)\*\*(.*)$/
const LINK_H = /^\*\*(연관[^*]*)\*\*(.*)$/
const EXT_ITEM = /^- \*\*(.+?)\*\*(.*)$/
const STEP = /^(\d+\.\s+)/

/** 항목 표 행 이름 — 괄호 앞만 본다(`포함(include)` = `포함`) */
const ucKey = (k: string) => k.replace(/\s*\(.*\)\s*$/, '').trim()
/** `**연관**: …`의 머리 뒤 글 — 쌍점과 빈칸을 뗀다 */
const after = (s: string) => s.replace(/^\s*:?\s*/, '')

export interface UcFlow {
  name: string
  lead: string
  steps: string[][]
}
export interface UcExtItem {
  on: string
  extra: string
  lines: string[]
}
export interface UcExtBlock {
  name: string
  lead: string
  items: UcExtItem[]
}
export interface UcPiece {
  name: string
  lines: string[]
}
export interface UcParts {
  rows: [string, string][]
  flows: UcFlow[]
  exts: UcExtBlock[]
  note: UcPiece | null
  links: UcPiece | null
  etc: string[]
}

/** view_build.uc_parts — 유스케이스 블록 하나를 줄 단위로 가른다(코드 펜스 인식) (STD-002 V-UC, #152).
 *  항목 표 = 첫 두 칸 표(머리 행은 뺀다). `**기본 흐름…**`·`**확장…**`·`**사후조건 참고**`·`**연관**` 줄이 조각을 연다 — 흐름은 번호 줄이
 *  단계, 확장은 `- **2a. 제목**` 줄이 한 확장이고, 빈 줄 없이 이어진 줄·들여 쓴 줄은 그 안. 어디에도 안 맞는 줄은 etc(「그 밖」) */
export function ucParts(text: string): UcParts {
  const lines = text.split('\n')
  const n = lines.length
  const [fenced] = fences(lines)
  const used = new Set<number>()
  let rows: [string, string][] = []
  const [trows, ta, tb] = firstTable(lines, fenced, 0, n)
  if (trows.length >= 2 && trows.every((r) => r.length === 2)) {
    rows = trows.slice(1).map((r): [string, string] => [r[0], r[1]])
    for (let k = ta; k < tb; k++) used.add(k)
  }
  const flows: UcFlow[] = []
  const exts: UcExtBlock[] = []
  let note: UcPiece | null = null
  let links: UcPiece | null = null
  let mode = ''
  let into: string[] | null = null
  let blank = false
  let fence = false
  for (let i = 0; i < n; i++) {
    if (used.has(i)) continue
    const l = lines[i]
    if (fence) {
      if (into) {
        into.push(l)
        used.add(i)
      }
      fence = !l.trimStart().startsWith('```')
      continue
    }
    let m: RegExpExecArray | null
    if ((m = FLOW_H.exec(l))) {
      flows.push({ name: m[1].trim(), lead: after(m[2]), steps: [] })
      mode = 'flow'
      into = null
      used.add(i)
    } else if ((m = EXT_H.exec(l))) {
      exts.push({ name: m[1].trim(), lead: after(m[2]), items: [] })
      mode = 'ext'
      into = null
      used.add(i)
    } else if ((m = NOTE_H.exec(l))) {
      note = { name: m[1].trim(), lines: [after(m[2])] }
      mode = 'note'
      into = note.lines
      used.add(i)
    } else if ((m = LINK_H.exec(l))) {
      links = { name: m[1].trim(), lines: [after(m[2])] }
      mode = 'link'
      into = links.lines
      used.add(i)
    } else if (mode === 'flow' && STEP.test(l)) {
      into = [l]
      flows[flows.length - 1].steps.push(into)
      used.add(i)
    } else if (mode === 'ext' && (m = EXT_ITEM.exec(l))) {
      const it: UcExtItem = { on: m[1].trim(), extra: m[2], lines: [] }
      exts[exts.length - 1].items.push(it)
      into = it.lines
      used.add(i)
    } else if (into && (!l.trim() || l[0] === ' ' || l[0] === '\t' || !blank)) {
      into.push(l) // 이어진 줄 — 빈 줄 없이 이어지거나 들여 쓴 줄
      used.add(i)
    } else into = null // 그 밖 — 모드는 그대로(다음 번호 줄은 같은 흐름)
    fence = l.trimStart().startsWith('```')
    blank = !l.trim()
  }
  const etc: string[] = []
  let gap = false
  for (let i = 0; i < n; i++) {
    if (used.has(i)) {
      gap = true
      continue
    }
    if (gap && etc.length && etc[etc.length - 1].trim()) etc.push('') // 쓰인 줄을 건너뛴 자리 — 앞뒤 문단이 붙지 않게
    gap = false
    etc.push(lines[i])
  }
  return { rows, flows, exts, note, links, etc }
}

// ───────────────────────── 그리기 ─────────────────────────
const ACT_DEFAULT: Record<UcActor, { label: string; hex: string }> = {
  agent: { label: '에이전트', hex: '#12776A' },
  human: { label: '사람', hex: '#3A5BA0' },
  github: { label: 'GitHub', hex: '#6B4A9E' },
  system: { label: '하위기능', hex: '#8A6D1F' },
}
const ACTOR_ORDER: UcActor[] = ['agent', 'human', 'github', 'system']
const actorOf = (id: string): UcActor => ACTOR_OF[id.charAt(3)] ?? 'system'

/** view_build.uc_inner — 카드 몸: 항목 표 → 기본 흐름 → 확장 → 사후조건 참고 → 연관 → 그 밖 (문서 순서) */
export function ucInner(id: string, p: UcParts, ctx: RenderCtx): string {
  const hex = ACT_DEFAULT[actorOf(id)].hex
  let h = ''
  if (p.rows.length) {
    h +=
      '<table class="attrs">' +
      p.rows
        .map(([k, v]) => {
          const key = ucKey(k)
          // 표 칸 안 줄바꿈은 <br>로 쓴다(마크다운 표는 줄을 못 나눈다) — 예전 상세 칸처럼 줄바꿈으로 되살린다
          const v1 = inline(v, ctx).replace(/&lt;br\s*\/?&gt;/g, '<br>')
          const val = key === '수준' ? `<span class="lv">${v1}</span>` : v1
          return `<tr${REL.includes(key) ? ' class="rel"' : ''}><th>${inline(k, ctx)}</th><td>${val}</td></tr>`
        })
        .join('') +
      '</table>'
  }
  for (const f of p.flows) {
    h += `<p class="sec-t">${esc(f.name)}</p>` + (f.lead.trim() ? renderBlocks(f.lead, ctx) : '')
    h +=
      '<ol class="flow">' +
      f.steps
        .map((st) => {
          const w = STEP.exec(st[0])![1].length
          const [lead, rest] = leadRest(st[0].slice(w).trim(), st.slice(1), w)
          return `<li>${inline(lead, ctx)}${renderBlocks(rest, ctx)}</li>`
        })
        .join('') +
      '</ol>'
  }
  for (const e of p.exts) {
    h += `<p class="sec-t">${esc(e.name)}</p>` + (e.lead.trim() ? renderBlocks(e.lead, ctx) : '')
    h +=
      '<div class="ext">' +
      e.items
        .map((it) => {
          const m = /^((?:\d+|\*)[a-z])\.\s*(.+)$/.exec(it.on)
          const title = (m ? m[2] : it.on) + it.extra
          const [, rest] = leadRest('', it.lines, 2)
          return `<div class="ext-item" style="border-left-color:${hex}"><div class="ext-on"><span class="br">${m ? esc(m[1]) : ''}</span>${inline(title, ctx)}</div>${renderBlocks(rest, ctx)}</div>`
        })
        .join('') +
      '</div>'
  }
  for (const piece of [p.note, p.links]) {
    if (piece) h += `<p class="sec-t">${esc(piece.name)}</p><div class="note">${renderBlocks(piece.lines.join('\n'), ctx)}</div>`
  }
  // 조각이 하나도 없는 항목(Cockburn이 아닌 문서)은 본문 전부를 그대로 — 「그 밖」 머리를 달지 않는다(V-SCN과 같다)
  return h ? h + etcBlock(p.etc, ctx) : renderBlocks(p.etc.join('\n'), ctx)
}

/** HTML의 글자 조각에만 fn — 태그 속성과 <a> 안 글자는 건드리지 않는다 (view_build._map_text) */
function mapText(h: string, fn: (t: string) => string): string {
  let depth = 0
  return h
    .split(/(<[^>]+>)/)
    .map((tok) => {
      if (tok.startsWith('<')) {
        if (/^<a[\s>]/.test(tok)) depth++
        else if (tok.startsWith('</a')) depth = Math.max(0, depth - 1)
        return tok
      }
      return depth === 0 && tok ? fn(tok) : tok
    })
    .join('')
}

const jumpA = (id: string, ctx: RenderCtx, cls: string, text: string) =>
  `<a class="${cls}" href="${esc(ctx.href(ctx.selfId, id))}" data-ref="${esc(ctx.selfId)}#${esc(id)}">${esc(text)}</a>`

/** view_build.uc_jumps — 글자 속 맨몸 `UC-xx`(`#` 뒤 제외)를 그 카드로 가는 링크로. 있는 유스케이스만 */
function jumps(h: string, ids: Set<string>, ctx: RenderCtx): string {
  return mapText(h, (t) => t.replace(/(?<![A-Za-z0-9_#-])(UC-[AHGS]\d+)(?![A-Za-z0-9_])/g, (m) => (ids.has(m) ? jumpA(m, ctx, 'jump', m) : m)))
}

/** view_build.uc_chips — 대응표의 표마다 머리 칸에 「유스케이스」가 든 열의 `UC-A1`·`A1`을 칩으로. 다른 열은 글자 그대로 */
function chips(h: string, ids: Set<string>, ctx: RenderCtx): string {
  return h.replace(/<table>([\s\S]*?)<\/table>/g, (_t, inner: string) => {
    const head = /<thead>([\s\S]*?)<\/thead>/.exec(inner)?.[1] ?? ''
    const cols = new Set([...head.matchAll(/<th>([\s\S]*?)<\/th>/g)].flatMap((m, j) => (m[1].replace(/<[^>]+>/g, '').includes('유스케이스') ? [j] : [])))
    const body = inner.replace(/<tbody>([\s\S]*?)<\/tbody>/, (_b, rowsHtml: string) =>
      '<tbody>' +
      rowsHtml.replace(/<tr>([\s\S]*?)<\/tr>/g, (_r, row: string) => {
        let j = -1
        return (
          '<tr>' +
          row.replace(/<td>([\s\S]*?)<\/td>/g, (_c, cell: string) => {
            j++
            if (!cols.has(j)) return `<td>${cell}</td>`
            const c = mapText(cell, (t) =>
              t.replace(/(?<![A-Za-z0-9_#-])(UC-[AHGS]\d+|[AHGS]\d+)(?![A-Za-z0-9_])/g, (m) => {
                const id = m.startsWith('UC-') ? m : 'UC-' + m
                return ids.has(id) ? jumpA(id, ctx, 'chip', m) : m
              }),
            )
            return `<td>${c}</td>`
          }) +
          '</tr>'
        )
      }) +
      '</tbody>',
    )
    return `<table>${body}</table>`
  })
}

/** 그림 한 개 — 파서가 항목 표에서 뽑은 관계(행 이름 두 가지 다) */
export interface UcNode {
  id: string
  name: string
  actor: UcActor
  package: string
  include: string
  extPoint: string
  general: string
}
function ucNode(id: string, name: string, p: UcParts): UcNode {
  const row = (k: string) => p.rows.find(([x]) => ucKey(x) === k)?.[1] ?? ''
  return { id, name, actor: actorOf(id), package: row('패키지'), include: row('포함'), extPoint: row('확장점'), general: row('일반화') }
}

/** view_build.uc_actors — `액터` 절 표에서 코드(A·H·G·S) 칸이 있는 행의 이름. 없으면 기본 이름 */
function actorsFrom(sec: string): Record<UcActor, string> {
  const out: Record<UcActor, string> = { agent: ACT_DEFAULT.agent.label, human: ACT_DEFAULT.human.label, github: ACT_DEFAULT.github.label, system: ACT_DEFAULT.system.label }
  for (const line of sec.split('\n')) {
    if (!line.trim().startsWith('|')) continue
    const cs = line.trim().replace(/^\|+|\|+$/g, '').split('|').map((c) => c.trim())
    const code = cs.find((c) => /^[AHGS]$/.test(c))
    const label = cs.find((c) => c && c !== code)
    if (code && label) out[ACTOR_OF[code]] = label
  }
  return out
}

const LEGEND = `<div class="key">
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#5C6B73" stroke-width="1.2"/></svg>연결</span>
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="27" y2="5" stroke="#5C6B73" stroke-width="1.2" stroke-dasharray="6 4"/><path d="M27,1 L34,5 L27,9" fill="none" stroke="#5C6B73" stroke-width="1.2"/></svg>«include» / «extend»</span>
  <span><svg width="34" height="12"><line x1="0" y1="6" x2="24" y2="6" stroke="#5C6B73" stroke-width="1.2"/><path d="M24,1 L34,6 L24,11 Z" fill="#fff" stroke="#5C6B73" stroke-width="1.2"/></svg>일반화</span>
  <span><svg width="30" height="14"><ellipse cx="15" cy="7" rx="13" ry="6" fill="#F8F9F7" stroke="#5C6B73" stroke-width="1.4" stroke-dasharray="6 4"/></svg>추상·다른 패키지</span>
</div>`

const DIAGRAM = `<h2>패키지 그림</h2>
<p class="soft">원본에 없다 — 항목 표의 패키지·포함·확장점·일반화 행과 주 액터(ID 글자)에서 그렸다. 타원을 누르면 그 유스케이스 카드로.</p>
<div class="tabs" id="tabs" role="tablist"></div>
<div class="canvas"><svg id="dg" xmlns="http://www.w3.org/2000/svg"></svg></div>
${LEGEND}`

export const vUc: ViewFn = ({ body, ctx }) => {
  const ids = new Set(itemBlocks(body, UC_ITEM).map((b) => b.id))
  const out: string[] = []
  const nodes: UcNode[] = []
  let actorSec = ''
  for (const [title, text] of splitSections(body)) {
    const name = secName(title)
    if (name.startsWith('액터')) actorSec = text
    if (name.startsWith('대응표')) {
      out.push(h2(title) + jumps(chips(renderBlocks(text, ctx), ids, ctx), ids, ctx))
      continue
    }
    let html = ''
    for (const p of splitItems(text, UC_ITEM)) {
      if (p.kind === 'text') {
        html += jumps(renderBlocks(p.text, ctx), ids, ctx)
        continue
      }
      const parts = ucParts(p.block.text)
      nodes.push(ucNode(p.block.id, p.block.title, parts))
      html += itemCard(ctx, p.block, jumps(ucInner(p.block.id, parts, ctx), ids, ctx), '이 유스케이스를 근거로 삼은 문서')
    }
    out.push(h2(title) + html)
  }
  return { html: `<div class="v-uc">${out.join('\n')}\n${DIAGRAM}</div>`, onMount: (root) => mount(root, nodes, actorsFrom(actorSec)) }
}

// ───────────────────────── 동작 — 패키지 그림 (view_build.py UC_JS와 같은 코드) ─────────────────────────
const NS = 'http://www.w3.org/2000/svg'
const RX = 94
const RY = 30

type Attrs = Record<string, string | number>
const el = (t: string, a: Attrs = {}): SVGElement => {
  const n = document.createElementNS(NS, t)
  for (const k in a) n.setAttribute(k, String(a[k]))
  return n
}
const parseIds = (s: string | undefined): string[] => (!s || s === '—' ? [] : (s.match(/UC-[AHGS]\d+/g) ?? []))
const firstId = (s: string | undefined): string | undefined => /UC-[AHGS]\d+/.exec(s ?? '')?.[0]

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

function mount(root: HTMLElement, ucs: UcNode[], labels: Record<UcActor, string>): () => void {
  const svg = root.querySelector<SVGSVGElement>('#dg')
  const tabs = root.querySelector<HTMLElement>('#tabs')
  if (!svg || !tabs || !ucs.length) return () => {}
  const ACT = Object.fromEntries(ACTOR_ORDER.map((k) => [k, { label: labels[k], hex: ACT_DEFAULT[k].hex }])) as Record<UcActor, { label: string; hex: string }>
  const D = { ucs }
  const UCMAP: Record<string, UcNode> = Object.fromEntries(ucs.map((u) => [u.id, u]))
  const PKGS: string[] = []
  for (const u of ucs) if (!PKGS.includes(u.package)) PKGS.push(u.package)
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
    const ryOf = (u: UcNode | undefined) => (u && u.extPoint && u.extPoint !== '—' ? RY + 16 : RY)
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
      // 액터 밑 글은 없다 — 싱크독 사람·도구 이름이 박혀 모든 프로젝트 그림에 나왔다 (#152)
      const n = el('text', { x, y: y + 74, class: 'a-name', fill: a.hex })
      n.textContent = a.label
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
      const u: UcNode | undefined = UCMAP[id]
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
    b.innerHTML = esc(p || '(패키지 없음)') + `<span class="cnt">${ucs.filter((u) => u.package === p).length}</span>`
    tabs.appendChild(b)
  })
  const setTab = (p: string) => {
    curPkg = p
    tabs.querySelectorAll<HTMLButtonElement>('button').forEach((x) => x.setAttribute('aria-selected', String(x.dataset.pkg === p)))
    drawPackage(p)
  }
  function refreshSel() {
    svg?.querySelectorAll<SVGGElement>('g.uc').forEach((g) => g.classList.toggle('sel', g.dataset.uc === curId))
  }
  /** 타원 → 그 카드로 (카드는 제자리에 있다 — 원본 순서) */
  function select(id: string, scroll: boolean) {
    const u = UCMAP[id]
    if (!u) return
    curId = id
    if (u.package !== curPkg) setTab(u.package)
    else refreshSel()
    if (scroll) root.querySelector(`#item-${id}`)?.scrollIntoView({ block: 'start' })
  }

  const onClick = (e: Event) => {
    const t = e.target
    if (!(t instanceof Element)) return
    const b = t.closest<HTMLButtonElement>('#tabs button[data-pkg]')
    if (b && b.dataset.pkg !== undefined) {
      setTab(b.dataset.pkg)
      return
    }
    const g = t.closest<SVGGElement>('g.uc[data-uc]')
    if (g && g.dataset.uc) select(g.dataset.uc, true)
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    const t = e.target
    if (!(t instanceof Element)) return
    const g = t.closest<SVGGElement>('g.uc[data-uc]')
    if (g && g.dataset.uc) {
      e.preventDefault()
      select(g.dataset.uc, true)
    }
  }
  root.addEventListener('click', onClick)
  root.addEventListener('keydown', onKey)

  // 처음: #item-UC-xx로 들어오면 그 패키지 탭(스크롤은 페이지가 한다), 아니면 첫 패키지
  drawPackage(curPkg)
  const hashId = /^#item-(UC-[AHGS]\d+)$/.exec(root.ownerDocument.location.hash)?.[1]
  if (hashId && UCMAP[hashId]) select(hashId, false)

  return () => {
    root.removeEventListener('click', onClick)
    root.removeEventListener('keydown', onKey)
  }
}

// ───────────────────────── CSS (.v-uc 스코프 — view_build.py UC_CSS와 바이트 같다, check_view_css 다섯째 쌍) ─────────────────────────
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
.v-uc .ext-only{font-size:11px; fill:var(--faint); font-style:italic}

.v-uc .key{display:flex; flex-wrap:wrap; gap:20px; margin-top:10px; font-size:12.5px; color:var(--soft); align-items:center}
.v-uc .key span{display:inline-flex; align-items:center; gap:7px}
.v-uc .key svg{display:inline-block}

/* 유스케이스 카드 몸 — 항목 표 → 기본 흐름 → 확장 → 사후조건 참고·연관 (카드 AM) */
.v-uc table.attrs{border-collapse:collapse; width:100%; margin:4px 0 22px; font-size:14px; background:var(--card)}
.v-uc table.attrs th{text-align:left; vertical-align:top; width:158px; font-weight:600; color:var(--soft);
  padding:9px 14px 9px 0; border-bottom:1px solid var(--hair); white-space:nowrap}
.v-uc table.attrs td{vertical-align:top; padding:9px 0; border-bottom:1px solid var(--hair)}
.v-uc table.attrs tr:last-child th,.v-uc table.attrs tr:last-child td{border-bottom:none}
.v-uc table.attrs tr.rel th{background:#F4F7F3; padding-left:10px}
.v-uc table.attrs tr.rel td{background:#F4F7F3; padding-right:10px}
.v-uc .lv{display:inline-block; font-size:12px; padding:1px 9px; border:1px solid var(--rule); background:var(--panel)}
.v-uc .sec-t{font-size:13px; font-weight:700; margin:0 0 11px; padding-bottom:7px; border-bottom:1.5px solid var(--ink)}
.v-uc ol.flow{margin:0 0 22px; padding-left:0; list-style:none; counter-reset:f}
.v-uc ol.flow>li{counter-increment:f; position:relative; padding:6px 0 6px 38px; border-bottom:1px solid var(--hair)}
.v-uc ol.flow>li:last-child{border-bottom:none}
.v-uc ol.flow>li::before{content:counter(f); position:absolute; left:0; top:6px;
  font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--faint); width:24px; text-align:right}
.v-uc .ext{margin-bottom:22px}
.v-uc .ext-item{border-left:2.5px solid var(--rule); padding:2px 0 2px 15px; margin-bottom:14px}
.v-uc .ext-on{font-weight:600; font-size:14px}
.v-uc .ext-on .br{font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:var(--soft); margin-right:7px}
.v-uc .ext-item ul{margin:5px 0 0; padding-left:17px; color:var(--soft); font-size:14px}
.v-uc .note{background:var(--card); border-left:2.5px solid var(--rule); padding:11px 15px; margin-bottom:22px; font-size:13.5px; color:var(--soft)}
.v-uc .note p{margin:0}
/* 맨몸 UC-xx·대응표 칩 → 그 카드 */
.v-uc a.jump{color:inherit; text-decoration:none; cursor:pointer; border-bottom:1px dashed currentColor}
.v-uc a.chip{color:inherit; text-decoration:none}
.v-uc .chip{display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:11.5px;
  padding:1px 7px; margin:2px 3px 2px 0; border:1px solid var(--rule); background:var(--panel); cursor:pointer}
.v-uc .chip:hover{border-color:var(--ink)}
@media (prefers-reduced-motion:reduce){.v-uc *{transition:none!important}}
`
