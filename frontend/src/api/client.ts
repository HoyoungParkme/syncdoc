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
  /** 이 단계 문서들의 미존재 참조 합. 색은 상태, 테두리는 끊어진 참조 (UI-2 2.2) */
  broken_count: number
}
/** 초안·완료 둘. `review`는 카드 V에서 사라졌다 */
export type DocStatus = 'draft' | 'approved'
export interface DocumentSummary {
  doc_id: string
  doc_type: string
  stage: number | null
  status: DocStatus
  current_version_no: number
  has_convention_error: boolean
  incomplete_warnings: string[]
  updated_at: string
  last_author: Author | null
  counts: Record<string, number>
  /** 휴지통 (카드 R). 목록엔 안 나오고 /trash·문서 조회에만 값이 찬다 */
  trashed_at?: string | null
}
export interface TrashResult {
  doc_id: string
  commit_hash: string
  broken_refs: number
  next_step: string | null
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
  /** 이 항목에서 나가는 참조 중 가리키는 곳이 없는 것(raw_target). 6.1 표시된 항목의 근거 */
  missing_refs: string[]
}
export interface Document extends DocumentSummary {
  body: string
  commit_hash: string | null
  convention_error_detail: string | null
  items: DocItem[]
  prev_doc_id: string | null
  next_doc_id: string | null
  missing_refs: string[]
  project_name: string
}
export interface ItemRef {
  doc_id: string | null
  item_id: string | null
  display_name: string | null
  raw_target: string
  is_missing: boolean
}
/** UI-4 목록 다이얼로그(6)의 끊어진 참조 행. `type`이 DocumentSummary(`document`)와 가른다 */
export interface BrokenRefSummary {
  type: 'broken_ref'
  /** 출발 항목. 항목 밖(문서 머리) 참조면 item_id가 null */
  source: ItemRef
  raw_target: string
}
export interface ItemReferences {
  doc_id: string
  item_id: string
  upstream: ItemRef[]
  downstream: ItemRef[]
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
export interface GraphNode {
  id: string
  doc_id: string
  item_id: string | null
  stage: number | null
  isolated: boolean
}
/** UI-8 범위 — 잘라내는 게 아니라 골라낸다 */
export type GraphScope = 'all' | 'approved'
export interface ChainItem {
  ref: ItemRef
  /** upstream | self | downstream. 단계 번호가 아니라 폐포 방향으로 정한다 */
  role: string
  status: DocStatus
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
  project_name: string
}
export interface RepoStatus {
  code: string
  /** UI-14 표가 「[코드] 이름」으로 적는다 (UI-002 1.6) */
  name: string
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
  status: DocStatus
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

/** 내가 git 커밋에 쓰는 이메일. GitHub 직접 push로 들어온 커밋을 내 계정으로 잇는 단서 (UI-13 2.3) */
export interface CommitEmail {
  id: number
  email: string
  added_at: string
}

export const STATUS_KO: Record<string, string> = { draft: '초안', approved: '완료' }
/** 미완성 경고 규칙 ID → 사람 말. SYNC-STD-001 4장 `화면 문구` 열의 전사 */
const WARN_KO: Record<string, (m: string) => string> = {
  'section.missing': (m) => `필수 절 없음: ${m}`,
  'item.none': () => '항목이 하나도 없음',
  'ref.missing': (m) => `가리키는 곳이 없는 참조: ${m}`,
  'entity.mismatch': (m) => `엔티티와 설계 클래스의 속성이 다름: ${m}`,
  'section.unnumbered': (m) => `번호 없는 절 제목: ${m}`,
  'dom.name': (m) => `DOM 세 문서의 이름이 어긋남: ${m}`,
}
/** `"section.missing: 시나리오"` → `"필수 절 없음: 시나리오"`.
 *  표에 없는 규칙은 문자열 그대로 — 규약을 늘렸는데 문구를 안 채운 것이 눈에 띄어야 한다 */
export function warnText(w: string): string {
  const i = w.indexOf(': ')
  const rule = i < 0 ? w : w.slice(0, i)
  const message = i < 0 ? '' : w.slice(i + 2)
  return WARN_KO[rule]?.(message) ?? w
}
/** UI-5 4a 배너와 `완료로` 비활성이 보는 미완성 목록.
 *  `ref.missing`은 컬럼에 없다 — 읽을 때 references.is_missing에서 온다(SYNC-STD-001 4장).
 *  완료 게이트(MS-007 change_status)가 세는 값과 같아야 사람이 이유 없이 막히지 않는다 */
export const incompleteOf = (d: Document): string[] => [
  ...d.incomplete_warnings,
  ...d.missing_refs.map((t) => `ref.missing: ${t}`),
]
/** 항목 참조 표기 DOC#ITEM · 문서 경로 */
export const refKey = (r: ItemRef | null): string => (r ? `${r.doc_id ?? r.raw_target}${r.item_id ? '#' + r.item_id : ''}` : '')
export const docPath = (docId: string | null, itemId?: string | null): string =>
  docId ? `/p/${docId.split('-')[0]}/d/${docId}${itemId ? '#item-' + itemId : ''}` : '#'
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
