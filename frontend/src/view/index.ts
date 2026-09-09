/** 타입 → V-* 렌더러 (view_build.py VIEWS). 유저용 탭이 여기 하나만 부른다. */
import type { Document, DownstreamView } from '../api/client'
import type { RenderCtx } from './md'
import { ITEM_PAT, plain, type ViewFn, type ViewOutput } from './types'
import { vApi, vCode, vDom, vInfra, vPrd, vRfq, vScn, vStd, vUiDesign } from './views'
import { ucCss, vUc } from './uc'
import { vWireframe, wireframeCss } from './wireframe'
import { seqCss, vSeq } from './seq'
import { msCss, vMs } from './ms'

function pick(type: string, title: string): ViewFn {
  switch (type) {
    case 'PRD':
      return vPrd
    case 'RFQ':
      return vRfq
    case 'SCN':
      return vScn
    case 'UC':
      return vUc
    case 'INFRA':
      return vInfra
    case 'DOM':
      return vDom
    case 'UI':
      return title.includes('와이어프레임') ? vWireframe : vUiDesign
    case 'API':
      return vApi
    case 'SEQ':
      return vSeq
    case 'MS':
      return vMs
    case 'STD':
      return vStd
    case 'CODE':
      return vCode
    default:
      return plain
  }
}

/** frontmatter를 떼고(정적 뷰도 본문만) 타입별 렌더러로. 참조 링크는 /p/{code}/d/{doc}#item-X.
 *  downstream(GET /api/docs/{id}/downstream)이 있으면 하위 수·근거 문서·추적표를 계산한다.
 *  미존재 참조(doc.missing_refs, document_view 4a)는 회색 ?(class missing)로 그린다. */
export function renderView(doc: Document, code: string, downstream?: DownstreamView | null): ViewOutput {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(doc.body)
  const fm: Record<string, string> = {}
  for (const line of (m ? m[1] : '').split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) fm[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  const body = m ? doc.body.slice(m[0].length) : doc.body
  const items = new Set(doc.items.map((i) => i.item_id))
  const missing = new Set(doc.missing_refs ?? [])
  const ctx: RenderCtx = {
    selfId: doc.doc_id,
    href: (d, it) => `/p/${d.split('-')[0] || code}/d/${d}${it ? '#item-' + it : ''}`,
    exists: (d, it) => (d === doc.doc_id ? !it || items.has(it) : !missing.has(it ? `${d}#${it}` : d)),
    downstream: downstream ? Object.fromEntries(downstream.by_document.map((x) => [x.doc_id, x.items])) : undefined,
    titles: downstream ? Object.fromEntries(downstream.by_document.map((x) => [x.doc_id, x.title])) : undefined,
  }
  const out = pick(doc.doc_type, fm.title ?? '')({ type: doc.doc_type, title: fm.title ?? '', body, ctx })
  return { html: out.html, onMount: out.onMount }
}

/** 흡수된 빌더(build·wf·seq·ms)의 CSS — 유저용 탭이 <style>로 한 번 넣는다 */
export const extraCss = [ucCss, wireframeCss, seqCss, msCss].join('\n')

export { ITEM_PAT }
