/** UI-16 사용 방법 — SYNC-UI-002#UI-16. 상단 바에서 어느 화면 위로든 뜨는 안내 다이얼로그.
 *  1 다이얼로그 · 2 사용 순서(2.1 행) · 3 11단계 표(3.1 단계 행, 3.2 STD 행, 3.3 ID 문법, 3.4 주의, 3.5 문서 구성) · 4 ✕ · 5 닫기
 *  6 붙이는 법 표(6.1 행) · 6.2 명령 상자(주소 채움) · 6.3 그 다음 · 6.4 발급 순간 그림 · 6.5 터미널 add · 6.6 터미널 list
 *  읽기 전용이고 상태가 없다 — 어디서 열든 같은 내용이고 닫으면 원래 화면 그대로다. */

import type { ReactNode } from 'react'

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
 *  뜻풀이는 각 절의 `필수 절`·`항목 블록`을 한 줄로 줄인 것이다.
 *  다섯째(3.5 문서 구성)는 그 단계에 문서가 몇 개고 **왜 그 수인지** — 표만 보면 DOM이 왜 셋이고
 *  UI·API가 왜 둘인지 모른다. 실질/선택은 SYNC-STD-003 결정을 그대로 옮긴 것 */
const STAGES: [string, string, string, string[], ReactNode][] = [
  ['RFQ', '요구·인터뷰', '무엇을 왜 만드나. 고객이 말한 것만 적는다', ['Q1'], '문서 하나. 고객이 말한 것을 Q 항목으로'],
  ['PRD', '제품 요구', '목표·비목표·요구사항. 요구에는 인수기준까지', ['G1', 'R12', 'N3'], '문서 하나. 목표 G · 요구 R · 비목표 N'],
  ['SCN', '사용자 시나리오', '페르소나와 실제 사용 흐름', ['P1', 'S1'], '문서 하나. 페르소나 P · 시나리오 S. 선택 — 한 사람이 전체를 쥘 수 있으면 건너뛴다'],
  ['UC', '유스케이스', '액터별 유스케이스. 기본 흐름과 확장', ['UC-H2', 'UC-A1'], '문서 하나. 액터별로 — 사람 H · 에이전트 A · GitHub G · 시스템 S'],
  ['INFRA', '인프라 아키텍처', '제약·구성도·기술 스택·데이터가 사는 곳', ['C1'], '문서 하나. 앞 단계에서 확정된 제약 C가 설계를 묶는다. 선택'],
  [
    'DOM',
    '도메인·클래스·데이터',
    '도메인 모델·클래스 명세·ERD를 한 단계에',
    ['Document', 'documents'],
    <>
      <b>문서 셋.</b> 같은 것을 세 층으로 — 도메인 모델(개념 <code>Document</code>) · 클래스 명세(클래스 <code>Document</code>) · ERD·DD(테이블{' '}
      <code>documents</code>). 이름으로 서로 참조하려고 한 단계에 둔다
    </>,
  ],
  [
    'UI',
    '화면',
    '화면 목록·흐름·화면별 요소',
    ['UI-5'],
    <>
      <b>문서 둘.</b> 화면 설계(무엇이 있나 — 목록·흐름) · 와이어프레임(어떻게 생겼나 — 같은 <code>UI-5</code>의 배치·요소·규칙). 와이어프레임은 선택
    </>,
  ],
  [
    'API',
    '인터페이스',
    'REST 엔드포인트와 MCP 도구',
    ['GET/api/docs/{docId}', 'get_doc'],
    <>
      <b>문서 둘.</b> 입구가 둘이라서 — REST(사람·화면이 부르는 <code>GET/api/…</code>) · MCP(에이전트가 부르는 도구 <code>get_document</code>)
    </>,
  ],
  ['SEQ', '시퀀스', '저장·판단·조회 흐름을 생명선으로', ['SEQ-12'], '문서 하나. 함수가 아니라 흐름 단위 — 저장 하나가 시퀀스 하나. 선택'],
  [
    'MS',
    'MINISPEC',
    '함수 하나하나의 시그니처와 처리 순서',
    ['SpecService.save'],
    <>
      <b>문서 여러 개.</b> MS 문서 하나 = 클래스 명세의 절 하나 = 코드 파일 하나. 크기가 아니라 구조로 나눈다(싱크독은 9개). 선택
    </>,
  ],
  ['CODE', '구현 계획', '슬라이스와 통합 테스트, 커밋 목록', ['B2', 'D1'], '문서 하나. 슬라이스 카드 A · B1… 와 완료 기록. 코드가 아니라 코드로 가는 계획'],
]

