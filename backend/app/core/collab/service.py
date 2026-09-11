"""SYNC-MS-005 — CommentService. comments만. 본문은 인자로 받는다. 함수 8개."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.account.models import User
from app.core.collab.models import Comment
from app.core.collab.repository import CommentRepository
from app.core.errors import NotFound
from app.core.types import CommentSummary, UserRef


def line_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode()).hexdigest()


# 백업에 본문이 없다(저장소가 public — INFRA 6.1). body가 NOT NULL이라 무언가 들어가야
# 하는데, 빈 문자열은 화면에 빈 칸으로 떠 사람이 버그로 읽는다
RESTORED_BODY = "(백업에서 복원 — 본문은 백업에 없습니다)"


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

    def all_in_project(self, project_id: int) -> list[Comment]:
        """SYNC-MS-005#CommentService.all_in_project

        해결된 것도 준다. 정렬이 (문서, 작성시각)이라 부모가 자식보다 먼저 온다 (#16).
        """
        return self.repo.all_in_project(project_id)

    def restore(
        self,
        document_id: int,
        parent_comment_id: int | None,
        line_no: int,
        line_hash: str,
        author_user_id: int,
        is_resolved: bool,
        created_at: datetime,
        original_location: str | None,
    ) -> tuple[Comment, bool]:
        """SYNC-MS-005#CommentService.restore

        한 행씩 부른다 — 부르는 쪽이 새 id를 받아야 다음 행의 부모를 채운다.
        이미 있던 행도 돌려주는 이유가 같다: 반쯤 복원된 상태에서 다시 눌러도
        답글이 제 부모에 붙어야 한다.
        """
        existing = self.repo.by_key(document_id, author_user_id, created_at)
        if existing is not None:
            return existing, False
        row = self.repo.add(
            Comment(
                document_id=document_id,
                parent_comment_id=parent_comment_id,
                line_no=line_no,
                line_hash=line_hash,
                body=RESTORED_BODY,
                author_user_id=author_user_id,
                is_resolved=is_resolved,
                created_at=created_at,
                original_location=original_location,
            )
        )
        return row, True

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
