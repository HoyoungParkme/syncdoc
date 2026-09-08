"""SYNC-MS-003 — ReferenceService. references 테이블만. pk만 안다 — 표시 이름은 queries가."""

from __future__ import annotations

from sqlalchemy.orm import Session

from syncdoc.core.markdown import REF, cut_blocks, masked_lines
from syncdoc.core.reference.models import Reference
from syncdoc.core.reference.repository import ReferenceRepository
from syncdoc.core.types import ExtractResult, RefEdge


def _edge(r: Reference) -> RefEdge:
    return RefEdge(
        from_item_pk=r.from_item_id,
        to_item_pk=r.to_item_id,
        to_document_id=r.to_document_id,
        raw_target=r.raw_target,
        is_missing=r.is_missing,
    )


class ReferenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ReferenceRepository(session)

    def extract(
        self,
        document_id: int,
        version_id: int,
        body: str,
        item_pks: dict[str, int],
        upstream_doc_ids: list[str],
    ) -> ExtractResult:
        """SYNC-MS-003#ReferenceService.extract"""
        # 1·2. [[ ]]마다 어느 항목 블록 안인지 — 경계는 markdown.cut_blocks(item_pks 헤딩)
        wanted: dict[tuple[int | None, str], tuple[int | None, int | None, bool]] = {}
        owner: dict[int, int] = {}  # 줄 idx → from_item_pk
        for b in cut_blocks(body, lambda tok: tok in item_pks):
            for ln in range(b.start_line - 1, b.end_line):
                owner[ln] = item_pks[b.item_id]
        for ln, line in enumerate(masked_lines(body)):
            for raw in REF.findall(line):
                wanted[(owner.get(ln), raw)] = self._resolve(raw, document_id)
        # 5. frontmatter upstream → 문서 참조
        for doc_id in upstream_doc_ids:
            wanted[(None, doc_id)] = self._resolve(doc_id, document_id)
        # 6. 기존 행과 대조 — 없어진 건 delete, 새 건 insert, 있는 건 extracted_version_id 갱신
        existing = {(r.from_item_id, r.raw_target): r for r in self.repo.from_document(document_id)}
        added = removed = missing = 0
        for key, row in existing.items():
            if key not in wanted:
                self.repo.delete(row)
                removed += 1
        for key, (to_item, to_doc, is_missing) in wanted.items():
            missing += is_missing
            if key in existing:
                existing[key].extracted_version_id = version_id
                continue
            self.repo.add(
                Reference(
                    from_item_id=key[0],
                    from_document_id=document_id,
                    to_item_id=to_item,
                    to_document_id=to_doc,
                    raw_target=key[1],
                    is_missing=is_missing,
                    extracted_version_id=version_id,
                )
            )
            added += 1
        self.session.flush()
        return ExtractResult(added=added, removed=removed, missing=missing)

    def _resolve(self, raw: str, this_document_id: int) -> tuple[int | None, int | None, bool]:
        """참조 문자열 → (to_item_pk, to_document_id, is_missing). DOC · DOC#ITEM · #ITEM"""
        doc_part, _, item_part = raw.partition("#")
        doc_pk = this_document_id if doc_part == "" else self.repo.document_id_of(doc_part)
        if doc_pk is None:
            return None, None, True
        if not item_part:
            return None, doc_pk, False
        pk = self.repo.item_pk_of(doc_pk, item_part)
        return (pk, None, False) if pk is not None else (None, None, True)

    def downstream(self, item_pk: int) -> list[RefEdge]:
        """SYNC-MS-003#ReferenceService.downstream"""
        return [_edge(r) for r in self.repo.to_item(item_pk)]
