---
doc_id: SYNC-MS-014
type: MS
title: MINISPEC — SpecService · markdown (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-002, SYNC-MS-003, SYNC-STD-001, SYNC-STD-004]
---

# MINISPEC — SpecService · markdown (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/markdown.rs`와 `crates/core/src/spec/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.3. 파이썬 판 [[SYNC-MS-002]]·`backend/app/core/markdown.py`와 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

서비스는 연결을 빌려 받는다 — `SpecService<'c> { pub db: &'c mut PgConnection }`. DB가 필요 없는 함수는 연결 없이 부르는 연관 함수다(`SpecService::item_blocks(…)`). 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]).

**카드 L5 몫은 엔진이다(2026-10-08)** — 마크다운 넷, 항목 블록, 규약 검증, frontmatter 채움, diff. **카드 L6이 문서 목록(`list_by_project`)을, 카드 L7이 저장·조회(만들기·저장·문서·항목·이름·이웃·ID 발급·선행조건)를 더했다** — 저장 파이프라인([[SYNC-MS-017]])과 읽기 조합이 쓴다. **타입은 문자열이다(L7)** — 파이썬처럼 에이전트가 보낸 모르는 타입도 받아 `frontmatter.type` 위반까지 같은 답을 낸다(`check`·`validate`·`apply_frontmatter`, 상태 조건도 문자열 그대로 비교). 나머지 SpecService(문서·버전 조회, 만들기·저장, 상태, 휴지통…)는 쓰는 카드(L7·L8·L9)가 이 문서에 더한다.

**파이썬 판과 바이트까지 같다**(사용자 결정 2026-10-08 — 유니코드까지). 파이썬 엔진은 YAML·마크다운 라이브러리 없이 정규식·`difflib`이고 메시지에 `repr`이 들어간다. 그래서
- 문자 분류는 **파이썬 3.12(유니코드 15.0)의 표**를 쓴다 — 정규식의 `\s`·`\S`·`\d`·`\w`와 `str.strip()`. 표는 `crates/core/src/pycompat/`의 생성물이다(`cargo xtask unicode-tables`). Rust 표준의 `trim()`·`char::is_whitespace`·`regex`의 `\d`는 쓰지 않는다(`\x1c`~`\x1f`, 유니코드 판이 다르다)
- 길이·자르기는 코드 포인트다(파이썬 `len`·`[:40]`) · 메시지의 `{x!r}`는 파이썬 `repr`이다
- `difflib`은 알고리즘째 옮긴다 — `SequenceMatcher`(autojunk: 200줄 이상이면 1%+1번 넘게 나오는 줄을 뺀다)·`get_grouped_opcodes`·`unified_diff`
- 항목 패턴 표 `TYPES`·`SUBTYPES`는 파이썬과 글자 하나 다르지 않다 — 카드 L6의 `get_template`이 패턴 문자열을 그대로 내보낸다. Rust는 그 문자열을 위 표의 문자 클래스로 바꿔 컴파일한다

