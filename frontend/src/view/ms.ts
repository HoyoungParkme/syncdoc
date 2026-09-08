/** tools/ms_build.py 포트 — V-MS (STD-002 2장 V-MS).
 *  함수 목록 절을 모듈(서비스)별 표로 재조립하고, 함수 항목(#### Class.method 제목)마다 카드 — 시그니처 코드 블록 · 근거 ·
 *  입력/처리(번호 목록) | 출력/예외/호출하는 것/테스트 관점 두 단. 부분이 4개 이하면 "간략형".
 *  파이썬은 카드 하나만 main.innerHTML로 보여줬다. 여기서는 카드를 전부 펼쳐 두고(가벼우니) 좌 목록·목록 표 행·[[#X]]가
 *  id="item-Class.method"로 스크롤한다. */
import { esc, inline, renderBlocks, secName, splitSections, itemBlocks, type RenderCtx } from './md'
import { ITEM_PAT, type ViewFn } from './types'

const PART_NAMES = ['시그니처', '근거', '입력', '처리', '출력', '예외', '호출하는 것', '테스트 관점'] as const
type PartName = (typeof PART_NAMES)[number]
const PART_RE = new RegExp(`^\\*\\*(${PART_NAMES.join('|')})\\*\\*[ ：:]*(.*)$`)
const LEFT: readonly PartName[] = ['입력', '처리']
const RIGHT: readonly PartName[] = ['출력', '예외', '호출하는 것', '테스트 관점']

interface Fn {
  id: string
  mod: string
  name: string
  title: string
  /** 시그니처 코드(펜스·백틱 벗긴 것) */
  sig: string
  /** 시그니처 부분에서 코드를 뺀 나머지 원문 */
  sigRest: string
  /** 부분 이름 → 원문 MD */
  parts: Map<PartName, string>
  /** 첫 부분 앞의 글 (파이썬은 버렸다) */
  lead: string
  brief: boolean
}
interface TextSec {
  kind: 'text'
  id: string
  title: string
  text: string
}
interface FnSec {
  kind: 'fn'
  id: string
  title: string
  lead: string
  fns: Fn[]
}
interface ListSec {
  kind: 'list'
  id: string
  title: string
  lead: string
}
type Sec = TextSec | FnSec | ListSec

const stripFm = (s: string): string => s.replace(/^---\n[\s\S]*?\n---\n/, '')
const trimRule = (s: string): string => s.replace(/\n---\s*$/, '')

/** **부분** 줄로 자른다. `근거: …` 한 줄짜리도 근거 부분으로 (ms_build의 parts) */
function parseParts(text: string): { parts: Map<PartName, string>; lead: string } {
  const parts = new Map<PartName, string>()
  const lead: string[] = []
  let cur: PartName | null = null
  const isPart = (s: string): s is PartName => (PART_NAMES as readonly string[]).includes(s)
  for (const l of text.split('\n')) {
    const m = PART_RE.exec(l)
    if (m && isPart(m[1])) {
      cur = m[1]
      parts.set(cur, m[2])
      continue
    }
    const g = /^근거[:：]\s*(.+)$/.exec(l)
    if (g && !parts.has('근거')) {
      parts.set('근거', g[1])
      continue
    }
    if (cur === null) lead.push(l)
    else parts.set(cur, `${parts.get(cur) ?? ''}\n${l}`)
  }
  for (const [k, v] of parts) parts.set(k, v.trim())
  return { parts, lead: lead.join('\n').trim() }
}

/** 시그니처 부분 → [코드, 나머지]. ```python 펜스 또는 `한 줄` */
function splitSig(sig: string): [string, string] {
  const fence = /```\w*\n([\s\S]*?)\n?```/.exec(sig)
  if (fence) return [fence[1].trim(), (sig.slice(0, fence.index) + sig.slice(fence.index + fence[0].length)).trim()]
  const tick = /`([^`]+)`/.exec(sig)
  if (tick && sig.trim().startsWith('`')) return [tick[1].trim(), (sig.slice(0, tick.index) + sig.slice(tick.index + tick[0].length)).trim()]
  return [sig.trim(), '']
}

