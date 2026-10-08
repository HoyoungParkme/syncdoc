---
doc_id: SYNC-MS-015
type: MS
title: MINISPEC — ReferenceService (Rust)
status: draft
upstream: [SYNC-DOM-004, SYNC-MS-003, SYNC-STD-004]
---

# MINISPEC — ReferenceService (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/core/src/reference/service.rs`의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.4. 파이썬 판 [[SYNC-MS-003]]과 **같은 이름·같은 처리**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10).

서비스는 연결을 빌려 받는다 — `ReferenceService<'c> { pub db: &'c mut PgConnection }`. 트랜잭션은 부르는 쪽이 쥔다([[SYNC-STD-004#DEV-10]]).

**카드 L6 몫은 미존재 참조 세기 하나다(2026-10-08)** — 프로젝트 요약([[SYNC-MS-018#queries.project_summary]])이 쓴다. 참조 뽑기·풀기(L7)와 조회(L8)는 그 카드가 더한다.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#ReferenceService.count_missing_by_document]] | 문서별 미존재 참조 수 |

---

## 2. 함수

#### ReferenceService.count_missing_by_document 문서별 미존재 참조 수

**시그니처**
```rust
pub async fn count_missing_by_document(&mut self, document_ids: &[i32]) -> Result<HashMap<i32, i64>, Problem>
```

근거: [[SYNC-MS-003#ReferenceService.count_missing_by_document]]

**처리** if 빈 목록 → 빈 지도 · `DB: references where from_document_id in ids and is_missing group by from_document_id` → `{문서 id: 수}` — 쿼리 한 번. 미존재가 없는 문서는 지도에 없다

**테스트 관점** (시험 DB) 미존재 둘 + 이어진 것 하나 → 2 · 미존재가 없는 문서는 키가 없다 · 빈 목록 → 쿼리 없이 빈 지도

---

## 3. 미결사항

없음. 나머지 참조 함수는 L7·L8이 더한다 — [[SYNC-CODE-002]].
