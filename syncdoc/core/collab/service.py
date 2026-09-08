"""SYNC-MS-005 — CommentService. comments만. 본문은 인자로 받는다. 함수 8개."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from syncdoc.core.account.models import User
from syncdoc.core.collab.models import Comment
from syncdoc.core.collab.repository import CommentRepository
from syncdoc.core.errors import NotFound
from syncdoc.core.types import CommentSummary, UserRef


def line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode()).hexdigest()


class CommentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CommentRepository(session)

    def list(self, document_id: int) -> list[Comment]:
        """SYNC-MS-005#CommentService.list"""
        rows = self.repo.all_of(document_id)
        by_id = {c.id: c for c in rows}
        for c in rows:
            c.replies = []
        top: list[Comment] = []
        for c in rows:
            parent = by_id.get(c.parent_comment_id) if c.parent_comment_id else None
            (parent.replies if parent else top).append(c)
        return top

    def add(
        self,
        document_id: int,
        line_no: int,
        line_text: str,
        body: str,
        user: User,
        parent_id: int | None,
    ) -> Comment:
        """SYNC-MS-005#CommentService.add"""
        if parent_id is not None:
            parent = self.repo.by_id(parent_id)
            if parent is None or parent.document_id != document_id:
                raise NotFound("comment", parent_id)
        return self.repo.add(
            Comment(
                document_id=document_id,
                parent_comment_id=parent_id,
                line_no=line_no,
                line_hash=line_hash(line_text),
                body=body,
                author_user_id=user.id,
                is_resolved=False,
                created_at=datetime.now(UTC),
            )
        )

    def resolve(self, comment_id: int, resolved: bool) -> Comment:
        """SYNC-MS-005#CommentService.resolve"""
        c = self.repo.by_id(comment_id)
        if c is None:
            raise NotFound("comment", comment_id)
        c.is_resolved = resolved
        self.session.flush()
        return c

    def unresolved_count(self, document_id: int) -> int:
        """SYNC-MS-005#CommentService.unresolved_count"""
        return self.repo.unresolved_count_of(document_id)

    def unresolved_in(self, document_ids: list[int]) -> list[CommentSummary]:
        """SYNC-MS-005#CommentService.unresolved_in"""
        return [
            CommentSummary(
                id=c.id,
                doc_id=doc_id,
                line_no=c.line_no,
                excerpt=c.body[:80],
                author=UserRef(id=u.id, github_login=u.github_login, display_name=u.display_name),
                created_at=c.created_at,
            )
            for c, doc_id, u in self.repo.unresolved_in(document_ids)
        ]

    def relocate(self, document_id: int, old_body: str, new_body: str, old_version_no: int) -> int:
        """SYNC-MS-005#CommentService.relocate"""
        rows = self.repo.unresolved_of(document_id)
        if not rows:
            return 0
        new_hashes: dict[str, list[int]] = {}
        for no, line in enumerate(new_body.split("\n"), start=1):
            new_hashes.setdefault(line_hash(line), []).append(no)
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
