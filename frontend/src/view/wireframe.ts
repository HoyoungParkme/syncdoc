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
import { esc, h2, inline, renderBlocks, type ItemBlock, type RenderCtx } from './md'
import { ITEM_PAT, type ViewFn } from './types'
import { downsWith, refLink } from './views'

export interface WfElem {
  no: string
  name: string
  kind: string
  shows: string
  onclick: string
}
export interface WfScenario {
  id: string
  title: string
  uc: string
  steps: string[]
}
export interface WfScreen {
  id: string
  name: string
  /** 메타 표 앞·뒤의 산문(TBL·VA식 「페이지. 목적. 주 유스케이스: …」). 없으면 '' */
  desc: string
  meta: [string, string][]
  /** 첫 ```html 코드블록. 없으면 '' — 그 화면은 설계 표 한 행으로 간다 */
  layout: string
  elems: WfElem[]
  rules: string[]
  scenarios: WfScenario[]
}

// ───────────────────────── 파싱 ─────────────────────────

const cells = (line: string): string[] =>
  line
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())

const isSep = (r: string[]) => r.every((c) => /^[-: ]*$/.test(c))

/** 코드 펜스 안 줄을 같은 길이의 공백으로 가린다(길이·줄 수 유지 — 가린 문자열의 index가 원문 index다).
 *  헤딩·표를 찾을 때 코드 안 `#`·`|`에 속지 않게 */
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

/** `#… 이름` 소제목(단계 무관) 뒤 ~ 다음 헤딩(단계 무관) 앞. 없으면 '' */
function subSection(text: string, name: string): string {
  const masked = maskFences(text)
  const re = new RegExp(`^#{1,6} ${name}\\s*$`, 'm')
  const m = re.exec(masked)
  if (!m) return ''
  const from = m.index + m[0].length
  const next = /^#{1,6} /m.exec(masked.slice(from))
  return text.slice(from, next ? from + next.index : undefined)
}

/** 표 한 장(첫 것) → 행들(구분선 제외). 표가 없으면 [] */
function firstTable(text: string): string[][] {
  const lines = maskFences(text).split('\n')
  const i = lines.findIndex((l) => l.trim().startsWith('|'))
  if (i < 0) return []
  const rows: string[][] = []
  for (let j = i; j < lines.length && lines[j].trim().startsWith('|'); j++) rows.push(cells(lines[j]))
  return rows.filter((r) => !isSep(r))
}

