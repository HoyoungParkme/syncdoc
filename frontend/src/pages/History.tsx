/** UI-7 버전 이력 — SYNC-UI-002#UI-7. 요소 번호 = data-el.
 *  1 문서 바(브레드크럼) · 2 버전 카드 목록(2.1 카드, 2.2 되돌리기, 2.3 A·B 뱃지)
 *  3 diff 영역(3.1 범위, 3.2 본문, 3.3 하위 참조 건수) · 7 이 변경이 닿는 곳
 *  4 되돌리기 확인(4.1 diff, 4.2 되돌리기, 4.3 취소) · 6 삭제 확인(6.1 삭제하고 되돌리기, 6.2 취소)
 *
 *  UI-5와 같은 3단 틀이다 — 탭으로 오갈 때 틀이 바뀌면 같은 문서를 보고 있다는 감각이 끊긴다. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ago, api, ApiError, docPath, josa, type Diff, type Document, type ItemReferences, type Version } from '../api/client'
import { DiffBox } from '../components/DiffBox'
import { StatusPill } from '../components/ui'
import { renderBlocks } from '../view/md'

type Deleted = { item_id: string; downstream: number[] }
const keyOf = (v: Version) => `${v.commit_hash}:${v.version_no ?? 's'}`

export function History() {
  const { code: proj = '', docId = '' } = useParams()
  const nav = useNavigate()
  const [doc, setDoc] = useState<Document | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [picked, setPicked] = useState<string[]>([]) // 체크 순서 (행 키). 두 개까지
  const [diff, setDiff] = useState<Diff | null>(null)
  const [hint, setHint] = useState<{ item: string; refs: ItemReferences } | null>(null)
  const [revertTo, setRevertTo] = useState<number | null>(null)
  const [revertDiff, setRevertDiff] = useState<Diff | null>(null)
  const [deleted, setDeleted] = useState<Deleted[] | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get<Document>(`/api/docs/${docId}`).then(setDoc).catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
    api.get<Version[]>(`/api/docs/${docId}/versions`).then((vs) => {
      setVersions(vs)
      const numbered = vs.filter((v) => v.version_no != null)
      setPicked(numbered.slice(0, 2).map(keyOf).reverse()) // 기본: 현재 ↔ 직전
    })
  }, [docId])
  const byKey = useMemo(() => new Map(versions.map((v) => [keyOf(v), v])), [versions])
  const range = useMemo(() => {
    const nos = picked.map((h) => byKey.get(h)?.version_no).filter((n): n is number => n != null)
    if (nos.length < 2) return null
    return { from: Math.min(...nos), to: Math.max(...nos) }
  }, [picked, byKey])
  useEffect(() => {
    setHint(null)
    if (!range) {
      setDiff(null)
      return
    }
    api.get<Diff>(`/api/docs/${docId}/diff?from=${range.from}&to=${range.to}`).then(setDiff).catch(() => setDiff(null))
  }, [range, docId])

  const toggle = (h: string) => {
    setPicked((p) => (p.includes(h) ? p.filter((x) => x !== h) : [...p, h].slice(-2))) // 세 번째면 먼저 체크한 것이 풀린다
  }
  /** 규칙: 늘 뒤쪽이 B(현재), 앞쪽이 A(이전). **고른 순서가 아니라 버전 번호로 정한다** —
   *  사람이 어느 쪽을 먼저 눌렀는지 신경 쓰지 않아도 되게 */
  const ab = useMemo(() => {
    const nos = picked.map((h) => byKey.get(h)?.version_no)
    if (picked.length < 2 || nos.some((n) => n == null)) return {}
    const [x, y] = picked
    const older = (nos[0] as number) < (nos[1] as number) ? x : y
    return { [older]: 'A', [older === x ? y : x]: 'B' } as Record<string, string>
  }, [picked, byKey])
  const openRevert = useCallback(
    (to: number) => {
      if (!doc) return
      setRevertTo(to)
      api.get<Diff>(`/api/docs/${docId}/diff?from=${doc.current_version_no}&to=${to}`).then(setRevertDiff).catch(() => setRevertDiff(null))
    },
    [doc, docId],
  )
  async function doRevert(confirm: boolean) {
    if (revertTo == null) return
    try {
      await api.post(`/api/docs/${docId}/revert`, { to_version: revertTo, confirm_item_deletion: confirm })
      nav(docPath(docId))
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'item-deletion-needs-confirm') {
        setDeleted((e.problem.deleted_items as Deleted[]) ?? [])
        return
      }
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  const showHint = (item: string) => {
    if (hint?.item === item) {
      setHint(null)
      return
    }
    api.get<ItemReferences>(`/api/docs/${docId}/items/${item.replace(/\//g, '~')}/references`).then((refs) => setHint({ item, refs }))
  }
  if (err) return <div className="page banner err">{err}</div>
  if (!doc) return null
  const firstRevertable = versions.find((v) => v.version_no != null && v.version_no !== doc.current_version_no)
  const changedItems = diff ? diff.hunks.filter((h) => h.item_id).length : 0
  const dels = diff ? diff.hunks.reduce((n, h) => n + h.lines.filter((l) => l.op === 'del').length, 0) : 0
  const adds = diff ? diff.hunks.reduce((n, h) => n + h.lines.filter((l) => l.op === 'add').length, 0) : 0
  const plainCtx = { selfId: docId, href: (d: string, it?: string) => docPath(d, it), exists: () => true }
  const titleOf = new Map(doc.items.map((i) => [i.item_id, i.display_name ?? '']))
  return (
    <div className="docscreen">
      <div className="docbar" data-el="1">
        <Link className="crumb" to={`/p/${proj}`}>
          {doc.project_name || proj}
        </Link>
        <span className="sep">›</span>
        <Link className="crumb mono" to={`/p/${proj}#stage-${doc.stage ?? ''}`}>
          {doc.stage ? `${doc.stage} ${doc.doc_type}` : doc.doc_type}
        </Link>
        <span className="sep">›</span>
        <b className="mono">{doc.doc_id}</b>
        <StatusPill status={doc.status} />
        <span className="ver mono">v{doc.current_version_no}</span>
      </div>
      <div className="body3">
        <nav className="vlist" data-el="2">
          <div className="lbl">버전 {versions.filter((v) => v.version_no != null).length}</div>
          {versions.map((v, i) => {
            const cur = v.version_no === doc.current_version_no
            const on = picked.includes(keyOf(v))
            return (
              <div className={`vcard${on ? ' sel' : ''}`} data-el={i === 0 ? '2.1' : undefined} key={keyOf(v)} onClick={() => toggle(keyOf(v))}>
                <div>
                  <b className="mono">{v.version_no != null ? `v${v.version_no}` : 'status'}</b>
                  {ab[keyOf(v)] && (
                    <span className="ab" data-el="2.3">
                      {ab[keyOf(v)]}
                    </span>
                  )}
                  {cur && <span className="lbl">현재</span>}
                  <span className="grow" />
                  <span className="lbl">{ago(v.created_at)}</span>
                </div>
                <div className={`msg${v.version_no == null ? ' lbl' : ''}`}>{v.message.split('\n')[0]}</div>
                <div className="by">
                  <span className="lbl">
                    {v.author?.kind === 'agent' ? '에이전트' : (v.author?.user?.display_name ?? '')}
                    {v.author?.kind === 'agent' && ` · 지시 ${v.author.instructed_by?.display_name ?? ''}`}
                    {v.author?.via === 'github' && ' · GitHub push'}
                  </span>
                  <span className="grow" />
                  {/* status 커밋은 본문이 같고, 현재 버전은 되돌릴 것이 없다 */}
                  {v.version_no != null && !cur && (
                    <span
                      className="btn sm danger"
                      data-el={firstRevertable && keyOf(v) === keyOf(firstRevertable) ? '2.2' : undefined}
                      onClick={(e) => {
                        e.stopPropagation()
                        openRevert(v.version_no!)
                      }}
                    >
                      되돌리기
                    </span>
                  )}
                </div>
              </div>
            )
          })}
          <p className="hint">
            두 개까지 고른다. 세 번째를 누르면 <b className="mono">A</b>가 밀려난다.
          </p>
        </nav>
        <div className="handle" />
        <section className="mainwrap" data-el="3">
          <div className="tabs">
            <Link to={docPath(docId)}>유저용</Link>
            <Link to={`${docPath(docId)}?tab=raw`}>원본</Link>
            <span className="on">이력</span>
          </div>
          <div className="drange">
            <b className="mono" data-el="3.1">{range ? `v${range.from} → v${range.to}` : `v${doc.current_version_no}`}</b>{' '}
            <span className="lbl">{range ? `항목 ${changedItems}개 변경 · 삭제 ${dels}줄 · 추가 ${adds}줄` : '버전이 하나뿐 — 전체 본문'}</span>
          </div>
          {range && diff ? (
            <div data-el="3.2">
              {diff.hunks.length === 0 && <div className="lbl">본문 차이 없음</div>}
              {/* 항목마다 카드. 어느 항목이 바뀌었는지가 줄보다 먼저 읽혀야 한다 */}
              {diff.hunks.map((h, i) => (
                <div className="dgroup" key={h.item_id ?? `_${i}`}>
                  <div className="dhead2">
                    {h.item_id ? <span className="idbadge">{h.item_id}</span> : <span className="lbl">항목 밖</span>}
                    {h.item_id && <b className="dtitle">{titleOf.get(h.item_id)}</b>}
                    <span className="grow" />
                    {h.item_id && h.downstream_count > 0 && (
                      <span className="hint" data-el="3.3" onClick={() => showHint(h.item_id!)}>
                        하위 참조 {h.downstream_count}건
                      </span>
                    )}
                  </div>
                  {hint?.item === h.item_id && (
                    <ul className="chk">
                      {hint.refs.downstream.map((r) => (
                        <li key={`${r.doc_id}#${r.item_id}`}>
                          <Link to={docPath(r.doc_id, r.item_id)}>
                            {r.doc_id}#{r.item_id}
                          </Link>{' '}
                          {r.display_name}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="diffbox">
                    {h.lines.map((ln, j) => (
                      <div key={j} className={`dl ${ln.op}`}>
                        <span className="mk">{ln.op === 'add' ? '+' : ln.op === 'del' ? '-' : ''}</span>
                        <span>{ln.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mybody body" data-el="3.2" dangerouslySetInnerHTML={{ __html: renderBlocks(doc.body.replace(/^---\n[\s\S]*?\n---\n/, ''), plainCtx) }} />
          )}
          <p className="footnote">되돌리기는 "이전 내용으로 새 버전 생성"이며 이력이 지워지지 않는다. 되돌린 결과가 현재 규약을 위반하면 거부된다.</p>
        </section>
        <div className="handle" />
        {/* 7 — 이 변경이 저장 전에 어디까지 번지는지 */}
        <aside className="vimpact" data-el="7">
          <div className="lbl">이 변경이 닿는 곳</div>
          {(diff?.hunks ?? []).filter((h) => h.item_id).length === 0 && <p className="hint">항목이 붙은 변경이 없습니다.</p>}
          {(diff?.hunks ?? [])
            .filter((h) => h.item_id)
            .map((h) => (
              <div className="icard" key={h.item_id} onClick={() => showHint(h.item_id!)}>
                <div>
                  <b className="mono">{h.item_id}</b>
                  <span className="grow" />
                  <span className="n">{h.downstream_count}</span>
                </div>
                <div className="lbl">{titleOf.get(h.item_id!)}</div>
              </div>
            ))}
          <p className="hint">항목 ID가 붙은 줄이 바뀌면 그 항목을 참조하는 하위 건수가 여기 나온다. 저장 전에 어디까지 번지는지 알 수 있다.</p>
        </aside>
      </div>
      {revertTo != null && !deleted && (
        <>
          <div className="backdrop" onClick={() => setRevertTo(null)} />
          <div className="dialog" data-el="4">
            <div className="dhead">v{revertTo}{josa(revertTo, '으로', '로')} 되돌리기</div>
            <div className="dbody">
              현재 v{doc.current_version_no}{josa(doc.current_version_no, '을', '를')} v{revertTo} 내용으로 되돌립니다. 이력은 지워지지 않고 <b>v{doc.current_version_no + 1}</b>{josa(doc.current_version_no + 1, '이', '가')} 새로 생깁니다.
              {revertDiff && (
                <div style={{ marginTop: 8 }}>
                  <div className="lbl">
                    v{doc.current_version_no} → v{doc.current_version_no + 1} (= v{revertTo} 내용)
                  </div>
                  <DiffBox diff={revertDiff} el="4.1" />
                </div>
              )}
              <div className="dacts">
                <button className="btn" data-el="4.3" onClick={() => setRevertTo(null)}>
                  취소
                </button>
                <button className="btn" data-el="4.2" style={{ fontWeight: 600 }} onClick={() => doRevert(false)}>
                  되돌리기
                </button>
              </div>
            </div>
          </div>
        </>
      )}
      {deleted && (
        <>
          <div className="backdrop" />
          <div className="dialog" data-el="6">
            <div className="dhead">항목 삭제 확인</div>
            <div className="dbody">
              v{revertTo}에는 {deleted.map((d) => `#${d.item_id}`).join(', ')}가 없습니다. 되돌리면 이 항목이 사라지고 하위 참조{' '}
              {deleted.reduce((n, d) => n + d.downstream.length, 0)}건에 <b>끊어진 참조</b> 플래그가 붙습니다.
              <ul className="chk">
                {deleted.map((d) => (
                  <li key={d.item_id}>
                    #{d.item_id} — 하위 {d.downstream.length}건
                  </li>
                ))}
              </ul>
              <div className="dacts">
                <button className="btn" data-el="6.2" onClick={() => setDeleted(null)}>
                  취소
                </button>
                <button className="btn" data-el="6.1" style={{ fontWeight: 600 }} onClick={() => doRevert(true)}>
                  삭제하고 되돌리기
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
