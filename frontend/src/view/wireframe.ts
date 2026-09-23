/** V-UI — 화면 문서 렌더러 하나 (STD-002 V-UI, 카드 X). tools/wf_build.py 포트.
 *  화면 항목 `UI-N`은 헤딩 단계와 무관하다(`## UI-N`·`#### UI-N`·… 전부). 화면마다 **html 코드블록 유무로 갈린다** —
 *  있으면 상단 화면 탭 + 좌 배치 뼈대 / 우 요소 표·규칙·시나리오(우측 셋이 다 비면 좌측 전폭), 없으면 화면 설계 표 한 행.
 *  항목 블록 안 조각은 소제목의 단계·문자열에 매이지 않는다: 배치 = 첫 ```html, 메타 표 = html 앞 첫 표,
 *  요소·규칙·시나리오 = `#… 요소`·`#… 규칙`·`#… 시나리오` 소제목 뒤. 화면이 아닌 절(0장·대응표·공통 틀·흐름·미결)은 순서대로 함께 그린다.
 *  뼈대의 `data-el` 번호와 요소 표의 `#` 열이 같은 번호라 클릭하면 양쪽이 서로 강조된다.
 *  배치는 iframe(srcdoc)에 격리해 그린다(frame.ts, 카드 Z) — 사이트 CSS가 안 스며들고 문서의 <style>·<link>가 그대로 산다. data-el은 그대로.
 *  「공통 틀」 절의 첫 html 블록은 이 문서 모든 화면 앞에 함께 들어간다.
 *  wf_build.py는 DATA json + script로 런타임에 그렸지만 여기서는 HTML을 정적으로 만들고 onMount가 탭·연동만 붙인다. */
import { commonBlock, frameHtml, hiIn, mountFrames, remeasure, safeLayout, splitCommon, type CommonParts } from './frame'
import { esc, etcBlock, h2, inline, leadRest, renderBlocks, type ItemBlock, type RenderCtx } from './md'
import { ITEM_PAT, type ViewFn } from './types'
import { itemCard } from './views'

export interface WfScenario {
  id: string
  title: string
  uc: string
  /** 단계마다 원본 줄 — 첫 줄이 번호 줄, 뒤는 이어진 줄 */
  steps: string[][]
}
export interface WfScreen {
  id: string
  name: string
  /** 화면 블록 원문(헤딩 줄 뺀 것). 설계만 있는 화면은 이것이 카드 몸이다 */
  text: string
  meta: [string, string][]
  /** 머리 중 메타 표를 뺀 원문 — 한 줄 목적 자리. renderBlocks로 그린다 */
  desc: string
  /** 첫 ```html 블록. 없으면 null — 그 화면은 카드로 간다 */
  layout: string | null
  /** 요소 소절의 첫 표 — 문서의 머리 행·칸 그대로 */
  elems: { header: string[]; rows: string[][] }
  /** 규칙마다 원본 줄 — 첫 줄이 `- `, 뒤는 이어진 줄 */
  rules: string[][]
  scenarios: WfScenario[]
  /** 어느 조각에도 쓰이지 않은 줄(원본 순서) — 화면 끝 「그 밖」 */
  etc: string[]
}

// ───────────────────────── 파싱 ─────────────────────────

const KNOWN = ['배치', '요소', '규칙', '시나리오']
const HEAD_LINE = /^#{1,6} (.+?)\s*$/
const SCEN_HEAD = /^\*\*(S-\d+) (.+?)\*\*(.*)$/
const STEP = /^(\s*\d+\.\s+)/

/** wf_build._cells — 앞뒤 `|`를 전부 떼고 칸으로 */
const cells = (line: string): string[] =>
  line
    .trim()
    .replace(/^\|+|\|+$/g, '')
    .split('|')
    .map((c) => c.trim())

const isSep = (r: string[]) => r.every((c) => /^[-: ]*$/.test(c))

