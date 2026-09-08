/** tools/seq_build.py 포트 — V-SEQ (STD-002 2장 V-SEQ).
 *  좌: 시퀀스 목록을 의미 묶음(저장 파이프라인·판단·조회·운영·공통)으로. 본문 위: 원본 `생명선` 절에서 이 시퀀스에
 *  나오는 것만 고른 생명선 표. 가운데: 좌 mermaid(<pre class="mermaid"> — 렌더는 페이지가 한다, 확대 버튼) / 우 단계 목록
 *  (mermaid 화살표에서 자동 추출, alt·opt·loop 문맥은 회색 줄). 아래: 읽을 때 볼 것.
 *  파이썬은 절 하나만 main.innerHTML로 갈아끼웠다. 여기서는 절마다 <details>를 두고 하나만 연다(아코디언) — 시퀀스 상세가
 *  항상 DOM에 있어 페이지가 #item-SEQ-N으로 스크롤할 수 있다. [[#SEQ-N]]과 본문의 SEQ-N 언급은 페이지 안 점프. */
import { esc, inline, renderBlocks, secName, splitSections, type RenderCtx } from './md'
import type { ViewFn } from './types'

const SEQ_HEAD = /^(SEQ-\d+|SEQ-C\d+)(?:\s+(.*))?$/
const SEQ_MENTION = /\b(SEQ-C?\d+)\b/g

/** 좌 목록의 의미 묶음 — 원본 대응표 순서가 아니라 뷰 규약이 정한 그룹 (STD-002 V-SEQ). 문서에 없는 id는 건너뛰고,
 *  여기 없는 시퀀스는 "기타"로 모은다. */
const GROUPS: ReadonlyArray<readonly [string, readonly string[]]> = [
  ['저장 파이프라인', ['SEQ-1', 'SEQ-2', 'SEQ-5', 'SEQ-7', 'SEQ-19']],
  ['판단·처리', ['SEQ-3', 'SEQ-6', 'SEQ-17', 'SEQ-18']],
  ['조회', ['SEQ-9', 'SEQ-10', 'SEQ-11', 'SEQ-12', 'SEQ-13', 'SEQ-14', 'SEQ-15']],
  ['프로젝트·계정·운영', ['SEQ-4', 'SEQ-8', 'SEQ-16', 'SEQ-20', 'SEQ-21']],
  ['공통 형태', ['SEQ-C1', 'SEQ-C2']],
]

interface LifeInfo {
  name: string
  what: string
  kind: string
  where: string
}
interface LifeRow extends LifeInfo {
  ab: string
  label: string
}
interface Participant {
  ab: string
  label: string
}
interface Step {
  from: string
  arrow: string
  to: string
  msg: string
  /** alt/opt/loop 문맥. "alt 조건 › opt 조건". rect는 제외 */
  ctx: string
  fromL: string
  toL: string
  /** 점선(반환) */
  ret: boolean
}
interface TextSec {
  kind: 'text'
  id: string
  title: string
  /** [제목, 원문] — 여러 절이 하나로 합쳐질 수 있다(개요 = 0장 + 1장) */
  parts: [string, string][]
}
interface SeqSec {
  kind: 'seq'
  id: string
  title: string
  lead: string
  mermaid: string
  after: string
  life: LifeRow[]
  steps: Step[]
}
type Sec = TextSec | SeqSec

const stripFm = (s: string): string => s.replace(/^---\n[\s\S]*?\n---\n/, '')
/** 절 끝의 구분선(---)은 절 나누기용이라 그리지 않는다 */
const trimRule = (s: string): string => s.replace(/\n---\s*$/, '')

/** 본문 안 표 전부 → 셀 배열(구분선 행 제외) */
function parseTables(text: string): string[][][] {
  const out: string[][][] = []
  let cur: string[][] | null = null
  for (const l of text.split('\n')) {
    if (l.startsWith('|')) {
      const cells = l
        .replace(/^\||\|$/g, '')
        .split('|')
        .map((c) => c.trim())
      if (cells.every((c) => /^[-: ]*$/.test(c))) continue
      if (!cur) {
        cur = []
        out.push(cur)
      }
      cur.push(cells)
    } else cur = null
  }
  return out
}