/** 항목 블록(헤딩 다음 줄부터) → 화면. 소제목 단계·문자열에 매이지 않는다 */
export function parseScreen(id: string, name: string, text: string): WfScreen {
  const lm = /```html\n([\s\S]*?)\n```/.exec(text)
  const layout = lm ? safeLayout(lm[1]) : ''
  const before = lm ? text.slice(0, lm.index) : text

  // 메타 표 = html 앞의 첫 표(헤더 행은 뺀다). 산문 = html 앞의 표·헤딩 아닌 줄
  const meta: [string, string][] = []
  for (const r of firstTable(before).slice(1)) if (r.length >= 2) meta.push([r[0], r[1]])
  const desc = maskFences(before)
    .split('\n')
    .filter((l) => l.trim() && !l.trim().startsWith('|') && !/^#{1,6} /.test(l))
    .map((l) => l.trim())
    .join(' ')

  const elems: WfElem[] = []
  for (const r of firstTable(subSection(text, '요소')).slice(1))
    if (r.length >= 5) elems.push({ no: r[0], name: r[1], kind: r[2], shows: r[3], onclick: r[4] })

  const rules = subSection(text, '규칙')
    .split('\n')
    .filter((l) => l.startsWith('- '))
    .map((l) => l.slice(2).trim())

  const scenarios: WfScenario[] = []
  for (const chunk of subSection(text, '시나리오').trim().split(/\n(?=\*\*S-\d+)/)) {
    const m = /^\*\*(S-\d+) (.+?)\*\*(?: — (.+))?\n/.exec(chunk + '\n')
    if (!m) continue
    const steps = chunk
      .split('\n')
      .slice(1)
      .filter((l) => /^\d+\./.test(l.trim()))
      .map((l) => l.trim().replace(/^\d+\.\s*/, ''))
    scenarios.push({ id: m[1], title: m[2], uc: m[3] ?? '', steps })
  }

  return { id, name, desc, meta, layout, elems, rules, scenarios }
}

/** 본문 전체 → 화면(html 있는 것만, 문서 순서). 검사·다른 도구용 — 뷰는 vUi가 절 순서대로 그린다 */
export function parseWireframe(body: string): WfScreen[] {
  const out: WfScreen[] = []
  for (const seg of segments(body)) if (seg.kind === 'item') out.push(parseScreen(seg.block.id, seg.block.title, seg.block.text))
  return out.filter((s) => s.layout)
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

/** 문장 속 "(7.1)" 같은 요소 번호를 클릭 가능한 칩으로 (wf_build.py chip) */
const chip = (s: string, ctx: RenderCtx): string =>
  inline(s, ctx).replace(/\((\d+(?:\.\d+)?[a-z]?)\)/g, '(<span class="eref" data-ref="$1">$1</span>)')

function screenHtml(s: WfScreen, i: number, ctx: RenderCtx, common: CommonParts): string {
  const meta = s.meta.map(([k, v]) => `<span><b>${esc(k)}</b>${inline(v, ctx)}</span>`).join('')
  const desc = s.desc ? `<div class="s-desc">${inline(s.desc, ctx)}</div>` : ''
  const rows = s.elems
    .map(
      (e) =>
        `<tr data-wf-row="${esc(e.no)}"><td class="no">${esc(e.no)}</td><td>${inline(e.name, ctx)}</td><td class="kind">${inline(e.kind, ctx)}</td><td>${inline(e.shows, ctx)}</td><td>${inline(e.onclick, ctx)}</td></tr>`,
    )
    .join('')
  const rules = s.rules.map((r) => `<li>${chip(r, ctx)}</li>`).join('')
  const scen = s.scenarios
    .map(
      (sc) =>
        `<div class="scen"><div class="st"><span class="k">${esc(sc.id)}</span>${inline(sc.title, ctx)}${sc.uc ? `<span class="uc">— ${inline(sc.uc, ctx)}</span>` : ''}</div><ol>${sc.steps.map((st) => `<li>${chip(st, ctx)}</li>`).join('')}</ol></div>`,
    )
    .join('')
  // 우측 셋이 다 비면 배치만 전폭으로 — 「html 블록만 필수」(STD-001 2.7)를 화면에서도 지킨다
  const rsecs = [
    s.elems.length
      ? `<div class="rsec"><h3>요소</h3><table class="el"><thead><tr><th>#</th><th>이름</th><th>종류</th><th>보여주는 것</th><th>누르면</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '',
    s.rules.length ? `<div class="rsec"><h3>규칙</h3><ul class="rules">${rules}</ul></div>` : '',
    s.scenarios.length ? `<div class="rsec"><h3>시나리오</h3>${scen}</div>` : '',
  ].join('')
  const frame = frameHtml(s.layout, common, ctx.assetBase ?? '')
  const split = rsecs
    ? `<div class="split"><div class="left">${frame}</div><div class="right">${rsecs}</div></div>`
    : `<div class="split full"><div class="left">${frame}</div></div>`
  return `<section class="screen" id="item-${esc(s.id)}" data-item="${esc(s.id)}" data-i="${i}"${i === 0 ? '' : ' style="display:none"'}>
    <div class="s-head"><b>${esc(s.id)} ${esc(s.name)}</b>${meta}</div>${desc}
    ${split}
  </section>`
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

/** 화면 묶음 하나 = 탭 줄 + 화면들. 문서에 묶음이 여럿일 수 있어(TBL식 「2.1 C 리포트 / 2.2 A 리포트」) .wfgroup으로 싼다 */
export function wireframeHtml(screens: WfScreen[], ctx: RenderCtx, common: CommonParts = { head: '', body: '' }): string {
  const tabs = screens
    .map(
      (s, i) =>
        `<button type="button" role="tab" aria-selected="${i === 0}" data-i="${i}"><span class="k">${esc(s.id)}</span>${esc(s.name)}</button>`,
    )
    .join('')
  return `<div class="wfgroup"><div class="stabs" role="tablist">${tabs}</div>\n<div class="screens">${screens.map((s, i) => screenHtml(s, i, ctx, common)).join('\n')}</div></div>`
}

/** html 없는 화면 → 화면 설계 표 한 행 (옛 vUiDesign). 첫 줄 산문에서 종류·목적·주 유스케이스를 뽑는다 */
function designTable(blocks: ItemBlock[], ctx: RenderCtx): string {
  const rows = blocks
    .map((b) => {
      const first = b.text.trim().split('\n')[0] ?? ''
      const kind = first.includes('.') ? first.split('.')[0] : ''
      const uc = /주 유스케이스: (.+)$/.exec(first)
      const purpose = first.includes('. ') ? first.split('. ').slice(1).join('. ').split(' 주 유스케이스')[0] : first
      const downs = downsWith(ctx, b.id)
      return `<tr id="item-${esc(b.id)}" data-item="${esc(b.id)}"><td class="iid">${esc(b.id)}</td><td>${inline(b.title, ctx)}</td><td>${esc(kind)}</td><td>${inline(purpose, ctx)}</td><td>${uc ? inline(uc[1], ctx) : ''}</td><td>${downs.map((d) => refLink(ctx, d)).join(' · ')}</td></tr>`
    })
    .join('')
  return `<table class="reassembled"><thead><tr><th>#</th><th>화면</th><th>종류</th><th>목적</th><th>주 유스케이스</th><th>참조한 곳</th></tr></thead><tbody>${rows}</tbody></table>`
}

/** 이어진 화면 항목 묶음 → html 없는 것은 표, 있는 것은 탭 묶음. 둘 다 있으면 표가 먼저 */
function renderRun(blocks: ItemBlock[], ctx: RenderCtx, common: CommonParts): string {
  const screens = blocks.map((b) => parseScreen(b.id, b.title, b.text))
  const design = blocks.filter((_, i) => !screens[i].layout)
  // 묶음 안에서는 번호순 — 옛 와이어프레임 뷰와 같다. 묶음(절) 순서는 문서 순서
  const wf = screens.filter((s) => s.layout).sort((a, b) => Number(a.id.split('-')[1]) - Number(b.id.split('-')[1]))
  return (design.length ? designTable(design, ctx) : '') + (wf.length ? wireframeHtml(wf, ctx, common) : '')
}

/** 절 본문 → 산문은 그대로, 화면 항목 묶음은 표·탭으로. 항목이 절 자체(`## UI-N`)인 경우는 vUi가 모은다 */
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
.split{display:grid;grid-template-columns:minmax(560px,1.15fr) minmax(420px,1fr)}
.split.full{grid-template-columns:1fr}
.split.full .left{border-right:none}
.s-desc{padding:8px 18px;border-bottom:1px solid var(--hair);font-size:13px;color:var(--soft)}
.wfgroup{margin-bottom:22px}
.left{padding:18px;border-right:1.5px solid var(--ink);background:#F2F3F0;overflow:auto}
.right{padding:0;max-height:88vh;overflow-y:auto}

/* 오른쪽 */
.rsec{padding:16px 20px;border-bottom:1px solid var(--hair)}
.rsec:last-child{border-bottom:none}
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
@media (max-width:1100px){.split{grid-template-columns:1fr}.left{border-right:none;border-bottom:1.5px solid var(--ink)}.right{max-height:none}}
`