/** wf_build._fences — 줄마다 펜스 줄(여는·안·닫는)인가, [여는 줄, 닫는 줄, 언어]. 안 닫힌 펜스는 끝까지 */
export function fences(lines: string[]): [boolean[], [number, number, string][]] {
  const flags = lines.map(() => false)
  const spans: [number, number, string][] = []
  let openAt = -1
  let lang = ''
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trimStart().startsWith('```')) {
      if (openAt < 0) {
        openAt = i
        lang = lines[i].trim().slice(3).trim()
      } else {
        spans.push([openAt, i, lang])
        openAt = -1
      }
      flags[i] = true
    } else if (openAt >= 0) flags[i] = true
  }
  if (openAt >= 0) spans.push([openAt, lines.length - 1, lang])
  return [flags, spans]
}

/** wf_build._first_table — [start, end)의 첫 표 → [행들(구분선 제외), 시작 줄, 끝 줄(제외)] */
export function firstTable(lines: string[], fenced: boolean[], start: number, end: number): [string[][], number, number] {
  for (let i = start; i < end; i++) {
    if (fenced[i] || !lines[i].trim().startsWith('|')) continue
    const rows: string[][] = []
    let j = i
    while (j < end && !fenced[j] && lines[j].trim().startsWith('|')) {
      const r = cells(lines[j])
      if (!isSep(r)) rows.push(r)
      j++
    }
    return [rows, i, j]
  }
  return [[], -1, -1]
}

/** wf_build._items — [start, end) → 항목마다 줄 번호 목록. isHead인 줄이 새 항목이고 빈 줄 없이 이어진 줄·들여 쓴 줄·빈 줄은
 *  그 항목 안(V-SCN 단계와 같은 규칙, #152). 코드 펜스는 여는 줄이 든 자리를 따른다. heads인 줄에서 항목이 끊긴다 —
 *  [그 줄, 그 뒤 첫 항목 번호]를 marks로 돌려준다(시나리오 머리) */
function items(lines: string[], start: number, end: number, isHead: (l: string) => boolean, heads?: (l: string) => boolean): [number[][], [number, number][]] {
  const out: number[][] = []
  const marks: [number, number][] = []
  let cur: number[] | null = null
  let into: number[] | null = null
  let blank = false
  let fence = false
  for (let i = start; i < end; i++) {
    const l = lines[i]
    if (fence) {
      if (into) into.push(i)
      fence = !l.trimStart().startsWith('```')
      continue
    }
    if (heads && heads(l)) {
      marks.push([i, out.length])
      cur = into = null
    } else if (isHead(l)) {
      cur = [i]
      out.push(cur)
      into = cur
    } else if (cur && (!l.trim() || l[0] === ' ' || l[0] === '\t' || !blank)) {
      cur.push(i)
      into = cur
    } else cur = into = null
    fence = l.trimStart().startsWith('```')
    blank = !l.trim()
  }
  return [out, marks]
}

/** wf_build.parse_screen — 화면 블록 하나(헤딩 줄을 뺀 본문)를 줄 단위로 가른다 (STD-002 V-UI, #152).
 *  머리 = 첫 소제목·배치 전(행이 전부 두 칸인 첫 표는 메타, 나머지는 한 줄 목적). 배치 = 첫 html 펜스. 소제목은 이름
 *  (「배치」「요소」「규칙」「시나리오」, 이름마다 처음 것)으로 찾는다. 어디에도 쓰이지 않은 줄은 원본 순서대로 etc(「그 밖」) */
