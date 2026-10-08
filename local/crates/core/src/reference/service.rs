//! ReferenceService — SYNC-MS-015 (파이썬 판 SYNC-MS-003과 같은 이름·같은 처리). references 테이블만.
//! pk만 안다 — 표시 이름은 queries가. 본문은 `markdown`의 순수 함수로 자른다(spec 묶음을 부르지 않는다)

use std::collections::HashMap;

use indexmap::IndexMap;
use sqlx::PgConnection;

use super::model::ReferenceRow;
use super::repo;
use crate::errors::Problem;
use crate::markdown::{REF, cut_blocks, masked_lines};
use crate::types::{ExtractResult, RefEdge};

/// 행 → 간선 — 파이썬 `_edge`
fn edge(r: ReferenceRow) -> RefEdge {
    RefEdge {
        from_item_pk: r.from_item_id,
        to_item_pk: r.to_item_id,
        to_document_id: r.to_document_id,
        raw_target: r.raw_target,
        is_missing: r.is_missing,
        from_document_id: r.from_document_id,
    }
}

/// 풀어 본 대상 — (항목 pk, 문서 pk, 미존재)
type Target = (Option<i32>, Option<i32>, bool);

/// 참조 서비스 — 연결을 빌려 받는다. 트랜잭션은 부르는 쪽이 쥔다 (SYNC-STD-004#DEV-10)
pub struct ReferenceService<'c> {
    pub db: &'c mut PgConnection,
}

impl ReferenceService<'_> {
    /// 참조 글 → 대상 — `DOC` · `DOC#ITEM` · `#ITEM`(이 문서). `#` 뒤가 비면 문서 참조 (파이썬 `_resolve`)
    async fn resolve(&mut self, raw: &str, this_document_id: i32) -> Result<Target, Problem> {
        let (doc_part, item_part) = raw.split_once('#').unwrap_or((raw, ""));
        let doc_pk = if doc_part.is_empty() {
            Some(this_document_id)
        } else {
            repo::document_id_of(&mut *self.db, doc_part).await?
        };
        let Some(doc_pk) = doc_pk else {
            return Ok((None, None, true));
        };
        if item_part.is_empty() {
            return Ok((None, Some(doc_pk), false));
        }
        Ok(
            match repo::item_pk_of(&mut *self.db, doc_pk, item_part).await? {
                Some(pk) => (Some(pk), None, false),
                None => (None, None, true),
            },
        )
    }

    /// SYNC-MS-015#ReferenceService.extract
    ///
    /// 같은 참조는 같은 행으로 남긴다 — 지우고 다시 넣으면 매 저장이 전부 삭제·추가로 보인다.
    /// 있던 행의 대상은 다시 풀지 않는다(잇기·끊기는 `resolve_missing`·`mark_missing`의 몫)
    pub async fn extract(
        &mut self,
        document_id: i32,
        version_id: i32,
        body: &str,
        item_pks: &HashMap<String, i32>,
        upstream_doc_ids: &[String],
    ) -> Result<ExtractResult, Problem> {
        // 1·2. `[[ ]]`마다 어느 항목 블록 안인지 — 안쪽 블록이 나중에 덮는다(파이썬과 같은 차례)
        let mut owner: HashMap<usize, i32> = HashMap::new();
        for b in cut_blocks(body, |tok| item_pks.contains_key(tok)) {
            for ln in b.start_line - 1..b.end_line {
                owner.insert(ln, item_pks[&b.item_id]);
            }
        }
        let mut wanted: IndexMap<(Option<i32>, String), Target> = IndexMap::new();
        for (ln, line) in masked_lines(body).iter().enumerate() {
            for c in REF.captures_iter(line) {
                let raw = c[1].to_string();
                let t = self.resolve(&raw, document_id).await?;
                wanted.insert((owner.get(&ln).copied(), raw), t);
            }
        }
        // 5. frontmatter upstream → 문서 참조
        for d in upstream_doc_ids {
            let t = self.resolve(d, document_id).await?;
            wanted.insert((None, d.clone()), t);
        }
        // 6. 있던 행과 대조
        let existing: IndexMap<(Option<i32>, String), ReferenceRow> =
            repo::from_document(&mut *self.db, document_id, true)
                .await?
                .into_iter()
                .map(|r| ((r.from_item_id, r.raw_target.clone()), r))
                .collect();
        let mut out = ExtractResult::default();
        for (key, row) in &existing {
            if !wanted.contains_key(key) {
                repo::delete(&mut *self.db, row.id).await?;
                out.removed += 1;
            }
        }
        for ((from_item, raw), (to_item, to_doc, is_missing)) in &wanted {
            out.missing += i64::from(*is_missing);
            if let Some(row) = existing.get(&(*from_item, raw.clone())) {
                repo::set_extracted(&mut *self.db, row.id, version_id).await?;
                continue;
            }
            repo::insert(
                &mut *self.db,
                &repo::NewReference {
                    from_item_id: *from_item,
                    from_document_id: document_id,
                    to_item_id: *to_item,
                    to_document_id: *to_doc,
                    raw_target: raw,
                    is_missing: *is_missing,
                    extracted_version_id: version_id,
                },
            )
            .await?;
            out.added += 1;
        }
        Ok(out)
    }

    /// SYNC-MS-015#ReferenceService.count_missing_by_document
    pub async fn count_missing_by_document(
        &mut self,
        document_ids: &[i32],
    ) -> Result<HashMap<i32, i64>, Problem> {
        if document_ids.is_empty() {
            return Ok(HashMap::new());
        }
        Ok(repo::count_missing_by_document(&mut *self.db, document_ids).await?)
    }

    /// SYNC-MS-015#ReferenceService.upstream
    pub async fn upstream(&mut self, item_pk: i32) -> Result<Vec<RefEdge>, Problem> {
        Ok(repo::from_item(&mut *self.db, item_pk)
            .await?
            .into_iter()
            .map(edge)
            .collect())
    }
}
