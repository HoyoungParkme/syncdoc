#!/usr/bin/env python3
"""SYNC-STD-004#DEV-14 — MINISPEC↔코드 일치 검사기.

MS 문서의 항목(시그니처)과 코드의 함수(docstring 첫 줄 = 항목 ID, DEV-3)를 대조한다.
  · 있음/없음: MS에 있는데 코드에 없거나(없음), 코드에 있는데 MS에 없으면(명세 밖) 미완
  · 시그니처: async 여부 · 인자 이름·타입·기본값 · 반환 타입 (공백·따옴표 무시)
코드는 import하지 않고 AST만 읽는다 — DB·환경 변수가 없어도 돈다.

**구현이 둘이다** — 파이썬 `backend/app`과 Rust `local/` (STD-001 2.10, 카드 BW).
  · 키는 `문서#항목` 전체다. 짧은 이름으로 세면 두 구현의 같은 이름(`SpecService.save`)이
    서로를 덮는다. 같은 키가 둘이면 — 명세 안이든 코드 안이든 — 미완
  · 시그니처의 언어는 펜스 태그, 태그가 없으면 `fn` 꼴이면 Rust다(STD-002 V-MS와 같다).
    명세와 코드의 언어가 다르면 미완
  · Rust는 tree-sitter-rust로 읽는다. `///` 첫 줄이 항목 ID다(속성은 건너, DEV-3). 함수 머리
    (가시성·async·이름·제네릭·인자·반환·where)를 주석·공백·끝 쉼표를 빼고 대조한다. 맨 위
    `fn`과 `impl`의 메서드만 본다 — 코드 그래프가 세는 함수와 같다(MS-011 enrich 2e)
  · **시그니처를 못 읽으면 미완이다.** 전에는 `?`를 찍고 셈에 넣지 않았다 — ```python 펜스만
    읽어서 Rust 시그니처는 전부 그렇게 지나갔다
  · 클래스 명세가 둘 이상이면 MS의 upstream에 클래스 명세가 꼭 하나다 — 어느 구현의 것인가

사용: python tools/check_code.py [--doc SYNC-MS-006 ...] [--items ID ...]
      python tools/check_code.py --specs <저장소>/docs/specs \
          --backend <저장소>/backend/app --local <저장소>/local
      python tools/check_code.py --selftest
      필터 없으면 MS 전부. `--items`는 `문서#항목`이나 항목만.
      종료 코드 1 = 미완, 2 = Rust를 읽어야 하는데 tree-sitter-rust가 없다 —
      `uv run --project backend python tools/check_code.py`로 돌린다.

프로젝트 코드는 명세에서 읽는다 — `SYNC-`를 박아 두지 않는다 (STD-004 4장, #57).
**코드도 훑어서 찾는다** — 예전에는 파일 목록을 상수로 들고 있어 남의 저장소에서는
아무것도 못 봤다. 이제 `--backend` 아래 `.py` 전부와 `--local` 아래 `.rs` 전부(`target/` 빼고)에서
`{CODE}-MS-NNN#항목` 주석을 찾는다. 코드가 아직 없는 프로젝트면 「볼 것이 없다」고 말하고 통과한다.
"""

from __future__ import annotations

import argparse
import ast
import functools
import glob
import os
import re
import sys
import tempfile
from typing import NamedTuple

import proj

ITEM = re.compile(r"^#{1,6} ([A-Za-z_]+\.[a-z_]+)\b")
SIG_FENCE = re.compile(r"\*\*시그니처\*\*\s*\n```([A-Za-z0-9_]*)[ \t]*\n(.*?)\n?```", re.S)
SIG_INLINE = re.compile(r"\*\*시그니처\*\*\s*`([^`]+)`")
SIG = re.compile(r"^(async def |def )?(\w+)\((.*)\)\s*->\s*(.+)$", re.S)
# `fn` 꼴 — 앞에 pub·pub(crate)·const·async·unsafe·extern이 붙어도 (STD-002 V-MS)
RS_FN = re.compile(
    r'^(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe)\s+)*(?:extern\s+(?:"[^"]*"\s+)?)?fn\s'
)
TAGS = {"python": "python", "py": "python", "rust": "rust", "rs": "rust"}
LANG = {"python": "파이썬", "rust": "Rust"}


