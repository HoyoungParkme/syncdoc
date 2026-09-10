/** UI-16 사용 방법 — SYNC-UI-002#UI-16. 상단 바에서 어느 화면 위로든 뜨는 안내 다이얼로그.
 *  1 다이얼로그 · 2 사용 순서(2.1 행) · 3 11단계 표(3.1 단계 행, 3.2 STD 행, 3.3 ID 문법, 3.4 주의) · 4 ✕ · 5 닫기
 *  읽기 전용이고 상태가 없다 — 어디서 열든 같은 내용이고 닫으면 원래 화면 그대로다. */

/** 여섯 단계. 웹에 편집이 없다는 것을 3에서 말한다 — 처음 온 사람이 가장 자주 헤매는 지점이다 */
const ORDER: [string, string, string][] = [
  ['저장소를 등록한다', '주소·코드·이름', '프로젝트 목록'],
  ['에이전트를 붙인다', 'MCP 토큰 발급 후 설정에 붙여넣기', '설정'],
  ['명세를 쌓는다', '에이전트에게 시킨다. 웹에는 편집이 없다', '에이전트'],
  ['읽고 확정한다', '상태를 초안 → 검토중 → 승인으로', '문서 뷰'],
  ['바뀐 것을 따라간다', '전파 선택, 확인 필요 처리', '내 할 일'],
  ['체인을 본다', '참조 그래프에서 노드 클릭', '참조 그래프'],
]

/** 11단계와 항목 ID 형식 — SYNC-STD-001 2장의 전사. 규약이 바뀌면 여기도 바뀐다 */
const STAGES: [string, string, string[]][] = [
  ['RFQ', '요구·인터뷰', ['Q1']],
  ['PRD', '제품 요구', ['G1', 'R12', 'N3']],
  ['SCN', '사용자 시나리오', ['P1', 'S1']],
  ['UC', '유스케이스', ['UC-H2', 'UC-A1']],
  ['INFRA', '인프라 아키텍처', ['C1']],
  ['DOM', '도메인·클래스·데이터', ['Document', 'documents']],
  ['UI', '화면', ['UI-5']],
  ['API', '인터페이스', ['GET/api/docs/{docId}', 'get_doc']],
  ['SEQ', '시퀀스', ['SEQ-12']],
  ['MS', 'MINISPEC', ['SpecService.save']],
  ['CODE', '구현 계획', ['B2', 'D1']],
]

export function HowTo({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog howto" data-el="1">
        <div className="dhead">
          <span>사용 방법</span>
          <span className="grow" />
          <span className="x" data-el="4" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <table className="grid" data-el="2">
            <tbody>
              <tr className="hd">
                <th />
                <th>무엇</th>
                <th>어떻게</th>
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

          <table className="grid" data-el="3">
            <tbody>
              <tr className="hd">
                <th>#</th>
                <th>코드</th>
                <th>이름</th>
                <th>항목 ID</th>
              </tr>
              {STAGES.map(([code, name, ids], i) => (
                <tr key={code} data-el={i === 0 ? '3.1' : undefined}>
                  <td className="no">{i + 1}</td>
                  <td className="code">{code}</td>
                  <td>{name}</td>
                  <td>
                    {ids.map((id) => (
                      <code key={id}>{id}</code>
                    ))}
                  </td>
                </tr>
              ))}
              {/* 단계 밖이라 번호가 없고 마지막에 흐리게 — SYNC-STD-001 2.12 */}
              <tr className="std" data-el="3.2">
                <td className="no">—</td>
                <td className="code">STD</td>
                <td>표준 (단계 밖)</td>
                <td>규칙 항목</td>
              </tr>
            </tbody>
          </table>

          <p className="lbl" data-el="3.3">
            문서 ID는 <code>{'{프로젝트코드}-{타입}-{번호}'}</code>, 항목 ID는 <code>{'{문서ID}#{항목번호}'}</code>, 본문 참조는{' '}
            <code>{'[[항목ID]]'}</code>.
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
