/** UI-16 사용 방법 — SYNC-UI-002#UI-16. 상단 바에서 어느 화면 위로든 뜨는 안내 다이얼로그.
 *  1 다이얼로그 · 2 사용 순서(2.1 행) · 3 11단계 표(3.1 단계 행, 3.2 STD 행, 3.3 ID 문법, 3.4 주의) · 4 ✕ · 5 닫기
 *  읽기 전용이고 상태가 없다 — 어디서 열든 같은 내용이고 닫으면 원래 화면 그대로다. */

/** 여섯 단계. 웹에 편집이 없다는 것을 3에서 말한다 — 처음 온 사람이 가장 자주 헤매는 지점이다 */
const ORDER: [string, string, string][] = [
  ['저장소를 등록한다', '명세 원본은 저장소의 docs/specs/에 둔다. 프로젝트 하나가 저장소 하나다.', '프로젝트 목록'],
  ['에이전트를 붙인다', '설정에서 MCP 토큰을 발급해 Claude Code·Codex·Gemini에 넣는다. 클라이언트는 상관없다.', '설정'],
  ['에이전트와 대화하며 명세를 쓴다', '명세 본문이 들어오는 길은 MCP와 GitHub push 둘뿐이다. 웹에는 편집 화면이 없다.', '에이전트'],
  ['웹에서 읽고 확정한다', '유저용 탭으로 읽고, 참조를 따라가고, 댓글을 달고, 상태를 바꾼다. 승인은 상위 대조를 거친다.', '문서 뷰'],
  ['내 할 일을 처리한다', '상위가 바뀌면 하위에 확인 필요가 붙는다. 알림은 없다 — 내 할 일 화면이 알림이다.', '내 할 일'],
  ['수정은 다시 에이전트에게', '확인하다 영향이 있으면 화면 밖에서 에이전트에게 고치게 하고 돌아와 확인한다.', '에이전트'],
]

/** 11단계와 항목 ID 형식 — SYNC-STD-001 2장의 전사. 규약이 바뀌면 여기도 바뀐다.
 *  뜻풀이는 각 절의 `필수 절`·`항목 블록`을 한 줄로 줄인 것이다 */
const STAGES: [string, string, string, string[]][] = [
  ['RFQ', '요구·인터뷰', '무엇을 왜 만드나. 고객이 말한 것만 적는다', ['Q1']],
  ['PRD', '제품 요구', '목표·비목표·요구사항. 요구에는 인수기준까지', ['G1', 'R12', 'N3']],
  ['SCN', '사용자 시나리오', '페르소나와 실제 사용 흐름', ['P1', 'S1']],
  ['UC', '유스케이스', '액터별 유스케이스. 기본 흐름과 확장', ['UC-H2', 'UC-A1']],
  ['INFRA', '인프라 아키텍처', '제약·구성도·기술 스택·데이터가 사는 곳', ['C1']],
  ['DOM', '도메인·클래스·데이터', '도메인 모델·클래스 명세·ERD를 한 단계에', ['Document', 'documents']],
  ['UI', '화면', '화면 목록·흐름·화면별 요소', ['UI-5']],
  ['API', '인터페이스', 'REST 엔드포인트와 MCP 도구', ['GET/api/docs/{docId}', 'get_doc']],
  ['SEQ', '시퀀스', '저장·판단·조회 흐름을 생명선으로', ['SEQ-12']],
  ['MS', 'MINISPEC', '함수 하나하나의 시그니처와 처리 순서', ['SpecService.save']],
  ['CODE', '구현 계획', '슬라이스와 통합 테스트, 커밋 목록', ['B2', 'D1']],
]

export function HowTo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog howto" data-el="1">
        <div className="dhead">
          <span>싱크독 사용 방법</span>
          <span className="grow" />
          <span className="x" data-el="4" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <p className="dlead">
            개발자가 PM 없이 11단계 명세 체인을 쓰고, 에이전트가 그 명세를 따르게 하는 플랫폼입니다. 쓰는 것은 에이전트, 판단하고 확정하는 것은 웹입니다.
          </p>
          <table className="grid" data-el="2">
            <tbody>
              <tr className="hd">
                <th />
                <th />
                <th />
                <th>어디서</th>
              </tr>
              {ORDER.map(([what, how, where], i) => (
                <tr key={what} data-el={i === 0 ? '2.1' : undefined}>
                  <td className="no">{i + 1}</td>
                  <td>{what}</td>
                  <td>{how}</td>
                  <td className="where">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4 className="sectitle">11단계가 뜻하는 것</h4>
          <table className="grid" data-el="3">
            <tbody>
              {STAGES.map(([code, name, what, ids], i) => (
                <tr key={code} data-el={i === 0 ? '3.1' : undefined}>
                  <td className="no">{i + 1}</td>
                  <td className="code">{code}</td>
                  <td>
                    <b>{name}</b> — {what}
                  </td>
                  <td className="ids">{ids.join(' · ')}</td>
                </tr>
              ))}
              {/* 단계 밖이라 번호가 없고 마지막에 흐리게 — SYNC-STD-001 2.12 */}
              <tr className="std" data-el="3.2">
                <td className="no">—</td>
                <td className="code">STD</td>
                <td>
                  <b>표준 (단계 밖)</b> — 명세가 아니라 명세를 쓰는 법. 싱크독 프로젝트에만 있다
                </td>
                <td className="ids">규칙 항목</td>
              </tr>
            </tbody>
          </table>

          <p className="lbl" data-el="3.3">
            오른쪽은 그 단계 문서 안에서 쓰는 항목 ID 형식. 문서 ID는 <code>{'{프로젝트코드}-{타입}-{번호}'}</code>, 항목 ID는{' '}
            <code>{'{문서ID}#{항목번호}'}</code>, 참조는 <code>{'[[항목ID]]'}</code>.
          </p>
          <p className="note" data-el="3.4">
            11단계 순서는 권장이지 강제가 아니다. 건너뛰어도 막지 않고 표시만 한다.
          </p>
        </div>
        <div className="dfoot">
          <span className="grow" />
          <button className="btn" type="button" data-el="5" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </>
  )
}