/** 에이전트를 붙이는 손 순서 — 2의 둘째 단계를 편 것. 셋째 행을 빼지 않는다(UI-16 규칙):
 *  켜져 있던 세션에 서버가 안 보여서 잘못 넣은 줄 아는 것이, 붙이는 사람이 가장 먼저 걸리는 자리다 */
const CONNECT: [string, ReactNode, string][] = [
  ['토큰을 발급한다', '설정 → MCP 토큰 → 발급. 이름을 적는다. 원문은 그때 한 번만 보이니 바로 복사한다.', '설정'],
  [
    '터미널에서 한 줄',
    <>
      아래 명령. <code>--scope user</code>면 어느 폴더에서 켜도 붙는다. Codex·Gemini CLI는 설정의 클라이언트 설정 JSON을 각자 설정
      파일에 넣는다.
    </>,
    '터미널',
  ],
  ['Claude Code를 새로 켠다', 'MCP 서버는 세션이 시작될 때 읽힌다. 켜져 있던 창에는 방금 넣은 서버가 안 보인다 — 나갔다가 다시 켠다.', '터미널'],
  [
    '붙었는지 본다',
    <>
      <code>claude mcp list</code>에 <code>syncdoc … ✔ Connected</code>, 또는 세션 안에서 <code>/mcp</code>. claude.ai 커넥터 목록에는 안
      나온다 — 이 컴퓨터 설정에만 있는 것이 정상이다.
    </>,
    '터미널',
  ],
]

export function HowTo({ onClose }: { onClose: () => void }) {
  // 주소는 UI-13 클라이언트 설정(8.1)과 같은 원천 — 사람이 옮겨 적으면 터널 주소를 틀린다.
  // 토큰은 발급 화면에서 한 번만 보이고 서버도 다시 못 준다 — 자리표시
  const cmd = `claude mcp add --transport http --scope user syncdoc \\
    ${window.location.origin}/mcp \\
    --header "Authorization: Bearer syncdoc_pat_…"`
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

          <h4 className="sectitle">에이전트를 붙이는 법</h4>
          <table className="grid" data-el="6">
            <tbody>
              {CONNECT.map(([what, how, where], i) => (
                <tr key={what} data-el={i === 0 ? '6.1' : undefined}>
                  <td className="no">{i + 1}</td>
                  <td>{what}</td>
                  <td>{how}</td>
                  <td className="where">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* 그림은 앱 밖 화면만 — 토큰이 한 번만 보이는 순간과 터미널. 앱 화면은 한 클릭 거리고 바뀌면 낡는다 (UI-16 규칙) */}
          <figure data-el="6.4">
            <img src="/howto/token-issued.png" alt="발급 직후 — 토큰 원문이 한 번만 보이는 화면" />
            <figcaption>1. 발급 직후. 원문은 이 화면에서 한 번만 보인다 (캡처에서는 가렸다)</figcaption>
          </figure>
          <pre className="snippet" data-el="6.2">
            {cmd}
          </pre>
          <figure data-el="6.5">
            <img src="/howto/term-add.png" alt="터미널 — claude mcp add 실행 결과" />
            <figcaption>2. 붙이면 이렇게 답한다. 토큰은 [REDACTED]로 가려진다</figcaption>
          </figure>
          <figure data-el="6.6">
            <img src="/howto/term-list.png" alt="터미널 — claude mcp list에 syncdoc Connected" />
            <figcaption>
              4. 새로 켠 뒤 <code>claude mcp list</code> — 이 줄이 보이면 붙은 것이다
            </figcaption>
          </figure>
          <p className="note" data-el="6.3">
            그 뒤로는 에이전트에게 「싱크독으로 프로젝트 하나 만들어 줘」라고 말하면 된다. 주소가 바뀌면 <code>claude mcp remove syncdoc</code> 후 다시
            넣는다.
          </p>

          <h4 className="sectitle">11단계가 뜻하는 것</h4>
          <table className="grid" data-el="3">
            <tbody>
              {STAGES.map(([code, name, what, ids, docs], i) => (
                <tr key={code} data-el={i === 0 ? '3.1' : undefined}>
                  <td className="no">{i + 1}</td>
                  <td className="code">{code}</td>
                  <td>
                    <b>{name}</b> — {what}
                    <div className="sub" data-el={i === 0 ? '3.5' : undefined}>
                      {docs}
                    </div>
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
            11단계 순서는 권장이지 강제가 아니다. 건너뛰어도 막지 않고 표시만 한다. <b>여섯(RFQ·PRD·UC·DOM·API·CODE)이 실질이고 나머지는 규모가 정한다</b> —
            가르는 것은 사람 수가 아니라 「머리에 안 들어가는가」다. 빈 단계는 「미작성」으로 남아 건너뛰었다는 사실이 보인다.
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