/** 생명선 표(0장) → {약어: 정보}. 헤더에 "약어"가 있는 첫 표. 약어 칸은 `RP·RD·RR`처럼 여럿일 수 있다 */
function lifeMap(text: string): Map<string, LifeInfo> {
  const map = new Map<string, LifeInfo>()
  const tbl = parseTables(text).find((t) => t.length > 1 && t[0].length >= 5 && t[0].includes('약어'))
  if (!tbl) return map
  const abCol = tbl[0].indexOf('약어')
  for (const row of tbl.slice(1)) {
    const cells = [...row]
    while (cells.length < 5) cells.push('')
    const [name] = cells
    const rest = cells.filter((_c, i) => i !== abCol && i !== 0)
    const info: LifeInfo = { name, what: rest[0] ?? '', kind: rest[1] ?? '', where: rest[2] ?? '' }
    for (const ab of cells[abCol].split(/[·,]\s*/)) if (ab.trim()) map.set(ab.trim(), info)
  }
  return map
}

const ID = '[\\p{L}\\p{N}_]+'
const P_RE = new RegExp(`^(?:participant|actor)\\s+(${ID})(?:\\s+as\\s+(.+))?$`, 'u')
const MSG_RE = new RegExp(`^(${ID})\\s*(-->>|->>|-->|->|--x|-x|--\\)|-\\))\\s*(${ID})\\s*:\\s*(.*)$`, 'u')
const CTX_RE = /^(alt|opt|loop|rect|par|critical|break)\b\s*(.*)$/
const ELSE_RE = /^(?:else|and|option)\b\s*(.*)$/

/** participant 목록과 단계(화살표) 목록. alt/opt/loop 문맥도 붙인다 (seq_build.parse_mermaid) */
function parseMermaid(mer: string): { parts: Participant[]; steps: Omit<Step, 'fromL' | 'toL' | 'ret'>[] } {
  const parts: Participant[] = []
  const steps: Omit<Step, 'fromL' | 'toL' | 'ret'>[] = []
  const ctx: [string, string][] = []
  for (const line of mer.split('\n')) {
    const t = line.trim()
    let m = P_RE.exec(t)
    if (m) {
      parts.push({ ab: m[1], label: (m[2] ?? m[1]).replace(/<br\s*\/?>/g, ' ') })
      continue
    }
    m = CTX_RE.exec(t)
    if (m) {
      ctx.push([m[1], m[2]])
      continue
    }
    m = ELSE_RE.exec(t)
    if (m && ctx.length) {
      ctx[ctx.length - 1] = [ctx[ctx.length - 1][0], m[1]]
      continue
    }
    if (t === 'end' && ctx.length) {
      ctx.pop()
      continue
    }
    m = MSG_RE.exec(t)
    if (m)
      steps.push({
        from: m[1],
        arrow: m[2],
        to: m[3],
        msg: m[4],
        ctx: ctx
          .filter(([k]) => k !== 'rect')
          .map(([k, v]) => `${k} ${v}`.trim())
          .join(' › '),
      })
  }
  return { parts, steps }
}

function buildSeq(id: string, title: string, text: string, life: Map<string, LifeInfo>): SeqSec {
  const fence = /```mermaid\n([\s\S]*?)\n```/.exec(text)
  const lead = fence ? text.slice(0, fence.index) : text
  const mermaid = fence ? fence[1] : ''
  const after = fence ? text.slice(fence.index + fence[0].length) : ''
  const { parts, steps } = parseMermaid(mermaid)
  const labels = new Map(parts.map((p) => [p.ab, p.label]))
  const rows: LifeRow[] = parts.map((p) => {
    const info = life.get(p.ab) ?? life.get(p.label.split(' ')[0]) ?? { name: '', what: '', kind: '', where: '' }
    return { ab: p.ab, label: p.label, ...info }
  })
  return {
    kind: 'seq',
    id,
    title,
    lead,
    mermaid,
    after,
    life: rows,
    steps: steps.map((s) => ({
      ...s,
      fromL: labels.get(s.from) ?? s.from,
      toL: labels.get(s.to) ?? s.to,
      ret: s.arrow.startsWith('--'),
    })),
  }
}

