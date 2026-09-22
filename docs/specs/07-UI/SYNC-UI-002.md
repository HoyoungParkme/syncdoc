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
| 배치 | 요소가 어디 있나 | HTML. 스타일은 자기 완결 — 공통 틀 절의 `<style>` + 화면 자신의 `<style>`. 요소마다 `data-el` 번호. 뷰는 iframe으로 그대로 그린다(카드 Z) |
| 요소 | 각 요소가 뭘 보여주고 누르면 뭐 되나 | 표 |
| 규칙 | 상태별 표시, 조건부 노출, 유효성 | 목록 |
| 시나리오 | 요소들이 이어져 무엇을 이루나 | 번호 매긴 흐름. 유스케이스 흐름을 이 화면 동작으로 옮긴 것 |

사람용 뷰는 배치를 왼쪽에, 요소·규칙·시나리오를 오른쪽에 나란히 렌더링한다. 요소 번호를 누르면 양쪽이 서로 강조된다.

**공통 틀**(상단 바)은 UI-5에서 한 번 정의하고 다른 화면에서는 생략한다. 여러 화면이 같이 쓰는 조각은 1장 공통 컴포넌트에 모았다. **스타일**은 「공통 틀」 절의 html 블록(`<style>`만)에 있고, 뷰가 그것을 이 문서 모든 화면의 iframe 앞에 넣는다([[SYNC-STD-001]] 2.7).

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
- **확인 버튼의 라벨이 상태를 말한다.** `휴지통에 넣기` / `삭제하고 되돌리기`처럼, 누르면 무슨 일이 생기는지 버튼에 적는다
- 다이얼로그 위에 다이얼로그가 뜰 수 있다 — UI-13 위의 재구축 확인이 그렇다

지금 쓰는 곳: UI-3 초기화 · UI-3 기존 명세 발견 · UI-4 목록 · UI-5 휴지통 확인 · UI-7 되돌리기 · UI-7 삭제 확인 · UI-13 설정 · UI-14 재구축 확인 · UI-15 11단계 흐름 · UI-16 사용 방법.

### 1.2 툴팁

브라우저 기본 툴팁을 쓰지 않는다. 줄바꿈이 안 되고 지연이 길다.

- 대상 위쪽 가운데. 흰 배경, 테두리, 그림자
- 마우스를 통과시킨다 — 툴팁이 대상을 가려 클릭을 막으면 안 된다
- **사라지는 조건이 마우스가 벗어날 때만이면 부족하다.** 클릭으로 대상이 사라지면 툴팁만 남는다. 화면 이동·스크롤·아무 곳 클릭에도 지운다

### 1.3 토스트

화면 아래 가운데. 잉크색 바탕에 흰 글씨. 2.6초 뒤 스스로 사라진다.

되돌릴 수 없는 일이 **끝났을 때** 무엇이 기록됐는지 알린다 — 상태 전환, 토큰 폐기, 재구축 완료. 누를 것이 없으므로 확인을 요구하는 데는 쓰지 않는다.

### 1.4 상태 필

`초안` · `완료` 둘. 상태색 바탕에 작은 알약. 완료만 글씨가 희다.

문서 상태를 보여주는 곳이면 어디든 같은 모양이다. 단계 대표 상태에도 같은 것을 쓴다.

### 1.5 항목 ID 뱃지

`R12` 같은 항목 ID를 감싸는 작은 사각 뱃지. 고정폭 글꼴, 항목 ID 뱃지 색 바탕([[SYNC-UI-001]] 3.1).

**항목 ID는 늘 뱃지로 감싼다.** 본문 글자와 섞이면 어디까지가 ID인지 안 보인다. 참조 표기(`[[…]]`)는 뱃지가 아니라 점선 밑줄이다 — 누르면 이동한다는 뜻이 다르다.

---

### 1.6 프로젝트 표기

프로젝트는 어디서든 **`[코드] 이름`**으로 적는다 — `[SYNC] 싱크독`. 코드는 고정폭·굵게, **대괄호까지 고정폭**이고, 이름은 본문체다.

- **대괄호가 있어야 코드가 문서 ID와 같은 어휘로 읽힌다.** `SYNC-PRD-001`의 접두가 `[SYNC]`다 — 목록에서 코드가 한 열처럼 훑히고, 이름이 코드의 일부인지 헷갈리지 않는다(`INS 보험청구심사 어시스턴트`는 어디까지가 코드인지 한 번 읽어야 안다)
- **여덟 자리가 전부 이 하나를 쓴다** — UI-2 목록 행 · UI-4 상세 머리(1.1·1.2) · UI-5 문서 바 브레드크럼과 킥커 · UI-7 문서 바 · UI-8 브레드크럼 · UI-9 단계 레일 `← [코드] 이름` · UI-14 관리 표. 한 곳만 다르면 어휘가 아니라 실수로 보인다
- 코드만 있고 이름이 없는 자리(결과 라벨의 `SYNC · 방금`)는 대괄호를 안 친다 — 대괄호는 이름과 붙을 때 코드를 가르는 표시다

### 1.7 그림 전체보기

유저용 본문 안의 **모든 그림** — mermaid 렌더 결과(구성도·클래스·ERD·흐름), UC 패키지 그림, SEQ 시퀀스 — 에 오른쪽 위 작은 「전체보기」 버튼이 붙는다. 본문 폭 안에서 그림이 작아 못 읽는 것을 여기서 푼다.

- **누르면 화면 전체다.** UI-8 전체보기(2.5)와 같은 층(3.3 겹침 순서 80)에 상단 바까지 덮는다. 위에 바 하나 — 그림 이름 · `－ 100% ＋` · 닫기. 그림은 **원본 SVG를 복제**해 띄우고 본문 쪽은 그대로다
- **열릴 때는 무대 폭에 맞춘다(100% 이하).** 시퀀스 하나가 3천px이라 100%로 열면 가로 스크롤부터 만난다. 확대는 25%씩, 최소 25% 최대 400%. `100%`를 누르면 원래 크기. 스크롤로 움직인다
- 위 바의 이름은 **문서 순서로 그 그림 앞에 있는 마지막 헤딩**(항목이면 항목 ID)이다 — 가장 가까운 조상의 첫 헤딩을 쓰면 앞선 형제의 제목이 잡힌다
- 닫는 길 셋 — 닫기 버튼 · `Esc` · 그림 바깥 클릭
- **SEQ의 자기 확대 바(－/100%/＋)는 그대로 둔다.** 그건 본문 안에서 조금 키우는 것이고, 전체보기는 화면을 통째로 쓰는 것이다
- 쓰는 곳: UI-5 유저용 본문(7.3 → 7.5·7.6) · UI-9 본문(4)의 그림. UI-8 그래프는 자기 전체보기(2.5)가 있다

## 공통 틀

이 절의 첫 html 블록은 뷰가 **이 문서 모든 화면의 iframe 앞에** 넣는다([[SYNC-STD-001]] 2.7). 마크업은 없고 `<style>`만이다 — 상단 바 같은 공통 조각은 UI-5 배치가 이미 품고 있어 마크업을 여기 두면 두 번 나온다. 카드 Z에서 렌더러 안에 있던 클래스 사전을 여기로 옮겼고, 앱 CSS에 우연히 맞아 보이던 클래스도 토큰을 값으로 풀어 옮겼다. 12화면을 디자인 도구로 다시 그리면(카드 AA) 뒤쪽은 줄어든다.

