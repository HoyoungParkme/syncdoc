---
doc_id: SYNC-UI-002
type: UI
title: 와이어프레임 — 싱크독
status: draft
upstream: [SYNC-UI-001]
---

# 와이어프레임: 싱크독 (SyncDoc)

---

## 0. 형식

화면마다 절 하나. 각 절은 네 부분이다.

| 부분 | 무엇 | 형태 |
|---|---|---|
| 배치 | 요소가 어디 있나 | HTML 뼈대. 요소마다 `data-el` 번호. 스타일 없음 |
| 요소 | 각 요소가 뭘 보여주고 누르면 뭐 되나 | 표 |
| 규칙 | 상태별 표시, 조건부 노출, 유효성 | 목록 |
| 시나리오 | 요소들이 이어져 무엇을 이루나 | 번호 매긴 흐름. 유스케이스 흐름을 이 화면 동작으로 옮긴 것 |

사람용 뷰는 배치를 왼쪽에, 요소·규칙·시나리오를 오른쪽에 나란히 렌더링한다. 요소 번호를 누르면 양쪽이 서로 강조된다.

**공통 틀**(상단 바)은 UI-5에서 한 번 정의하고 다른 화면에서는 생략한다. 여러 화면이 같이 쓰는 조각은 1장 공통 컴포넌트에 모았다.

**색·글꼴·간격 값은 여기 없다.** [[SYNC-UI-001]] 3장 디자인 토큰이 원본이다. 이 문서는 무엇이 어디 있고 누르면 뭐가 되는지만 정한다.

**UI-6 원본 편집은 v0.2에서 삭제됐다.** 그려보니 명세에 없는 기능(실시간 검사 등)을 끌어들이게 되고, 명세대로 그려도 사람이 손으로 검사·충돌·삭제를 다루는 화면이 되어 에이전트가 쓰는 흐름과 어긋났다. 이 판단이 화면 설계로 되먹임되어 UI-6이 빠졌다.

---

## 1. 공통 컴포넌트

화면마다 다시 그리지 않는 것들. 여기서 한 번 정하고 각 절에서는 이름만 부른다.
값은 [[SYNC-UI-001]] 3장 토큰을 쓴다.

### 1.1 다이얼로그

오버레이 위 흰 카드. 머리·본문·발 세 층이고 본문만 스크롤한다.

- 머리: 제목 · 메타 · 닫기(`✕`)
- 발: 왼쪽에 힌트 텍스트, 오른쪽에 취소·확인 버튼
- 바깥을 누르면 닫힌다. 카드 안 클릭은 바깥으로 새지 않는다
- **확인 버튼의 라벨이 상태를 말한다.** `어긋난 곳 없음 · 승인` / `어긋남 2건 표시하고 승인`처럼, 누르면 무슨 일이 생기는지 버튼에 적는다
- 다이얼로그 위에 다이얼로그가 뜰 수 있다 — UI-13 위의 재구축 확인이 그렇다

지금 쓰는 곳: UI-3 초기화 · UI-3 기존 명세 발견 · UI-4 목록 · UI-5 상위 대조 · UI-7 되돌리기 · UI-7 삭제 확인 · UI-12 전파 선택 · UI-13 설정 · UI-14 재구축 확인 · UI-15 11단계 흐름 · UI-16 사용 방법.

### 1.2 툴팁

브라우저 기본 툴팁을 쓰지 않는다. 줄바꿈이 안 되고 지연이 길다.

- 대상 위쪽 가운데. 흰 배경, 테두리, 그림자
- 마우스를 통과시킨다 — 툴팁이 대상을 가려 클릭을 막으면 안 된다
- **사라지는 조건이 마우스가 벗어날 때만이면 부족하다.** 클릭으로 대상이 사라지면 툴팁만 남는다. 화면 이동·스크롤·아무 곳 클릭에도 지운다

### 1.3 토스트

화면 아래 가운데. 잉크색 바탕에 흰 글씨. 2.6초 뒤 스스로 사라진다.

되돌릴 수 없는 일이 **끝났을 때** 무엇이 기록됐는지 알린다 — 확인 처리, 전파 결정, 토큰 폐기, 재구축 완료. 누를 것이 없으므로 확인을 요구하는 데는 쓰지 않는다.

### 1.4 상태 필

`초안` · `검토중` · `승인` 셋. 상태색 바탕에 작은 알약. 승인만 글씨가 희다.

문서 상태를 보여주는 곳이면 어디든 같은 모양이다. 단계 대표 상태에도 같은 것을 쓴다.

### 1.5 항목 ID 뱃지

`R12` 같은 항목 ID를 감싸는 작은 사각 뱃지. 고정폭 글꼴, 검토중 색 바탕.

**항목 ID는 늘 뱃지로 감싼다.** 본문 글자와 섞이면 어디까지가 ID인지 안 보인다. 참조 표기(`[[…]]`)는 뱃지가 아니라 점선 밑줄이다 — 누르면 이동한다는 뜻이 다르다.

---

