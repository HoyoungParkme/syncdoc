"""SYNC-MS-005 — CommentService. comments만. 본문은 인자로 받는다.

B1: relocate · count_unresolved · count_unresolved_by_document.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from syncdoc.core.collab.repository import CommentRepository


def line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode()).hexdigest()


class CommentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CommentRepository(session)

    def relocate(self, document_id: int, old_body: str, new_body: str) -> int:
        """SYNC-MS-005#CommentService.relocate"""
        rows = self.repo.unresolved_of(document_id)
        if not rows:
            return 0
        new_hashes: dict[str, list[int]] = {}
        for no, line in enumerate(new_body.split("\n"), start=1):
            new_hashes.setdefault(line_hash(line), []).append(no)
        old_version_no = self.repo.current_version_no(document_id) - 1
        moved = 0
        for c in rows:
            cands = new_hashes.get(c.line_hash, [])
            if len(cands) == 1:
                c.line_no = cands[0]
            elif cands:
                c.line_no = min(cands, key=lambda n: (abs(n - c.line_no), n))
            elif c.original_location is None:
                c.original_location = f"v{old_version_no}:{c.line_no}"
            if cands:
                moved += 1
        self.session.flush()
        return moved

    def count_unresolved(self, project_id: int) -> int:
        """SYNC-MS-005#CommentService.count_unresolved"""
        return self.repo.count_unresolved_in_project(project_id)

    def count_unresolved_by_document(self, document_ids: list[int]) -> dict[int, int]:
        """SYNC-MS-005#CommentService.count_unresolved_by_document"""
        return self.repo.count_unresolved_by_document(document_ids)
