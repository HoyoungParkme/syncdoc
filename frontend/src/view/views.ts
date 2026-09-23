/** V-PRD · V-RFQ · V-SCN · V-INFRA · V-DOM · V-API · V-STD — tools/view_build.py 포트. V-UI는 wireframe.ts(vUi).
 *  하위 참조 수·추적표·"근거로 삼은 문서"는 ctx.downstream(GET /api/docs/{id}/downstream, B4)에서 계산한다 —
 *  view_build.downstream_of와 같은 모양 {문서ID: [항목ID들]}. */
import { BLOCK_START, esc, etcBlock, h2, inline, itemBlocks, renderBlocks, secName, splitItems, splitSections, type ItemBlock, type RenderCtx } from './md'
import { ITEM_PAT, plain, type ViewFn } from './types'

const card = (id: string, title: string, inner: string, ctx: RenderCtx, cls = 'card') =>
  `<article class="${cls}" id="item-${esc(id)}" data-item="${esc(id)}"><div class="card-h"><span class="iid">${esc(id)}</span><b>${inline(title, ctx)}</b></div>${inner}</article>`

/** view_build.downstream_of(did)에서 항목 id를 참조한 문서들 (정렬) */
export const downsWith = (ctx: RenderCtx, id: string): string[] =>
  Object.entries(ctx.downstream ?? {})
    .filter(([, v]) => v.includes(id))
    .map(([d]) => d)
    .sort()
export const refLink = (ctx: RenderCtx, d: string) => `<a class="ref" href="${esc(ctx.href(d))}" data-ref="${esc(d)}">${esc(d)}</a>`
/** 추적표 — 이 문서를 근거로 삼은 문서 (원본에 없음. 참조에서 계산) */
const traceTable = (ctx: RenderCtx): string => {
  const downs = Object.entries(ctx.downstream ?? {}).sort(([a], [b]) => (a < b ? -1 : 1))
  if (!downs.length) return ''
  const rows = downs
    .map(([d, v]) => `<tr><td>${refLink(ctx, d)}</td><td>${esc(ctx.titles?.[d] ?? '')}</td><td>${esc([...v].sort().join(', '))}</td></tr>`)
    .join('')
  return `<h2>추적표 — 이 문서를 근거로 삼은 문서</h2><p class="soft">원본에 없다. 다른 문서의 참조에서 계산했다.</p><table class="trace"><thead><tr><th>문서</th><th>제목</th><th>참조한 항목</th></tr></thead><tbody>${rows}</tbody></table>`
}

const head = (s: string): [string, string] => {
  const nl = s.indexOf('\n')
  return nl < 0 ? [s, ''] : [s.slice(0, nl), s.slice(nl + 1)]
}

/** view_build.item_card — 머리 ID 뱃지·제목·필·`하위 N` · 몸 · 바닥 "{label}: 문서들". 하위가 없으면 필·바닥을 안 그린다 */
const itemCard = (ctx: RenderCtx, b: ItemBlock, inner: string, label: string, pills = ''): string => {
  const down = downsWith(ctx, b.id)
  let c = `<article class="card" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><div class="card-h"><span class="iid">${esc(b.id)}</span><b>${inline(b.title, ctx)}</b>${pills}`
  if (down.length) c += `<span class="pill soft">하위 ${down.length}</span>`
  c += '</div>' + inner
  if (down.length) c += `<div class="down">${label}: ` + down.map((d) => refLink(ctx, d)).join(' · ') + '</div>'
  return c + '</article>'
}

/** view_build.item_cards — 항목 밖 문장은 그대로, 항목은 본문 전부를 몸으로 한 카드 (V-PRD 목표·V-INFRA 제약, #120) */
const itemCards = (ctx: RenderCtx, text: string, pat: RegExp, label: string): string =>
  splitItems(text, pat)
    .map((p) => (p.kind === 'text' ? renderBlocks(p.text, ctx) : itemCard(ctx, p.block, renderBlocks(p.block.text, ctx), label)))
    .join('')

