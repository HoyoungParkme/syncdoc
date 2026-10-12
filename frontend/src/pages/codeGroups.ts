/** UI-17 화면용 커뮤니티 — SYNC-UI-002#UI-17 규칙 「커뮤니티」(카드 BY, 사용자 결정 2026-10-12).
 *  묶음은 서버가 계산한 것(MS-011 communities, 두 판 바이트 같음)을 그대로 받고, 이름과 큰 무리 나누기만 여기서 한다 —
 *  서버의 허브 이름 라벨은 무엇의 무리인지 읽히지 않고 크기가 쏠렸다. 커뮤니티는 이 화면만 쓴다.
 *  1 나누기 — 함수 150개 넘는 무리는 공통 폴더 바로 아래 폴더(바로 있는 파일은 파일)마다, 여전히 넘으면 한 단 더,
 *    10개 미만 조각은 그 무리의 「기타」로 · 2 이름 — 절반 이상이 한 파일이면 파일, 아니면 절반 이상을 품는 가장 깊은 폴더,
 *    없으면 함수가 가장 많은 맨 위 폴더 · 3 번호 — 크기 내림차순, 같으면 이름순 · 4 보이는 이름 — 파일 이름 · 폴더 마지막 두 단 */
import type { CodeCommunity, CodeNode, CodeNodes } from '../api/client'

/** 이보다 함수가 많은 무리를 나눈다 */
export const SPLIT_OVER = 150
/** 나눈 조각이 이보다 작으면 「기타」로 합친다 */
export const OTHER_UNDER = 10

/** 화면용 커뮤니티 — `label`은 보이는 이름, `full`은 전체 경로(툴팁) */
export interface ViewCommunity extends CodeCommunity {
  full: string
}
export type ViewNodes = Omit<CodeNodes, 'communities'> & { communities: ViewCommunity[] }

const OTHER = ' · 기타'
const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
/** 파일의 폴더 단들 — 맨 위 파일이면 빈 목록 */
const dirParts = (file: string) => file.split('/').slice(0, -1)

/** 함수들의 공통 폴더(단들) */
function commonDir(fns: CodeNode[]): string[] {
  let pre = dirParts(fns[0].file)
  for (const f of fns) {
    const parts = dirParts(f.file)
    let i = 0
    while (i < pre.length && i < parts.length && pre[i] === parts[i]) i++
    pre = pre.slice(0, i)
  }
  return pre
}

/** 1 나누기 — 조각마다 함수들과, 「기타」면 그 공통 폴더 */
function split(fns: CodeNode[]): { fns: CodeNode[]; other?: string }[] {
  if (fns.length <= SPLIT_OVER) return [{ fns }]
  const pre = commonDir(fns)
  const groups = new Map<string, CodeNode[]>()
  for (const f of fns) {
    // 공통 폴더 바로 아래 한 단 — 그 폴더, 또는 거기 바로 있는 파일
    const key = f.file.split('/').slice(0, pre.length + 1).join('/')
    const g = groups.get(key)
    if (g) g.push(f)
    else groups.set(key, [f])
  }
  if (groups.size <= 1) return [{ fns }] // 한 파일뿐 — 더 못 나눈다
  const out: { fns: CodeNode[]; other?: string }[] = []
  const small: CodeNode[] = []
  for (const key of [...groups.keys()].sort(cmp)) {
    const g = groups.get(key)!
    if (g.length < OTHER_UNDER) small.push(...g)
    else out.push(...split(g))
  }
  if (out.length === 0) return [{ fns }] // 다 작은 조각 — 나눈 뜻이 없다
  if (small.length) out.push({ fns: small, other: pre.join('/') })
  return out
}

/** 2 이름 — 파일 경로, 또는 폴더 경로 + `/` */
function nameOf(fns: CodeNode[]): string {
  const half = (n: number) => n * 2 >= fns.length
  const files = new Map<string, number>()
  const dirs = new Map<string, number>()
  for (const f of fns) {
    files.set(f.file, (files.get(f.file) ?? 0) + 1)
    const parts = dirParts(f.file)
    for (let i = 1; i <= parts.length; i++) {
      const d = parts.slice(0, i).join('/')
      dirs.set(d, (dirs.get(d) ?? 0) + 1)
    }
  }
  const file = [...files].filter(([, n]) => half(n)).sort((a, b) => cmp(a[0], b[0]))[0]
  if (file) return file[0]
  const depth = (d: string) => d.split('/').length
  const deep = [...dirs].filter(([, n]) => half(n)).sort((a, b) => depth(b[0]) - depth(a[0]) || cmp(a[0], b[0]))[0]
  if (deep) return `${deep[0]}/`
  const top = [...dirs].filter(([d]) => depth(d) === 1).sort((a, b) => b[1] - a[1] || cmp(a[0], b[0]))[0]
  if (top) return `${top[0]}/`
  return [...files].sort((a, b) => b[1] - a[1] || cmp(a[0], b[0]))[0][0] // 맨 위 파일들뿐
}

/** 4 보이는 이름 — 파일 이름, 폴더는 마지막 두 단과 `/`, 「기타」는 그 폴더의 보이는 이름 뒤에 */
export function shownName(full: string): string {
  if (full.endsWith(OTHER)) return `${shownName(full.slice(0, -OTHER.length))}${OTHER}`
  if (full.endsWith('/')) return `${full.slice(0, -1).split('/').slice(-2).join('/')}/`
  return full.slice(full.lastIndexOf('/') + 1)
}

/** 서버 그래프 → 화면용 — 커뮤니티를 나누고 이름 붙여 번호를 다시 매기고, 함수의 커뮤니티를 그 번호로 바꾼다 */
export function regroup(d: CodeNodes): ViewNodes {
  if (d.communities.length === 0) return { ...d, communities: [] }
  const byComm = new Map<number, CodeNode[]>()
  for (const f of d.functions) {
    if (f.community === null || f.community === undefined) continue
    const g = byComm.get(f.community)
    if (g) g.push(f)
    else byComm.set(f.community, [f])
  }
  const pieces: { fns: CodeNode[]; full: string }[] = []
  for (const c of d.communities) {
    for (const p of split(byComm.get(c.id) ?? [])) {
      if (p.fns.length === 0) continue
      pieces.push({ fns: p.fns, full: p.other === undefined ? nameOf(p.fns) : p.other ? `${p.other}/${OTHER}` : '기타' })
    }
  }
  // 3 번호 — 크기 내림차순, 같으면 보이는 이름·전체 경로 순
  pieces.sort((a, b) => b.fns.length - a.fns.length || cmp(shownName(a.full), shownName(b.full)) || cmp(a.full, b.full))
  const seen = new Map<string, number>()
  const cid = new Map<string, number>()
  const communities = pieces.map((p, id) => {
    const base = shownName(p.full)
    const n = (seen.get(base) ?? 0) + 1
    seen.set(base, n)
    for (const f of p.fns) cid.set(f.key, id)
    return { id, label: n > 1 ? `${base} (${n})` : base, size: p.fns.length, full: p.full }
  })
  const functions = d.functions.map((f) => (f.community === null || f.community === undefined ? f : { ...f, community: cid.get(f.key) ?? null }))
  return { ...d, communities, functions }
}