export function parseScreen(id: string, name: string, text: string): WfScreen {
  const lines = text.split('\n')
  const n = lines.length
  const [fenced, spans] = fences(lines)
  const used = new Set<number>()
  const mark = (from: number, to: number) => {
    for (let k = from; k < to; k++) used.add(k)
  }
  let layout: string | null = null
  let layAt = n
  const html = spans.find(([, , lang]) => lang === 'html')
  if (html) {
    layout = safeLayout(lines.slice(html[0] + 1, html[1]).join('\n'))
    layAt = html[0]
    mark(html[0], html[1] + 1)
  }
  const heads: number[] = []
  for (let i = 0; i < n; i++) if (!fenced[i] && HEAD_LINE.test(lines[i])) heads.push(i)
  const headEnd = Math.min(layAt, heads.length ? heads[0] : n)
  let meta: [string, string][] = []
  const [mrows, ma, mb] = firstTable(lines, fenced, 0, headEnd)
  if (mrows.length >= 2 && mrows.every((r) => r.length === 2)) {
    meta = mrows.slice(1).map((r): [string, string] => [r[0], r[1]])
    mark(ma, mb)
  }
  const desc = lines.filter((_, i) => i < headEnd && !used.has(i)).join('\n')
  mark(0, headEnd)
  let elems: WfScreen['elems'] = { header: [], rows: [] }
  let rules: string[][] = []
  const scenarios: WfScenario[] = []
  const seen = new Set<string>()
  heads.forEach((h, k) => {
    const nm = HEAD_LINE.exec(lines[h])![1].trim()
    if (!KNOWN.includes(nm) || seen.has(nm)) return // 모르는 소절은 제목째 그 밖
    seen.add(nm)
    used.add(h)
    const stop = k + 1 < heads.length ? heads[k + 1] : n
    if (nm === '요소') {
      const [rows, a, b] = firstTable(lines, fenced, h + 1, stop)
      if (rows.length >= 2) {
        elems = { header: rows[0], rows: rows.slice(1) }
        mark(a, b)
      }
    } else if (nm === '규칙') {
      const [its] = items(lines, h + 1, stop, (l) => l.startsWith('- '))
      rules = its.map((it) => it.map((x) => lines[x]))
      its.forEach((it) => it.forEach((x) => used.add(x)))
    } else if (nm === '시나리오') {
      const [its, marks] = items(lines, h + 1, stop, (l) => STEP.test(l), (l) => SCEN_HEAD.test(l))
      marks.forEach(([i, first], j) => {
        const m = SCEN_HEAD.exec(lines[i])!
        const steps = its.slice(first, j + 1 < marks.length ? marks[j + 1][1] : its.length)
        scenarios.push({ id: m[1], title: m[2], uc: m[3].replace(/^\s*[—–\-.·:]*\s*/, '').trim(), steps: steps.map((st) => st.map((x) => lines[x])) })
        used.add(i)
        steps.forEach((st) => st.forEach((x) => used.add(x)))
      })
    }
  })
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
  return { id, name, text, meta, desc, layout, elems, rules, scenarios, etc }
}

/** 본문 전체 → 화면(html 있는 것만, 문서 순서). 검사·다른 도구용 — 뷰는 vUi가 절 순서대로 그린다 */
export function parseWireframe(body: string): WfScreen[] {
  const out: WfScreen[] = []
  for (const seg of segments(body)) if (seg.kind === 'item') out.push(parseScreen(seg.block.id, seg.block.title, seg.block.text))
  return out.filter((s) => s.layout !== null)
}

type Segment = { kind: 'prose'; text: string } | { kind: 'item'; block: ItemBlock }

/** 본문을 산문 조각과 화면 항목 블록으로 자른다(문서 순서). 헤딩 단계 무관 — `## UI-N`도 `##### UI-N`도 항목이다.
 *  블록은 같은 단계 이상 헤딩 전까지(md.itemBlocks와 같은 규칙). 코드 펜스 안 `#`은 헤딩이 아니다 */