**맞춤은 정답으로 본다** — `cargo xtask spec-golden`이 파이썬 판으로 꼴 모음(약 150, 입력째 얼려 둔다)의 답을 `crates/core/tests/golden/spec.json`에 만들고 `cargo test`가 비교한다(`--check`로 다시 만들어 바이트 비교, [[SYNC-STD-004#DEV-7]]). `cargo xtask spec-diff`는 지금의 명세·템플릿 전부, 명세마다 git 이력 최근 다섯 판의 diff, 씨앗 고정 무작위 본문 2000을 두 판에 돌려 비교한다(커밋하지 않는다).

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#markdown.parse_frontmatter]] | frontmatter → 필드·줄 수 |
| [[#markdown.masked_lines]] | frontmatter·코드를 비운 줄 |
| [[#markdown.headings]] | 마스킹한 줄의 헤딩 |
| [[#markdown.cut_blocks]] | 항목 블록 자르기 |
| [[#SpecService.item_blocks]] | 본문 → 항목 블록 |
| [[#SpecService.validate]] | 규약 검증 — 삭제된 ID를 DB에서 |
| [[#SpecService.check]] | 규약 검사 — DB 없이 |
| [[#SpecService.apply_frontmatter]] | 생성 시 frontmatter 채움 |
| [[#SpecService.diff]] | 두 버전 diff — 본문을 DB에서 |
| [[#SpecService.diff_bodies]] | 두 본문 diff — DB 없이 |
| [[#SpecService.list_by_project]] | 프로젝트 문서 목록 |
| [[#SpecService.issue_doc_id]] | 문서 ID 발급 |
| [[#SpecService.precondition]] | DOM 선행조건 |
| [[#SpecService.get_document]] | 문서 조회 |
| [[#SpecService.get_item]] | 항목 블록 조회 |
| [[#SpecService.detect_deleted_items]] | 사라진 항목 찾기 |
| [[#SpecService.describe_items]] | 항목 pk → 표시 정보 |
| [[#SpecService.describe_documents]] | 문서 pk → 표시 정보 |
| [[#SpecService.create]] | 문서 행 생성 |
| [[#SpecService.save]] | 버전·항목 저장 |
| [[#SpecService.item_pks]] | 문서의 항목 pk 지도 |
| [[#SpecService.neighbors]] | 앞뒤 단계 문서 |
| [[#SpecService.resolve_item]] | doc_id·item_id → pk |

---

## 2. 함수

#### markdown.parse_frontmatter frontmatter → 필드·줄 수

**시그니처**
```rust
pub fn parse_frontmatter(body: &str) -> (IndexMap<String, String>, usize)
```

근거: [[SYNC-STD-001]] 1.2 · 파이썬 `markdown.parse_frontmatter`

**처리** 파이썬과 같다 — YAML이 아니다
1. 본문 머리가 `^---\n(.*?)\n---\n`(점은 줄바꿈까지, 가장 짧게)에 맞지 않으면 → `({}, 0)`. BOM·CRLF로 시작하는 본문은 맞지 않는다. 닫는 줄이 `--- `처럼 어긋나면 다음 `\n---\n`까지 먹는다
2. 가운데를 `\n`으로 나눠 줄마다 첫 `:` 앞뒤 — 키·값 모두 파이썬 `strip()`. 따옴표·`[A, B]`는 글자 그대로. 같은 키는 처음 자리에 마지막 값(파이썬 dict)
3. `→ (필드, 맞은 부분의 \n 수)` — 닫는 `---` 줄까지 센 줄 수

**출력** `(필드, 줄 수)` — 필드는 넣은 차례

**호출하는 것** 없음

**테스트 관점** 정답 파일과 같다 · `---\n---\n`은 없음 · `---\n\n---\n`은 빈 키 하나 · 콜론 없는 줄은 키 · 값의 `\x1c`는 파이썬처럼 벗긴다

---

#### markdown.masked_lines frontmatter·코드를 비운 줄

**시그니처**
```rust
pub fn masked_lines(body: &str) -> Vec<String>
```

근거: [[SYNC-STD-001]] 1.5 · [[SYNC-MS-002#SpecService.item_blocks]] 2

**처리** 파이썬과 같다 — 줄 수를 지킨다
1. 본문을 `\n`으로 나눈다(`\r`은 줄에 남는다) · frontmatter 줄은 빈 줄
2. 「```」로 시작하는 줄은 코드블록을 열고 닫으며 빈 줄이 된다 — 들여쓴 펜스·`~~~`는 펜스가 아니고 네 개 백틱도 연다·닫는다(CommonMark가 아니다) · 블록 안 줄은 빈 줄
3. 밖의 줄은 `` `[^`]*` ``를 왼쪽부터 같은 수(코드 포인트)의 공백으로

**출력** 본문 줄 수와 같은 줄들

**호출하는 것** [[#markdown.parse_frontmatter]]

**테스트 관점** 정답 파일과 같다 · 줄 수가 본문과 같다 · 한글 인라인 코드도 글자 수만큼 공백

---

#### markdown.headings 마스킹한 줄의 헤딩

**시그니처**
```rust
pub fn headings(body: &str) -> Vec<(usize, usize, String, String)>
```

근거: [[SYNC-STD-001]] 1.3

**처리** 마스킹한 줄마다 `^(#{1,6}) (\S+)(?: (.*))?$`(`\S`는 파이썬 공백 표의 여집합) → `(줄 번호 0부터, # 수, 첫 토큰, 나머지 또는 "")`. 탭·두 칸 띄움은 헤딩이 아니다

**호출하는 것** [[#markdown.masked_lines]]

**테스트 관점** 정답 파일과 같다 · 코드블록 안 헤딩은 없다 · `#### R1\r`(CRLF, 제목 없음)은 헤딩이 아니다

---

#### markdown.cut_blocks 항목 블록 자르기

**시그니처**
```rust
pub fn cut_blocks(body: &str, is_item: impl Fn(&str) -> bool) -> Vec<ItemBlock>
```

근거: [[SYNC-STD-001]] 1.3 · [[SYNC-MS-002#SpecService.item_blocks]] 4 · [[SYNC-MS-003#ReferenceService.extract]] 1

**처리** 파이썬과 같다 — 헤딩 가운데 `is_item(첫 토큰)`인 것마다 블록 끝 = 뒤 헤딩 중 레벨이 같거나 높은(#이 적거나 같은) 첫 것의 앞 줄, 없으면 본문 끝 · `ItemBlock { item_id, display_name: 나머지를 파이썬 strip(), level, start_line, end_line(1부터, 끝 포함), text: 원본 줄 범위를 \n으로 }`

**호출하는 것** [[#markdown.headings]]

**테스트 관점** 정답 파일과 같다 · 마지막 항목은 본문 끝까지 · 아래 레벨 소제목은 블록 안 · `display_name`은 마스킹한 줄에서(인라인 코드는 공백)

---

#### SpecService.item_blocks 본문 → 항목 블록

**시그니처**
```rust
pub fn item_blocks(body: &str, doc_type: DocType, title: Option<&str>) -> Vec<ItemBlock>
```

근거: [[SYNC-MS-002#SpecService.item_blocks]]

**처리** [[SYNC-MS-002#SpecService.item_blocks]]와 같다 — `title`이 없으면 본문 frontmatter의 `title` · 서브타입은 `SUBTYPES` 차례로 첫 키워드(제목에 들어 있으면) · 패턴은 `^(?:패턴|…)$` · 파싱은 `spawn_blocking` 없이 바로(부르는 쪽이 정한다)

**출력** 항목 블록 — 본문 차례

**호출하는 것** [[#markdown.parse_frontmatter]] · [[#markdown.cut_blocks]]

**테스트 관점** 정답 파일과 같다 · 지금의 명세 전부에서 파이썬과 같은 항목 ID · 코드블록 안 `#### R99`는 항목이 아니다 · DOM 「클래스」·「ERD」 제목이 패턴을 가른다

---

#### SpecService.validate 규약 검증 — 삭제된 ID를 DB에서

**시그니처**
```rust
pub async fn validate(&mut self, body: &str, doc_type: &str, entry: Entry, current_status: Option<DocStatus>) -> Result<ValidateResult, Problem>
```

근거: [[SYNC-MS-002#SpecService.validate]] · [[SYNC-STD-004#DEV-16]]

**처리**
1. `deleted` — 본문 frontmatter의 `doc_id`가 비었거나 그 문서가 없으면 빈 집합 · 문서의 `convention_error_detail`이 `file.deleted:`로 시작하거나 `trashed_at`이 있으면 빈 집합(되살림은 복구다) · 아니면 `DB: items where document_id and is_deleted`의 `item_id`
2. `→ SpecService::check(body, doc_type, entry, current_status, deleted)` — `spawn_blocking`에서(긴 본문 파싱)

**출력** `ValidateResult` — 위반이 비면 통과

**예외** DB 오류 → `! Internal` · 규약 위반은 결과로 돌려준다

**호출하는 것** [[#markdown.parse_frontmatter]](본문의 `doc_id`) · [[#SpecService.check]]

**테스트 관점** (시험 DB) 삭제된 `R15`를 다시 쓰면 `item.reused` · 같은 본문을 `web_revert`로 → 통과 · 문서가 `file.deleted:`·휴지통이면 통과 · 없는 문서·빈 `doc_id`는 삭제 집합이 비었다

---

#### SpecService.check 규약 검사 — DB 없이

**시그니처**
```rust
pub fn check(body: &str, doc_type: &str, entry: Entry, current_status: Option<DocStatus>, deleted: &HashSet<String>) -> ValidateResult
```

근거: [[SYNC-MS-002#SpecService.validate]] 1~8 · [[SYNC-STD-001]] 3장·4장

**처리** [[SYNC-MS-002#SpecService.validate]]의 처리를 같은 차례·같은 문장으로 — 삭제된 ID만 인자로 받는다
- 위반 차례: frontmatter(필드 → `type` → `status` → `doc_id` → `upstream` → `title.subtype` → `status_change`) → 헤딩 차례로(`duplicate`·`reused`·`padding` 또는 `punct`·`pattern`) → `ref.format` 차례로
- 경고 차례: `section.unnumbered` → `section.missing`(필수 절 차례) → `item.none` → `entity.mismatch`(이름 차례) → `layer.table` → `constraint.source`
- `item.padding`은 파이썬의 `(?<![0-9])0\d` — 앞이 ASCII 숫자가 아닌 `0` 뒤에 파이썬 `\d`(룩비하인드는 손으로 본다)
- 문장의 `{x!r}`는 파이썬 `repr`, `None`은 `None` · `section.unnumbered`의 글은 앞 40 코드 포인트

**출력** `ValidateResult { violations: [Violation { line, rule, message }], warnings: [Warning { rule, message }] }`

**호출하는 것** [[#markdown.parse_frontmatter]] · [[#markdown.masked_lines]] · [[#SpecService.item_blocks]]

**테스트 관점** 정답 파일·무작위 차이 시험과 같다 · 지금의 명세 전부 위반 0·경고 0 · frontmatter 없는 본문 → 위반 하나 · `R01` → `item.padding` · `R1.` → `item.punct` · MCP에서 status 바꿈 → `frontmatter.status_change`, GitHub는 통과 · 필수 절 하나 빼면 경고 하나 · INFRA `출처:` 줄이 없는 제약 → `constraint.source` · DOM 클래스 명세에 층 표가 없으면 `layer.table`

---

#### SpecService.apply_frontmatter 생성 시 frontmatter 채움

**시그니처**
```rust
pub fn apply_frontmatter(body: &str, doc_id: &str, doc_type: &str, status: DocStatus) -> Result<String, Problem>
```

근거: [[SYNC-MS-002#SpecService.apply_frontmatter]]

**처리** [[SYNC-MS-002#SpecService.apply_frontmatter]]와 같다 — frontmatter가 없으면 첫 `# ` 헤딩(원본 본문에서, 파이썬 `strip()`)이나 `doc_id`를 제목으로 네 줄을 앞에 붙인다 · 있으면 `doc_id`·`type`·`status` 줄의 첫 것만 `키: 값`으로 바꾸고 없는 키는 그 차례로 끝에 더한다 · 다른 줄은 그대로

**예외** `doc_id`가 있고 발급한 것과 다르면 `! ConventionViolation [frontmatter.doc_id: 발급 {doc_id}와 다름: {본문의 것}]`(422, 경고 빈 목록)

**호출하는 것** [[#markdown.parse_frontmatter]]

**테스트 관점** 정답 파일과 같다 · frontmatter 없는 본문 → 네 필드 · `doc_id` 비움 → 채움 · 다른 `doc_id` → 위반 · `upstream`은 그대로

---

#### SpecService.diff 두 버전 diff — 본문을 DB에서

**시그니처**
```rust
pub async fn diff(&mut self, doc_id: &str, from_no: i32, to_no: i32, context: usize) -> Result<Diff, Problem>
```

근거: [[SYNC-MS-002#SpecService.diff]] · [[SYNC-STD-004#DEV-16]]

**처리**
1. `DB: documents where doc_id` · if 없음 → `! NotFound { resource: "document", id: doc_id }`
2. `DB: versions where document_id and version_no in (from_no, to_no)` · 차례로 if 없음 → `! NotFound { resource: "version", id: "{doc_id} v{no}" }`
3. `→ SpecService::diff_bodies(본문 둘, doc_type, from_no, to_no, context)` — `spawn_blocking`에서

`context` 기본은 파이썬 `DIFF_CONTEXT_LINES`와 같은 3 — `spec::DIFF_CONTEXT_LINES`

**예외** `not-found`(문서·판) · DB 오류 → `! Internal`

**호출하는 것** [[#SpecService.diff_bodies]]

**테스트 관점** (시험 DB) 판 둘 → 파이썬과 같은 hunk · 같은 판 → hunk 없음 · 없는 판·없는 문서 → `not-found`(파이썬과 같은 `id`)

---

#### SpecService.diff_bodies 두 본문 diff — DB 없이

**시그니처**
```rust
pub fn diff_bodies(from: &str, to: &str, doc_type: DocType, from_no: i32, to_no: i32, context: usize) -> Diff
```

근거: [[SYNC-MS-002#SpecService.diff]] 2~5 · #345

**처리** [[SYNC-MS-002#SpecService.diff]] 2~5와 같다
1. 본문마다 항목 ID → 블록 글(같은 ID는 처음 자리에 마지막 글), 항목 밖 줄이 공백만이 아니면 `None` 키 하나 — 각 본문의 frontmatter `title`로 패턴을 고른다
2. 차례: 새 본문의 키 → 옛 본문에만 있는 키 → `None`은 맨 뒤
3. 두 글의 「strip해 빈 줄을 뺀 줄들」이 같으면 건너뜀 · 한쪽이 비면 다른 쪽 글을 끝 `\n`을 떼고 줄마다 전부 `add` 또는 `del` · 아니면 `unified_diff(n=context)`에서 머리 두 줄과 `@@`를 뺀 줄 — 첫 글자 `+`·`-`·` ` → `add`·`del`·`ctx`
4. `→ Diff { from_version, to_version, hunks: [Hunk { item_id, lines, downstream_count: 0 }] }`

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** 정답 파일·무작위 차이 시험·git 이력 diff와 같다 · 항목 하나만 고침 → hunk 하나 · 공백만 바꿈 → 없음 · 항목 추가 → 전부 `add` · 역방향 → op가 뒤집힘 · `---` 줄 삭제 → `(del, ---)`(#345) · 200줄 넘는 블록(autojunk)도 파이썬과 같다 · `context`를 키우면 `ctx`만 는다

---

#### SpecService.list_by_project 프로젝트 문서 목록

**시그니처**
```rust
pub async fn list_by_project(&mut self, project_id: i32, stage: Option<i32>, status: Option<&str>, has_convention_error: Option<bool>) -> Result<Vec<DocumentSummary>, Problem>
```

근거: [[SYNC-MS-002#SpecService.list_by_project]] · [[SYNC-MS-018#queries.project_summary]]

**처리** [[SYNC-MS-002#SpecService.list_by_project]]와 같다 — `DB: documents where project_id` 가운데 휴지통이 아닌 것 · 조건(단계 번호 — `STD`는 단계 없음 · 상태 · 규약 오류) · 문서마다 최근 버전 하나(쿼리 한 번)의 작성자 `AuthorRef { kind, user_id, instructed_by_id, via }` · `incomplete_warnings`는 JSON 목록을 읽는다(없으면 빈 목록) · (단계, 없으면 99) → `doc_id` 차례

**출력** `DocumentSummary` — `counts`는 비고 이름 붙은 작성자(`author`)는 없다 — `queries`가 채운다

**테스트 관점** (시험 DB) 단계·`doc_id` 차례, `STD`는 맨 뒤 · 휴지통 문서는 안 나온다 · 작성자는 최근 버전의 것 · 버전이 없으면 작성자 없음 · `stage=6` → DOM만 · `status` 조건

---

#### SpecService.issue_doc_id 문서 ID 발급

**시그니처**
```rust
pub async fn issue_doc_id(&mut self, project_id: i32, code: &str, doc_type: &str) -> Result<String, Problem>
```

근거: [[SYNC-MS-002#SpecService.issue_doc_id]]

**처리** `DB: documents where project_id and doc_type`(휴지통 것까지)의 `doc_id` 끝 `-` 뒤 수의 가장 큰 것(없으면 0) + 1 · `→ "{code}-{doc_type}-{n:03}"`

**테스트 관점** 첫 문서 → `001` · 휴지통 문서도 센다 · 타입마다 따로

---

#### SpecService.precondition DOM 선행조건

**시그니처**
```rust
pub async fn precondition(&mut self, project_id: i32, doc_type: &str, title: &str) -> Result<Option<(String, Vec<String>)>, Problem>
```

근거: [[SYNC-MS-002#SpecService.precondition]] · [[SYNC-STD-001]] 2.6

**처리** [[SYNC-MS-002#SpecService.precondition]]과 같다 — DOM이 아니면 없음 · 서브타입 「클래스」 → 프로젝트에 API 문서가 하나라도(휴지통 것까지) 있으면 없음, 아니면 `("API 문서(REST 또는 MCP) — 클래스의 메서드는 API가 정한다", DOM 문서 ID들 정렬)` · 「ERD」 → 제목에 「클래스」인 DOM 문서가 있으면 없음, 아니면 `("DOM 클래스 명세 — 테이블은 엔티티 클래스에서 나온다", …)` · 그 밖 → 없음

**테스트 관점** API 없는 프로젝트의 「클래스 명세」 → 요구와 DOM 목록 · API 하나 있으면 없음 · 클래스 명세 없이 「ERD」 → 요구 · 「도메인 모델」·DOM 아닌 타입 → 없음

---

#### SpecService.get_document 문서 조회

**시그니처**
```rust
pub async fn get_document(&mut self, doc_id: &str) -> Result<Document, Problem>
```

근거: [[SYNC-MS-002#SpecService.get_document]]

**처리** `DB: documents where doc_id` · 없으면 `! NotFound { resource: "document", id: doc_id }` · 항목은 지우지 않은 것을 id 차례로 · 최근 판의 해시·id·작성자 · `→ Document`(문서 요약 + 본문·해시·규약 오류 문장·항목) — 휴지통 문서도 돌려준다

**테스트 관점** 항목은 id 차례·지운 것 없음 · 해시는 최근 판 · 없는 문서 → `not-found`

---

#### SpecService.get_item 항목 블록 조회

**시그니처**
```rust
pub async fn get_item(&mut self, doc_id: &str, item_id: &str) -> Result<ItemView, Problem>
```

근거: [[SYNC-MS-002#SpecService.get_item]] · [[SYNC-API-002#get_item]]

**처리** [[SYNC-MS-002#SpecService.get_item]]과 같다 — `get_document` · `item_id`의 `~`를 `/`로 · `DB: items where document_id and item_id`(지운 것까지) · 없으면 `! NotFoundWithItems { resource: "item", id: "{doc_id}#{item_id}", available_items: 지우지 않은 항목 ID들 }` · 지웠으면 `! ItemDeleted { deleted_at }` · 본문의 그 항목 블록 · `→ ItemView`

**테스트 관점** 마지막 항목은 문서 끝까지 · 아래 레벨 소제목은 블록 안 · 없는 항목 → `available_items` · 지운 항목 → `item-deleted` · `GET~api~me` → `GET/api/me`

---

#### SpecService.detect_deleted_items 사라진 항목 찾기

**시그니처**
```rust
pub async fn detect_deleted_items(&mut self, document: &Document, body: &str) -> Result<Vec<i32>, Problem>
```

근거: [[SYNC-MS-002#SpecService.detect_deleted_items]]

**처리** 새 본문의 항목 ID 집합(문서 타입, 제목은 본문 frontmatter) · `DB: items where document_id and not is_deleted`(id 차례) 가운데 집합에 없는 것의 pk

**호출하는 것** [[#SpecService.item_blocks]]

**테스트 관점** 항목 하나 지움 → pk 하나 · 제목만 바꿈·순서만 바꿈 → 빈 목록

---

#### SpecService.describe_items 항목 pk → 표시 정보

**시그니처**
```rust
pub async fn describe_items(&mut self, item_pks: &[i32]) -> Result<HashMap<i32, ItemRef>, Problem>
```

근거: [[SYNC-MS-002#SpecService.describe_items]]

**처리** 빈 목록 → 빈 지도 · `DB: items join documents where id in pks` → `{pk: ItemRef { doc_id, item_id, display_name, is_deleted, deleted_at }}`

**테스트 관점** 지운 항목도 `is_deleted`와 함께 · 없는 pk는 지도에 없다

---

#### SpecService.describe_documents 문서 pk → 표시 정보

**시그니처**
```rust
pub async fn describe_documents(&mut self, document_ids: &[i32]) -> Result<HashMap<i32, DocRef>, Problem>
```

근거: [[SYNC-MS-002#SpecService.describe_documents]]

**처리** 빈 목록 → 빈 지도 · `DB: documents where id in ids` → `{id: DocRef { document_id, doc_id, title: frontmatter 제목(비면 doc_id), stage, status }}`

**테스트 관점** 제목 없는 문서 → doc_id

---

#### SpecService.create 문서 행 생성

**시그니처**
```rust
pub async fn create(&mut self, project_id: i32, doc_id: &str, doc_type: &str, body: &str, commit_hash: &str, author: &Author, message: &str, validate_result: &ValidateResult) -> Result<VersionRow, Problem>
```

근거: [[SYNC-MS-002#SpecService.create]]

**처리** [[SYNC-MS-002#SpecService.create]]와 같다 — `documents insert`(상태는 frontmatter가 `draft`·`approved`면 그것, 아니면 `draft` · 판 1 · 규약 결과 — `has_convention_error`, `convention_error_detail = "rule: message"`를 줄마다, `incomplete_warnings = 경고 「rule: message」들의 JSON 목록`(ensure_ascii 없이, 비면 없음)) · 항목 블록마다 `items insert`(블록 차례) · `versions insert`(판 1 · `author_kind` · 작성자·지시자 · `via`는 입구를 접은 것 — `web_revert`·`web_status` → `web` · message · `created_at=now`)

**테스트 관점** 문서·항목·판 행 · 경고가 `incomplete_warnings`에 · `via=mcp`

---

#### SpecService.save 버전·항목 저장

**시그니처**
```rust
pub async fn save(&mut self, document: &Document, body: &str, commit_hash: &str, author: &Author, message: &str, deleted_item_pks: &[i32], validate_result: &ValidateResult) -> Result<VersionRow, Problem>
```

근거: [[SYNC-MS-002#SpecService.save]]

**처리** [[SYNC-MS-002#SpecService.save]]의 `mcp` 갈래와 같다 — 판 = 현재 + 1 · `versions insert` · 항목 블록마다 있으면 이름을 고치고 **되살리고**(`is_deleted=false`·`deleted_at` 없음), 없으면 `insert` · `deleted_item_pks`는 `is_deleted=true`·`deleted_at=now` · 완료 문서이고 본문이 바뀌었으면 상태를 `draft`로 · `status_changes insert(approved → draft, 바꾼 사람, via, "본문 수정으로 자동 강등", 커밋 없음)` · 본문·판·상태·규약 결과 · 휴지통에서 나온다 · `updated_at=now`

**다른 점** 재구축(`rebuild`)·상태 커밋 해시(`github` 입구)는 L11 — 받지 않는다

**테스트 관점** v2 · 지운 항목 표시 · 같은 ID가 다시 나타나면 되살림 · 완료 문서 → 초안·상태 변경 행 하나

---

#### SpecService.item_pks 문서의 항목 pk 지도

**시그니처**
```rust
pub async fn item_pks(&mut self, document_id: i32) -> Result<HashMap<String, i32>, Problem>
```

근거: [[SYNC-MS-002#SpecService.item_pks]]

**처리** 지우지 않은 항목의 `{item_id: pk}`

**테스트 관점** 지운 항목은 없다

---

#### SpecService.neighbors 앞뒤 단계 문서

**시그니처**
```rust
pub async fn neighbors(&mut self, doc_id: &str) -> Result<(Option<String>, Option<String>), Problem>
```

근거: [[SYNC-MS-002#SpecService.neighbors]]

**처리** 없는 문서 → `not-found` · 단계 없음(STD) → 둘 다 없음 · 휴지통이 아닌 같은 프로젝트 문서 가운데 앞 단계·뒤 단계 각각의 가장 작은 `doc_id`(바로 이웃 단계만)

**테스트 관점** RFQ·PRD·SCN 하나씩 → PRD의 앞뒤 · 이웃 단계가 비면 없음

---

#### SpecService.resolve_item doc_id·item_id → pk

**시그니처**
```rust
pub async fn resolve_item(&mut self, doc_id: &str, item_id: &str) -> Result<i32, Problem>
```

근거: [[SYNC-MS-002#SpecService.resolve_item]]

**처리** 문서·항목(지운 것까지)이 없으면 `! NotFound { resource: "item", id: "{doc_id}#{item_id}" }` · 지웠으면 `! ItemDeleted` · `→ pk`. `~`는 바꾸지 않는다(파이썬과 같다)

**테스트 관점** 없는 문서도 `item` not-found · 지운 항목 → `item-deleted`

---

## 3. 미결사항

없음. 나머지 SpecService 함수는 쓰는 카드가 더한다 — [[SYNC-CODE-002]].
