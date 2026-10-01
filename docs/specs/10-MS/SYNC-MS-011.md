---
doc_id: SYNC-MS-011
type: MS
title: MINISPEC — codegraph — 코드 호출 그래프와 명세 대조
status: draft
upstream: [SYNC-DOM-002, SYNC-DOM-003, SYNC-SEQ-001, SYNC-STD-001]
---

# MINISPEC — codegraph — 코드 호출 그래프와 명세 대조

## 0. 이 문서가 다루는 것

`core/codegraph/graph.py`(순수 함수 6개)와 `core/codegraph/service.py`(`CodeGraphService` 5개). 클래스 명세 [[SYNC-DOM-002]] 4.11의 시그니처를 함수 내부까지 내린 것.

명세↔코드 대조([[SYNC-PRD-001#R13]])를 맡는다 — 2026-09-30 사용자 결정으로 graphify가 뽑은 호출 그래프에 싱크독의 보강을 더해, MINISPEC의 「호출하는 것」과 실제 호출을 가른다. **명세 묶음과 선이 없다**: 항목 ID는 그래프 안의 글자이고, 「호출하는 것」은 부르는 쪽(검사기 `check_calls`, 화면·챗봇은 카드 AY·AZ의 `queries`)이 명세에서 읽어 넘긴다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입 `CallDiff`는 [[SYNC-DOM-002]] 2.8에 있다.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `·` 같은 단계 안 구분.

**두 파일로 나눈 이유.** `graph.py`는 DB를 모른다 — 검사기가 DB 없이 같은 함수를 부른다(결과가 웹과 같아야 한다). `service.py`는 `code_graphs` 한 행을 읽고 쓰는 것만 한다.

**그래프 모양** — `code_graphs.graph`(JSONB)에 그대로 들어가는 것.

| 키 | 모양 | 뜻 |
|---|---|---|
| `functions` | `[{key, name, qual, file, line, end, ms, community}]` | 저장소 안에 정의된 함수·메서드. `key`는 `파일:줄`. `qual`은 `Class.fn` 또는 `모듈.fn`. `end`는 끝 줄(모르면 null). `ms`는 docstring 첫 줄의 항목 ID(없으면 null). `community`는 든 커뮤니티 번호(없으면 null — 카드 BD) |
| `calls` | `[[from_key, to_key, via]]` | 호출 선. `via`는 `graphify`(graphify가 찾은 것) 또는 `enrich`(싱크독이 보강한 것) |
| `communities` | `[{id, label, size}]` | 함수가 하나라도 든 커뮤니티(카드 BD). `id`는 graphify `cluster`의 번호(0이 가장 큼), `label`은 허브 노드 이름, `size`는 든 함수 수. **2026-10-01 이전 그래프에는 없다** — 읽는 쪽이 빈 것으로 본다 |

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#codegraph.touches_code]] | 바뀐 경로에 코드 파일이 있나 |
| [[#codegraph.load]] | 저장소의 graph.json이 있으면 그것, 없으면 graphify로 추출 |
| [[#codegraph.reduce]] | 함수·호출 선만 남긴다 |
| [[#codegraph.enrich]] | 파이썬 코드로 타입을 풀어 호출을 보강한다 |
| [[#codegraph.communities]] | 함수를 graphify 군집으로 묶는다 |
| [[#codegraph.spec_calls]] | 명세의 「호출하는 것」을 항목 ID 집합으로 |
| [[#codegraph.compare]] | 명세 호출과 코드 호출을 같음·코드만·명세만으로 |
| [[#CodeGraphService.get]] | 프로젝트의 그래프 행 |
| [[#CodeGraphService.save]] | 새 그래프로 바꿔 끼운다 |
| [[#CodeGraphService.fail]] | 실패 이유만 남긴다 — 옛 그래프는 그대로 |
| [[#CodeGraphService.delete_by_project]] | 프로젝트 해제와 함께 |
| [[#CodeGraphService.read]] | 그래프 커밋의 파일을 줄 범위로 — 비밀 꼴 거부, 300줄 |

---

## 2. 함수

#### codegraph.touches_code 바뀐 경로에 코드 파일이 있나

**시그니처** `def touches_code(paths: list[str]) -> bool`

근거: [[SYNC-UC-001#UC-S8]] 확장 1a

**처리** 경로 하나라도 확장자가 `CODE_EXTS`(graphify가 읽는 코드 — `.py .ts .tsx .js .jsx .mjs .go .rs .java .kt .scala .rb .php .cs .c .h .cpp .hpp .swift .lua .ex .exs .jl .sh .sql .vue .svelte`)에 들면 `True`. `docs/specs/` 아래와 `graphify-out/` 아래는 코드가 아니다 — 명세만 바꾼 커밋이 그래프를 다시 만들지 않게

**테스트 관점** 명세 md만 → False · `.py` 하나 → True · `docs/specs/assets/x.js` → False · `graphify-out/graph.json` → False

---

#### codegraph.load 저장소의 graph.json 또는 graphify 추출

**시그니처** `async def load(src_dir: Path) -> tuple[str, dict]`

근거: [[SYNC-UC-001#UC-S8]] 기본 흐름 2 · 사용자 결정 2026-09-30 — 저장소에 있으면 그것, 없으면 서버가

**입력** `src_dir` 한 커밋을 푼 폴더(서버는 `git archive`, 검사기는 작업 트리 사본)

**처리**
1. if `src_dir/graphify-out/graph.json`이 있다 → `("repo", json.load(그 파일))` — 개발자가 graphify 원래 방식으로 만들어 커밋한 것
2. else → `("server", `[[SYNC-MS-009#graphify.extract]]`(src_dir))`

**출력** `(출처, graphify의 graph.json 원형)`

**예외** 저장소의 graph.json이 JSON이 아니면 `! CodeGraphFailed("graph.json 형식")` · 추출 실패는 `graphify.extract`의 것

**호출하는 것** [[SYNC-MS-009#graphify.extract]]

**테스트 관점** graph.json이 있으면 graphify를 부르지 않고 `repo` · 없으면 `server`이고 함수 노드가 있다 · 깨진 graph.json → `CodeGraphFailed`

---

#### codegraph.reduce 함수·호출 선만 남긴다

**시그니처** `def reduce(raw: dict) -> dict`

근거: 사용자 결정 2026-09-30 — DB에 줄인 모양으로(싱크독 저장소 4.6 MB → 454 KB)

**처리**
1. 함수 = `_callable`이 참이고 `_callable_class`가 아닌 노드. `file` = `source_file`, `line` = `source_location`의 `L` 뒤 숫자, `key` = `f"{file}:{line}"`, `name` = `label`에서 앞 `.`과 뒤 `()`를 뗀 것
2. `qual` — 메서드면 `method` 선으로 매단 클래스 노드의 이름을 붙여 `Class.fn`, 아니면 `모듈.fn`. 모듈 이름은 파일 이름에서 확장자를 뗀 것이고, 그것이 `service`·`__init__`·`index`면 **그 폴더 이름** — `core/codegraph/service.py`의 함수는 `codegraph.x`
3. `ms` — `rationale_for` 선으로 붙은 docstring 노드의 라벨이 `^[A-Z][A-Z0-9]*-MS-\d+#[\w.]+`로 시작하면 그 ID. 아니면 null
4. `calls` = `calls`·`indirect_call` 선 중 양 끝이 1의 함수인 것 → `[from_key, to_key, "graphify"]`. 같은 쌍은 하나로
5. import·포함·문서 링크·docstring·개념 노드는 버린다. 군집은 [[#codegraph.communities]]가 raw 그래프에서 따로 계산해 붙인다(카드 BD) — 여기서는 `community`를 두지 않는다
6. `→ {"functions": [...], "calls": [...]}` (`end`는 null로 둔다 — 파이썬은 `enrich`가 채운다)

**테스트 관점** 클래스 노드·import 선이 빠진다 · 메서드는 `Class.fn`, `service.py`의 함수는 폴더 이름 · docstring ID가 `ms`로 · 같은 호출 둘 → 하나

---

#### codegraph.enrich 파이썬 코드로 호출을 보강한다

**시그니처** `def enrich(src_dir: Path, graph: dict) -> dict`

근거: 사용자 결정 2026-09-30 — graphify는 변수의 타입을 추론하지 않아 `spec = SpecService(s); spec.get_document()`를 못 잡는다(실측: 명세만 58건 중 대부분). 싱크독이 보강해 푼다

**입력** `graph` — `reduce`의 결과. `src_dir` — 같은 커밋의 파일

**처리** — `graph.functions` 중 `.py` 파일만. 다른 언어는 손대지 않는다
1. 파일마다 `ast.parse`. 함수 정의를 `(파일, def 줄)`과 `(파일, 첫 데코레이터 줄)` 둘로 찾아 그래프의 함수에 맞춘다(graphify가 어느 줄을 머리로 삼든 맞는다). 못 맞춘 정의는 새 함수로 더한다
2. 맞춘 함수마다 `end` = `end_lineno` · `qual` = AST로 본 `Class.fn`/`모듈.fn`(2단계 규칙과 같다) · docstring 첫 줄이 항목 ID면 `ms`를 그것으로(AST가 진실)
3. 함수 몸통에서 **타입을 아는 변수**를 모은다 — 인자 주석 `x: Cls` · `x = Cls(…)` · `a, b = A(…), B(…)`. `Cls`는 이 그래프 안에 정의된 클래스 이름일 때만
4. 호출 `x.m(…)`(3의 변수) · `Cls(…).m(…)` · `self.m(…)`(메서드 안) → `Cls.m`이 그래프에 있으면 `[이 함수, 그 함수, "enrich"]`. 이미 있는 선이면 더하지 않는다
5. `→ graph` (같은 객체에 더해 돌려준다)

**테스트 관점** 다섯 꼴이 각각 선을 만든다 — 주석·대입·튜플 대입·즉석 생성·`self` · 모르는 클래스는 안 만든다 · graphify가 이미 잡은 선은 겹치지 않는다 · 데코레이터 달린 함수도 맞춘다 · docstring ID가 `ms`로

---

#### codegraph.communities 함수를 graphify 군집으로 묶는다

**시그니처** `def communities(raw: dict, graph: dict) -> dict`

근거: [[SYNC-UC-001#UC-S8]] 기본 흐름 3 · UI-17 · 사용자 결정 2026-10-01(그래프를 만들 때 서버가 군집한다 — raw 그래프에는 파일·클래스·호출 선이 다 들어 함수가 제 파일·클래스와 같이 묶인다 · Louvain seed 42, 모델·네트워크 없음 · 한 번)

**입력** `raw` — `load`가 준 원형 · `graph` — `enrich`까지 끝난 그래프(같은 객체에 더해 돌려준다)

**처리**
1. `G = graphify.paths.load_node_link_graph(raw)` · if 노드 0 → 모든 함수 `community = None`, `communities = []` → 6
2. `C = graphify.cluster.cluster(G)` · `labels = graphify.cluster.label_communities_by_hub(G, C)` — graspologic이 없으면 networkx Louvain(seed 42)이라 결정적. **예외는 삼키고** 1의 빈 결과 + `log.warning` — 군집이 안 돼도 그래프는 남는다
3. 노드 → 커뮤니티 사상에서 **key → 커뮤니티**(`key`는 `reduce`와 같은 규칙 — `source_file` + `source_location`의 `L` 뒤 숫자)와 **파일 → 커뮤니티**(그 파일 노드들의 다수 커뮤니티, 동률이면 작은 번호)
4. 함수마다 `community` = key의 것 · 없으면(enrich가 더한 정의) 파일의 것 · 그것도 없으면 None
5. `communities = [{id, label: labels[id](끝 "()" 뗌), size: 든 함수 수}]` — 함수가 0인 군집(테스트·문서 노드만 든 것)은 뺀다. `size` 내림차순, 같으면 `id`
6. `→ graph`

**호출하는 것** 없음 (graphify 라이브러리 — MINISPEC 밖)

**호출되는 것** [[SYNC-MS-007#pipeline.build_code_graph]] 3 — `enrich` 뒤. 검사기(`check_calls`)는 부르지 않는다 — 대조에 군집이 필요 없다

**테스트 관점** contains·method 선으로 이어진 파일 둘 → 함수가 파일별로 갈린다 · 라벨이 허브 이름이고 `()`가 없다 · `size` = 함수 수이고 함수 없는 군집은 없다 · enrich가 더한 함수는 파일로 받는다 · 같은 raw 두 번 → 같은 결과 · 노드 없는 raw → 빈 목록·None

---

#### codegraph.spec_calls 명세의 「호출하는 것」

**시그니처** `def spec_calls(items: list[tuple[str, str]]) -> dict[str, set[str]]`

근거: 사용자 결정 2026-09-30 — 명세의 호출은 「호출하는 것」 줄만 읽는다(처리 단계 글은 부르는 쪽까지 섞여 기준이 못 된다) · [[SYNC-STD-001]] 2.10

**입력** `items` — MINISPEC 항목마다 `(항목 ID, 블록 본문)`. 프로젝트의 MS 문서 전부

**처리**
1. 이름표 = 항목 ID마다 `#` 뒤(`pipeline.save_pipeline`) → 항목 ID. 이름이 겹치면 그 이름은 이름표에서 뺀다(모호하다)
2. 항목마다 본문에서 `**호출하는 것**`으로 시작하는 줄을 찾는다. 없으면 빈 집합
3. 그 줄의 `[[문서#항목]]`(같은 문서 줄임 `[[#항목]]`은 그 항목의 문서로 푼다)과 백틱 이름(`` `git.fetch` ``, 괄호 앞까지)을 이름표·항목 ID 집합에 비춰 **MINISPEC 항목인 것만** 남긴다. 자기 자신은 뺀다
4. `→ {항목 ID: 집합}` — 모든 항목이 키로 있다

**테스트 관점** `[[#x]]`가 같은 문서로 풀린다 · 백틱 이름이 항목이면 들어가고 아니면(`exists` 같은 말) 빠진다 · 줄이 없는 항목은 빈 집합 · 겹치는 짧은 이름은 안 쓴다

---

#### codegraph.compare 명세 호출과 코드 호출을 가른다

**시그니처** `def compare(graph: dict, spec: dict[str, set[str]]) -> list[CallDiff]`

근거: [[SYNC-PRD-001#R13]] · [[SYNC-STD-004#DEV-14]] · 사용자 결정 2026-09-30 — 「호출하는 것」은 실제로 부르는 다른 MINISPEC 항목 전부(비공개 도우미를 건너 닿는 것까지)

**처리**
1. 함수 ↔ 항목 — `ms`가 있으면 그것. 없으면 `qual`이 어느 항목 이름(`#` 뒤)과 같을 때 그 항목(docstring 규약이 없는 프로젝트, 사용자 결정 「ID 먼저, 없으면 이름」)
2. `spec`의 항목마다: 함수가 없으면 `CallDiff(ms_id, function=None, …)` — 존재는 `check_code`가 본다
3. 코드 호출 = 그 함수에서 `calls`를 따라가며 **항목이 없는 함수(도우미)는 건너 계속**, 항목이 있는 함수에 닿으면 그 항목을 모으고 멈춘다. 방문 표시로 사이클을 멈춘다. 자기 자신은 뺀다
4. `same = 명세 ∩ 코드` · `code_only = 코드 − 명세` · `spec_only = 명세 − 코드` — 전부 정렬
5. `→ [CallDiff]` 항목 ID 순

**테스트 관점** 도우미를 건너 닿은 호출이 코드 호출에 든다 · 항목이 있는 함수 너머는 안 간다 · 사이클에서 멈춘다 · docstring 없는 함수가 이름으로 이어진다 · 함수 없는 항목은 `function=None`

---

#### CodeGraphService.get 프로젝트의 그래프 행

**시그니처** `def get(project_id: int) -> CodeGraph | None`

**처리** `DB: code_graphs where project_id` → 행 또는 None. 소유 검사는 부르는 쪽(`queries`, 카드 AY)이 프로젝트를 열 때 이미 했다

**테스트 관점** 없으면 None

---

#### CodeGraphService.save 새 그래프로 바꿔 끼운다

**시그니처** `def save(project_id: int, commit_hash: str, source: str, graph: dict) -> CodeGraph`

근거: [[SYNC-UC-001#UC-S8]] 기본 흐름 4 · 사용자 결정 2026-09-30 — 프로젝트마다 최신 하나

**처리** 행이 없으면 만들고, 있으면 `commit_hash`·`source`·`graph`·`function_count = len(functions)`·`call_count = len(calls)`·`built_at = clock.now()`를 **한 번에** 바꾸고 `error = None`. 옛 그래프는 남기지 않는다 · `→ 행`

**테스트 관점** 두 번 저장하면 행 하나, 뒤의 것 · 앞의 `error`가 지워진다 · 개수 열이 맞다

---

#### CodeGraphService.fail 실패 이유만 남긴다

**시그니처** `def fail(project_id: int, commit_hash: str, reason: str) -> CodeGraph`

근거: [[SYNC-UC-001#UC-S8]] 확장 2a

**처리** 행이 있으면 **그래프·커밋·출처는 그대로** 두고 `error = f"{commit_hash[:7]}: {reason}"[:300]`. 없으면 빈 그래프(`functions`·`calls` 빈 목록)에 `commit_hash`·`source` null로 행을 만들고 `error`를 쓴다 · `→ 행`

**테스트 관점** 성공 뒤 실패 → 옛 그래프가 남고 `error`만 · 첫 빌드부터 실패 → 빈 그래프 + `error` · 300자에서 자른다

---

#### CodeGraphService.delete_by_project 프로젝트 해제와 함께

**시그니처** `def delete_by_project(project_id: int) -> None`

**처리** `DB: code_graphs where project_id` 삭제 — [[SYNC-MS-001#ProjectService.delete_project]]가 명세 표보다 먼저 같은 트랜잭션에서 부른다

**테스트 관점** 해제 뒤 행 0

---

#### CodeGraphService.read 그래프 커밋의 파일을 줄 범위로

**시그니처** `async def read(project_id: int, workdir: Path, path: str, start: int, end: int | None) -> CodeText`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 3 · 사용자 결정 2026-09-30(코드 본문은 DB에 두지 않고 그래프 커밋의 저장소에서 · 커밋된 파일만 · 비밀 꼴 거부 · 300줄) — 코드 탭(카드 AY)과 질문 탭 `read_code`(카드 AZ)가 같이 쓴다

**처리**
1. `row = get(project_id)` · if None 또는 `row.commit_hash` None → `! not-found {resource: code_graph}`
2. `path`를 저장소 안 상대 경로로 — 절대 경로·`..`는 `! not-found {resource: file}` · 파일 이름이 `DENY`(`.env*` · `*.pem` · `*.key` · `id_rsa*` · `*.p12` · `*secret*`)에 걸리면 **같은** `! not-found {resource: file}` — 있는지가 새지 않게
3. `text = `[[SYNC-MS-009#git.read]]`(workdir, path, row.commit_hash)` — **그래프 커밋의 커밋된 파일만**. 작업 사본·`.gitignore`된 파일은 못 본다 · 없으면 `! not-found {resource: file}`
4. `start = max(1, start)` · `end = min(줄 수, end or 줄 수)` · 300줄을 넘으면 `end = start + 299`, `truncated = True`
5. `→ CodeText(path, start, end, row.commit_hash, 그 줄들, truncated)`

**호출하는 것** [[#CodeGraphService.get]] · [[SYNC-MS-009#git.read]]

**테스트 관점** 그래프 커밋의 내용이다(뒤에 바뀐 것이 아니다) · 300줄에서 자르고 `truncated` · `.env`·`id_rsa`·`secrets.yaml`·`../x`·절대 경로 → `not-found` · 그래프 없음 → `not-found`

---

## 3. 미결사항

- [ ] 파이썬 밖(TS·Go…)의 보강 — 지금은 graphify 결과 그대로. 싱크독 코드는 MINISPEC 함수가 전부 파이썬이라 급하지 않다