/** 같은 문서 참조([[#SEQ-N]])에 data-jump를 달고, 본문 텍스트의 SEQ-N 언급을 점프 링크로 (태그·링크 안은 건드리지 않는다) */
function jumpify(html: string, ids: ReadonlySet<string>, selfId: string): string {
  const withRefs = html.replace(/data-ref="([^"#]+)#(SEQ-C?\d+)"/g, (m, d: string, id: string) =>
    d === selfId && ids.has(id) ? `${m} data-jump="${id}"` : m,
  )
  let inA = 0
  return withRefs
    .split(/(<[^>]+>)/)
    .map((piece) => {
      if (piece.startsWith('<')) {
        if (/^<a[\s>]/i.test(piece)) inA++
        else if (/^<\/a>/i.test(piece)) inA = Math.max(0, inA - 1)
        return piece
      }
      if (inA > 0) return piece
      return piece.replace(SEQ_MENTION, (m, id: string) => (ids.has(id) ? `<a class="jump" data-jump="${id}">${m}</a>` : m))
    })
    .join('')
}

const elId = (s: Sec): string => (s.kind === 'seq' ? `item-${s.id}` : `sec-${s.id}`)

function seqInner(s: SeqSec, ctx: RenderCtx, J: (h: string) => string): string {
  let h = `<div class="lead">${J(renderBlocks(s.lead, ctx))}</div>`
  if (s.life.length) {
    const lifeRows = s.life
      .map(
        (l) =>
          `<tr><td class="mono">${esc(l.ab)}</td><td><b>${esc(l.label)}</b></td><td>${inline(l.what, ctx)}</td><td class="kind">${esc(l.kind)}</td><td class="soft">${inline(l.where, ctx)}</td></tr>`,
      )
      .join('')
    h += `<h3>생명선 — 이 그림에 나오는 것</h3><table class="life"><thead><tr><th>약어</th><th>이름</th><th>실체</th><th>종류</th><th>정의</th></tr></thead><tbody>${lifeRows}</tbody></table>`
  }
  if (s.mermaid) {
    let lastCtx: string | null = null
    const stepRows = s.steps
      .map((st, i) => {
        const ctxRow = st.ctx !== lastCtx ? `<tr class="ctx"><td colspan="3">${st.ctx ? esc(st.ctx) : '기본 흐름'}</td></tr>` : ''
        lastCtx = st.ctx
        const who = st.ret
          ? `${esc(st.fromL)} <span class="arr ret">⇢</span> ${esc(st.toL)}`
          : `${esc(st.fromL)} <span class="arr">→</span> ${esc(st.toL)}`
        return `${ctxRow}<tr class="${st.ret ? 'ret' : ''}" data-step="${i + 1}"><td class="no">${i + 1}</td><td class="who">${who}</td><td>${esc(st.msg)}</td></tr>`
      })
      .join('')
    h += `<h3>흐름</h3><div class="split"><div class="dia-wrap"><div class="zoom"><button type="button" data-z="-">－</button><button type="button" data-z="0">100%</button><button type="button" data-z="+">＋</button></div><div class="dia mer"><pre class="mermaid">${esc(s.mermaid)}</pre></div></div><div class="steps"><table><thead><tr><th>#</th><th>누가 → 누구</th><th>무엇</th></tr></thead><tbody>${stepRows}</tbody></table><div class="soft hint">→ 호출 · ⇢ 반환. 회색 줄은 분기(alt)·조건(opt)·반복(loop) 안이라는 뜻. 번호는 그림의 번호와 같다.</div></div></div>`
  }
  if (s.after.trim()) {
    // **읽을 때 볼 것** 문단(또는 "— …" 한 줄)을 소제목으로 승격 (seq_build의 replace)
    const after = J(renderBlocks(s.after, ctx))
      .replace(/<p><strong>읽을 때 볼 것<\/strong><\/p>/, '<h3>읽을 때 볼 것</h3>')
      .replace(/<p><strong>읽을 때 볼 것<\/strong>\s*(?:—|–|-)?\s*/, '<h3>읽을 때 볼 것</h3><p>')
    h += `<div class="after">${after}</div>`
  }
  return h
}

