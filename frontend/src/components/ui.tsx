/** 공통 컴포넌트 — SYNC-UI-002 1장. 화면마다 다시 그리지 않는 것들.
 *  1.2 툴팁 · 1.3 토스트 · 1.4 상태 필 · 1.5 항목 ID 뱃지.
 *  1.1 다이얼로그는 컴포넌트가 아니라 CSS 셸이다(styles.css `.dialog`) — 화면마다 속이 달라서. 닫는 Esc만 여기(useEscape). */
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useLocation } from 'react-router-dom'
import { STATUS_KO } from '../api/client'

/** 열려 있는 다이얼로그들의 닫기 — 나중에 연 것이 위. 창에 keydown 하나만 듣는다 */
const escStack: { close: () => void }[] = []
function onEscape(e: KeyboardEvent): void {
  // 한글 조합 중의 Esc는 조합을 끝내는 키다 — 다이얼로그까지 닫으면 쓰던 글이 날아간다
  if (e.key !== 'Escape' || e.isComposing || e.defaultPrevented) return
  const top = escStack[escStack.length - 1]
  if (!top) return
  e.preventDefault()
  top.close()
}

/** 1.1 다이얼로그 · 1.7 그림 전체보기 — Esc는 바깥을 누른 것과 같다. 겹쳐 떠 있으면 맨 위 하나만 닫는다 (#117).
 *  `onClose`가 null이면 열려 있지 않은 것. 진행 중이라 바깥 클릭을 막는 곳은 onClose 안에서 똑같이 막는다 */
export function useEscape(onClose: (() => void) | null): void {
  const latest = useRef(onClose)
  useEffect(() => {
    latest.current = onClose
  })
  const open = onClose !== null
  useEffect(() => {
    if (!open) return
    const entry = { close: () => latest.current?.() }
    escStack.push(entry)
    if (escStack.length === 1) window.addEventListener('keydown', onEscape)
    return () => {
      escStack.splice(escStack.indexOf(entry), 1)
      if (escStack.length === 0) window.removeEventListener('keydown', onEscape)
    }
  }, [open])
}

/** 1.4 상태 필. 상태색 바탕에 작은 알약. 완료만 글씨가 희다.
 *  `status`가 없으면 `미작성` — 단계에 문서가 아직 없는 칸(UI-4)이 그렇다. */
export function StatusPill({ status, el }: { status: string | null; el?: string }) {
  return (
    <span className={`pill pill-${status ?? 'none'}`} data-el={el}>
      {status ? STATUS_KO[status] : '미작성'}
    </span>
  )
}

/** 1.5 항목 ID 뱃지. 본문 글자와 섞이면 어디까지가 ID인지 안 보여서 늘 감싼다.
 *  참조 표기(`[[…]]`)는 뱃지가 아니라 점선 밑줄이다 — 누르면 이동한다는 뜻이 다르다. */
export function ItemIdBadge({ children, el }: { children: ReactNode; el?: string }) {
  return (
    <span className="idbadge" data-el={el}>
      {children}
    </span>
  )
}

/** 1.2 툴팁. 브라우저 기본 툴팁(`title`)을 쓰지 않는다 — 줄바꿈이 안 되고 지연이 길다.
 *
 *  사라지는 조건이 마우스가 벗어날 때만이면 부족하다. 클릭으로 대상이 사라지면 툴팁만 남는다.
 *  그래서 화면 이동·스크롤·아무 곳 클릭에도 지운다.
 *
 *  body로 포털을 쓴다. 대상이 `overflow:auto` 안(문서 목차·오른쪽 패널)에 있으면 잘리기 때문. */
/** UI-002 1.6 프로젝트 표기 — 「[코드] 이름」. 코드는 고정폭·굵게, 대괄호까지. 여덟 자리가 이 하나를 쓴다 —
 *  한 곳만 다르면 어휘가 아니라 실수로 보인다. 이름이 없는 자리는 이걸 쓰지 않는다(대괄호는 이름과 가르는 표시다) */
export function ProjName({ code, name, elCode, elName }: { code: string; name?: string | null; elCode?: string; elName?: string }) {
  return (
    <>
      <b className="mono" data-el={elCode}>
        [{code}]
      </b>
      {name ? (
        <>
          {' '}
          <span data-el={elName}>{name}</span>
        </>
      ) : null}
    </>
  )
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const loc = useLocation()
  useEffect(() => setAt(null), [loc])
  useEffect(() => {
    if (!at) return
    const off = () => setAt(null)
    // 캡처 단계로 듣는다 — 대상이 클릭을 멈춰 세워도 툴팁은 지워져야 한다
    window.addEventListener('scroll', off, true)
    window.addEventListener('click', off, true)
    return () => {
      window.removeEventListener('scroll', off, true)
      window.removeEventListener('click', off, true)
    }
  }, [at])
  const show = (e: MouseEvent<HTMLSpanElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setAt({ x: r.left + r.width / 2, y: r.top })
  }
  return (
    <span className="tipwrap" onMouseEnter={show} onMouseLeave={() => setAt(null)}>
      {children}
      {at &&
        createPortal(
          <span className="tip" style={{ left: at.x, top: at.y }}>
            {text}
          </span>,
          document.body,
        )}
    </span>
  )
}

/** 1.3 토스트. 되돌릴 수 없는 일이 **끝났을 때** 무엇이 기록됐는지 알린다.
 *  누를 것이 없으므로 확인을 요구하는 데는 쓰지 않는다. */
const TOAST_EVENT = 'syncdoc:toast'
const TOAST_MS = 2600

export function toast(message: string) {
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: message }))
}

/** 셸이 한 번 그린다. 화면마다 두면 화면을 떠날 때 토스트도 같이 사라진다. */
export function ToastHost() {
  // 같은 문장이 두 번 오면 상태가 안 바뀌어 타이머가 안 돈다. 번호를 같이 센다
  const [cur, setCur] = useState<{ n: number; text: string } | null>(null)
  useEffect(() => {
    const on = (e: Event) =>
      setCur((prev) => ({ n: (prev?.n ?? 0) + 1, text: (e as CustomEvent<string>).detail }))
    window.addEventListener(TOAST_EVENT, on)
    return () => window.removeEventListener(TOAST_EVENT, on)
  }, [])
  const n = cur?.n
  useEffect(() => {
    if (n === undefined) return
    const t = setTimeout(() => setCur(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [n])
  if (!cur) return null
  return <div className="toast">{cur.text}</div>
}