export const vPrd: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    const name = secName(title)
    if (name.startsWith('목표')) {
      out.push(h2(title) + itemCards(ctx, text, /G\d+/, '이 목표를 근거로 삼은 문서'))
      continue
    }
    if (name.startsWith('요구사항')) {
      out.push(h2(title))
      // 절 머리·소절(### 3.1 …) 제목·소절 머리는 그대로, 항목은 카드
      for (const p of splitItems(text, /R\d+|N\d+/)) {
        if (p.kind === 'text') {
          out.push(renderBlocks(p.text, ctx))
          continue
        }
        const b = p.block
        const ac = [...b.text.matchAll(/^- \[([ x])\] (.+)$/gm)]
        const done = ac.filter((m) => m[1] === 'x').length
        const desc = b.text.replace(/^- \[[ x]\] .+$/gm, '').trim()
        let inner = renderBlocks(desc, ctx)
        if (ac.length)
          inner +=
            '<ul class="ac">' +
            ac
              .map(
                (m) =>
                  `<li class="${m[1] === 'x' ? 'done' : ''}"><span class="box">${m[1] === 'x' ? '✓' : ''}</span>${inline(m[2], ctx)}</li>`,
              )
              .join('') +
            '</ul>'
        const pills = ac.length ? `<span class="pill">인수기준 ${done}/${ac.length}</span>` : ''
        out.push(itemCard(ctx, b, inner, '이 요구사항을 근거로 삼은 문서', pills))
      }
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, ITEM_PAT.PRD))
  }
  out.push(traceTable(ctx))
  return { html: out.join('\n') }
}

/** V-RFQ — 원본 순서 그대로. 끝에 추적표(요구가 어디로 갔나) + 근거로 안 쓰인 요구 경고 */
export const vRfq: ViewFn = ({ body, ctx }) => {
  const out = [renderBlocks(body, ctx, /Q\d+/)]
  const downs = Object.entries(ctx.downstream ?? {})
  if (downs.length) {
    const byQ = new Map<string, Set<string>>()
    for (const [d, v] of downs) for (const it of v) (byQ.get(it) ?? byQ.set(it, new Set()).get(it)!).add(d)
    const titles = new Map(itemBlocks(body, /Q\d+/).map((b) => [b.id, b.title]))
    const rows = [...byQ.entries()]
      .sort(([a], [b]) => (a === '(문서)') !== (b === '(문서)') ? (a === '(문서)' ? 1 : -1) : a < b ? -1 : 1)
      .map(([q, ds]) => `<tr><td class="iid">${esc(q)}</td><td>${inline(titles.get(q) ?? '', ctx)}</td><td>${[...ds].sort().map((d) => refLink(ctx, d)).join(' · ')}</td></tr>`)
      .join('')
    out.push(`<h2>추적표 — 요구가 어디로 갔나</h2><p class="soft">원본에 없다. 다른 문서의 참조에서 계산했다. 어느 요구도 근거로 안 쓰였다면 그 요구는 구현 계획이 없는 것이다.</p><table class="trace"><thead><tr><th>요구</th><th>내용</th><th>근거로 삼은 문서</th></tr></thead><tbody>${rows}</tbody></table>`)
    const unused = [...titles.keys()].filter((q) => !byQ.has(q))
    if (unused.length) out.push(`<p class="warn">근거로 쓰이지 않은 요구: ${esc(unused.join(', '))}</p>`)
  }
  return { html: out.join('\n') }
}

/** view_build.scn_parts — S 블록 → 머리·단계들·변형들·꼬리·그 밖 줄 목록. 규약 조각대로 가르고 안 맞는 줄은 그 밖
 *  (STD-002 V-SCN, #152). 단계는 번호 줄 + 빈 줄 없이 이어진 줄·들여 쓴 줄. 변형은 `**변형` 줄부터 다음 변형·성공 조건·
 *  연관 줄 전까지 전부. 꼬리는 `**성공 조건`·`**연관` 줄부터 다음 변형 전까지. 코드블록 안 줄은 여는 줄이 든 조각을 따른다 */