export const vSeq: ViewFn = ({ body, ctx }) => {
  const src = stripFm(body)
  const life = lifeMap(src)
  const pre: [string, string][] = []
  const post: [string, string][] = []
  const seqs: SeqSec[] = []
  for (const [title, text] of splitSections(src)) {
    const m = SEQ_HEAD.exec(title)
    if (m) seqs.push(buildSeq(m[1], (m[2] ?? '').trim(), trimRule(text), life))
    else (seqs.length ? post : pre).push([title, trimRule(text)])
  }
  const ids = new Set(seqs.map((s) => s.id))
  const J = (h: string): string => jumpify(h, ids, ctx.selfId)

  const secs: Sec[] = []
  if (pre.length) secs.push({ kind: 'text', id: 'overview', title: pre.length > 1 ? '개요 · 대응표' : secName(pre[0][0]), parts: pre })
  secs.push(...seqs)
  post.forEach(([t, x], i) => {
    const name = secName(t)
    const id = name.startsWith('되먹일') ? 'feedback' : name.startsWith('미결') ? 'pending' : `tail${i + 1}`
    secs.push({ kind: 'text', id, title: name, parts: [[t, x]] })
  })
  const byId = new Map(secs.map((s) => [s.id, s]))

  // 좌 목록: 개요 → 의미 묶음 → 기타 → 정리
  const navGroups: [string, Sec[]][] = []
  const overview = byId.get('overview')
  if (overview) navGroups.push(['개요', [overview]])
  const used = new Set<string>()
  for (const [g, gids] of GROUPS) {
    const list: Sec[] = []
    for (const id of gids) {
      const s = byId.get(id)
      if (s) {
        list.push(s)
        used.add(id)
      }
    }
    if (list.length) navGroups.push([g, list])
  }
  const rest = seqs.filter((s) => !used.has(s.id))
  if (rest.length) navGroups.push(['기타', rest])
  const tails = secs.filter((s) => s.kind === 'text' && s.id !== 'overview')
  if (tails.length) navGroups.push(['정리', tails])

  const nav = navGroups
    .map(
      ([g, list]) =>
        `<div class="grp">${esc(g)}</div>` +
        list
          .map((s) =>
            s.kind === 'seq'
              ? `<a href="#${elId(s)}" data-id="${esc(s.id)}"><span class="k">${esc(s.id)}</span>${inline(s.title, ctx)}</a>`
              : `<a href="#${elId(s)}" data-id="${esc(s.id)}">${esc(s.title)}</a>`,
          )
          .join(''),
    )
    .join('')

  const main = secs
    .map((s, i) => {
      const open = i === 0 ? ' open' : ''
      if (s.kind === 'seq') {
        return `<details class="seq-sec seq-item" id="${elId(s)}" data-id="${esc(s.id)}" data-item="${esc(s.id)}"${open}><summary><h2><span class="k">${esc(s.id)}</span>${inline(s.title, ctx)}</h2></summary><div class="seq-body">${seqInner(s, ctx, J)}</div></details>`
      }
      const inner = s.parts
        .map(([t, x], k) => (k ? `<h3>${esc(secName(t))}</h3>` : '') + J(renderBlocks(x, ctx)))
        .join('')
      return `<details class="seq-sec" id="${elId(s)}" data-id="${esc(s.id)}"${open}><summary><h2>${esc(s.title)}</h2></summary><div class="seq-body">${inner}</div></details>`
    })
    .join('\n')

  const html = `<div class="seqv"><nav class="seq-nav">${nav}</nav><main class="seq-main">${main}</main></div>`

  const onMount = (root: HTMLElement): (() => void) => {
    const secEls = Array.from(root.querySelectorAll<HTMLDetailsElement>('details.seq-sec'))
    const secById = new Map(secEls.map((d) => [d.dataset.id ?? '', d]))
    const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('.seq-nav a[data-id]'))
    const mark = (id: string): void => {
      for (const a of links) a.classList.toggle('sel', a.dataset.id === id)
    }
    const select = (id: string, scroll: boolean): void => {
      const d = secById.get(id)
      if (!d) return
      for (const o of secEls) if (o !== d && o.open) o.open = false
      if (!d.open) d.open = true
      mark(id)
      if (scroll) d.scrollIntoView({ block: 'start' })
    }
    const zoom = (btn: HTMLElement): void => {
      const box = btn.closest('.dia-wrap')?.querySelector<HTMLElement>('.dia')
      const svg = box?.querySelector<SVGSVGElement>('svg')
      if (!box || !svg) return
      const prev = Number(box.dataset.scale ?? '1') || 1
      const z = btn.dataset.z
      const next = z === '+' ? prev * 1.2 : z === '-' ? prev / 1.2 : 1
      const base = svg.getBoundingClientRect().height / prev
      box.dataset.scale = String(next)
      svg.style.transform = `scale(${next})`
      svg.style.transformOrigin = '0 0'
      box.style.height = next === 1 ? '' : `${base * next + 40}px`
    }
    const onClick = (e: MouseEvent): void => {
      const t = e.target
      if (!(t instanceof Element)) return
      const navA = t.closest<HTMLAnchorElement>('.seq-nav a[data-id]')
      if (navA && root.contains(navA)) {
        e.preventDefault()
        select(navA.dataset.id ?? '', true)
        return
      }
      const jump = t.closest<HTMLElement>('[data-jump]')
      if (jump && root.contains(jump) && secById.has(jump.dataset.jump ?? '')) {
        e.preventDefault()
        select(jump.dataset.jump ?? '', true)
        return
      }
      const zb = t.closest<HTMLElement>('.zoom button[data-z]')
      if (zb && root.contains(zb)) zoom(zb)
    }
    // toggle은 버블링하지 않는다 — capture로 받는다. 사용자가 summary를 눌러 열었거나 페이지가 #item-SEQ-N으로 열었을 때 나머지를 닫고 목록 표시
    const onToggle = (e: Event): void => {
      const d = e.target
      if (!(d instanceof HTMLDetailsElement) || !d.classList.contains('seq-sec') || !d.open) return
      for (const o of secEls) if (o !== d && o.open) o.open = false
      mark(d.dataset.id ?? '')
    }
    const fromHash = (): boolean => {
      let h = ''
      try {
        h = decodeURIComponent(location.hash.slice(1))
      } catch {
        h = location.hash.slice(1)
      }
      const id = h.replace(/^(?:item-|sec-)/, '')
      if (!id || !secById.has(id)) return false
      select(id, true)
      return true
    }
    root.addEventListener('click', onClick)
    root.addEventListener('toggle', onToggle, true)
    window.addEventListener('hashchange', fromHash)
    if (!fromHash()) {
      const first = secEls.find((d) => d.open) ?? secEls[0]
      if (first) mark(first.dataset.id ?? '')
    }
    return () => {
      root.removeEventListener('click', onClick)
      root.removeEventListener('toggle', onToggle, true)
      window.removeEventListener('hashchange', fromHash)
    }
  }

  return { html, onMount }
}

