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
export interface AccessToken {
  id: number
  label: string
  issued_at: string
  expires_at: string | null
  revoked_at: string | null
  token?: string
}

export const STATUS_KO: Record<string, string> = { draft: '초안', review: '검토중', approved: '승인' }
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
