/** 코드 본문 한 조각 — 줄 번호가 붙은 `<pre>`. UI-5 코드 탭 8.21과 UI-17 패널 4.6이 같은 모양으로 그린다(카드 BF).
 *  둘이 같은 읽기(CodeGraphService.read)를 쓰므로 그리기도 하나여야 다른 코드를 보이지 않는다. */
import type { CodeText } from '../api/client'

export function CodeLines({ src }: { src: CodeText }) {
  return (
    <pre>
      {src.text.split('\n').map((ln, i) => (
        <div key={i}>
          <span className="ln">{src.start + i}</span>
          {ln}
        </div>
      ))}
      {src.truncated && <div className="lbl">… 300줄에서 잘랐습니다</div>}
    </pre>
  )
}