/** seq_build.py TPL의 <style> 중 .layout 이하 — .seqv 아래로 범위 한정 */
export const seqCss = `
.seqv{--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--panel:#F8F9F7;display:grid;grid-template-columns:250px minmax(0,1fr);border:1.5px solid var(--ink);background:#fff;min-height:60vh;font-size:14px;line-height:1.6;color:var(--ink)}
.seqv .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
.seqv .soft{color:var(--soft)}
.seqv .seq-nav{border-right:1.5px solid var(--ink);background:var(--panel);overflow-y:auto;max-height:88vh;position:sticky;top:0;align-self:start}
.seqv .seq-nav a{display:block;padding:8px 14px;font-size:13px;color:var(--ink);text-decoration:none;border-left:3px solid transparent;line-height:1.35;cursor:pointer}
.seqv .seq-nav a:hover{background:#EAEEEA}
.seqv .seq-nav a.sel{border-left-color:var(--ink);background:#fff;font-weight:600}
.seqv .seq-nav a .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}
.seqv .seq-nav .grp{padding:12px 14px 4px;font-size:11px;font-weight:700;color:var(--soft)}
.seqv .seq-main{padding:8px 30px 30px;min-width:0;overflow-x:auto}
.seqv details.seq-sec{border-bottom:1px solid var(--hair)}
.seqv details.seq-sec>summary{list-style:none;cursor:pointer;padding:10px 0;display:flex;align-items:baseline;gap:8px}
.seqv details.seq-sec>summary::-webkit-details-marker{display:none}
.seqv details.seq-sec>summary::before{content:"▸";color:var(--faint);font-size:12px;flex:none}
.seqv details.seq-sec[open]>summary::before{content:"▾"}
.seqv details.seq-sec>summary h2{margin:0;font-size:15px;font-weight:600;letter-spacing:-.01em;border:none;padding:0}
.seqv details.seq-sec[open]>summary h2{font-size:22px;font-weight:700}
.seqv details.seq-sec>summary h2 .k{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--faint);margin-right:8px;font-weight:500}
.seqv .seq-body{padding:4px 0 26px}
.seqv .seq-body h3{font-size:15px;margin:26px 0 10px;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}
.seqv .seq-body h4{font-size:13.5px;margin:20px 0 8px;color:var(--soft)}
.seqv .lead{color:var(--soft);margin-bottom:14px}
.seqv .lead p{margin:0 0 6px}
.seqv .dia{border:1px solid var(--rule);background:#fff;padding:14px;margin:12px 0 20px;overflow:auto}
.seqv .dia svg{display:block;max-width:none}
.seqv .dia pre.mermaid{margin:0;font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;background:none}
.seqv .dia pre.mermaid[data-processed]{white-space:normal}
.seqv .zoom{display:flex;gap:6px;justify-content:flex-end;margin-bottom:-6px;position:relative;z-index:1}
.seqv .zoom button{font:inherit;font-size:12px;padding:3px 9px;border:1px solid var(--rule);background:var(--panel);cursor:pointer}
.seqv .split{display:grid;grid-template-columns:minmax(520px,1.4fr) minmax(360px,1fr);gap:16px;align-items:start}
.seqv .dia-wrap{min-width:0}
.seqv .steps{position:sticky;top:12px;max-height:82vh;overflow-y:auto}
.seqv .steps table{font-size:12.5px;margin:0}
.seqv .steps td.no{font-family:ui-monospace,Menlo,monospace;color:var(--faint);width:1%;white-space:nowrap}
.seqv .steps td.who{white-space:nowrap;font-weight:600}
.seqv .steps .arr{color:var(--soft);font-weight:400;margin:0 3px}
.seqv .steps .arr.ret{color:#1a5fb4}
.seqv .steps tr.ret td{color:var(--soft)}
.seqv .steps tr.ctx td{background:#EEF0EC;color:var(--soft);font-size:11.5px;font-weight:600;padding:5px 9px}
.seqv .steps .hint{font-size:12px;margin-top:6px}
.seqv table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 14px;background:#fff}
.seqv th{text-align:left;font-weight:600;color:var(--soft);padding:7px 9px;border-bottom:1.5px solid var(--ink);background:var(--panel);white-space:nowrap}
.seqv td{padding:7px 9px;border-bottom:1px solid var(--hair);vertical-align:top}
.seqv table.life td.kind{white-space:nowrap;color:var(--soft)}
.seqv .after h4,.seqv .after p{margin-top:8px}
.seqv a.jump{color:#1a5fb4;cursor:pointer;border-bottom:1px dashed #1a5fb4;font-family:ui-monospace,Menlo,monospace;font-size:.92em;text-decoration:none}
.seqv a.ref[data-jump]{cursor:pointer}
@media (max-width:1200px){.seqv .split{grid-template-columns:1fr}.seqv .steps{position:static;max-height:none}}
@media (max-width:900px){.seqv{grid-template-columns:1fr}.seqv .seq-nav{position:static;max-height:220px;border-right:none;border-bottom:1.5px solid var(--ink)}}
`
