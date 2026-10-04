---
doc_id: SYNC-MS-011
type: MS
title: MINISPEC — codegraph — 코드 호출 그래프와 명세 대조
status: approved
upstream: [SYNC-DOM-002, SYNC-DOM-003, SYNC-SEQ-001, SYNC-STD-001]
---

# MINISPEC — codegraph — 코드 호출 그래프와 명세 대조

## 0. 이 문서가 다루는 것

`core/codegraph/graph.py`(순수 함수)와 `core/codegraph/service.py`(`CodeGraphService`) — 목록은 1장. 클래스 명세 [[SYNC-DOM-002]] 4.11의 시그니처를 함수 내부까지 내린 것.

명세↔코드 대조([[SYNC-PRD-001#R13]])를 맡는다 — 2026-09-30 사용자 결정으로 graphify가 뽑은 호출 그래프에 싱크독의 보강을 더해, MINISPEC의 「호출하는 것」과 실제 호출을 가른다. **명세 묶음과 선이 없다**: 항목 ID는 그래프 안의 글자이고, 「호출하는 것」은 부르는 쪽(검사기 `check_calls`, 화면·챗봇은 카드 AY·AZ의 `queries`)이 명세에서 읽어 넘긴다.

형식은 [[SYNC-STD-001]] 2.10 — 시그니처·근거·입력·처리·출력·예외·호출하는 것·테스트 관점, 분기는 `if 조건 → 결과`, 간략형 허용. 내부 타입 `CallDiff`는 [[SYNC-DOM-002]] 2.8에 있다.

**표기** — `→` 반환·결과, `!` 예외, `DB:` 테이블 접근, `·` 같은 단계 안 구분.

**두 파일로 나눈 이유.** `graph.py`는 DB를 모른다 — 검사기가 DB 없이 같은 함수를 부른다(결과가 웹과 같아야 한다). `service.py`는 `code_graphs` 한 행을 읽고 쓰는 것만 한다.

**그래프 모양** — `code_graphs.graph`(JSONB)에 그대로 들어가는 것.

| 키 | 모양 | 뜻 |
|---|---|---|
| `functions` | `[{key, name, qual, file, line, end, item, ms, community}]` | 저장소 안에 정의된 함수·메서드. `key`는 `파일:줄`. `qual`은 `Class.fn` 또는 `모듈.fn`. `end`는 끝 줄(파이썬·TS/JS는 `enrich`가 채운다, 다른 언어는 null). `item`은 이 함수가 속한 명세 항목 ID — docstring 첫 줄의 항목 ID(어느 문서든 — MINISPEC·API·UI…), 화면 코드(`.ts/.tsx/.js/.jsx`)는 파일 첫 주석의 화면 ID(없으면 null — 카드 BJ). `ms`는 그중 MINISPEC 항목일 때 같은 값(아니면 null) — 대조는 `ms`로만. `community`는 든 커뮤니티 번호(없으면 null — 카드 BD). **`item`은 2026-10-02 이전 그래프에 없다** — 읽는 쪽이 `ms`로 본다 |
| `calls` | `[[from_key, to_key, via]]` | 호출 선. `via`는 `graphify`(graphify가 찾은 것) 또는 `enrich`(싱크독이 보강한 것) |
| `communities` | `[{id, label, size}]` | 함수가 하나라도 든 커뮤니티(카드 BD). `id`는 Louvain 군집 번호(0이 가장 큼 — #253), `label`은 허브 노드 이름(그 커뮤니티의 함수를 품은 코드 노드 — 함수·그 파일·메서드가 든 클래스, 테스트가 아닌 것 — #255·#306·#308), `size`는 든 함수 수. **2026-10-01 이전 그래프에는 없다** — 읽는 쪽이 빈 것으로 본다 |

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#codegraph.touches_code]] | 바뀐 경로에 코드 파일이 있나 |
| [[#codegraph.load]] | 저장소의 graph.json이 있으면 그것, 없으면 graphify로 추출 |
| [[#codegraph.reduce]] | 함수·호출 선만 남긴다 |
| [[#codegraph.enrich]] | 파이썬 코드로 타입을 풀어 호출을 보강한다 |
| [[#codegraph.communities]] | 함수를 Louvain 군집으로 묶는다 |
| [[#codegraph.spec_calls]] | 명세의 「호출하는 것」을 항목 ID 집합으로 |
| [[#codegraph.compare]] | 명세 호출과 코드 호출을 같음·코드만·명세만으로 |
| [[#codegraph.item_function]] | 항목 ID → 그 항목의 함수(화면 항목은 파일 이름과 같은 컴포넌트) |
| [[#codegraph.item_neighbors]] | 함수의 부르는 것·불리는 곳을 항목 있는 함수까지 — 도우미·같은 항목은 건너 |
| [[#codegraph.layer_table]] | 클래스 명세 「폴더 구조」 절의 층 표를 읽는다 |
| [[#codegraph.layers]] | 항목 없는 함수마다 층 — 도우미 규칙, 표의 첫 일치 줄. 안 맞는 줄도 |
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
1. 함수 = `_callable`이 참이고 `_callable_class`가 아닌 노드. `file` = `source_file`, `line` = `source_location`의 `L` 뒤 숫자, `key` = `f"{file}:{line}"`, `name` = `label`에서 앞 `.`과 뒤 `()`를 뗀 것. **테스트 파일의 노드는 함수가 아니다** — 테스트는 구현이 아니라 대조에서 뺀다. 테스트 파일은 경로에 `tests/`·`test/`·`__tests__/` 단이 있거나, 이름이 `test_*.py`·`*_test.py`·`*.test.*`·`*.spec.*`(js·jsx·ts·tsx)·`conftest.py`인 것 — [[#codegraph.communities]]도 같은 판정
2. `qual` — 메서드면 `method` 선으로 매단 클래스 노드의 이름을 붙여 `Class.fn`, 아니면 `모듈.fn`. 모듈 이름은 파일 이름에서 확장자를 뗀 것이고, 그것이 `service`·`__init__`·`index`면 **그 폴더 이름** — `core/codegraph/service.py`의 함수는 `codegraph.x`
3. `item` — `rationale_for` 선으로 붙은 docstring 노드의 라벨이 `^[A-Z][A-Z0-9]*-[A-Z]+-\d+#\S+`로 시작하면 그 ID(공백 앞까지 — `SYNC-API-001#GET/api/docs/{docId} — 설명`에서 ` — ` 앞). 아니면 null. `ms` — `item`이 `-MS-` 문서의 항목이면 같은 값, 아니면 null(카드 BJ — 전에는 MINISPEC ID만 읽었다)
4. `calls` = `calls`·`indirect_call` 선 중 양 끝이 1의 함수인 것 → `[from_key, to_key, "graphify"]`. 같은 쌍은 하나로
5. import·포함·문서 링크·docstring·개념 노드는 버린다. 군집은 [[#codegraph.communities]]가 raw 그래프에서 따로 계산해 붙인다(카드 BD) — 여기서는 `community`를 두지 않는다
6. `→ {"functions": [...], "calls": [...], "files": [...]}` (`end`는 null로 둔다 — 파이썬은 `enrich`가 채운다). `files`는 graphify가 읽은 코드 파일 — `file_type == code`인 노드의 `source_file`, 테스트 파일 빼고 정렬. 함수가 하나도 없는 파일도 든다. `enrich`가 쓰고 지우므로 저장 모양(0장)에는 없다(#282)

**테스트 관점** 클래스 노드·import 선이 빠진다 · 테스트 파일의 함수가 빠진다 · 메서드는 `Class.fn`, `service.py`의 함수는 폴더 이름 · MINISPEC docstring ID가 `item`·`ms` 둘 다로 · API docstring ID(`#` 뒤에 `/`·`{}`)는 `item`에만, 설명은 잘린다 · 같은 호출 둘 → 하나

---

#### codegraph.enrich 파이썬·TS/JS 코드로 그래프를 보강한다

**시그니처** `def enrich(src_dir: Path, graph: dict) -> dict`

근거: 사용자 결정 2026-09-30 — graphify는 변수의 타입을 추론하지 않아 `spec = SpecService(s); spec.get_document()`를 못 잡는다(실측: 명세만 58건 중 대부분). 싱크독이 보강해 푼다 · 사용자 결정 2026-10-02(카드 BL) — graphify는 TS/JS 함수의 끝 줄을 하나도 안 준다(실측: 싱크독 프런트 201개 전부 null — `CodeGraph` 컴포넌트가 코드 보기에서 L58–L117로 잘렸다)와 객체 리터럴의 화살표 메서드(`api.get`)를 놓친다. 끝 줄 + 빠진 맨 위 함수 + 호출을 채운다. 중첩 함수는 맨 위만(파이썬과 같이) — graphify가 이미 넣은 중첩 함수는 지우지 않고 끝 줄만

**입력** `graph` — `reduce`의 결과. `src_dir` — 같은 커밋의 파일

**처리** — `graph.functions` 중 `.py` 파일(1·2·4·5)과 `.ts/.tsx/.js/.jsx/.mjs` 파일(2a~2d·3)만. TS/JS는 `graph.functions`의 파일에 더해 `reduce`가 준 `files`의 TS/JS도 읽는다 — graphify가 객체 리터럴 안 화살표만 든 파일(`export const api = { get: () => … }`)을 함수 0개로 놓쳐도 그 파일을 다시 읽는다(#282, 2026-10-02 사용자 결정 「graphify가 읽은 파일 전부」). `files`는 다 쓴 뒤 그래프에서 지운다. 다른 언어(Go 등)는 손대지 않는다. 보강은 **더하기만** 한다 — graphify가 준 함수·선을 지우지 않는다
1. 파일마다 `ast.parse`. 함수 정의를 `(파일, def 줄)`과 `(파일, 첫 데코레이터 줄)` 둘로 찾아 그래프의 함수에 맞춘다(graphify가 어느 줄을 머리로 삼든 맞는다). 못 맞춘 정의는 새 함수로 더한다
2. 맞춘 함수마다 `end` = `end_lineno` · `qual` = AST로 본 `Class.fn`/`모듈.fn`(2단계 규칙과 같다) · docstring 첫 줄이 항목 ID(`reduce` 3의 정규식)면 `item`을 그것으로, `-MS-` 문서면 `ms`도(AST가 진실)
2a. TS/JS — 파일마다 tree-sitter(`tree-sitter-typescript` — graphify가 이미 쓰는 문법. `.tsx`·`.jsx`는 TSX, 나머지는 TypeScript 문법)로 읽는다. **맨 위 정의**: `[export [default]] function f` · `const f = (…) => …` / `function` · `class C { m() }` → `C.m` · `const o = { m() {}, k: () => … }` → `o.m`·`o.k`. 머리 줄은 선언문의 첫 줄과 함수 노드의 첫 줄 둘로 그래프의 함수에 맞추고, 못 맞춘 정의는 새 함수로 더한다(`item`·`ms` null)
2b. 맞춘·더한 맨 위 함수마다 `end` = 선언문 끝 줄 · `qual` = `C.m`/`o.m` 또는 `모듈.f`(2단계의 모듈 규칙)
2c. 그래프에 있는데 `end`가 없는 TS/JS 함수(graphify가 넣은 중첩 함수 — 컴포넌트 안 핸들러)는 파일의 함수 노드(function·arrow·method) 중 같은 줄에서 시작하는 것의 끝 줄로 채운다
2d. 맨 위 정의의 몸통에서 호출 `f(…)` · `o.m(…)` · JSX `<Comp …>` → 같은 파일의 맨 위 이름, 또는 **상대 import**(`./x`·`../api/client` — 확장자 `.ts .tsx .js .jsx .mjs`나 폴더의 `index.*`로 파일을 찾는다. 별칭 `a as b`·default import도)한 파일의 맨 위 이름이 그래프에 있으면 `[이 함수, 그 함수, "enrich"]`. 이미 있는 선이면 더하지 않는다. 패키지 import(`react`)·경로 별칭은 풀지 않는다
3. 화면 코드 — 파일마다 **첫 주석**(맨 위 `/** … */` 또는 `//` 묶음)에서 `[A-Z][A-Z0-9]*-UI-\d{3}#UI-\d+`를 찾아, 그 파일 함수 중 `item`이 없는 것 전부에 준다(`ms`는 건드리지 않는다). 화면 하나 = 파일 하나(DEV-17)라 파일 단위로 잇는다. 첫 주석에 화면 ID가 없는 파일(공용 부품·뷰 렌더러)은 그대로 null. 2026-10-02 사용자 결정, 카드 BJ
4. 함수 몸통에서 **타입을 아는 변수**를 모은다 — 인자 주석 `x: Cls` · `x = Cls(…)` · `a, b = A(…), B(…)`. `Cls`는 이 그래프 안에 정의된 클래스 이름일 때만. 그리고 **타입을 아는 속성** — 클래스 `__init__`의 `self.x = Cls(…)`(또는 `self.x: Cls = …`)는 그 클래스 메서드 전부에서 `self.x`의 타입이다(카드 BM — 서비스가 리포지토리를 `self.repo`로 들고 부르는 134곳이 그래프에 없어 리포지토리 93개 중 89개가 외톨이였다)
5. 호출 `x.m(…)`(4의 변수) · `Cls(…).m(…)` · `self.m(…)`(메서드 안) · `self.x.m(…)`(4의 속성) → `Cls.m`이 그래프에 있으면 `[이 함수, 그 함수, "enrich"]`. 이미 있는 선이면 더하지 않는다
6. `→ graph` (같은 객체에 더해 돌려준다)

**테스트 관점** 다섯 꼴이 각각 선을 만든다 — 주석·대입·튜플 대입·즉석 생성·`self` · `__init__`의 `self.repo = Repo(…)` 뒤 다른 메서드의 `self.repo.get(…)` → `Repo.get` · 모르는 클래스는 안 만든다 · graphify가 이미 잡은 선은 겹치지 않는다 · 데코레이터 달린 함수도 맞춘다 · MINISPEC docstring ID가 `item`·`ms`로, API docstring ID는 `item`만 · `.tsx` 첫 주석의 화면 ID가 그 파일 함수 전부의 `item`으로(`ms`는 null), 화면 ID 없는 파일은 null · TS/JS — 맨 위 함수의 끝 줄·qual(function·const 화살표·class 메서드·객체 리터럴 메서드와 화살표) · graphify가 놓친 맨 위 정의를 더하고 화면 ID도 받는다 · 중첩 함수는 끝 줄만, 지우지 않는다 · graphify가 함수 0개로 본 TS 파일도 `files`로 읽어 `api.get`과 그 선을 더하고, 결과에 `files`가 남지 않는다(#282) · 같은 파일·상대 import(별칭·default·`index`)·JSX·`o.m` 호출이 `enrich` 선으로 · 패키지 import는 안 잇는다 · 깨진 파일은 건너뛴다

---

#### codegraph.communities 함수를 Louvain 군집으로 묶는다

**시그니처** `def communities(raw: dict, graph: dict) -> dict`

근거: [[SYNC-UC-001#UC-S8]] 기본 흐름 3 · UI-17 · 사용자 결정 2026-10-01(그래프를 만들 때 서버가 군집한다 — raw 그래프에는 파일·클래스·호출 선이 다 들어 함수가 제 파일·클래스와 같이 묶인다 · Louvain seed 42, 모델·네트워크 없음 · 한 번) · **#253 — graphify `cluster`를 쓰지 않는다.** 그것은 Louvain 뒤에 50노드 이상·응집도 0.05 미만 군집을 다시 쪼개는 2차 패스가 있어 싱크독(노드 4,197)이 111~131개로 터진다(resolution 0.1~1.0 모두). networkx Louvain만 돌리면 resolution 1.0에서 19개 — SCN S9의 「스물 몇 개」가 그대로 나온다. 사용자 결정 2026-10-01: Louvain 직접, resolution 1.0 · **#306 — 테스트는 군집에서 뺀다**(사용자 결정 2026-10-03). 테스트 노드·선이 군집에 들자, 테스트가 나눠 부르는 같은 파일의 함수가 둘로 갈리고 차수가 큰 테스트 파일이 라벨이 됐다 — 운영 CCR `test_pipeline.py`·VA `tests/conftest.py`·SYNC `test_tools.py` · **#308 — 라벨은 그 커뮤니티의 함수를 품은 것만**(사용자 결정 2026-10-04). 차수에는 타입 표기·상속·import 선도 들어, 메서드 없는 타입 클래스(SYNC `User` — 227선 중 `references` 122·`uses` 85, 메서드 0)·의존성 목록 파일(`package.json` — npm 의존성 `imports`)·바깥 이름(VA `Analysis`)이 라벨이 됐다. 그런 라벨은 화면의 허브 함수가 라벨에서 안 나와 둘이 따로 놀았다(UI-17 「허브 함수」). 후보가 없으면 지금 규칙(사용자 결정)

**입력** `raw` — `load`가 준 원형 · `graph` — `enrich`까지 끝난 그래프(같은 객체에 더해 돌려준다)

**처리**
1. `G = graphify.paths.load_node_link_graph(raw에서 테스트 노드와 그 선을 뺀 것)` — 테스트 노드는 `source_file`이 테스트 파일([[#codegraph.reduce]] 1과 같은 판정)인 노드. 묶음·라벨·차수가 구현 코드로만 정해진다(#306) · if 노드 0 → 모든 함수 `community = None`, `communities = []` → 7
2. `C = networkx.community.louvain_communities(G 무향, resolution=1.0, seed=42)` — **graphify `cluster`가 아니다**(#253, 근거). Louvain은 노드·선 순서에 민감하므로 노드와 양 끝을 정렬한 선으로 그래프를 다시 만들어 넣어 결정적으로. 군집은 크기 내림차순(같으면 정렬한 노드 튜플)으로 번호를 매긴다 — `0`이 가장 큰 군집. **예외는 삼키고** 1의 빈 결과 + `log.warning` — 군집이 안 돼도 그래프는 남는다
3. 노드 → 커뮤니티 사상에서 **key → 커뮤니티**(`key`는 `reduce`와 같은 규칙 — `source_file` + `source_location`의 `L` 뒤 숫자)와 **파일 → 커뮤니티**(그 파일 노드들의 다수 커뮤니티, 동률이면 작은 번호)
4. 함수마다 `community` = key의 것 · 없으면(enrich가 더한 정의) 파일의 것 · 그것도 없으면 None
5. **라벨** — `labels = graphify.cluster.label_communities_by_hub(G, 후보)`, 라벨은 graphify의 허브 이름(차수 최고, 차수는 `G`로 잰다). **후보는 그 군집의 코드 노드(graphify `file_type == code`) 중 그 커뮤니티의 함수(4)를 품은 것**(#308): 함수 노드는 그 `key`가 그 커뮤니티의 함수일 때 · 클래스 노드(`_callable_class`)는 그 커뮤니티에 같은 파일이고 `qual`이 `클래스이름.`으로 시작하는 함수(메서드)가 있을 때 · 그 밖 코드 노드(파일)는 그 커뮤니티에 같은 `source_file`의 함수가 있을 때. `source_file`이 없는 노드는 못 된다. if 후보가 없다 → 그 군집의 코드 노드 전부(지금 규칙). 문서·절 노드는 군집에는 들되 라벨에서 뺀다 — 문서 제목·절 노드도 `source_file`을 가지므로 `file_type`으로 가른다(#255 — 「SEQUENCE: 싱크독」·「2. 함수」 같은 이름이 나왔다). **예외는 삼키고** 라벨만 없이(번호) + `log.warning`
6. `communities = [{id, label: labels[id](끝 "()" 뗌, 없으면 번호), size: 든 함수 수}]` — 함수가 0인 군집(문서 노드나 함수 없는 파일만 든 것)은 뺀다. `size` 내림차순, 같으면 `id`
7. `→ graph`

**호출하는 것** 없음 (graphify 라이브러리 — MINISPEC 밖)

**호출되는 것** [[SYNC-MS-007#pipeline.build_code_graph]] 3 — `enrich` 뒤. 검사기(`check_calls`)는 부르지 않는다 — 대조에 군집이 필요 없다

**테스트 관점** contains·method 선으로 이어진 파일 둘 → 함수가 파일별로 갈린다 · 라벨이 허브 이름이고 `()`가 없다 · `size` = 함수 수이고 함수 없는 군집은 없다 · enrich가 더한 함수는 파일로 받는다 · 같은 raw 두 번 → 같은 결과 · 노드 없는 raw → 빈 목록·None · 노드가 가장 많은 군집이 `0`(#253) · 문서 노드가 차수 최고여도 라벨은 코드 노드 이름(#255) · 테스트가 나눠 부르는 같은 파일의 함수는 한 커뮤니티이고 차수 최고인 테스트 파일도 라벨이 못 된다 — 테스트 노드를 뺀 raw와 같은 결과(#306) · 메서드 없는 타입 클래스·함수 없는 파일(`package.json`)이 차수 최고여도 라벨이 못 되고 라벨은 함수를 품은 노드(#308) · 후보가 없으면 그 군집의 코드 노드 중 허브(#308)

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

#### codegraph.item_function 항목 ID로 그 항목의 함수

**시그니처** `def item_function(graph: dict, item_id: str) -> dict | None`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 2 · 사용자 결정 2026-10-02(화면 항목은 파일 이름과 같은 컴포넌트 하나, 카드 BK)

**처리**
1. `cands = [f for f in graph.functions if f.item == item_id]` · 없으면 `→ None`(옛 그래프·항목 없음)
2. 이름이 파일 이름(확장자 뗀 것)과 같은 함수가 있으면 그것 — `CodeGraph.tsx`의 `CodeGraph`. 화면 항목은 파일 함수 전부가 같은 `item`이라 여기서 하나로 좁힌다
3. 없으면 `(file, line)` 순으로 첫 함수
4. `→ 함수 dict`

**테스트 관점** 파일 이름과 같은 함수가 먼저 · 없으면 첫 함수 · 두 파일이 같은 항목이면 이름 맞는 파일 · `item` 없는 그래프 → None

---

#### codegraph.item_neighbors 항목 있는 함수까지의 부르는 것·불리는 곳

**시그니처** `def item_neighbors(graph: dict, key: str) -> tuple[list[str], list[str]]`

근거: [[SYNC-UC-001#UC-H20]] 기본 흐름 2 · 사용자 결정 2026-10-02(항목 있는 함수만, `item` 기준, 카드 BK)

**처리** — [[#codegraph.compare]] 3과 같은 걷기를 `item`으로, 양방향
1. `start = functions 중 key` · `own = start.item`(없으면 None)
2. 정방향: `calls`를 따라가며 `item`이 없거나 **`own`과 같은** 함수(도우미·같은 항목의 다른 함수)는 건너 계속, 다른 `item`이 있는 함수에 닿으면 멈춘다. 방문 표시로 사이클을 멈춘다. 자기 자신은 뺀다
3. 역방향: `calls`를 거꾸로 같은 규칙
4. 닿은 함수를 항목 ID로 접는다(한 항목 = 먼저 닿은 함수 하나) · 항목 ID 순
5. `→ (부르는 것 key 목록, 불리는 곳 key 목록)`

**테스트 관점** 도우미를 건너 닿는다 · 같은 항목의 함수는 건너 그 너머까지 · 항목 있는 함수 너머는 안 간다 · 역방향도 같다 · 사이클에서 멈춘다 · 같은 항목 둘은 하나로 · `ms`만 있는 옛 그래프는 빈 목록

---

#### codegraph.layer_table 클래스 명세의 층 표를 읽는다

**시그니처** `def layer_table(body: str) -> list[dict]`

근거: [[SYNC-STD-001]] 2.6 층 표 · 사용자 결정 2026-10-02(층 표는 클래스 명세 「폴더 구조」 절에 필수 · 명세 칸은 `[[…]]` 링크 · 카드 BM)

**입력** `body` — DOM 클래스 명세 원본 전체

**처리**
1. 「폴더 구조」 절만 본다 — `## ` 헤딩 글자가 번호를 떼고 `폴더 구조`로 시작하는 절부터 다음 `## `까지. 코드블록 안 줄은 표가 아니다
2. 머리 칸이 차례로 `경로`·`층`·`명세`인 첫 표 · 없으면 `→ []`
3. 몸 줄마다 `{patterns, name, specs, line}` — `patterns` = 경로 칸의 백틱 안 꼴들(` · `로 나열) · `name` = 층 칸 글자 · `specs` = 명세 칸을 ` · `로 나눈 조각마다 `{ref: 첫 [[…]] 안 또는 None, note: 링크를 뺀 나머지 글자}` · `line` = 본문 줄 번호. 꼴이 하나도 없는 줄은 버린다
4. `→ 줄 목록` — 표 순서 그대로(순서가 우선순위)

**테스트 관점** 번호 붙은 절·안 붙은 절 · 코드블록 안 표는 안 읽는다 · 머리가 다른 표는 건너뛴다 · 다른 절의 표는 안 읽는다 · 꼴 여럿·조각 여럿 · 링크 없는 조각은 `ref` None · 표 없음 → 빈 목록

---

#### codegraph.layers 항목 없는 함수마다 층

**시그니처** `def layers(graph: dict, rows: list[dict]) -> tuple[dict[str, dict], list[dict]]`

근거: [[SYNC-STD-001]] 2.6 판정 순서 · [[SYNC-UC-001#UC-H20]] 기본 흐름 5 · 사용자 결정 2026-10-02(도우미는 규칙으로 · 위에서부터 첫 줄 · 층 없는 함수와 안 맞는 줄은 검사가 잡는다, 카드 BM)

**입력** `graph` — 그래프 모양 그대로 · `rows` — [[#codegraph.layer_table]]

**처리**
1. 꼴 → 정규식: `**` → 여러 단, `*` → 한 단(`/` 빼고), 나머지 글자는 그대로 — 경로 전체가 맞아야 한다
2. `has_item` = 항목(`item`, 옛 그래프는 `ms`)이 있는 함수가 하나라도 든 파일들
3. 함수마다 — 항목이 있으면 층을 안 붙인다(항목이 먼저) · `file in has_item`이면 `{name: "도우미", specs: []}` · 아니면 표 위에서부터 첫 일치 줄의 `{name, specs}` · 아무 줄에도 안 맞으면 붙이지 않는다
4. 줄마다 **모든 함수**(항목 있는 것도)와 대조해 하나도 안 맞는 줄을 모은다
5. `→ (항목 없는 함수 key → {name, specs}, 안 맞는 줄 목록)` — 층이 없는 함수는 dict에 없다

**테스트 관점** 항목 있는 함수는 층이 없다 · 같은 파일에 항목 있으면 도우미(표보다 먼저) · 첫 일치가 이긴다 · `*`는 한 단만, `**`는 여러 단 · 안 맞는 줄 · 표가 비면 도우미만 · 옛 그래프(`item` 없음)는 `ms`로

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

- [x] 파이썬 밖(TS·Go…)의 보강 — 지금은 graphify 결과 그대로. 싱크독 코드는 MINISPEC 함수가 전부 파이썬이라 급하지 않다 — **결정(2026-10-02, 카드 BL): TS/JS는 tree-sitter로 끝 줄·빠진 맨 위 함수·호출을 채운다**([[#codegraph.enrich]] 2a~2d). 끝 줄이 없어 화면 컴포넌트의 코드 보기가 잘리는 것이 실제 문제였다. Go 등 다른 언어는 graphify 그대로 — 그 언어의 프로젝트가 생기면 같은 꼴로 더한다
