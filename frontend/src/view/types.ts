/** view_build.py의 VIEWS·ITEM_PAT — 타입별 본문 렌더러 계약 (STD-002 2장 V-*) */
import { renderBlocks, type RenderCtx } from './md'

export const ITEM_PAT: Record<string, RegExp> = {
  RFQ: /Q\d+/,
  PRD: /G\d+|R\d+|N\d+/,
  SCN: /P\d+|S\d+/,
  UC: /UC-[AHGS]\d+/,
  INFRA: /C\d+/,
  DOM: /[A-Za-z][A-Za-z0-9_]+/,
  UI: /UI-\d+/,
  API: /(GET|POST|PUT|PATCH|DELETE)\/\S+|[a-z][a-z_]+/,
  SEQ: /SEQ-\d+|SEQ-C\d+/,
  MS: /[A-Za-z_]+\.[a-z_]+/,
  STD: /[A-Z]+-\d+|V-[A-Z]+/,
  CODE: /[A-C]\d*/,
}

export interface ViewInput {
  type: string
  title: string
  body: string
  ctx: RenderCtx
}
export interface ViewOutput {
  html: string
  /** innerHTML 삽입 뒤 호출 — 탭·좌우 연동 같은 동작. 정리 함수를 돌려줄 수 있다 */
  onMount?: (root: HTMLElement) => void | (() => void)
}
export type ViewFn = (input: ViewInput) => ViewOutput

export const plain: ViewFn = ({ type, body, ctx }) => ({ html: renderBlocks(body, ctx, ITEM_PAT[type] ?? /\S+/) })