function segments(text: string): Segment[] {
  const lines = text.split('\n')
  const out: Segment[] = []
  let prose: string[] = []
  let inFence = false
  const flush = () => {
    if (prose.some((l) => l.trim())) out.push({ kind: 'prose', text: prose.join('\n') })
    prose = []
  }
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (/^\s*```/.test(l)) inFence = !inFence
    const h = inFence ? null : /^(#{1,6}) (UI-\d+)(?: (.*))?$/.exec(l)
    if (!h) {
      prose.push(l)
      i++
      continue
    }
    flush()
    const lvl = h[1].length
    let j = i + 1
    let fence = false
    while (j < lines.length) {
      if (/^\s*```/.test(lines[j])) fence = !fence
      const h2 = fence ? null : /^(#{1,6}) /.exec(lines[j])
      if (h2 && h2[1].length <= lvl) break
      j++
    }
    out.push({ kind: 'item', block: { id: h[2], title: h[3] ?? '', level: lvl, text: lines.slice(i + 1, j).join('\n') } })
    i = j
  }
  flush()
  return out
}

// ───────────────────────── HTML ─────────────────────────

/** wf_build._chip — 글자 속 "(7.1)" 같은 요소 번호를 누를 수 있는 칩으로. 태그 속성은 건드리지 않는다 — 규칙·단계의
 *  이어진 줄에도 붙이고, 링크 주소 속 "(1)"은 깨지 않게 (#152) */
const chip = (h: string): string =>
  `>${h}<`
    .replace(/>([^<]+)</g, (_m, t: string) => '>' + t.replace(/\((\d+(?:\.\d+)?[a-z]?)\)/g, '(<span class="eref" data-ref="$1">$1</span>)') + '<')
    .slice(1, -1)

/** wf_build._item_html — 규칙 하나·시나리오 단계 하나: 첫 문단은 칩을 붙여 그 자리, 이어진 줄은 그 아래 (#152) */
const itemHtml = (lines: string[], width: number, ctx: RenderCtx): string => {
  const [lead, rest] = leadRest(lines[0].slice(width).trim(), lines.slice(1), width)
  return chip(inline(lead, ctx) + renderBlocks(rest, ctx))
}

/** wf_build._screen_html — 정적 뷰와 같은 HTML(카드 AL). 배치가 위, 요소 표·규칙·시나리오·「그 밖」이 아래 */
function screenHtml(s: WfScreen, i: number, ctx: RenderCtx, common: CommonParts): string {
  const meta = s.meta.map(([k, v]) => `<span><b>${esc(k)}</b>${inline(v, ctx)}</span>`).join('')
  const d = renderBlocks(s.desc, ctx)
  const desc = d ? `<div class="s-desc">${d}</div>` : ''
  const right: string[] = []
  const { header, rows } = s.elems
  if (rows.length) {
    // 문서가 쓴 머리 행·칸 그대로 — 다섯 칸으로 고정해 칸 모자란 행을 버리던 것(#152). 「종류」 칸만 좁게
    const kind = header.map((c) => c === '종류')
    const td = (j: number, c: string) => (j < kind.length && kind[j] ? `<td class="kind">${inline(c, ctx)}</td>` : `<td>${inline(c, ctx)}</td>`)
    const th = header.map((c) => `<th>${inline(c, ctx)}</th>`).join('')
    const tb = rows
      .map((r) => `<tr data-wf-row="${esc(r[0])}"><td class="no">${esc(r[0])}</td>` + r.slice(1).map((c, j) => td(j + 1, c)).join('') + '</tr>')
      .join('')
    right.push(`<div class="rsec"><h3>요소</h3><table class="el"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`)
  }
  if (s.rules.length) right.push('<div class="rsec"><h3>규칙</h3><ul class="rules">' + s.rules.map((r) => `<li>${itemHtml(r, 2, ctx)}</li>`).join('') + '</ul></div>')
  if (s.scenarios.length) {
    const scen = s.scenarios
      .map(
        (x) =>
          `<div class="scen"><div class="st"><span class="k">${esc(x.id)}</span>${inline(x.title, ctx)}` +
          (x.uc ? `<span class="uc">— ${inline(x.uc, ctx)}</span>` : '') +
          '</div><ol>' +
          x.steps.map((st) => `<li>${itemHtml(st, STEP.exec(st[0])![1].length, ctx)}</li>`).join('') +
          '</ol></div>',
      )
      .join('')
    right.push(`<div class="rsec"><h3>시나리오</h3>${scen}</div>`)
  }
  // 조각에 안 맞는 줄은 아래 판 끝 「그 밖」 — 둘째 html 블록은 공통 틀과 함께 (STD-002 V-UI, #152)
  right.push(etcBlock(s.etc, { ...ctx, common }))
  let inner = frameHtml(s.layout ?? '', common, ctx.assetBase ?? '')
  if (right.join('')) inner += `<div class="rsecs">${right.join('')}</div>`
  return `<section class="screen" id="item-${esc(s.id)}" data-item="${esc(s.id)}" data-i="${i}"${i === 0 ? '' : ' style="display:none"'}><div class="s-head"><b>${esc(s.id)} ${esc(s.name)}</b>${meta}</div>${desc}<div class="wfstack">${inner}</div></section>`
}

