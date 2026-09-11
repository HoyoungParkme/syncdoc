/** 3단 틀의 폭과 손잡이 — SYNC-UI-002#UI-5 요소 6.2·8.3, #UI-7 규칙.
 *  **UI-5와 UI-7이 같이 쓴다.** 두 화면이 같은 요소를 쓰므로 여기로 뺐다(STD-004 DEV-17).
 *  같은 localStorage 키를 읽어야 "화면을 옮겨도 유지된다"는 규칙이 성립한다 — 이력으로 갈 때
 *  사이드바가 기본값으로 튀면 같은 문서를 보고 있다는 감각이 끊긴다 (#36). */
import { useState } from 'react'

/** localStorage는 사파리 프라이빗 모드 등에서 던진다. 기억은 편의라 실패해도 화면은 떠야 한다 */
export function readStore(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
export function writeStore(key: string, v: string): void {
  try {
    localStorage.setItem(key, v)
  } catch {
    /* 기억만 못 할 뿐이다 */
  }
}

/** 좌 140~400 · 우 180~460 (UI-5 요소 6.2·8.3) */
export const TOC = { key: 'syncdoc.ui5.toc', init: 186, min: 140, max: 400 }
export const PANEL = { key: 'syncdoc.ui5.panel', init: 250, min: 180, max: 460 }

/** 손잡이가 끄는 폭. 저장해 둔 값이 명세 범위 밖일 수 있어 잘라 넣는다.
 *  **더하기는 반드시 함수형으로.** mousemove 리스너는 mousedown 때 한 번 만들어지므로
 *  바깥 값을 그대로 읽으면 드래그 내내 같은 시작값에 마지막 증분만 더해진다 */
export function useWidth({ key, init, min, max }: { key: string; init: number; min: number; max: number }) {
  const [w, setW] = useState(() => {
    const v = Number(readStore(key))
    return Number.isFinite(v) && v > 0 ? Math.min(max, Math.max(min, v)) : init
  })
  const add = (dx: number) =>
    setW((prev) => {
      const v = Math.min(max, Math.max(min, prev + dx))
      writeStore(key, String(v))
      return v
    })
  return [w, add] as const
}

/** 세로 손잡이. 드래그하는 동안만 window에 붙는다 — 놓으면 떼어 낸다.
 *  `el`은 요소 번호. UI-7 배치에는 번호가 없어 생략한다 */
export function Handle({ el, onDrag }: { el?: string; onDrag: (dx: number) => void }) {
  const down = (e: React.MouseEvent) => {
    e.preventDefault()
    let last = e.clientX
    const move = (m: MouseEvent) => {
      onDrag(m.clientX - last)
      last = m.clientX
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none' // 끄는 동안 본문이 선택되지 않게
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }
  return <div className="handle" data-el={el} onMouseDown={down} />
}