class Sig(NamedTuple):
    """시그니처 하나. 못 읽었으면 lang이 None이고 show가 이유다."""

    where: str  # 명세는 문서 ID, 코드는 `파일:줄`
    lang: str | None  # "python" · "rust"
    key: object  # 대조할 값 — 파이썬 (async, 인자, 반환), Rust 머리(공백 없이)
    show: str  # 불일치 때 찍는 꼴


class NoTreeSitter(Exception):
    """Rust를 읽어야 하는데 tree-sitter-rust가 없다."""


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).replace('"', "'")


@functools.cache
def _rust_parser():
    try:
        import tree_sitter_rust
        from tree_sitter import Language, Parser
    except ImportError:
        return None
    return Parser(Language(tree_sitter_rust.language()))


def _parser():
    p = _rust_parser()
    if p is None:
        raise NoTreeSitter
    return p


def _blocks(text: str):
    """(항목, 블록 글) — 코드펜스 안의 `#` 줄(파이썬 주석)은 항목 헤딩이 아니다."""
    lines = text.split("\n")
    heads, fence = [], False
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence = not fence
        elif not fence and (m := ITEM.match(line)):
            heads.append((i, m.group(1)))
    for k, (i, item) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        yield item, "\n".join(lines[i + 1 : end])


def _py_show(a: bool, params: str, ret: str) -> str:
    return f"{'async ' if a else ''}({params}) -> {ret}"


def _comments(node, stop: int):
    """머리(본문 앞) 안의 주석 노드."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.start_byte >= stop:
            continue
        if n.type in ("line_comment", "block_comment"):
            yield n
        else:
            stack.extend(n.children)


def _rs_head(fn, src: bytes) -> tuple[str, str]:
    """함수 머리 → (대조 꼴, 보일 꼴). 본문 앞까지에서 주석을 빼고 공백을 지운다.

    rustfmt가 여러 줄로 펼친 머리의 끝 쉼표(`y: u8,\\n)`·where 끝)도 지운다 — 한 줄 명세와 같게.
    """
    body = fn.child_by_field_name("body")
    stop = body.start_byte if body is not None else fn.end_byte
    parts, at = [], fn.start_byte
    for c in sorted(_comments(fn, stop), key=lambda n: n.start_byte):
        parts.append(src[at : c.start_byte])
        at = c.end_byte
    parts.append(src[at:stop])
    text = b" ".join(parts).decode("utf-8")
    canon = re.sub(r",(?=[)>\]])", "", "".join(text.split())).rstrip(",")
    return canon, " ".join(text.split())


def _rs_spec(text: str) -> tuple[str, str] | None:
    """명세의 Rust 시그니처 → 머리. 본문 `{}`을 붙여 함수 하나로 읽고, 못 읽으면 None."""
    src = (text.strip().rstrip(";").rstrip() + "\n{}").encode("utf-8")
    root = _parser().parse(src).root_node
    kids = root.named_children
    if root.has_error or len(kids) != 1 or kids[0].type != "function_item":
        return None
    return _rs_head(kids[0], src)


def _spec_sig(doc: str, block: str) -> Sig:
    m = SIG_FENCE.search(block)
    if m:
        tag, text = m.group(1).lower(), m.group(2)
    elif m := SIG_INLINE.search(block):
        tag, text = "", m.group(1)
    else:
        return Sig(doc, None, None, "시그니처가 없다")
    lang = TAGS.get(tag) if tag else ("rust" if RS_FN.match(text.strip()) else "python")
    if lang is None:
        return Sig(doc, None, None, f"모르는 언어 `{tag}`")
    if lang == "rust":
        head = _rs_spec(text)
        return Sig(doc, "rust", *head) if head else Sig(doc, None, None, "Rust 함수 머리가 아니다")
    sig = SIG.match(" ".join(text.split()))
    if not sig:
        return Sig(doc, None, None, "파이썬 def 꼴이 아니다")
    a, p, r = (
        (sig.group(1) or "").startswith("async"),
        norm(sig.group(3)),
        norm(sig.group(4)),
    )
    return Sig(doc, "python", (a, p, r), _py_show(a, p, r))


def spec_items(specs: str, code: str) -> dict[str, list[Sig]]:
    """{문서#항목: [시그니처]} — 둘 이상이면 한 문서에 같은 항목 헤딩이 둘이다."""
    out: dict[str, list[Sig]] = {}
    for path in sorted(glob.glob(os.path.join(proj.type_dir(specs, "MS"), f"{code}-MS-*.md"))):
        doc = os.path.basename(path)[:-3]
        for item, block in _blocks(open(path, encoding="utf-8").read()):
            out.setdefault(f"{doc}#{item}", []).append(_spec_sig(doc, block))
    return out


def _params(a: ast.arguments) -> list[str]:
    """시그니처의 인자를 명세 표기 그대로 — 위치 전용(`/`)·`*args`·키워드 전용(`*`)·`**kwargs`까지.

    `args.args`만 보면 `*` 뒤 인자가 빠져 명세와 코드가 글자 그대로 같아도 불일치가 난다 (#196).
    """

    def one(arg: ast.arg, default: ast.expr | None) -> str:
        s = f"{arg.arg}:{ast.unparse(arg.annotation) if arg.annotation else '?'}"
        return s + (f"={ast.unparse(default)}" if default is not None else "")

    skip = ("self", "cls")
    ponly = [x for x in a.posonlyargs if x.arg not in skip]
    pos = ponly + [x for x in a.args if x.arg not in skip]
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    out = [one(x, d) for x, d in zip(pos, defaults, strict=True)]
    if ponly:
        out.insert(len(ponly), "/")
    if a.vararg:
        out.append("*" + one(a.vararg, None))
    elif a.kwonlyargs:
        out.append("*")
    out += [one(x, d) for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=True)]
    if a.kwarg:
        out.append("**" + one(a.kwarg, None))
    return out


