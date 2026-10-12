/** UI-15 11단계 흐름 — SYNC-UI-002#UI-15. UI-8 노드를 누르면 뜬다.
 *  1 다이얼로그(1.1 제목, 1.2 이어진 수) · 2 안내 · 3 체인(3.1 항목 칩, 3.2 단계 라벨, 3.3 빈 단계, 3.4 문서 묶음 — 카드 CA)
 *  4 문서 뷰로 열기 · 5 닫기(✕) · 6 닫기
 *
 *  직접 참조가 아니라 전이적 폐포다. 역할은 단계 번호가 아니라 폐포 방향으로 정해져 온다
 *  (서버가 정한다 — MS-008 item_chain). 범위(UI-8 2.1~2.3)와 무관하게 늘 전체 참조를 본다. */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, docPath, refKey, type ChainItem, type ItemChain as Chain } from '../api/client'
import { useEscape } from './ui'

/** 단계 라벨의 역할 말. 한 단계에 두 방향이 다 걸리면 함께 적는다 */
const ROLE_KO: Record<string, string> = { upstream: '근거 ↑', self: '이 항목', downstream: '파생 ↓' }
const ROLE_ORDER = ['upstream', 'self', 'downstream']
/** 이 항목 밖 칩이 이보다 많은 단계는 문서별 묶음(3.4)으로 접는다 (카드 CA) */
const FOLD_OVER = 24
const NONE: ReadonlySet<string> = new Set()

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
  // 펼친 묶음 `{단계}|{문서}` — 어느 항목의 것인지 같이 든다. 다른 항목으로 옮기면 다 접힌 것과 같다 (카드 CA)
  const at = `${docId}#${itemId}`
  const [opened, setOpened] = useState<{ at: string; keys: Set<string> }>(() => ({ at, keys: new Set() }))
  const open = opened.at === at ? opened.keys : NONE
  const nav = useNavigate()
  useEscape(onClose) // 1.1 — 불러오는 중이어도 Esc면 열기를 그만둔다
  useEffect(() => {
    setCh(null)
    api
      .get<Chain>(`/api/docs/${docId}/items/${itemId.replace(/\//g, '~')}/chain`)
      .then(setCh)
      .catch(() => onClose())
  }, [docId, itemId, onClose])
  if (!ch) return null
  // 칩은 좁다. 같은 프로젝트 안이므로 코드 접두는 제목에서만 보이면 된다
  const code = ch.item.doc_id?.split('-')[0] ?? ''
  const short = (k: string) => (code && k.startsWith(code + '-') ? k.slice(code.length + 1) : k)
  const chip = (it: ChainItem) => (
    <span
      key={refKey(it.ref)}
      className={`chip${it.role === 'self' ? ' me' : ''}${it.ref.is_missing ? ' gone' : ''}`}
      data-el="3.1"
      title={`${refKey(it.ref)}${it.ref.display_name ? ' ' + it.ref.display_name : ''}`}
      onClick={() => !it.ref.is_missing && it.ref.doc_id && it.ref.item_id && onPick({ docId: it.ref.doc_id, itemId: it.ref.item_id })}
    >
      <i className={`dot dot-${it.status}`} />
      {short(refKey(it.ref))}
      {it.ref.display_name ? ` ${it.ref.display_name}` : ''}
      {it.ref.is_missing && ' (없는 항목)'}
    </span>
  )
  /** 한 단계의 칩 — 이 항목 밖 칩이 24개 넘으면 문서별 묶음(3.4)으로 접고, 펼친 묶음 뒤에만 그 문서의 칩 (카드 CA) */
  const chipsOf = (stage: number, items: ChainItem[]) => {
    const others = items.filter((it) => it.role !== 'self')
    if (others.length <= FOLD_OVER) return items.map(chip)
    const byDoc = new Map<string, ChainItem[]>()
    for (const it of others) {
      const d = it.ref.doc_id ?? it.ref.raw_target
      byDoc.set(d, [...(byDoc.get(d) ?? []), it])
    }
    const toggle = (k: string) =>
      setOpened((s) => {
        const n = new Set(s.at === at ? s.keys : NONE)
        if (n.has(k)) n.delete(k)
        else n.add(k)
        return { at, keys: n }
      })
    return [
      ...items.filter((it) => it.role === 'self').map(chip),
      ...[...byDoc.keys()].sort().flatMap((d) => {
        const k = `${stage}|${d}`
        const on = open.has(k)
        return [
          <span key={k} className="chip docgrp" data-el="3.4" title={`${d} — ${on ? '접기' : '펼치기'}`} onClick={() => toggle(k)}>
            {short(d)} · {byDoc.get(d)!.length}개 {on ? '▾' : '▸'}
          </span>,
          ...(on ? byDoc.get(d)!.map(chip) : []),
        ]
      }),
    ]
  }
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog chaindlg" data-el="1">
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
            이 항목이 11단계 체인에서 어디에 있고 어디로 흐르는지. 위는 이 항목이 근거로 삼은 것, 아래는 이 항목을 근거로 삼은 것. 항목을 누르면 그 항목 기준으로 다시 봅니다.
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
                    <div className="cchips">{chipsOf(r.stage, r.items)}</div>
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
          <button className="btn solid" type="button" data-el="4" onClick={() => nav(docPath(ch.item.doc_id, ch.item.item_id))}>
            문서 뷰로 열기
          </button>
        </div>
      </div>
    </>
  )
}
