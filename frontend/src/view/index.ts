/** 타입 → V-* 렌더러 (view_build.py VIEWS). 유저용 탭이 여기 하나만 부른다. */
import type { Document, DownstreamView } from '../api/client'
import type { RenderCtx } from './md'
import { ITEM_PAT, plain, type ViewFn, type ViewOutput } from './types'
import { vApi, vCode, vDom, vInfra, vPrd, vRfq, vScn, vStd } from './views'
import { ucCss, vUc } from './uc'
import { vUi, wireframeCss } from './wireframe'
import { seqCss, vSeq } from './seq'
import { msCss, vMs } from './ms'
import { mountFrames } from './frame'

/** 문서 타입 → docs/specs 아래 폴더. 배치 iframe의 <base href>가 이 폴더를 가리켜 상대 경로(../assets/x.png)가 맞다 */
const DIR: Record<string, string> = {
  RFQ: '01-RFQ', PRD: '02-PRD', SCN: '03-SCN', UC: '04-UC', INFRA: '05-INFRA', DOM: '06-DOM', UI: '07-UI', API: '08-API', SEQ: '09-SEQ', MS: '10-MS', CODE: '11-CODE', STD: 'STD',
}

function pick(type: string): ViewFn {
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
      return vUi // 화면 설계·와이어프레임 하나로 — 화면마다 html 유무로 갈린다 (STD-002 V-UI)
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
    assetBase: `/api/projects/${doc.doc_id.split('-')[0] || code}/files/${DIR[doc.doc_type] ?? doc.doc_type}/`,
  }
  const out = pick(doc.doc_type)({ type: doc.doc_type, title: fm.title ?? '', body, ctx })
  // 타입별 onMount 뒤에 html 블록 iframe(wfbox)도 산다 — 이미 산 것(V-UI)은 mountFrames가 건너뛴다. 정리도 둘 다
  const onMount = (root: HTMLElement) => {
    const a = out.onMount?.(root)
    const b = mountFrames(root)
    return () => {
      if (typeof a === 'function') a()
      b()
    }
  }
  return { html: out.html, onMount, title: fm.title ?? doc.doc_id, lead: leadOf(body) }
}

/** 본문 맨 앞 문단 — 화면이 제목 아래 리드로 쓴다(UI-5·UI-9 헤더 블록).
 *  `#` 제목·구분선·빈 줄을 건너뛰고 첫 문단만. `##`(절)을 만나면 리드가 없는 문서다 */
function leadOf(body: string): string {
  const lines = body.split('\n')
  let i = 0
  while (i < lines.length) {
    const l = lines[i].trim()
    if (l === '' || l === '---' || /^# /.test(l)) i++
    else break
  }
  if (i >= lines.length || /^#{2,}\s/.test(lines[i]) || lines[i].startsWith('|')) return ''
  const out: string[] = []
  for (; i < lines.length && lines[i].trim() !== ''; i++) out.push(lines[i].trim())
  return out.join(' ').replace(/\[\[([^\]]+)\]\]/g, '$1').replace(/[*`]/g, '')
}

/** 흡수된 빌더(build·wf·seq·ms)의 CSS — 유저용 탭이 <style>로 한 번 넣는다 */
export const extraCss = [ucCss, wireframeCss, seqCss, msCss].join('\n')

export { ITEM_PAT }
