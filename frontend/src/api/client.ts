/** SYNC-API-001 REST 클라이언트. 세션 쿠키. 에러는 problem+json(2장)을 Problem으로 던진다. */

export interface Problem {
  type: string
  title: string
  status: number
  detail?: string
  [k: string]: unknown
}

export class ApiError extends Error {
  problem: Problem
  constructor(p: Problem) {
    super(p.detail ?? p.title)
    this.problem = p
  }
  get kind(): string {
    return this.problem.type.replace('urn:syncdoc:', '')
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  })
  if (r.status === 204) return undefined as T
  const text = await r.text()
  const data = text ? JSON.parse(text) : null
  if (!r.ok) throw new ApiError(data && data.type ? data : { type: 'urn:syncdoc:http', title: r.statusText, status: r.status })
  return data as T
}

export const api = {
  get: <T>(url: string) => call<T>('GET', url),
  post: <T>(url: string, body?: unknown) => call<T>('POST', url, body),
  del: <T>(url: string) => call<T>('DELETE', url),
}

// ── SYNC-API-001 4장 스키마 ──
export interface UserRef {
  id: number
  github_login: string
  display_name: string
}
export interface User extends UserRef {
  created_at: string
}
export interface Author {
  kind: 'human' | 'agent'
  user: UserRef | null
  instructed_by: UserRef | null
  via: string
}
export interface StageSummary {
  stage: number
  doc_type: string
  status: string | null
  doc_count: number
  gate_warning: boolean
  /** 이 단계 문서들의 열린 플래그 합. 색은 상태, 테두리는 플래그 (UI-2 2.2) */
  flag_count: number
}
export interface DocumentSummary {
  doc_id: string
  doc_type: string
  stage: number | null
  status: 'draft' | 'review' | 'approved'
  current_version_no: number
  has_convention_error: boolean
  incomplete_warnings: string[]
  updated_at: string
  last_author: Author | null
  counts: Record<string, number>
}
export interface ProjectSummary {
  code: string
  name: string
  remote_url: string
  stages: StageSummary[]
  std_docs: DocumentSummary[]
  counts: Record<string, number>
  updated_at: string | null
}
export interface Version {
  doc_id: string
  version_no: number | null
  commit_hash: string
  message: string
  author: Author | null
  created_at: string
}
export interface ProjectDetail extends ProjectSummary {
  docs: DocumentSummary[]
  recent_changes: Version[]
  /** 폴링이 DB에 적어 둔 값 그대로. 이 화면이 fetch를 돌리지 않는다 (UI-4 요소 7) */
  last_processed_commit: string | null
  behind_by: number | null
}
export interface DocItem {
  item_id: string
  display_name: string | null
  flags: string[]
}
export interface Document extends DocumentSummary {
  body: string
  commit_hash: string | null
  convention_error_detail: string | null
  items: DocItem[]
  prev_doc_id: string | null
  next_doc_id: string | null
  missing_refs: string[]
}
export interface ItemRef {
  doc_id: string | null
  item_id: string | null
  display_name: string | null
  raw_target: string
  is_missing: boolean
}
export interface FlagSummary {
  id: number
  kind: string
  target: ItemRef
  cause: ItemRef | null
  cause_version_no: number | null
  assignee: UserRef | null
  raised_at: string
  resolved_at: string | null
}
export interface ItemReferences {
  doc_id: string
  item_id: string
  upstream: ItemRef[]
  downstream: ItemRef[]
  flags: FlagSummary[]
}
export interface UpstreamCheck {
  target: ItemRef
  target_version_no: number
  target_status: string
  referenced_from: string[]
}
export interface Comment {
  id: number
  doc_id: string
  line_no: number
  original_location: string | null
  body: string
  author: UserRef | null
  is_resolved: boolean
  created_at: string
  replies: Comment[]
}
export interface DiffLine {
  op: 'add' | 'del' | 'ctx'
  text: string
}
export interface Hunk {
  item_id: string | null
  downstream_count: number
  lines: DiffLine[]
}
export interface Diff {
  from_version: number
  to_version: number
  hunks: Hunk[]
}
export interface FlagDetail extends FlagSummary {
  cause_diff: Diff | null
  cause_change_count: number
  target_body: string
  target_version_no: number
  target_changed_since_raise: boolean
  cause_deleted_at: string | null
  cause_body: string | null
}
export interface PendingDecision {
  version_id: number
  doc_id: string
  version_no: number
  message: string
  affected_count: number
  created_at: string
}
export interface CommentSummary {
  id: number
  doc_id: string
  line_no: number
  excerpt: string
  author: UserRef | null
  created_at: string
}
export interface Todo {
  needs_check: FlagSummary[]
  broken_ref: FlagSummary[]
  upstream_impact: FlagSummary[]
  pending_decisions: PendingDecision[]
  convention_errors: DocumentSummary[]
  unresolved_comments: CommentSummary[]
  unassigned: FlagSummary[]
  total: number
}
export interface AffectedItem extends ItemRef {
  caused_by_items: string[]
  assignee: UserRef | null
}
export interface DecisionDetail {
  version: Version
  doc_id: string
  change_diff: Diff
  affected: AffectedItem[]
  choice: 'propagate' | 'skip' | 'undecided'
}
export interface GraphNode {
  id: string
  doc_id: string
  item_id: string | null
  stage: number | null
  isolated: boolean
  /** 미해결 플래그가 붙은 항목. 노드 테두리·배경과 ▲가 이걸 본다 (UI-8 3.1) */
  has_flag: boolean
}
/** UI-8 범위 — 잘라내는 게 아니라 골라낸다 */
export type GraphScope = 'all' | 'approved' | 'flagged'
export interface ChainItem {
  ref: ItemRef
  /** upstream | self | downstream. 단계 번호가 아니라 폐포 방향으로 정한다 */
  role: string
  status: string
  has_flag: boolean
}
export interface ChainRow {
  stage: number
  doc_type: string
  items: ChainItem[]
}
export interface ItemChain {
  item: ItemRef
  upstream_count: number
  downstream_count: number
  /** 항상 11개. 항목이 없는 단계도 빈 채로 온다 */
  rows: ChainRow[]
}
export interface GraphEdge {
  from: string
  to: string | null
  raw_target: string
  is_missing: boolean
}
export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}
export interface RepoStatus {
  code: string
  remote_url: string
  last_processed_commit: string | null
  synced_at: string | null
  behind_by: number | null
  error: string | null
}
export interface RebuildResult {
  docs: number
  items: number
  references: number
  versions: number
  convention_errors: { doc_id: string; detail: string }[]
}
export interface SaveResult {
  doc_id: string
  version_no: number
  commit_hash: string
  status: string
  pending_decision_version_id: number | null
  warnings: string[]
}
export interface DownstreamView {
  by_item: Record<string, ItemRef[]>
  by_document: { doc_id: string; title: string; items: string[] }[]
}
export interface AccessToken {
  id: number
  label: string
  issued_at: string
  expires_at: string | null
  revoked_at: string | null
  /** 만료가 없어, 안 쓰는 토큰을 찾는 단서가 이것뿐이다 (UI-13 3.5) */
  last_used_at: string | null
  /** 원문. 발급 응답에서만 온다 — 서버는 해시만 저장한다 */
  token?: string
}

