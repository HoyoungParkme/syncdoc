---
doc_id: SYNC-STD-004
type: STD
title: 개발 규약 — 코드 파트 표준
status: draft
upstream: [SYNC-STD-001, SYNC-DOM-002, SYNC-DOM-003]
---

# 개발 규약

## 0. 이 문서가 다루는 것

명세 체인 10단계가 끝난 뒤 **코드로 가는 법**. 읽는 사람은 코드를 짜는 에이전트와 그걸 시키는 사람이다. 명세 작성 규약([[SYNC-STD-001]])이 "문서를 어떻게 쓰나"라면 이건 "그 문서로 코드를 어떻게 짜나".

세 가지를 정한다 — 코드가 지켜야 할 규칙(1·2장), 작업을 어떻게 자르나(3장), 언제 끝났다고 하나(4장). 프로젝트마다 다른 것(어느 슬라이스를 어떤 순서로)은 그 프로젝트의 CODE 문서([[SYNC-CODE-001]])에 둔다.

**원칙** — 코드는 MINISPEC을 옮긴 것이다. MINISPEC에 없는 함수를 만들면 MINISPEC을 먼저 고친다. 명세 없는 코드는 싱크독이 막으려는 바로 그것이다.

---

## 1. 코딩 규약

#### DEV-1 폴더와 파일은 클래스 명세 1장 그대로

`syncdoc/core/{묶음}/models.py · repository.py · service.py`, `core/pipeline.py`, `core/queries.py`, `web/routers/*.py`, `mcp/tools.py`, `infra/git.py · github.py`. 새 폴더를 만들려면 클래스 명세를 먼저 고친다.

테스트는 거울 구조 — `tests/core/spec/test_service.py`가 `core/spec/service.py`를 검사한다.

#### DEV-2 이름은 명세의 이름

클래스·메서드·테이블·컬럼 이름은 클래스 명세·ERD·DD·MINISPEC에 적힌 그대로. `SpecService.save`를 `save_document`로 바꾸지 않는다. 바꿔야 하면 명세부터.

Python: 클래스 `PascalCase`, 함수·변수 `snake_case`, 상수 `UPPER`. 테이블·컬럼 `snake_case`. React: 컴포넌트 `PascalCase`, 파일명 = 컴포넌트명.

**DTO와 ORM 이름이 같을 때** — DTO(API 응답·클래스 2.8)가 그 이름을 갖고, ORM 모델은 코드에서 `*Row`로 별칭한다: `Document`(DTO) / `DocumentRow`(ORM), `Version` / `VersionRow`. 서비스가 내부에서 돌려주는 건 Row, 입구로 나가는 건 DTO. MINISPEC 시그니처의 엔티티 이름은 Row다.

#### DEV-3 함수 docstring 첫 줄 = MINISPEC 항목 ID

```python
async def save_pipeline(...):
    """SYNC-MS-007#pipeline.save_pipeline"""
```

코드에서 명세로 돌아가는 유일한 고리. 검사기가 이걸로 MINISPEC↔코드 일치를 대조한다(4장).

`_`로 시작하는 비공개 헬퍼는 MINISPEC이 없어도 된다 — 단 **그 모듈 밖에서 부르지 않는다.** 밖에서 부르게 되면 MINISPEC 항목으로 올린다.

#### DEV-4 타입 힌트 필수, 형식은 도구가

모든 함수 시그니처에 타입 힌트. MINISPEC 시그니처와 같아야 한다. `from __future__ import annotations`를 모든 모듈에 — `list[...]` 표기가 MINISPEC과 같게. 포맷은 `ruff format`, 린트는 `ruff check` — 손으로 맞추지 않는다. `tests/`는 E501 무시, 중간 커밋은 F401 무시, `mcp/tools.py`는 E501 무시(도구 description이 API 명세 원문이라 길다) — 전부 pyproject에 명시. React는 `prettier` + `eslint`.