const scnParts = (text: string) => {
  const head: string[] = []
  const steps: string[][] = []
  const variants: string[][] = []
  const tail: string[] = []
  const etc: string[] = []
  let cur = head
  let mode = 'head'
  let fence = false
  let blank = false
  for (const l of text.split('\n')) {
    if (fence) {
      cur.push(l)
      fence = !l.trimStart().startsWith('```')
      continue
    }
    if (l.startsWith('**변형')) {
      variants.push([])
      cur = variants[variants.length - 1]
      mode = 'var'
    } else if (l.startsWith('**성공 조건') || l.startsWith('**연관')) {
      cur = tail
      mode = 'tail'
    } else if (mode === 'var' || mode === 'tail') {
      // 그 변형·꼬리에 그대로
    } else if (/^\d+\. /.test(l)) {
      steps.push([])
      cur = steps[steps.length - 1]
      mode = 'steps'
    } else if (mode === 'steps' && (!l.trim() || l[0] === ' ' || l[0] === '\t' || !blank)) {
      // 그 단계에 — 빈 줄·들여 쓴 줄·빈 줄 없이 이어진 줄
    } else if (mode === 'steps' || mode === 'etc') {
      cur = etc
      mode = 'etc'
    }
    cur.push(l)
    fence = l.trimStart().startsWith('```')
    blank = !l.trim()
  }
  return { head, steps, variants, tail, etc }
}

/** view_build.step_html — 첫 문단은 번호 옆, 나머지(밑 목록·둘째 문단)는 번호 너비만큼 들여쓰기를 떼고 그 아래 (#152) */
const stepHtml = (lines: string[], ctx: RenderCtx): string => {
  const num = /^\d+\. /.exec(lines[0])![0]
  const rest = lines.slice(1).map((l) => l.replace(new RegExp(`^ {1,${num.length}}`), ''))
  const lead = [lines[0].slice(num.length)]
  while (rest.length && rest[0].trim() && !BLOCK_START.test(rest[0])) lead.push(rest.shift()!)
  return inline(lead.join(' '), ctx) + renderBlocks(rest.join('\n'), ctx)
}

/** view_build.variant_html — 접힘. 이름은 summary, 첫 줄 나머지부터 다음 표시 줄 전까지가 몸 (#152) */
const variantHtml = (lines: string[], ctx: RenderCtx): string => {
  const m = /^\*\*(변형[^*]*)\*\*:?\s*(.*)/.exec(lines[0])
  const [name, first] = m ? [m[1], m[2]] : ['변형', lines[0]]
  return `<details class="variant"><summary>${esc(name)}</summary>${renderBlocks([first, ...lines.slice(1)].join('\n'), ctx)}</details>`
}

/** view_build.scn_card — 머리 ID·제목·`N단계` / 주체·상황 → 단계 타임라인 → 변형(접힘) → 성공 조건·연관 → 그 밖 */
const scnCard = (b: ItemBlock, ctx: RenderCtx): string => {
  const p = scnParts(b.text)
  const lis = p.steps.map((s) => `<li>${stepHtml(s, ctx)}</li>`).join('')
  const vars = p.variants.map((v) => variantHtml(v, ctx)).join('')
  return `<article class="scard" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><div class="card-h"><span class="iid">${esc(b.id)}</span><b>${inline(b.title, ctx)}</b><span class="pill soft">${p.steps.length}단계</span></div>${renderBlocks(p.head.join('\n'), ctx)}<ol class="steps">${lis}</ol>${vars}${renderBlocks(p.tail.join('\n'), ctx)}${etcBlock(p.etc, ctx)}</article>`
}

/** view_build.v_scn — 항목 밖 문장(절 머리·소절 제목·소절 머리)은 원본 순서 그대로, 항목 헤딩 단계와 무관.
 *  전에는 절 머리를 `### `·`#### ` 글자로 잘라 항목 헤딩이 다른 단계면 절 전체가 한 번 더 그려졌다 (#152) */
