/** tools/view_build.py의 공통 렌더러 포트 — inline · render_blocks · split_sections · item_blocks (STD-002 1장 공통 렌더링).
 *  React 유저용 탭은 이 HTML과 같게 그린다(STD-002 4장). 문자열 HTML을 만들고 페이지가 innerHTML로 넣는다. */

export interface RenderCtx {
  selfId: string
  /** 참조 링크 href. itemId 없으면 문서. */
  href: (docId: string, itemId?: string) => string
  /** 대상 존재 여부. 모르면 true(링크). 같은 문서 항목은 items로 판정 */
  exists: (docId: string, itemId?: string) => boolean
  /** 이 문서를 참조하는 문서 → 참조한 항목 ID들("(문서)" 포함). view_build.downstream_of. 없으면 추적표 생략 */
  downstream?: Record<string, string[]>
  /** 참조하는 문서의 제목 (추적표 열) */
  titles?: Record<string, string>
  /** 참이면 문단마다 `data-src`(그 문단 **첫 줄의 원본 텍스트**)가 붙는다.
   *  웹 문서 뷰가 그걸로 원본 줄 번호를 찾아 줄 댓글 버튼(UI-5 요소 7.4)을 놓는다.
   *  **번호가 아니라 텍스트인 이유**: 타입별 렌더러가 본문을 절·항목 블록으로 여러 번 쪼개
   *  `render_blocks`를 부르므로, 블록 안 상대 위치로는 원본 줄 번호를 알 수 없다.
   *  정적 뷰(view_build.py)는 주지 않는다 — 거기엔 댓글이 없다 (STD-002 6장) */
  lineSrc?: boolean
}

const NUL = '\uE000' // 코드 스팬 자리표시 (사용자 영역 문자)