/** `## 절` 단위 → [제목, 본문]. md.splitSections와 같되 코드 펜스 안 `## `은 절이 아니다 —
 *  와이어프레임 html 예시에 마크다운 제목이 들어 있어(TBL·SYNC-UI-002) 거기서 갈리면 펜스 짝이 어긋난다 */
function sections(body: string): [string, string][] {
  const out: [string, string][] = []
  let title: string | null = null
  let buf: string[] = []
  let inFence = false
  for (const l of body.split('\n')) {
    if (/^\s*```/.test(l)) inFence = !inFence
    if (!inFence && l.startsWith('## ')) {
      if (title !== null) out.push([title, buf.join('\n')])
      title = l.slice(3).trim()
      buf = []
      continue
    }
    if (title !== null) buf.push(l)
  }
  if (title !== null) out.push([title, buf.join('\n')])
  return out
}

/** wf_build._design_cards — 배치가 없는 화면은 화면마다 카드: 머리 ID·이름·하위 N, 몸은 블록 전부, 바닥 「이 화면을 근거로 삼은
 *  문서」. 전에는 표 한 행에 첫 줄만 실려 나머지가 사라졌다 (STD-002 V-UI, #152). 종류·유스케이스는 머리로 뽑지 않는다 */
const designCards = (screens: WfScreen[], ctx: RenderCtx): string =>
  screens.map((s) => itemCard(ctx, { id: s.id, title: s.name, level: 0, text: s.text }, renderBlocks(s.text, ctx), '이 화면을 근거로 삼은 문서')).join('')

/** wf_build._group_html — 이어진 화면 항목 묶음 하나(.wfgroup) = 카드(배치 없는 화면) + 탭 줄·화면들(배치 있는 화면).
 *  묶음 안은 번호순, 묶음(절) 순서는 문서 순서. 문서에 묶음이 여럿일 수 있다(TBL식 「2.1 C 리포트 / 2.2 A 리포트」) */
function renderRun(blocks: ItemBlock[], ctx: RenderCtx, common: CommonParts): string {
  const screens = blocks.map((b) => parseScreen(b.id, b.title, b.text)).sort((a, b) => Number(a.id.split('-')[1]) - Number(b.id.split('-')[1]))
  const plain = screens.filter((s) => s.layout === null)
  const wired = screens.filter((s) => s.layout !== null)
  const out: string[] = []
  if (plain.length) out.push(designCards(plain, ctx))
  if (wired.length) {
    const tabs = wired.map((s, i) => `<button type="button" role="tab" aria-selected="${i === 0}" data-i="${i}"><span class="k">${esc(s.id)}</span>${esc(s.name)}</button>`).join('')
    out.push(`<div class="stabs" role="tablist">${tabs}</div><div class="screens">${wired.map((s, i) => screenHtml(s, i, ctx, common)).join('')}</div>`)
  }
  return `<div class="wfgroup">${out.join('')}</div>`
}

/** 절 본문 → 산문은 그대로, 화면 항목 묶음은 카드·탭으로. 항목이 절 자체(`## UI-N`)인 경우는 vUi가 모은다 */
function renderSection(text: string, ctx: RenderCtx, common: CommonParts): string {
  const out: string[] = []
  let run: ItemBlock[] = []
  const flush = () => {
    if (run.length) out.push(renderRun(run, ctx, common))
    run = []
  }
  for (const seg of segments(text)) {
    if (seg.kind === 'item') run.push(seg.block)
    else {
      flush()
      out.push(renderBlocks(seg.text, ctx, ITEM_PAT.UI))
    }
  }
  flush()
  return out.join('\n')
}

// ───────────────────────── 동작 (wf_build.py script) ─────────────────────────

const attrQ = (v: string) => v.replace(/["\\]/g, '\\$&')

/** 탭 전환 + 요소 번호 양쪽 강조. 묶음(.wfgroup)마다 따로 돈다. root에 위임해 정리 함수로 뗀다.
 *  배치 안 요소는 iframe 문서 안에 있다 — 강조·클릭은 frame.ts(hiIn·mountFrames)를 거친다 */
export function mountWireframe(root: HTMLElement): () => void {
  const groups = (): HTMLElement[] => Array.from(root.querySelectorAll<HTMLElement>('.wfgroup'))
  const tabsOf = (g: HTMLElement): HTMLButtonElement[] => Array.from(g.querySelectorAll<HTMLButtonElement>(':scope > .stabs > button'))
  const screensOf = (g: HTMLElement): HTMLElement[] => Array.from(g.querySelectorAll<HTMLElement>(':scope > .screens > section.screen'))

  const show = (g: HTMLElement, i: number) => {
    tabsOf(g).forEach((b, j) => b.setAttribute('aria-selected', String(i === j)))
    screensOf(g).forEach((s, j) => (s.style.display = i === j ? '' : 'none'))
    remeasure(g) // 숨겨 있던 화면은 0으로 재졌다 — 열리면 다시
  }
  const hi = (sec: HTMLElement, no: string) => {
    sec.querySelectorAll('[data-wf-row].hi').forEach((n) => n.classList.remove('hi'))
    const frame = sec.querySelector<HTMLIFrameElement>('iframe.wfframe-if')
    if (frame) hiIn(frame, no)
    const row = sec.querySelector<HTMLElement>(`[data-wf-row="${attrQ(no)}"]`)
    if (row) {
      row.classList.add('hi')
      row.scrollIntoView({ block: 'nearest' })
    }
  }

  const onClick = (e: MouseEvent) => {
    const t = e.target
    if (!(t instanceof Element)) return
    const tab = t.closest<HTMLButtonElement>('.stabs > button')
    const g = tab?.closest<HTMLElement>('.wfgroup')
    if (tab && g && root.contains(tab)) {
      show(g, Number(tab.dataset.i))
      return
    }
    const sec = t.closest<HTMLElement>('section.screen')
    if (!sec || !root.contains(sec)) return
    const row = t.closest<HTMLElement>('[data-wf-row]')
    if (row && sec.contains(row)) {
      hi(sec, row.dataset.wfRow ?? '')
      return
    }
    const ref = t.closest<HTMLElement>('.eref')
    if (ref && sec.contains(ref)) hi(sec, ref.dataset.ref ?? '')
  }
  root.addEventListener('click', onClick)

  // iframe 안 클릭 → 표 행 강조 (frame.ts가 iframe 쪽 강조는 이미 했다)
  const unmountFrames = mountFrames(root, (no, frame) => {
    const sec = frame.closest<HTMLElement>('section.screen')
    if (!sec) return
    sec.querySelectorAll('[data-wf-row].hi').forEach((n) => n.classList.remove('hi'))
    const row = sec.querySelector<HTMLElement>(`[data-wf-row="${attrQ(no)}"]`)
    if (row) {
      row.classList.add('hi')
      row.scrollIntoView({ block: 'nearest' })
    }
  })

  // #item-UI-N 으로 들어오면 그 화면 탭을 연다 (숨긴 section은 스크롤할 수 없으므로)
  const openHash = () => {
    const m = /^#item-(UI-\d+)$/.exec(location.hash)
    if (!m) return
    for (const g of groups()) {
      const i = screensOf(g).findIndex((s) => s.dataset.item === m[1])
      if (i >= 0) {
        show(g, i)
        return
      }
    }
  }
  openHash()
  window.addEventListener('hashchange', openHash)

  return () => {
    root.removeEventListener('click', onClick)
    window.removeEventListener('hashchange', openHash)
    unmountFrames()
  }
}

/** V-UI 렌더러 하나. `## UI-N` 절이 이어지면 한 묶음, 다른 절은 제목 + 안의 화면 항목을 자리에서 표·탭으로 */
export const vUi: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  // 「공통 틀」 절의 첫 html 블록 — 스타일·링크는 head, 마크업은 body 앞. 모든 화면 iframe에 함께 들어간다
  const common = splitCommon(commonBlock(body))
  let run: ItemBlock[] = []
  const flush = () => {
    if (run.length) out.push(renderRun(run, ctx, common))
    run = []
  }
  for (const [title, text] of sections(body)) {
    const m = /^(UI-\d+)(?:\s+(.*))?$/.exec(title)
    if (m) {
      run.push({ id: m[1], title: m[2] ?? '', level: 2, text })
      continue
    }
    flush()
    out.push(h2(title) + renderSection(text, ctx, common))
  }
  flush()
  return { html: out.join('\n'), onMount: mountWireframe }
}

// ───────────────────────── CSS (wf_build.py <style>) ─────────────────────────
// view_build.py가 하듯 .wrap{max-width:1560px…}는 뺐다. header·body·footer는 페이지 틀이 맡으므로 함께 뺐다.
// 배치(뼈대) 스타일은 여기 없다 — 문서가 자기 완결 html로 들고 오고 iframe 안에서만 산다(카드 Z). 배지·강조는 frame.ts FRAME_CSS.

export const wireframeCss = `
/* 스코프 없이 :root 를 쓰면 이 CSS가 body 안 <style>로 주입될 때 문서 전체를 이긴다.
   와이어프레임이 뿜는 루트는 형제 둘(.stabs · .screens)이라 셀렉터도 둘이다. */
.stabs,.screens{--paper:#EDEFEC;--panel:#F8F9F7;--card:#fff;--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--hi:#FFF1B8;--hi-b:#C9A800}
.stabs .mono,.screens .mono{font-family:ui-monospace,Menlo,Consolas,monospace}

.stabs{display:flex;flex-wrap:wrap;margin-top:22px;border:1.5px solid var(--ink);border-bottom:none;background:var(--panel)}
.stabs button{font:inherit;font-size:13.5px;padding:10px 16px;background:none;border:none;border-right:1px solid var(--rule);cursor:pointer;color:var(--soft);position:relative}
.stabs button[aria-selected=true]{background:var(--card);color:var(--ink);font-weight:700}
.stabs button[aria-selected=true]::after{content:"";position:absolute;left:0;right:0;bottom:-1.5px;height:3px;background:var(--ink)}
.stabs .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}

.screen{border:1.5px solid var(--ink);background:var(--card)}
.s-head{display:flex;gap:18px;flex-wrap:wrap;padding:12px 18px;border-bottom:1.5px solid var(--ink);background:var(--panel);font-size:13px}
.s-head b{font-size:16px;margin-right:6px}
.s-head span{color:var(--soft)}
.s-head span b{font-size:13px;color:var(--ink);font-weight:600;margin-right:4px}
.s-desc{padding:8px 18px;border-bottom:1px solid var(--hair);font-size:13px;color:var(--soft)}
.s-desc p{margin:2px 0}
.wfgroup{margin-bottom:22px}
/* 배치가 위, 요소 표·규칙·시나리오가 아래 (카드 AC, #134) — 좌우로 나누면 배치가 본문의 절반만 받아
   1280 아트보드가 늘 60%로 줄어 보였다. 세로로 쌓으면 본문 폭을 다 쓴다 */
.wfstack{padding:18px;background:#F2F3F0}
.rsecs{margin-top:14px;background:var(--card);border:1px solid var(--rule)}

/* 배치 틀 — 도구 줄 + iframe. 정적 뷰(wf_build.py)와 같아야 한다 */
.wfbox{margin:8px 0}
.wfbar{display:flex;align-items:center;gap:8px;padding:0 0 6px;font-size:11.5px;color:var(--soft)}
.wfbar .grow{flex:1}
.wfbar .wfdim{font-family:ui-monospace,Menlo,monospace}
.wfbar button{font:inherit;font-size:11.5px;padding:3px 9px;background:var(--card);border:1px solid var(--rule);border-radius:2px;cursor:pointer;color:var(--ink)}
.wfbar button:hover{border-color:var(--ink)}
.wfframe{position:relative;overflow:auto;background:var(--card);border:1px solid var(--rule)}
.wfframe-if{border:0;display:block;width:100%}
.wfframe.scaled{overflow:hidden}
.wfframe.scaled .wfframe-if{position:absolute;left:0;top:0}

/* 아래 */
.rsec{padding:16px 20px}
.rsec+.rsec{border-top:1px solid var(--hair)}
/* 「그 밖」 — 아래 판 끝. 점선은 .etc(뷰 CSS)가 긋는다 (#152) */
.rsecs>.etc{margin:0;padding:12px 20px 16px}
.rsec h3{margin:0 0 10px;font-size:13px;font-weight:700;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}
table.el{border-collapse:collapse;width:100%;font-size:12.5px}
table.el th{text-align:left;font-weight:600;color:var(--soft);padding:6px 8px;border-bottom:1.5px solid var(--ink);background:var(--panel)}
table.el td{padding:7px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
table.el tr{cursor:pointer}
table.el tr:hover td{background:#F2F4F1}
table.el tr.hi td{background:var(--hi)}
table.el td.no{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;white-space:nowrap;width:1%}
table.el td.kind{color:var(--soft);white-space:nowrap}
.rules{margin:0;padding-left:18px;font-size:13px;line-height:1.75}
.scen{margin-bottom:14px}
.scen .st{font-weight:700;font-size:13.5px}
.scen .st .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}
.scen .uc{font-size:11.5px;color:var(--soft);margin-left:6px;font-weight:400}
.scen ol{margin:4px 0 0;padding-left:22px;font-size:13px;line-height:1.7}
.scen ol li span.eref{font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#EEF0EC;padding:0 5px;border-radius:2px;cursor:pointer;border:1px solid var(--hair)}
.scen ol li span.eref:hover{border-color:var(--ink)}

/* 정적 뷰의 전체보기 층 — 앱은 React가 그린다(UI-5 7.6). 규칙을 한 곳에 두려고 같이 산다 */
.wffull-layer{position:fixed;inset:0;z-index:2147483100;display:flex;flex-direction:column;background:var(--card)}
.wffull-layer .gbar{display:flex;align-items:center;gap:10px;padding:8px 14px;border-bottom:1.5px solid var(--ink);background:var(--panel);font-size:12.5px}
.wffull-layer .gbar .grow{flex:1}
.wffull-layer .gbar button{font:inherit;font-size:12px;padding:4px 10px;background:var(--card);border:1px solid var(--rule);cursor:pointer}
.wffull-layer .stage{flex:1;min-height:0;overflow:auto;padding:22px;background:#F2F3F0}
.wffull-layer .pic{margin:0 auto;background:var(--card);border:1px solid var(--rule);position:relative;overflow:hidden}
.wffull-layer .pic iframe{border:0;display:block;position:absolute;left:0;top:0;transform-origin:0 0}
`
