/** UI-7 버전 이력 — SYNC-UI-002#UI-7. 요소 번호 = data-el.
 *  1 문서 바 · 2 버전 목록(2.1 행, 2.2 되돌리기) · 3 diff 영역(3.1 범위, 3.2 본문, 3.3 하위 참조 건수)
 *  · 4 되돌리기 확인(4.1 diff, 4.2 되돌리기, 4.3 취소) · 6 삭제 확인(6.1 삭제하고 되돌리기, 6.2 취소) */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ago, api, ApiError, docPath, STATUS_KO, type Diff, type Document, type ItemReferences, type Version } from '../api/client'
import { DiffBox } from '../components/DiffBox'
import { renderBlocks } from '../view/md'

type Deleted = { item_id: string; downstream: number[] }

export function History() {
  const { docId = '' } = useParams()
  const nav = useNavigate()
  const [doc, setDoc] = useState<Document | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [picked, setPicked] = useState<string[]>([]) // 체크 순서 (commit_hash). 두 개까지
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
      setPicked(numbered.slice(0, 2).map((v) => v.commit_hash).reverse()) // 기본: 현재 ↔ 직전
    })
  }, [docId])
  const byHash = useMemo(() => new Map(versions.map((v) => [v.commit_hash, v])), [versions])
  const range = useMemo(() => {
    const nos = picked.map((h) => byHash.get(h)?.version_no).filter((n): n is number => n != null)
    if (nos.length < 2) return null
    return { from: Math.min(...nos), to: Math.max(...nos) }
  }, [picked, byHash])
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
  const firstRevertable = versions.find((v) => v.version_no != null && v.version_no !== doc.current_version_no)?.commit_hash
  const changedItems = diff ? diff.hunks.filter((h) => h.item_id).length : 0
  const dels = diff ? diff.hunks.reduce((n, h) => n + h.lines.filter((l) => l.op === 'del').length, 0) : 0
  const adds = diff ? diff.hunks.reduce((n, h) => n + h.lines.filter((l) => l.op === 'add').length, 0) : 0
  const plainCtx = { selfId: docId, href: (d: string, it?: string) => docPath(d, it), exists: () => true }
  return (
    <>
      <div className="docbar" data-el="1">
        <span>
          <b>{doc.doc_id}</b> · <span className={`st st-${doc.status}`}>{STATUS_KO[doc.status]}</span> · v{doc.current_version_no}
        </span>
        <span className="tabs">
          <Link to={docPath(docId)}>유저용</Link>
          <Link to={`${docPath(docId)}?tab=raw`}>원본</Link>
          <span className="on">이력</span>
        </span>
      </div>
      <div className="body2 hist">
        <table className="vers" data-el="2">
          <thead>
            <tr>
              <th />
              <th>버전</th>
              <th>시각</th>
              <th>작성</th>
              <th>변경</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {versions.map((v, i) => {
              const cur = v.version_no === doc.current_version_no
              return (
                <tr key={v.commit_hash + (v.version_no ?? 's')} className={cur ? 'cur' : ''} data-el={i === 0 ? '2.1' : undefined}>
                  <td>
                    <input type="checkbox" checked={picked.includes(v.commit_hash)} onChange={() => toggle(v.commit_hash)} />
                  </td>
                  <td>
                    {v.version_no != null ? <b>v{v.version_no}</b> : '—'} {cur && <span className="lbl">현재</span>}
                  </td>
                  <td>{ago(v.created_at)}</td>
                  <td>
                    {v.author?.kind === 'agent' ? '에이전트' : (v.author?.user?.display_name ?? '')}
                    {v.author?.kind === 'agent' && (
                      <>
                        <br />
                        <span className="lbl">지시 {v.author.instructed_by?.display_name ?? ''}</span>
                      </>
                    )}
                    {v.author?.via === 'github' && (
                      <>
                        <br />
                        <span className="lbl">GitHub push</span>
                      </>
                    )}
                  </td>
                  <td className={v.version_no == null ? 'lbl' : ''}>{v.message.split('\n')[0]}</td>
                  <td>
                    {v.version_no != null && !cur && (
                      <span className="btn sm" data-el={v.commit_hash === firstRevertable ? '2.2' : undefined} onClick={() => openRevert(v.version_no!)}>
                        되돌리기
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <section className="diffpane" data-el="3">
          <div className="sech">
            <b data-el="3.1">{range ? `v${range.from} → v${range.to}` : `v${doc.current_version_no}`}</b>{' '}
            <span className="lbl">{range ? `항목 ${changedItems}개 변경 · 삭제 ${dels}줄 · 추가 ${adds}줄` : '버전이 하나뿐 — 전체 본문'}</span>
          </div>
          {range && diff ? (
            <div className="diffbox" data-el="3.2">
              {diff.hunks.length === 0 && <div className="lbl">본문 차이 없음</div>}
              {diff.hunks.map((h, i) => (
                <div key={h.item_id ?? `_${i}`} style={i ? { marginTop: 8 } : undefined}>
                  <div className="lbl">
                    {h.item_id ? `#${h.item_id}` : '(항목 밖)'}{' '}
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
                  {h.lines.map((ln, j) => (
                    <div key={j} className={`dl ${ln.op}`}>
                      {ln.op === 'add' ? '+ ' : ln.op === 'del' ? '- ' : '  '}
                      {ln.text}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="mybody body" data-el="3.2" dangerouslySetInnerHTML={{ __html: renderBlocks(doc.body.replace(/^---\n[\s\S]*?\n---\n/, ''), plainCtx) }} />
          )}
        </section>
      </div>
      {revertTo != null && !deleted && (
        <>
          <div className="backdrop" onClick={() => setRevertTo(null)} />
          <div className="dialog" data-el="4">
            <div className="dhead">v{revertTo}으로 되돌리기</div>
            <div className="dbody">
              현재 v{doc.current_version_no}을 v{revertTo} 내용으로 되돌립니다. 이력은 지워지지 않고 <b>v{doc.current_version_no + 1}</b>이 새로 생깁니다.
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
    </>
  )
}
