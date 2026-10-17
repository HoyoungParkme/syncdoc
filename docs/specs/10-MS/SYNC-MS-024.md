---
doc_id: SYNC-MS-024
type: MS
title: MINISPEC — codegraph 흐름 — 호출 순서·라우트·화면 요청·장비·실행 단위
status: approved
upstream: [SYNC-DOM-002, SYNC-DOM-003, SYNC-SEQ-001, SYNC-MS-011, SYNC-INFRA-001]
---

# MINISPEC — codegraph 흐름 — 호출 순서·라우트·화면 요청·장비·실행 단위

## 0. 이 문서가 다루는 것

`core/codegraph/flow.py`·`steps.py`·`routes.py`·`infra.py`(순수 함수) — 목록은 1장. 클래스 명세 [[SYNC-DOM-002]] 4.11의 흐름 모듈을 함수 내부까지 내린 것. 흐름 보기([[SYNC-PRD-001#R16]], UI-19)가 쓰는 키를 코드 그래프에 더한다. view_arc의 분석기(`python_analyzer.py`·`ts-analyzer.mts`·`infra.mts`·`stack.mts`)를 옮기되, **두 판이 같은 입력에 바이트까지 같은 결과를 내도록** 규칙을 좁혔다 — Rust 판([[SYNC-MS-026]])이 같은 처리를 tree-sitter로 한다.

형식은 [[SYNC-STD-001]] 2.10. **표기** — `→` 반환·결과, `·` 같은 단계 안 구분.

**좁힌 것과 왜.** view_arc는 파이썬 분석기가 타입을 풀어 호출 대상을 찾는다. 그것을 두 판에서 똑같이 다시 만들면 크고 틀리기 쉽다. 그래서 **호출 대상은 그래프에 이미 있는 호출 선**([[SYNC-MS-011#codegraph.enrich]] — graphify와 싱크독 보강이 푼 것)에서 이름으로 고른다. 호출 **차례**는 호출식이 **끝나는 바이트 위치**로 정한다 — 안쪽 호출(`f(g(x))`의 `g`)이 먼저 끝나고, 같은 줄의 형제는 앞의 것이 먼저 끝난다. 파이썬 `ast`와 tree-sitter 둘 다 바이트 위치를 주므로 두 판이 같은 차례를 낸다.

**언어** — `.py`(파이썬) · `.ts .tsx .js .jsx .mjs`(TS/JS) · `.rs`(Rust) · `.java`(Java) · `.go`(Go) — 다섯 갈래. 다른 언어 파일은 `files`에만 든다. Java·Go는 3차(카드 CN·L33, 2026-10-17) — `tree-sitter-java` 0.23.5 · `tree-sitter-go` 0.25.0, 두 판이 같은 판의 문법을 쓴다.

**더하는 키** — `code_graphs.graph`에 들어간다([[SYNC-DOM-003#code_graphs]]).

| 키 | 모양 | 뜻 |
|---|---|---|
| `files` | `[{path, lang, loc}]` | 저장소의 코드 파일 전부 — [[#flow.files]] |
| `functions[].steps` | `[{k, line, label, to?, inferred?, deferred?, awaited?, infra?}]` — `?`는 있을 때만 | 함수의 호출 순서 — [[#steps.steps]] |
| `functions[].route` | `{method, path}` 또는 null | 함수가 받는 라우트 — [[#routes.routes]] |
| `http` | `[{from, to, inferred}]` | 화면 요청 → 라우트 함수 — [[#routes.http_links]] |
| `infra` | `{nodes: [InfraNode], links: [{from, to, protocol}]}` | 장비와 연결 — [[#infra.infra]] |
| `units` | `[{name, kind, dir, lang, framework, command, port}]` | 실행 단위 — [[#infra.units]] |

**순서와 모양은 고정이다** — 목록은 처리에 적은 차례대로, 사전의 키는 표에 적은 차례대로 만든다. 정답 파일이 두 판의 결과를 바이트로 비교한다([[SYNC-DOM-004]] 4.13).

**건너뛰는 폴더** — 모든 함수가 같은 것을 건너뛴다: 이름이 `.`으로 시작하는 폴더, `node_modules` `vendor` `target` `dist` `build` `out` `venv` `.venv` `__pycache__` `site-packages` `coverage` `graphify-out`.

**테스트 파일** — [[SYNC-MS-011#codegraph.reduce]] 1의 판정과 같다. 흐름에서 뺀다(`files`에도 없다).

**걷는 차례와 정규식** — 폴더를 걸을 때는 이름의 바이트 순이다(파일 시스템 차례에 기대지 않는다). 표의 정규식은 view_arc(JS)의 것을 옮겼다 — `\w`·`\d`·`\s`는 ASCII 뜻이고(파이썬 `re.ASCII`), `/i`는 대소문자 무시다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#flow.extend]] | 흐름 키를 차례로 더한다 — 실패한 키만 비운다 |
| [[#flow.files]] | 저장소의 코드 파일 목록 |
| [[#steps.steps]] | 함수마다 호출 순서 |
| [[#routes.routes]] | 함수마다 받는 라우트 |
| [[#routes.http_links]] | 화면 요청을 라우트 함수에 잇는다 |
| [[#infra.units]] | 실행 단위 — 서버·화면·작업 |
| [[#infra.infra]] | 장비·연결, 호출 순서에 닿는 장비 표시 |

---

## 2. 함수

#### flow.extend 흐름 키를 차례로 더한다

**시그니처** `def extend(src_dir: Path, graph: dict) -> dict`

근거: [[SYNC-UC-001#UC-S8]] 4·5 · [[SYNC-SEQ-001#SEQ-26]] · 사용자 결정 2026-10-12 — 그래프는 하나(흐름 키를 코드 그래프에 더한다)

**입력** `src_dir` — 그 커밋을 푼 폴더. `graph` — [[SYNC-MS-011#codegraph.enrich]]의 결과(`functions`·`calls`)

**처리**
1. `graph["files"] = files(src_dir)`
2. `graph["units"] = units(src_dir, graph)`
3. `steps(src_dir, graph)` — 함수마다 `steps`
4. `routes(src_dir, graph)` — 함수마다 `route`
5. `graph["http"] = http_links(src_dir, graph)`
6. `infra(src_dir, graph)` — `graph["infra"]`와 steps의 `infra`
7. **지우기** — 함수마다 steps에서 `to`도 `infra`도 없는 `call`을 뺀다(라이브러리 `split` 같은 것 — 재생에 쓸 데가 없고 그래프가 몇 MB로 커진다). 반환·예외는 둔다
8. 2~7은 각각 따로 감싼다 — 하나가 예외를 내면 그 키만 빈 값(`units`·`http` `[]`, `infra` `{"nodes": [], "links": []}`, 함수의 `steps` `[]`·`route` null)으로 두고 로그 한 줄, 나머지는 계속한다. 1이 실패하면 `files` `[]`
9. `→ graph` (같은 객체)

**출력** 흐름 키가 든 그래프. 함수마다 `steps`·`route` 키가 반드시 있다

**호출하는 것** [[#flow.files]] · [[#infra.units]] · [[#steps.steps]] · [[#routes.routes]] · [[#routes.http_links]] · [[#infra.infra]]

**테스트 관점** 키 여섯이 다 생긴다 · 한 단계가 터져도 그 키만 비고 그래프는 돌아온다 · 함수마다 `steps`·`route`가 있다 · 대상도 장비도 없는 호출이 빠지고 반환·예외는 남는다

---

#### flow.files 저장소의 코드 파일 목록

**시그니처** `def files(src_dir: Path) -> list[dict]`

근거: [[SYNC-UC-001#UC-H24]] 3a — 함수를 못 읽는 언어도 건물로

**처리**
1. `src_dir` 아래를 걷는다(0장의 건너뛰는 폴더 빼고, 심볼릭 링크는 따르지 않는다)
2. 확장자가 [[SYNC-MS-011]]의 `CODE_EXTS`인 파일, 테스트 파일 빼고
3. 파일마다 `{path: src_dir 기준 '/' 경로, lang, loc}` — `lang`은 `.py`→`python` · `.ts .tsx`→`typescript` · `.js .jsx .mjs`→`javascript` · `.rs`→`rust` · 그 밖은 점을 뺀 확장자(`go`). `loc` = 줄 수(바이트의 `\n` 수, 마지막 줄이 `\n` 없이 끝나면 +1, 빈 파일 0)
4. `path`의 바이트 순으로 정렬 → 목록

**테스트 관점** 건너뛰는 폴더·테스트 파일이 빠진다 · 확장자별 lang · 끝 줄바꿈 유무와 loc · 정렬

---

#### steps.steps 함수마다 호출 순서

**시그니처** `def steps(src_dir: Path, graph: dict) -> dict`

근거: [[SYNC-PRD-001#R16]] 「함수를 고르면 코드에서 읽은 호출·반환·예외를 재생」 · view_arc `StepWalker`를 0장의 좁힌 규칙으로

**입력** `graph` — `functions`·`calls`가 있는 그래프

**처리**
1. 파일마다(그래프 함수의 `file` 중 다섯 언어) 한 번 읽는다. 맨 앞 UTF-8 BOM은 떼고 센다. UTF-8이 아니거나 파싱하지 못하면(파이썬 `SyntaxError`) 그 파일 함수는 `steps: []`. 바이트 위치는 파일 바이트(BOM을 뗀) 안의 자리 — 파이썬은 줄의 시작 바이트 + `col_offset`
2. **정의 찾기** — 파일의 모든 함수 정의(중첩 포함)를 줄로 색인한다
   - 파이썬: `FunctionDef`·`AsyncFunctionDef` — `def` 줄과 첫 데코레이터 줄 둘 다
   - TS/JS: `function_declaration`·`generator_function_declaration`·`method_definition`·`function_expression`·`arrow_function` — 그 노드의 첫 줄, 그리고 `lexical_declaration`·`variable_declaration`·`export_statement`·`pair`·`public_field_definition`의 값으로 들어 있으면 그 문의 첫 줄
   - Rust: `function_item` — `fn` 낱말이 든 줄
   - Java: `method_declaration`·`constructor_declaration` — 선언의 첫 줄(어노테이션·수식어 줄부터, [[SYNC-MS-011#codegraph.enrich]] 2i의 key 줄)
   - Go: `function_declaration`·`method_declaration` — 선언의 첫 줄(`func` 줄)
   - 그래프 함수 `line`에 맞는 정의가 없으면 `steps: []`. 둘 이상이면 시작 바이트가 앞선 것
3. **훑기** — 정의의 몸통(`body` — 파이썬은 매개변수 기본값의 `Depends(…)`도)을 다 내려가며 아래 「사건」을 모은다. **중첩 정의**(파이썬 `def`·`lambda`, TS/JS 함수·화살표, Rust `closure_expression`·중첩 `function_item`, Java `lambda_expression`, Go `func_literal`) 안은 계속 내려가되 그 안의 사건은 `deferred: true`이고 그 안의 `return`·`raise`는 모으지 않는다. Go `go`·`defer` 문 안도 같다(나중에 돈다). 파이썬 `class` 정의 안은 내려가지 않는다 — Java도 `class_body`(익명 클래스 몸통)와 메서드 안 타입 선언 안은 내려가지 않는다
4. **사건** — 각 사건은 `(끝 바이트, 시작 바이트, 내용)`
   - 호출 — 파이썬 `Call` · TS/JS `call_expression`(함수 자리가 `import`이면 뺀다) · Rust `call_expression` · Go `call_expression` · Java `method_invocation`(`label`은 호출식 처음부터 `name`의 끝까지 — `this.repo.find`) · Java `object_creation_expression`(`label` = `new ` + 타입 글자). 함수 자리의 소스 글자가 `label`, 끝 바이트는 호출식 전체의 끝. 파이썬 `Depends(…)`가 매개변수 기본값이면 `label`은 `Depends(` + 첫 인자 글자 + `)`이고 `line`은 함수 정의의 `def` 줄이다. 기본값의 다른 호출은 사건이 아니다
   - JSX — TS/JS `jsx_opening_element`·`jsx_self_closing_element`의 이름이 대문자로 시작하면(`Comp`·`Foo.Bar`) 호출 하나, `label` = `<` + 이름 + `>`
   - 반환 — 파이썬 `Return` · TS/JS `return_statement` · Rust `return_expression` · Java·Go `return_statement`. `label` = `return` 또는 `return ` + 값 글자(Go는 값 목록 `a, b` 전부, 괄호를 벗기지 않는다)
   - 예외 — 파이썬 `Raise`(`raise ` + 예외 글자, 없으면 `raise`) · TS/JS·Java `throw_statement`(`throw ` + 값 글자). Rust·Go는 없다(Go `panic(…)`은 호출이다)
   - `awaited` — 호출이 파이썬 `Await`의 값 그 자체 · TS/JS `await_expression`의 자식 그 자체 · Rust `await_expression`의 앞 식 그 자체일 때. Java·Go는 없다
5. **차례** — Depends 사건이 맨 앞(시작 바이트 차례), 나머지는 `(끝 바이트, -시작 바이트)` 오름차순 — 안쪽 호출이 먼저, `return f()`에서 호출이 반환보다 먼저
6. **글자** — 글자를 뽑는 식(호출의 함수 자리·반환 값·예외 값·Depends 인자)이 괄호로만 싸여 있으면 괄호를 벗긴 안쪽 식이다(파이썬 `ast`에는 괄호 노드가 없다 — 괄호 묶음 튜플 `(a, b)`는 튜플이라 괄호째). 소스 바이트를 UTF-8로 읽고(못 읽는 바이트는 대체 문자), 공백 문자 묶음(`\s+`, 파이썬 `str.split()`과 같은 공백)을 한 칸으로, 앞뒤를 자르고, `.` 바로 앞뒤의 한 칸을 지운다(여러 줄 사슬 `map\n  .lock()` → `map.lock`). 글자 수(코드 포인트)가 70을 넘으면 앞 69자 + `…`. 반환·예외는 합친 뒤 자른다
7. **줄** — 호출·JSX·반환·예외가 시작하는 줄(1부터). Depends는 2의 `def` 줄
8. **대상(`to`)** — 호출의 마지막 이름: 파이썬 `Name.id` · `Attribute.attr` / TS/JS `identifier` · `member_expression`의 `property` · JSX 이름의 마지막 조각 / Rust `identifier` · `field_expression`의 `field` · `scoped_identifier`의 `name` · `generic_function`이면 그 안의 함수 / Java `method_invocation`의 `name` · `new T`는 타입의 단순 이름(제네릭·경로를 뗀 `T` — 생성자 이름과 같다) / Go `identifier` · `selector_expression`의 `field`. Depends는 첫 인자의 마지막 이름. 이름이 없으면(`f()()`, `a[0]()`) `to` null. Depends의 첫 인자는 맨 이름 호출과 같이 본다
   - 이 함수에서 나가는 호출 선(`calls`의 from이 이 함수) 중 대상 함수의 `name`이 그 이름인 것이 **딱 하나**면 그 함수 열쇠, `inferred: false`
   - 없고 호출이 **맨 이름·경로 호출**(파이썬 `Name` · TS/JS `identifier` · Rust `identifier`·`scoped_identifier` · Java 받는 쪽 없는 `m()`·`new T` · Go `identifier`)이면, 그래프에서 **같은 언어**(0장의 다섯 갈래) 파일의 함수 중 `name`이 그 이름인 것이 **딱 하나**이고 그것이 이 함수가 아닐 때 그 열쇠, `inferred: true`. 메서드 호출(`x.m()`)은 짐작하지 않는다 — 받는 쪽 타입을 모르면 `split`·`clone` 같은 이름이 엉뚱한 언어의 함수에 붙는다
   - 그 밖 null, `inferred: false`
   - 장비 판정([[#infra.infra]])이 쓰도록 각 호출의 마지막 이름을 함께 남긴다 — 결과에는 나가지 않는다
9. 한 함수에 사건이 200개를 넘으면 차례대로 앞 200개만
10. 함수마다 `steps = [{k, line, label, …}]` — `k`는 `call`(JSX 포함)·`return`·`raise`. **기본값인 키는 싣지 않는다** — `to`는 있을 때만, `inferred`·`deferred`·`awaited`는 참일 때만(`true`). 키 차례는 `k, line, label, to, inferred, deferred, awaited`. `infra`는 [[#infra.infra]]가 있을 때만 `awaited` 뒤에 단다
11. 정의를 못 찾은 함수·다섯 언어가 아닌 함수는 `steps: []` · `→ graph`

**테스트 관점** 중첩 호출 `f(g(x))` → g, f · 형제 호출은 앞에서부터 · `return f()` → 호출, 반환 · `await` 표시 · 중첩 함수·화살표·클로저 안 호출이 `deferred`이고 그 안 `return`은 없다 · 파이썬 데코레이터 달린 함수도 찾는다 · Depends가 맨 앞 · JSX `<Comp>` · 글자 공백 접기와 70자 자르기(한글 포함) · 나가는 선으로 `to`(같은 이름 둘이면 null) · 선이 없을 때 맨 이름 호출은 같은 언어에서 하나뿐인 이름 → `inferred`, 메서드 호출·다른 언어는 짐작하지 않는다 · 기본값 키가 빠진다 · `.` 앞뒤 공백 · 200개 자르기 · 파싱 실패 파일 → 빈 목록 · **Java** 람다 안 호출이 `deferred` · `throw` · `new T` → 생성자 · `this.x.m` 글자 · **Go** `defer`·`go`·`func` 리터럴 안이 `deferred` · `return` 값 목록

---

#### routes.routes 함수마다 받는 라우트

**시그니처** `def routes(src_dir: Path, graph: dict) -> dict`

근거: [[SYNC-PRD-001#R16]] 「라우트를 읽는다」 · view_arc `route_of`·`collect_routers`·ts-analyzer의 라우트 꼴을 아래 꼴로 좁혔다

**처리** — 함수마다 `route`를 null로 두고, 찾은 것만 채운다. 경로 매개변수는 `{이름}` 꼴로 맞춘다(Flask `<int:id>`→`{id}`, Express `:id`→`{id}`, Next `[id]`→`{id}`, `[...rest]`→`{rest}`). 경로는 앞에 `/`를 붙이고 끝 `/`는 뗀다(`/`만 남으면 `/`)

1. **파이썬** — 파일마다(그래프 `files`의 `.py` 전부 — 함수 없는 `main.py`의 `include_router`도 읽는다)
   - 라우터 이름 표: 맨 위 `X = APIRouter(…)`·`FastAPI(…)`·`Blueprint(…)`·`Flask(…)`(생성자 이름의 마지막 조각으로) — `prefix=` 키워드가 글자 상수면 그 접두어(Blueprint는 `url_prefix=`)
   - 함수의 데코레이터 `@X.get|post|put|patch|delete|head|options(경로, …)` → `{method: 대문자, path: 접두어 + 경로}` · `@X.route(경로, methods=[…])` → 첫 방법(없으면 `GET`) · `@X.api_route(경로, methods=[…])` 같다. `X`는 이름 표의 것이거나 임의 이름(`app`) — 이름 표에 없으면 접두어 없이
   - `app.include_router(X, prefix="…")`가 같은 저장소의 다른 파일 `X`를 가리키면 접두어를 앞에 더한다 — `from 모듈 import router as X`·`모듈.router` 꼴만, 한 단만
2. **TS/JS** — 파일마다
   - `X.get|post|put|patch|delete|all(경로 글자, …, 핸들러)` — `X`가 `express()`·`express.Router()`·`Router()`·`fastify(…)`·`new Hono()`·`new Koa…Router()`로 만든 이름일 때. 핸들러가 이름(`h`·`ctrl.h`)이면 그 이름의 그래프 함수, 인라인 함수면 그 함수 정의 줄의 그래프 함수. `all`은 `ANY`
   - NestJS — 클래스 `@Controller('p')`의 메서드 `@Get('q')`·`@Post…` → `/p/q`
   - Next — 경로가 `app/**/route.(ts|js)`인 파일의 `export async function GET|POST|…` → `/` + `app/` 뒤 폴더들(괄호 묶음 `(group)` 폴더는 뺀다)
3. **Rust** — 파일마다 `.route("경로", 방법(핸들러)…)`의 사슬(`get(h).post(g)`) → 핸들러 이름의 그래프 함수(같은 파일에서 `use`한 함수 포함, 마지막 이름으로 — 같은 이름이 둘이면 이 파일의 것). actix `#[get("경로")]` 속성 → 그 함수
4. **Java** — 파일마다 `class_declaration`(중첩 포함)의 어노테이션 `@RequestMapping(…)`(이름의 마지막 조각으로)이 접두어, 그 몸통에 바로 든 `method_declaration`의 어노테이션 `@GetMapping`·`@PostMapping`·`@PutMapping`·`@PatchMapping`·`@DeleteMapping` → 그 방법, `@RequestMapping` → `method = RequestMethod.X`(배열이면 첫 것)의 `X`, 없으면 `ANY`. 경로 = 인자의 첫 글자 상수 — 이름 없는 인자 · `value =` · `path =`(배열이면 첫 글자), 없으면 `""`. 접두어와 이어 붙이고(`/`로 한 번), Spring 정규식 매개변수 `{id:\d+}` → `{id}`. 메서드에 어노테이션이 둘이면 표의 것 중 처음 것 → 그 선언 첫 줄의 그래프 함수
5. **Go** — 파일마다 호출 `X.M("경로", …, 핸들러)` — `M`이 `HandleFunc`·`Handle`·`Any`(→ `ANY`) · `GET`·`POST`·`PUT`·`PATCH`·`DELETE`(gin·echo) · `Get`·`Post`·`Put`·`Patch`·`Delete`(chi·fiber, 대문자로). 경로가 `"GET /p"` 꼴(Go 1.22)이면 방법과 경로로 나눈다. 핸들러 = 마지막 인자 — 이름(`h`) 또는 `x.h`의 `h`, 그 밖(함수 리터럴·호출)은 건너뛴다. 파일 위에서부터 `g := X.Group("/p")`(왼쪽 이름 하나)를 모아 `g`로 부른 등록에 `X`의 접두어 + `/p`를 붙인다. 경로 매개변수 `:id`·`*rest`(gin) · `{rest...}`(Go 1.22) → `{id}`·`{rest}`. 핸들러 이름의 그래프 Go 함수 중 같은 폴더의 것, 없으면 모든 Go 함수 — 딱 하나일 때
6. 같은 함수에 둘 이상이면 처음 것(1~5의 차례) · `→ graph`

**테스트 관점** FastAPI `prefix`·Flask `<int:id>`·Blueprint `url_prefix`·`include_router` 접두어 · Express `:id`·인라인 핸들러 · NestJS · Next `app/api/items/[id]/route.ts` · axum 사슬 `get(h).post(g)` · actix 속성 · 끝 `/` · Spring 클래스 접두어·`{id:\d+}`·`@RequestMapping(method=…)`·`path = {…}` · gin `Group`·`:id` · Go 1.22 `"POST /p/{rest...}"`

---

#### routes.http_links 화면 요청을 라우트 함수에 잇는다

**시그니처** `def http_links(src_dir: Path, graph: dict) -> list[dict]`

근거: [[SYNC-PRD-001#R16]] 「화면의 요청을 라우트에 잇는다」 · view_arc R2 — 글자로 칸마다 맞으면 exact, 아니면 inferred

**처리**
1. 화면 파일 = [[#infra.units]]의 `web` 단위 폴더 안 TS/JS 파일, 또는 `.tsx`·`.jsx` 파일
2. 화면 파일의 그래프 함수마다 정의 몸통(steps 2와 같은 찾기)의 호출 중 **첫 인자가 `/`로 시작하는 글자·템플릿 글자**인 것 — 함수 자리의 마지막 이름이 `fetch`·`get`·`post`·`put`·`patch`·`delete`·`del`·`head`·`request`인 것만. 방법: 이름이 `get`·`post`… → 그것(`del`→`DELETE`), `fetch`·`request` → 둘째 인자 객체의 `method:` 글자, 없으면 `GET`. 템플릿의 `${…}`는 칸 하나(`*`). 쿼리(`?` 뒤)는 뗀다. **서버의 라우트 등록(`app.get('/x', h)` — 2번째 인자가 있는 Express 꼴의 `X`)은 요청이 아니다** — routes 2의 라우터 이름으로 부른 것은 건너뛴다
3. 라우트 = `route`가 있는 함수 전부. 경로를 `/`로 나눈 칸끼리 맞춘다 — 칸 수가 같고, 칸마다 같은 글자거나 라우트 칸이 `{…}`이거나 요청 칸이 `*`이면 맞다. 방법이 같거나 라우트가 `ANY`
   - 맞는 라우트 중 **글자 칸이 글자 칸과 맞은 수**가 가장 큰 것들. 하나면 그것, 둘 이상이면 다 
   - `inferred` — 요청 칸 `*`가 라우트의 글자 칸과 맞았거나, 맞는 라우트가 둘 이상
4. 맞는 것이 없으면 끝맞춤 — 요청 경로가 라우트 경로의 뒤쪽과 칸마다 맞으면(라우트가 `/api` 같은 접두어를 더 가졌다) 같은 고르기로, 모두 `inferred: true`
5. `{from: 요청한 함수, to: 라우트 함수, inferred}` — 같은 쌍은 하나(먼저 나온 것). `(from, to)` 바이트 순 정렬 → 목록

**테스트 관점** `` api.get(`/api/projects/${code}/flow`) `` → `GET /api/projects/{code}/flow` exact · `fetch(url, {method:'POST'})` · 템플릿 칸이 글자 칸과 맞으면 inferred · 서버 라우트 등록은 요청이 아니다 · 끝맞춤 inferred · 화면 파일이 아니면 안 본다

---

#### infra.units 실행 단위 — 서버·화면·작업

**시그니처** `def units(src_dir: Path, graph: dict) -> list[dict]`

근거: [[SYNC-PRD-001#R17]] 「기록 도구 명령」 · [[SYNC-UC-001#UC-H24]] 2 받침대 · view_arc `stack.mts`를 아래 꼴로 좁혔다

**처리** — 0장의 건너뛰는 폴더 밖, 깊이 3까지의 목록 파일을 본다. 단위마다 `{name, kind, dir, lang, framework, command, port}`. `dir`은 목록 파일이 든 폴더(루트면 `""`), `name`은 `dir`의 마지막 조각(루트면 저장소 폴더 이름이 아니라 `app`)
1. **`package.json`** — `dependencies`의 이름에 `express`·`fastify`·`koa`·`@nestjs/core`·`hono` 중 하나 → `server`(framework Express·Fastify·Koa·NestJS·Hono, 표 차례로 첫 것) · 아니면 `dependencies`·`devDependencies`에 `next` → `web`, Next.js · `vite` → `web`, Vite · `react`·`vue`·`svelte` → `web`, React·Vue·Svelte. 둘 다 아니면 단위가 아니다. `lang` = `tsconfig.json`이 같은 폴더에 있으면 `typescript`, 아니면 `javascript`. `command` = `scripts.dev`가 있으면 `npm run dev`, 아니면 `scripts.start`가 있으면 `npm start`, 아니면 null. `port` = 그 스크립트 글자의 `--port N`·`-p N`, 없으면 Vite 5173 · Next.js 3000 · 그 밖 null. JSON이 깨졌으면 건너뛴다
2. **파이썬** — `pyproject.toml`·`requirements.txt`·`manage.py`가 든 폴더마다 그 아래 `.py` 파일(테스트 빼고, 경로 바이트 순)을 읽어 처음 찾은 것 하나:
   - `manage.py`가 있으면 Django — `server`, `python manage.py runserver 8000`, 8000
   - 맨 위 대입 `V = FastAPI(…)` → FastAPI — `server`, `uvicorn {모듈}:{V} --port 8000`, 8000 · `V = Flask(…)` → Flask — `server`, `flask --app {모듈} run --port 5000`, 5000 · `V = Celery(…)` → Celery — `job`, `celery -A {모듈} worker`, null
   - `{모듈}` = 단위 폴더 기준 파일 경로를 점으로(`.py`를 떼고 `__init__`은 뗀다 — `app/main.py` → `app.main`)
   - 그 폴더에 `uv.lock`이 있으면 command 앞에 `uv run `
   - `lang` = `python`. 찾은 것이 없으면 단위가 아니다
3. **`Cargo.toml`** — `[dependencies]`(또는 `[workspace.dependencies]`) 표의 키에 `axum` → `server`, Axum · `actix-web` → `server`, Actix. `[package]`의 `name`이 있으면 `cargo run -p {name}`, 없으면 null. port null. `lang` = `rust`. 작업 공간 루트(`[workspace]`만)는 단위가 아니다
4. **Spring Boot** — `pom.xml`·`build.gradle`·`build.gradle.kts`(그 차례로 그 폴더에 있는 첫 것)의 글자에 `spring-boot` 또는 `springframework.boot`가 있으면 `server`, Spring Boot, `lang` = `java`. `command` = Maven `./mvnw spring-boot:run`(같은 폴더에 `mvnw`가 있을 때, 없으면 `mvn spring-boot:run`) · Gradle `./gradlew bootRun`(`gradlew`가 있을 때, 없으면 `gradle bootRun`). `port` = 그 폴더 `src/main/resources/application.yml`·`.yaml`·`.properties`(그 차례로 첫 맞는 것)의 `server:` 아래 `port:` 또는 `server.port=` — `${X:기본}`·`${X:-기본}`은 기본값으로 — 없으면 8080. 첫 파일에 Spring이 없으면 단위가 아니다
5. **Go** — `go.mod`의 글자에 `gin-gonic/gin` → Gin · `labstack/echo` → Echo · `go-chi/chi` → chi · `gofiber/fiber` → Fiber · `gorilla/mux` → gorilla/mux(표 차례로 첫 것), 없으면 net/http. 그 폴더 아래 깊이 4까지(0장 폴더 빼고) `.go` 파일(테스트 빼고)을 경로 바이트 순으로 읽어 `^package main\b`(여러 줄)와 `func main(`이 든 첫 파일 — 없으면 단위가 아니다. net/http인데 그 파일에 `net/http`가 없으면 단위가 아니다(서버가 아닌 CLI). `server`, `lang` = `go`, `command` = 그 파일이 단위 폴더 바로 아래면 `go run .`, 아니면 `go run ./{그 파일의 폴더}`. `port` = 그 파일의 첫 `["'`]([\w.]*):(\d{4,5})["'`]`의 수, 없으면 8080
6. `(dir, name)` 바이트 순 정렬 → 목록

**테스트 관점** Express·Vite·Next의 kind·framework·명령·포트(`--port` 우선) · FastAPI 모듈 경로와 `uv run ` · Flask·Django·Celery · axum `-p` · 깨진 package.json · 깊이 3 넘는 것은 안 본다 · Spring `mvnw`·`${PORT:8081}` · Gradle 래퍼 없음 · Spring 없는 pom · Go Gin `go run ./cmd/api`·포트 글자 · net/http 없는 CLI는 단위가 아니다

---

#### infra.infra 장비·연결, 호출 순서에 닿는 장비 표시

**시그니처** `def infra(src_dir: Path, graph: dict) -> dict`

근거: [[SYNC-PRD-001#R16]] 「장비는 코드의 라이브러리 호출·의존성 목록·docker-compose·설정 파일의 주소로 찾는다. 주소는 호스트·포트만」 · [[SYNC-INFRA-001#C13]] · view_arc `infra.mts`의 표를 옮겼다 · Java 줄과 타입 표는 view_arc `generic.mts`(카드 CN)

**표** — 1장 밖 상수로 둔다(두 판이 같은 표).
- `LIBS` 패키지 → `(id, kind, name, io 정규식, protocol)` — view_arc `infra.mts`의 Python·Node 줄 그대로(sqlalchemy·sqlmodel·psycopg2·psycopg·asyncpg·pymysql·sqlite3·aiosqlite·pymongo·motor·neo4j·redis·boto3·minio·openai·anthropic·requests·httpx·aiohttp·urllib·elasticsearch·opensearchpy·pika·aio_pika·kafka·aiokafka·celery · pg·@neondatabase/serverless·mysql2·better-sqlite3·drizzle-orm·@prisma/client·typeorm·sequelize·knex·mongoose·mongodb·ioredis·@upstash/redis·bullmq·@aws-sdk/client-s3·@aws-sdk/lib-storage·aws-sdk·@anthropic-ai/sdk·@google/generative-ai·@google/genai·axios·node-fetch·undici·fetch·kafkajs·amqplib·@elastic/elasticsearch·neo4j-driver·@supabase/supabase-js)과 Rust 줄(`sqlx` db·DB·`^(fetch\w*|execute\w*)$`·SQL · `tokio_postgres` db·PostgreSQL·`^(query\w*|execute\w*|prepare)$`·SQL · `reqwest` http·외부 HTTP·`^(send|get|post|put|patch|delete|head)$`·HTTPS · `redis` cache·Redis·`^(query\w*|get|set\w*|del)$`·Redis · `aws_sdk_s3` storage·S3 저장소·`^send$`·S3), 그 뒤에 Java 줄(view_arc의 `spring-data`·`jdbc`·`jpa`·`jooq`·`mybatis`·`java-mongo`·`java-neo4j`·`java-redis`·`java-http`·`java-kafka`·`java-amqp`·`java-s3`·`java-search`·`spring-ai` — io는 모두 `.`, 받는 쪽 타입이 이미 장비다)과 Go 줄(키는 import 경로에서 `/vN` 조각을 뗀 것 — `database/sql` · `github.com/jackc/pgx` · `github.com/jackc/pgx/pgxpool` · `gorm.io/gorm` · `go.mongodb.org/mongo-driver/mongo` · `github.com/redis/go-redis` · `github.com/go-redis/redis` · `net/http`(`^(Get|Post|PostForm|Head|Do)$`) · `github.com/aws/aws-sdk-go-v2/service/s3` · `github.com/sashabaranov/go-openai` · `github.com/anthropics/anthropic-sdk-go` · `github.com/segmentio/kafka-go` · `github.com/rabbitmq/amqp091-go`, io는 각 라이브러리의 입출력 메서드 이름 — 정확한 정규식은 두 판의 표가 같다)
- `JAVA_TYPES` 타입 단순 이름 → Java 줄 키 — view_arc `TYPE_LIBS` 그대로(`.NET` 줄 뺌: `JdbcTemplate`→jdbc · `EntityManager`→jpa · `RestTemplate`·`WebClient`→java-http · `RedisTemplate`→java-redis · `MongoTemplate`→java-mongo · `KafkaTemplate`→java-kafka · `S3Client`→java-s3 · `ChatClient`→spring-ai …) · `REPO_BASES` 저장소 인터페이스가 넓히는 타입 → 키(`MongoRepository`→java-mongo · `ElasticsearchRepository`→java-search · `Neo4jRepository`→java-neo4j · `JpaRepository`·`CrudRepository`·`PagingAndSortingRepository`…→spring-data, 표 차례로 첫 맞는 줄) · `GO_NAMES` 패키지 이름이 경로에서 안 나오는 Go 경로(`github.com/rabbitmq/amqp091-go`→`amqp` · `github.com/anthropics/anthropic-sdk-go`→`anthropic`)
- `DEPS`·`IMAGES`·`SCHEMES`·`HTTP_KEYS`·`HOST_KEYS`·`PLACEHOLDER`·`LOCAL_HOSTS`·`NOT_APP` — view_arc `infra.mts` 그대로(DEPS의 Java·Go·.NET·PHP 패턴 조각도 그대로 둔다 — 맞을 파일이 없을 뿐이다)

**처리**
1. **함수의 패키지** — 앱 코드 파일(다섯 언어)마다 import 표: 파이썬 `import a.b as c`→`c: a` · `import a.b`→`a: a` · `from a.b import c as d`→`d: a`(상대 import는 뺀다) · TS/JS `import x from 'p'`·`import {a as b} from 'p'`·`import * as n from 'p'`·`const x = require('p')`(상대 경로·`node:`는 뺀다, `@scope/name/sub`는 `@scope/name`, `name/sub`는 `name`) · Rust 맨 위 `use a::…`의 첫 조각들(`a`). Rust는 `use` 경로의 첫 조각이 패키지이고, 가져온 마지막 이름(별칭)과 그 첫 조각 둘 다 표에 든다(`use reqwest::Client` → `Client: reqwest`·`reqwest: reqwest`). 변수 → 패키지: 파일 맨 위와 함수 몸통의 `v = X(…)`·파이썬 `with X(…) as v`·`const v = new X(…)`·`let v = X::new(…)`처럼 오른쪽 식의 맨 앞 이름이 표에 있을 때 · 함수 매개변수의 타입 주석 안 이름 중 표에 있는 첫 것 · 파이썬 메서드면 그 클래스 `__init__`의 `self.a = X(…)`·`self.a: T`도 `self.a`로
   - **Java** — import 표는 비어 있다. 저장소의 `.java`(그래프 `files`, 경로 바이트 순)에서 `interface R extends B…`의 `B`(제네릭을 뗀 단순 이름)가 `REPO_BASES`에 맞으면 `R` → 그 키(처음 본 것). 알려진 타입 = `JAVA_TYPES` + 그 저장소 인터페이스. 함수마다(그것을 몸통에 바로 든 클래스·enum·record) 그 타입의 필드 · 매개변수 · 지역 변수(`T x` · `var x = new T(…)`)의 타입이 알려진 타입이면 변수 → 그 키
   - **Go** — import 표: 별칭, 없으면 `GO_NAMES`, 그것도 없으면 경로(`/vN`을 뗀)의 마지막 조각에서 앞 `go-`·뒤 `-go`를 뗀 것 → 경로(`/vN`을 뗀). `_`·`.` 별칭은 뺀다. 함수마다 매개변수·`var x T`의 타입 `p.T`(포인터·제네릭을 벗김)의 `p` · `x := …`(왼쪽 첫 이름)·`var x = …`의 오른쪽 식 맨 앞 이름(`p.F(…)`·`&p.T{…}`·`p.T{…}`) · 받는 쪽 `r`의 타입이 같은 파일의 구조체면 그 필드 `f`의 타입 `p.T` → `r.f`
2. **호출 순서에 장비** — 앱 코드(경로가 `NOT_APP`에 맞지 않고 화면 파일이 아닌 것)의 함수마다 steps의 `call` 중 `to`가 없는 것: `label`의 맨 앞 이름(글자 `[A-Za-z_][A-Za-z0-9_]*`. 파이썬은 `self.a`까지 한 덩어리 · Java는 앞 `this.`를 뗀 이름 · Go는 `a.b`가 변수 표에 있으면 그것을 먼저)으로 1의 변수, 없으면 import 표에서 패키지를 찾는다. TS/JS 맨 앞 이름이 `fetch`이고 표에 없으면 패키지 `fetch`. `LIBS[패키지]`가 있고 steps가 남긴 마지막 이름이 `io`에 맞으면 그 step의 `infra = "infra:" + id`. 장비 id마다 근거 `코드: {패키지들 — 처음 본 차례, ', '로} — {첫 파일}`(파일이 둘 이상이면 ` 외 N개 파일`)
3. **의존성** — 깊이 3까지 `package.json`(그 파일의 `dependencies`에 `FRONT_ONLY`가 있고 `SERVER_DEPS`가 없으면 건너뛴다)·`pom.xml`(`<dependency>…<groupId>g</groupId>…<artifactId>a<` → `g:a`, 앞뒤 공백 뗌)·`build.gradle(.kts)`(`implementation|api|runtimeOnly|compileOnly` 뒤 `(`와 따옴표 다음 `g:a`)·`go.mod`(줄 머리 `require `가 있거나 없이 `점이 든 호스트/경로 v숫자` → 경로)·`Cargo.toml`(이름이 `dependencies`로 끝나는 표의 키 — `[dependencies]`·`[dev-dependencies]`·`[workspace.dependencies]`)·`pyproject.toml`(`dependencies = [...]` 안 글자의 이름 부분)·`requirements*.txt`(줄의 이름 부분) → `DEPS` 첫 맞는 줄. 근거 `의존성: {이름} — {파일}`
4. **docker-compose** — 루트와 한 단 아래 폴더의 `docker-compose.yml|yaml`·`compose.yml|yaml`·`docker-compose.dev.yml` → view_arc `parseCompose`로 서비스·이미지·포트, `IMAGES` 첫 맞는 줄 → `where: container`. 근거 `docker-compose: {서비스} ({이미지}[, 포트 …]) — {파일}`. 같은 폴더 `.env`의 값으로 `${VAR:-기본}`을 채운다(그 파일이 저장소에 있을 때만 — 커밋되지 않은 `.env`는 서버가 모른다)
5. **설정 주소** — 루트와 한 단 아래의 `.env`·`.env.local`·`.env.development`(순위 4) · `.env.example`·`.env.sample`·`.env.template`(1) · 깊이 7까지 `config.py`·`settings.py`·`conf.py`·`application*.yml|yaml|properties`(3, `test/` 아래는 빼고 — 0장 폴더와 `bin obj tests test data docs`는 건너뛴다). 파일 차례는 폴더마다 위 차례, 그다음 깊이 걷기. 키·값에서 `scheme://` 주소 → 호스트·포트만(view_arc `hostOf`), `SCHEMES`(http면 `HTTP_KEYS`) 첫 맞는 줄. `…_HOST`·`…_PORT` 짝은 `HOST_KEYS`로. `where` = sqlite면 `local` · 호스트가 compose 서비스 이름이거나 이 PC 이름이면서 그 포트를 compose가 열었으면 `container` · 이 PC 이름이면 `local` · 그 밖 `external`. 근거 `설정: {파일} {키} → {호스트:포트}`
6. **ORM** — `schema.prisma`의 `provider`·`drizzle.config.*`의 `dialect` → 근거 `ORM 설정: {파일} ({종류})`
7. **합치기** — 같은 장비 id를 여러 곳에서 찾으면 근거를 다 모으고(처음 본 차례, 겹치면 하나), `where`·`host`는 순위가 큰 근거(코드·의존성·ORM 1 · compose 2 · 설정 그 순위)의 것으로(`host`가 비어 있으면 순위가 낮은 근거의 것으로 채운다), `name`은 더 구체적인 것(`DB`보다 다른 이름, 그다음 긴 것)
8. **노드** — 차례대로
   - 화면 함수가 하나라도 있거나 `web` 단위가 있으면 `{id: "infra:browser", kind: "browser", name: "브라우저", where: "local", host: null, evidence: ["화면 코드가 브라우저에서 돈다"], dir: null}`
   - `server` 단위마다 `{id: "infra:server:" + name, kind: "backend", name: framework + " 서버", where: "local", host: port가 있으면 "localhost:" + port, evidence: [framework + " — " + (dir 또는 "루트")], dir}` — 백엔드 함수(화면 파일이 아닌 다섯 언어 함수)가 있는데 `server` 단위가 없으면 `{id: "infra:backend", name: "백엔드 서버", evidence: ["백엔드 코드가 이 PC에서 돈다"], dir: ""}` 하나
   - 찾은 장비 — id 바이트 순. `{id: "infra:" + id, kind, name, where(없으면 api는 external, 그 밖 local), host(없으면 null), evidence, dir: null}`
9. **선** — 브라우저가 있으면 브라우저 → 서버(http 연결의 라우트 함수가 든 서버들, 없으면 모든 서버). 서버 → 장비(그 장비의 근거 파일이 든 서버들, 없으면 모든 서버 — 서버가 하나면 늘 그것). 파일이 든 서버 = `dir`이 그 파일 경로의 앞이면서 가장 긴 것. `protocol` = 장비의 protocol(compose·설정만으로 찾아 없으면 `LIBS`·`IMAGES` 줄의 것, 그래도 없으면 `""`), 브라우저 → 서버는 `HTTP`. `(from, to)` 차례로
10. `graph["infra"] = {"nodes": [...], "links": [...]}` · `→ graph`

**테스트 관점** `session.execute` → db 장비, `select()`는 아니다(io 정규식) · `self.repo = Repo(…)`가 아닌 `self.client = OpenAI()` 뒤 `self.client.chat.completions.create` → openai · Node `prisma.user.findMany` · Rust `sqlx::query(…).fetch_one` · 의존성만 있는 장비 · compose 이미지와 포트 · `.env.example`의 `DATABASE_URL`이 `postgresql://u:p@localhost:5432/x` → `localhost:5432`, 비밀번호가 남지 않는다 · 자리 표시 호스트는 버린다 · 화면만 있는 package.json의 의존성은 안 본다 · 순위로 where·host · 서버 둘이면 파일 폴더로 선을 가른다 · 테스트·스크립트 코드의 호출은 근거가 아니다 · **Java** `this.jdbc.query`(필드 타입) · `JpaRepository`를 넓힌 저장소의 `repo.findById` · **Go** 구조체 필드 `s.db.Query` · `rdb.Get`은 맞고 `rdb.Close`는 io에 안 맞는다 · `http.Get` · `pom.xml`·`go.mod` 의존성

---

## 3. 미결사항

- [x] Java·Go — tree-sitter 문법을 두 판에 더하고 라우트(Spring·net/http)·호출 순서를 붙인다(3차, 사용자 결정 2026-10-12) — 결정(2026-10-17, 「나머지 지금 해줘」): 0장 다섯 갈래로 넓혔다. 정의·호출 선은 [[SYNC-MS-011#codegraph.enrich]] 2i~2l, 라우트는 Spring 어노테이션과 Go 등록 호출만, 장비는 Java 받는 쪽 타입·Go import 경로로
- [ ] 호출 대상을 그래프의 선에서 이름으로만 고른다 — view_arc처럼 반환 타입·생성자로 더 푸는 것은 필요해지면