export const STATUS_KO: Record<string, string> = { draft: '초안', review: '검토중', approved: '승인' }
export const FLAG_KO: Record<string, string> = { needs_check: '확인 필요', broken_ref: '끊어진 참조', upstream_impact: '하위 불일치' }
/** 항목 참조 표기 DOC#ITEM · 문서 경로 */
export const refKey = (r: ItemRef | null): string => (r ? `${r.doc_id ?? r.raw_target}${r.item_id ? '#' + r.item_id : ''}` : '')
export const docPath = (docId: string | null, itemId?: string | null): string =>
  docId ? `/p/${docId.split('-')[0]}/d/${docId}${itemId ? '#item-' + itemId : ''}` : '#'
/** 경과 — "3일" · "3시간" · "5분" (UI-10 age) */
export function age(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s >= 86400) return `${Math.floor(s / 86400)}일`
  if (s >= 3600) return `${Math.floor(s / 3600)}시간`
  return `${Math.max(1, Math.floor(s / 60))}분`
}
/** 버전 번호 뒤 조사 — 마지막 자리를 읽은 소리의 받침으로 고른다. 2·4·5·9는 받침이 없다 */
const HAS_FINAL = [true, true, false, true, false, false, true, true, true, false]
export const josa = (n: number, withFinal: string, without: string): string =>
  (HAS_FINAL[Math.abs(n) % 10] ? withFinal : without)

export const STAGE_TYPES = ['RFQ', 'PRD', 'SCN', 'UC', 'INFRA', 'DOM', 'UI', 'API', 'SEQ', 'MS', 'CODE']
export const STAGE_NAMES: Record<string, string> = {
  RFQ: 'RFQ', PRD: 'PRD', SCN: '사용자 시나리오', UC: 'USECASE', INFRA: '인프라', DOM: '도메인·클래스·데이터',
  UI: '화면', API: 'API', SEQ: 'SEQUENCE', MS: 'MINISPEC', CODE: 'CODE',
}

/** 상대 시각 — "3시간 전" */
export function ago(iso: string | null): string {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return '방금'
  if (s < 3600) return `${Math.floor(s / 60)}분 전`
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`
  if (s < 86400 * 2) return '어제'
  return `${Math.floor(s / 86400)}일 전`
}

export const authorLabel = (a: Author | null): string =>
  !a ? '' : a.kind === 'agent' ? `에이전트(${a.instructed_by?.display_name ?? a.user?.display_name ?? ''})` : (a.user?.display_name ?? '')