export const esc = (s: string | null | undefined): string =>
  (s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export function splitRef(r: string): [string, string] {
  const i = r.indexOf('#')
  return i < 0 ? [r, ''] : [r.slice(0, i), r.slice(i + 1)]
}

export function inline(s: string, ctx: RenderCtx): string {
  s = esc(s)
  const codes: string[] = []
  // 코드 스팬은 참조·강조 처리에서 제외 (STD-001 1.4)
  s = s.replace(/`([^`]+)`/g, (_m, c: string) => {
    codes.push(c)
    return `${NUL}${codes.length - 1}${NUL}`
  })
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/\[\[([^\]]+)\]\]/g, (_m, r: string) => {
    const [d0, it] = splitRef(r)
    const d = d0 || ctx.selfId
    const ok = ctx.exists(d, it || undefined)
    const label = d !== ctx.selfId ? r : '#' + it
    const href = ctx.href(d, it || undefined)
    const data = `${esc(d)}${it ? '#' + esc(it) : ''}`
    return `<a class="${ok ? 'ref' : 'ref missing'}" href="${esc(href)}" data-ref="${data}">${esc(label)}</a>`
  })
  s = s.replace(/(?<![\w/])(https?:\/\/[^\s<]+)/g, '<a href="$1">$1</a>')
  s = s.replace(new RegExp(`${NUL}(\\d+)${NUL}`, 'g'), (_m, i: string) => `<code>${codes[Number(i)]}</code>`)
  return s
}

const HEAD = /^(#{1,6}) (.+)$/

export function fullMatch(re: RegExp, s: string): boolean {
  return new RegExp(`^(?:${re.source})$`).test(s)
}

/** 헤딩·문단·목록·표·코드블록. 항목 헤딩은 뱃지. mermaid는 <pre class=mermaid>. */
export function renderBlocks(text: string, ctx: RenderCtx, itemPat?: RegExp): string {
  const out: string[] = []
  const lines = text.split('\n')
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (l.startsWith('```')) {
      const lang = l.slice(3).trim()
      let j = i + 1
      const code: string[] = []
      while (j < lines.length && !lines[j].startsWith('```')) {
        code.push(lines[j])
        j++
      }
      const src = code.join('\n')
      if (lang === 'mermaid') out.push(`<div class="mer"><pre class="mermaid">${esc(src)}</pre></div>`)
      else if (lang === 'html') out.push(`<div class="wfbox">${src}</div>`)
      else out.push(`<pre class="code" data-lang="${esc(lang)}"><code>${esc(src)}</code></pre>`)
      i = j + 1
      continue
    }
    const h = HEAD.exec(l)
    if (h) {
      const lvl = h[1].length
      const t = h[2]
      const tok = t.split(' ')[0]
      const isItem = itemPat && fullMatch(itemPat, tok) && !/^\d/.test(tok)
      if (isItem) {
        const title = t.slice(tok.length).trim()
        out.push(
          `<h${lvl} class="item" id="item-${esc(tok)}" data-item="${esc(tok)}"><span class="iid">${esc(tok)}</span>${inline(title, ctx)}</h${lvl}>`,
        )
      } else {
        out.push(`<h${lvl} id="sec-${esc(t.replace(/[^\w가-힣]/g, ''))}">${inline(t, ctx)}</h${lvl}>`)
      }
      i++
      continue
    }
    if (l.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        rows.push(
          lines[i]
            .replace(/^\||\|$/g, '')
            .split('|')
            .map((c) => c.trim()),
        )
        i++
      }
      const body = rows.filter((r) => !r.every((c) => /^[-: ]*$/.test(c)))
      if (body.length) {
        const th = body[0].map((c) => `<th>${inline(c, ctx)}</th>`).join('')
        const tb = body
          .slice(1)
          .map((r) => '<tr>' + r.map((c) => `<td>${inline(c, ctx)}</td>`).join('') + '</tr>')
          .join('')
        out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`)
      }
      continue
    }
    if (/^\s*- \[[ x]\] /.test(l)) {
      const items: [boolean, string][] = []
      while (i < lines.length && /^\s*- \[[ x]\] /.test(lines[i])) {
        const chk = lines[i].slice(0, 8).includes('x')
        items.push([chk, inline(lines[i].replace(/^\s*- \[[ x]\] /, ''), ctx)])
        i++
      }
      out.push(
        '<ul class="ac">' +
          items.map(([c, t]) => `<li class="${c ? 'done' : ''}"><span class="box">${c ? '✓' : ''}</span>${t}</li>`).join('') +
          '</ul>',
      )
      continue
    }
    if (/^\s*- /.test(l)) {
      const items: [number, string][] = []
      while (i < lines.length && /^\s*- /.test(lines[i])) {
        const ind = lines[i].length - lines[i].trimStart().length
        items.push([ind, inline(lines[i].replace(/^\s*- /, ''), ctx)])
        i++
      }
      out.push('<ul>' + items.map(([ind, t]) => `<li style="margin-left:${Math.floor(ind / 2) * 14}px">${t}</li>`).join('') + '</ul>')
      continue
    }
    if (/^\d+\. /.test(l)) {
      const items: string[] = []
      while (i < lines.length && (/^\d+[a-z]?\. /.test(lines[i]) || lines[i].startsWith('   '))) {
        if (/^\d+[a-z]?\. /.test(lines[i])) items.push(inline(lines[i].replace(/^\d+[a-z]?\. /, ''), ctx))
        else if (items.length) items[items.length - 1] += '<br>' + inline(lines[i].trim(), ctx)
        i++
      }
      out.push('<ol>' + items.map((x) => `<li>${x}</li>`).join('') + '</ol>')
      continue
    }
    if (l.startsWith('> ')) {
      const q: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        q.push(inline(lines[i].slice(2), ctx))
        i++
      }
      out.push('<blockquote>' + q.join('<br>') + '</blockquote>')
      continue
    }
    if (l.trim() === '---') {
      out.push('<hr>')
      i++
      continue
    }
    if (l.trim() === '') {
      i++
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,6} |```|\||\s*- |\d+\. |> |---$)/.test(lines[i])) {
      para.push(lines[i])
      i++
    }
    // lineSrc가 아니면 속성도 없다 — 정적 뷰(view_build.py)와 같은 HTML이 나온다
    const at = ctx.lineSrc ? ` data-src="${esc(para[0])}"` : ''
    out.push(`<p${at}>${inline(para.join(' '), ctx)}</p>`)
  }
  return out.join('\n')
}

/** ## 절 단위 → [제목, 본문] */
export function splitSections(body: string): [string, string][] {
  const parts = body.split(/^## /m)
  return parts.slice(1).map((p) => {
    const nl = p.indexOf('\n')
    return nl < 0 ? [p.trim(), ''] : [p.slice(0, nl).trim(), p.slice(nl + 1)]
  })
}

export interface ItemBlock {
  id: string
  title: string
  level: number
  text: string
}

/** 항목 헤딩 블록 → [{id, title, level, text}] (헤딩 다음 줄부터, 같은 레벨 이상 헤딩 전까지) */
export function itemBlocks(body: string, pat: RegExp): ItemBlock[] {
  const lines = body.split('\n')
  const out: ItemBlock[] = []
  let i = 0
  while (i < lines.length) {
    const h = /^(#{1,6}) (\S+)(?: (.*))?$/.exec(lines[i])
    if (h && fullMatch(pat, h[2]) && !/^\d/.test(h[2])) {
      const lvl = h[1].length
      let j = i + 1
      while (j < lines.length) {
        const h2 = /^(#{1,6}) /.exec(lines[j])
        if (h2 && h2[1].length <= lvl) break
        j++
      }
      out.push({ id: h[2], title: h[3] || '', level: lvl, text: lines.slice(i + 1, j).join('\n') })
      i = j
    } else i++
  }
  return out
}

export const secName = (title: string) => title.replace(/^\d+\.\s*/, '')
export const h2 = (title: string) => `<h2>${esc(title)}</h2>`
