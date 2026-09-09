/** 줄 단위 diff 상자 — UI-11 2.3 · UI-12 2.1 공통. 항목 ID별로 묶고 add/del/ctx 줄. */
import type { Diff } from '../api/client'

export function DiffBox({ diff, el }: { diff: Diff; el?: string }) {
  if (diff.hunks.length === 0) return <div className="diffbox lbl" data-el={el}>변경 없음</div>
  return (
    <div className="diffbox" data-el={el}>
      {diff.hunks.map((h, i) => (
        <div key={h.item_id ?? `_${i}`} style={i ? { marginTop: 6 } : undefined}>
          <div className="lbl">{h.item_id ? `#${h.item_id}` : '(항목 밖)'}{h.downstream_count > 0 && ` · 하위 ${h.downstream_count}`}</div>
          {h.lines.map((ln, j) => (
            <div key={j} className={`dl ${ln.op}`}>
              {ln.op === 'add' ? '+ ' : ln.op === 'del' ? '- ' : '  '}
              {ln.text}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
