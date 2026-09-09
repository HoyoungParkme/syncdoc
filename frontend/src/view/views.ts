/** V-PRD · V-RFQ · V-SCN · V-INFRA · V-DOM · V-API · V-STD · V-UI(화면 설계) — tools/view_build.py 포트.
 *  하위 참조 수·추적표·"근거로 삼은 문서"는 ctx.downstream(GET /api/docs/{id}/downstream, B4)에서 계산한다 —
 *  view_build.downstream_of와 같은 모양 {문서ID: [항목ID들]}. */
import { esc, h2, inline, itemBlocks, renderBlocks, secName, splitSections, type RenderCtx } from './md'
import { ITEM_PAT, plain, type ViewFn } from './types'

const card = (id: string, title: string, inner: string, ctx: RenderCtx, cls = 'card') =>
  `<article class="${cls}" id="item-${esc(id)}" data-item="${esc(id)}"><div class="card-h"><span class="iid">${esc(id)}</span><b>${inline(title, ctx)}</b></div>${inner}</article>`

/** view_build.downstream_of(did)에서 항목 id를 참조한 문서들 (정렬) */
const downsWith = (ctx: RenderCtx, id: string): string[] =>
  Object.entries(ctx.downstream ?? {})
    .filter(([, v]) => v.includes(id))
    .map(([d]) => d)
    .sort()
const refLink = (ctx: RenderCtx, d: string) => `<a class="ref" href="${esc(ctx.href(d))}" data-ref="${esc(d)}">${esc(d)}</a>`
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