def _ms_id(doc: str, code: str) -> str | None:
    """주석 첫 줄의 첫 낱말이 `{CODE}-MS-…#…`이면 그 ID."""
    first = doc.strip().split("\n", 1)[0].split()
    tok = first[0] if first else ""
    return tok if tok.startswith(f"{code}-MS-") and "#" in tok else None


def _rs_doc(fn, src: bytes) -> str | None:
    """정의 바로 앞 `///` 묶음의 첫 줄 — 사이의 속성 `#[…]`은 건너뛴다 (MS-011 enrich 2f와 같다)."""
    first = None
    p = fn.prev_sibling
    while p is not None and p.type in ("line_comment", "attribute_item"):
        if p.type == "line_comment":
            text = src[p.start_byte : p.end_byte].decode("utf-8")
            if not text.startswith("///") or text.startswith("////"):
                break
            first = text[3:].strip()
        p = p.prev_sibling
    return first


def _rs_fns(root):
    """맨 위 `fn`과 `impl` 블록의 메서드 — 코드 그래프와 같다 (MS-011 enrich 2e).

    인라인 `mod { }`(테스트 포함)는 안 본다.
    """
    for c in root.named_children:
        if c.type == "function_item":
            yield c
        elif c.type == "impl_item" and (body := c.child_by_field_name("body")) is not None:
            yield from (m for m in body.named_children if m.type == "function_item")


def _rs_files(local: str) -> list[str]:
    """`local/` 아래 `.rs` — 빌드 산출물(`target/`)과 숨은 폴더는 뺀다."""
    out = []
    for d, dirs, files in os.walk(local):
        dirs[:] = sorted(x for x in dirs if x != "target" and not x.startswith("."))
        out += [os.path.join(d, f) for f in sorted(files) if f.endswith(".rs")]
    return out