export const vScn: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    const name = secName(title)
    if (name.startsWith('페르소나')) {
      let html = ''
      let grid = '' // 이어진 P 카드끼리 한 그리드
      for (const p of splitItems(text, /P\d+/)) {
        if (p.kind === 'item') {
          grid += card(p.block.id, p.block.title, renderBlocks(p.block.text, ctx), ctx, 'pcard')
          continue
        }
        if (grid) html += `<div class="pgrid">${grid}</div>`
        grid = ''
        html += renderBlocks(p.text, ctx)
      }
      if (grid) html += `<div class="pgrid">${grid}</div>`
      out.push(h2(title) + html)
      continue
    }
    if (name.startsWith('시나리오')) {
      out.push(h2(title) + splitItems(text, /S\d+/).map((p) => (p.kind === 'text' ? renderBlocks(p.text, ctx) : scnCard(p.block, ctx))).join(''))
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, ITEM_PAT.SCN))
  }
  return { html: out.join('\n') }
}

/** V-INFRA — 제약은 카드, 절 머리 그대로. 마지막 제약 뒤 문단은 그 제약의 본문이다 — 특정 문장으로 꼬리를 알아보지 않는다(#120) */
export const vInfra: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    if (secName(title).startsWith('제약')) {
      out.push(h2(title) + itemCards(ctx, text, /C\d+/, '이 제약을 근거로 삼은 문서'))
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, /C\d+/))
  }
  return { html: out.join('\n') }
}