#### DEV-5 에러는 problem+json 타입 하나에 예외 클래스 하나

`urn:syncdoc:version-conflict` ↔ `VersionConflict(Problem)`. API 명세 2장 에러 표와 1:1. 새 에러는 API 명세부터.

#### DEV-6 로그에 남기지 않는 것

토큰 원문(MCP·GitHub), 비밀키, 본문 전체. 로그는 `doc_id`·`version_no`·`user_id`·`entry`·소요 시간까지.

#### DEV-16 async는 호출 관계가 정한다

- `infra/*`(subprocess·httpx)는 전부 `async def`
- DB만 만지는 서비스 메서드는 `def` (SQLAlchemy sync 세션. 2~3명 규모)
- **async 함수를 하나라도 부르면 그 함수도 `async def`** — `login_github`(github), `init_project`(git), `change_status`·`revert`(pipeline), `pipeline.*`, `queries.*`, 라우터·MCP 도구 전부
- MINISPEC 시그니처에 `async def`가 명시된다. 없으면 sync. 코드가 이걸 어기면 명세가 틀린 것 — 명세부터

#### DEV-17 React는 와이어프레임을 옮긴 것

함수가 MINISPEC 항목이듯, 화면은 와이어프레임 항목이다.

- **화면 하나 = 컴포넌트 하나.** `UI-10` → `pages/Todo.tsx`. 경로 없이 다른 화면 위에 뜨는 다이얼로그(`UI-12`)는 `components/`에 두고 여는 화면이 부른다
- **요소 번호 = `data-el`.** 와이어프레임 배치 HTML의 `data-el="2.1"`이 JSX의 같은 DOM 노드에 그대로. 반복 행(`2.1`, `4.1`)은 첫 행에만 — 배치 HTML과 같게
- **요소를 컴포넌트로 쪼개지 않는다.** 하위 요소는 JSX 블록. 두 화면 이상이 같은 요소를 쓸 때만 `components/`로 빼고 `el` prop으로 자기 번호를 받는다 (`DiffBox`가 UI-11 2.3·UI-12 2.1)
- 컴포넌트 첫 docstring에 그 화면의 요소 번호 목록 — DEV-3의 화면판
- 화면 간 진입은 URL로 — `#item-X`(항목 선택·패널), `?panel=comments`(패널 탭). 와이어프레임 "누르면" 열이 정한다
- 검사기 `tools/check_ui.py` — 컴포넌트의 `data-el` 집합과 UI-002 배치의 번호 집합을 대조(`dataset.el` 동적 부여도 읽는다). 사람이 확인할 때는 개발자 도구에서 `data-el`을 보고 요소 표와 대조

---

## 2. DB 물리 규칙

#### DEV-7 마이그레이션은 Alembic, 리비전 하나 = ERD 변경 하나

- 첫 리비전 `0001_initial` = ERD·DD 테이블 전부 (12개). 이후 리비전은 ERD·DD가 바뀔 때만
- 리비전 메시지 = 바뀐 ERD 항목: `0002_add_flags_upstream_impact`
- 열거형은 DB enum이 아니라 `varchar` + 앱 검증 (ERD 설계 규칙). 값 추가에 마이그레이션 없음
- `downgrade`를 반드시 쓴다. 되돌릴 수 없는 리비전은 리뷰에서 막는다

#### DEV-8 인덱스는 ERD·DD 3장에 적힌 것만

FK 전부, unique 제약 전부, 그리고 ERD·DD 3장 인덱스 표. 쿼리가 느리다고 코드에서 인덱스를 추가하지 않는다 — ERD·DD 3장에 먼저 적고 리비전을 만든다.

#### DEV-9 정규화는 3NF, 예외는 명시

모든 테이블 3NF. 의도적 비정규화는 둘뿐이고 ERD·DD에 이유가 있다 — `documents.current_body`(조회 캐시), `propagation_decisions.affected_pks`(저장 시점 스냅샷). 셋째가 생기면 ERD·DD에 이유를 적는다.