def code_items(backend: str, local: str, code: str) -> tuple[dict[str, list[Sig]], int, int]:
    """({주석 항목ID: [시그니처]}, 훑은 .py 수, 훑은 .rs 수)

    파일 목록을 상수로 들지 않고 뿌리 아래를 전부 훑는다 — 상수로 들면 남의
    저장소에서 0건을 내고, 그게 「맞다」가 아니라 「안 봤다」다 (STD-004 4장, #57).
    """
    out: dict[str, list[Sig]] = {}
    py = (
        sorted(glob.glob(os.path.join(backend, "**", "*.py"), recursive=True))
        if os.path.isdir(backend)
        else []
    )
    for path in py:
        rel = os.path.relpath(path, os.path.dirname(backend))
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            key = _ms_id(ast.get_docstring(node) or "", code)
            if not key:
                continue
            a = isinstance(node, ast.AsyncFunctionDef)
            p = norm(",".join(_params(node.args)))
            r = norm(ast.unparse(node.returns) if node.returns else "?")
            out.setdefault(key, []).append(
                Sig(f"{rel}:{node.lineno}", "python", (a, p, r), _py_show(a, p, r))
            )
    rs = _rs_files(local) if os.path.isdir(local) else []
    tagged = re.compile(rb"///\s*" + re.escape(code.encode()) + rb"-MS-")
    for path in rs:
        src = open(path, "rb").read()
        if not tagged.search(src):
            continue
        rel = os.path.relpath(path, os.path.dirname(local))
        for fn in _rs_fns(_parser().parse(src).root_node):
            key = _ms_id(_rs_doc(fn, src) or "", code)
            if not key:
                continue
            where = f"{rel}:{fn.start_point[0] + 1}"
            if fn.has_error:
                out.setdefault(key, []).append(Sig(where, None, None, "코드를 못 읽음"))
            else:
                out.setdefault(key, []).append(Sig(where, "rust", *_rs_head(fn, src)))
    return out, len(py), len(rs)


def check(
    specs: str, backend: str, local: str, docs: list[str], items: list[str]
) -> tuple[list[str], int]:
    """(찍을 줄, 미완 수). Rust를 읽어야 하는데 tree-sitter가 없으면 NoTreeSitter."""
    project = proj.code_of(specs)
    spec = spec_items(specs, project)
    if not os.path.isdir(backend) and not os.path.isdir(local):
        return [
            f"{project}: MINISPEC 항목 {len(spec)}개 · 대조할 코드가 없다 ({backend} · {local})"
        ], 0
    code, n_py, n_rs = code_items(backend, local, project)
    scope = {
        k
        for k in spec
        if (not docs or k.split("#", 1)[0] in docs)
        and (not items or k in items or k.split("#", 1)[1] in items)
    }
    lines: list[str] = []
    bad = 0
    count = {lang: [0, 0] for lang in LANG}  # 언어 → [일치, 대상]
    for k in sorted(scope):
        ss, cs = spec[k], code.get(k, [])
        s = ss[0]
        if s.lang:
            count[s.lang][1] += 1
        if len(ss) > 1:
            msg = f"명세에 둘 — {s.where}에 같은 항목 헤딩이 {len(ss)}개"
        elif s.lang is None:
            msg = f"시그니처를 못 읽음 — {s.show}"
        elif not cs:
            msg = "없음"
        elif len(cs) > 1:
            msg = "코드에 둘 — " + " · ".join(c.where for c in cs)
        elif cs[0].lang is None:
            msg = f"코드를 못 읽음 ({cs[0].where})"
        elif cs[0].lang != s.lang:
            msg = f"언어가 다르다 — MS는 {LANG[s.lang]}, 코드는 {LANG[cs[0].lang]} ({cs[0].where})"
        elif cs[0].key != s.key:
            msg = f"불일치\n     MS  : {s.show}\n     code: {cs[0].show} ({cs[0].where})"
        else:
            count[s.lang][0] += 1
            lines.append(f"✓  {k}")
            continue
        bad += 1
        lines.append(f"✗  {k:56s} {msg}")
    for k in sorted(k for k in code if k not in spec):
        for c in code[k]:
            lines.append(f"✗  {k:56s} 명세 밖 — MINISPEC에 없는 함수 ({c.where})")
            bad += 1
    # 구현이 둘 이상이면 MS마다 어느 구현의 것인지 정해져 있어야 한다 (STD-001 2.10)
    if len(proj.all_by_title(specs, "DOM", "클래스")) > 1:
        impl = proj.class_doc_of(specs)
        for d in sorted({k.split("#", 1)[0] for k in scope} - set(impl)):
            msg = "구현을 모른다 — upstream에 클래스 명세가 꼭 하나여야 한다 (STD-001 2.10)"
            lines.append(f"✗  {d:56s} {msg}")
            bad += 1
    ok = sum(v[0] for v in count.values())
    langs = " · ".join(f"{LANG[x]} {count[x][0]}/{count[x][1]}" for x in LANG)
    files = f"파일 .py {n_py} · .rs {n_rs}"
    lines.append(
        f"\n합계: {project} · {files} · 대상 {len(scope)}, 일치 {ok}, 미완 {bad} · {langs}"
    )
    return lines, bad


