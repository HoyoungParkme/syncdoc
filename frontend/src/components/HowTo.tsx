/** UI-16 사용 방법 — SYNC-UI-002#UI-16. 상단 바에서 어느 화면 위로든 뜨는 안내 다이얼로그.
 *  1 다이얼로그 · 2 사용 순서(2.1 행) · 3 11단계 표(3.1 단계 행, 3.2 STD 행, 3.3 ID 문법, 3.4 주의, 3.5 문서 구성) · 4 ✕ · 5 닫기
 *  6 붙이는 법 표(6.1 행) · 6.2 명령 상자(주소 채움) · 6.3 그 다음 · 6.4 발급 순간 그림 · 6.5 터미널 add · 6.6 터미널 list
 *  읽기 전용이고 상태가 없다 — 어디서 열든 같은 내용이고 닫으면 원래 화면 그대로다. */

import type { ReactNode } from 'react'

/** 여섯 단계. 웹에 편집이 없다는 것을 3에서 말한다 — 처음 온 사람이 가장 자주 헤매는 지점이다 */
const ORDER: [string, string, string][] = [
  ['저장소를 등록한다', '명세 원본은 저장소의 docs/specs/에 둔다. 프로젝트 하나가 저장소 하나다. 초기화는 빈 단계 폴더와 README 하나만 커밋한다 — 규약·템플릿 사본은 넣지 않고 README가 싱크독 저장소를 링크로 가리킨다.', '프로젝트 목록'],
  ['에이전트를 붙인다', '설정에서 MCP 토큰을 발급해 Claude Code·Codex·Gemini에 넣는다. 클라이언트는 상관없다.', '설정'],
  ['에이전트와 대화하며 명세를 쓴다', '명세 본문이 들어오는 길은 MCP와 GitHub push 둘뿐이다. 웹에는 편집 화면이 없다. 커밋·PR에 에이전트 표시(Co-Authored-By 등)는 남기지 않는다.', '에이전트'],
  ['웹에서 읽고 완료로 올린다', '유저용 탭으로 읽고, 참조를 따라가고, 다 됐으면 완료로 올린다. 규약 오류·미완성·끊어진 참조가 있으면 막힌다.', '문서 뷰'],
  ['끊어진 것을 잡는다', '상위 항목이 사라지면 하위 참조가 끊어진 참조로 보인다. 알림은 없다 — 프로젝트 상세의 수치가 알림이다.', '프로젝트 상세'],
  ['수정은 다시 에이전트에게', '확인하다 영향이 있으면 화면 밖에서 에이전트에게 고치게 하고 돌아와 확인한다.', '에이전트'],
]

/** 11단계와 항목 ID 형식 — SYNC-STD-001 2장의 전사. 규약이 바뀌면 여기도 바뀐다.
 *  뜻풀이는 각 절의 `필수 절`·`항목 블록`을 한 줄로 줄인 것이다.
 *  docs(3.5 문서 구성)는 그 단계에 문서가 몇 개고 **왜 그 수인지** — 줄글로 쓰지 않는다(UI-16 규칙):
 *  수는 라벨, 문서는 줄마다 하나, 선택은 태그. 실질/선택은 SYNC-STD-003 결정을 그대로 옮긴 것 */