#### DEV-10 트랜잭션 경계는 MINISPEC이 정한 곳

`pipeline.save_pipeline` 6단계, `pipeline.rebuild` 3~9단계처럼 MINISPEC에 "한 트랜잭션"이라고 적힌 범위가 트랜잭션이다. 서비스 메서드는 트랜잭션도 세션도 열지 않는다 — 호출자의 것 안에서 돈다.

**세션 소유자는 입구 층이다** — `pipeline`·`queries`·라우터·MCP 도구가 `db.session_scope()`로 열고 닫는다. 서비스 하나만 부르는 라우터(SEQ-C1)는 라우터가 연다. `init_project`처럼 서비스가 트랜잭션을 언급하면 그건 "이 범위를 한 트랜잭션으로 묶어라"는 호출자에게 하는 지시다.

---

## 3. 작업 단위 — 슬라이스 카드

#### DEV-11 개발 순서는 기반 → 슬라이스 → 통합

```
A  기반 (수평)     뼈대 · DB 전체 · infra 어댑터 · 인증
                   기능이 아니라 땅이다. 수직으로 자를 수 없다
B  슬라이스 (수직)  시나리오 하나 = 슬라이스 하나. DB→서비스→조율자→입구→화면→테스트를 끝까지
                   시나리오 우선순위 순서. 앞 슬라이스가 만든 걸 뒤 슬라이스가 쓴다
C  통합·배포       외부 연결 · 첫 사용
```

계층별(전부 DB → 전부 서비스 → …)도 기능별(모든 걸 슬라이스로)도 아니다. 기반은 계층으로, 기능은 슬라이스로. 에이전트가 "아직 없는 걸 부르는" 일이 없으면서 B1이 끝나면 뭐가 돌아간다.

#### DEV-12 슬라이스 카드 형식

프로젝트 CODE 문서에 슬라이스마다 항목 하나. **에이전트는 카드 하나를 받아 카드 안 참조만 따라간다.**

```markdown
#### B3 상위 변경 추적

| 항목 | 내용 |
|---|---|
| 근거 | [[SYNC-SCN-001#S4]] · UC-H10 · H11 · S3 · S4 |
| 구현 함수 | [[SYNC-MS-004#TrackingService.detect_impact]] · … (MINISPEC 항목 전부) |
| API | [[SYNC-API-001#POST/api/decisions/{versionId}]] · … |
| 화면 | [[SYNC-UI-002#UI-10]] · UI-11 · UI-12 |
| 테스트 | 구현 함수의 테스트 관점 전부 + S4를 E2E로 |
| 스텁 | `함수 → 빈 결과` 또는 `함수 → ! not-implemented`. 어느 카드가 푸는지 함께 적는다 |
| 선행 | B1 · B2 |
| 완료 | (커밋 기록란. DEV-14) |
```

`구현 함수`에 없는 함수를 짜게 되면 카드가 틀린 것이다. 카드를 고치고, 필요하면 MINISPEC을 고친다.

**카드는 호출 그래프로 닫혀 있어야 한다.** 카드의 함수가 부르는 함수는 (a) 같은 카드에 있거나 (b) 선행 카드에서 완료됐거나 (c) 카드에 "스텁"으로 명시되어야 한다. 스텁은 둘뿐 — 빈 결과를 돌려주거나(`detect_impact → []`), `not-implemented` 에러를 내거나(`import_existing → 501`). 조용히 다르게 동작하는 스텁은 안 된다. **스텁을 해제해도 그것을 선언한 앞 카드는 미완으로 되돌리지 않는다** — 해제한 카드가 완료란에 해제 사실을 적는다. 계획된 인계이지 버그가 아니므로 DEV-15의 `fix(#이슈번호)`와도 다르다. 카드를 쓸 때 MINISPEC의 `호출하는 것`을 따라 닫힘을 확인한다.

#### DEV-13 에이전트 작업 순서