_SELF_FILES = {
    "docs/specs/06-DOM/T-DOM-002.md": "---\ndoc_id: T-DOM-002\ntitle: 클래스 명세 — 파이썬\n---\n",
    "docs/specs/06-DOM/T-DOM-004.md": "---\ndoc_id: T-DOM-004\ntitle: 클래스 명세 — Rust\n---\n",
    "docs/specs/10-MS/T-MS-001.md": """---
doc_id: T-MS-001
type: MS
title: 시험 MINISPEC — 파이썬
status: draft
upstream: [T-DOM-002]
---

## 2. 함수

#### Svc.save 같다

**시그니처**
```python
async def save(body: str, *, force: bool = False) -> str
```

#### Svc.load 반환이 다르다

**시그니처** `def load(key: str) -> bytes`

#### Svc.gone 코드에 없다

**시그니처** `def gone() -> None`

#### Svc.bad 시그니처를 못 읽는다

**시그니처** 글로만 적었다

#### Svc.twice 코드에 둘

**시그니처** `def twice() -> None`

#### Svc.lang 언어가 다르다

**시그니처** `def lang() -> None`

```python
# Svc.fake 펜스 안의 줄은 항목이 아니다
```

## 3. 미결사항
""",
    "docs/specs/10-MS/T-MS-002.md": """---
doc_id: T-MS-002
type: MS
title: 시험 MINISPEC — Rust
status: draft
upstream: [T-DOM-004]
---

#### Svc.save 두 구현의 같은 이름 — 제 구현으로

**시그니처**
```rust
pub async fn save(&mut self, body: &str) -> Result<String, Problem>
```

#### Svc.fmt rustfmt 여러 줄 머리 · 속성 뒤 /// · 머리 안 주석

**시그니처** `pub fn fmt<T: Into<String>>(x: T, y: Option<u8>) -> String where T: Clone`

#### Svc.recv &self와 &mut self

**시그니처** `pub fn recv(&self) -> u8`

#### Svc.inner 테스트 모듈 안은 안 본다

**시그니처** `fn inner() -> u8`

#### Svc.dup 명세에 둘

**시그니처** `pub fn dup()`

#### Svc.dup 명세에 둘

**시그니처** `pub fn dup()`
""",
    "docs/specs/10-MS/T-MS-003.md": """---
doc_id: T-MS-003
type: MS
title: 시험 MINISPEC — 구현 모름
status: draft
upstream: []
---

#### Odd.run 구현을 모른다

**시그니처** `def run() -> None`
""",
    "backend/app/svc.py": '''class Svc:
    async def save(self, body: str, *, force: bool = False) -> str:
        """T-MS-001#Svc.save"""

    def load(self, key: str) -> str:
        """T-MS-001#Svc.load"""

    def twice(self) -> None:
        """T-MS-001#Svc.twice"""


def twice() -> None:
    """T-MS-001#Svc.twice"""


def extra() -> None:
    """T-MS-001#Svc.extra"""


def run() -> None:
    """T-MS-003#Odd.run — 뒤 설명은 자유"""
''',
    "local/crates/core/src/spec.rs": """use crate::Problem;

pub struct Svc;

impl Svc {
    /// T-MS-002#Svc.save
    pub async fn save(&mut self, body: &str) -> Result<String, Problem> {
        Ok(body.to_string())
    }

    #[inline]
    /// T-MS-002#Svc.fmt
    pub fn fmt<T: Into<String>>(
        x: T,
        y: Option<u8>, // 둘째
    ) -> String
    where
        T: Clone,
    {
        x.into()
    }

    /// T-MS-002#Svc.recv
    pub fn recv(&mut self) -> u8 {
        0
    }
}

/// T-MS-002#Svc.dup
pub fn dup() {}

/// T-MS-001#Svc.lang
pub fn lang() {}

#[cfg(test)]
mod tests {
    /// T-MS-002#Svc.inner
    fn inner() -> u8 {
        1
    }
}
""",
    "local/target/debug/build/out/gen.rs": "/// T-MS-002#Svc.gen\npub fn gen() {}\n",
}


