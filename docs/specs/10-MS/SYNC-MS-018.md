---
doc_id: SYNC-MS-018
type: MS
title: MINISPEC — queries — 읽기 조합 (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-008, SYNC-API-001, SYNC-API-002]
---

# MINISPEC — queries (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/queries.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.7. 파이썬 판 [[SYNC-MS-008]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 여러 묶음의 서비스를 불러 응답 하나로 엮는다 — 쓰지 않는다.

**카드 L6 몫은 프로젝트 요약 하나다(2026-10-08)** — `init_project`·`POST /api/projects`가 돌려주고 `GET /api/projects`가 목록으로 낸다(사용자 결정 — 요약 전부, 문서가 있어도 맞게). 나머지 조회(L8)는 그 카드가 더한다.

**다른 점(전체)** 파이썬은 함수마다 세션을 연다 — Rust는 부르는 쪽의 연결을 받는다(첫 인자 `db`).

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#queries.project_summary]] | 내 프로젝트들의 요약 — 11단계·STD 문서·수 |

---

## 2. 함수

#### queries.project_summary 내 프로젝트들의 요약

**시그니처**
```rust
pub async fn project_summary(db: &mut PgConnection, user: &UserRow) -> Result<Vec<ProjectSummary>, Problem>
```

근거: [[SYNC-MS-008#queries.project_summary]] · [[SYNC-UC-001#UC-H14]] · [[SYNC-API-001#GET/api/projects]]

**처리** [[SYNC-MS-008#queries.project_summary]]와 같다
1. 프로젝트마다(`ProjectService.list_owned` — 코드 차례) `docs = SpecService.list_by_project(id)` · `per_doc = ReferenceService.count_missing_by_document(docs의 id)`
2. 단계 1~11(`RFQ`…`CODE`)마다 그 단계 문서 — `status`는 하나라도 `draft`면 `draft`, 다 `approved`면 `approved`, 없으면 없음 · `gate_warning`은 문서가 있고 앞 단계 가운데 문서가 있는데 `approved`가 아닌 것이 있나 · `broken_count`는 그 단계 문서들의 미존재 참조 합
3. `counts` — `broken_ref`(미존재 참조 합)·`convention_errors`(규약 오류 문서 수)·`incomplete`(경고 있는 문서 수) · `std_docs` — 타입 `STD` 문서 · `updated_at` — 문서들의 가장 늦은 것, 없으면 없음 · `remote_url` — 서버 저장이면 없음
4. `updated_at`이 있는 것을 먼저 그 내림차순, 없는 것은 뒤에 원래 차례로(파이썬 안정 정렬)

**출력** `ProjectSummary { code, name, storage, remote_url, stages[11], std_docs, counts, updated_at }`. 입구가 직렬화한다 — REST는 pydantic 꼴(`Z`), MCP는 파이썬 `_project_json` 꼴(`+00:00`, `std_docs`의 `last_author`는 늘 없음 — 파이썬 판에서 이 경로는 작성자 이름을 붙이지 않는다)

**호출하는 것** [[SYNC-MS-013#ProjectService.list_owned]] · [[SYNC-MS-014#SpecService.list_by_project]] · [[SYNC-MS-015#ReferenceService.count_missing_by_document]]

**테스트 관점** (시험 DB) 새 프로젝트 → 11칸 모두 없음·수 0·`updated_at` 없음 · 단계에 초안 하나 + 완료 하나 → 그 단계 `draft` · 앞 단계 초안 뒤 단계 문서 → `gate_warning` · 휴지통 문서는 안 센다 · 미존재 참조 → 단계 `broken_count`와 `counts.broken_ref` · `STD` 문서는 `std_docs`에만(단계 밖) · 두 프로젝트 → 최근 것 먼저, 문서 없는 것은 뒤 · 남의 프로젝트는 안 나온다

---

## 3. 미결사항

없음. 나머지 조회는 L8이 더한다 — [[SYNC-CODE-002]].