```
1. 카드를 읽는다. 선행 슬라이스가 완료인지 확인
2. 카드의 참조를 전부 연다 — 시나리오·유스케이스(왜) → MINISPEC(어떻게) → API·화면(입구)
3. MINISPEC 순서대로 구현. 함수 하나 = 커밋 하나. docstring에 항목 ID
4. MINISPEC 테스트 관점을 테스트로. 통과할 때까지
5. 슬라이스 E2E (시나리오 흐름 그대로)
6. 완료 조건(DEV-14) 확인 → CODE 문서 완료란에 기록 → 다음 카드
```

막히면 — 명세가 틀렸거나 모자란 것이다. 코드로 우회하지 않고 명세를 고치고 그 문서에 플래그가 붙게 한다.

**작업 메모(WORKLOG 등)는 명세를 이기지 못한다.** 되먹임으로 명세가 갱신되면 메모의 "결정"이 낡는다. 다시 시작할 때 명세를 먼저 읽고 메모를 맞춘 뒤 일한다.

---

## 4. 완료 조건

#### DEV-14 슬라이스가 끝났다는 것

| 조건 | 확인 방법 |
|---|---|
| 카드의 구현 함수가 전부 있다 | `docstring` 항목 ID 대조. MINISPEC에 있는데 코드에 없거나 그 반대면 미완 |
| 시그니처가 MINISPEC과 같다 | 검사기가 타입 힌트와 대조 |
| 테스트 통과 | 단위(테스트 관점) + E2E(시나리오) 전부 |
| 린트·포맷 통과 | `ruff check` · `ruff format --check` |
| 명세 통과 | `validate.py` 위반 0 (코드가 명세를 고쳤으면) |
| CODE 문서 기록 | 슬라이스 카드 완료란에 커밋 해시·PR·날짜(KST) |
| **화면 확인** (화면이 있는 카드만) | 에이전트가 `tsc`·`build`·API 테스트까지 하고, **사람이 브라우저에서 와이어프레임 요소 번호대로 눌러 본다.** 스크린샷을 PR에. 에이전트는 눈이 없다 — 이 조건만 사람 몫 |

여섯(화면 카드는 일곱) 다 되어야 다음 카드. 하나라도 빠지면 그 슬라이스는 미완이고 다음 슬라이스의 `선행` 조건이 안 된다.

#### DEV-15 커밋·PR

- 커밋 메시지 규격: `code(슬라이스): 함수명 — 요약` 예: `code(B3): TrackingService.detect_impact — diff 기반 판정`. 명세 커밋(`spec(…)`)과 구분
- 이미 끝난 슬라이스의 버그를 고칠 때는 `fix(#이슈번호): 요약`. 카드가 아니라 **이슈가 단위**다. 이슈에 무엇이 왜 틀렸는지와 어느 명세가 근거인지를 적고, 카드는 건드리지 않는다
- PR = 슬라이스 하나. PR 설명 = 카드 내용 + 완료 조건 체크
- 리뷰는 코드가 아니라 **카드 대조** — 구현 함수 목록과 코드가 맞는지, 테스트 관점이 테스트에 있는지

---

## 5. 미결사항

- [x] MINISPEC↔코드 일치 검사기 — `tools/check_code.py`. AST로 docstring 항목 ID·시그니처 대조. `--doc`·`--items`로 범위 지정
- [x] React 쪽 대응 — DEV-17. 화면 = 컴포넌트, 요소 = `data-el`. 검사기 `tools/check_ui.py` 완료 — B2~B4 화면 13개 대조(`--screens`로 범위 지정). DEV-14 여섯째(화면 확인) 앞에 돌린다
- [x] 슬라이스가 앞 슬라이스 코드를 고쳐야 할 때 — 앞 카드를 미완으로 되돌리나, 새 카드를 만드나 — 결정: 둘 다 아니다. 이슈 하나 = 수정 하나로 두고 `fix(#이슈번호)` 커밋. 카드는 그대로 (DEV-15)