def selftest() -> int:
    """검사기가 두 구현을 가르는지 — .py·.rs 조각으로 (카드 BW)."""
    with tempfile.TemporaryDirectory() as tmp:
        for rel, text in _SELF_FILES.items():
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w", encoding="utf-8").write(text)
        specs = os.path.join(tmp, "docs", "specs")
        lines, bad = check(
            specs,
            os.path.join(tmp, "backend", "app"),
            os.path.join(tmp, "local"),
            [],
            [],
        )
    row = {ln.split()[1]: ln for ln in lines if ln[:1] in "✓✗"}

    def got(k: str, mark: str, msg: str = "") -> bool:
        return k in row and row[k].startswith(mark) and msg in row[k]

    cases = [
        ("파이썬 일치", got("T-MS-001#Svc.save", "✓")),
        ("두 구현의 같은 이름 — 제 구현으로", got("T-MS-002#Svc.save", "✓")),
        ("파이썬 불일치", got("T-MS-001#Svc.load", "✗", "불일치")),
        ("없음", got("T-MS-001#Svc.gone", "✗", "없음")),
        ("못 읽는 시그니처는 미완", got("T-MS-001#Svc.bad", "✗", "못 읽음")),
        ("코드에 둘", got("T-MS-001#Svc.twice", "✗", "코드에 둘")),
        ("언어가 다르다", got("T-MS-001#Svc.lang", "✗", "언어가 다르다")),
        ("명세 밖", got("T-MS-001#Svc.extra", "✗", "명세 밖")),
        ("rustfmt 여러 줄 머리·속성 뒤 ///·머리 안 주석", got("T-MS-002#Svc.fmt", "✓")),
        ("Rust 불일치 — &self와 &mut self", got("T-MS-002#Svc.recv", "✗", "&mut self")),
        ("테스트 모듈은 안 본다", got("T-MS-002#Svc.inner", "✗", "없음")),
        ("명세에 둘", got("T-MS-002#Svc.dup", "✗", "명세에 둘")),
        (
            "구현 모름 — 클래스 명세가 둘이면",
            got("T-MS-003", "✗", "구현을 모른다") and got("T-MS-003#Odd.run", "✓"),
        ),
        (
            "펜스 안 # 줄·target/은 안 본다",
            "T-MS-001#Svc.fake" not in row and "T-MS-002#Svc.gen" not in row,
        ),
        (
            "합계 — 언어마다",
            "대상 12, 일치 4, 미완 10 · 파이썬 2/6 · Rust 2/5" in lines[-1] and bad == 10,
        ),
    ]
    failed = [name for name, ok in cases if not ok]
    for name in failed:
        print("✗ ", name)
    if failed:
        print("\n".join(lines))
    print("check_code: 통과" if not failed else f"check_code: {len(failed)} 실패")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    proj.add_specs(ap)
    ap.add_argument("--backend", help="파이썬 소스 뿌리 (기본: 명세와 같은 저장소의 backend/app)")
    ap.add_argument("--local", help="Rust 소스 뿌리 (기본: 명세와 같은 저장소의 local)")
    ap.add_argument("--doc", nargs="*", default=[])
    ap.add_argument("--items", nargs="*", default=[])
    ap.add_argument("--selftest", action="store_true", help="두 구현을 가르는지 조각으로 확인")
    a = ap.parse_args()
    repo = proj.repo_of(a.specs)
    try:
        if a.selftest:
            return selftest()
        lines, bad = check(
            a.specs,
            a.backend or os.path.join(repo, "backend", "app"),
            a.local or os.path.join(repo, "local"),
            a.doc,
            a.items,
        )
    except NoTreeSitter:
        print(
            "Rust를 읽어야 하는데 tree-sitter-rust가 없다 — "
            "uv run --project backend python tools/check_code.py",
            file=sys.stderr,
        )
        return 2
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
