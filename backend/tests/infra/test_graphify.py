"""SYNC-MS-009 테스트 관점 — graphify.extract(카드 AX). graphify를 실제로 돌린다(코드만, 모델 없음)."""

from pathlib import Path

import pytest

from app.core.errors import CodeGraphFailed
from app.infra import graphify


async def test_extract_reads_python_calls(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def a():\n    return b()\n\n\ndef b():\n    return 1\n")
    raw = await graphify.extract(tmp_path)
    labels = {n.get("label") for n in raw["nodes"]}
    assert {"a()", "b()"} <= labels
    assert any(e["relation"] == "calls" for e in raw["links"])


def test_clean_env_has_no_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    env = graphify._clean_env(tmp_path)
    assert set(env) == {"PATH", "LANG", "HOME"} and env["HOME"] == str(tmp_path)
    assert "sk-secret" not in "".join(env.values())


async def test_missing_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(CodeGraphFailed):
        await graphify.extract(tmp_path / "없음")