function parseFns(text: string): Fn[] {
  return itemBlocks(text, ITEM_PAT.MS).map((b) => {
    const dot = b.id.indexOf('.')
    const { parts, lead } = parseParts(trimRule(b.text.trimEnd()))
    const [sig, sigRest] = splitSig(parts.get('시그니처') ?? '')
    return {
      id: b.id,
      mod: b.id.slice(0, dot),
      name: b.id.slice(dot + 1),
      title: b.title,
      sig,
      sigRest,
      parts,
      lead,
      brief: parts.size <= 4,
    }
  })
}

/** 목록 표의 시그니처 칸 — 첫 줄, def 떼고 90자 */
const sigLine = (f: Fn): string =>
  f.sig
    .split('\n')[0]
    .replace(/^(async )?def /, '')
    .slice(0, 90)

/** 같은 문서 참조([[#Class.method]])에 data-jump */
function jumpify(html: string, ids: ReadonlySet<string>, selfId: string): string {
  return html.replace(/data-ref="([^"#]+)#([^"]+)"/g, (m, d: string, id: string) =>
    d === selfId && ids.has(id) ? `${m} data-jump="${esc(id)}"` : m,
  )
}

const mods = (fns: Fn[]): string[] => [...new Set(fns.map((f) => f.mod))]

function listTable(fns: Fn[]): string {
  return mods(fns)
    .map((m) => {
      const rows = fns
        .filter((f) => f.mod === m)
        .map(
          (f) =>
            `<tr data-id="${esc(f.id)}"><td><a href="#item-${esc(f.id)}" data-jump="${esc(f.id)}">${esc(f.name)}</a></td><td>${esc(f.title)}</td><td><code>${esc(sigLine(f))}</code></td><td>${f.brief ? '간략' : '전체'}</td></tr>`,
        )
        .join('')
      return `<h3 class="ms-mod">${esc(m)}</h3><table class="list"><thead><tr><th>함수</th><th>한 줄</th><th>시그니처</th><th>상세도</th></tr></thead><tbody>${rows}</tbody></table>`
    })
    .join('')
}

function card(f: Fn, ctx: RenderCtx, J: (h: string) => string): string {
  const R = (k: PartName): string => {
    const v = f.parts.get(k)
    return v === undefined ? '' : `<h5>${k}</h5>${J(renderBlocks(v, ctx))}`
  }
  const sig = f.parts.has('시그니처')
    ? `<h5>시그니처</h5><pre class="code" data-lang="python"><code>${esc(f.sig)}</code></pre>${f.sigRest ? J(renderBlocks(f.sigRest, ctx)) : ''}`
    : ''
  const left = LEFT.map(R).join('')
  const right = RIGHT.map(R).join('')
  const two = left || right ? `<div class="two"><div>${left}</div><div>${right}</div></div>` : ''
  return `<article class="ms-card${f.brief ? ' brief' : ''}" id="item-${esc(f.id)}" data-item="${esc(f.id)}"><h4 class="ms-h"><span class="mod">${esc(f.mod)}.</span>${esc(f.name)}<span class="t"> — ${inline(f.title, ctx)}</span>${f.brief ? '<span class="brief-tag">간략형</span>' : ''}</h4>${f.lead ? `<div class="lead">${J(renderBlocks(f.lead, ctx))}</div>` : ''}${sig}${R('근거')}${two}</article>`
}