export const vDom: ViewFn = ({ title: t, body, ctx }) => {
  const pat = /[A-Z][A-Za-z]+/
  if (t.includes('도메인')) {
    const out: string[] = []
    for (const [title, text] of splitSections(body)) {
      if (secName(title).startsWith('개념별')) {
        const lead = text.split(/^#### /m)[0]
        const cards = itemBlocks(text, pat)
          .map((b) => card(b.id, b.title, renderBlocks(b.text, ctx), ctx, 'pcard'))
          .join('')
        out.push(`${h2(title)}${renderBlocks(lead, ctx)}<div class="pgrid dom">${cards}</div>`)
        continue
      }
      out.push(h2(title) + renderBlocks(text, ctx, pat))
    }
    return { html: out.join('\n') }
  }
  if (t.includes('클래스')) {
    const out: string[] = []
    for (const [title, text] of splitSections(body)) {
      if (secName(title).startsWith('엔티티')) {
        const groups = text.split(/^### /m)
        out.push(h2(title) + renderBlocks(groups[0], ctx))
        for (const grp of groups.slice(1)) {
          const [gt, gb] = head(grp)
          const classes = [...gb.matchAll(/```mermaid\nclassDiagram\n([\s\S]*?)\n```/g)].map((m) => m[1])
          const rels = new Set<string>()
          for (const b of itemBlocks(gb, pat))
            for (const m of b.text.matchAll(/^- `(\w+)` ([^—]+) — ([^`]+) `(\w+)`(?: \((.+)\))?/gm))
              rels.add(`    ${m[1]} "${m[2].trim()}" -- "${m[3].trim()}" ${m[4]}` + (m[5] ? ` : ${m[5]}` : ''))
          if (!classes.length) {
            out.push(`<h3>${esc(gt)}</h3>` + renderBlocks(gb, ctx, pat))
            continue
          }
          const merged = 'classDiagram\n' + classes.join('\n') + '\n' + [...rels].sort().join('\n')
          out.push(
            `<h3>${esc(gt)}</h3><p class="soft">클래스 ${classes.length}개의 조각을 합친 묶음 다이어그램 — 뷰가 만든다(V-DOM). 원본은 클래스마다 따로.</p><div class="mer"><pre class="mermaid">${esc(merged)}</pre></div>`,
          )
          for (const b of itemBlocks(gb, pat)) {
            const rest = b.text.replace(/```mermaid\n[\s\S]*?\n```\n?/g, '')
            out.push(
              `<div class="card" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><div class="card-h"><span class="iid">${esc(b.id)}</span><b>${inline(b.title, ctx)}</b></div>${renderBlocks(rest, ctx)}</div>`,
            )
          }
        }
        continue
      }
      out.push(h2(title) + renderBlocks(text, ctx, pat))
    }
    return { html: out.join('\n') }
  }
  return { html: renderBlocks(body, ctx, /[a-z][a-z0-9_]+/) }
}

export const vApi: ViewFn = ({ title: t, body, ctx }) => {
  if (t.includes('REST')) {
    const out: string[] = []
    let n = 0
    for (const [title, text] of splitSections(body)) {
      const name = secName(title)
      if (name.startsWith('엔드포인트')) {
        const groups = text.split(/^### /m)
        out.push(h2(title) + renderBlocks(groups[0], ctx))
        let rows = ''
        let details = ''
        for (const grp of groups.slice(1)) {
          const [gt, gb] = head(grp)
          rows += `<tr class="grp"><td colspan="5">${esc(gt)}</td></tr>`
          for (const b of itemBlocks(gb, /(GET|POST|PUT|PATCH|DELETE)\/\S+/)) {
            const sl = b.id.indexOf('/')
            const meth = b.id.slice(0, sl)
            const path = b.id.slice(sl)
            const meta = b.text.trim().startsWith('```') ? '' : b.text.trim().split('\n')[0]
            rows += `<tr><td><span class="meth m-${meth.toLowerCase()}">${meth}</span></td><td class="mono"><a href="#item-${esc(b.id)}">${esc(path)}</a></td><td>${inline(b.title, ctx)}</td><td class="small">${inline(meta, ctx)}</td></tr>`
            if (/```yaml\n/.test(b.text)) n++
            details += `<details class="ep" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><summary><span class="meth m-${meth.toLowerCase()}">${meth}</span> <span class="mono">${esc(path)}</span> — ${inline(b.title, ctx)}</summary>${renderBlocks(b.text, ctx)}</details>`
          }
        }
        out.push(
          `<table class="reassembled eps"><thead><tr><th></th><th>경로</th><th>요약</th><th>화면 · 유스케이스 · 서비스</th></tr></thead><tbody>${rows}</tbody></table><h3>엔드포인트 상세</h3>${details}`,
        )
        continue
      }
      if (name.startsWith('스키마')) {
        out.push(
          h2(title) +
            renderBlocks(text.split('```')[0], ctx) +
            `<details class="ep"><summary>공통 스키마 (components) 펼치기</summary>${renderBlocks(text, ctx)}</details><p class="soft">OpenAPI 전체 합치기(조각 ${n}개)는 정적 뷰(view_build.py)에서. React 탭은 조각 그대로.</p>`,
        )
        continue
      }
      out.push(h2(title) + renderBlocks(text, ctx))
    }
    return { html: out.join('\n') }
  }
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    if (secName(title).startsWith('도구 정의')) {
      out.push(h2(title))
      for (const b of itemBlocks(text, /[a-z][a-z_]+/)) {
        const j = /```json\n(\{\s*"name"[\s\S]*?)\n```/.exec(b.text)
        let schemaTbl = ''
        if (j) {
          try {
            const d = JSON.parse(j[1]) as {
              description: string
              inputSchema?: { properties?: Record<string, Record<string, unknown>>; required?: string[] }
            }
            const props = d.inputSchema?.properties ?? {}
            const req = new Set<string>(d.inputSchema?.required ?? [])
            const rows = Object.entries(props)
              .map(([k, v]) => {
                const items = v.items as { type?: string } | undefined
                const typ =
                  String(v.type ?? '') +
                  (v.type === 'array' && items ? '[' + items.type + ']' : '') +
                  (Array.isArray(v.enum) ? ' ' + (v.enum as string[]).join('|') : '')
                return `<tr><td class="mono">${esc(k)}</td><td class="mono">${esc(typ)}</td><td>${req.has(k) ? '○' : ''}</td><td>${esc(String(v.description ?? ''))}</td></tr>`
              })
              .join('')
            schemaTbl = `<p class="desc">${esc(d.description)}</p><table class="schema"><thead><tr><th>인자</th><th>타입</th><th>필수</th><th>설명</th></tr></thead><tbody>${rows}</tbody></table>`
          } catch {
            schemaTbl = ''
          }
        }
        const rest = b.text.replace(/```json\n\{\s*"name"[\s\S]*?\n```\n?/, '')
        out.push(card(b.id, b.title, schemaTbl + renderBlocks(rest, ctx), ctx))
      }
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, /[a-z][a-z_]+/))
  }
  return { html: out.join('\n') }
}

export const vStd: ViewFn = ({ body, ctx }) => ({ html: renderBlocks(body, ctx, ITEM_PAT.STD) })

export const vCode: ViewFn = (i) => plain(i)
