"""화면 확인용 미리보기 서버 (DEV-14 일곱째 조건 — 사람이 브라우저에서 눌러 본다).

GitHub OAuth 없이 본다: 개발 DB(syncdoc_dev, 테스트 컨테이너)를 새로 만들고, 이 저장소의 작업 트리를
로컬 bare 원격에 커밋 하나로 올려 **재구축**한다 — 저장소를 등록할 때와 같은 길이라 문서·항목·참조와
코드 그래프(코드 탭·관계도 코드 호출)가 다 생긴다. 그 뒤 GitHub에서 직접 고친 것처럼 커밋을 더 push해
S4 상태(버전 이력·끊어진 참조)를, SQL로 규약 오류를 심는다.
로그인은 /__dev/login/{login} (hoyoung · minjun). 앱 코드는 건드리지 않는다 — 라우트는 여기서 붙인다.

    uv run --project backend python tools/dev_preview.py            # 시드 + 서버 (http://localhost:8000/__dev/login/hoyoung)
    uv run --project backend python tools/dev_preview.py --serve    # 시드 없이 서버만
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = Path(os.environ.get("SYNCDOC_PREVIEW_DIR", "/tmp/syncdoc-preview"))
os.environ["DATABASE_URL"] = "postgresql+psycopg://syncdoc:syncdoc@localhost:5434/syncdoc_dev"
os.environ.setdefault("SECRET_KEY", "dev-preview-secret")
os.environ.setdefault("REPOS_DIR", str(PREVIEW / "repos"))
sys.path.insert(0, str(ROOT / "backend"))  # 임포트 패키지는 backend/app (DOM-002 1장)

from fastapi import Depends, Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import db  # noqa: E402
from app.core import pipeline  # noqa: E402
from app.core.account.service import AccountService  # noqa: E402
from app.core.project.models import Project, Repository  # noqa: E402
from app.core.reference.service import ReferenceService  # noqa: E402
from app.core.spec.service import SpecService  # noqa: E402
from app.core.types import DocType, spec_dir  # noqa: E402
from app.main import app  # noqa: E402
from app.web import auth  # noqa: E402

# 커밋 신원 — noreply 메일의 앞부분이 login이라 그 계정으로 잡힌다 (AccountService.user_for_commit)
HOYOUNG = ("박호영", "hoyoung@users.noreply.github.com")
MINJUN = ("김민준", "minjun@users.noreply.github.com")


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def git(cwd: Path, *args: str, who: tuple[str, str] = HOYOUNG) -> str:
    return sh("git", "-c", f"user.name={who[0]}", "-c", f"user.email={who[1]}", *args, cwd=cwd)


def fresh_db() -> None:
    for q in ("DROP DATABASE IF EXISTS syncdoc_dev", "CREATE DATABASE syncdoc_dev"):
        sh(
            "docker",
            "exec",
            "syncdoc-test-pg",
            "psql",
            "-U",
            "syncdoc",
            "-d",
            "syncdoc_test",
            "-c",
            q,
        )
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "backend" / "alembic.ini"))  # DOM-002 1장 — 파이썬은 backend/ 아래
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")


def copy_tree(dest: Path) -> None:
    """작업 트리를 복사한다 — 추적 파일과 무시되지 않는 새 파일(check_calls와 같다). 커밋 전 명세·코드도
    미리 본다. 무시되는 파일(.env·node_modules·빌드 결과)은 안 간다."""
    files = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "-co", "--exclude-standard"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    for f in files:
        if not f:
            continue
        rel = f.decode()
        src = ROOT / rel
        if not src.is_file():
            continue  # 지웠지만 아직 커밋 안 한 파일
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def fresh_repo() -> tuple[Path, Path, Path]:
    """bare 원격과 클론 둘 — seed(시드가 GitHub 사용자처럼 커밋해 push한다) · work(싱크독의 작업 사본).
    첫 커밋은 이 저장소의 작업 트리 그대로 — 명세로 문서를, 코드로 코드 그래프를 만든다."""
    shutil.rmtree(PREVIEW, ignore_errors=True)
    PREVIEW.mkdir(parents=True)
    remote, seed, work = PREVIEW / "remote.git", PREVIEW / "seed", PREVIEW / "work"
    git(PREVIEW, "init", "-q", "--bare", "-b", "main", str(remote))
    git(PREVIEW, "clone", "-q", str(remote), str(seed))
    git(seed, "checkout", "-q", "-b", "main")
    copy_tree(seed)
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "chore(SYNC): 지금 작업 트리 그대로")
    git(seed, "push", "-q", "origin", "HEAD:main")
    git(PREVIEW, "clone", "-q", str(remote), str(work))
    return remote, seed, work


def push(seed: Path, rel: str, body: str, message: str, who: tuple[str, str]) -> None:
    """GitHub에서 직접 고친 것처럼 — 시드 클론에서 파일 하나를 바꿔 커밋하고 push한다.
    먼저 당긴다: 싱크독이 그새 커밋했을 수 있다(README 판·상태 강등)."""
    git(seed, "pull", "-q", "--rebase", "origin", "main", who=who)
    (seed / rel).write_text(body, encoding="utf-8")
    git(seed, "add", rel, who=who)
    git(seed, "commit", "-q", "-m", message, who=who)
    git(seed, "push", "-q", "origin", "HEAD:main", who=who)


def with_downstream(s: Session, doc_id: str, exclude: set[str] = frozenset()) -> tuple[str, int]:
    """하위 참조가 있는 항목 (item_id, pk) 하나."""
    spec, refs = SpecService(s), ReferenceService(s)
    for i in spec.get_document(doc_id).items:
        if i.item_id not in exclude and any(e.from_item_pk for e in refs.downstream(i.pk)):
            return i.item_id, i.pk
    raise RuntimeError(f"{doc_id}: 하위 참조 있는 항목 없음")


def edited(s: Session, doc_id: str, item_id: str) -> str:
    """항목 블록 끝에 한 줄 추가한 본문."""
    spec = SpecService(s)
    d = spec.get_document(doc_id)
    block = next(b for b in spec.item_blocks(d.body, DocType(d.doc_type)) if b.item_id == item_id)
    lines = d.body.split("\n")
    lines.insert(
        block.end_line, "미리보기용으로 이 항목의 내용이 바뀌었다. 하위 문서가 영향을 받는다."
    )
    return "\n".join(lines)


def without(s: Session, doc_id: str, item_id: str) -> str:
    spec = SpecService(s)
    d = spec.get_document(doc_id)
    block = next(b for b in spec.item_blocks(d.body, DocType(d.doc_type)) if b.item_id == item_id)
    lines = d.body.split("\n")
    del lines[block.start_line - 1 : block.end_line]
    return "\n".join(lines)


async def seed() -> None:
    from tests.core.account.test_service import make_user

    fresh_db()
    remote, seed_dir, work = fresh_repo()
    with db.SessionLocal() as s:
        # 사용자를 먼저 만든다 — Project.owner_user_id·Repository.registered_by_user_id가 호영을 참조한다
        hoyoung = make_user(s, login="hoyoung")
        hoyoung.display_name = "박호영"
        # 민준은 남이다 — 호영의 프로젝트가 안 보인다(1인 도구). 이력에 커밋 작성자로만 나온다
        minjun = make_user(s, login="minjun")
        minjun.display_name = "김민준"
        s.flush()
        p = Project(code="SYNC", name="싱크독", owner_user_id=hoyoung.id)
        s.add(p)
        s.flush()
        s.add(
            Repository(
                project_id=p.id,
                remote_url=str(remote),
                workdir_path=str(work),
                registered_by_user_id=hoyoung.id,
            )
        )
        s.commit()

    # 1. 등록처럼 재구축으로 읽는다 — 문서·항목·참조, 그리고 코드 그래프
    r = await pipeline.rebuild("SYNC")
    print(
        f"  재구축 — 문서 {r.docs} · 항목 {r.items} · 참조 {r.references}"
        f" · 규약 오류 {len(r.convention_errors)}"
    )
    # 재구축이 백그라운드로 건 코드 그래프를 기다린다 — 안 기다리면 이 루프가 끝날 때 취소된다
    task = pipeline._graph_tasks.get("SYNC")
    if task is not None:
        await task
    with db.SessionLocal() as s:
        row = s.execute(
            text("SELECT function_count, call_count, error FROM code_graphs")
        ).first()
        print(f"  코드 그래프 — {tuple(row) if row else '없음'}")
        q_edit, _ = with_downstream(s, "SYNC-RFQ-001")
        q_del, _ = with_downstream(s, "SYNC-RFQ-001", {q_edit})
        body = edited(s, "SYNC-RFQ-001", q_edit)
    rel = f"docs/specs/{spec_dir('RFQ')}/SYNC-RFQ-001.md"

    # 2. 민준이 GitHub에서 RFQ 항목을 고쳐 push — 버전이 하나 는다(전파 없음)
    push(seed_dir, rel, body, f"spec(SYNC-RFQ-001): {q_edit} 보강", MINJUN)
    await pipeline.read_pending("SYNC", hoyoung)
    print(f"  RFQ {q_edit} 수정 → 버전 하나")
    # 3. 민준이 하위 참조가 있는 항목을 지워 push — 하위 참조가 끊어진다
    with db.SessionLocal() as s:
        body = without(s, "SYNC-RFQ-001", q_del)
    push(seed_dir, rel, body, f"spec(SYNC-RFQ-001): {q_del} 삭제", MINJUN)
    await pipeline.read_pending("SYNC", hoyoung)
    print(f"  RFQ {q_del} 삭제 → 끊어진 참조")
    # 4. 규약 오류
    with db.SessionLocal() as s:
        s.execute(
            text(
                "UPDATE documents SET has_convention_error=true, convention_error_detail='frontmatter.status: 미리보기용 오류' WHERE doc_id='SYNC-UC-001'"
            )
        )
        s.commit()
    print("시드 완료 — hoyoung id", hoyoung.id)


@app.get("/__dev/login/{login}")
def _dev_login(login: str, request: Request, session: Session = Depends(db.get_session)):
    user = AccountService(session).user_by_login(login)
    if user is None:
        return {"error": f"없는 사용자 {login}"}
    auth.login(request, user)
    return RedirectResponse("/", status_code=302)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # 파일로 돌려도 시드 진행이 바로 보이게 — 서버가 안 끝난다
    if "--serve" not in sys.argv:
        asyncio.run(seed())
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="warning")