export const vMs: ViewFn = ({ body, ctx }) => {
  const src = stripFm(body)
  const secs: Sec[] = []
  let listAt = -1
  splitSections(src).forEach(([title, text0], i) => {
    const text = trimRule(text0)
    const name = secName(title)
    const fns = parseFns(text)
    if (fns.length) {
      const lead = text.split(/^#### /m)[0]
      secs.push({ kind: 'fn', id: `s${i}`, title, lead: trimRule(lead), fns })
    } else if (name.startsWith('함수 목록')) {
      listAt = secs.length
      const ls = text.split('\n')
      const k = ls.findIndex((l) => l.startsWith('|'))
      secs.push({ kind: 'list', id: 'list', title, lead: (k < 0 ? ls : ls.slice(0, k)).join('\n') })
    } else secs.push({ kind: 'text', id: name.startsWith('미결') ? 'pending' : `s${i}`, title, text })
  })
  const fns = secs.flatMap((s) => (s.kind === 'fn' ? s.fns : []))
  if (listAt < 0 && fns.length) {
    const at = secs.findIndex((s) => s.kind === 'fn')
    secs.splice(at, 0, { kind: 'list', id: 'list', title: '함수 목록', lead: '' })
  }
  const ids = new Set(fns.map((f) => f.id))
  const J = (h: string): string => jumpify(h, ids, ctx.selfId)

  // 좌 목록: 절 → (함수 목록) → 모듈별 함수 → 나머지 절
  const nav: string[] = []
  for (const s of secs) {
    if (s.kind === 'fn') {
      for (const m of mods(s.fns)) {
        nav.push(`<div class="grp">${esc(m)}</div>`)
        for (const f of s.fns.filter((x) => x.mod === m))
          nav.push(
            `<a href="#item-${esc(f.id)}" data-id="${esc(f.id)}" class="${f.brief ? 'brief' : ''}"><span class="k">${esc(f.name)}</span><span class="t">${esc(f.title)}</span></a>`,
          )
      }
    } else nav.push(`<a href="#ms-${esc(s.id)}" data-id="${esc(s.id)}"><span class="k">${esc(secName(s.title))}</span></a>`)
  }

  const main = secs
    .map((s) => {
      if (s.kind === 'list')
        return `<section class="ms-sec" id="ms-list" data-id="list"><h2>${esc(s.title)}</h2>${s.lead.trim() ? J(renderBlocks(s.lead, ctx)) : ''}${listTable(fns)}</section>`
      if (s.kind === 'fn')
        return `<section class="ms-sec" id="ms-${esc(s.id)}" data-id="${esc(s.id)}"><h2>${esc(s.title)}</h2>${s.lead.trim() ? J(renderBlocks(s.lead, ctx)) : ''}${mods(
          s.fns,
        )
          .map(
            (m) =>
              `<h3 class="ms-mod">${esc(m)}</h3>` +
              s.fns
                .filter((f) => f.mod === m)
                .map((f) => card(f, ctx, J))
                .join(''),
          )
          .join('')}</section>`
      return `<section class="ms-sec" id="ms-${esc(s.id)}" data-id="${esc(s.id)}"><h2>${esc(s.title)}</h2>${J(renderBlocks(s.text, ctx))}</section>`
    })
    .join('\n')

  const html = `<div class="msv"><nav class="ms-nav">${nav.join('')}</nav><main class="ms-main">${main}</main></div>`

  const onMount = (root: HTMLElement): (() => void) => {
    const targets = new Map<string, HTMLElement>()
    for (const el of root.querySelectorAll<HTMLElement>('.ms-main [data-item], .ms-main .ms-sec[data-id]'))
      targets.set(el.dataset.item ?? el.dataset.id ?? '', el)
    const links = Array.from(root.querySelectorAll<HTMLAnchorElement>('.ms-nav a[data-id]'))
    let timer: ReturnType<typeof setTimeout> | undefined
    const select = (id: string): boolean => {
      const el = targets.get(id)
      if (!el) return false
      for (const a of links) a.classList.toggle('sel', a.dataset.id === id)
      el.scrollIntoView({ block: 'start' })
      if (el.classList.contains('ms-card')) {
        root.querySelectorAll('.ms-card.hit').forEach((c) => c.classList.remove('hit'))
        el.classList.add('hit')
        if (timer !== undefined) clearTimeout(timer)
        timer = setTimeout(() => el.classList.remove('hit'), 1500)
      }
      return true
    }
    const onClick = (e: MouseEvent): void => {
      const t = e.target
      if (!(t instanceof Element)) return
      const navA = t.closest<HTMLAnchorElement>('.ms-nav a[data-id]')
      if (navA && root.contains(navA)) {
        if (select(navA.dataset.id ?? '')) e.preventDefault()
        return
      }
      const jump = t.closest<HTMLElement>('[data-jump]')
      if (jump && root.contains(jump)) {
        if (select(jump.dataset.jump ?? '')) e.preventDefault()
        return
      }
      const row = t.closest<HTMLTableRowElement>('table.list tr[data-id]')
      if (row && root.contains(row)) select(row.dataset.id ?? '')
    }
    const fromHash = (): void => {
      let h = ''
      try {
        h = decodeURIComponent(location.hash.slice(1))
      } catch {
        h = location.hash.slice(1)
      }
      const id = h.replace(/^(?:item-|ms-)/, '')
      if (id) select(id)
    }
    root.addEventListener('click', onClick)
    window.addEventListener('hashchange', fromHash)
    fromHash()
    return () => {
      root.removeEventListener('click', onClick)
      window.removeEventListener('hashchange', fromHash)
      if (timer !== undefined) clearTimeout(timer)
    }
  }

  return { html, onMount }
}

/** ms_build.py TPL의 <style> 중 .layout 이하 — .msv 아래로 범위 한정 */
export const msCss = `
.msv{--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--panel:#F8F9F7;display:grid;grid-template-columns:270px minmax(0,1fr);border:1.5px solid var(--ink);background:#fff;min-height:60vh;font-size:14px;line-height:1.6;color:var(--ink)}
.msv .ms-nav{border-right:1.5px solid var(--ink);background:var(--panel);overflow-y:auto;max-height:88vh;position:sticky;top:0;align-self:start}
.msv .ms-nav .grp{padding:12px 14px 4px;font-size:11px;font-weight:700;color:var(--soft)}
.msv .ms-nav a{display:block;padding:7px 14px;font-size:13px;color:var(--ink);text-decoration:none;border-left:3px solid transparent;line-height:1.35;cursor:pointer}
.msv .ms-nav a:hover{background:#EAEEEA}
.msv .ms-nav a.sel{border-left-color:var(--ink);background:#fff;font-weight:600}
.msv .ms-nav a .k{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--ink)}
.msv .ms-nav a .t{color:var(--soft);font-size:12px;margin-left:6px}
.msv .ms-nav a.brief .k{color:var(--soft)}
.msv .ms-main{padding:8px 30px 30px;min-width:0;overflow-x:auto}
.msv .ms-sec{padding:12px 0 8px;border-bottom:1px solid var(--hair)}
.msv .ms-sec>h2{margin:0 0 8px;font-size:22px;font-weight:700;letter-spacing:-.02em;border:none;padding:0}
.msv h3.ms-mod{font-size:13px;margin:22px 0 8px;padding-bottom:6px;border-bottom:1.5px solid var(--ink);color:var(--soft);letter-spacing:.02em}
.msv .ms-card{padding:14px 0 18px;border-top:1px solid var(--hair);scroll-margin-top:12px;transition:background .6s}
.msv .ms-card.hit{background:#FFF7D6}
.msv .ms-card h4.ms-h{margin:0 0 4px;font-size:18px;font-weight:700;letter-spacing:-.02em}
.msv .ms-card h4.ms-h .mod{color:var(--faint);font-weight:500;font-size:14px}
.msv .ms-card h4.ms-h .t{color:var(--soft);font-weight:500;font-size:14px}
.msv .ms-card h5{font-size:12.5px;margin:16px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--ink);color:var(--ink)}
.msv .ms-card .lead{color:var(--soft)}
.msv .brief-tag{display:inline-block;font-size:11px;padding:1px 8px;border:1px solid var(--rule);background:var(--panel);color:var(--soft);margin-left:8px;vertical-align:middle;font-weight:500}
.msv pre.code{background:#1E2A30;color:#E8ECE8;padding:12px 14px;font:12.5px/1.55 ui-monospace,Menlo,monospace;overflow-x:auto;margin:6px 0 12px;border-radius:2px;white-space:pre-wrap}
.msv pre.code code{background:none;color:inherit;padding:0;font-size:inherit}
.msv table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 14px;background:#fff}
.msv th{text-align:left;font-weight:600;color:var(--soft);padding:7px 9px;border-bottom:1.5px solid var(--ink);background:var(--panel)}
.msv td{padding:7px 9px;border-bottom:1px solid var(--hair);vertical-align:top}
.msv table.list td:first-child{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;white-space:nowrap}
.msv table.list td:first-child a{color:inherit;text-decoration:none}
.msv table.list tr{cursor:pointer}
.msv table.list tr:hover td{background:#F2F4F1}
.msv ol,.msv ul{margin:4px 0 12px;padding-left:22px}
.msv li{margin:4px 0}
.msv .two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.msv a.ref[data-jump],.msv [data-jump]{cursor:pointer}
@media (max-width:1000px){.msv{grid-template-columns:1fr}.msv .ms-nav{position:static;max-height:220px;border-right:none;border-bottom:1.5px solid var(--ink)}.msv .two{grid-template-columns:1fr}}
`
