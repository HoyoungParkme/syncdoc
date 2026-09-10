/** UI-15 11단계 흐름 — SYNC-UI-002#UI-15. UI-8 노드를 누르면 뜬다.
 *  1 다이얼로그(1.1 제목, 1.2 이어진 수) · 2 안내 · 3 체인(3.1 항목 칩, 3.2 단계 라벨, 3.3 빈 단계)
 *  4 문서 뷰로 열기 · 5 닫기(✕) · 6 닫기
 *
 *  직접 참조가 아니라 전이적 폐포다. 역할은 단계 번호가 아니라 폐포 방향으로 정해져 온다
 *  (서버가 정한다 — MS-008 item_chain). 범위(UI-8 2.1~2.3)와 무관하게 늘 전체 참조를 본다. */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, docPath, refKey, type ItemChain as Chain } from '../api/client'

/** 단계 라벨의 역할 말. 한 단계에 두 방향이 다 걸리면 함께 적는다 */
const ROLE_KO: Record<string, string> = { upstream: '근거 ↑', self: '이 항목', downstream: '파생 ↓' }
const ROLE_ORDER = ['upstream', 'self', 'downstream']

export function ItemChain({
  docId,
  itemId,
  onPick,
  onClose,
}: {
  docId: string
  itemId: string
  onPick: (n: { docId: string; itemId: string }) => void
  onClose: () => void
}) {
  const [ch, setCh] = useState<Chain | null>(null)
  const nav = useNavigate()
  useEffect(() => {
    setCh(null)
    api
      .get<Chain>(`/api/docs/${docId}/items/${itemId.replace(/\//g, '~')}/chain`)
      .then(setCh)
      .catch(() => onClose())
  }, [docId, itemId, onClose])
  if (!ch) return null
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog wide chaindlg" data-el="1">
        <div className="dhead">
          <span data-el="1.1">
            {refKey(ch.item)}
            {ch.item.display_name ? ` — ${ch.item.display_name}` : ''}
          </span>
          <span className="lbl" data-el="1.2">
            상위로 {ch.upstream_count}개 · 하위로 {ch.downstream_count}개 이어짐
          </span>
          <span className="grow" />
          <span className="x" data-el="5" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <p className="lbl" data-el="2">
            이 항목이 11단계 체인에서 어디에 있고 어디로 흐르는지. 위는 근거로 삼은 것, 아래는 이 항목을 근거로 삼은 것.
          </p>
          <div className="chain" data-el="3">
            {ch.rows.map((r) => {
              const roles = ROLE_ORDER.filter((x) => r.items.some((i) => i.role === x))
              return (
                <div key={r.stage} className={`crow${r.items.length ? '' : ' empty'}${roles.includes('self') ? ' cur' : ''}`}>
                  <div className="cstage" data-el="3.2">
                    {r.stage} {r.doc_type}
                    {roles.length > 0 && (
                      <>
                        <br />
                        <span className="lbl">{roles.map((x) => ROLE_KO[x]).join(' · ')}</span>
                      </>
                    )}
                  </div>
                  {/* 항목이 없는 단계도 남긴다 — 체인이 어디서 끊겼는지 보이는 게 이 화면의 목적이다 */}
                  {r.items.length === 0 ? (
                    <div className="cchips lbl" data-el="3.3">
                      이 단계에는 이어지는 항목이 없다
                    </div>
                  ) : (
                    <div className="cchips">
                      {r.items.map((it) => (
                        <span
                          key={refKey(it.ref)}
                          className={`chip${it.role === 'self' ? ' me' : ''}${it.ref.is_missing ? ' gone' : ''}`}
                          data-el="3.1"
                          title={`${refKey(it.ref)}${it.ref.display_name ? ' ' + it.ref.display_name : ''}`}
                          onClick={() =>
                            !it.ref.is_missing &&
                            it.ref.doc_id &&
                            it.ref.item_id &&
                            onPick({ docId: it.ref.doc_id, itemId: it.ref.item_id })
                          }
                        >
                          <i className={`dot dot-${it.status}`} />
                          {refKey(it.ref)}
                          {it.ref.display_name ? ` ${it.ref.display_name}` : ''}
                          {it.has_flag && ' ▲'}
                          {it.ref.is_missing && ' (없는 항목)'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        <div className="dfoot">
          <span className="lbl">참조는 하위 → 상위로만 적히고, 역방향은 계산된 것이다</span>
          <span className="grow" />
          <button className="btn" type="button" data-el="6" onClick={onClose}>
            닫기
          </button>
          <button className="btn" type="button" data-el="4" onClick={() => nav(docPath(ch.item.doc_id, ch.item.item_id))}>
            문서 뷰로 열기
          </button>
        </div>
      </div>
    </>
  )
}