```html
<style>
/* 카드 Z — 렌더러 사전에서 옮김. 이 블록은 이 문서 모든 화면의 iframe 앞에 들어간다 */
body{margin:0;font-family:system-ui,sans-serif;font-size:12.5px;color:#222;background:#f4f4f4}
.lbl{color:#777;font-size:11px}
.topbar{display:flex;align-items:center;gap:12px;padding:8px 12px;background:#e8e8e8;border-bottom:1px solid #bbb}
.grow{flex:1}
.badge{display:inline-block;background:#d33;color:#fff;font-size:10px;padding:0 5px;border-radius:8px}
.btn{padding:3px 8px;border:1px solid #666;background:#fafafa;display:inline-block}
.docbar{display:flex;align-items:center;gap:12px;padding:7px 12px;background:#f0f0f0;border-bottom:1px solid #bbb}
.tabs span{padding:3px 8px;border:1px solid #999;margin-right:-1px}
.tabs span.on{background:#fff;font-weight:600}
.body3{display:grid;grid-template-columns:150px 1fr 220px;gap:10px;padding:10px}
.toc{padding:8px;line-height:1.8;height:fit-content}
.toc .d1{padding-left:12px}
.main{padding:14px 16px;min-height:420px}
.banner{padding:6px 10px;background:#fff3cd;border:1px solid #d9a800;margin-bottom:10px}
.item{padding:5px 8px;margin:10px 0 4px;background:#f7f7f7;border-left:3px solid #666}
.item .id{font:600 11px ui-monospace,monospace;color:#555;margin-right:6px}
.flag{display:inline-block;font-size:10px;padding:0 6px;border:1px solid #d33;color:#d33;margin-left:6px;border-radius:2px}
.ref{color:#1a5fb4;border-bottom:1px dashed #1a5fb4}
.line{position:relative;padding-right:24px;margin:4px 0}
.cbtn{position:absolute;right:0;top:0;width:18px;height:18px;border:1px solid #999;font-size:10px;text-align:center;line-height:16px;color:#777;background:#fff}
.cbtn.has{border-color:#1a5fb4;color:#1a5fb4;font-weight:600}
.diagram{margin:12px 0;padding:10px;background:#fafafa;border:1px solid #ccc;text-align:center}
.diagram .img{height:110px;background:repeating-linear-gradient(45deg,#eee 0 10px,#f8f8f8 10px 20px);border:1px solid #ddd;display:flex;align-items:center;justify-content:center;color:#888}
.diagram .acts{margin-top:6px;text-align:right}
.nav{display:flex;justify-content:space-between;margin-top:20px;padding-top:10px;border-top:1px solid #ddd}
.panel{height:fit-content}
.ptabs{display:flex;border-bottom:1px solid #999}
.ptabs span{flex:1;text-align:center;padding:6px;border-right:1px solid #999}
.ptabs span:last-child{border-right:none}
.ptabs span.on{background:#fff;font-weight:600}
.pbody{padding:10px}
.pbody h4{margin:8px 0 4px;font-size:11px;color:#666}
.pbody ul{margin:0 0 8px;padding-left:14px;line-height:1.7}
h2{font-size:15px;margin:6px 0 10px}
.body2{display:grid;grid-template-columns:1fr 240px;gap:10px;padding:10px}
.editor{display:grid;grid-template-columns:28px 1fr;min-height:300px;background:#fff}
.gutter{display:flex;flex-direction:column;background:#f0f0f0;color:#999;font:11px/1.55 ui-monospace,monospace;text-align:right;padding:8px 4px}
.gutter .err{color:#d33;font-weight:700}.gutter .del{color:#c60;font-weight:700}
.code{margin:0;padding:8px;font:11.5px/1.55 ui-monospace,monospace;white-space:pre-wrap}
.errline{background:#ffe0e0;display:block}.delline{background:#fff0e0;display:block;text-decoration:line-through}
.chk{margin:0 0 8px;padding-left:16px;line-height:1.6}
.chk .bad{color:#b00}.chk .ok{color:#3a7}.chk .warn{color:#a60}
.btn.sm{font-size:10px;padding:1px 6px;margin-top:3px}
.dialog{margin:12px;border:2px solid #444;background:#fff;box-shadow:0 4px 18px rgba(0,0,0,.18)}
.dhead{padding:7px 12px;background:#444;color:#fff;font-weight:600}
.dbody{padding:12px}
.diffbox{margin:8px 0;padding:8px;background:#fafafa;border:1px solid #ddd;font:11px/1.6 ui-monospace,monospace}
.dl{color:#b00}.dl.add{color:#080}
.dacts{text-align:right;margin-top:8px}
.rawwrap{margin:10px;background:#fff}
.phead{display:flex;align-items:center;gap:14px;padding:10px 12px;background:#f0f0f0;border-bottom:1px solid #bbb}
.stats{display:flex;gap:8px;padding:8px 12px}
.stat{padding:5px 10px;border:1px solid #999;background:#fff}
.stat b{font-size:14px;margin-right:4px}
table.stages{border-collapse:collapse;width:100%;background:#fff;font-size:12px}
table.stages td{padding:5px 8px;border-bottom:1px solid #e5e5e5;vertical-align:middle}
table.stages tr.stg td{background:#f7f7f7;font-weight:600}
table.stages tr.doc td{padding-left:14px;font-weight:400;color:#333}
table.stages td.no{width:24px;color:#999;text-align:right}
.st{display:inline-block;padding:1px 7px;border-radius:2px;font-size:10.5px;font-weight:600}
.st.ok{background:#d6f0d6;color:#1a6}.st.rv{background:#fff0b3;color:#960}.st.dr{background:#e8e8e8;color:#666}.st.na{background:#fff;color:#bbb;border:1px dashed #ccc}
.gate{font-size:10px;color:#c60;border:1px solid #c60;padding:0 5px;margin-left:4px}
.cm{font-size:10px;color:#1a5fb4;border:1px solid #1a5fb4;padding:0 5px;margin-left:4px}
.err{font-size:10px;color:#b00;border:1px solid #b00;padding:0 5px;margin-left:4px}
.recent{margin:0;padding-left:14px;line-height:1.5}
.recent li{margin-bottom:6px}
.todo{padding:10px 12px}
.grp{margin-bottom:12px;background:#fff}
.grp.dim{opacity:.6}
.grp h4{margin:0;padding:6px 10px;background:#f0f0f0;font-size:12px;border-bottom:1px solid #ccc}
.cnt{display:inline-block;background:#666;color:#fff;font-size:10px;padding:0 6px;border-radius:8px;margin-left:6px}
.row{display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid #eee;font-size:12px}
.row .k{font:600 11px ui-monospace,monospace;color:#444}
.age{font-size:11px;color:#c60;font-weight:600;white-space:nowrap}
.empty{padding:24px;text-align:center;color:#999;border:1px dashed #ccc;background:#fafafa}
.stack{padding:10px 12px;display:flex;flex-direction:column;gap:10px}
.cause,.mine{background:#fff}
.sech{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#f0f0f0;border-bottom:1px solid #ccc;font-size:12px}
.mybody{padding:10px 12px;font-size:12px;line-height:1.6}
.mybody p{margin:4px 0}
.acts{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#f7f7f7;border:1px solid #ccc}
.dialog.wide{margin:18px 30px}
.dhead{display:flex;align-items:center;gap:10px}
.dhead .lbl{color:#ddd}
.x{cursor:pointer;padding:0 6px}
.propacts{display:flex;align-items:flex-end;gap:10px;margin-top:12px}
.skipbox{display:flex;flex-direction:column;gap:5px}
.inp{border:1px solid #999;padding:4px 8px;font-size:11px;width:260px;background:#fff}
.body2.hist{grid-template-columns:1fr 1fr}
table.vers{border-collapse:collapse;width:100%;background:#fff;font-size:11.5px}
table.vers th{text-align:left;padding:5px 8px;background:#f0f0f0;border-bottom:1px solid #ccc;font-weight:600}
table.vers td{padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}
table.vers tr.cur td{background:#fffbe6}
.diffpane{background:#fff}
.hint{font-size:10px;color:#1a5fb4;border:1px solid #1a5fb4;padding:0 5px;margin-left:6px}
table.grid{border-collapse:collapse;width:calc(100% - 24px);margin:10px 12px;background:#fff;font-size:11.5px}
table.grid th{padding:6px 5px;background:#f0f0f0;border-bottom:1px solid #ccc;font-weight:600;font-size:10.5px;text-align:center}
table.grid th:nth-child(2){text-align:left}
table.grid td{padding:7px 5px;border-bottom:1px solid #eee;text-align:center;vertical-align:middle}
table.grid td:nth-child(2){text-align:left}
.cell{display:inline-block;width:26px;height:22px;line-height:22px;border-radius:2px;font-size:10.5px;font-weight:600;position:relative}
.cell.ok{background:#d6f0d6;color:#1a6}.cell.rv{background:#fff0b3;color:#960}.cell.dr{background:#e8e8e8;color:#666}.cell.na{background:#fff;border:1px dashed #ddd}
.cell i{position:absolute;top:-6px;right:-6px;font-style:normal;font-size:9px;color:#c60}
.warn{color:#c60;font-size:14px}
.login{max-width:360px;margin:60px auto;padding:30px;background:#fff;text-align:center}
.logo{font-size:20px;margin-bottom:10px}
.btn.big{display:block;padding:10px;margin:14px 0;font-size:13px}
.form{padding:12px}
.form label{display:block;font-size:11px;font-weight:600;margin:10px 0 3px}
.inp.wide{width:100%}
.ferr{color:#b00;font-size:11px;margin-top:3px}
.facts{margin-top:14px;text-align:right}
.banner.err{background:#ffe0e0;border-color:#b00;margin:0 12px}
.banner.warn{background:#e8f0ff;border-color:#3a5ba0}
.btn.on{background:#fff;font-weight:600}
.graph{display:flex;gap:18px;padding:14px 12px;background:#fff;margin:10px 12px;min-height:200px;position:relative}
.col{display:flex;flex-direction:column;gap:6px;min-width:120px}
.colh{font-size:10px;font-weight:700;color:#888;text-align:center;border-bottom:1px solid #ddd;padding-bottom:3px}
.node{font:10.5px ui-monospace,monospace;padding:4px 6px;border:1.5px solid #3a5ba0;border-radius:12px;background:#eef2fa;text-align:center}
.node.sel{background:#fff6d9;border-color:#c9a800}
.node.iso{background:#fff;border-style:dashed;border-color:#999;color:#777}
.edges{position:absolute;bottom:6px;left:12px}
.legend{padding:0 12px 10px;display:flex;gap:14px}
.steps{display:flex;gap:3px}
.stp{font-size:10px;padding:2px 6px;border:1px solid #bbb;background:#fff}
.stp.done{background:#d6f0d6;border-color:#8c8}.stp.cur{background:#fff0b3;border-color:#c9a800;font-weight:700}.stp.na{color:#bbb;border-style:dashed}
.readbody{padding:10px 12px}
.row.dimrow{opacity:.5}
.tokbox{font:12px ui-monospace,monospace;padding:8px;background:#f4f4f4;border:1px solid #ccc;margin:8px 0}
.mono{font-family:ui-monospace,monospace;font-size:11px}
table.uptbl{border-collapse:collapse;width:100%;font-size:11.5px;margin:8px 0}
table.uptbl th{text-align:left;padding:4px 6px;background:#f0f0f0;border-bottom:1px solid #ccc}
table.uptbl td{padding:5px 6px;border-bottom:1px solid #eee}
.rawbar{display:flex;align-items:center;gap:10px;padding:6px 10px;background:#f0f0f0;border-bottom:1px solid #bbb}

/* 카드 Z — 앱 styles.css에 우연히 맞아 보이던 클래스. 토큰은 값으로 풀었다. 12화면을 디자인 도구로 다시 그리면(카드 AA) 줄어든다 */
.btn.solid{background:#17181c;border-color:#17181c;color:#fff;font-weight:500;padding:7px 13px}
.btn.solid:hover{background:#000}
.btn.sm.solid{padding:6px 12px;font-size:13px}
.dialog.narrow{width:min(560px,92vw)}
.dfoot{flex:none;display:flex;align-items:center;gap:10px;padding:12px 18px;
  border-top:1px solid #e2e0da;background:#fbfaf8;font-size:13px;color:#46443f}
.login .cap{margin:0;color:#6b6862;font-size:12.5px}
.heat{background:#ffffff;border:1px solid #e2e0da;border-radius:8px;overflow:hidden}
.hrow{display:grid;grid-template-columns:20px 196px repeat(11,minmax(0,1fr));gap:4px;
  align-items:center;padding:11px 14px;border-bottom:1px solid #f0eeea}
.hrow:last-child{border-bottom:none}
.hrow.head{padding:7px 14px 6px;background:#fbfaf8;
  border-bottom:1px solid #e2e0da;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:11px;
  color:#46443f;letter-spacing:.2px;text-align:center}
.hrow .warn{text-align:center;font-size:13px}
.pname{display:flex;flex-direction:column;gap:0;min-width:0;cursor:pointer;font-size:15.5px;line-height:1.15}
.pname .mono{font-size:13px;font-weight:600}
.pname .sub{display:flex;align-items:center;gap:6px;font-size:12.5px;
  color:#46443f;white-space:nowrap;line-height:1.2}
.pname .sub .work{color:#b8342a;font-weight:600}
.pname .sub .mid{color:#cfccc4}
.cell.na{background:#ffffff;border-color:#e2e0da}
.cell.missing{border-width:1.5px;border-color:#b8342a}
.legend i.sw{width:11px;height:11px;border:1px solid transparent;border-radius:2px;background:#9c9891}
.legend i.sw.ok{background:#2f7d5b}
.legend i.sw.na{background:#ffffff;border-color:#e2e0da}
.willcommit{margin-top:18px;padding:10px 12px;
  background:#fbfaf8;border:1px solid #e2e0da;border-radius:8px;
  font-size:12.5px}
.willcommit .mono{display:block;color:#46443f;font-size:12px;margin-top:3px}
.setdlg{width:min(620px,92vw)}
.setdlg .dbody{background:#fbfaf8;padding:16px 18px}
.card{border:1px solid #e2e0da;border-radius:8px;background:#ffffff;
  padding:16px;margin-bottom:14px}
.card:last-child{margin-bottom:0}
.cardh{display:flex;align-items:center;gap:8px;margin-bottom:9px;font-size:15px}
.cardh b{font-weight:600}
.card>.lbl{margin:0 0 4px;line-height:1.7;font-size:14px}
.row .two{display:flex;flex-direction:column;gap:1px;min-width:0}
.row .two .lbl{font-size:12px}
.snippet{margin:8px 0 0;padding:10px 12px;background:#f3f1ec;
  border-radius:6px;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12px;
  color:#46443f;overflow-x:auto;white-space:pre}
.admin{margin-top:10px;border-top:1px solid #f0eeea;padding-top:10px}
.adminh{margin-bottom:8px}
.adminbody table.vers{width:100%;border-collapse:collapse;font-size:12.5px;background:#ffffff}
.adminbody table.vers th{background:#fbfaf8;color:#46443f;font-weight:600}
.adminbody table.vers td:last-child{white-space:nowrap}
.adminbody table.vers td:nth-child(2){max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.adminbody table.vers th,.adminbody table.vers td{padding:6px 8px;
  border-bottom:1px solid #f0eeea;text-align:left;vertical-align:middle}
.adminbody table.vers tr:last-child td{border-bottom:none}
.tokbox .tok{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:13.5px;background:#ffffff;
  border:1px solid #e2e0da;border-radius:5px;padding:8px 10px;
  margin:0 0 8px;word-break:break-all}
.phead .repo{display:inline-block;margin-top:3px;font-size:13px;color:#46443f}
.stgh{display:flex;align-items:center;gap:8px;padding:9px 13px;
  border-bottom:1px solid #e2e0da;background:#fbfaf8;font-size:14px}
.stgh b{font-weight:600}
.stgh .sw{width:14px;height:14px;border-radius:2px;border:1px solid transparent;background:#9c9891}
.stgh .sw.ok{background:#2f7d5b}
.stgh .sw.na{background:#ffffff;border-color:#e2e0da}
.stg .nm{font-size:14.5px;font-weight:500}
.stg .caret{width:10px;text-align:center;font-size:11.5px;color:#46443f}
.doc .dot{width:8px;height:8px;border-radius:50%;flex:none;background:#9c9891}
.doc .dot.ok{background:#2f7d5b}
.st.dr,.st-draft{background:#9c9891;color:#17181c}
.st.na{background:none;color:#a8a49c}
.miss{font-size:12px;font-weight:600;color:#b8342a;
  border:1px solid #b8342a;border-radius:9px;padding:1px 7px}
.rc{padding:7px 0;border-bottom:1px solid #f4f2ee;cursor:pointer}
.rc>div:first-child{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap}
.rc .mono{font-size:12.5px;font-weight:500}
.rc .msg{margin-top:2px;color:#1f2024}
.rc .lbl{margin-top:1px}
.sync{margin-top:11px;padding-top:10px;border-top:1px solid #f0eeea;line-height:1.7}
.sync .behind{color:#b8342a;font-weight:600}
.docbar .crumb{color:#46443f;text-decoration:none;cursor:pointer;font-size:13.5px}
.docbar .crumb:hover{color:#17181c}
.docbar .crumb.mono{font-size:12.5px}
.docbar .sep{color:#6b6862;font-size:12px}
.docbar .ver{color:#46443f;font-size:12.5px;text-decoration:none;
  border-bottom:1px dashed #cfccc4;cursor:pointer}
.handle{position:relative;width:1px;background:#e2e0da;cursor:col-resize}
.handle::after{content:"";position:absolute;top:0;bottom:0;left:-4px;width:9px}
.handle:hover{background:#b8342a}
.toc,.vlist{background:#fbfaf8;padding:13px 12px;
  overflow:auto;min-height:0}
.marked{margin-top:14px;padding-top:10px;border-top:1px solid #e2e0da}
.marked>div{display:flex;align-items:center;gap:5px;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  font-size:12px;cursor:pointer;padding:2px 0}
.marked>div .lbl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.marked .lbl{font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif}
.marked .dot{flex:none;width:6px;height:6px;border-radius:50%}
.marked .dot-miss{background:#b8342a}
.mainwrap,.body3>.main{overflow:auto;scrollbar-gutter:stable;padding:20px 26px 60px;
  background:#ffffff;min-width:0;min-height:0}
.mainwrap>*,.body3>.main>*{max-width:min(1440px,100%);margin-left:auto;margin-right:auto}
.dochead{margin-bottom:22px}
.kicker{font-size:12px;color:#46443f;letter-spacing:.3px}
.dochead h1{display:block;margin:4px 0 0;font-size:27px;font-weight:600;letter-spacing:-.4px}
.lead{margin:6px 0 0;font-size:15px;color:#46443f;line-height:1.65;text-wrap:pretty}
.tabs .btn,.tabs .radios{border-bottom:none;padding-bottom:0}
.body3 .panel,.vimpact{background:#fbfaf8;border:none;border-left:1px solid #e2e0da;
  border-radius:0;box-shadow:none;padding:0;min-height:0}
.vimpact{padding:13px 12px;font-size:13px;overflow:auto}
.selitem{display:flex;align-items:center;gap:6px;margin-bottom:12px;font-size:14px;font-weight:500}
.rcard{display:block;border:1px solid #e2e0da;background:#ffffff;border-radius:5px;
  padding:6px 8px;margin-bottom:5px;text-decoration:none;color:inherit;cursor:pointer}
.rcard b{font-size:12px;font-weight:500}
.rcard .lbl{margin:1px 0 0}
.rcard.missing{border-style:dashed;color:#a8a49c}
.docnav{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding-top:14px;margin-top:26px;border-top:1px solid #e2e0da}
.docnav .grow{flex:1}
.radios{display:inline-flex;align-items:center;gap:2px;border:1px solid #e2e0da;
  border-radius:6px;padding:2px;background:#fbfaf8}
.radio{display:flex;align-items:center;gap:6px;padding:4px 10px;
  border-radius:4px;cursor:pointer;font-size:13px;color:#46443f}
.radio::before{content:"";width:11px;height:11px;flex:none;border-radius:50%;
  border:1px solid #cfccc4;background:#ffffff;box-shadow:inset 0 0 0 2.5px #ffffff}
.radio.on{background:#ffffff;color:#17181c;font-weight:500}
.radio.on::before{border-color:#17181c;box-shadow:inset 0 0 0 2.5px #ffffff,inset 0 0 0 5px #17181c}
.editor pre.mdsrc{margin:0;padding:12px 14px;background:transparent;
  color:#1f2024;font:inherit;white-space:pre-wrap;border-radius:0}
li.ref.missing{color:#a8a49c}
.vcard{border:1px solid #e2e0da;background:#ffffff;border-radius:6px;
  padding:7px 8px;margin-bottom:5px;cursor:pointer;font-size:12.5px}
.vcard:hover{border-color:#cfccc4}
.vcard>div{display:flex;align-items:center;gap:6px}
.vcard .mono{font-size:13px}
.vcard .msg{display:block;margin-top:3px;color:#1f2024;line-height:1.45}
.vcard .by{margin-top:4px;align-items:flex-start}
.vcard .msg,.vcard .by .lbl{word-break:keep-all}
.vcard .by .lbl{min-width:0;flex:1;line-height:1.4}
.vcard .btn.sm{flex:none;white-space:nowrap;padding:1px 6px;font-size:11.5px}
.vcard.sel{border:1.5px solid #17181c;background:#fdf8ec}
.ab{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:11px;font-weight:700;background:#17181c;
  color:#fff;border-radius:3px;padding:0 5px}
.btn.danger,.btn.sm.danger{border-color:#b8342a;color:#b8342a;font-weight:500}
.btn.danger:disabled{opacity:.45;cursor:not-allowed}
.btn.sm.danger:hover{background:#fdf1ef}
.vlist .hint{margin-top:8px;padding-top:9px;border-top:1px solid #e2e0da}
.drange{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.drange .mono{font-size:19px;font-weight:600}
.dgroup{border:1px solid #e2e0da;border-radius:7px;overflow:hidden;margin-bottom:10px}
.dhead2{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:9px 12px;
  background:#fbfaf8;border-bottom:1px solid #e2e0da;font-size:14px}
.dhead2 b{font-weight:600}
.footnote{color:#46443f;font-size:12.5px;line-height:1.6;
  margin-top:22px;padding-top:12px;border-top:1px solid #e2e0da}
.dgroup .hint{border:1px solid #cfccc4;background:#ffffff;border-radius:9px;
  padding:1px 8px;cursor:pointer;white-space:nowrap}
.icard{border:1px solid #e2e0da;background:#ffffff;border-radius:6px;
  padding:7px 9px;margin-bottom:6px;cursor:pointer}
.icard>div{display:flex;align-items:center}
.icard .n{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-weight:600;color:#46443f}
.dl .mk{width:26px;flex:none;text-align:center;font-weight:600}
.dl.add{background:#eef6f0}
.dl.add .mk,.dl.add>span:last-child{color:#2f7d5b}
.dl.del{background:#fdf1ef}
.dl.del .mk,.dl.del>span:last-child{color:#b8342a}
.dlead{margin:0 0 14px;color:#1f2024;line-height:1.65;text-wrap:pretty}
.crumbs{display:flex;align-items:center;gap:8px;margin-bottom:3px;font-size:13.5px}
.crumbs a{color:#46443f;text-decoration:none}
.crumbs a:hover{color:#17181c}
.crumbs>span:last-child{color:#6b6862}
.crumbs .sep{color:#6b6862;font-size:12px}
.gcard{border:1px solid #e2e0da;border-radius:8px;background:#ffffff;overflow:hidden}
.gcard.full{position:fixed;inset:0;z-index:80;border:none;border-radius:0;
  display:flex;flex-direction:column;background:#ffffff}
.gbar{display:flex;align-items:center;gap:8px;padding:10px 14px;
  border-bottom:1px solid #e2e0da;background:#fbfaf8;font-size:13px}
.gbar .btn.on{background:#17181c;color:#fff;border-color:#17181c}
.gbar .sep{width:1px;height:16px;background:#cfccc4;margin:0 4px}
.gbar .lbl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gcard .canvas{position:relative;overflow:auto;height:calc(100vh - 50px - 190px);background:#ffffff}
.gcard.full .canvas{flex:1;height:auto}
.dfull{position:fixed;inset:0;z-index:80;display:flex;flex-direction:column;background:#ffffff}
.dfull .gbar b{font-weight:600}
.dfull .zv{min-width:44px;text-align:center;font-size:12px}
.dfull .stage{flex:1;min-height:0;overflow:auto;padding:22px;background:#fbfaf8}
.dfull .pic{margin:0 auto;background:#ffffff;border:1px solid #e2e0da;border-radius:6px}
.dfull .pic svg{display:block;width:100%!important;height:100%!important;max-width:none!important}
.nlabel{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.edges .e{fill:none;stroke:#8f8b83;stroke-width:1.2;marker-end:url(#ah)}
.edges .e.back{stroke:#b8860b;stroke-width:1.4;stroke-dasharray:5 3;marker-end:url(#ahr)}
.edges .e.gone{stroke:#b8342a;stroke-width:1.6;stroke-dasharray:3 3;marker-end:url(#ahb)}
.edges .e.dim{opacity:.1}
.glegend{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;
  padding:8px 14px;border-top:1px solid #f0eeea;
  background:#fbfaf8;font-size:12.5px}
.glegend span{display:inline-flex;align-items:center;gap:5px}
.glegend .back{color:#8a6410}
.glegend .gone{color:#b8342a}
.glegend .grow{flex:1}
.glegend svg.sw{width:22px;height:8px;vertical-align:middle}
.glegend svg.sw .e{fill:none;stroke:#8f8b83;stroke-width:1}
.glegend svg.sw .e.back{stroke:#b8860b;stroke-dasharray:4 3}
.glegend svg.sw .e.gone{stroke:#b8342a;stroke-dasharray:3 3}
.chain{margin-top:12px;border:1px solid #e2e0da;border-radius:6px;overflow:hidden}
.crow{display:grid;grid-template-columns:120px minmax(0,1fr);gap:10px;
  padding:8px 12px;border-bottom:1px solid #f0eeea}
.crow:last-child{border-bottom:none}
.crow.cur{background:#fdf8ec}
.crow.empty{background:#fbfaf8}
.crow.empty .cstage,.crow.empty .cchips{color:#a8a49c}
.cstage{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#46443f;line-height:1.6}
.crow.cur .cstage,.crow.cur .cstage .lbl{color:#8a6410;font-weight:600}
.cstage .lbl{font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;font-size:12.5px}
.cchips{display:flex;flex-wrap:wrap;gap:5px;align-items:flex-start;font-size:12.5px}
.chip{display:inline-flex;align-items:center;gap:5px;max-width:320px;
  padding:2px 8px;border:1px solid #e2e0da;border-radius:5px;
  background:#ffffff;font-size:12.5px;cursor:pointer;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chip:hover{border-color:#cfccc4}
.chip .dot{flex:none;width:6px;height:6px;border-radius:50%;background:#9c9891}
.chip .dot-approved{background:#2f7d5b}
.chip.me{background:#ffffff;border:1.5px solid #17181c;font-weight:600;cursor:default}
.chip.gone{border-style:dashed;color:#a8a49c;cursor:default}
.steprail{display:flex;align-items:center;gap:9px;flex:none;
  padding:11px 18px;background:#ffffff;
  border-bottom:1px solid #e2e0da;overflow-x:auto;overflow-y:hidden}
.steprail .back{flex:none;font-size:13.5px;color:#46443f;text-decoration:none;white-space:nowrap}
.steprail .back:hover{color:#17181c}
.stp.na{opacity:.45;cursor:default}
.dot{width:6px;height:6px;border-radius:50%;background:#9c9891}
.dot-approved{background:#2f7d5b}
.dot-none{background:none;border:1px solid #cfccc4}
.dot-miss{background:#b8342a}
.stp.cur .dot-none{border-color:rgba(255,255,255,.5)}
.readbody .dochead{margin:0 0 18px}
.pill{display:inline-block;padding:1px 8px;border-radius:9px;
  font-size:12px;font-weight:600;line-height:1.55;white-space:nowrap;
  background:#9c9891;color:#17181c}
.pill-approved{background:#2f7d5b;color:#ffffff}
.idbadge{display:inline-block;padding:0 5px;border-radius:3px;
  background:#d99b1e;color:#17181c;
  font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;font-weight:600}
.howto .dlead{margin:0 0 16px;font-size:14px;color:#46443f;line-height:1.7;text-wrap:pretty}
.sectitle{margin:22px 0 8px;font-size:14px;font-weight:600}
.howto tr.hd th{background:none;color:#6b6862;font-size:12.5px;font-weight:400;border-bottom:1px solid #f0eeea}
.howto td.no,.howto tr.hd th:first-child{width:26px;text-align:center;color:#6b6862;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12px}
.howto td .sub{margin-top:5px;font-size:13px;color:#46443f;line-height:1.6}
.howto td .sub .cnt{display:inline-block;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12px;font-weight:600;
  color:#17181c;background:#f3f1ec;border-radius:3px;padding:0 6px;margin-right:5px}
.howto td .sub .tag{display:inline-block;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#6b6862;line-height:1.5;
  border:1px solid #cfccc4;border-radius:3px;padding:0 5px;margin-left:6px;vertical-align:1px}
.howto td .sub ul.docs{list-style:none;margin:4px 0 0;padding:0;display:flex;flex-direction:column;gap:2px}
.howto td .sub ul.docs b{color:#17181c;font-weight:500}
.howto td.where{color:#46443f;white-space:nowrap;width:74px}
.howto td.ids{width:150px;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#46443f}
.howto tr.std td{color:#6b6862}
.howto figure+.snippet{margin-top:12px}
.howto .note{margin:0;padding:10px 12px;border-radius:6px;
  background:#fdf8ec;color:#8a6410;font-size:13px}
.qa{display:flex;flex-direction:column;gap:9px;margin:9px 0}
.qa .turn{display:flex;flex-direction:column;gap:4px}
.qa .q{align-self:flex-end;max-width:92%;padding:5px 9px;border-radius:5px;
  background:#f3f1ec;color:#17181c;font-size:14px;white-space:pre-wrap}
.qa .a{padding:5px 9px;border:1px solid #e2e0da;border-radius:5px;
  background:#ffffff;color:#1f2024;font-size:14px;line-height:1.6;white-space:pre-wrap}
.qa .a.wait{color:#6b6862;border-style:dashed}
.qa .a.fail{color:#b8342a;background:#fdf1ef;border-color:#fdf1ef}
.qa .qsrc{font-size:12.5px;color:#6b6862;font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace}
.qa .qprog{display:flex;flex-direction:column;gap:3px;padding:4px 9px;border-left:2px solid #e2e0da;
  font-size:13px;color:#46443f}
.qa .qprog .read{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;color:#6b6862}
.qa .qprog.done{font-size:12.5px;color:#6b6862}
.qa .qsrc a{color:#46443f}
</style>
```