export const vPrd: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    const name = secName(title)
    if (name.startsWith('목표')) {
      const rows = itemBlocks(text, /G\d+/)
        .map(
          (b) =>
            `<tr id="item-${esc(b.id)}" data-item="${esc(b.id)}"><td class="iid">${esc(b.id)}</td><td>${inline(b.title, ctx)}</td><td class="num">${downsWith(ctx, b.id).length || ''}</td></tr>`,
        )
        .join('')
      out.push(
        `${h2(title)}<table class="reassembled"><thead><tr><th>#</th><th>목표</th><th>하위 참조</th></tr></thead><tbody>${rows}</tbody></table>`,
      )
      continue
    }
    if (name.startsWith('요구사항')) {
      out.push(h2(title))
      for (const sub of text.split(/^### /m)) {
        if (!sub.trim()) continue
        const [st, srest] = head(sub)
        if (!srest.trim() && !sub.includes('####')) continue
        if (!sub.startsWith('####')) out.push(`<h3>${esc(st)}</h3>`)
        const src = sub.startsWith('####') ? '#### ' + sub : srest
        for (const b of itemBlocks(src, /R\d+|N\d+/)) {
          const ac = [...b.text.matchAll(/^- \[([ x])\] (.+)$/gm)]
          const done = ac.filter((m) => m[1] === 'x').length
          const desc = b.text.replace(/^- \[[ x]\] .+$/gm, '').trim()
          const down = downsWith(ctx, b.id)
          let c = `<article class="card" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><div class="card-h"><span class="iid">${esc(b.id)}</span><b>${inline(b.title, ctx)}</b>`
          if (ac.length) c += `<span class="pill">인수기준 ${done}/${ac.length}</span>`
          if (down.length) c += `<span class="pill soft">하위 ${down.length}</span>`
          c += '</div>' + renderBlocks(desc, ctx)
          if (ac.length)
            c +=
              '<ul class="ac">' +
              ac
                .map(
                  (m) =>
                    `<li class="${m[1] === 'x' ? 'done' : ''}"><span class="box">${m[1] === 'x' ? '✓' : ''}</span>${inline(m[2], ctx)}</li>`,
                )
                .join('') +
              '</ul>'
          if (down.length) c += '<div class="down">이 요구사항을 근거로 삼은 문서: ' + down.map((d) => refLink(ctx, d)).join(' · ') + '</div>'
          out.push(c + '</article>')
        }
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

export const vScn: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    const name = secName(title)
    if (name.startsWith('페르소나')) {
      const cards = itemBlocks(text, /P\d+/)
        .map((b) => card(b.id, b.title, renderBlocks(b.text, ctx), ctx, 'pcard'))
        .join('')
      const lead = text.split(/^#### /m)[0]
      out.push(`${h2(title)}${renderBlocks(lead, ctx)}<div class="pgrid">${cards}</div>`)
      continue
    }
    if (name.startsWith('시나리오')) {
      out.push(h2(title) + renderBlocks(text.split(/^### /m)[0], ctx))
      for (const b of itemBlocks(text, /S\d+/)) {
        const hd: string[] = []
        const steps: string[] = []
        const variants: string[] = []
        const tail: string[] = []
        let mode = 'head'
        for (const l of b.text.split('\n')) {
          if (/^\d+\. /.test(l)) {
            mode = 'steps'
            steps.push(l)
          } else if (l.startsWith('**변형')) {
            mode = 'var'
            variants.push(l)
          } else if (l.startsWith('**성공 조건') || l.startsWith('**연관')) {
            mode = 'tail'
            tail.push(l)
          } else if (mode === 'head') hd.push(l)
          else if (mode === 'steps' && l.trim() && !l.startsWith('**')) {
            if (steps.length) steps[steps.length - 1] += '\n' + l
          } else if (mode === 'var') variants.push(l)
          else if (mode === 'tail') tail.push(l)
        }
        let varHtml = ''
        for (const v of variants.filter((x) => x.trim())) {
          const m = /\*\*(변형[^*]*)\*\*:?\s*(.*)/.exec(v)
          varHtml += m
            ? `<details class="variant"><summary>${esc(m[1])}</summary><p>${inline(m[2], ctx)}</p></details>`
            : `<p>${inline(v, ctx)}</p>`
        }
        const stepHtml = steps.map((x) => `<li>${inline(x.split('\n')[0].replace(/^\d+\. /, ''), ctx)}</li>`).join('')
        out.push(
          `<article class="scard" id="item-${esc(b.id)}" data-item="${esc(b.id)}"><div class="card-h"><span class="iid">${esc(b.id)}</span><b>${inline(b.title, ctx)}</b><span class="pill soft">${steps.length}단계</span></div>${renderBlocks(hd.join('\n'), ctx)}<ol class="steps">${stepHtml}</ol>${varHtml}${renderBlocks(tail.join('\n'), ctx)}</article>`,
        )
      }
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, ITEM_PAT.SCN))
  }
  return { html: out.join('\n') }
}

export const vInfra: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    if (secName(title).startsWith('제약')) {
      const lead = text.split(/^#### /m)[0]
      const rows = itemBlocks(text, /C\d+/)
        .map((b) => {
          const src = /^출처: (.+)$/m.exec(b.text)
          const downs = downsWith(ctx, b.id)
          return `<tr id="item-${esc(b.id)}" data-item="${esc(b.id)}"><td class="iid">${esc(b.id)}</td><td>${inline(b.title, ctx)}</td><td>${src ? inline(src[1], ctx) : ''}</td><td>${downs.map((d) => refLink(ctx, d)).join(' · ')}</td></tr>`
        })
        .join('')
      const tailIdx = text.lastIndexOf('\n\n**')
      const tail = tailIdx >= 0 && text.includes('이 설계의 두 축') ? text.slice(tailIdx) : ''
      out.push(
        `${h2(title)}${renderBlocks(lead, ctx)}<table class="reassembled"><thead><tr><th>#</th><th>제약</th><th>출처 (근거)</th><th>이 제약을 근거로 삼은 곳</th></tr></thead><tbody>${rows}</tbody></table>${renderBlocks(tail, ctx)}`,
      )
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

/** 화면 설계(UI-001): UI 항목 표로 재조립. 와이어프레임은 wireframe.ts */
export const vUiDesign: ViewFn = ({ body, ctx }) => {
  const out: string[] = []
  for (const [title, text] of splitSections(body)) {
    if (secName(title).startsWith('화면 목록')) {
      const rows = itemBlocks(text, /UI-\d+/)
        .map((b) => {
          const first = b.text.trim().split('\n')[0]
          const kind = first.includes('.') ? first.split('.')[0] : ''
          const uc = /주 유스케이스: (.+)$/.exec(first)
          const purpose = first.includes('. ') ? first.split('. ').slice(1).join('. ').split(' 주 유스케이스')[0] : first
          const downs = downsWith(ctx, b.id)
          return `<tr id="item-${esc(b.id)}" data-item="${esc(b.id)}"><td class="iid">${esc(b.id)}</td><td>${inline(b.title, ctx)}</td><td>${esc(kind)}</td><td>${inline(purpose, ctx)}</td><td>${uc ? inline(uc[1], ctx) : ''}</td><td>${downs.map((d) => refLink(ctx, d)).join(' · ')}</td></tr>`
        })
        .join('')
      const lead = text.split(/^#### /m)[0]
      out.push(
        `${h2(title)}${renderBlocks(lead, ctx)}<table class="reassembled"><thead><tr><th>#</th><th>화면</th><th>종류</th><th>목적</th><th>주 유스케이스</th><th>참조한 곳</th></tr></thead><tbody>${rows}</tbody></table>`,
      )
      continue
    }
    out.push(h2(title) + renderBlocks(text, ctx, /UI-\d+/))
  }
  return { html: out.join('\n') }
}

export const vCode: ViewFn = (i) => plain(i)
