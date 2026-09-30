"""SYNC-MS-011 — core/codegraph/service.py. CodeGraphService — code_graphs 한 행을 읽고 쓴다.

프로젝트마다 최신 하나(2026-09-30 사용자 결정). 성공하면 통째로 바꿔 끼우고, 실패하면 옛
그래프를 두고 이유만 남긴다. 추출·줄이기·보강·대조는 graph.py(DB를 모른다)가 한다.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.codegraph.models import CodeGraph
from app.core.codegraph.repository import CodeGraphRepository
from app.core.errors import NotFound
from app.core.types import CodeText
from app.infra import git
from app.infra.git import GitError

# 한 번에 읽는 줄 상한 — 코드 탭과 질문 탭 read_code가 같이 (2026-09-30 사용자 결정)
MAX_LINES = 300
# 커밋돼 있어도 읽어 주지 않는 이름 — 키·인증서·비밀 설정 (카드 AZ 결정, 여기 한곳에 둔다)
DENY = (".env*", "*.pem", "*.key", "id_rsa*", "*.p12", "*secret*")


def _empty() -> dict:
    return {"functions": [], "calls": []}


class CodeGraphService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CodeGraphRepository(session)

    def get(self, project_id: int) -> CodeGraph | None:
        """SYNC-MS-011#CodeGraphService.get"""
        return self.repo.get(project_id)

    def save(self, project_id: int, commit_hash: str, source: str, graph: dict) -> CodeGraph:
        """SYNC-MS-011#CodeGraphService.save

        한 행을 한 번에 바꿔 끼운다 — 반쯤 바뀐 그래프를 읽는 일이 없다. 앞의 실패 이유는 지운다.
        """
        row = self.repo.get(project_id) or self.repo.add(
            CodeGraph(project_id=project_id, graph=_empty(), built_at=now_utc())
        )
        row.commit_hash = commit_hash
        row.source = source
        row.graph = graph
        row.function_count = len(graph.get("functions", []))
        row.call_count = len(graph.get("calls", []))
        row.built_at = now_utc()
        row.error = None
        self.session.flush()
        return row

    def fail(self, project_id: int, commit_hash: str, reason: str) -> CodeGraph:
        """SYNC-MS-011#CodeGraphService.fail

        옛 그래프·커밋·출처는 그대로 — 이유만. 첫 빌드부터 실패했으면 빈 그래프로 행을 만든다.
        """
        row = self.repo.get(project_id) or self.repo.add(
            CodeGraph(project_id=project_id, graph=_empty(), function_count=0, call_count=0)
        )
        row.error = f"{commit_hash[:7]}: {reason}"[:300]
        row.built_at = now_utc()
        self.session.flush()
        return row

    def delete_by_project(self, project_id: int) -> None:
        """SYNC-MS-011#CodeGraphService.delete_by_project"""
        self.repo.delete_by_project(project_id)

    async def read(
        self, project_id: int, workdir: Path, path: str, start: int, end: int | None
    ) -> CodeText:
        """SYNC-MS-011#CodeGraphService.read

        그래프를 만든 커밋의 **커밋된 파일만** 읽는다 — 작업 사본·.gitignore 파일은 못 본다.
        비밀 꼴·저장소 밖 경로는 없는 파일과 **같은** not-found — 있는지가 새지 않게.
        """
        row = self.get(project_id)
        if row is None or row.commit_hash is None:
            raise NotFound("code_graph", str(project_id))
        rel = PurePosixPath(path.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise NotFound("file", path)
        if any(fnmatch.fnmatch(rel.name.lower(), pat) for pat in DENY):
            raise NotFound("file", path)
        try:
            text = await git.read(workdir, str(rel), row.commit_hash)
        except GitError as e:
            raise NotFound("file", path) from e
        lines = text.splitlines()
        first = max(1, start)
        last = min(len(lines), end or len(lines))
        truncated = last - first + 1 > MAX_LINES
        if truncated:
            last = first + MAX_LINES - 1
        return CodeText(
            str(rel), first, last, row.commit_hash, "\n".join(lines[first - 1 : last]), truncated
        )