---

## UI-5 문서 뷰

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-5]] |
| 경로 | `/p/{프로젝트코드}/d/{문서ID}` · 원본 탭은 `?tab=raw` |
| 진입 | UI-4 문서 클릭 · UI-4 수치 다이얼로그(6) 행 · UI-8 노드 클릭 · 다른 문서의 참조 링크 |
| 유스케이스 | [[SYNC-UC-001#UC-H2]] [[SYNC-UC-001#UC-H3]] [[SYNC-UC-001#UC-H8]] [[SYNC-UC-001#UC-H19]] |

### 배치

```html
<div class="topbar"><!-- 공통 틀. SYNC-UI-001 4장 -->
  <strong>싱크독</strong>
  <span class="grow"></span>
  <span class="btn">사용 방법</span>
  <span class="btn">설정</span>
  <span class="btn">로그아웃</span>
</div>

<div class="docbar" data-el="1"><!-- 브레드크럼. 어디서 들어왔든 지금 자리를 말한다 -->
  <span class="crumb"><b class="mono">[SYNC]</b> 싱크독</span><span class="sep">›</span>
  <span class="crumb mono">2 PRD</span><span class="sep">›</span>
  <b class="mono">SYNC-PRD-001</b>
  <span class="pill pill-approved" data-el="1.1">완료</span>
  <span class="ver mono" data-el="1.2">v7</span>
  <span class="grow"></span>
  <span class="btn" data-el="3">초안으로</span><!-- 토글 하나. 초안이면 「완료로」 -->
  <span class="btn danger" data-el="12">휴지통에 넣기</span><!-- 휴지통에 있는 문서면 이 자리에 없다(4b 배너가 대신) -->
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
      <div><span class="dot dot-miss"></span> R2 <span class="lbl">끊어진 참조 1</span></div>
    </div>
  </nav>
  <div class="handle" data-el="6.2"></div>

  <div class="mainwrap"><!-- 안쪽 max-width는 세 탭이 같다 -->
    <div class="tabs" data-el="2"><!-- 본문 폭 안, 밑줄로 구분. 원본일 때만 오른쪽에 10.3·10.4·10.2 -->
      <span class="on" data-el="2.1">유저용</span><span data-el="2.2">원본</span><span data-el="2.3">이력</span>
    </div>
    <div class="banner" data-el="4">⚠ 규약 오류: frontmatter.status 누락 (커밋 a1b2c3 · 김민준)</div>
    <div class="banner warn" data-el="4a">미완성: 필수 절 「성공지표」 없음 · 완료 불가</div>

    <div class="dochead"><!-- 킥커·제목·리드. 본문(7)은 innerHTML로 갈아 끼워서 형제로 둔다 -->
      <div class="kicker mono">[SYNC] 싱크독 · 2단계 PRD</div>
      <h1>PRD — 싱크독</h1>
      <p class="lead">바이브코딩 시대에 개발자가 PM 없이 11단계 명세 체인을 쓰고, 에이전트가 그 명세를 따르게 하는 플랫폼.</p>
    </div>

    <article class="main" data-el="7">
      <h2>3. 요구사항</h2>
      <div class="item" data-el="7.1"><span class="id">#R1</span>에이전트용 원본과 사람용 뷰</div>
      <p class="line">명세는 규약이 있는 Markdown으로 작성한다. 근거: <span class="ref" data-el="7.2">[[SYNC-RFQ-001#Q03]]</span></p>
      <p class="line">사람용 뷰는 원본에서 파생 생성한다.</p>
      <div class="item"><span class="id">#R2</span>ID 기반 상호참조 <span class="miss">끊어진 참조 1</span></div>
      <p class="line">본문에서 <span class="ref missing">[[SYNC-DOM-001#참조]]</span>로 참조하면 관계가 추출된다.</p>
      <div class="diagram" data-el="7.3"><span class="btn sm" data-el="7.5">전체보기</span><div class="img">mermaid 렌더링 결과 (브라우저)</div></div>
      <!-- 7.5를 누르면 화면 전체에 그림(7.6, 공통 1.7). 위 바에 이름 · －100%＋ · 닫기 -->
      <div class="dfull" data-el="7.6"><div class="gbar"><b>SEQ-1</b> <span class="lbl">전체보기</span><span class="grow"></span><span class="btn sm">－</span><span class="mono">100%</span><span class="btn sm">＋</span><span class="btn sm">100%</span><span class="btn sm">닫기</span></div><div class="stage"><div class="pic">원본 SVG 복제</div></div></div>
    </article>

    <div class="docnav" data-el="9"><!-- 본문 열 안, 본문과 같은 폭 -->
      <span class="btn">← SYNC-RFQ-001</span>
      <span class="btn">SYNC-SCN-001 →</span>
    </div>
  </div>

  <div class="handle" data-el="8.3"></div>
  <aside class="panel" data-el="8">
    <div class="ptabs"><span class="on" data-el="8.1">참조</span><span data-el="8.4">질문</span></div>
    <div class="pbody">
      <div class="lbl">선택</div>
      <div class="selitem"><span class="idbadge">R1</span> 에이전트용 원본과 사람용 뷰</div>
      <div class="lbl">상위 참조 (근거)</div>
      <div class="rcard"><b class="mono">SYNC-RFQ-001#Q03</b><div class="lbl">명세를 어디에 어떤 형식으로 두나</div></div>
      <div class="lbl">하위 참조 (파생) 2</div>
      <div class="rcard"><b class="mono">SYNC-UC-001#UC-A6</b><div class="lbl">명세를 작성·수정한다</div></div>
      <div class="rcard"><b class="mono">SYNC-UC-001#UC-H2</b><div class="lbl">문서를 읽는다</div></div>
      <!-- 가리키는 곳이 없는 참조(is_missing)는 회색 카드 + 경고 아이콘. 상위 쪽에 뜬다 -->
      <div class="rcard missing"><b class="mono">SYNC-DOM-001#참조</b> <span class="miss">가리키는 곳 없음</span><div class="lbl">항목이 삭제됐거나 아직 안 쓰였다</div></div>
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
    <pre class="mdsrc">---
doc_id: SYNC-PRD-001
type: PRD
status: approved
---
#### R1 에이전트용 원본과 사람용 뷰
명세는 규약이 있는 Markdown으로 작성한다. 근거: [[SYNC-RFQ-001#Q03]]
사람용 뷰는 원본에서 파생 생성한다.</pre>
  </div>
</div>

<!-- 문서 삭제 확인 (12). 걸리는 것이 있으면 13.2가 보이고 13.3이 막힌다 -->
<div class="dialog narrow" data-el="13">
  <div class="dhead">휴지통에 넣기 — SYNC-PRD-001</div>
  <div class="dbody">
    <p data-el="13.1"><b>제품 요구사항 — 싱크독</b> · 버전 7개 · 파일이 저장소에서 지워집니다. 행과 이력은 남아 <b>되살릴 수 있습니다.</b></p>
    <div class="banner warn" data-el="13.2">넣으면 끊어지는 것<br>
      · 들어오는 참조 3 — <b>SYNC-UC-001#UC-A6</b> · <b>SYNC-UC-001#UC-A1</b> · <b>SYNC-API-002</b> → 그 참조가 <b>끊어진 참조</b>가 됩니다</div>
    <div class="dacts"><span class="btn" data-el="13.4">닫기</span> <span class="btn danger" data-el="13.3">휴지통에 넣기</span></div>
  </div>
</div>

<!-- 질문 탭(8.4)을 눌렀을 때의 패널 본문. 참조 탭 본문과 자리를 바꿔 든다 -->
<aside class="panel">
  <div class="ptabs"><span data-el="8.1">참조</span><span class="on">질문</span></div>
  <div class="pbody">
    <div class="lbl" data-el="8.5">R1 에이전트용 원본과 사람용 뷰 · 이 항목을 보며 묻습니다</div><!-- 항목이 없으면 「문서 전체 · SYNC-PRD-001에 대해 묻습니다」 -->
    <div class="qa" data-el="8.7">
      <div class="q">원본과 뷰를 왜 나눴나요?</div>
      <div class="qprog" data-el="8.9"><!-- 진행 줄. 답이 오기 전엔 또렷이, 온 뒤엔 작고 흐리게 남는다 -->
        <div>R1 본문을 읽는다 — 왜 나눴는지가 거기 적혀 있을 것이다</div>
        <div class="dim">읽음 · SYNC-PRD-001#R1</div>
        <div>근거 Q1을 읽는다 — 상위가 무엇을 요구했는지</div>
        <div class="dim">읽음 · SYNC-RFQ-001#Q1</div>
      </div>
      <div class="a">에이전트가 읽을 것을 전제로 규약이 있는 MD를 원본으로 두고, 사람용은 거기서 파생 생성합니다. 근거는 <b>SYNC-RFQ-001#Q1</b>이고 이 항목의 상위입니다.</div>
      <div class="qsrc">본 것: SYNC-PRD-001#R1 · SYNC-RFQ-001#Q1</div>
    </div>
    <textarea data-el="8.6" placeholder="이 문서에 대해 묻습니다"></textarea>
  </div>
</aside>

<!-- 휴지통에 있는 문서를 열면 (4b). 상태 토글(3)·삭제(12)는 없다 -->
<div class="banner warn" data-el="4b">휴지통에 있는 문서입니다 — 2026-09-16 박호영 · 파일은 저장소에 없고 되살리면 돌아옵니다 <span class="btn sm" data-el="4b.1">되살리기</span></div>

```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 문서 바 | 영역 | 브레드크럼 `프로젝트 › 단계 › 문서 ID`, 상태(1.1), 버전(1.2). 앞 두 조각은 눌러서 되짚어 올라간다 | — |
| 1.1 | 상태 | 뱃지 | `초안`·`완료`. 색으로 구분 | — |
| 1.2 | 버전 | 텍스트 | 현재 버전 번호 | 이력(UI-7)으로 |
| 2 | 탭 | 탭 | 유저용(기본)·원본·이력. **본문 안 맨 위**, 본문과 같은 폭. 활성 탭만 굵고 아래 2px 잉크선 | — |
| 2.1 | 유저용 | 탭 | 사람용 뷰(7) | 본문 영역을 7로 |
| 2.2 | 원본 | 탭 | 에이전트가 읽는 MD(10) | 본문 영역을 10으로 |
| 2.3 | 이력 | 탭 | | UI-7로 |
| 3 | 상태 토글 | 버튼 | 초안이면 `완료로`, 완료면 `초안으로`. 갈 곳이 하나라 고를 것이 없다 | 전환(UC-H8). 완료로 올릴 때 규약 오류·미완성·끊어진 참조가 있으면 서버가 `status-blocked`로 거절하고 토스트에 이유 — 배너(4·4a)가 이미 말하는 값이다. 다이얼로그 없음 |
| 4 | 규약 오류 배너 | 배너 | 어긴 규약, 커밋, 작성자. 오류 없으면 안 보임. 고치려면 에이전트에게 | — |
| 4b | 휴지통 배너 | 배너 | `trashed_at`이 있으면. 언제·누가 넣었나, 되살리면 돌아온다는 것. 이 배너가 있으면 3·12가 없다 | — |
| 4b.1 | 되살리기 | 버튼 | 배너 안 | `POST /api/docs/{docId}/restore` → 같은 문서 새 버전(UC-H18 5) |
| 4a | 미완성 배너 | 배너 | 미완성 경고(`incomplete_warnings`) **+ 가리키는 곳이 없는 참조**(`missing_refs`). 둘을 이어 붙여 한 배너로. **[[SYNC-STD-001]] 4장 `화면 문구` 열을 쓴다** — `warnings`가 실어 오는 `rule`은 기계가 읽는 ID다. 규약 오류와 색이 다르고, 저장은 됐고 완료만 막힘 | — |
| 6 | 목차 | 목록 | 절 제목과 그 아래 항목. 항목은 한 칸 들여 흐리게. 각 줄은 한 줄로 자른다 | 본문 해당 위치로 스크롤 |
| 6.1 | 표시된 항목 | 목록 | 가리키는 곳이 없는 참조(`is_missing`)를 가진 항목만. 색 점 · 항목 ID · 건수. 하나도 없으면 블록 자체가 안 보인다 | 본문 해당 항목으로 스크롤하고 패널(8)을 연다 |
| 6.2 | 사이드바 경계 | 손잡이 | 좌측 폭을 끈다. 140~400px | — |
| 7 | 유저용 본문 | 영역 | 사람용 뷰로 렌더링된 원본. 목차·본문·패널 3단 | — |
| 7.1 | 항목 헤더 | 행 | 항목 ID, 제목, 끊어진 참조 수(있으면, 경고색) | 패널(8) 참조 탭에 이 항목의 상위·하위 |
| 7.2 | 참조 링크 | 링크 | `[[…]]` | 그 문서의 UI-5로 이동, 해당 항목 위치. 미존재 참조면 이동 안 하고 경고 |
| 7.3 | 다이어그램 | 그림 | mermaid 코드블록을 브라우저가 렌더링. 문법 오류면 원본 코드와 오류 메시지 | — |
| 7.5 | 전체보기 | 버튼 | 그림(7.3)마다 오른쪽 위. 작고 흐리게, 마우스를 올리면 또렷이 | 전체보기 층(7.6) |
| 7.6 | 그림 전체보기 | 층 | 화면 전체. 위 바에 그림 이름 · `－ 100% ＋` · 닫기, 아래에 원본 SVG 복제(공통 1.7) | 닫기·Esc·바깥 클릭 → 닫힘 |
| 8 | 오른쪽 패널 | 영역 | 참조 탭(8.1) / 질문 탭(8.4). 유저용 탭에서만 | — |
| 8.3 | 패널 경계 | 손잡이 | 우측 폭을 끈다. 180~460px | — |
| 8.1 | 참조 탭 | 패널 | 선택 항목의 상위 참조·하위 참조. 가리키는 곳이 없는 참조는 회색 카드에 경고 아이콘(UC-H2 2c) | 참조 클릭 → 7.2와 같음 |
| 8.4 | 질문 탭 | 탭 | 읽다가 묻는다(UC-H19). 모델이 같은 프로젝트를 관계도로 따라 읽는다. **모델 키가 없으면 이 탭이 없다** — `GET /api/me`의 `llm_enabled`로 안다 | 패널을 질문으로 |
| 8.5 | 맥락 줄 | 텍스트 | 지금 무엇을 보며 묻는지. 항목이 있으면 「`X 이름` · 이 항목을 보며 묻습니다」, 없으면 「문서 전체 · `{doc_id}`에 대해 묻습니다」. 항목은 힌트다 | — |
| 8.6 | 질문 입력 | 입력 | **항상 활성**(휴지통 문서 제외). 보내는 동안만 비활성. 보내면 8.7에 쌓인다 | — |
| 8.7 | 대화 | 목록 | 질문·진행 줄(8.9)·답이 차례로. **서버에 저장되지 않는다** — 대화는 프로젝트 단위로 브라우저에만 있다. 답 아래 「본 것」 = 모델이 실제로 읽은 대상, 부른 순서 | 대상 ID → 7.2와 같음(다른 문서면 그 문서로) |
| 8.9 | 진행 줄 | 목록 | 답이 오기 전에 모델이 읽기 전마다 쓰는 한 줄(`note`)과 읽은 대상(`read`)이 **실시간으로 차례로** 쌓인다. 답이 오면 작고 흐리게 남는다 — 무엇을 보고 답했는지의 과정 | — |
| 9 | 단계 이동 | 버튼 2개 | 이전·다음 단계 문서 ID. 없으면 비활성 | 그 문서의 UI-5 |
| 10 | 원본 본문 | 영역 | 원본 MD 그대로. 줄 번호. 3단 틀은 유저용과 같고 본문 열만 바뀐다 | — |
| 10.1 | MD 텍스트 | 읽기 전용 텍스트 | 저장소의 파일 내용 그대로 | 선택·복사만. 편집 불가 |
| 10.2 | 복사 | 버튼 | | 전체 원본을 클립보드로. 에이전트에게 붙여넣는 용도 |
| 10.3 | 원문 | 라디오 | 줄번호 거터와 MD 그대로(기본). 탭 줄(2) 오른쪽에 복사(10.2)와 함께 놓인다 | 본문을 원문으로 |
| 10.4 | 렌더링 | 라디오 | 같은 MD를 파싱해 그린 것. frontmatter는 회색 블록, 절·항목·체크박스·인라인 코드·참조를 구분해 보여준다 | 본문을 렌더링으로 |
| 12 | 휴지통에 넣기 | 버튼 | 상태 토글(3) 오른쪽. `위험` 색. 휴지통에 있는 문서면 없다 | 확인(13) |
| 13 | 휴지통 확인 | 다이얼로그 | 폭 560. 제목·버전 수·되살릴 수 있음(13.1). 끊어질 것(13.2) | — |
| 13.1 | 무엇이 되나 | 텍스트 | 문서 제목 · 버전 수 · 「파일이 저장소에서 지워지고 행과 이력은 남아 되살릴 수 있다」 | — |
| 13.2 | 끊어지는 것 | 배너 | `document-deletion-needs-confirm`의 `inbound_refs`(문서ID#항목ID, 각각 링크). **막지 않는다** — 알고 넣게 한다. 0이면 배너 없음 | 참조 → 그 문서의 UI-5 새 탭 |
| 13.3 | 휴지통에 넣기 | 버튼 | `위험` 색 | `DELETE /api/docs/{docId}` → UI-4로 |
| 13.4 | 닫기 | 버튼 | | 아무 일 없음(UC-H18 2a) |

### 규칙
- URL로 진입 상태를 정한다 — `#item-X`는 그 항목으로 스크롤하고 선택해 참조 패널(8.1)을 연다. UI-4 수치 다이얼로그(6) 행이 이걸로 들어온다

- 유저용(2.1)이 기본. 원본(2.2)은 URL `?tab=raw`로 직접 열 수도 있다
- 원본 탭(10)에서도 목차(6)와 패널(8)은 그대로다. 탭을 오갈 때 3단 틀이 흔들리지 않아야 한다. 원본 본문에는 항목 클릭이 없을 뿐이다
- **세 탭의 본문 최대 폭이 같아야 한다.** 다르면 탭을 오갈 때 가운데 정렬된 본문이 좌우로 흔들린다([[SYNC-UI-001#UI-5]] 4.1)
- 사이드바 폭(6.2·8.3)은 사람마다 기억한다. 화면을 옮겨도 유지된다. 기본 좌 186px · 우 250px, 손잡이는 폭 9px에 좌우 -4px 물림(누르기 쉬우면서 자리는 1px만 먹는다)
- 사이드바 바탕은 `배경 보조`다. 본문 흰색과 갈라 놔야 어디가 읽는 곳인지 바로 보인다
- **3단은 화면 높이를 채우고 가운데 열만 스크롤한다.** 목차와 패널은 각자 안에서 스크롤하고 페이지 자체는 스크롤하지 않는다([[SYNC-UI-001]] 4장 앱 셸)
- 목차 줄은 한 줄로 자르고 넘치면 말줄임한다. 항목 제목이 길어도 아래 `표시된 항목`(6.1)이 화면 밖으로 밀려나지 않아야 한다
- 배너(4·4a)와 단계 이동(9)은 본문 열 안, 본문과 같은 폭이다. 밖에 두면 본문 왼쪽 끝과 어긋난다
- 유저용 본문 맨 위에 **문서 머리** 세 줄을 얹는다 — 킥커(`프로젝트 · n단계 타입`, 단계 밖이면 `단계 밖 STD`) · 제목(frontmatter `title`) · 리드(원본 0장 첫 문단). 원본 탭(10)에는 없다. 원본은 파일 그대로를 보는 화면이다
- 원문/렌더링(10.3·10.4) 선택도 기억한다. 원본을 보는 사람은 대개 같은 쪽만 본다
- 7.1 클릭은 패널을 참조 탭으로 자동 전환
- 처음 열면 패널(8)은 참조 탭이고 "항목을 선택하세요"
- 규약 오류(4)가 있으면 상태 토글(3)이 비활성이고 배너에 이유 표시. 미완성(4a)이면 `완료로`만 비활성(`초안으로`는 언제나 된다). 배너는 유저용·원본 양쪽에 보인다
- **끊어진 참조도 미완성(4a)이다.** 저장은 됐고 완료만 막힌다. 가리키는 문서가 아직 안 쓰인 것일 수 있고, 그 문서가 들어오면 저절로 풀린다 — 이 문서를 다시 저장하지 않아도 된다. 그래서 배너가 보여주는 값과 완료를 막는 값이 **같은 곳에서 온다**(`missing_refs`)
- **완료는 확인 없이 바로 된다.** v1의 상위 대조 다이얼로그는 상위 담당자에게 어긋남을 알리는 장치였다 — 혼자 쓰면 알릴 상대가 없다. 어긋남은 사람이 읽고 에이전트에게 고치게 한다
- **지우기는 휴지통이다(PRD N3).** 어떤 문서든 넣을 수 있고, 확인(13)은 막는 게 아니라 무엇이 끊어지는지 보여준다 — 13.2는 화면이 세지 않고 서버가 `document-deletion-needs-confirm`으로 준 값이다(웹은 먼저 `confirm` 없이 불러 그 목록을 받고, 넣기를 누르면 `confirm=true`로 다시 부른다. 판정은 한 곳 `pipeline.trash_document`). 휴지통에 있는 문서는 4b 배너 하나로 말하고 상태 토글·넣기 버튼이 없다. 되살리기(4b.1)와 완전 삭제는 UI-4 휴지통 묶음(8)에도 있다
- 참조 링크(7.2)가 미존재 참조면 회색 + 경고 아이콘, 클릭해도 이동 없음
- **질문 탭(8.4)은 기본 탭이 아니다.** 처음 열면 여전히 참조 탭이고, 7.1이 참조 탭으로 가는 기존 전환도 그대로다. 질문 탭은 사람이 직접 누를 때만 열린다. URL은 `?panel=ask`
- **항목은 힌트다.** 고르지 않아도 문서 전체로 묻는다(8.5 「문서 전체」). 골랐으면 「지금 보는 항목」으로 실려 모델이 거기서 시작한다. 어느 쪽이든 모델은 같은 프로젝트를 도구로 따라 읽는다
- **진행 줄(8.9)은 실시간이다.** 응답이 SSE라 도구를 부를 때마다 한 줄씩 온다 — 한꺼번에 몰려 오면 잘못된 것이다. 답이 오기 전엔 또렷이, 온 뒤엔 흐리게
- **모델 키가 없으면 탭 자체가 없다**(인프라 5.3). 참조 탭만 남고 나머지 화면은 그대로다. 꺼진 기능을 회색으로 남겨 두지 않는다 — 켤 방법이 사람에게 없다
- **대화는 프로젝트 단위이고 서버에 저장되지 않는다.** 같은 프로젝트 안에서 문서·항목을 옮겨도 남고(8.5만 바뀐다), 다른 프로젝트로 가면 새 대화다. 새로고침하면 사라진다. 남기는 길을 화면에 두지 않는다 — 답을 명세에 옮기는 것은 사람과 그 사람의 에이전트가 한다([[SYNC-PRD-001]] 2장 「전달」의 경계)
- 답이 길어도 **패널 안에서만 스크롤한다**. 3단 규칙 그대로
- **휴지통에 있는 문서(4b)에는 질문 탭이 없다.** 파일이 저장소에서 지워진 상태라 물을 본문이 없다 — 3이 없는 것과 같은 이유다
- 다이어그램(7.3)은 편집·내려받기가 없다. 고치려면 원본의 코드블록을 에이전트에게 고치게 한다. **크게 보는 길은 전체보기(7.5)뿐이다** — 본문 폭(`--doc-w`)을 다 써도 시퀀스 스물몇 줄은 못 읽는다(공통 1.7)

### 시나리오

**S-1 항목의 근거를 따라간다** — UC-H3
1. 항목 헤더(7.1)를 클릭한다
2. 패널(8)이 참조 탭(8.1)으로 바뀌고 상위·하위 참조가 뜬다
3. 상위 참조를 클릭하면 그 문서의 UI-5로 이동해 해당 항목 위치에서 열린다
4. 브라우저 뒤로 가기로 원래 문서로 돌아온다

**S-2 문서를 완료로 올린다** — UC-H8
1. 배너(4·4a)가 없는지 본다. 미완성이 있으면 에이전트에게 채우게 한 뒤 돌아온다
2. 상태 토글(3) `완료로`를 누른다
3. 상태(1.1)가 `완료`로 바뀌고 토글이 `초안으로`가 된다. 끊어진 참조가 남아 있었으면 거절되고 토스트가 4a의 이유를 다시 말한다

**S-4 에이전트에게 줄 원본을 확인한다** — UC-H2 기본 흐름 4
1. 원본 탭(2.2)을 누른다
2. 본문 영역이 원본(10)으로 바뀌고 MD가 줄 번호와 함께 보인다
3. 복사(10.2)를 누르면 전체가 클립보드에 들어간다
4. 자기 에이전트에 붙여넣거나, 에이전트가 MCP로 직접 읽게 한다

**S-5 읽다가 막혀서 묻는다** — UC-H19
1. 질문 탭(8.4)을 누른다. 항목을 골랐으면 맥락 줄(8.5)에 그 ID와 제목이, 안 골랐으면 「문서 전체」가 떠 있다 — 어느 쪽이든 묻는다
2. 입력(8.6)에 「이 요구사항의 근거가 뭐라고 했어?」라고 묻는다
3. 진행 줄(8.9)이 흐른다 — 「R1 본문을 읽는다」 「읽음 · SYNC-PRD-001#R1」 「근거 Q1을 읽는다」 「읽음 · SYNC-RFQ-001#Q1」. 도구를 부를 때마다 한 줄씩
4. 답(8.7)이 뜨고 진행 줄은 흐려진다. 아래 「본 것」에 읽은 대상이 순서대로 보인다. 누르면 그 항목으로 간다
5. 이어 물으면 앞 대화가 함께 간다. 같은 프로젝트의 다른 문서로 옮겨도 대화는 그대로다
6. 다른 프로젝트로 가면 새 대화다. 남길 값이 있었으면 에이전트에게 말해 명세를 고치게 한다

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
    <div><b class="mono" data-el="1.1">[SYNC]</b> <span data-el="1.2">싱크독</span></div>
    <a class="repo mono" data-el="1.3">github.com/dfocus/syncdoc</a>
  </div>
  <span class="grow"></span>
  <span class="btn" data-el="2.1">참조 그래프</span>
  <span class="btn" data-el="2.2">순서대로 읽기</span>
</div>

<div class="stats" data-el="3"><!-- 세 칸. 0이면 흐리게, 1 이상이면 경고색 + 경고 테두리 -->
  <span class="stat" data-el="3.2"><b>1</b> 끊어진 참조</span>
  <span class="stat" data-el="3.4"><b>1</b> 규약 오류</span>
  <span class="stat dim" data-el="3.5"><b>0</b> 미완성</span>
</div>

<div class="body2">
  <div class="stages" data-el="4">
    <div class="stgh"><!-- 머리에 미니 히트맵 11칸 — UI-2에서 본 그 프로젝트 행이 여기 다시 있다 -->
      <b>11단계</b><span class="grow"></span>
      <i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i><i class="sw ok"></i>
      <i class="sw ok"></i><i class="sw dr"></i><i class="sw dr"></i><i class="sw dr"></i><i class="sw dr"></i><i class="sw na"></i>
    </div>

    <div class="stg" data-el="4.1">
      <span class="no mono">1</span><span class="nm">RFQ</span>
      <span class="st ok">완료</span><span class="grow"></span>
      <span class="lbl">1개</span><span class="caret">▾</span>
    </div>
    <div class="doc" data-el="4.2">
      <span class="mono">SYNC-RFQ-001</span><span class="dot ok"></span>
      <span class="lbl">완료 · v3 · 2일 전 · 박호영</span>
    </div>

    <div class="stg">
      <span class="no mono">7</span><span class="nm">화면</span>
      <span class="st dr">초안</span><span class="gate" data-el="4.3">상위 미완료</span>
      <span class="grow"></span><span class="lbl">2개</span><span class="caret">▸</span>
    </div>
    <div class="doc">
      <span class="mono">SYNC-UI-002</span><span class="dot dr"></span>
      <span class="lbl">초안 · v2 · 3시간 전 · 에이전트(박호영)</span>
      <span class="grow"></span>
      <span class="miss">끊어진 참조 1</span>
    </div>

    <div class="stg" data-el="4.4">
      <span class="no mono">—</span><span class="nm">표준 (STD)</span>
      <span class="st dr">초안</span><span class="grow"></span>
      <span class="lbl">4개</span><span class="caret">▸</span>
    </div>

    <!-- 휴지통 (8). 0건이면 묶음 자체가 없다. 접혀 있고 흐리다 -->
    <div class="stg dim" data-el="8">
      <span class="no mono">—</span><span class="nm">휴지통</span><span class="grow"></span>
      <span class="lbl">2개</span><span class="caret">▾</span>
    </div>
    <div class="doc dim" data-el="8.1">
      <span class="mono">SYNC-DOM-003</span> <span class="lbl">ERD·DD — 싱크독</span>
      <span class="lbl">v3 · 2026-09-16 박호영이 넣음</span><span class="grow"></span>
      <span class="btn sm" data-el="8.2">되살리기</span> <span class="btn sm danger" data-el="8.3">완전 삭제</span>
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

<!-- 완전 삭제 확인 (8.4) -->
<div class="dialog narrow" data-el="8.4">
  <div class="dhead">완전 삭제 — SYNC-DOM-003</div>
  <div class="dbody">행까지 지워지고 <b>되돌릴 수 없습니다.</b> 번호는 다시 쓰일 수 있습니다.
    <div class="banner warn">지울 수 없습니다 — 아직 가리키는 곳이 있습니다<br>· <b>SYNC-DOM-002#Document</b></div>
    <div class="dacts"><span class="btn">닫기</span> <span class="btn danger">완전 삭제</span></div>
  </div>
</div>

<div class="dialog" data-el="6">
  <div class="dhead">끊어진 참조 1건</div>
  <div class="dbody">
    <ul class="chk">
      <li><b>SYNC-PRD-001#R2</b> → <span class="mono">SYNC-DOM-001#참조</span> 가리키는 곳 없음 · 3일 전</li>
    </ul>
  </div>
</div>
```


### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 프로젝트 헤더 | 영역 | 코드(1.1), 이름(1.2), 저장소 주소(1.3) | — |
| 1.1 | 코드 | 텍스트 | 프로젝트 코드 | — |
| 1.2 | 이름 | 텍스트 | 프로젝트 이름 | — |
| 1.3 | 저장소 주소 | 링크 | GitHub 주소 | 새 탭으로 GitHub |
| 2.1 | 참조 그래프 | 버튼 | | UI-8로 |
| 2.2 | 순서대로 읽기 | 버튼 | | UI-9로 |
| 3 | 요약 수치 | 영역 | 프로젝트 전체의 끊어진 참조·규약 오류·미완성 건수. 0이면 흐리게 | — |
| 3.2 | 끊어진 참조 | 수치 | 가리키는 곳이 없는 참조(`references.is_missing`) 수. 항목이 삭제됐거나 아직 안 쓰였다 | 목록 다이얼로그(6). UC-H14 기본 흐름 4 |
| 3.4 | 규약 오류 | 수치 | has_convention_error 문서 수 | 목록 다이얼로그(6) |
| 3.5 | 미완성 | 수치 | incomplete_warnings가 있는 문서 수 | 목록 다이얼로그(6) |
| 4 | 11단계 표 | 표 | 단계 행(4.1)과 그 아래 문서 행(4.2) | — |
| 4.1 | 단계 행 | 행 | 순번, 단계 이름, 대표 상태, 문서 수. 문서가 여럿이면 **가장 낮은 상태**(UC-H14 1a). 문서 없으면 `미작성`(3a) | 문서 행 접기/펼치기 |
| 4.2 | 문서 행 | 행 | 문서 ID, 상태, 버전, 최근 수정 시각·주체, 끊어진 참조 수, 규약 오류 | UI-5로 |
| 4.3 | 상위 미완료 표시 | 뱃지 | 이 단계에 문서가 있는데 앞 단계에 초안 문서가 있을 때(UC-H14 1b). 막지 않는다 | — |
| 4.4 | 표준 묶음 | 행 | 11단계 밖 `STD` 문서. 대표 상태·문서 수. 없으면(다른 프로젝트) 행 자체가 없음 | 문서 행 접기/펼치기 |
| 5 | 최근 변경 | 목록 | 이 프로젝트의 최근 버전·상태 변경 N건. 커밋 메시지 접두어(`spec`/`status`)로 구분 | 문서 클릭 → UI-5 |
| 6 | 목록 다이얼로그 | 다이얼로그 | 3.x에서 누른 종류의 항목 목록. 항목·원인·시각 | 항목 클릭 → 그 문서의 UI-5 해당 위치 |
| 7 | 동기화 상태 | 영역 | 최근 변경 아래. 이 저장소를 어디까지 처리했나 | — |
| 7.1 | 마지막 처리 커밋 | 텍스트 | `repositories.last_processed_commit` | 새 탭으로 GitHub 커밋 |
| 7.2 | 밀린 커밋 | 수치 | 원격이 앞선 커밋 수. 0이면 최신 | — |
| 8 | 휴지통 | 묶음 | 11단계 표 맨 아래(표준 묶음 아래). `GET /api/projects/{code}/trash`. **0건이면 묶음 자체가 없다.** 흐리게 — 살아 있는 문서와 한눈에 갈린다 | 펼침/접힘 |
| 8.1 | 휴지통 문서 행 | 행 | 문서 ID·제목·마지막 버전·언제 누가 넣었나 | 그 문서의 UI-5 (4b 배너) |
| 8.2 | 되살리기 | 버튼 | 행마다 | `POST …/restore` → 그 문서의 UI-5(UC-H18 5) |
| 8.3 | 완전 삭제 | 버튼 | 행마다. `위험` 색 | 확인(8.4). 서버가 `document-has-history`면 걸리는 것을 8.4 안에 보여주고 막는다 |
| 8.4 | 완전 삭제 확인 | 다이얼로그 | 「행까지 지워지고 되돌릴 수 없다」 + 걸리는 것(있으면) | 확인 → `POST …/purge` → 묶음에서 사라짐 |

### 규칙

- **휴지통(8)은 단계 표의 일부가 아니다.** 단계 칸(4.1)·미니 히트맵·요약 수치(3)·최근 변경(5)·그래프·순서 읽기는 휴지통 문서를 세지 않는다. 휴지통에 있는 동안 그 문서는 프로젝트에 없는 것이다 — 행만 남아 되돌릴 수 있을 뿐
- 완전 삭제는 되살리기보다 한 단계 깊다 — 확인(8.4)이 한 번 더 있고, 남이 가리키는 동안은 서버가 막는다
- 단계 상태 색: `완료` 초록 / `초안` 회색 / `미작성` 빈칸. UI-2와 같은 기준
- **11단계 표 머리에 미니 히트맵 11칸을 둔다.** UI-2에서 본 그 프로젝트 행이 여기 다시 있다 — 목록에서 눌러 들어온 사람이 같은 그림을 찾을 수 있게. 14px 정사각형
- 단계 행은 아코디언이고 **기본은 접힘이다.** 캐럿(`▾`/`▸`)이 접힘 상태를 말하고 행 전체가 손잡이다.
  열두 줄이 다 펼쳐지면 화면 하나에 11단계가 안 들어와, 이 화면이 답하려는 "어디까지 왔나"를 먼저 못 본다.
  시나리오 S-1도 "단계 행을 누르면 문서 행이 펼쳐지고"로 접힌 상태에서 출발한다
- UI-2 칸에서 `#stage-N`으로 들어오면 **그 단계만 펼친 채로** 연다(UI-2 요소 2.2 "그 단계 위치")
- 문서 행은 46px 들여쓰고 바탕을 한 톤 낮춘다(`#fdfdfc`). 단계 행과 같은 높이로 두면 어느 쪽이 묶음인지 안 보인다
- 요약 수치(3)는 **17.5px 고정폭**. 0이면 흐리게(`opacity .55`), 1 이상이면 경고색 숫자에 경고 테두리
- 4.1의 대표 상태는 그 단계 문서들 중 가장 낮은 것. 완료 2개 + 초안 1개면 `초안`
- 4.3은 표시만 한다. 순서는 권장이지 강제가 아니다(PRD 비목표)
- **요약 수치는 세 칸이다.** 끊어진 참조·규약 오류·미완성 — 셋 다 문서를 읽어 판정한 값이고, 사람이 에이전트에게 고치게 해야 풀린다. v1의 여섯 칸 중 플래그 둘과 댓글은 협업 장치와 함께 빠졌다([[SYNC-CODE-001#V]])
- 수치가 0이면 흐리게, 1 이상이면 경고색으로. 세 칸 모두 눌러 목록(6)을 연다
- 최근 변경(5)은 `status` 커밋도 포함한다. 상태만 바뀐 것도 변경이다
- **동기화 상태(7)는 읽기만 한다.** 폴링이 갱신한 DB 값을 그대로 보여준다 — 이 화면에 들어올 때마다 fetch가 돌지 않는다. 재구축 같은 조작은 여기 없고 UI-14에 있다([[SYNC-UI-001#UI-14]] 7장 4)

### 시나리오

**S-1 어느 단계가 막혔는지 파악한다** — UC-H14 기본 흐름 3
1. 11단계 표(4)를 위에서 아래로 훑는다
2. USECASE 단계에 `상위 미완료`(4.3)가 붙어 있다. 사용자 시나리오가 아직 초안이라서다
3. 단계 행을 누르면 문서 행이 펼쳐지고, 문서 행에 `규약 오류`가 보인다
4. 문서 행(4.2)을 눌러 UI-5로 들어간다

**S-2 처리할 건수를 파고든다** — UC-H14 기본 흐름 4
1. 요약 수치(3)에서 `끊어진 참조 1`을 누른다
2. 목록 다이얼로그(6)가 뜨고 어느 항목의 어느 참조가 가리키는 곳이 없는지 나열된다
3. 항목을 누르면 그 문서의 UI-5가 해당 항목 위치에서 열린다

**S-3 누가 뭘 바꿨는지 본다**
1. 최근 변경(5)을 본다. 에이전트가 쓴 것과 사람이 쓴 것이 구분된다
2. `status: 초안 → 완료` 같은 상태 전환도 줄로 보인다
3. 문서를 누르면 UI-5로 간다

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
  <span class="crumb"><b class="mono">[SYNC]</b> 싱크독</span><span class="sep">›</span>
  <span class="crumb mono">2 PRD</span><span class="sep">›</span>
  <b class="mono">SYNC-PRD-001</b>
  <span class="pill pill-approved">완료</span><span class="ver mono">v7</span>
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
      <div class="msg">status: 초안 → 완료</div>
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
    v3에는 <b>#R15</b>가 없습니다. 되돌리면 이 항목이 사라지고 하위 참조 2건이 <b>끊어진 참조</b>가 됩니다.
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
| 3.1 | 비교 범위 | 텍스트 | `vA → vB`, 변경 항목 수, 줄 수. 두 행이 같은 번호로 읽히면 비교할 것이 없다고 말한다 | — |
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
- **`status` 행은 그 시점의 버전 번호로 읽는다.** `v6 → status → v7`이면 `status` 행은 `v6`이다 — 상태 변경은 본문을 안 바꾸므로 그때의 본문은 직전 버전의 본문이다. 이렇게 읽지 않으면 `version_no`가 없어 비교 범위가 안 잡히고 diff 영역이 빈 채로 남는다(#18)
- 두 행이 **같은 번호로 읽히면**(예: `v6`과 그 뒤 `status`) 비교할 것이 없다. 3.1이 그렇게 말한다 — 빈 화면으로 두면 고장인지 같은 내용인지 구분이 안 된다
- 되돌리기(4.2)는 UC-A6과 같은 파이프라인을 탄다. 규약 검사·참조 추출이 전부 돈다. 되돌린 결과가 현재 규약을 위반하면 거부된다(UC-H7 4a)
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
      <span><b class="mono">[SYNC]</b> 싱크독</span>
      <span class="sub"><b class="work">끊어진 참조 1 · 규약 오류 1</b> · 21문서 · 12분 전</span>
    </span>
    <span class="cell ok" data-el="2.2">1</span>
    <span class="cell ok missing">1</span>
    <span class="cell ok">1</span>
    <span class="cell ok">1</span>
    <span class="cell ok">1</span>
    <span class="cell dr missing">3</span>
    <span class="cell dr">2 <i data-el="2.4">▲</i></span>
    <span class="cell dr">2 <i>▲</i></span>
    <span class="cell dr">1 <i>▲</i></span>
    <span class="cell dr">3 <i>▲</i></span>
    <span class="cell na"></span>
  </div>

  <div class="hrow">
    <span></span>
    <span class="pname"><span><b class="mono">RHYM</b> 리듬핏</span><span class="sub">1문서 · 어제</span></span>
    <span class="cell dr">1</span>
    <span class="cell na"></span><span class="cell na"></span><span class="cell na"></span><span class="cell na"></span>
    <span class="cell na"></span><span class="cell na"></span><span class="cell na"></span><span class="cell na"></span>
    <span class="cell na"></span><span class="cell na"></span>
  </div>
</div>

<div class="legend lbl" data-el="4">
  <span><i class="sw dr"></i> 초안</span>
  <span><i class="sw ok"></i> 완료</span> <span><i class="sw na"></i> 미작성</span>
  <span class="warn">⚠ 끊어진 참조·규약 오류 있음</span> <span class="warn">▲ 상위 미완료 (막지는 않는다)</span>
</div>

<div class="empty" data-el="3">내 프로젝트가 없습니다. 위의 프로젝트 초기화로 시작하세요.</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 헤더 | 영역 | 제목, 프로젝트 수 | — |
| 1.1 | 프로젝트 초기화 | 버튼 | | UI-3으로 |
| 2 | 현황판 | 표 | 프로젝트가 행, 11단계가 열(UC-H14 기본 흐름 1) | — |
| 2.1 | 프로젝트 행 | 행 | 코드·이름, 그 아래 끊어진 참조·규약 오류 요약 | UI-4로 |
| 2.2 | 단계 칸 | 칸 | 그 단계의 대표 상태를 색으로. 문서 수를 숫자로. 문서가 여럿이면 **가장 낮은 상태**(UC-H14 1a). 없으면 빈칸(3a) | UI-4로 (그 단계 위치) |
| 2.3 | 경고 표시 | 아이콘 | 끊어진 참조·규약 오류가 하나라도 있는 프로젝트(UC-H14 기본 흐름 2) | — |
| 2.4 | 상위 미완료 표시 | 아이콘 | 이 단계에 문서가 있는데 앞 단계에 초안이 있을 때(UC-H14 1b) | — |
| 3 | 빈 상태 | 텍스트 | 내가 소유한 프로젝트가 하나도 없을 때만. 남의 프로젝트가 있어도 여기서는 「없다」 | — |
| 4 | 범례 | 텍스트 | 칸 색과 기호가 무엇을 뜻하는지. 표 아래 한 줄 | — |

### 규칙

- **표가 아니라 격자다.** `20px 196px repeat(11,1fr)` · `gap 4px` · 행 `padding 10px 14px`. 칸은 높이 22px에 `border-radius 3px`이고 **열 폭을 꽉 채운다** — 작은 칩으로 그리면 색이 띠로 안 읽히고 히트맵이 아니게 된다
- 열 이름은 `1 RFQ` … `11 CODE`. 단계 번호를 붙여 순서가 보이게 한다. 11px 고정폭, 머리 행 배경 `배경 보조`
- 프로젝트 칸(196px)은 두 줄이다 — 첫 줄 `코드`(고정폭 13px/600) + `이름`(15.5px), 둘째 줄 `끊어진 참조 N · 규약 오류 M`(0이 아닌 것만, 경고색 600) · `N문서 · 갱신 시각`(12.5px 보조)
- 칸 색: `완료` 초록 / `초안` 회색 / `미작성` 빈칸. UI-4와 같은 기준
- 2.3 경고는 종류를 구분하지 않고 하나로. 종류별 건수는 **툴팁**과 2.1 행 아래 요약과 UI-4에서
- 칸(2.2)의 문서에 끊어진 참조가 있으면 경고색 테두리를 두른다. 색은 상태, 테두리는 끊어진 참조 — 두 정보가 한 칸에 겹치지 않게
- **범례(4)를 뺄 수 없다.** 색 셋과 기호 둘을 처음 보는 사람이 알 방법이 이것뿐이다
- 프로젝트 정렬은 최근 변경순. 오래 안 건드린 프로젝트가 아래
- **목록에는 내가 소유한 프로젝트만 뜬다**([[SYNC-PRD-001#R12]]). 서버가 로그인 계정으로 걸러 주므로 화면은 받은 것만 그린다. 남의 프로젝트는 세지도 않는다 — 헤더(1)의 「N개」는 내 것의 수다. 주소를 직접 쳐서 남의 UI-4·UI-5로 가면 not-found 화면이다

### 시나리오

**S-1 어느 프로젝트가 막혀 있나 본다** — UC-H14 기본 흐름 1~2
1. 로그인하면 이 화면이다
2. 행마다 11칸 색을 훑는다. SYNC는 6단계까지 채워졌고 뒤가 비어 있다
3. SYNC 앞에 경고(2.3)가 있다. 행 아래에 "끊어진 참조 1 · 규약 오류 1"
4. 프로젝트 행(2.1)을 눌러 UI-4로 들어간다

**S-2 단계 하나로 바로 간다**
1. SYNC 행의 UC 칸에 `▲`(2.4)가 보인다. 앞 단계가 초안인데 이미 문서가 있다
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
| 2 | GitHub로 로그인 | 버튼 | | GitHub OAuth 동의 화면으로. 공개 저장소 범위(`public_repo`)만 요청 |
| 3 | 복귀 안내 | 텍스트 | 원래 URL이 있었으면 그리로 간다는 안내 | — |

### 규칙

- 유일하게 공통 틀(상단 바)이 없는 화면
- **이 화면은 서버에서 아무것도 안 읽는다.** v1.2에 11단계 색 띠를 뒀다가 뺐다 — 아래 참고
- **카드에 담지 않는다.** 앱 배경 위에 로고·설명·버튼만 놓고 화면 세로 가운데에 둔다. 흰 판을 깔면 배경과 카드가 한 겹 더 갈리면서 로그인 폼이 '입력할 것이 많은 화면'처럼 보인다 — 여기서 할 일은 버튼 하나다
- **버튼은 콘텐츠 폭을 채우는 검정 채움이다.** 이 화면에서 유일한 동작이므로 유일한 강조여야 한다. 테두리만 있는 버튼으로 두면 배경과 대비가 없어 어디를 눌러야 할지 눈이 먼저 못 찾는다
- 복귀 안내(3)는 버튼보다 한 단계 낮은 캡션이다. 누를 것이 아니라 알림이다
- OAuth 성공 → 원래 가려던 URL. 없으면 UI-2
- OAuth 토큰은 앱 비밀키로 암호화해 저장한다(인프라 5장). 이 화면은 그 사실을 보여주지 않는다
- 누구나 GitHub 계정이면 들어온다. 그런데 보이는 것은 자기가 등록한 프로젝트뿐이라([[SYNC-PRD-001#R12]]), 등록한 것이 없는 계정은 로그인은 되지만 UI-2가 빈 상태(3)다

### 시나리오

**S-1 처음 들어온다**
1. 공개 주소를 열면 이 화면이다
2. GitHub로 로그인(2)을 누른다. GitHub 동의 화면에서 허용한다
3. UI-2로 간다

**S-2 링크로 문서에 바로 들어오려 했다**
1. 예전에 저장해 둔 `…/d/SYNC-PRD-001` 링크를 열었는데 로그인이 안 되어 있다
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

    <label class="chk"><input type="checkbox" data-el="2.6"> 저장소가 없으면 새로 만든다 <span class="lbl">(공개로 만들어집니다)</span></label>

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
| 2.6 | 없으면 만든다 | 체크박스 | 끄면 지금과 같다 — 없는 저장소면 `push-failed`. 켜면 **공개 저장소**를 만들어 준다([[SYNC-CODE-001#F]]). **비공개 선택지는 없다** — v1의 폴링이 토큰 없이 돌아 비공개면 조용히 죽는다 | — |
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
- **등록하는 사람이 소유자다**([[SYNC-PRD-001#R12]]). 이 프로젝트는 그 뒤로 이 계정에만 보인다. 옮기거나 나누는 조작은 없다

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
    <div class="crumbs"><a href="/p/SYNC"><b class="mono">[SYNC]</b> 싱크독</a><span class="sep">›</span><span>참조 그래프</span></div>
    <b>참조 그래프</b>
  </div>
  <span class="grow"></span>
  <span class="lbl" data-el="1.1">SYNC · 문서 21 · 항목 339 · 참조 949</span>
</div>

<div class="gcard">
  <div class="gbar" data-el="2">
    <span class="lbl">범위</span>
    <span class="btn on" data-el="2.1">전체</span>
    <span class="btn" data-el="2.2">완료만</span>
    <span class="sep"></span>
    <span class="lbl" data-el="2.4">노드에 마우스를 올려 그 항목만 보기</span>
    <span class="grow"></span>
    <span class="btn" data-el="2.5">전체보기</span>
  </div>

  <div class="canvas" data-el="3">
    <div class="colh">1 RFQ</div><div class="colh">2 PRD</div><div class="colh">3 SCN</div><div class="colh">…</div>
    <div class="node" data-el="3.1"><span class="nlabel">RFQ-001#Q1</span></div>
    <div class="node"><span class="nlabel">PRD-001#R1</span></div>
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
| 2.2 | 완료만 | 버튼 | **문서 상태가 `완료`인 문서의 항목**만. 확정된 뼈대만 본다 | 범위를 완료만으로(UC-H4 2b) |
| 2.4 | 포커스 라벨 | 텍스트 | 노드에 올리기 전에는 안내. 올리면 `문서#항목 — 상위 n · 하위 m` | — |
| 2.5 | 전체보기 | 버튼 | | 상단 바까지 숨기고 화면 전체를 캔버스로. 다시 누르면 복귀 |
| 3 | 캔버스 | 영역 | 열 = 11단계, 노드 = 항목. 안에서 스크롤 | — |
| 3.1 | 노드 | 노드 | 항목 ID. 라벨이 넘치면 말줄임 | UI-15 11단계 흐름 |
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

**S-2 확정된 뼈대만 본다** — UC-H4 확장 2b
1. 노드가 수백 개라 읽기 어렵다. `완료만`(2.2)을 누른다
2. 완료 문서의 항목과 그것들 사이 참조만 남는다. 통계(1.1)도 그만큼 줄어든다
3. `전체`(2.1)로 돌아오면 초안 문서의 항목이 다시 보인다

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
  <div class="banner" data-el="3">이 단계에 완료된 문서가 없습니다. <b>SYNC-SCN-001</b>은 <b>초안</b>입니다. <span class="btn sm" data-el="3.1">초안 보기</span></div>

  <article class="main" data-el="4">
    <div class="dochead">
      <div class="kicker mono" data-el="4.1">싱크독 · 3/11 · SYNC-SCN-001 · 초안 v4</div>
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
| 1 | 단계 레일 | 영역 | 화면 맨 위 전폭 서브바. 왼쪽에 `← [코드] 이름`(1.6), 그 뒤로 단계 칩(2) | 왼쪽 링크 → UI-4 |
| 2 | 단계 표시 | 진행 표시 | 11단계 칩. 번호와 타입 코드는 항상 보인다. 번호는 흐리게, 상태 점은 **라벨 뒤**. 현재 단계는 채워서 | 단계 클릭 → 그 단계로 |
| 3 | 미확정 배너 | 배너 | 이 단계에 완료 문서가 없을 때. 있는 문서와 상태(UC-H16 2a) | — |
| 3.1 | 초안 보기 | 버튼 | | 초안 문서를 본문(4)에 띄운다(UC-H16 2a1) |
| 4 | 본문 | 사람용 뷰 | 현재 단계의 완료 문서. UI-5 유저용 탭과 같은 렌더링, 목차·패널 없음(UC-H16 기본 흐름 2) | — |
| 4.1 | 위치 | 텍스트 | 문서 머리의 킥커. `[코드] 이름 · n/11 · 문서ID · 상태 v버전`(1.6). 그 아래 제목과 리드가 온다 | — |
| 5 | 이동 | 영역 | 앞·뒤 단계와 문서 열기 | — |
| 5.1 | 이전 단계 | 버튼 | | 앞 단계로 |
| 5.2 | 다음 단계 | 버튼 | 이 화면의 주 동선이라 채운 버튼이다 | 뒤 단계로(UC-H16 기본 흐름 3) |
| 5.3 | 이 문서 열기 | 버튼 | | 현재 문서의 UI-5 |

### 규칙

- 기본은 완료 문서만. 완료가 없으면 배너(3)가 뜨고 본문은 비어 있다. 초안 보기(3.1)를 눌러야 보인다
- 한 단계에 완료 문서가 여럿이면(DOM처럼) 문서 ID 순으로 이어서 보여준다
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

**S-2 완료 안 된 단계를 만난다** — UC-H16 확장 2a
1. 3 SCN에 도착하니 배너(3)가 뜬다. 초안이라 확정본이 없다
2. 초안 보기(3.1)를 누르면 초안 문서가 본문에 보인다. 4.1에 "초안 v4"라고 표시된다
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
<div class="dialog setdlg" data-el="1"><!-- 폭 620px. 카드 넷이 드는 폭이다 -->
  <div class="dhead"><span>설정</span><span class="grow"></span><span class="x" data-el="7">✕</span></div>
  <div class="dbody">

    <!-- 토큰이 맨 위다. 이 화면에 오는 이유가 토큰이라서 -->
    <section class="card" data-el="3">
      <div class="cardh"><b>MCP 토큰</b><span class="grow"></span><span class="btn sm solid" data-el="3.4">+ 발급</span></div>
      <p class="lbl">에이전트가 싱크독에 붙을 때 씁니다. 남에게 주면 그 사람 작업이 내 이름으로 남습니다.</p>
      <div class="row"><input class="inp wide" data-el="3.3" placeholder="이름 — 예: Gemini 노트북"><span class="btn sm solid">발급</span></div>
      <div class="tokbox" data-el="4">
        <b>한 번만 보입니다. 지금 복사하세요.</b>
        <div class="tok" data-el="4.1">syncdoc_pat_7f3a…c91e</div>
        <span class="btn sm" data-el="4.2">복사</span>
      </div>
      <div class="row" data-el="3.1">
        <span class="two"><b>Claude Code 노트북</b><span class="lbl mono">발급 2026-09-01</span></span>
        <span class="grow"></span> <span class="lbl" data-el="3.5">마지막 사용 12분 전</span> <span class="btn sm danger" data-el="3.2">폐기</span>
      </div>
      <div class="row dimrow"><span class="two"><b>테스트용</b><span class="lbl mono">발급 2026-08-28 · <s>폐기됨 2026-09-02</s></span></span></div>
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

    <!-- 계정은 맨 아래. 로그아웃은 상단 바에도 있다 -->
    <section class="card" data-el="2">
      <div class="cardh"><b>내 계정</b></div>
      <div class="row"><span data-el="2.1">HoyoungParkme</span> <span class="lbl">GitHub · 박호영</span><span class="grow"></span><span class="btn sm" data-el="2.2">로그아웃</span></div>
      <p class="lbl">커밋 이메일 — GitHub에서 바로 push한 커밋을 내 계정으로 잇습니다. 등록 뒤 관리에서 인덱스 재구축을 한 번 돌리세요.</p>
      <div class="row" data-el="2.3"><span class="mono">you@example.com</span><span class="grow"></span><span class="btn sm danger" data-el="2.4">삭제</span></div>
      <div class="row"><input class="inp wide" data-el="2.5" placeholder="you@example.com"><span class="btn sm" data-el="2.6">추가</span></div>
    </section>

  </div>
  <div class="dfoot"><span class="grow"></span><span class="btn solid" data-el="9">닫기</span></div>
</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 다이얼로그 | 다이얼로그 | 어느 화면 위에서든 뜬다. 닫으면 보던 화면 그대로 | — |
| 2 | 내 계정 | 카드 | GitHub 로그인 ID(2.1), 표시 이름, 커밋 이메일 목록(2.3) | — |
| 2.1 | 로그인 ID | 텍스트 | GitHub 계정 | — |
| 2.2 | 로그아웃 | 버튼 | | 세션 종료 → UI-1 |
| 2.3 | 커밋 이메일 행 | 행 | 등록된 이메일 하나. 고정폭. 하나도 없으면 행이 없다 | — |
| 2.4 | 삭제 | 버튼 | | 확인 후 삭제 |
| 2.5 | 이메일 입력 | 입력 | git 커밋에 쓰는 이메일 | — |
| 2.6 | 추가 | 버튼 | 2.5가 비어 있으면 비활성 | 등록하고 목록에 더한다. 남이 이미 등록했으면 그 자리에 오류 |
| 3 | MCP 토큰 | 카드 | 내 토큰 목록과 발급 | — |
| 3.1 | 토큰 행 | 행 | 두 줄 — 이름 / 발급일(연도까지). 오른쪽에 마지막 사용(3.5) · 폐기. **원문은 안 보인다**(해시만 저장) | — |
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
- **카드 순서는 MCP 토큰 · 클라이언트 설정 · 관리 · 내 계정이다.** 이 화면에 오는 이유가 토큰이라 토큰이 맨 위다. 로그아웃은 상단 바에도 있으므로 계정은 맨 아래
- 카드 머리는 제목과 동작만 든다. 설명은 제목 아래 별도 줄. 세 카드가 같은 서식을 쓴다
- 발급(3.4)은 카드 머리의 채운 버튼이다. 누르면 이름 입력(3.3)이 목록 위에 펼쳐진다 — 기본 상태의 카드는 제목·발급·토큰 목록만 보인다
- 토큰 행(3.1)은 두 줄이다. 첫 줄이 이름, 둘째 줄이 고정폭으로 발급일(연도까지). 식별자를 다루는 목록임이 서식으로 보여야 한다
- **버튼 위계는 셋이다** — 채움(발급·닫기) · 테두리(보조) · 빨강(폐기). 폐기는 이 화면에서 유일한 파괴 동작이라 유일한 색이다
- 다이얼로그 폭은 `620px`. 본문 바탕은 `배경 보조`라 흰 카드가 카드로 읽힌다
- **커밋 이메일(2.3~2.6)은 GitHub 계정과 커밋 작성자를 잇는 다리다.** git 커밋이 남기는 신원은 이름과 이메일뿐이고 이름은 아무 문자열이라 계정과 못 잇는다. 등록 안 하면 GitHub에서 바로 push한 내 커밋이 **다른 사람으로 잡혀 이력의 작성자가 남이 된다**
- **등록만으로는 이미 쌓인 것이 안 옮겨진다.** 버전은 인덱스를 다시 만들 때 작성자를 다시 찾는다. **등록 → 관리(5)에서 인덱스 재구축** 순서로 해야 한다. 이 안내를 카드에 둔다
- **순서를 뒤집으면 화면이 잠긴다.** 이메일 없이 재구축하면 그 사람이 마지막으로 만진 문서 전부에 `author.unknown` 규약 오류가 붙고, 규약 오류가 있는 문서는 상태 변경 버튼이 통째로 비활성이다(UI-5 규칙)
- **이메일 하나는 사람 하나다.** 남이 이미 등록한 이메일은 거부된다(409 `email-taken`). 먼저 등록한 쪽이 임자다. 사칭을 완전히 막지는 못하지만 권한은 안 준다 — push는 여전히 그 사람의 OAuth 토큰이 있어야 한다
- **삭제(2.4)는 확인을 받는다.** 다음 재구축에서 그 이메일로 들어온 커밋이 자리표시로 돌아간다
- **행에 토큰 접두어를 두지 않는다.** 서버는 해시만 저장하므로 접두어를 남기려면 컬럼을 따로 만들어야 하는데, 이름(label)이 이미 어느 토큰인지 말한다. 컬럼 하나를 더 두고 기존 토큰은 빈칸으로 남기는 값을 치를 만큼은 아니다(#20)

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

**S-3 GitHub에서 바로 push한 내 커밋이 남으로 잡혔다**
1. 문서 이력(UI-7)의 작성자가 내 계정이 아니다
2. 설정 → 내 계정에서 이메일 입력(2.5)에 `git config user.email` 값을 적고 추가(2.6)
3. 관리(5.1)를 열고 인덱스 재구축을 돌린다
4. 버전 작성자가 내 계정으로 바뀐다

---

## UI-14 관리

| 항목 | 내용 |
|---|---|
| 화면 설계 | [[SYNC-UI-001#UI-14]] |
| 경로 | 없음. **UI-13 다이얼로그 안 관리 카드(6)** |
| 진입 | UI-13 관리 카드 열기(5.1) |
| 유스케이스 | [[SYNC-UC-001#UC-S6]] (사람이 관리 화면에서 실행) · [[SYNC-UC-001#UC-H17]] (해제) · [[SYNC-DOM-003#repositories]] |

### 배치

```html
<!-- UI-13 다이얼로그 안 관리 카드(6)를 펼친 모습 -->
<div class="adminh" data-el="1"><span class="lbl">위험한 동작이 있습니다</span></div>

<div class="adminbody">
  <table class="vers" data-el="2">
    <tr><th>프로젝트</th><th>저장소</th><th>마지막 처리 커밋</th><th>동기화</th><th></th></tr>
    <tr data-el="2.1"><td><b class="mono">[SYNC]</b> 싱크독</td><td class="lbl">dfocus/syncdoc</td><td><span class="mono" data-el="2.2">a1b2c3d</span> <span class="lbl">1시간 전</span></td><td data-el="2.3"><span class="st ok">최신</span></td><td><span class="btn sm" data-el="3">인덱스 재구축</span> <span class="btn sm danger" data-el="7">해제</span></td></tr>
    <tr><td><b class="mono">[DBA]</b> 데이터베이스 관리</td><td class="lbl">dfocus/dba-ax</td><td><span class="mono">9e8f7a6</span> <span class="lbl">3일 전</span></td><td><span class="st behind">밀림 2</span></td><td><span class="btn sm">인덱스 재구축</span> <span class="btn sm danger">해제</span></td></tr>
    <tr><td><b class="mono">[AIRD]</b> 에어데이터</td><td class="lbl">dfocus/airdata</td><td><span class="mono">—</span></td><td><span class="st na">문서 없음</span></td><td><span class="btn sm">인덱스 재구축</span> <span class="btn sm danger">해제</span></td></tr>
  </table>

  <div class="dialog" data-el="4">
    <div class="dhead">SYNC 인덱스 재구축</div>
    <div class="dbody">
      저장소의 모든 MD를 다시 읽어 참조 관계와 버전 목록을 처음부터 만듭니다. 문서가 많으면 몇 분 걸립니다.
      <!-- 해제(7)일 때는 머리가 「SYNC 싱크독에서 해제」, 본문이 「등록과 작업 사본을 지웁니다」이고 아래 안내(4.3)가 붙는다. 다이얼로그는 하나다 -->
      <div class="banner warn" data-el="4.3"><b>GitHub 저장소는 그대로 남습니다</b> — 다시 등록하면 문서와 이력이 git에서 복원됩니다</div>
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
| 2.1 | 저장소 행 | 행 | 프로젝트(「[코드] 이름」, 1.6), 저장소, 마지막 처리 커밋(2.2), 동기화(2.3) | — |
| 2.2 | 마지막 처리 커밋 | 텍스트 | `repositories.last_processed_commit`과 시각 | 새 탭으로 GitHub 커밋 |
| 2.3 | 동기화 상태 | 뱃지 | 원격 최신과 같으면 `최신`, 처리 안 한 커밋이 있으면 `밀림 N`(UC-G1 1a·1b) | — |
| 3 | 인덱스 재구축 | 버튼 | 행마다 | 확인 다이얼로그(4) |
| 4 | 재구축 확인 | 다이얼로그 | 무엇을 다시 만들고 무엇은 안 건드리는지(UC-S6 최소 보장) | — |
| 4.1 | 재구축 | 버튼 | | UC-S6 실행. 끝나면 결과(5) |
| 4.2 | 취소 | 버튼 | | 닫힘 |
| 4.3 | 해제 안내 | 텍스트 | 해제(7)일 때만. 저장소는 남는다 · 재등록하면 문서와 이력이 복원된다 | — |
| 5 | 재구축 결과 | 영역 | 마지막 실행 결과(UC-S6 기본 흐름 4) | — |
| 5.1 | 집계 | 텍스트 | 읽은 문서·항목·참조·버전 수 | — |
| 5.2 | 규약 오류 목록 | 목록 | 재구축 중 발견된 위반 문서(UC-S6 2a) | 문서 클릭 → UI-5 |
| 7 | 해제 | 버튼 | 행마다, 재구축(3) 옆. 위험색 외곽선 — 토큰 폐기(UI-13 3.2)와 같은 어휘 | 확인 다이얼로그(4, 안내 4.3) → [[SYNC-API-001#DELETE/api/projects/{code}]]. 끝나면 UI-2로 |

### 규칙

- **독립 화면이 아니라 UI-13 안의 영역이다.** v1.2에서 별도 페이지를 없앴다. 재구축은 위험해서 깊이 두는 게 맞지만, 자주 보는 동기화 상태는 UI-4에도 함께 내보낸다([[SYNC-UI-001#UI-14]] 7장 4)
- 재구축은 참조 테이블·버전 목록·항목 테이블을 지우고 다시 만든다(UC-S6). 저장소에 있는 것은 전부 되살아난다 — v2에서는 저장소 밖에 사는 추적 데이터가 없어 「건드리지 않는 것」을 약속할 필요가 없어졌다([[SYNC-CODE-001#V]])
- **버전 번호는 바뀔 수 있다.** 재구축은 커밋마다 버전을 만들므로 번호가 전부 다시 매겨진다. 버전을 가리키는 것은 참조뿐이고 참조도 함께 다시 만들어지므로 어긋날 것이 없다
- 동기화 상태(2.3)는 **DB에서 읽는다.** 폴링이 `behind_by`·`fetched_at`을 갱신하므로 이 카드를 열 때마다 fetch가 돌지 않는다([[SYNC-DOM-002#Repository]])
- `밀림 N`은 폴링이 잡아 처리한다(UC-G1 1b). 이 화면에 수동 동기화 버튼은 없다 — 유스케이스에 없다
- 재구축 확인(4)은 **UI-13 위에 한 겹 더** 뜬다. 다이얼로그 위의 다이얼로그다
- 이 표에는 내가 소유한 프로젝트만 뜬다([[SYNC-PRD-001#R12]]). 역할 구분은 여전히 없다 — 소유자는 셋(재구축·해제·동기화 보기) 다 할 수 있다. 위험한 동작이라 확인 다이얼로그(4)가 한 번 더 막는다
- **해제(7)는 싱크독의 등록·색인·작업 사본만 지운다.** GitHub 저장소는 손대지 않는다 — 명세 원본은 거기 있고, 다시 등록하면 문서가 git에서 복원된다(UC-A1 3a2). 그래서 재구축과 같은 표에 둔다: 둘 다 「이 저장소를 싱크독이 어떻게 들고 있나」를 만지는 일이다
- **해제 확인(4)은 무엇이 남는지 말한다(4.3).** GitHub 저장소와 그 이력은 그대로고, 다시 등록하면 문서가 돌아온다. 뭉뚱그려 「정말 지울까요?」라고만 물으면 사람이 무엇을 잃는지 모른 채 누른다
- **해제가 끝나면 UI-2로 간다.** 이 다이얼로그는 어느 화면 위에서든 뜨므로 지운 프로젝트의 상세 위에서 눌렀을 수 있다
- **버튼은 「해제」 두 글자다.** 이 표는 620px 다이얼로그 안에 있다([[SYNC-UI-001#UI-13]] 규칙) — 열이 늘거나 버튼이 길면 머리글이 두 줄로 꺾이고 버튼이 세로로 쌓인다(실측 34px → 55px). 둘이 한 칸에 가로로 서야 한다

### 시나리오

**S-1 DB를 날려먹었다** — UC-S6
1. Postgres를 다시 만들었다. 문서는 GitHub에 다 있다
2. 프로젝트마다 인덱스 재구축(3)을 누른다. 확인(4.1)
3. 결과(5)에 집계와 규약 오류가 뜬다. 참조 그래프가 살아난다. 상태도 `status(` 커밋에서 돌아온다 — 저장소 밖에 살던 것이 없으니 잃은 것도 없다

**S-2 서버를 며칠 꺼뒀다**
1. 표(2)에서 DBA가 `밀림 2`(2.3)다. 꺼진 동안 누가 push했다
2. 폴링이 곧 잡는다. 기다리거나, 급하면 재구축(3)

**S-3 시험으로 만든 프로젝트를 치운다** — UC-H17
1. 설정 → 관리를 열고 표(2)에서 그 행의 해제(7)를 누른다
2. 확인(4)에 저장소는 남는다는 것(4.3)이 뜬다. 해제(4.1)
3. UI-2로 돌아오고 그 행이 없다. GitHub에는 저장소가 그대로 있다

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
    <p class="lbl" data-el="2">이 항목이 11단계 체인에서 어디에 있고 어디로 흐르는지. 위는 이 항목이 근거로 삼은 것, 아래는 이 항목을 근거로 삼은 것. 항목을 누르면 그 항목 기준으로 다시 봅니다.</p>

    <div class="chain" data-el="3">
      <div class="crow">
        <div class="cstage" data-el="3.2">1 RFQ<br><span class="lbl">근거 ↑</span></div>
        <div class="cchips"><span class="chip" data-el="3.1"><i class="dot dot-approved"></i>RFQ-001#Q1 원본은 누가 읽는가</span></div>
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
    <span class="btn solid" data-el="4">문서 뷰로 열기</span>
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
| 3.1 | 항목 칩 | 칩 | 상태 점 · 항목 ID · 제목. 없는 항목이면 점선과 `(없는 항목)` | 그 항목 기준으로 다시 그린다 |
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
- 다이얼로그 폭은 `720px`. 넓히면 칩 사이가 벌어져 행이 헐거워진다
- **이 항목 칩(3.1)은 채우지 않는다.** 흰 바탕에 1.5px 진한 테두리다. 자리 표시는 행 배경과 왼쪽 라벨이 이미 하고 있어 칩까지 채우면 강조가 셋이 된다
- 현재 단계 행은 왼쪽 라벨까지 주의색이다. 행 배경만으로는 훑을 때 놓친다
- 칩 안 항목 ID에서 프로젝트 코드 접두는 뺀다. 같은 프로젝트 안이고 칩은 좁다 — 전체 ID는 제목(1.1)에 있다

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
  <div class="dhead"><span>싱크독 사용 방법</span><span class="grow"></span><span class="x" data-el="4">✕</span></div>
  <div class="dbody">
    <p class="dlead">개발자가 PM 없이 11단계 명세 체인을 쓰고, 에이전트가 그 명세를 따르게 하는 플랫폼입니다. 쓰는 것은 에이전트, 판단하고 확정하는 것은 웹입니다.</p>

    <table class="grid" data-el="2">
      <tr class="hd"><th></th><th></th><th></th><th>어디서</th></tr>
      <tr data-el="2.1"><td class="no">1</td><td>저장소를 등록한다</td><td>명세 원본은 저장소의 docs/specs/에 둔다. 프로젝트 하나가 저장소 하나다.</td><td class="where">프로젝트 목록</td></tr>
      <tr><td class="no">2</td><td>에이전트를 붙인다</td><td>설정에서 MCP 토큰을 발급해 Claude Code·Codex·Gemini에 넣는다. 클라이언트는 상관없다.</td><td class="where">설정</td></tr>
      <tr><td class="no">3</td><td>에이전트와 대화하며 명세를 쓴다</td><td>명세 본문이 들어오는 길은 MCP와 GitHub push 둘뿐이다. 웹에는 편집 화면이 없다. <b>커밋·PR에 에이전트 표시(Co-Authored-By 등)를 남기지 않는다.</b></td><td class="where">에이전트</td></tr>
      <tr><td class="no">4</td><td>웹에서 읽고 완료로 올린다</td><td>유저용 탭으로 읽고, 참조를 따라가고, 막히면 그 자리에서 묻고, 다 됐으면 완료로 올린다. 완료 문서를 고치면 초안으로 돌아온다.</td><td class="where">문서 뷰</td></tr>
      <tr><td class="no">5</td><td>끊어진 것을 잡는다</td><td>상위 항목이 사라지면 그것을 가리키던 참조가 끊어진 참조로 뜬다. 알림은 없다 — 프로젝트 상세의 수치가 알림이다.</td><td class="where">프로젝트 상세</td></tr>
      <tr><td class="no">6</td><td>수정은 다시 에이전트에게</td><td>어긋남이 보이면 화면 밖에서 에이전트에게 고치게 하고 돌아와 확인한다.</td><td class="where">에이전트</td></tr>
    </table>

    <h4 class="sectitle">에이전트를 붙이는 법</h4>
    <table class="grid" data-el="6"><!-- 2의 둘째 단계를 손 순서로 편 것. 머리 행 없음 -->
      <tr data-el="6.1"><td class="no">1</td><td>토큰을 발급한다</td><td>설정 → MCP 토큰 → 발급. 이름을 적는다. 원문은 그때 한 번만 보이니 바로 복사한다.</td><td class="where">설정</td></tr>
      <tr><td class="no">2</td><td>터미널에서 한 줄</td><td>아래 명령. <code>--scope user</code>면 어느 폴더에서 켜도 붙는다. Codex·Gemini CLI는 설정의 클라이언트 설정 JSON을 각자 설정 파일에 넣는다.</td><td class="where">터미널</td></tr>
      <tr><td class="no">3</td><td>Claude Code를 새로 켠다</td><td>MCP 서버는 세션이 시작될 때 읽힌다. 켜져 있던 창에는 방금 넣은 서버가 안 보인다 — 나갔다가 다시 켠다.</td><td class="where">터미널</td></tr>
      <tr><td class="no">4</td><td>붙었는지 본다</td><td><code>claude mcp list</code>에 <code>syncdoc … ✔ Connected</code>, 또는 세션 안에서 <code>/mcp</code>. claude.ai 커넥터 목록에는 안 나온다 — 이 컴퓨터 설정에만 있는 것이 정상이다.</td><td class="where">터미널</td></tr>
    </table>
    <figure data-el="6.4"><img src="/howto/token-issued.png" alt="발급 직후 — 토큰 원문이 한 번만 보이는 화면"><figcaption>1. 발급 직후. 원문은 이 화면에서 한 번만 보인다 (캡처에서는 가렸다)</figcaption></figure>
    <pre class="snippet" data-el="6.2">claude mcp add --transport http --scope user syncdoc \
    https://{이 화면의 주소}/mcp \
    --header "Authorization: Bearer syncdoc_pat_…"</pre>
    <figure data-el="6.5"><img src="/howto/term-add.png" alt="터미널 — claude mcp add 실행 결과"><figcaption>2. 붙이면 이렇게 답한다. 토큰은 [REDACTED]로 가려진다</figcaption></figure>
    <figure data-el="6.6"><img src="/howto/term-list.png" alt="터미널 — claude mcp list에 syncdoc Connected"><figcaption>4. 새로 켠 뒤 <code>claude mcp list</code> — 이 줄이 보이면 붙은 것이다</figcaption></figure>
    <p class="note" data-el="6.3">그 뒤로는 에이전트에게 「싱크독으로 프로젝트 하나 만들어 줘」라고 말하면 된다. 주소가 바뀌면 <code>claude mcp remove syncdoc</code> 후 다시 넣는다.</p>

    <h4 class="sectitle">11단계가 뜻하는 것</h4>
    <table class="grid" data-el="3"><!-- 머리 행 없음. 위 소제목이 그 일을 한다 -->
      <tr data-el="3.1"><td class="no">1</td><td class="code">RFQ</td><td><b>요구·인터뷰</b> — 무엇을 왜 만드나. 고객이 말한 것만 적는다<div class="sub" data-el="3.5"><span class="cnt">문서 1</span> 고객이 말한 것 → Q 항목</div></td><td class="ids">Q1</td></tr>
      <tr><td class="no">2</td><td class="code">PRD</td><td><b>제품 요구</b> — 목표·비목표·요구사항. 요구에는 인수기준까지<div class="sub"><span class="cnt">문서 1</span> 목표 G · 요구 R · 비목표 N</div></td><td class="ids">G1 · R12 · N3</td></tr>
      <tr><td class="no">6</td><td class="code">DOM</td><td><b>도메인·클래스·데이터</b> — 도메인 모델·클래스 명세·ERD를 한 단계에<div class="sub"><span class="cnt">문서 3</span> 같은 것을 세 층으로. 이름으로 서로 참조한다 — <b>한 번에 쓰지 않는다</b><ul class="docs"><li><b>도메인 모델</b> — 개념 <code>Document</code> · 여기서</li><li><b>클래스 명세</b> — 클래스 <code>Document</code> · <b>8 API 뒤에</b> 돌아와서</li><li><b>ERD·DD</b> — 테이블 <code>documents</code> · 클래스 명세 뒤에</li></ul></div></td><td class="ids">Document · documents</td></tr>
      <tr><td class="no">7</td><td class="code">UI</td><td><b>화면</b> — 화면 목록·흐름·화면별 요소<div class="sub"><span class="cnt">문서 2</span> 무엇이 있나 / 어떻게 생겼나<ul class="docs"><li><b>화면 설계</b> — 목록·흐름 <code>UI-5</code></li><li><b>와이어프레임</b> — 같은 <code>UI-5</code>의 배치·요소·규칙. 배치는 <b>디자인 도구 산출물을 그대로</b>(스타일까지 든 자기 완결 html) <span class="tag">선택</span></li></ul></div></td><td class="ids">UI-5</td></tr>
      <tr><td class="no">8</td><td class="code">API</td><td><b>인터페이스</b> — REST 엔드포인트와 MCP 도구<div class="sub"><span class="cnt">문서 2</span> 입구가 둘<ul class="docs"><li><b>REST</b> — 사람·화면이 부른다 <code>GET/api/…</code></li><li><b>MCP</b> — 에이전트가 부른다 <code>get_document</code></li></ul></div></td><td class="ids">GET/api/docs/{docId} · get_doc</td></tr>
      <tr><td class="no">10</td><td class="code">MS</td><td><b>MINISPEC</b> — 함수 하나하나의 시그니처와 처리 순서<div class="sub"><span class="cnt">문서 N</span> MS 하나 = 클래스 명세 절 하나 = 코드 파일 하나 (싱크독 9개) <span class="tag">선택</span></div></td><td class="ids">SpecService.save</td></tr>
      <tr class="std" data-el="3.2"><td class="no">—</td><td class="code">STD</td><td><b>표준 (단계 밖)</b> — 명세가 아니라 명세를 쓰는 법. 싱크독 프로젝트에만 있다</td><td class="ids">규칙 항목</td></tr>
    </table>

    <p class="lbl" data-el="3.3">오른쪽은 그 단계 문서 안에서 쓰는 항목 ID 형식. 문서 ID는 <code>{프로젝트코드}-{타입}-{번호}</code>, 항목 ID는 <code>{문서ID}#{항목번호}</code>, 참조는 <code>[[항목ID]]</code>.</p>
    <p class="note" data-el="3.4">11단계 순서는 권장이지 강제가 아니다. 건너뛰어도 막지 않고 표시만 한다 — DOM 셋의 순서만 예외다(클래스 명세는 API 뒤, ERD는 클래스 명세 뒤). <b>여섯(RFQ·PRD·UC·DOM·API·CODE)이 실질이고 나머지는 규모가 정한다</b> — 가르는 것은 사람 수가 아니라 「머리에 안 들어가는가」다. 빈 단계는 「미작성」으로 남아 건너뛰었다는 사실이 보인다.</p>
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
| 3.4 | 주의 | 텍스트 | 11단계 순서는 강제가 아니라는 안내와, 그 예외 하나(DOM 셋의 순서 — [[SYNC-STD-001]] 2.6), 여섯(RFQ·PRD·UC·DOM·API·CODE)이 실질이고 나머지는 규모가 정한다는 것([[SYNC-STD-003]] 결정) | — |
| 3.5 | 문서 구성 | 텍스트 | 단계 행 안 둘째 줄. **문서 수 라벨**(`문서 3`) + 이유 한 줄 + 문서가 여럿이면 **줄마다 하나**(이름 — 항목 예) + 선택이면 **「선택」 태그**. DOM은 개념→클래스→테이블 세 층이라 셋 — **순서가 있어 줄마다 언제 쓰는지도 적는다**(도메인 모델은 여기서, 클래스 명세는 API 뒤에, ERD는 그 뒤 — [[SYNC-STD-001]] 2.6), UI는 무엇이 있나/어떻게 생겼나라 둘, API는 입구가 둘이라 둘, MS는 코드 파일마다 하나 | — |
| 4 | 닫기(✕) | 버튼 | | 닫힘 |
| 5 | 닫기 | 버튼 | | 닫힘 |
| 6 | 붙이는 법 표 | 표 | 토큰 → 명령 → 새 세션 → 확인. 2의 둘째 단계를 손 순서로 편 것 | — |
| 6.1 | 붙이는 행 | 행 | 한 단계 | — |
| 6.2 | 명령 | 코드 상자 | `claude mcp add …` 한 줄. **주소는 이 화면의 주소로 채워져 있다.** 토큰만 자리표시 | — |
| 6.3 | 그 다음 | 텍스트 | 붙은 뒤 첫마디와, 주소가 바뀌었을 때 하는 일 | — |
| 6.4 | 발급 순간 그림 | 그림 | 토큰 원문이 한 번만 보이는 화면. 원문은 가려져 있다 | — |
| 6.5 | 터미널 그림 (add) | 그림 | `claude mcp add`가 답하는 모양. 주소는 자리표시 | — |
| 6.6 | 터미널 그림 (list) | 그림 | `claude mcp list`의 `syncdoc … ✔ Connected` 한 줄 | — |

### 규칙

- 이 화면은 **읽기 전용이고 상태가 없다.** 어디서 열든 같은 내용이고, 닫으면 원래 화면 그대로다
- 항목 ID 형식은 [[SYNC-STD-001]] 2장의 타입별 패턴을 사람 말로 옮긴 것이다. 규약이 바뀌면 여기도 바뀐다
- **화면 단계의 안내는 「디자인 도구 산출물을 그대로」다.** 회색 상자 뼈대를 가르치지 않는다 — 에이전트가 가진 디자인 도구로 만든 자기 완결 html을 그대로 넣는다([[SYNC-STD-001]] 2.7, 카드 Z)
- **사용 순서 3행에 커밋 표시 규약을 적는다.** GitHub에 올리는 커밋·PR에 에이전트 표시(Co-Authored-By·세션 링크·Generated with)를 남기지 않는다 — 작성자는 사람의 계정이다([[SYNC-STD-001]] 1장)
- **"순서는 강제가 아니다"를 빼지 않는다.** 11단계를 보면 차례로 다 채워야 하는 것처럼 읽힌다. 실제로는 건너뛴 단계를 표시만 하고 막지 않는다([[SYNC-UC-001#UC-H14]] 1b)
- 본문 맨 위 문단이 이 도구가 무엇인지 한 번에 말한다. 표만 있으면 처음 온 사람이 무엇을 읽고 있는지 모른다
- 두 표 사이에 소제목 `11단계가 뜻하는 것`을 둔다. 두 번째 표에는 머리 행이 없다 — 소제목이 그 일을 한다
- 설명은 문장으로 쓴다. 키워드 단문으로 줄이면 행이 얇아져 표가 목록처럼 읽힌다
- **단계마다 문서 구성(3.5)을 둘째 줄로 붙인다.** 표만 보면 DOM이 왜 셋이고 UI·API가 왜 둘인지 모른다 — 실제로 목록 화면에서 `SYNC-DOM-001·002·003`을 보고 물었다. 근거는 [[SYNC-STD-001]] 2장의 서브타입이고, 실질/선택은 [[SYNC-STD-003]] 결정을 그대로 옮긴다
- **둘째 줄을 줄글로 쓰지 않는다.** 처음엔 한 문단으로 썼더니 660px 안에서 세 줄로 접혀 읽히지 않았다 — 수는 라벨(`문서 3`), 문서는 줄마다 하나(이름 — 항목 예), 선택은 태그. 첫 줄의 이름을 가리지 않게 본문보다 한 단계 작고 흐리되, 라벨과 문서 이름은 본문 잉크로 세운다
- 항목 ID는 고정폭 평문이다. 칩으로 그리면 표에 색 상자가 열한 줄 생겨 단계 이름보다 먼저 눈에 든다
- 다이얼로그 폭은 `660px`
- **명령(6.2)의 주소는 채워서 보여준다.** UI-13 클라이언트 설정(8.1)과 같은 원천 — 지금 열려 있는 화면의 origin — 을 쓴다. `{주소}`를 사람이 바꿔 넣게 두면 터널 주소를 옮겨 적다가 틀린다. 토큰은 발급 화면에서 한 번만 보이는 값이라 여기 채울 수 없고, 자리표시로 둔다
- **그림(6.4~6.6)은 앱 밖 화면만이다.** 토큰이 한 번만 보이는 순간과 터미널 둘 — 앱 안에서 볼 수 없는 것이다. 앱 화면은 캡처로 넣지 않는다 — 한 클릭 거리고, 화면이 바뀌면 캡처가 낡는다. 터미널 그림의 주소는 `{싱크독 주소}` 자리표시다 — 실제 주소는 6.2가 채운다. 파일은 `frontend/public/howto/`, 경로 `/howto/*.png`
- **「새로 켠다」(6 셋째 행)를 빼지 않는다.** 실제로 붙이는 사람이 가장 먼저 걸리는 자리다 — 켜져 있던 세션에 서버가 안 보여서 잘못 넣은 줄 안다. 설명서가 앱 밖에 있으면 이 한 줄을 못 보고, 그래서 앱 안에 둔다

### 시나리오

**S-1 처음 들어온 사람**
1. 상단 바에서 `사용 방법`을 누른다
2. 여섯 단계를 읽고 "웹에는 편집이 없다"는 것을 안다
3. 11단계 표에서 자기 프로젝트가 어느 단계까지 와 있는지 가늠한다

**S-2 항목 ID 형식이 기억 안 난다**
1. 다이얼로그를 열어 11단계 표(3)에서 그 타입의 항목 ID 형식을 본다
2. 닫으면 보던 화면 그대로다

**S-3 다른 컴퓨터에서 에이전트를 붙인다**
1. 그 컴퓨터의 브라우저로 로그인하고 `사용 방법`을 연다
2. 붙이는 법 표(6)를 따라 토큰을 발급하고 명령(6.2)을 복사해 터미널에 붙인다 — 주소가 이미 채워져 있다
3. Claude Code를 새로 켜고 `/mcp`로 확인한다

---

## 미결사항

- [x] UI 문서의 필수 절이 `미결사항` 하나가 되면서(카드 X, [[SYNC-STD-001]] 2.7) 이 문서에도 절이 생겼다. 열린 것은 없다 — 화면별 미결은 [[SYNC-UI-001]] 7장 판단 지점에 있다
- [x] 공통 틀 `<style>`의 뒤쪽(앱 CSS에서 옮긴 100여 클래스)은 12화면을 디자인 도구로 다시 그리면(카드 AA) 줄어든다. 그때 정리한다