## UI-5 문서 뷰

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-5]] |
| 경로 | `/p/{프로젝트코드}/d/{문서ID}` · 원본 탭은 `?tab=raw` |
| 진입 | UI-4 문서 클릭 · UI-8 노드 클릭 · 다른 문서의 참조 링크 · UI-10 댓글·규약 오류·끊어진 참조 행 |
| 유스케이스 | [[SYNC-UC-001#UC-H2]] [[SYNC-UC-001#UC-H3]] [[SYNC-UC-001#UC-H8]] [[SYNC-UC-001#UC-H9]] |

### 배치

```html
<div class="topbar"><!-- 공통 틀. SYNC-UI-001 4장 -->
  <strong>싱크독</strong>
  <span class="grow"></span>
  <span class="btn">사용 방법</span>
  <span class="btn">내 할 일 <span class="badge">3</span></span>
  <span class="btn">설정</span>
  <span class="btn">로그아웃</span>
</div>

<div class="docbar" data-el="1"><!-- 브레드크럼. 어디서 들어왔든 지금 자리를 말한다 -->
  <span class="crumb">싱크독</span><span class="sep">›</span>
  <span class="crumb mono">2 PRD</span><span class="sep">›</span>
  <b class="mono">SYNC-PRD-001</b>
  <span class="pill pill-approved" data-el="1.1">승인</span>
  <span class="ver mono" data-el="1.2">v7</span>
  <span class="grow"></span>
  <span data-el="5" class="lbl">미해결 댓글 2</span>
  <span class="btn" data-el="3">상태 변경 ▾</span>
</div>

<!-- 3단. 화면 높이를 채우고 가운데 열만 스크롤한다. 탭을 바꿔도 이 틀은 그대로다 -->
<div class="body3" data-el="7">
  <nav class="toc" data-el="6">
    <div class="lbl">목차</div>
    <div>1. 목표</div>
    <div>2. 비목표</div>
    <div>3. 요구사항</div>
    <div class="d1">R1 에이전트용 원본과 사람용 뷰</div>
    <div class="d1">R2 ID 기반 상호참조</div>
    <div>4. 성공지표</div>
    <div class="marked" data-el="6.1">
      <div class="lbl">표시된 항목</div>
      <div><span class="dot flag"></span> R1 <span class="lbl">확인 필요</span></div>
      <div><span class="dot cm"></span> R2 <span class="lbl">미해결 댓글 2</span></div>
    </div>
  </nav>
  <div class="handle" data-el="6.2"></div>

  <div class="mainwrap"><!-- 안쪽 max-width는 세 탭이 같다 -->
    <div class="tabs" data-el="2"><!-- 본문 폭 안, 밑줄로 구분. 원본일 때만 오른쪽에 10.3·10.4·10.2 -->
      <span class="on" data-el="2.1">유저용</span><span data-el="2.2">원본</span><span data-el="2.3">이력</span>
    </div>
    <div class="banner" data-el="4">⚠ 규약 오류: frontmatter.status 누락 (커밋 a1b2c3 · 김민준)</div>
    <div class="banner warn" data-el="4a">미완성: 필수 절 「성공지표」 없음 · 승인 불가</div>

    <div class="dochead"><!-- 킥커·제목·리드. 본문(7)은 innerHTML로 갈아 끼워서 형제로 둔다 -->
      <div class="kicker mono">싱크독 · 2단계 PRD</div>
      <h1>PRD — 싱크독</h1>
      <p class="lead">바이브코딩 시대에 개발자가 PM 없이 11단계 명세 체인을 쓰고, 에이전트가 그 명세를 따르게 하는 플랫폼.</p>
    </div>

    <article class="main" data-el="7">
      <h2>3. 요구사항</h2>
      <div class="item" data-el="7.1"><span class="id">#R1</span>에이전트용 원본과 사람용 뷰 <span class="flag">확인 필요</span></div>
      <p class="line">명세는 규약이 있는 Markdown으로 작성한다. 근거: <span class="ref" data-el="7.2">[[SYNC-RFQ-001#Q03]]</span><span class="cbtn" data-el="7.4">+</span></p>
      <p class="line">사람용 뷰는 원본에서 파생 생성한다.<span class="cbtn has">2</span></p>
      <div class="item"><span class="id">#R2</span>ID 기반 상호참조</div>
      <p class="line">본문에서 <span class="ref">[[SYNC-DOM-001#참조]]</span>로 참조하면 관계가 추출된다.<span class="cbtn">+</span></p>
      <div class="diagram" data-el="7.3"><div class="img">mermaid 렌더링 결과 (브라우저)</div></div>
    </article>

    <div class="docnav" data-el="9"><!-- 본문 열 안, 본문과 같은 폭 -->
      <span class="btn">← SYNC-RFQ-001</span>
      <span class="btn">SYNC-SCN-001 →</span>
    </div>
  </div>

  <div class="handle" data-el="8.3"></div>
  <aside class="panel" data-el="8">
    <div class="ptabs"><span class="on" data-el="8.1">참조</span><span data-el="8.2">댓글 2</span></div>
    <div class="pbody">
      <div class="lbl">선택</div>
      <div class="selitem"><span class="idbadge">R1</span> 에이전트용 원본과 사람용 뷰</div>
      <div class="lbl">상위 참조 (근거)</div>
      <div class="rcard"><b class="mono">SYNC-RFQ-001#Q03</b><div class="lbl">명세를 어디에 어떤 형식으로 두나</div></div>
      <div class="lbl">하위 참조 (파생) 2</div>
      <div class="rcard"><b class="mono">SYNC-UC-001#UC-A6</b><div class="lbl">명세를 작성·수정한다</div></div>
      <div class="rcard flagged"><b class="mono">SYNC-UC-001#UC-H2</b> <span class="flag">확인 필요</span><div class="lbl">문서를 읽는다</div></div>
      <div class="lbl">플래그</div>
      <div class="rcard flagged"><b>확인 필요</b><div class="lbl">원인 <span class="mono">SYNC-RFQ-001#Q03</span> v4 · 3일 전</div></div>
    </div>
  </aside>
</div>

<!-- 원본 탭 — 3단 틀은 그대로고 본문 열만 바뀐다 -->
<div class="mainwrap" data-el="10">
  <div class="tabs" data-el="2">
    <span data-el="2.1">유저용</span><span class="on" data-el="2.2">원본</span><span data-el="2.3">이력</span>
    <span class="grow"></span>
    <span class="radios"><span class="radio on" data-el="10.3">원문</span><span class="radio" data-el="10.4">렌더링</span></span>
    <span class="btn" data-el="10.2">복사</span>
  </div>
  <div class="editor" data-el="10.1">
    <div class="gutter"><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span><span>7</span><span>8</span></div>
    <pre class="code">---
doc_id: SYNC-PRD-001
type: PRD
status: approved
---
#### R1 에이전트용 원본과 사람용 뷰
명세는 규약이 있는 Markdown으로 작성한다. 근거: [[SYNC-RFQ-001#Q03]]
사람용 뷰는 원본에서 파생 생성한다.</pre>
  </div>
</div>

<!-- 승인 시 상위 대조 -->
<div class="dialog" data-el="11">
  <div class="dhead">승인 전 상위 대조 — SYNC-API-002</div>
  <div class="dbody">
    이 문서가 근거로 삼은 상위 항목입니다. 이 문서의 내용과 <b>어긋난 것</b>이 있으면 표시하세요. 표시한 항목에 <b>하위 불일치</b> 플래그가 붙어 상위 담당자에게 갑니다.
    <table class="uptbl" data-el="11.1">
      <tr><th></th><th>상위 항목</th><th>현재</th><th>참조한 곳</th></tr>
      <tr data-el="11.2"><td><input type="checkbox" checked></td><td><b>SYNC-UC-001#UC-A6</b> 명세를 작성·수정한다</td><td>v9 · 승인</td><td>update_document</td></tr>
      <tr><td></td><td><b>SYNC-UC-001#UC-A1</b> 프로젝트를 초기화한다</td><td>v9 · 승인</td><td>init_project</td></tr>
      <tr><td></td><td><b>SYNC-DOM-002#SpecService</b></td><td>v3 · 검토중</td><td>get_document 외 4</td></tr>
      <tr><td></td><td><b>SYNC-STD-001</b> (문서 전체)</td><td>v2 · 승인</td><td>frontmatter upstream</td></tr>
    </table>
    <div class="dacts"><span class="btn" data-el="11.4">닫기</span> <span class="btn" data-el="11.3" style="font-weight:600">어긋남 1건 표시하고 승인</span></div>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 문서 바 | 영역 | 브레드크럼 `프로젝트 › 단계 › 문서 ID`, 상태(1.1), 버전(1.2). 앞 두 조각은 눌러서 되짚어 올라간다 | — |
| 1.1 | 상태 | 뱃지 | `초안`·`검토중`·`승인`. 색으로 구분 | — |
| 1.2 | 버전 | 텍스트 | 현재 버전 번호 | 이력(UI-7)으로 |
| 2 | 탭 | 탭 | 유저용(기본)·원본·이력. **본문 안 맨 위**, 본문과 같은 폭. 활성 탭만 굵고 아래 2px 잉크선 | — |
| 2.1 | 유저용 | 탭 | 사람용 뷰(7) | 본문 영역을 7로 |
| 2.2 | 원본 | 탭 | 에이전트가 읽는 MD(10) | 본문 영역을 10으로 |
| 2.3 | 이력 | 탭 | | UI-7로 |
| 3 | 상태 변경 | 드롭다운 | 갈 수 있는 상태 | 고르면 변경(UC-H8). `승인`이면 상위 대조 다이얼로그(11)를 거친다. 규약 오류(4)가 있으면 비활성 |
| 4 | 규약 오류 배너 | 배너 | 어긴 규약, 커밋, 작성자. 오류 없으면 안 보임. 고치려면 에이전트에게 | — |
| 4a | 미완성 배너 | 배너 | 필수 절 누락 등 미완성 경고(STD-001 4장). 규약 오류와 색이 다르다. 저장은 됐고 승인만 막힘 | — |
| 5 | 미해결 댓글 수 | 텍스트 | 이 문서의 미해결 댓글 개수. 0이면 안 보임 | 패널(8) 댓글 탭 |
| 6 | 목차 | 목록 | 절 제목과 그 아래 항목. 항목은 한 칸 들여 흐리게. 각 줄은 한 줄로 자른다 | 본문 해당 위치로 스크롤 |
| 6.1 | 표시된 항목 | 목록 | 플래그나 미해결 댓글이 붙은 항목만. 색 점 · 항목 ID · 종류. 하나도 없으면 블록 자체가 안 보인다 | 본문 해당 항목으로 스크롤하고 패널(8)을 연다 |
| 6.2 | 사이드바 경계 | 손잡이 | 좌측 폭을 끈다. 140~400px | — |
| 7 | 유저용 본문 | 영역 | 사람용 뷰로 렌더링된 원본. 목차·본문·패널 3단 | — |
| 7.1 | 항목 헤더 | 행 | 항목 ID, 제목, 플래그 뱃지(있으면) | 패널(8) 참조 탭에 이 항목의 상위·하위·플래그 |
| 7.2 | 참조 링크 | 링크 | `[[…]]` | 그 문서의 UI-5로 이동, 해당 항목 위치. 미존재 참조면 이동 안 하고 경고 |
| 7.3 | 다이어그램 | 그림 | mermaid 코드블록을 브라우저가 렌더링. 문법 오류면 원본 코드와 오류 메시지 | — |
| 7.4 | 댓글 버튼 | 버튼 | `+` 또는 댓글 개수 | 패널(8) 댓글 탭에 이 줄 스레드. 없으면 새 댓글 입력 |
| 8 | 오른쪽 패널 | 영역 | 참조 탭(8.1) / 댓글 탭(8.2). 유저용 탭에서만 | — |
| 8.3 | 패널 경계 | 손잡이 | 우측 폭을 끈다. 180~460px | — |
| 8.1 | 참조 탭 | 패널 | 선택 항목의 상위 참조·하위 참조·플래그(원인 항목 링크, UC-H2 2c) | 참조·원인 클릭 → 7.2와 같음 |
| 8.2 | 댓글 탭 | 패널 | 선택 줄의 스레드. 답글·해결됨 | 해결됨 → 5번 개수 줄어듦 |
| 9 | 단계 이동 | 버튼 2개 | 이전·다음 단계 문서 ID. 없으면 비활성 | 그 문서의 UI-5 |
| 10 | 원본 본문 | 영역 | 원본 MD 그대로. 줄 번호. 3단 틀은 유저용과 같고 본문 열만 바뀐다 | — |
| 10.1 | MD 텍스트 | 읽기 전용 텍스트 | 저장소의 파일 내용 그대로 | 선택·복사만. 편집 불가 |
| 10.2 | 복사 | 버튼 | | 전체 원본을 클립보드로. 에이전트에게 붙여넣는 용도 |
| 10.3 | 원문 | 라디오 | 줄번호 거터와 MD 그대로(기본). 탭 줄(2) 오른쪽에 복사(10.2)와 함께 놓인다 | 본문을 원문으로 |
| 10.4 | 렌더링 | 라디오 | 같은 MD를 파싱해 그린 것. frontmatter는 회색 블록, 절·항목·체크박스·인라인 코드·참조를 구분해 보여준다 | 본문을 렌더링으로 |
| 11 | 상위 대조 | 다이얼로그 | `승인`으로 갈 때만. 이 문서가 참조하는 상위 항목 전부(UC-H8 3) | — |
| 11.1 | 상위 항목 표 | 표 | 항목·현재 버전과 상태·이 문서에서 참조한 곳 | 항목 클릭 → 새 탭으로 그 문서 UI-5 |
| 11.2 | 어긋남 체크 | 체크박스 | 행마다 | 체크한 항목에 `하위 불일치` 플래그 |
| 11.3 | 승인 | 버튼 | 체크 수를 버튼에 표시. 0이면 "어긋난 곳 없음 · 승인" | 상태 변경 + 체크한 상위에 플래그(UC-S4). UI-5 갱신 |
| 11.4 | 닫기 | 버튼 | | 승인하지 않음(UC-H8 3b) |

### 규칙
- URL로 진입 상태를 정한다 — `#item-X`는 그 항목으로 스크롤하고 선택해 참조 패널(8.1)을 연다. `?panel=comments`는 댓글 탭(8.2)을 연다. 내 할 일(UI-10) 행이 이걸로 들어온다

- 유저용(2.1)이 기본. 원본(2.2)은 URL `?tab=raw`로 직접 열 수도 있다
- 원본 탭(10)에서도 목차(6)와 패널(8)은 그대로다. 탭을 오갈 때 3단 틀이 흔들리지 않아야 한다. 원본 본문에는 항목 클릭·댓글 버튼이 없을 뿐이다
- **세 탭의 본문 최대 폭이 같아야 한다.** 다르면 탭을 오갈 때 가운데 정렬된 본문이 좌우로 흔들린다([[SYNC-UI-001#UI-5]] 4.1)
- 사이드바 폭(6.2·8.3)은 사람마다 기억한다. 화면을 옮겨도 유지된다. 기본 좌 186px · 우 250px, 손잡이는 폭 9px에 좌우 -4px 물림(누르기 쉬우면서 자리는 1px만 먹는다)
- 사이드바 바탕은 `배경 보조`다. 본문 흰색과 갈라 놔야 어디가 읽는 곳인지 바로 보인다
- **3단은 화면 높이를 채우고 가운데 열만 스크롤한다.** 목차와 패널은 각자 안에서 스크롤하고 페이지 자체는 스크롤하지 않는다([[SYNC-UI-001#4]] 앱 셸)
- 목차 줄은 한 줄로 자르고 넘치면 말줄임한다. 항목 제목이 길어도 아래 `표시된 항목`(6.1)이 화면 밖으로 밀려나지 않아야 한다
- 배너(4·4a)와 단계 이동(9)은 본문 열 안, 본문과 같은 폭이다. 밖에 두면 본문 왼쪽 끝과 어긋난다
- 유저용 본문 맨 위에 **문서 머리** 세 줄을 얹는다 — 킥커(`프로젝트 · n단계 타입`, 단계 밖이면 `단계 밖 STD`) · 제목(frontmatter `title`) · 리드(원본 0장 첫 문단). 원본 탭(10)에는 없다. 원본은 파일 그대로를 보는 화면이다
- 원문/렌더링(10.3·10.4) 선택도 기억한다. 원본을 보는 사람은 대개 같은 쪽만 본다
- 7.1 클릭은 패널을 참조 탭으로, 7.4 클릭은 댓글 탭으로 자동 전환
- 처음 열면 패널(8)은 참조 탭이고 "항목을 선택하세요"
- 규약 오류(4)가 있으면 3(상태 변경)이 비활성이고 배너에 이유 표시. 미완성(4a)이면 3에서 `승인`만 비활성. 배너는 유저용·원본 양쪽에 보인다
- `승인`은 상위 대조(11)를 건너뛸 수 없다. 상위 항목이 하나도 없는 문서(RFQ)는 다이얼로그가 "상위 없음"으로 뜨고 바로 승인
- 참조 링크(7.2)가 미존재 참조면 회색 + 경고 아이콘, 클릭해도 이동 없음
- 다이어그램(7.3)은 편집·내려받기가 없다. 고치려면 원본의 코드블록을 에이전트에게 고치게 한다

### 시나리오

**S-1 항목의 근거를 따라간다** — UC-H3
1. 항목 헤더(7.1)를 클릭한다
2. 패널(8)이 참조 탭(8.1)으로 바뀌고 상위·하위 참조가 뜬다
3. 상위 참조를 클릭하면 그 문서의 UI-5로 이동해 해당 항목 위치에서 열린다
4. 브라우저 뒤로 가기로 원래 문서로 돌아온다

**S-2 문서를 확정한다** — UC-H8
1. 미해결 댓글 수(5)를 확인한다. 있으면 패널 댓글 탭에서 처리한다
2. 상태 변경(3)에서 `승인`을 고른다
3. 상위 대조(11)가 뜬다. 상위 항목 넷을 하나씩 열어 본다
4. UC-A6가 이 문서와 어긋난다 — 체크(11.2)한다
5. "어긋남 1건 표시하고 승인"(11.3)을 누른다. 상태(1.1)가 `승인`으로, UC-A6에 `하위 불일치` 플래그가 붙는다

**S-3 댓글을 단다** — UC-H9
1. 본문 줄 옆 댓글 버튼(7.4)을 클릭한다
2. 패널(8)이 댓글 탭(8.2)으로 바뀌고 입력창이 뜬다
3. 입력하고 저장하면 7.4가 `+`에서 개수로 바뀌고 5번이 1 늘어난다

**S-4 에이전트에게 줄 원본을 확인한다** — UC-H2 기본 흐름 4
1. 원본 탭(2.2)을 누른다
2. 본문 영역이 원본(10)으로 바뀌고 MD가 줄 번호와 함께 보인다
3. 복사(10.2)를 누르면 전체가 클립보드에 들어간다
4. 자기 에이전트에 붙여넣거나, 에이전트가 MCP로 직접 읽게 한다

---

## UI-4 프로젝트 상세

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-4]] |
| 경로 | `/p/{프로젝트코드}` |
| 진입 | UI-2 행 클릭 · 상단 바 프로젝트 선택 |
| 유스케이스 | [[SYNC-UC-001#UC-H14]] 기본 흐름 3·4, 확장 1a·1b·3a |

### 배치

```html
<div class="phead" data-el="1">
  <div>
    <div><b class="mono" data-el="1.1">SYNC</b> <span data-el="1.2">싱크독</span></div>
    <a class="repo mono" data-el="1.3">github.com/dfocus/syncdoc</a>
  </div>
  <span class="grow"></span>
  <span class="btn" data-el="2.1">참조 그래프</span>
  <span class="btn" data-el="2.2">순서대로 읽기</span>
</div>

<div class="stats" data-el="3"><!-- 여섯 칸. 0이면 흐리게, 1 이상이면 경고색 + 경고 테두리 -->
  <span class="stat" data-el="3.1"><b>4</b> 확인 필요</span>
  <span class="stat" data-el="3.2"><b>1</b> 끊어진 참조</span>
  <span class="stat" data-el="3.6"><b>1</b> 하위 불일치</span>
  <span class="stat" data-el="3.3"><b>2</b> 미해결 댓글</span>
  <span class="stat" data-el="3.4"><b>1</b> 규약 오류</span>
  <span class="stat dim" data-el="3.5"><b>0</b> 미완성</span>
</div>

<div class="body2">
  <div class="stages" data-el="4">
    <div class="stgh"><!-- 머리에 미니 히트맵 11칸 — UI-2에서 본 그 프로젝트 행이 여기 다시 있다 -->
      <b>11단계</b><span class="grow"></span>
      <i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i>
      <i class="sw rv"></i><i class="sw rv"></i><i class="sw rv"></i><i class="sw rv"></i><i class="sw dr"></i><i class="sw dr"></i>
    </div>

    <div class="stg" data-el="4.1">
      <span class="no mono">1</span><span class="nm">RFQ</span>
      <span class="st ok">승인</span><span class="grow"></span>
      <span class="lbl">1개</span><span class="caret">▾</span>
    </div>
    <div class="doc" data-el="4.2">
      <span class="mono">SYNC-RFQ-001</span><span class="dot ok"></span>
      <span class="lbl">승인 · v3 · 2일 전 · 박호영</span>
    </div>

    <div class="stg">
      <span class="no mono">7</span><span class="nm">화면</span>
      <span class="st rv">검토중</span><span class="gate" data-el="4.3">상위 미승인</span>
      <span class="grow"></span><span class="lbl">2개</span><span class="caret">▸</span>
    </div>
    <div class="doc">
      <span class="mono">SYNC-UI-002</span><span class="dot rv"></span>
      <span class="lbl">검토중 · v2 · 3시간 전 · 에이전트(김민준)</span>
      <span class="grow"></span>
      <span class="flag">확인 필요 2</span><span class="cm">댓글 2</span>
    </div>

    <div class="stg" data-el="4.4">
      <span class="no mono">—</span><span class="nm">표준 (STD)</span>
      <span class="st dr">초안</span><span class="grow"></span>
      <span class="lbl">4개</span><span class="caret">▸</span>
    </div>
  </div>

  <aside class="panel" data-el="5">
    <div class="pbody">
      <h4>최근 변경</h4>
      <div class="rc">
        <div><span class="mono">SYNC-SCN-001</span> <span class="mono lbl">v4</span><span class="grow"></span><span class="lbl">3시간 전</span></div>
        <div class="msg">spec: 페르소나 P2 툴 목록 갱신</div>
        <div class="lbl">에이전트 · 지시 김민준</div>
      </div>
      <div class="sync lbl" data-el="7">마지막 처리 커밋 <span class="mono" data-el="7.1">eb30fd6</span><br>밀린 커밋 <span data-el="7.2">0</span></div>
    </div>
  </aside>
</div>

<div class="dialog" data-el="6">
  <div class="dhead">확인 필요 4건</div>
  <div class="dbody">
    <ul class="chk">
      <li><b>SYNC-PRD-001#R1</b> · 원인 SYNC-RFQ-001#Q03 v4 · 3일 전 · 담당 박호영</li>
    </ul>
  </div>
</div>
```


### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 프로젝트 헤더 | 영역 | 코드(1.1), 이름(1.2), 저장소 주소(1.3) | — |
| 1.3 | 저장소 주소 | 링크 | GitHub 주소 | 새 탭으로 GitHub |
| 2.1 | 참조 그래프 | 버튼 | | UI-8로 |
| 2.2 | 순서대로 읽기 | 버튼 | | UI-9로 |
| 3 | 요약 수치 | 영역 | 프로젝트 전체의 플래그·댓글·오류 건수. 0이면 흐리게 | — |
| 3.1 | 확인 필요 | 수치 | `확인 필요` 플래그 수 | 목록 다이얼로그(6). UC-H14 기본 흐름 4 |
| 3.2 | 끊어진 참조 | 수치 | `끊어진 참조` 플래그 수 | 목록 다이얼로그(6) |
| 3.6 | 하위 불일치 | 수치 | `하위 불일치` 플래그 수 | 목록 다이얼로그(6) |
| 3.3 | 미해결 댓글 | 수치 | is_resolved=false 댓글 수 | 목록 다이얼로그(6) |
| 3.4 | 규약 오류 | 수치 | has_convention_error 문서 수 | 목록 다이얼로그(6) |
| 3.5 | 미완성 | 수치 | incomplete_warnings가 있는 문서 수 | 목록 다이얼로그(6) |
| 4 | 11단계 표 | 표 | 단계 행(4.1)과 그 아래 문서 행(4.2) | — |
| 4.1 | 단계 행 | 행 | 순번, 단계 이름, 대표 상태, 문서 수. 문서가 여럿이면 **가장 낮은 상태**(UC-H14 1a). 문서 없으면 `미작성`(3a) | 문서 행 접기/펼치기 |
| 4.2 | 문서 행 | 행 | 문서 ID, 상태, 버전, 최근 수정 시각·주체, 플래그 수, 댓글 수, 규약 오류 | UI-5로 |
| 4.3 | 상위 미승인 표시 | 뱃지 | 이 단계에 문서가 있는데 앞 단계에 미승인 문서가 있을 때(UC-H14 1b). 막지 않는다 | — |
| 4.4 | 표준 묶음 | 행 | 11단계 밖 `STD` 문서. 대표 상태·문서 수. 없으면(다른 프로젝트) 행 자체가 없음 | 문서 행 접기/펼치기 |
| 5 | 최근 변경 | 목록 | 이 프로젝트의 최근 버전·상태 변경 N건. 커밋 메시지 접두어(`spec`/`status`)로 구분 | 문서 클릭 → UI-5 |
| 6 | 목록 다이얼로그 | 다이얼로그 | 3.x에서 누른 종류의 항목 목록. 항목·원인·시각·담당 | 항목 클릭 → 그 문서의 UI-5 해당 위치 |
| 7 | 동기화 상태 | 영역 | 최근 변경 아래. 이 저장소를 어디까지 처리했나 | — |
| 7.1 | 마지막 처리 커밋 | 텍스트 | `repositories.last_processed_commit` | 새 탭으로 GitHub 커밋 |
| 7.2 | 밀린 커밋 | 수치 | 원격이 앞선 커밋 수. 0이면 최신 | — |

### 규칙

- 단계 상태 색: `승인` 초록 / `검토중` 노랑 / `초안` 회색 / `미작성` 빈칸. UI-2와 같은 기준
- **11단계 표 머리에 미니 히트맵 11칸을 둔다.** UI-2에서 본 그 프로젝트 행이 여기 다시 있다 — 목록에서 눌러 들어온 사람이 같은 그림을 찾을 수 있게. 14px 정사각형
- 단계 행은 아코디언이고 **기본은 접힘이다.** 캐럿(`▾`/`▸`)이 접힘 상태를 말하고 행 전체가 손잡이다.
  열두 줄이 다 펼쳐지면 화면 하나에 11단계가 안 들어와, 이 화면이 답하려는 "어디까지 왔나"를 먼저 못 본다.
  시나리오 S-1도 "단계 행을 누르면 문서 행이 펼쳐지고"로 접힌 상태에서 출발한다
- UI-2 칸에서 `#stage-N`으로 들어오면 **그 단계만 펼친 채로** 연다(UI-2 요소 2.2 "그 단계 위치")
- 문서 행은 46px 들여쓰고 바탕을 한 톤 낮춘다(`#fdfdfc`). 단계 행과 같은 높이로 두면 어느 쪽이 묶음인지 안 보인다
- 요약 수치(3)는 **17.5px 고정폭**. 0이면 흐리게(`opacity .55`), 1 이상이면 경고색 숫자에 경고 테두리
- 4.1의 대표 상태는 그 단계 문서들 중 가장 낮은 것. 승인 2개 + 초안 1개면 `초안`
- 4.3은 표시만 한다. 순서는 권장이지 강제가 아니다(PRD 비목표)
- 요약 수치(3)는 프로젝트 전체이고, 내 것만 보려면 내 할 일(UI-10)
- **요약 수치는 여섯 칸이다.** 플래그 세 종류(3.1·3.2·3.6)를 다 세운다. `하위 불일치`만 빼면 내 할 일에는 뜨는데 프로젝트 요약에는 안 잡히는 구멍이 생긴다
- 수치가 0이면 흐리게, 1 이상이면 경고색으로. 여섯 칸 모두 눌러 목록(6)을 연다
- 최근 변경(5)은 `status` 커밋도 포함한다. 상태만 바뀐 것도 변경이다
- **동기화 상태(7)는 읽기만 한다.** 폴링이 갱신한 DB 값을 그대로 보여준다 — 이 화면에 들어올 때마다 fetch가 돌지 않는다. 재구축 같은 조작은 여기 없고 UI-14에 있다([[SYNC-UI-001#UI-14]] 7장 4)

### 시나리오

**S-1 어느 단계가 막혔는지 파악한다** — UC-H14 기본 흐름 3
1. 11단계 표(4)를 위에서 아래로 훑는다
2. USECASE 단계에 `상위 미승인`(4.3)이 붙어 있다. 사용자 시나리오가 아직 검토중이라서다
3. 단계 행을 누르면 문서 행이 펼쳐지고, 문서 행에 `규약 오류`가 보인다
4. 문서 행(4.2)을 눌러 UI-5로 들어간다

**S-2 처리할 건수를 파고든다** — UC-H14 기본 흐름 4
1. 요약 수치(3)에서 `확인 필요 4`를 누른다
2. 목록 다이얼로그(6)가 뜨고 4건이 항목·원인·담당과 함께 나열된다
3. 항목을 누르면 그 문서의 UI-5가 해당 항목 위치에서 열린다

**S-3 누가 뭘 바꿨는지 본다**
1. 최근 변경(5)을 본다. 에이전트가 쓴 것과 사람이 쓴 것이 구분된다
2. `status: 검토중 → 승인` 같은 상태 변경도 줄로 보인다
3. 문서를 누르면 UI-5로 간다

---

## UI-10 내 할 일

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-10]] |
| 경로 | `/todo` |
| 진입 | 상단 바 배지 |
| 유스케이스 | [[SYNC-UC-001#UC-H15]] 기본 흐름 1~3, 확장 2a |

### 배치

```html
<div class="phead" data-el="1">
  <div><b>내 할 일</b> <span class="lbl" data-el="1.1">7건 · 경과일순</span></div>
</div>

<div class="todo">

  <section class="grp" data-el="2">
    <h4>확인 필요 <span class="cnt">2</span></h4>
    <div class="row" data-el="2.1">
      <span class="k">SYNC-PRD-001#R1</span> 에이전트용 원본과 사람용 뷰
      <span class="lbl">원인 SYNC-RFQ-001#Q03 v4</span>
      <span class="grow"></span><span class="age">3일</span>
    </div>
    <div class="row">
      <span class="k">SYNC-PRD-001#R9</span> MCP 서버
      <span class="lbl">원인 SYNC-RFQ-001#Q03 v4</span>
      <span class="grow"></span><span class="age">3일</span>
    </div>
  </section>

  <section class="grp" data-el="3">
    <h4>끊어진 참조 <span class="cnt">1</span></h4>
    <div class="row" data-el="3.1">
      <span class="k">SYNC-DOM-002#Version</span> Version
      <span class="lbl">→ SYNC-DOM-001#다이어그램 (2일 전 삭제)</span>
      <span class="grow"></span><span class="age">2일</span>
    </div>
  </section>

  <section class="grp" data-el="9">
    <h4>하위 불일치 <span class="cnt">1</span></h4>
    <div class="row" data-el="9.1">
      <span class="k">SYNC-UC-001#UC-A6</span> 명세를 작성·수정한다
      <span class="lbl">← SYNC-API-002#update_document 이(가) 어긋남 지목</span>
      <span class="grow"></span><span class="age">1일</span>
    </div>
  </section>

  <section class="grp" data-el="4">
    <h4>전파 미결정 <span class="cnt">1</span></h4>
    <div class="row" data-el="4.1">
      <span class="k">SYNC-PRD-001</span> v7
      <span class="lbl">spec: R10 다이어그램 렌더링으로 변경 · 하위 3건</span>
      <span class="grow"></span><span class="age">1일</span>
    </div>
  </section>

  <section class="grp" data-el="5">
    <h4>규약 오류 <span class="cnt">1</span></h4>
    <div class="row" data-el="5.1">
      <span class="k">SYNC-UC-001</span>
      <span class="lbl">커밋 a1b2c3 · frontmatter.status 누락</span>
      <span class="grow"></span><span class="age">1일</span>
    </div>
  </section>

  <section class="grp" data-el="6">
    <h4>미해결 댓글 <span class="cnt">2</span></h4>
    <div class="row" data-el="6.1">
      <span class="k">SYNC-PRD-001</span> 12행
      <span class="lbl">김민준: 이 부분 에이전트가 파싱 가능한지…</span>
      <span class="grow"></span><span class="age">2일</span>
    </div>
    <div class="row">
      <span class="k">SYNC-SCN-001</span> 40행
      <span class="lbl">김민준: P2 툴 목록에 Cursor 빠짐</span>
      <span class="grow"></span><span class="age">3시간</span>
    </div>
  </section>

  <section class="grp dim" data-el="7">
    <h4>담당 미지정 <span class="cnt">1</span></h4>
    <div class="row" data-el="7.1">
      <span class="k">SYNC-UC-001#UC-H2</span> 사람용 뷰로 읽는다
      <span class="lbl">확인 필요 · 원인 SYNC-PRD-001#R1 v7</span>
      <span class="grow"></span><span class="age">1일</span>
    </div>
  </section>

  <div class="empty" data-el="8">처리할 일이 없습니다</div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 제목, 총 건수(1.1) | — |
| 1.1 | 총 건수 | 텍스트 | 2~6·9 묶음의 합. 담당 미지정(7)은 제외. 정렬 기준은 경과일순(UC-H15 기본 흐름 2) | — |
| 2 | 확인 필요 | 묶음 | 내가 담당인 `needs_check` 플래그. 0건이면 묶음 숨김 | — |
| 2.1 | 확인 필요 행 | 행 | 대상 항목 ID·제목, 원인 항목·버전, 경과일 | UI-11로 (UC-H15 기본 흐름 3) |
| 3 | 끊어진 참조 | 묶음 | 내가 담당인 `broken_ref` 플래그. 0건이면 숨김 | — |
| 3.1 | 끊어진 참조 행 | 행 | 대상 항목, 사라진 상위 항목과 삭제 시각, 경과일 | 그 문서의 UI-5 `#item-X`. 항목 선택 + 참조 패널에 플래그 정보(UC-H12 기본 흐름 1) |
| 9 | 하위 불일치 | 묶음 | 내가 담당인 `upstream_impact` 플래그 — 내 항목이 하위와 어긋났다고 지목됨. 0건이면 숨김 | — |
| 9.1 | 하위 불일치 행 | 행 | 내 항목, 지목한 하위 항목, 경과일 | UI-11로 |
| 4 | 전파 미결정 | 묶음 | 내가 지시한 저장 중 `undecided`인 것. 0건이면 숨김 | — |
| 4.1 | 전파 미결정 행 | 행 | 문서·버전, 커밋 메시지 요약, 영향받는 하위 건수, 경과일 | UI-12 다이얼로그 (UC-H10 기본 흐름 1) |
| 5 | 규약 오류 | 묶음 | 내 커밋으로 `has_convention_error`가 된 문서. 0건이면 숨김 | — |
| 5.1 | 규약 오류 행 | 행 | 문서 ID, 커밋, 위반 요약 | 그 문서의 UI-5. 배너(4)에 상세 |
| 6 | 미해결 댓글 | 묶음 | 내가 최근 작성한 문서에 달린 `is_resolved=false` 댓글. 0건이면 숨김 | — |
| 6.1 | 미해결 댓글 행 | 행 | 문서, 줄 번호, 댓글 앞부분, 작성자, 경과 | 그 문서의 UI-5 `?panel=comments#line-N`. 댓글 탭 열림 |
| 7 | 담당 미지정 | 묶음 | assignee가 null인 플래그 전부. 누구 것도 아니라 모두에게 보임(UC-H15 확장 2a). 흐리게 | — |
| 7.1 | 담당 미지정 행 | 행 | 2.1·3.1과 같은 내용 | 종류에 따라 UI-11 또는 UI-5 `#item-X` |
| 8 | 빈 상태 | 텍스트 | 2~7이 모두 0건일 때만 | — |

### 규칙

- 일곱 묶음은 별도 저장소 없이 각각 DB를 직접 조회한다(UC-H15 기본 흐름 2). 플래그·전파결정·문서·댓글 테이블
- 묶음 안 정렬은 경과일 내림차순. 오래 방치된 게 위
- **묶음 순서는 고정이다** — 확인 필요 · 하위 불일치 · 끊어진 참조 · 전파 미결정 · 규약 오류 · 미해결 댓글 · 담당 미지정. 건수에 따라 순서가 바뀌면 매번 눈으로 다시 찾아야 한다
- 담당 미지정(7)은 마지막이고 흐리게 둔다. 남의 것이 아니라 아무의 것도 아닌 것이다
- 상단 바 배지 숫자 = 1.1 총 건수. 담당 미지정은 배지에 안 들어간다
- 0건 묶음은 제목까지 숨긴다. 전부 0이면 빈 상태(8)만 보인다
- 처리가 끝나면(확인함, 전파 선택, 댓글 해결) 이 화면으로 돌아왔을 때 그 행이 사라진다

### 시나리오

**S-1 오늘 처리할 것을 훑는다** — UC-H15 기본 흐름 1~2
1. 상단 바 배지를 눌러 들어온다
2. 여섯 묶음이 경과일순으로 보인다. 3일 된 확인 필요가 맨 위다
3. 어느 묶음이 몇 건인지 제목의 숫자로 한눈에 본다

**S-2 확인 필요를 처리하러 간다** — UC-H15 기본 흐름 3 → UC-H11
1. 확인 필요 행(2.1)을 누른다
2. UI-11이 열린다. 처리하고 돌아오면 그 행이 사라져 있다

**S-3 전파 여부를 결정한다** — UC-H10 기본 흐름 1
1. 전파 미결정 행(4.1)을 누른다
2. UI-12 다이얼로그가 이 화면 위에 뜬다
3. 결정하면 다이얼로그가 닫히고 행이 사라진다. 닫기만 하면 행이 남는다

**S-4 담당이 없는 플래그를 맡는다** — UC-H15 확장 2a
1. 담당 미지정(7)에 항목이 보인다. 팀원 누구 것도 아니다
2. 행(7.1)을 누르면 UI-11로 간다. 처리하면 확인자가 나로 기록된다

---

## UI-11 플래그 처리

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-11]] |
| 경로 | `/todo/flags/{플래그ID}` |
| 진입 | UI-10 확인 필요 행(2.1) · 담당 미지정 행(7.1) |
| 유스케이스 | [[SYNC-UC-001#UC-H11]] 기본 흐름 1~6, 확장 3a·3b·4a |

### 배치

```html
<div class="phead" data-el="1">
  <div>
    <span class="flag">확인 필요</span>
    <b data-el="1.1">SYNC-PRD-001#R1</b> 에이전트용 원본과 사람용 뷰
    <span class="lbl" data-el="1.2">담당 박호영 · 3일 전 부여</span>
  </div>
  <span class="grow"></span>
  <span class="btn" data-el="5">← 내 할 일</span>
</div>

<div class="stack">

  <section class="cause" data-el="2">
    <div class="sech">
      <b data-el="2.1">원인: SYNC-RFQ-001#Q03</b> 두 가지 버전
      <span class="lbl" data-el="2.2">v4 → v6 · 그 사이 2번 바뀜</span>
      <span class="grow"></span>
      <span class="btn sm" data-el="2.4">문서에서 보기</span>
    </div>
    <div class="diffbox" data-el="2.3">
      <div class="dl">- 사람용 그림은 draw.io 수준으로 자동 생성한다.</div>
      <div class="dl add">+ 사람용 그림은 mermaid 렌더링으로 충분하다. 브라우저가 그린다.</div>
      <div class="dl">- 내려받기를 지원한다.</div>
    </div>
  </section>

  <section class="mine" data-el="3">
    <div class="sech">
      <b data-el="3.1">내 항목: SYNC-PRD-001#R1</b>
      <span class="lbl" data-el="3.2">v7 · 플래그 부여 후 변경 없음</span>
      <span class="grow"></span>
      <span class="btn sm" data-el="3.4">문서에서 보기</span>
    </div>
    <div class="mybody" data-el="3.3">
      <div class="item"><span class="id">#R1</span>에이전트용 원본과 사람용 뷰</div>
      <p>명세는 에이전트가 읽을 것을 전제로, 규약이 있는 Markdown으로 작성한다. 이 MD가 원본이자 에이전트용 산출물이다.</p>
      <p>사람용 뷰는 원본에 그림·참조 링크·상태 표시를 더해 파생 생성한다. 근거: <span class="ref">[[SYNC-RFQ-001#Q03]]</span></p>
    </div>
  </section>

  <div class="acts" data-el="4">
    <span class="lbl" data-el="4.2">영향이 있으면 에이전트에게 수정을 시킨 뒤 돌아와 확인하세요</span>
    <span class="grow"></span>
    <span class="btn" data-el="4.1" style="font-weight:600">확인함</span>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 플래그 종류, 대상 항목(1.1), 담당·부여 시각(1.2) | — |
| 2 | 원인 영역 | 영역 | 위쪽. `확인 필요`면 원인 항목의 변경 diff, `하위 불일치`면 지목한 하위 항목의 현재 본문(UC-H11 기본 흐름 2) | — |
| 2.1 | 원인 항목 | 텍스트 | 원인 항목 ID와 제목 | — |
| 2.2 | 원인 버전 범위 | 텍스트 | 플래그 부여 시점 버전 → 현재 버전. 그 사이 또 바뀌었으면 횟수(UC-H11 3a) | — |
| 2.3 | 원인 diff | diff | 2.2 범위의 줄 단위 변경. 여러 번 바뀌었으면 누적. `하위 불일치`면 diff 대신 하위 항목 본문 블록 | — |
| 2.4 | 문서에서 보기 | 버튼 | | 원인 문서의 UI-5 해당 항목 위치 |
| 3 | 내 항목 영역 | 영역 | 아래쪽. 플래그가 붙은 항목의 현재 내용 | — |
| 3.1 | 내 항목 | 텍스트 | 항목 ID와 제목 | — |
| 3.2 | 내 항목 버전 | 텍스트 | 현재 버전. 플래그 부여 후 바뀌었는지 여부 | — |
| 3.3 | 내 항목 본문 | 사람용 뷰 | 항목 블록만. 읽기 전용 | — |
| 3.4 | 문서에서 보기 | 버튼 | | 내 문서의 UI-5 해당 항목 위치 |
| 4 | 처리 영역 | 영역 | 확인함 버튼과 안내 | — |
| 4.1 | 확인함 | 버튼 | | 플래그 해제, 확인자·시각·수정 동반 여부 기록(UC-H11 기본 흐름 5~6). UI-10으로 |
| 4.2 | 안내 | 텍스트 | 수정이 필요하면 에이전트에게 시키고 돌아오라는 안내(UC-H11 기본 흐름 4). **지금 누르면 어느 쪽으로 기록되는지도 여기 적는다** — `수정 동반` 또는 `수정 없음` | — |
| 5 | 내 할 일로 | 버튼 | | 처리하지 않고 UI-10으로. 플래그는 남는다 |

### 규칙

- 위가 원인, 아래가 내 항목. 위를 읽고 아래에 영향이 있는지 판단하는 순서(UC-H11 기본 흐름 2~3)
- 2.2에서 원인이 여러 번 바뀌었으면 2.3은 부여 시점 → 현재까지 누적 diff (UC-H11 3a)
- 3.2 "플래그 부여 후 변경 없음/있음"은 시스템이 판정한다. 부여 시점의 내 문서 버전과 현재 버전을 비교. 이 값이 확인함(4.1) 때 `수정 동반 여부`로 기록된다(UC-H11 3b)
- **확인 버튼은 하나다.** 수정 동반 여부를 사람에게 묻지 않는다 — 시스템이 이미 아는 것을 두 번 물으면 답이 어긋난다. 대신 안내(4.2)에 어느 쪽으로 기록될지 미리 보여준다
- 이 화면에는 편집이 없다. 수정은 에이전트에게 시키고(UC-A6), 돌아오면 3.2·3.3이 갱신되어 있다
- 원인 항목 쪽이 잘못됐다고 판단하면(UC-H11 4a) 확인함을 누르지 않고 5로 나간다. 플래그는 남는다
- 담당 미지정 플래그를 열었을 때 확인함을 누르면 확인자가 나로 기록된다

### 시나리오

**S-1 영향이 있어 수정한다** — UC-H11 기본 흐름 1~6
1. UI-10에서 행을 눌러 들어온다
2. 원인 diff(2.3)를 읽는다. drawio가 빠졌다
3. 내 항목(3.3)에 "그림 자동 생성"이 남아 있다. 영향이 있다
4. 에이전트에게 "PRD R1에서 그림 생성 문구 빼줘"라고 시킨다. 에이전트가 MCP로 수정한다
5. 이 화면으로 돌아온다. 3.2가 "v8 · 플래그 부여 후 변경 있음"으로 바뀌어 있다
6. 확인함(4.1)을 누른다. 플래그가 해제되고 `수정 동반`으로 기록된다

**S-2 영향이 없다** — UC-H11 확장 3b
1. 원인 diff(2.3)를 읽는다
2. 내 항목(3.3)은 이 변경과 무관하다
3. 바로 확인함(4.1)을 누른다. `수정 없음`으로 기록된다

**S-3 원인이 그 사이 또 바뀌었다** — UC-H11 확장 3a
1. 2.2에 "v4 → v6 · 그 사이 2번 바뀜"이 보인다
2. 2.3이 두 번의 변경을 누적한 diff다. 중간 버전을 따로 볼 필요가 없다

**S-4 원인 쪽이 잘못됐다** — UC-H11 확장 4a
1. 원인 diff를 읽어보니 원인 항목의 변경 자체가 틀렸다
2. 확인함을 누르지 않고 내 할 일로(5) 나간다. 플래그는 그대로 남는다
3. 에이전트에게 원인 항목을 고치게 한다. 그러면 그 저장이 다시 UC-S3을 돌리고, 이 플래그의 원인 버전이 갱신된다

---

## UI-12 전파 선택

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-12]] |
| 경로 | UI-10 위의 다이얼로그. 별도 경로 없음 |
| 진입 | UI-10 전파 미결정 행(4.1) |
| 유스케이스 | [[SYNC-UC-001#UC-H10]] 기본 흐름 1~3, 확장 2a·2b |

### 배치

```html
<div class="dialog wide" data-el="1">
  <div class="dhead">
    <span data-el="1.1">전파 선택 — SYNC-PRD-001 v7</span>
    <span class="grow"></span>
    <span class="lbl" data-el="1.2">저장: 에이전트(박호영) · 1일 전</span>
    <span class="x" data-el="6">✕</span>
  </div>
  <div class="dbody">

    <div class="sech" data-el="2"><b>이 버전에서 바뀐 것</b> <span class="lbl">v6 → v7 · 항목 2개</span></div>
    <div class="diffbox" data-el="2.1">
      <div class="lbl">#R10 다이어그램 렌더링</div>
      <div class="dl">- 텍스트 원본에서 사람이 보는 그림을 자동 생성한다. Mermaid와 drawio 두 가지</div>
      <div class="dl add">+ 원본의 mermaid 코드블록을 사람용 뷰에서 렌더링한다. 브라우저가 한다</div>
      <div class="lbl" style="margin-top:6px">#R1 에이전트용 원본과 사람용 뷰</div>
      <div class="dl add">+ 웹 문서 뷰는 유저용과 원본 두 탭을 전환해 보여준다</div>
    </div>

    <div class="sech" data-el="3"><b>영향받는 하위 항목</b> <span class="lbl">3건</span></div>
    <ul class="chk" data-el="3.1">
      <li><b>SYNC-UC-001#UC-H2</b> 사람용 뷰로 읽는다 <span class="lbl">← #R1, #R10 · 담당 김민준</span></li>
      <li><b>SYNC-UC-001#UC-A6</b> 명세를 작성·수정한다 <span class="lbl">← #R1 · 담당 박호영</span></li>
      <li><b>SYNC-DOM-001#다이어그램</b> <span class="lbl">← #R10 · 담당 미지정</span></li>
    </ul>

    <div class="propacts">
      <div class="skipbox" data-el="5">
        <span class="btn" data-el="5.1">하위 전파 안 함</span>
        <input class="inp" data-el="5.2" placeholder="사유 (필수) — 예: 오탈자 수정">
      </div>
      <span class="grow"></span>
      <span class="btn" data-el="4" style="font-weight:600">예 — 3건에 확인 필요 붙이기</span>
    </div>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 다이얼로그 | 다이얼로그 | UI-10 위에 뜬다. 뒤 화면은 흐리게 | — |
| 1.1 | 제목 | 텍스트 | 문서 ID와 버전 | — |
| 1.2 | 저장 주체 | 텍스트 | 누가(에이전트면 지시자 포함) 언제 저장했나 | — |
| 2 | 변경 영역 | 영역 | 이 버전에서 바뀐 항목 ID 목록과 diff(UC-H10 기본 흐름 1) | — |
| 2.1 | 변경 diff | diff | 이전 버전 → 이 버전. 항목 ID별로 묶음 | — |
| 3 | 영향 영역 | 영역 | UC-S3이 찾은 하위 항목(UC-H10 기본 흐름 1) | — |
| 3.1 | 하위 항목 목록 | 목록 | 항목 ID·제목, 어느 변경 항목의 하위인지, 담당자 | 항목 클릭 → 그 문서의 UI-5 (새 탭) |
| 4 | 예 | 버튼 | 붙을 플래그 건수를 버튼에 표시 | UC-S4 실행. 3.1 전부에 `확인 필요`. 다이얼로그 닫힘, UI-10에서 행 사라짐 |
| 5 | 전파 안 함 영역 | 영역 | 버튼(5.1)과 사유 입력(5.2) | — |
| 5.1 | 하위 전파 안 함 | 버튼 | 5.2가 비어 있으면 비활성 | `skip` + 사유 기록(UC-H10 2a). 플래그 안 붙음. 닫힘 |
| 5.2 | 사유 | 한 줄 입력 | 필수 | — |
| 6 | 닫기 | 버튼 | | 결정 없이 닫힘. `미결정` 유지, UI-10 행 남음(UC-H10 2b) |

### 규칙

- 결정은 셋 중 하나이며 한 번 하면 바꿀 수 없다. `propagate` / `skip` / `undecided`
- 5.1은 사유(5.2)가 비어 있으면 눌리지 않는다. `skip`은 사유 필수
- 4를 누르면 3.1의 모든 항목에 플래그가 붙는다. 일부만 고를 수 없다. 일부만 영향이 없다면 그 담당자가 UI-11에서 "수정 없음"으로 확인하면 된다
- 하위 항목 클릭(3.1)은 새 탭으로 연다. 다이얼로그 위에서 판단 중이므로 이 화면을 떠나지 않는다
- 저장 주체가 에이전트면 1.2에 지시자를 함께 보여준다. 이 다이얼로그는 지시자의 내 할 일에 뜬다

### 시나리오

**S-1 전파한다** — UC-H10 기본 흐름 1~3
1. UI-10에서 전파 미결정 행을 눌러 연다
2. 변경 diff(2.1)를 읽는다. R10이 실질적으로 바뀌었다
3. 영향 목록(3.1)을 본다. 3건, 담당자가 셋
4. 예(4)를 누른다. 3건에 `확인 필요`가 붙고 각 담당자의 내 할 일에 뜬다

**S-2 오탈자라 전파하지 않는다** — UC-H10 확장 2a
1. 변경 diff(2.1)를 보니 띄어쓰기만 고쳤다
2. 사유(5.2)에 "오탈자"라고 적는다. 그러면 5.1이 활성화된다
3. 하위 전파 안 함(5.1)을 누른다. 플래그 없이 닫히고 사유가 이력에 남는다

**S-3 판단을 미룬다** — UC-H10 확장 2b
1. 영향 범위가 커서 지금 결정하기 어렵다
2. 닫기(6)를 누른다
3. UI-10에 행이 그대로 남아 있다. 나중에 다시 연다

---

## UI-7 버전 이력

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-7]] |
| 경로 | `/p/{프로젝트코드}/d/{문서ID}/history` |
| 진입 | UI-5 이력 탭(2.3) · UI-5 버전(1.2) |
| 유스케이스 | [[SYNC-UC-001#UC-H6]] 기본 흐름 1~3, 확장 3a·3b · [[SYNC-UC-001#UC-H7]] 기본 흐름 1~4, 확장 3a·4a |

### 배치

```html
<!-- 문서 뷰와 같은 3단 틀. 좌: 버전, 가운데: diff, 우: 영향. 화면 높이를 채우고 가운데만 스크롤한다 -->
<div class="docbar" data-el="1">
  <span class="crumb">싱크독</span><span class="sep">›</span>
  <span class="crumb mono">2 PRD</span><span class="sep">›</span>
  <b class="mono">SYNC-PRD-001</b>
  <span class="pill pill-approved">승인</span><span class="ver mono">v7</span>
</div>

<div class="body3">
  <nav class="vlist" data-el="2">
    <div class="lbl">버전 7</div>

    <div class="vcard sel" data-el="2.1">
      <div><b class="mono">v7</b> <span class="ab" data-el="2.3">B</span><span class="grow"></span><span class="lbl">1일 전</span></div>
      <div class="msg">spec: R10 다이어그램 렌더링으로 변경</div>
      <div class="by"><span class="lbl">에이전트 · 지시 박호영</span></div>
    </div>

    <div class="vcard">
      <div><b class="mono">status</b><span class="grow"></span><span class="lbl">1일 전</span></div>
      <div class="msg">status: 검토중 → 승인</div>
      <div class="by"><span class="lbl">박호영</span></div>
    </div>

    <div class="vcard sel">
      <div><b class="mono">v6</b> <span class="ab">A</span><span class="grow"></span><span class="lbl">2일 전</span></div>
      <div class="msg">spec: 웹 편집 삭제</div>
      <div class="by"><span class="lbl">에이전트 · 지시 박호영</span><span class="grow"></span><span class="btn sm danger" data-el="2.2">되돌리기</span></div>
    </div>

    <p class="hint">두 개까지 고른다. 세 번째를 누르면 <b class="mono">A</b>가 밀려난다.</p>
  </nav>
  <div class="handle"></div>

  <section class="mainwrap" data-el="3">
    <div class="tabs"><span>유저용</span><span>원본</span><span class="on">이력</span></div>
    <div class="drange">
      <b class="mono" data-el="3.1">v6 → v7</b>
      <span class="lbl">항목 2개 변경 · 삭제 3줄 · 추가 4줄</span>
    </div>

    <div class="dgroup"><!-- 항목마다 카드. 어느 항목이 바뀌었는지가 먼저 읽혀야 한다 -->
      <div class="dhead2">
        <span class="idbadge">R10</span><b>다이어그램 렌더링</b>
        <span class="grow"></span>
        <span class="hint" data-el="3.3">하위 참조 2건</span>
      </div>
      <div class="diffbox" data-el="3.2">
        <div class="dl del"><span class="mk">-</span><span>텍스트 원본에서 사람이 보는 그림을 자동 생성한다.</span></div>
        <div class="dl add"><span class="mk">+</span><span>원본의 다이어그램 코드블록을 사람용 뷰에서 그림으로 렌더링한다.</span></div>
      </div>
    </div>

    <p class="footnote">되돌리기는 "이전 내용으로 새 버전 생성"이며 이력이 지워지지 않는다. 되돌린 결과가 현재 규약을 위반하면 거부된다.</p>
  </section>

  <div class="handle"></div>
  <aside class="vimpact" data-el="7">
    <div class="lbl">이 변경이 닿는 곳</div>
    <div class="icard"><b class="mono">R10</b> <span class="n">2</span><div class="lbl">다이어그램 렌더링</div></div>
    <div class="icard"><b class="mono">R1</b> <span class="n">4</span><div class="lbl">에이전트용 원본과 사람용 뷰</div></div>
    <p class="hint">항목 ID가 붙은 줄이 바뀌면 그 항목을 참조하는 하위 건수가 여기 나온다.</p>
  </aside>
</div>

<div class="dialog" data-el="4">
  <div class="dhead">v6으로 되돌리기</div>
  <div class="dbody">
    현재 v7을 v6 내용으로 되돌립니다. 이력은 지워지지 않고 <b>v8</b>이 새로 생깁니다.
    <div class="diffbox" data-el="4.1">
      <div class="dl del"><span class="mk">-</span><span>원본의 다이어그램 코드블록을…</span></div>
      <div class="dl add"><span class="mk">+</span><span>텍스트 원본에서 사람이 보는 그림을…</span></div>
    </div>
  </div>
  <div class="dfoot"><span class="grow"></span><span class="btn" data-el="4.3">취소</span> <span class="btn solid" data-el="4.2">되돌리기</span></div>
</div>

<div class="dialog" data-el="6">
  <div class="dhead">항목 삭제 확인</div>
  <div class="dbody">
    v3에는 <b>#R15</b>가 없습니다. 되돌리면 이 항목이 사라지고 하위 참조 2건에 <b>끊어진 참조</b> 플래그가 붙습니다.
    <ul class="chk"><li>SYNC-UC-001#UC-H7</li><li>SYNC-DOM-003#versions</li></ul>
  </div>
  <div class="dfoot"><span class="grow"></span><span class="btn" data-el="6.2">취소</span> <span class="btn solid" data-el="6.1">삭제하고 되돌리기</span></div>
</div>
```


### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 문서 바 | 영역 | UI-5와 같음. 이력 탭 활성 | 유저용·원본 → UI-5 |
| 2 | 버전 목록 | 목록 | **좌측 사이드바의 카드 목록.** 최신이 위. 버전 번호, 시각, 작성 주체, 커밋 메시지(UC-H6 기본 흐름 2). `status` 커밋도 카드로 |
| 2.1 | 버전 카드 | 카드 | 번호, `A`/`B` 뱃지(고른 두 개), 시각, 작성(사람/에이전트+지시자/GitHub push), 변경 요약, 되돌리기 | 고르면 diff 대상. 두 개까지 |
| 7 | 이 변경이 닿는 곳 | 패널 | 우측. 바뀐 항목마다 하위 참조 건수 카드. 이 변경이 저장 전에 어디까지 번지는지 | 항목 클릭 → 3.3과 같음 |
| 2.3 | A·B 뱃지 | 뱃지 | 고른 두 버전 중 어느 쪽이 이전(`A`)이고 어느 쪽이 현재(`B`)인지 | — |
| 2.2 | 되돌리기 | 버튼 | 현재 버전과 `status` 행 제외한 행마다 | 되돌리기 확인(4) 열림(UC-H7 기본 흐름 1~2) |
| 3 | diff 영역 | 영역 | 선택한 두 버전의 줄 단위 diff(UC-H6 기본 흐름 3). 기본은 현재 ↔ 직전 | — |
| 3.1 | 비교 범위 | 텍스트 | `vA → vB`, 변경 항목 수, 줄 수 | — |
| 3.2 | diff 본문 | diff | 항목 ID별로 묶은 변경 줄 | — |
| 3.3 | 하위 참조 건수 | 뱃지 | 항목 ID가 붙은 줄이 바뀌었으면 그 항목을 참조하는 하위 건수(UC-H6 3a) | 클릭 → 하위 항목 목록 |
| 4 | 되돌리기 확인 | 다이얼로그 | 되돌릴 버전과 현재의 차이, 새 버전 번호(UC-H7 기본 흐름 2) | — |
| 4.1 | 되돌리기 diff | diff | 현재 → 되돌린 결과 | — |
| 4.2 | 되돌리기 | 버튼 | | 그 내용으로 새 버전 생성(UC-H7 기본 흐름 3~4). 되돌린 본문에 지금 있는 항목이 없고 하위 참조가 있으면 삭제 확인(6)이 한 번 더 뜬다. UI-5로 |
| 6 | 삭제 확인 | 다이얼로그 | 되돌리기로 사라지는 항목과 하위 참조 목록(UC-A6 4b). 서버가 `item-deletion-needs-confirm`을 돌려줬을 때 | — |
| 6.1 | 삭제하고 되돌리기 | 버튼 | | `confirm_item_deletion=true`로 재요청 |
| 6.2 | 취소 | 버튼 | | 닫힘. 되돌리지 않음 |
| 4.3 | 취소 | 버튼 | | 닫힘. 아무 일 없음(UC-H7 3a) |

### 규칙

- **두 개까지 고른다. 세 번째를 고르면 `A`가 밀려난다.** 늘 뒤쪽이 `B`(현재), 앞쪽이 `A`(이전)다 — 순서를 사람이 신경 쓰지 않아도 되게
- 고른 카드는 잉크색 1.5px 테두리와 주의 배경으로 구분한다. 뱃지(2.3)가 어느 쪽이 A인지 말해 준다
- **UI-5와 같은 3단 틀을 쓴다.** 좌측 사이드바·본문·우측 패널의 폭과 손잡이가 같다 — 탭으로 오갈 때 틀이 바뀌면 같은 문서를 보고 있다는 감각이 끊긴다
- diff는 **항목마다 카드**다. 머리에 항목 ID 뱃지·제목·하위 참조 건수를 놓는다 — 어느 항목이 바뀌었는지가 줄보다 먼저 읽혀야 한다
- 버전이 하나뿐이면 diff 영역(3)에 비교 대신 전체 본문(UC-H6 3b)
- `status` 커밋 행과 현재 버전은 되돌리기(2.2)가 없다. `status`는 본문이 같고, 현재 버전은 되돌릴 것이 없다. diff 대상으로는 고를 수 있다
- 되돌리기(4.2)는 UC-A6과 같은 파이프라인을 탄다. 규약 검사·참조 추출·변경 영향 감지가 전부 돈다. 되돌린 결과가 현재 규약을 위반하면 거부된다(UC-H7 4a)
- 되돌리기 후 하위 영향이 있으면 전파 미결정이 되어 내 할 일에 뜬다
- 되돌린 본문에 지금 있는 항목이 없으면(예: v3엔 `#R15`가 없음) 서버가 삭제 확인을 요구한다. 웹은 확인 다이얼로그(6)로 받아 재요청한다

### 시나리오

**S-1 지난번 이후 뭐가 바뀌었나 본다** — UC-H6 기본 흐름 1~3
1. UI-5에서 이력 탭을 누른다. 현재 v7과 직전 v6 diff가 기본으로 보인다
2. 3일 전 v5도 보고 싶다. v5를 체크하고 v7을 남긴다. 3.1이 `v5 → v7`로 바뀐다
3. 3.2에서 두 버전 사이 변경을 항목별로 읽는다

**S-2 바뀐 항목이 어디에 영향을 주는지 본다** — UC-H6 확장 3a
1. diff에서 `#R10` 옆에 `하위 참조 2건`(3.3)이 보인다
2. 누르면 그 2건 목록이 뜬다. 이 변경이 어디까지 번지는지 저장 전에 알 수 있다

**S-3 잘못된 버전을 되돌린다** — UC-H7 기본 흐름 1~4
1. v6 행의 되돌리기(2.2)를 누른다
2. 확인 다이얼로그(4)에 현재 → 되돌린 결과 diff가 보인다. v8이 새로 생긴다는 안내
3. 되돌리기(4.2)를 누른다
4. v8이 생기고 UI-5로 간다. v7은 이력에 그대로 남아 있다

**S-4 되돌리기가 거부된다** — UC-H7 확장 4a
1. v3으로 되돌리려 한다. v3은 지금 규약(항목 ID 형식)이 생기기 전 버전이다
2. 되돌리기(4.2)를 누르면 규약 위반으로 거부되고 어느 부분인지 알려준다
3. 에이전트에게 v3 내용을 참고해 다시 쓰게 하는 수밖에 없다

---

## UI-2 프로젝트 목록

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-2]] |
| 경로 | `/` |
| 진입 | 로그인 직후 · 상단 바 로고 |
| 유스케이스 | [[SYNC-UC-001#UC-H14]] 기본 흐름 1~2, 확장 1a·1b·3a |

### 배치

```html
<!-- 표가 아니라 격자다. 칸이 열 폭을 꽉 채우는 막대여야 색 띠로 읽힌다 -->
<div class="phead" data-el="1">
  <div><b>프로젝트</b> <span class="lbl">4개</span></div>
  <span class="grow"></span>
  <span class="btn solid" data-el="1.1">+ 프로젝트 초기화</span>
</div>

<div class="heat" data-el="2"><!-- grid-template-columns: 20px 196px repeat(11,1fr) · gap 4px -->
  <div class="hrow head">
    <span></span><span></span>
    <span>1 RFQ</span><span>2 PRD</span><span>3 SCN</span><span>4 UC</span><span>5 INFRA</span><span>6 DOM</span>
    <span>7 UI</span><span>8 API</span><span>9 SEQ</span><span>10 MS</span><span>11 CODE</span>
  </div>

  <div class="hrow" data-el="2.1">
    <span class="warn" data-el="2.3">⚠</span>
    <span class="pname">
      <span><b class="mono">SYNC</b> 싱크독</span>
      <span class="sub"><b class="work">처리할 것 9</b> · 21문서 · 12분 전</span>
    </span>
    <span class="cell ok" data-el="2.2">1</span>
    <span class="cell ok flagged">1</span>
    <span class="cell ok">1</span>
    <span class="cell ok">1</span>
    <span class="cell ok">1</span>
    <span class="cell rv flagged">3</span>
    <span class="cell rv">2 <i data-el="2.4">▲</i></span>
    <span class="cell rv flagged">2 <i>▲</i></span>
    <span class="cell rv">1 <i>▲</i></span>
    <span class="cell dr">3 <i>▲</i></span>
    <span class="cell dr">1 <i>▲</i></span>
  </div>

  <div class="hrow">
    <span></span>
    <span class="pname"><span><b class="mono">RHYM</b> 리듬핏</span><span class="sub">1문서 · 어제</span></span>
    <span class="cell rv">1</span>
    <span class="cell na"></span><span class="cell na"></span><span class="cell na"></span><span class="cell na"></span>
    <span class="cell na"></span><span class="cell na"></span><span class="cell na"></span><span class="cell na"></span>
    <span class="cell na"></span><span class="cell na"></span>
  </div>
</div>

<div class="legend lbl" data-el="4">
  <span><i class="sw dr"></i> 초안</span> <span><i class="sw rv"></i> 검토중</span>
  <span><i class="sw ok"></i> 승인</span> <span><i class="sw na"></i> 미작성</span>
  <span class="warn">⚠ 플래그·규약 오류 있음</span> <span class="warn">▲ 상위 미승인 (막지는 않는다)</span>
</div>

<div class="empty" data-el="3">등록된 프로젝트가 없습니다. 위의 프로젝트 초기화로 시작하세요.</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 제목, 프로젝트 수 | — |
| 1.1 | 프로젝트 초기화 | 버튼 | | UI-3으로 |
| 2 | 현황판 | 표 | 프로젝트가 행, 11단계가 열(UC-H14 기본 흐름 1) | — |
| 2.1 | 프로젝트 행 | 행 | 코드·이름, 그 아래 플래그·오류 요약 | UI-4로 |
| 2.2 | 단계 칸 | 칸 | 그 단계의 대표 상태를 색으로. 문서 수를 숫자로. 문서가 여럿이면 **가장 낮은 상태**(UC-H14 1a). 없으면 빈칸(3a) | UI-4로 (그 단계 위치) |
| 2.3 | 경고 표시 | 아이콘 | 플래그·규약 오류가 하나라도 있는 프로젝트(UC-H14 기본 흐름 2) | — |
| 2.4 | 상위 미승인 표시 | 아이콘 | 이 단계에 문서가 있는데 앞 단계에 미승인이 있을 때(UC-H14 1b) | — |
| 3 | 빈 상태 | 텍스트 | 프로젝트가 하나도 없을 때만 | — |
| 4 | 범례 | 텍스트 | 칸 색과 기호가 무엇을 뜻하는지. 표 아래 한 줄 | — |

### 규칙

- **표가 아니라 격자다.** `20px 196px repeat(11,1fr)` · `gap 4px` · 행 `padding 10px 14px`. 칸은 높이 22px에 `border-radius 3px`이고 **열 폭을 꽉 채운다** — 작은 칩으로 그리면 색이 띠로 안 읽히고 히트맵이 아니게 된다
- 열 이름은 `1 RFQ` … `11 CODE`. 단계 번호를 붙여 순서가 보이게 한다. 11px 고정폭, 머리 행 배경 `배경 보조`
- 프로젝트 칸(196px)은 두 줄이다 — 첫 줄 `코드`(고정폭 13px/600) + `이름`(15.5px), 둘째 줄 `처리할 것 N`(있을 때만 경고색 600) · `N문서 · 갱신 시각`(12.5px 보조)
- 칸 색: `승인` 초록 / `검토중` 노랑 / `초안` 회색 / `미작성` 빈칸. UI-4와 같은 기준
- 2.3 경고는 종류를 구분하지 않고 하나로. 종류별 건수는 **툴팁**과 2.1 행 아래 요약과 UI-4에서
- 칸(2.2)에 플래그가 있으면 경고색 테두리를 두른다. 색은 상태, 테두리는 플래그 — 두 정보가 한 칸에 겹치지 않게
- **범례(4)를 뺄 수 없다.** 색 넷과 기호 둘을 처음 보는 사람이 알 방법이 이것뿐이다
- 프로젝트 정렬은 최근 변경순. 오래 안 건드린 프로젝트가 아래

### 시나리오

**S-1 어느 프로젝트가 막혀 있나 본다** — UC-H14 기본 흐름 1~2
1. 로그인하면 이 화면이다
2. 행마다 11칸 색을 훑는다. SYNC는 6단계까지 채워졌고 뒤가 비어 있다
3. SYNC 앞에 경고(2.3)가 있다. 행 아래에 "확인 필요 4 · 규약 오류 1"
4. 프로젝트 행(2.1)을 눌러 UI-4로 들어간다

**S-2 단계 하나로 바로 간다**
1. SYNC 행의 UC 칸에 `▲`(2.4)가 보인다. 앞 단계가 미승인인데 이미 문서가 있다
2. 그 칸(2.2)을 누르면 UI-4가 UC 단계 위치에서 열린다

**S-3 새 프로젝트를 시작한다** — UC-A1 웹 경로
1. 프로젝트 초기화(1.1)를 누른다
2. UI-3으로 간다

---

## UI-1 로그인

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-1]] |
| 경로 | `/login` · 미인증 상태로 어디든 접근하면 여기로 |
| 진입 | 미인증 |
| 유스케이스 | 인프라 5장 GitHub OAuth |

### 배치

```html
<!-- 카드가 없다. 앱 배경 위에 그대로 놓고 화면 세로 가운데에 둔다 -->
<div class="login" data-el="1">
  <div class="logo"><b>싱크독</b> <span class="mono">SyncDoc</span></div>
  <p class="lbl" data-el="1.1">개발자가 PM 없이 11단계 명세 체인을 쓰고,<br>에이전트가 그 명세를 따르게 하는 플랫폼</p>
  <a class="btn solid big" data-el="2">GitHub로 로그인</a>
  <p class="cap" data-el="3">로그인 후 원래 가려던 화면으로 돌아갑니다</p>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 로그인 영역 | 영역 | 로고, 안내, 버튼. 상단 바 없음 | — |
| 1.1 | 한 줄 설명 | 텍스트 | 이 도구가 무엇인지 | — |
| 2 | GitHub로 로그인 | 버튼 | | GitHub OAuth 동의 화면으로. 저장소 범위(`repo`)만 요청 |
| 3 | 복귀 안내 | 텍스트 | 원래 URL이 있었으면 그리로 간다는 안내 | — |

### 규칙

- 유일하게 공통 틀(상단 바)이 없는 화면
- **이 화면은 서버에서 아무것도 안 읽는다.** v1.2에 11단계 색 띠를 뒀다가 뺐다 — 아래 참고
- **카드에 담지 않는다.** 앱 배경 위에 로고·설명·버튼만 놓고 화면 세로 가운데에 둔다. 흰 판을 깔면 배경과 카드가 한 겹 더 갈리면서 로그인 폼이 '입력할 것이 많은 화면'처럼 보인다 — 여기서 할 일은 버튼 하나다
- **버튼은 콘텐츠 폭을 채우는 검정 채움이다.** 이 화면에서 유일한 동작이므로 유일한 강조여야 한다. 테두리만 있는 버튼으로 두면 배경과 대비가 없어 어디를 눌러야 할지 눈이 먼저 못 찾는다
- 복귀 안내(3)는 버튼보다 한 단계 낮은 캡션이다. 누를 것이 아니라 알림이다
- OAuth 성공 → 원래 가려던 URL. 없으면 UI-2
- OAuth 토큰은 앱 비밀키로 암호화해 저장한다(인프라 5장). 이 화면은 그 사실을 보여주지 않는다
- 등록된 저장소에 접근 권한이 없는 계정은 로그인은 되지만 프로젝트가 하나도 안 보인다

### 시나리오

**S-1 처음 들어온다**
1. 공개 주소를 열면 이 화면이다
2. GitHub로 로그인(2)을 누른다. GitHub 동의 화면에서 허용한다
3. UI-2로 간다

**S-2 링크로 문서에 바로 들어오려 했다**
1. 팀원이 보낸 `…/d/SYNC-PRD-001` 링크를 열었는데 로그인이 안 되어 있다
2. 이 화면으로 온다. 로그인한다
3. 원래 링크의 UI-5로 간다

---

## UI-3 프로젝트 초기화

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-3]] |
| 경로 | UI-2 위의 다이얼로그. 별도 경로 없음 |
| 진입 | UI-2 초기화 버튼(1.1) |
| 유스케이스 | [[SYNC-UC-001#UC-A1]] 기본 흐름 1~6, 확장 2a·2b·3a·4a (사람 경로) |

### 배치

```html
<div class="dialog narrow" data-el="1"><!-- 폭 560. 입력 셋이라 넓힐 이유가 없다 -->
<div class="dhead"><b>프로젝트 초기화</b><span class="grow"></span><span class="x" data-el="3.3">✕</span></div>
<div class="dbody">
  <div class="form" data-el="2"><!-- 입력 넷을 한 상자로 묶는다 -->
    <label>저장소 주소</label>
    <input class="inp wide mono" data-el="2.1" placeholder="https://github.com/owner/repo">
    <div class="lbl">싱크독이 이 저장소에 쓰기 권한이 있어야 합니다</div>

    <label>프로젝트 코드</label>
    <input class="inp mono" data-el="2.2" placeholder="AIRD" style="width:140px">
    <div class="lbl">영문 대문자 4자 이내. 문서 ID 앞부분이 됩니다 — 예: <code>AIRD-PRD-001</code></div>
    <div class="ferr" data-el="2.4">이미 쓰이는 코드입니다</div>

    <label>이름</label>
    <input class="inp wide" data-el="2.3" placeholder="에어데이터">

    <div class="willcommit" data-el="2.5">
      <b>커밋될 것</b>
      <div class="mono">docs/specs/_templates/ · 12개</div>
      <div class="mono">docs/specs/{01-RFQ, 02-PRD, … , 11-CODE}/</div>
      <div class="mono">docs/specs/assets/</div>
    </div>
  </div>
</div>
<div class="dfoot">
  <span class="grow"></span>
  <span class="btn" data-el="3.2">취소</span>
  <span class="btn solid" data-el="3.1">초기화</span>
</div>
</div>

<div class="dialog" data-el="4">
  <div class="dhead">기존 명세 발견</div>
  <div class="dbody">
    이 저장소에 이미 <code>docs/specs/</code>가 있습니다. 문서 12개.
    덮어쓰지 않고 그대로 가져와 등록할까요?
    <div class="dacts"><span class="btn" data-el="4.2">취소</span> <span class="btn" data-el="4.1" style="font-weight:600">가져와서 등록</span></div>
  </div>
</div>

<div class="banner err" data-el="5">push 실패: 권한 없음 (403). 만들던 작업물은 버렸습니다. 저장소 권한을 확인하세요.</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 브레드크럼(`프로젝트 › 참조 그래프`)과 제목. 통계(1.1)는 오른쪽 끝 | 브레드크럼 첫 조각 → UI-4 |
| 2 | 입력 폼 | 영역 | 세 입력(UC-A1 기본 흐름 1) | — |
| 2.1 | 저장소 주소 | 입력 | GitHub 저장소 URL | — |
| 2.2 | 프로젝트 코드 | 입력 | 영문 대문자 4자 이내 | — |
| 2.3 | 이름 | 입력 | 표시 이름 | — |
| 2.4 | 코드 오류 | 텍스트 | 초기화 시도 후 서버가 거부한 이유. 중복(UC-A1 2a) 또는 형식(2b). 시도 전엔 안 보임 | — |
| 2.5 | 커밋될 것 | 영역 | 등록하면 저장소에 무엇이 생기는지. 빈 저장소가 아니면 안 보인다 | — |
| 3.1 | 초기화 | 버튼 | | 서버에 요청. 결과에 따라 2.4 / 4 / 5 / UI-2 |
| 3.2 | 취소 | 버튼 | | UI-2로 |
| 3.3 | 닫기(✕) | 버튼 | | 3.2와 같다 |
| 4 | 기존 명세 발견 | 다이얼로그 | 저장소에 `docs/specs/`가 이미 있을 때(UC-A1 3a). 발견된 문서 수 | — |
| 4.1 | 가져와서 등록 | 버튼 | | UC-S6 인덱스 재구축 후 등록(3a2). UI-2로 |
| 4.2 | 취소 | 버튼 | | 등록 안 함(3a3). 폼으로 |
| 5 | push 실패 | 배너 | 원인(권한·네트워크). 작업물을 버렸다는 안내(UC-A1 4a) | — |

### 규칙

- 화면은 검사하지 않는다. 초기화(3.1)를 누르면 서버가 코드 형식·중복 → 저장소 접근 → `docs/specs/` 존재 순으로 판정한다
- **다이얼로그 폭은 560px.** 입력이 셋이라 넓힐 이유가 없다. 넓히면 입력창만 길어지고 폼이 헐거워진다
- **입력 넷을 테두리 상자 하나로 묶는다.** 머리·폼·발 세 층으로 읽혀야 어디까지가 채울 곳인지 보인다
- **초기화(3.1)가 주 동작이다.** 검정 채움. 취소와 같은 모양이면 어느 쪽이 진행인지 눈이 못 고른다
- 식별자를 넣는 칸은 고정폭이다 — 저장소 주소(2.1)와 프로젝트 코드(2.2). 힌트의 예시 문서 ID도 같다
- 입력 셋에 예시를 placeholder로 둔다. 무엇을 넣는 칸인지 라벨만으로는 모자란다
- 성공하면 UI-2로 가고 새 프로젝트 행이 11단계 전부 `미작성`으로 보인다
- MCP로도 같은 일을 할 수 있다(UC-A1 주 액터 에이전트). 이 화면은 MCP 연결 전에 시작하기 위한 입구

### 시나리오

**S-1 새 저장소를 등록한다** — UC-A1 기본 흐름 1~6
1. 세 칸(2.1~2.3)을 채우고 초기화(3.1)를 누른다
2. 서버가 clone → `docs/specs/` 생성 → 템플릿 복사 → 커밋 → push → 등록
3. UI-2로 가고 새 행이 보인다

**S-2 코드가 겹친다** — UC-A1 확장 2a
1. 코드에 `SYNC`를 넣고 초기화를 누른다
2. 2.4에 "이미 쓰이는 코드입니다"가 뜬다. 고쳐서 다시 누른다

**S-3 이미 명세가 있는 저장소** — UC-A1 확장 3a
1. 다른 팀원이 만들어둔 저장소를 등록하려 한다
2. 초기화를 누르면 다이얼로그(4)가 뜬다. 문서 12개가 있다
3. 가져와서 등록(4.1)을 누른다. 인덱스가 재구축되고 UI-2에 프로젝트가 뜬다

---

## UI-8 참조 그래프

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-8]] |
| 경로 | `/p/{프로젝트코드}/graph` |
| 진입 | UI-4 참조 그래프 버튼(2.1) |
| 유스케이스 | [[SYNC-UC-001#UC-H4]] 기본 흐름 1~3, 확장 2a·2b |

### 배치

```html
<div class="phead" data-el="1">
  <div>
    <div class="crumbs"><a href="/p/SYNC">싱크독</a><span class="sep">›</span><span>참조 그래프</span></div>
    <b>참조 그래프</b>
  </div>
  <span class="grow"></span>
  <span class="lbl" data-el="1.1">SYNC · 문서 21 · 항목 339 · 참조 949</span>
</div>

<div class="gcard">
  <div class="gbar" data-el="2">
    <span class="lbl">범위</span>
    <span class="btn on" data-el="2.1">전체</span>
    <span class="btn" data-el="2.2">승인만</span>
    <span class="btn" data-el="2.3">플래그 있는 것</span>
    <span class="sep"></span>
    <span class="lbl" data-el="2.4">노드에 마우스를 올려 그 항목만 보기</span>
    <span class="grow"></span>
    <span class="btn" data-el="2.5">전체보기</span>
  </div>

  <div class="canvas" data-el="3">
    <div class="colh">1 RFQ</div><div class="colh">2 PRD</div><div class="colh">3 SCN</div><div class="colh">…</div>
    <div class="node" data-el="3.1"><span class="nlabel">RFQ-001#Q1</span></div>
    <div class="node flag"><span class="nlabel">PRD-001#R1</span><span class="nflag">▲</span></div>
    <div class="node iso" data-el="3.5"><span class="nlabel">◌ PRD-001#R11</span></div>
    <svg class="edges">
      <path class="e" data-el="3.2"></path>
      <path class="e back" data-el="3.3"></path>
      <path class="e gone" data-el="3.4"></path>
    </svg>
  </div>

  <div class="glegend lbl" data-el="4">
    <span>노드 = 항목 · 열 = 11단계</span> <span>─ 참조 (하위 → 상위)</span>
    <span class="back">┈ 되돌아오는 참조</span> <span class="gone">┈ 미존재 참조</span> <span>◌ 고립 (참조 없음)</span>
    <span class="grow"></span>
    <span>노드에 마우스를 올리면 그 항목의 참조만 남는다 · 클릭 → 11단계 흐름</span>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 제목 | — |
| 1.1 | 통계 | 텍스트 | 지금 그려진 문서·항목·참조 수. **범위를 좁히면 같이 줄어든다** | — |
| 2 | 툴바 | 영역 | 범위 선택과 전체보기 | — |
| 2.1 | 전체 | 버튼 | 프로젝트의 모든 항목(기본) | 범위를 전체로 |
| 2.2 | 승인만 | 버튼 | **문서 상태가 `승인`인 문서의 항목**만. 확정된 뼈대만 본다 | 범위를 승인만으로(UC-H4 2b) |
| 2.3 | 플래그 있는 것 | 버튼 | **항목에 미해결 플래그가 붙은 것**만. 지금 흔들리는 곳만 본다 | 범위를 플래그로(UC-H4 2b) |
| 2.4 | 포커스 라벨 | 텍스트 | 노드에 올리기 전에는 안내. 올리면 `문서#항목 — 상위 n · 하위 m` | — |
| 2.5 | 전체보기 | 버튼 | | 상단 바까지 숨기고 화면 전체를 캔버스로. 다시 누르면 복귀 |
| 3 | 캔버스 | 영역 | 열 = 11단계, 노드 = 항목. 안에서 스크롤 | — |
| 3.1 | 노드 | 노드 | 항목 ID. 라벨이 넘치면 말줄임. 플래그가 있으면 경고색 테두리·배경과 오른쪽 끝 `▲` | UI-15 11단계 흐름 |
| 3.2 | 참조 간선 | 선 | 하위 → 상위. 상위가 왼쪽 열이면 곡선, 같은 열이면 왼쪽으로 나갔다 돌아오는 꺾은선 | — |
| 3.3 | 되돌아오는 간선 | 선 | 상위가 **오른쪽 열**일 때. 체인을 거슬러 올라가는 참조라 눈에 띄어야 한다 | — |
| 3.4 | 미존재 참조 | 선 | 대상 항목이 **정말로 없을 때**. 노드 왼쪽으로 짧게 뻗다 끊긴다 | — |
| 3.5 | 고립 노드 | 노드 | 상위도 하위도 없는 항목. 점선 테두리와 `◌`(UC-H4 2a) | 3.1과 같음 |
| 4 | 범례 | 텍스트 | 기호 설명. 선 견본을 실제 선으로 그린다. 선 종류를 말하는 두 항목은 라벨도 그 색. 조작 안내는 오른쪽 끝 | — |

### 규칙

- **열은 11단계 고정이고 항상 다 그린다.** 범위는 잘라내는 게 아니라 골라내는 것이다([[SYNC-UI-001#UI-8]] 7장 3). 단계·문서로 좁히던 v1.1 방식은 버렸다 — 한 걸음만 나가도 문서 대부분에 닿아 좁힌 의미가 없었다
- **범위 밖과 미존재는 다르다.** 범위를 좁혀 대상 노드가 빠진 간선은 그리지 않는다. `3.4` 미존재 참조는 **그 항목이 어느 문서에도 없을 때만** 쓴다. 둘을 같이 그리면 범위를 좁힐 때마다 없는 참조가 늘어난 것처럼 보인다
- **열 안 순서는 이웃의 평균 위치로 정렬한다.** 상위 기준 정렬과 하위 기준 정렬을 번갈아 네 번 돌린다. 이웃이 없는 노드는 제자리. 결정론적이라 언제 그려도 같은 그림이 나온다
- 되돌아오는 간선(3.3)은 노드를 관통하지 않는다. 모든 행 아래 전용 레인까지 내려가 가로지른 뒤 올라온다. DOM이 API·SEQ를 참조하는 경우가 여기 해당한다
- 노드에 마우스를 올리면 **직접 상위·하위만** 남기고 나머지를 흐린다. 전이적으로 따라가지 않는다 — 그건 UI-15가 한다
- **치수는 고정이다.** 열 간격 150px · 노드 폭 118px · 노드 높이 26px · 행 간격 40px · 캔버스 여백 18px. 열 간격과 노드 폭의 차 32px가 간선이 지나는 거터다 — 노드가 열 폭을 다 쓰면 선이 노드를 밟는다
- 간선에는 화살촉을 단다. 방향(하위 → 상위)이 그림만으로 읽혀야 한다. 되돌아오는 간선(3.3)의 모서리 반지름은 8px
- 배치 계산은 브라우저가 한다. 서버는 노드·간선 목록만 준다([[SYNC-MS-008#queries.graph_view]])

### 시나리오

**S-1 전체를 훑고 고립을 찾는다** — UC-H4 기본 흐름 1~2, 확장 2a
1. UI-4에서 참조 그래프를 연다. 11단계가 열로 늘어선다
2. PRD 열에 점선 테두리와 `◌`가 붙은 노드(3.5)가 보인다. 근거도 없고 파생도 없다
3. 노드를 눌러 UI-15로 가서 체인이 어디서 끊겼는지 본다

**S-2 흔들리는 곳만 본다** — UC-H4 확장 2b
1. 노드가 수백 개라 읽기 어렵다. `플래그 있는 것`(2.3)을 누른다
2. 미해결 플래그가 붙은 항목과 그것들 사이 참조만 남는다. 통계(1.1)도 그만큼 줄어든다
3. `승인만`(2.2)으로 바꾸면 반대로 확정된 뼈대만 남는다

**S-3 한 항목의 이웃을 본다** — UC-H4 기본 흐름 3
1. `PRD-001#R1` 노드(3.1)에 마우스를 올린다
2. 그 항목의 직접 상위·하위만 진하게 남고 나머지가 흐려진다. 포커스 라벨(2.4)에 `상위 1 · 하위 4`
3. 더 멀리 따라가려면 노드를 눌러 UI-15로

**S-4 좁게 보다가 크게 본다**
1. 캔버스가 답답하다. 전체보기(2.5)를 누른다
2. 상단 바까지 사라지고 화면 전체가 캔버스가 된다
3. 다시 누르면 돌아온다

---

## UI-9 순서대로 읽기

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-9]] |
| 경로 | `/p/{프로젝트코드}/read` · `?stage=N` |
| 진입 | UI-4 순서대로 읽기 버튼(2.2) |
| 유스케이스 | [[SYNC-UC-001#UC-H16]] 기본 흐름 1~3, 확장 2a |

### 배치

```html
<!-- 단계 레일은 전폭 서브바다. 제목은 여기가 아니라 본문 머리에 있다 -->
<div class="steprail" data-el="1">
  <a class="back" href="/p/SYNC">← 싱크독</a>
  <div class="steps" data-el="2">
    <span class="stp"><span class="no">1</span> RFQ<i class="dot dot-approved"></i></span><span class="stp"><span class="no">2</span> PRD<i class="dot dot-approved"></i></span><span class="stp cur"><span class="no">3</span> SCN<i class="dot dot-review"></i></span><span class="stp"><span class="no">4</span> UC<i class="dot dot-draft"></i></span><span class="stp na"><span class="no">5</span> INFRA<i class="dot dot-none"></i></span>
  </div>
</div>

<div class="readbody">
  <div class="banner" data-el="3">이 단계에 승인된 문서가 없습니다. <b>SYNC-SCN-001</b>은 <b>검토중</b>입니다. <span class="btn sm" data-el="3.1">초안 보기</span></div>

  <article class="main" data-el="4">
    <div class="dochead">
      <div class="kicker mono" data-el="4.1">싱크독 · 3/11 · SYNC-SCN-001 · 검토중 v4</div>
      <h1>사용자 시나리오 — 싱크독</h1>
      <p class="lead">누가 어떤 상황에서 싱크독을 쓰는지. 여기서 정한 시나리오가 유스케이스의 근거가 된다.</p>
    </div>
    <h2>1. 페르소나</h2>
    <p>박호영 — 디포커스 AI팀 개발자. 싱크독을 만들었고 자기 프로젝트에도 쓴다…</p>
    <h2>2. 시나리오</h2>
    <p>S1 대화하다가 명세가 쌓인다 …</p>
  </article>

  <!-- 이동 줄은 본문 밖. 안에 넣으면 문서의 일부처럼 읽힌다 -->
  <div class="docnav" data-el="5">
    <span class="btn" data-el="5.1">← 2 PRD</span>
    <span class="btn" data-el="5.3">이 문서 열기</span>
    <span class="grow"></span>
    <span class="btn solid" data-el="5.2">4 USECASE →</span>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 단계 레일 | 영역 | 화면 맨 위 전폭 서브바. 왼쪽에 `← 프로젝트 이름`, 그 뒤로 단계 칩(2) | 왼쪽 링크 → UI-4 |
| 2 | 단계 표시 | 진행 표시 | 11단계 칩. 번호와 타입 코드는 항상 보인다. 번호는 흐리게, 상태 점은 **라벨 뒤**. 현재 단계는 채워서 | 단계 클릭 → 그 단계로 |
| 3 | 미확정 배너 | 배너 | 이 단계에 승인 문서가 없을 때. 있는 문서와 상태(UC-H16 2a) | — |
| 3.1 | 초안 보기 | 버튼 | | 승인 아닌 문서를 본문(4)에 띄운다(UC-H16 2a1) |
| 4 | 본문 | 사람용 뷰 | 현재 단계의 승인 문서. UI-5 유저용 탭과 같은 렌더링, 목차·패널 없음(UC-H16 기본 흐름 2) | — |
| 4.1 | 위치 | 텍스트 | 문서 머리의 킥커. `프로젝트 · n/11 · 문서ID · 상태 v버전`. 그 아래 제목과 리드가 온다 | — |
| 5 | 이동 | 영역 | 앞·뒤 단계와 문서 열기 | — |
| 5.1 | 이전 단계 | 버튼 | | 앞 단계로 |
| 5.2 | 다음 단계 | 버튼 | 이 화면의 주 동선이라 채운 버튼이다 | 뒤 단계로(UC-H16 기본 흐름 3) |
| 5.3 | 이 문서 열기 | 버튼 | | 현재 문서의 UI-5 |

### 규칙

- 기본은 승인 문서만. 승인이 없으면 배너(3)가 뜨고 본문은 비어 있다. 초안 보기(3.1)를 눌러야 보인다
- 한 단계에 승인 문서가 여럿이면(DOM처럼) 문서 ID 순으로 이어서 보여준다
- 문서가 하나도 없는 단계(단계 표시 `na`)는 다음(5.2)이 건너뛴다
- 단계 표시(2)는 가로로만 넘친다. 세로 넘침을 막지 않으면 칩 줄이 본문을 밀어낸다
- 본문(4)에 참조 링크는 있으나 클릭하면 UI-5로 간다. 이 화면은 순서를 유지하는 게 목적이라 안에서 점프하지 않는다
- 문서마다 머리(킥커 4.1 · 제목 · 리드)를 얹는다. 리드는 원본 0장 첫 문단이다 — UI-5 유저용 본문과 같은 블록
- 배너·본문·이동 줄은 같은 좌우 경계를 쓴다(`max-width:760px` 가운데). 폭이 서로 다르면 화면이 층져 보인다
- 이동 줄(5)은 본문 카드 **밖**이다. 안에 두면 문서의 일부처럼 읽힌다

### 시나리오

**S-1 처음부터 끝까지 읽는다** — UC-H16 기본 흐름 1~3
1. UI-4에서 순서대로 읽기를 연다. 1 RFQ부터 시작
2. 다음(5.2)을 누르며 내려간다. 단계 표시(2)에서 어디까지 왔는지 본다
3. 7 UI 이후는 문서가 없어 6 DOM에서 끝난다

**S-2 승인 안 된 단계를 만난다** — UC-H16 확장 2a
1. 3 SCN에 도착하니 배너(3)가 뜬다. 검토중이라 확정본이 없다
2. 초안 보기(3.1)를 누르면 검토중인 문서가 본문에 보인다. 4.1에 "검토중 v4"라고 표시된다
3. 확정 아님을 알고 읽는다

**S-3 읽다가 자세히 보고 싶다**
1. 본문에서 `[[SYNC-PRD-001#R12]]` 참조를 눌렀다
2. UI-5로 이동한다. 돌아오려면 뒤로 가기

---

## UI-13 설정

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-13]] |
| 경로 | 어느 화면 위든 뜨는 다이얼로그. 별도 경로 없음 |
| 진입 | 상단 바 `설정` |
| 유스케이스 | 인프라 5장 MCP 토큰 · [[SYNC-DOM-003#access_tokens]] · [[SYNC-UC-001#UC-S6]](관리 카드) |

### 배치

```html
<div class="dialog" data-el="1">
  <div class="dhead"><span>설정</span><span class="grow"></span><span class="x" data-el="7">✕</span></div>
  <div class="dbody">

    <section class="card" data-el="2">
      <div class="cardh"><b>내 계정</b></div>
      <div class="row"><span data-el="2.1">HoyoungParkme</span> <span class="lbl">GitHub · 박호영</span><span class="grow"></span><span class="btn sm" data-el="2.2">로그아웃</span></div>
    </section>

    <section class="card" data-el="3">
      <div class="cardh"><b>MCP 토큰</b> <span class="lbl">에이전트가 싱크독에 붙을 때 씁니다</span><span class="grow"></span><span class="btn sm" data-el="3.4">+ 발급</span></div>
      <div class="tokbox" data-el="4">
        <b>한 번만 보입니다. 지금 복사하세요.</b>
        <div class="tok" data-el="4.1">syncdoc_pat_7f3a…c91e</div>
        <span class="btn sm" data-el="4.2">복사</span>
      </div>
      <div class="row" data-el="3.1">
        <b>Claude Code 노트북</b> <span class="lbl mono">syncdoc_pat_7f3a…</span> <span class="lbl">발급 09-01</span>
        <span class="grow"></span> <span class="lbl" data-el="3.5">마지막 사용 12분 전</span> <span class="btn sm" data-el="3.2">폐기</span>
      </div>
      <div class="row dimrow"><b>테스트용</b> <span class="lbl">발급 08-28 · <s>폐기됨 09-02</s></span></div>
      <div class="row"><input class="inp" data-el="3.3" placeholder="이름 — 예: Gemini 노트북"></div>
    </section>

    <section class="card" data-el="8">
      <div class="cardh"><b>클라이언트 설정</b></div>
      <p class="lbl">Claude Code · Codex · Gemini CLI가 같은 엔드포인트를 씁니다.</p>
      <pre class="snippet" data-el="8.1">{
  "mcpServers": {
    "syncdoc": {
      "url": "https://…/mcp",
      "headers": { "Authorization": "Bearer syncdoc_pat_…" }
    }
  }
}</pre>
    </section>

    <section class="card" data-el="5">
      <div class="cardh"><b>관리</b> <span class="lbl">인덱스 재구축 · 저장소 동기화</span><span class="grow"></span><span class="btn sm" data-el="5.1">열기</span></div>
      <div class="admin" data-el="6"><!-- UI-14 --></div>
    </section>

  </div>
  <div class="dfoot"><span class="grow"></span><span class="btn" data-el="9">닫기</span></div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 다이얼로그 | 다이얼로그 | 어느 화면 위에서든 뜬다. 닫으면 보던 화면 그대로 | — |
| 2 | 내 계정 | 카드 | GitHub 로그인 ID(2.1), 표시 이름 | — |
| 2.1 | 로그인 ID | 텍스트 | GitHub 계정 | — |
| 2.2 | 로그아웃 | 버튼 | | 세션 종료 → UI-1 |
| 3 | MCP 토큰 | 카드 | 내 토큰 목록과 발급 | — |
| 3.1 | 토큰 행 | 행 | 이름 · 접두어 · 발급일 · 마지막 사용(3.5) · 폐기 여부. **원문은 안 보인다**(해시만 저장) | — |
| 3.2 | 폐기 | 버튼 | 유효한 토큰에만 | 확인 후 폐기. 그 토큰으로 오는 MCP 요청이 거부된다 |
| 3.3 | 토큰 이름 | 입력 | 어느 에이전트에 쓸지 | — |
| 3.4 | 발급 | 버튼 | 3.3이 비어 있으면 비활성 | 발급하고 원문 상자(4)를 연다 |
| 3.5 | 마지막 사용 | 텍스트 | 이 토큰으로 마지막에 들어온 시각. 한 번도 안 썼으면 `없음` | — |
| 4 | 토큰 원문 상자 | 영역 | 발급 직후에만. **한 번만 보인다** | — |
| 4.1 | 토큰 원문 | 텍스트 | 발급된 토큰 | — |
| 4.2 | 복사 | 버튼 | | 클립보드로 |
| 5 | 관리 | 카드 | 관리 영역 입구 | — |
| 5.1 | 열기 | 버튼 | 접혀 있음 / 펼침 | 6을 펼치거나 접는다 |
| 6 | 관리 영역 | 영역 | UI-14. 펼쳤을 때만 | — |
| 7 | 닫기(✕) | 버튼 | | 닫힘 |
| 8 | 클라이언트 설정 | 카드 | 에이전트에 붙여넣을 MCP 설정 | — |
| 8.1 | 설정 스니펫 | 텍스트 | 읽기 전용 JSON. 주소와 토큰 자리 | — |
| 9 | 닫기 | 버튼 | | 닫힘 |

### 규칙

- **토큰 원문은 발급 직후 상자(4)에서만 보인다.** 서버는 해시만 저장하므로 다시 보여줄 수 없다(인프라 5장). 다이얼로그를 닫으면 상자도 사라진다
- 폐기된 토큰 행은 흐리게 남긴다. 지우지 않는다
- **폐기(3.2)는 확인을 받는다.** 되돌릴 수 없고 그 토큰을 쓰던 에이전트가 즉시 끊긴다
- 토큰으로 들어온 MCP 요청은 발급자 계정으로 기록된다. 남에게 토큰을 주면 그 사람 작업이 내 이름으로 남는다 — 이 안내를 3번 카드에 둔다
- **토큰에 프로젝트 범위가 없다.** 토큰 하나가 그 사람이 보는 모든 프로젝트에 쓴다([[SYNC-PRD-001]] 6장). 만료도 없다(인프라 9장) — 그래서 `마지막 사용`(3.5)이 안 쓰는 토큰을 찾는 유일한 단서다
- 관리(6)는 **접힌 채로 연다.** 인덱스 재구축이 위험한 동작이라 한 번 더 눌러야 보인다([[SYNC-UI-001#UI-14]] 7장 4)

### 시나리오

**S-1 새 에이전트를 연결한다**
1. 상단 바 `설정`을 눌러 다이얼로그를 연다
2. 토큰 이름(3.3)에 `Gemini 노트북`을 적고 발급(3.4)
3. 원문 상자(4)가 뜬다. 복사(4.2)한다
4. 클라이언트 설정(8.1)을 보고 Gemini의 MCP 설정에 붙여넣는다
5. 목록(3)에 새 행이 생기고 `마지막 사용 없음`이다

**S-2 안 쓰는 토큰을 정리한다**
1. 목록에서 `마지막 사용 3개월 전`인 행을 본다
2. 폐기(3.2)를 누르고 확인한다. 즉시 거부된다

---

## UI-14 관리

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-14]] |
| 경로 | 없음. **UI-13 다이얼로그 안 관리 카드(6)** |
| 진입 | UI-13 관리 카드 열기(5.1) |
| 유스케이스 | [[SYNC-UC-001#UC-S6]] (사람이 관리 화면에서 실행) · [[SYNC-DOM-003#repositories]] |

### 배치

```html
<!-- UI-13 다이얼로그 안 관리 카드(6)를 펼친 모습 -->
<div class="adminh" data-el="1"><span class="lbl">위험한 동작이 있습니다</span></div>

<div class="adminbody">
  <table class="vers" data-el="2">
    <tr><th>프로젝트</th><th>저장소</th><th>마지막 처리 커밋</th><th>동기화</th><th></th></tr>
    <tr data-el="2.1"><td><b>SYNC</b></td><td class="lbl">dfocus/syncdoc</td><td><span class="mono" data-el="2.2">a1b2c3d</span> <span class="lbl">1시간 전</span></td><td data-el="2.3"><span class="st ok">최신</span></td><td><span class="btn sm" data-el="3">인덱스 재구축</span></td></tr>
    <tr><td><b>DBA</b></td><td class="lbl">dfocus/dba-ax</td><td><span class="mono">9e8f7a6</span> <span class="lbl">3일 전</span></td><td><span class="st rv">밀림 2</span></td><td><span class="btn sm">인덱스 재구축</span></td></tr>
    <tr><td><b>AIRD</b></td><td class="lbl">dfocus/airdata</td><td><span class="mono">—</span></td><td><span class="st na">문서 없음</span></td><td><span class="btn sm">인덱스 재구축</span></td></tr>
  </table>

  <div class="dialog" data-el="4">
    <div class="dhead">SYNC 인덱스 재구축</div>
    <div class="dbody">
      저장소의 모든 MD를 다시 읽어 참조 관계와 버전 목록을 처음부터 만듭니다.
      <b>플래그·전파 결정·댓글은 건드리지 않습니다.</b> 문서가 많으면 몇 분 걸립니다.
      <div class="dacts"><span class="btn" data-el="4.2">취소</span> <span class="btn" data-el="4.1" style="font-weight:600">재구축</span></div>
    </div>
  </div>

  <section class="grp" data-el="5">
    <h4>재구축 결과 <span class="lbl">SYNC · 방금</span></h4>
    <div class="row"><span data-el="5.1">문서 9 · 항목 87 · 참조 142 · 버전 41</span></div>
    <div class="row"><span data-el="5.2">규약 오류 1 — <b>SYNC-UC-001</b> frontmatter.status 누락</span></div>
  </section>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 경고 줄 | 텍스트 | 위험한 동작이 있다는 안내. 제목은 카드가 이미 달고 있다 | — |
| 2 | 저장소 표 | 표 | 프로젝트마다 저장소와 동기화 상태 | — |
| 2.1 | 저장소 행 | 행 | 프로젝트, 저장소, 마지막 처리 커밋(2.2), 동기화(2.3) | — |
| 2.2 | 마지막 처리 커밋 | 텍스트 | `repositories.last_processed_commit`과 시각 | 새 탭으로 GitHub 커밋 |
| 2.3 | 동기화 상태 | 뱃지 | 원격 최신과 같으면 `최신`, 처리 안 한 커밋이 있으면 `밀림 N`(UC-G1 1a·1b) | — |
| 3 | 인덱스 재구축 | 버튼 | 행마다 | 확인 다이얼로그(4) |
| 4 | 재구축 확인 | 다이얼로그 | 무엇을 다시 만들고 무엇은 안 건드리는지(UC-S6 최소 보장) | — |
| 4.1 | 재구축 | 버튼 | | UC-S6 실행. 끝나면 결과(5) |
| 4.2 | 취소 | 버튼 | | 닫힘 |
| 5 | 재구축 결과 | 영역 | 마지막 실행 결과(UC-S6 기본 흐름 4) | — |
| 5.1 | 집계 | 텍스트 | 읽은 문서·항목·참조·버전 수 | — |
| 5.2 | 규약 오류 목록 | 목록 | 재구축 중 발견된 위반 문서(UC-S6 2a) | 문서 클릭 → UI-5 |

### 규칙

- **독립 화면이 아니라 UI-13 안의 영역이다.** v1.2에서 별도 페이지를 없앴다. 재구축은 위험해서 깊이 두는 게 맞지만, 자주 보는 동기화 상태는 UI-4에도 함께 내보낸다([[SYNC-UI-001#UI-14]] 7장 4)
- 재구축은 참조 테이블·버전 목록·항목 테이블을 지우고 다시 만든다. 플래그·전파결정·댓글은 그대로다(UC-S6 최소 보장, 인프라 6장)
- 동기화 상태(2.3)는 **DB에서 읽는다.** 폴링이 `behind_by`·`fetched_at`을 갱신하므로 이 카드를 열 때마다 fetch가 돌지 않는다([[SYNC-DOM-002#Repository]])
- `밀림 N`은 폴링이 잡아 처리한다(UC-G1 1b). 이 화면에 수동 동기화 버튼은 없다 — 유스케이스에 없다
- 재구축 확인(4)은 **UI-13 위에 한 겹 더** 뜬다. 다이얼로그 위의 다이얼로그다
- 이 화면은 누구나 들어올 수 있다. 권한 구분이 없기 때문이다(PRD 비목표). 대신 확인 다이얼로그(4)가 한 번 막는다

### 시나리오

**S-1 DB를 날려먹었다** — UC-S6
1. Postgres를 다시 만들었다. 문서는 GitHub에 다 있다
2. 프로젝트마다 인덱스 재구축(3)을 누른다. 확인(4.1)
3. 결과(5)에 집계와 규약 오류가 뜬다. 참조 그래프가 살아난다
4. 플래그·댓글은 돌아오지 않는다. 인프라 6장에서 감수하기로 한 것

**S-2 서버를 며칠 꺼뒀다**
1. 표(2)에서 DBA가 `밀림 2`(2.3)다. 꺼진 동안 누가 push했다
2. 폴링이 곧 잡는다. 기다리거나, 급하면 재구축(3)

---

## UI-15 11단계 흐름

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-15]] |
| 경로 | UI-8 위의 다이얼로그. 별도 경로 없음 |
| 진입 | UI-8 노드 클릭(3.1) · 이 다이얼로그 안 다른 항목 칩(3.1) |
| 유스케이스 | [[SYNC-UC-001#UC-H4]] 기본 흐름 3 |

### 배치

```html
<div class="dialog" data-el="1">
  <div class="dhead">
    <span data-el="1.1">SYNC-UC-001#UC-A6 — 명세를 작성·수정한다</span>
    <span class="lbl" data-el="1.2">상위로 3개 · 하위로 5개 이어짐</span>
    <span class="grow"></span>
    <span class="x" data-el="5">✕</span>
  </div>
  <div class="dbody">
    <p class="lbl" data-el="2">이 항목이 11단계 체인에서 어디에 있고 어디로 흐르는지. 위는 근거로 삼은 것, 아래는 이 항목을 근거로 삼은 것.</p>

    <div class="chain" data-el="3">
      <div class="crow">
        <div class="cstage" data-el="3.2">1 RFQ<br><span class="lbl">근거 ↑</span></div>
        <div class="cchips"><span class="chip" data-el="3.1">RFQ-001#Q1 원본은 누가 읽는가</span></div>
      </div>
      <div class="crow cur">
        <div class="cstage">4 UC<br><span class="lbl">이 항목</span></div>
        <div class="cchips"><span class="chip me">UC-001#UC-A6 명세를 작성·수정한다</span></div>
      </div>
      <div class="crow empty">
        <div class="cstage">5 INFRA</div>
        <div class="cchips" data-el="3.3">이 단계에는 이어지는 항목이 없다</div>
      </div>
      <div class="crow">
        <div class="cstage">6 DOM<br><span class="lbl">파생 ↓</span></div>
        <div class="cchips"><span class="chip">DOM-002#SpecService 명세 저장</span></div>
      </div>
    </div>
  </div>
  <div class="dfoot">
    <span class="lbl">참조는 하위 → 상위로만 적히고, 역방향은 계산된 것이다</span>
    <span class="grow"></span>
    <span class="btn" data-el="6">닫기</span>
    <span class="btn" data-el="4">문서 뷰로 열기</span>
  </div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 다이얼로그 | 다이얼로그 | UI-8 위에 뜬다 | — |
| 1.1 | 제목 | 텍스트 | 기준 항목의 ID와 제목 | — |
| 1.2 | 이어진 수 | 텍스트 | 상위 방향·하위 방향으로 **전이적으로** 닿는 항목 수 | — |
| 2 | 안내 | 텍스트 | 위가 근거, 아래가 파생이라는 설명 | — |
| 3 | 체인 | 영역 | **11단계를 다 나열한다.** 항목이 없는 단계도 남긴다 | — |
| 3.1 | 항목 칩 | 칩 | 상태 점 · 항목 ID · 제목 · 플래그 `▲`. 없는 항목이면 점선과 `(없는 항목)` | 그 항목 기준으로 다시 그린다 |
| 3.2 | 단계 라벨 | 텍스트 | 단계 번호·코드와 역할(`근거 ↑` / `이 항목` / `파생 ↓`) | — |
| 3.3 | 빈 단계 | 텍스트 | `이 단계에는 이어지는 항목이 없다` | — |
| 4 | 문서 뷰로 열기 | 버튼 | | 기준 항목의 UI-5 해당 위치 |
| 5 | 닫기(✕) | 버튼 | | 닫힘 |
| 6 | 닫기 | 버튼 | | 닫힘 |

### 규칙

- **직접 참조가 아니라 전이적 폐포다.** 상위 방향과 하위 방향으로 각각 너비 우선 탐색을 돌려 닿는 항목을 다 모은다. 사이클이 있어도 방문 표시로 멈춘다
- **역할(3.2)은 단계 번호가 아니라 폐포 방향으로 정한다.** 상위 폐포에 든 항목이 있는 단계는 `근거 ↑`, 하위 폐포면 `파생 ↓`. 되돌아오는 참조가 있으면 근거가 오른쪽 단계에 놓일 수 있는데, 단계 번호로 판정하면 그걸 `파생`으로 잘못 적는다
- 한 단계에 두 방향이 다 걸리면 `근거 ↑ · 파생 ↓`로 함께 적는다
- **항목이 없는 단계도 회색으로 남긴다.** 체인이 어디서 끊겼는지 보이는 게 이 화면의 목적이다. 빈 단계를 접으면 "UI 단계에 아무것도 안 이어졌다"는 사실이 안 보인다
- 칩(3.1)을 누르면 그 항목 기준으로 다시 그린다. 뒤로 가기는 없다 — 계속 따라가는 화면이지 되짚는 화면이 아니다
- 범위(UI-8 2.1~2.3)와 무관하게 항상 전체 참조를 본다. 범위는 그리는 것을 고르는 조작이지 관계를 지우는 조작이 아니다

### 시나리오

**S-1 이 요구가 어디까지 갔나** — UC-H4 기본 흐름 3
1. UI-8에서 `PRD-001#R1` 노드를 누른다
2. 11단계가 세로로 늘어선다. 위로 RFQ 하나, 아래로 UC·DOM·API·MS가 채워져 있다
3. `9 SEQ` 행이 비어 있다(3.3). 시퀀스 명세가 이 요구를 안 다뤘다는 뜻이다

**S-2 근거를 거슬러 올라간다**
1. `근거 ↑`에 있는 `RFQ-001#Q1` 칩(3.1)을 누른다
2. 그 항목 기준으로 다시 그려진다. 이제 Q1이 `이 항목`이고 아래로 파생이 쭉 보인다

**S-3 문서로 들어간다**
1. 흐름을 다 봤다. `문서 뷰로 열기`(4)를 누른다
2. UI-5가 그 항목 위치에서 열린다

---

## UI-16 사용 방법

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-16]] |
| 경로 | 어느 화면 위든 뜨는 다이얼로그. 별도 경로 없음 |
| 진입 | 상단 바 `사용 방법` |
| 유스케이스 | 없음 — 안내 전용 |

### 배치

```html
<div class="dialog" data-el="1">
  <div class="dhead"><span>사용 방법</span><span class="grow"></span><span class="x" data-el="4">✕</span></div>
  <div class="dbody">
    <table class="grid" data-el="2">
      <tr class="hd"><th></th><th>무엇</th><th>어떻게</th><th>어디서</th></tr>
      <tr data-el="2.1"><td>1</td><td>저장소를 등록한다</td><td>주소·코드·이름</td><td>프로젝트 목록</td></tr>
      <tr><td>2</td><td>에이전트를 붙인다</td><td>MCP 토큰 발급 후 설정에 붙여넣기</td><td>설정</td></tr>
      <tr><td>3</td><td>명세를 쌓는다</td><td>에이전트에게 시킨다. 웹에는 편집이 없다</td><td>에이전트</td></tr>
      <tr><td>4</td><td>읽고 확정한다</td><td>상태를 초안 → 검토중 → 승인으로</td><td>문서 뷰</td></tr>
      <tr><td>5</td><td>바뀐 것을 따라간다</td><td>전파 선택, 확인 필요 처리</td><td>내 할 일</td></tr>
      <tr><td>6</td><td>체인을 본다</td><td>참조 그래프에서 노드 클릭</td><td>참조 그래프</td></tr>
    </table>

    <table class="grid" data-el="3">
      <tr class="hd"><th>#</th><th>코드</th><th>이름</th><th>항목 ID</th></tr>
      <tr data-el="3.1"><td>1</td><td>RFQ</td><td>요구·인터뷰</td><td><code>Q1</code></td></tr>
      <tr><td>2</td><td>PRD</td><td>제품 요구</td><td><code>G1</code> <code>R12</code></td></tr>
      <tr class="std" data-el="3.2"><td>—</td><td>STD</td><td>표준 (단계 밖)</td><td>규칙 항목</td></tr>
    </table>

    <p class="lbl" data-el="3.3">문서 ID는 <code>{프로젝트코드}-{타입}-{번호}</code>, 항목 ID는 <code>{문서ID}#{항목번호}</code>, 본문 참조는 <code>[[항목ID]]</code>.</p>
    <p class="note" data-el="3.4">11단계 순서는 권장이지 강제가 아니다. 건너뛰어도 막지 않고 표시만 한다.</p>
  </div>
  <div class="dfoot"><span class="grow"></span><span class="btn" data-el="5">닫기</span></div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 다이얼로그 | 다이얼로그 | 어느 화면 위에서든 뜬다 | — |
| 2 | 사용 순서 | 표 | 여섯 단계. 무엇을·어떻게·어디서 | — |
| 2.1 | 순서 행 | 행 | 한 단계 | — |
| 3 | 11단계 표 | 표 | 단계 번호·코드·이름·항목 ID 형식 | — |
| 3.1 | 단계 행 | 행 | 한 단계 | — |
| 3.2 | 표준 행 | 행 | `STD`. 단계 밖이라 회색으로 마지막에 | — |
| 3.3 | ID 문법 | 텍스트 | 문서 ID·항목 ID·참조 표기 | — |
| 3.4 | 주의 | 텍스트 | 11단계 순서는 강제가 아니라는 안내 | — |
| 4 | 닫기(✕) | 버튼 | | 닫힘 |
| 5 | 닫기 | 버튼 | | 닫힘 |

### 규칙

- 이 화면은 **읽기 전용이고 상태가 없다.** 어디서 열든 같은 내용이고, 닫으면 원래 화면 그대로다
- 항목 ID 형식은 [[SYNC-STD-001]] 2장의 타입별 패턴을 사람 말로 옮긴 것이다. 규약이 바뀌면 여기도 바뀐다
- **"순서는 강제가 아니다"를 빼지 않는다.** 11단계를 보면 차례로 다 채워야 하는 것처럼 읽힌다. 실제로는 건너뛴 단계를 표시만 하고 막지 않는다([[SYNC-UC-001#UC-H14]] 1b)

### 시나리오

**S-1 처음 들어온 사람**
1. 상단 바에서 `사용 방법`을 누른다
2. 여섯 단계를 읽고 "웹에는 편집이 없다"는 것을 안다
3. 11단계 표에서 자기 프로젝트가 어느 단계까지 와 있는지 가늠한다

**S-2 항목 ID 형식이 기억 안 난다**
1. 다이얼로그를 열어 11단계 표(3)에서 그 타입의 항목 ID 형식을 본다
2. 닫으면 보던 화면 그대로다

