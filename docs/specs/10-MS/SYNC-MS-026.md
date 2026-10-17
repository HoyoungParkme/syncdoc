---
doc_id: SYNC-MS-026
type: MS
title: MINISPEC — codegraph 흐름 — 호출 순서·라우트·화면 요청·장비·실행 단위 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-024, SYNC-MS-022, SYNC-INFRA-001]
---

# MINISPEC — codegraph 흐름 (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/codegraph/src/flow/`의 `mod.rs`·`steps.rs`·`routes.rs`·`infra.rs`(순수 함수 — DB 없음, 모듈은 `flow::steps`처럼 `flow` 아래) — 목록은 1장. 클래스 명세 [[SYNC-DOM-004]] 4.13. 파이썬 판 [[SYNC-MS-024]]과 **같은 이름·같은 처리·같은 결과(바이트)**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 같은지는 정답 파일(`tests/golden/codegraph.json`의 `flow` — 고정 시험 저장소)과 `cargo xtask codegraph-diff`(지금 커밋)가 본다.

**값(JSON) 위에서 더한다.** 흐름 키(`files`·`units`·`http`·`infra`, 함수의 `steps`·`route`)는 `Graph` 구조체가 아니라 직렬화한 그래프 값(`serde_json::Value`, 키 차례를 지킨다)에 더한다 — `Graph.files`(줄이기의 파일 이름 목록)와 흐름의 `files`(객체 목록)가 이름이 같아서다. 그래서 그래프 만들기는 커뮤니티 **뒤에** 흐름을 더한다([[SYNC-MS-017#pipeline.build_code_graph]]). 파이썬 판은 커뮤니티 앞이지만 두 단계는 서로의 키를 보지 않고, 객체 키의 차례는 비교(값 비교)와 저장(JSONB)이 따지지 않는다.

**파이썬 `ast` 대신 tree-sitter-python** — [[SYNC-MS-022]] 0장과 같은 파서(줄바꿈을 `\n`로 맞추고, 문법 오류면 그 파일을 건너뛴다). [[SYNC-MS-024]]가 `ast`로 읽는 것을 같은 뜻으로 —
- 호출 `Call` = `call` · 반환 `Return` = `return_statement` · 예외 `Raise` = `raise_statement`(글자는 `from` 앞 예외만) · `Await` = `await` · `Lambda` = `lambda` · 함수 정의는 `function_definition`(데코레이터를 벗긴), 클래스 `class_definition`
- 글자를 뽑는 식이 괄호로만 싸여 있으면 벗긴다 — `ast`에는 괄호 노드가 없다(괄호 튜플 `(a, b)`는 `tuple`이라 괄호째 — `ast.Tuple`도 3.8부터 괄호를 품는다)
- 매개변수 기본값의 Depends — `default_parameter`·`typed_default_parameter`의 값
- 변수 표의 주석 이름 — `ast.walk`처럼 너비 우선으로 처음 만나는 이름

**정규식** — 파이썬 판이 `re.ASCII`로 쓴 표는 `\w`·`\d`·`\s`를 ASCII 꼴로 바꿔 컴파일한다(regex crate의 `\w`는 유니코드다). 글자 공백 접기(steps 6)만 파이썬 `str.split()`의 공백(유니코드 — `syncdoc_pycompat`의 표)이다.

**표기** — `→` 반환·결과, `·` 같은 단계 안 구분.

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

**시그니처**
```rust
pub fn extend(src_dir: &Path, graph: &mut Value)
```

근거: [[SYNC-MS-024#flow.extend]] · 0장 「값 위에서 더한다」

**처리** [[SYNC-MS-024#flow.extend]] 1~9 그대로. 「예외」는 Rust에 없으므로 각 단계는 `Result`를 돌려 실패하면 그 키만 빈 값이다(파일을 못 읽거나 파싱하지 못한 것은 단계 안에서 그 파일만 건너뛴다 — 실패가 아니다)

**호출하는 것** [[#flow.files]] · [[#infra.units]] · [[#steps.steps]] · [[#routes.routes]] · [[#routes.http_links]] · [[#infra.infra]]

**테스트 관점** 정답 파일의 `flow`와 같다 · 키 여섯 · 대상도 장비도 없는 호출이 빠진다 · 흐름 사례(정답 파일의 `flow_cases` — 파이썬 판 흐름 시험의 입력과 답, `xtask/py/flow_cases.py`)가 모두 같다

---

#### flow.files 저장소의 코드 파일 목록

**시그니처**
```rust
pub fn files(src_dir: &Path) -> Vec<Value>
```

**처리** [[SYNC-MS-024#flow.files]] 그대로 — 링크는 따르지 않는다(`file_type`으로 본다)

**테스트 관점** 정답 파일과 같다

---

#### steps.steps 함수마다 호출 순서

**시그니처**
```rust
pub fn steps(src_dir: &Path, graph: &mut Value) -> HashMap<String, Vec<Option<String>>>
```

근거: [[SYNC-MS-024#steps.steps]] · 0장 「파이썬 `ast` 대신」

**처리** [[SYNC-MS-024#steps.steps]] 그대로. 장비 판정이 쓸 「호출마다 마지막 이름」(파이썬 판은 그래프의 `_idents`)은 돌려주는 값이다 — 그래프에 넣지 않는다

**출력** 함수 열쇠 → step마다 마지막 이름(호출이 아니면 없음)

**테스트 관점** 정답 파일과 같다 · 중첩 호출 차례 · `await` · 괄호 벗기기 · Depends 맨 앞 · 70자 자르기(한글) · 문법 오류 파일 → 빈 목록

---

#### routes.routes 함수마다 받는 라우트

**시그니처**
```rust
pub fn routes(src_dir: &Path, graph: &mut Value)
```

**처리** [[SYNC-MS-024#routes.routes]] 그대로

**테스트 관점** 정답 파일과 같다

---

#### routes.http_links 화면 요청을 라우트 함수에 잇는다

**시그니처**
```rust
pub fn http_links(src_dir: &Path, graph: &Value) -> Vec<Value>
```

**처리** [[SYNC-MS-024#routes.http_links]] 그대로

**테스트 관점** 정답 파일과 같다

---

#### infra.units 실행 단위 — 서버·화면·작업

**시그니처**
```rust
pub fn units(src_dir: &Path) -> Vec<Value>
```

**처리** [[SYNC-MS-024#infra.units]] 그대로. `package.json`은 키 차례를 지켜 읽는다

**테스트 관점** 정답 파일과 같다

---

#### infra.infra 장비·연결, 호출 순서에 닿는 장비 표시

**시그니처**
```rust
pub fn infra(src_dir: &Path, graph: &mut Value, idents: &HashMap<String, Vec<Option<String>>>)
```

**처리** [[SYNC-MS-024#infra.infra]] 그대로. 마지막 이름은 [[#steps.steps]]가 돌려준 것

**테스트 관점** 정답 파일과 같다 · 비밀번호가 남지 않는다

---

## 3. 미결사항

- [ ] tree-sitter-python과 `ast`의 차이가 싱크독 저장소 밖에서 드러나면(새 문법 등) 정답 파일에 그 꼴을 더하고 맞춘다