type Docs = { n: string; why: ReactNode; list?: [string, ReactNode, boolean?][]; opt?: boolean }
const STAGES: [string, string, string, string[], Docs][] = [
  ['RFQ', '요구·인터뷰', '무엇을 왜 만드나. 고객이 말한 것만 적는다', ['Q1'], { n: '1', why: '고객이 말한 것 → Q 항목' }],
  ['PRD', '제품 요구', '목표·비목표·요구사항. 요구에는 인수기준까지', ['G1', 'R12', 'N3'], { n: '1', why: '목표 G · 요구 R · 비목표 N' }],
  ['SCN', '사용자 시나리오', '페르소나와 실제 사용 흐름', ['P1', 'S1'], { n: '1', why: '페르소나 P · 시나리오 S', opt: true }],
  ['UC', '유스케이스', '액터별 유스케이스. 기본 흐름과 확장', ['UC-H2', 'UC-A1'], { n: '1', why: '액터별 — 사람 H · 에이전트 A · GitHub G · 시스템 S' }],
  ['INFRA', '인프라 아키텍처', '제약·구성도·기술 스택·데이터가 사는 곳', ['C1'], { n: '1', why: '앞 단계에서 확정된 제약 C', opt: true }],
  [
    'DOM',
    '도메인·클래스·데이터',
    '도메인 모델·클래스 명세·ERD를 한 단계에',
    ['Document', 'documents'],
    {
      n: '3',
      why: (
        <>
          같은 것을 세 층으로. 이름으로 서로 참조한다 — <b>한 번에 쓰지 않는다</b>
        </>
      ),
      // 셋은 순서가 있고 사이에 다른 단계가 낀다 (STD-001 2.6) — 줄마다 언제 쓰는지
      list: [
        ['도메인 모델', <>개념 <code>Document</code> · 여기서</>],
        [
          '클래스 명세',
          <>
            클래스 <code>Document</code> · <b>8 API 뒤에</b> 돌아와서
          </>,
        ],
        ['ERD·DD', <>테이블 <code>documents</code> · 클래스 명세 뒤에</>],
      ],
    },
  ],
  [
    'UI',
    '화면',
    '화면 목록·흐름·화면별 요소',
    ['UI-5'],
    {
      // 규약은 「하나 또는 둘」이다 — 한 문서에 다 써도 된다 (STD-001 2.7, 카드 AE)
      n: '1~2',
      why: '한 문서에 다 써도 되고, 무엇이 있나 / 어떻게 생겼나로 나눠도 된다',
      list: [
        ['화면 설계', <>목록·흐름 <code>UI-5</code></>],
        ['와이어프레임', <>같은 <code>UI-5</code>의 배치·요소·규칙 — 배치는 디자인 도구 산출물(자기 완결 html)을 그대로</>, true],
      ],
    },
  ],
  [
    'API',
    '인터페이스',
    'REST 엔드포인트와 MCP 도구',
    ['GET/api/docs/{docId}', 'get_doc'],
    {
      n: '2',
      why: '입구가 둘',
      list: [
        ['REST', <>사람·화면이 부른다 <code>GET/api/…</code></>],
        ['MCP', <>에이전트가 부른다 <code>get_document</code></>],
      ],
    },
  ],
  ['SEQ', '시퀀스', '저장·판단·조회 흐름을 생명선으로', ['SEQ-12'], { n: '1', why: '저장 하나 = 시퀀스 하나', opt: true }],
  ['MS', 'MINISPEC', '함수 하나하나의 시그니처와 처리 순서', ['SpecService.save'], { n: 'N', why: 'MS 하나 = 클래스 명세 절 하나 = 코드 파일 하나 (싱크독 9개)', opt: true }],
  ['CODE', '구현 계획', '슬라이스와 통합 테스트, 커밋 목록', ['B2', 'D1'], { n: '1', why: '슬라이스 카드 A · B1… 와 완료 기록' }],
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
                      <span className="cnt">문서 {docs.n}</span> {docs.why}
                      {docs.opt && <span className="tag">선택</span>}
                      {docs.list && (
                        <ul className="docs">
                          {docs.list.map(([name, ex, opt]) => (
                            <li key={name}>
                              <b>{name}</b> — {ex}
                              {opt && <span className="tag">선택</span>}
                            </li>
                          ))}
                        </ul>
                      )}
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
                  <b>표준 (단계 밖)</b> — 명세가 아니라 명세를 쓰는 법. 싱크독 저장소에만 있고, 새 저장소의 README가 링크로 가리킨다
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
            11단계 순서는 권장이지 강제가 아니다. 건너뛰어도 막지 않고 표시만 한다 — DOM 셋의 순서만 예외다(클래스 명세는 API 뒤, ERD는 클래스 명세 뒤).{' '}
            <b>여섯(RFQ·PRD·UC·DOM·API·CODE)이 실질이고 나머지는 규모가 정한다</b> —
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
