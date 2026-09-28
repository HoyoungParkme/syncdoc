#!/usr/bin/env python3
"""정적 뷰와 앱 유저용 탭이 같은 HTML을 내는지 — SYNC-STD-002 1장·4장 (카드 AP, #153).

`view_build.py`가 참조 구현이고 React 유저용 탭(`frontend/src/view`)은 같은 HTML을 그려야 한다. 지키는 장치가
CSS 대조(`check_view_css`)뿐이라, #120처럼 두 구현이 똑같이 틀리거나 한쪽만 틀려도 아무도 못 잡았다.

두 벌을 같은 입력(문서·색인·하위 참조·제목·배치 기준 경로)으로 그려 파싱해 비교한다 — 태그·속성(순서 무관)·글자.
뜻이 같은 차이는 보지 않는다: 엔티티 표기(`'`↔`&#x27;`)·태그 사이 공백·`<br>`↔`<br/>`·주석.
`<style>`·`<script>`도 보지 않는다 — CSS는 check_view_css가 보고, 스크립트는 정적 뷰 전용이다.
배치 iframe의 `srcdoc` 속은 풀어서 같은 규칙으로 본다. `<pre>` 속 글자는 공백까지 본다.
예외는 규약에 적은 하나 — V-API의 OpenAPI 합치기(`div.oa-merge` 속)는 정적 뷰만 한다.

앱 모듈은 `frontend/node_modules`의 rolldown으로 임시 파일 하나로 묶어 Node로 돌린다 — 새 의존성은 없다.
분기는 앱 `view/index.ts`의 `pick`을 그대로 쓴다.

사용: python3 tools/check_view_html.py [--specs <저장소>/docs/specs]
  기본은 싱크독 문서 전부 + view_build 셀프테스트 시험 문서. --specs면 그 저장소 문서만.
종료 코드: 0 같음 · 1 다름 · 2 준비 안 됨(node·frontend/node_modules가 없거나 앱이 묶이지 않음)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
FRONT = os.path.join(ROOT, "frontend")
ROLLDOWN = os.path.join(FRONT, "node_modules", ".bin", "rolldown")
VIEW_INDEX = os.path.join(FRONT, "src", "view", "index.ts")
sys.path.insert(0, TOOLS)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
FIXTURES = ("_SELF_PRD", "_SELF_INFRA", "_SELF_SCN", "_SELF_UI", "_SELF_UI_REF", "_SELF_UC", "_SELF_MS", "_SELF_SEQ")

# 앱 쪽 진입 — 입력 JSON을 받아 문서마다 pick(type)으로 그린다. 링크는 정적 뷰와 같은 view_{doc}.html
ENTRY = """import { readFileSync } from 'node:fs'
import { pick } from %(index)s
const input = JSON.parse(readFileSync(process.argv[2], 'utf-8'))
const out = {}
for (const d of input.docs) {
  const ctx = {
    selfId: d.id,
    href: (doc, it) => `view_${doc}.html` + (it ? `#item-${it}` : ''),
    exists: (doc, it) => doc in input.index && (!it || input.index[doc].includes(it)),
    downstream: d.downstream,
    titles: input.titles,
    assetBase: d.base,
  }
  try {
    out[d.id] = pick(d.type)({ type: d.type, title: d.title, body: d.body, ctx }).html
  } catch (e) {
    out[d.id] = '\\u0000앱 오류: ' + String((e && e.stack) || e)
  }
}
process.stdout.write(JSON.stringify(out))
"""


class _Canon(HTMLParser):
    """HTML → 비교용 토큰 줄. 태그는 속성을 정렬해 한 토큰, 글자는 공백을 한 칸으로(<pre> 속은 그대로)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.toks: list[str] = []
        self.skip = 0  # style·script 속
        self.pre = 0
        self.oa = 0  # div.oa-merge 속 — 그 안 div 깊이

    def _attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        out = []
        for k, v in sorted(attrs):
            if v is None:
                out.append(k)
            elif k == "class":
                out.append(f'class="{" ".join(sorted(v.split()))}"')
            elif k == "srcdoc":
                out.append("srcdoc=[" + " ".join(canon(v)) + "]")
            else:
                out.append(f'{k}="{v}"')
        return " ".join(out)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip:
            return
        if self.oa:
            if tag == "div":
                self.oa += 1
            return
        if tag in ("style", "script"):
            self.skip += 1
            return
        a = self._attrs(attrs)
        self.toks.append(f"<{tag}{' ' + a if a else ''}>")
        if tag == "pre":
            self.pre += 1
        if tag == "div" and "oa-merge" in (dict(attrs).get("class") or "").split():
            self.oa = 1  # 정적 전용 칸(OpenAPI 합치기) — 속은 보지 않는다 (STD-002 V-API)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if self.skip:
            if tag in ("style", "script"):
                self.skip -= 1
            return
        if self.oa:
            if tag == "div":
                self.oa -= 1
                if self.oa == 0:
                    self.toks.append("</div>")
            return
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
        self.toks.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.skip or self.oa:
            return
        t = data if self.pre else re.sub(r"\s+", " ", data).strip()
        if t:
            self.toks.append(t)


def canon(html: str) -> list[str]:
    c = _Canon()
    c.feed(html)
    c.close()
    return c.toks


def _docs(vb, fixtures: bool) -> list[str]:
    """비교할 문서 ID들. 시험 문서는 ALL에 넣어 서로의 참조가 풀리게 한다(셀프테스트와 같은 방식)."""
    if fixtures:
        for name in FIXTURES:
            raw = getattr(vb, name, None)
            if raw is None:
                continue
            d = vb.parse_doc(raw, f"{name}.md")
            vb.ALL[d["fm"]["doc_id"]] = d
    return sorted(vb.ALL)


def _static(vb, did: str) -> str:
    d = vb.ALL[did]
    t = d["fm"]["type"]
    fn = vb.VIEWS.get(t)
    try:
        return fn(d) if fn else vb.v_plain(d, vb.ITEM_PAT.get(t, r"\S+"))
    except Exception as e:  # noqa: BLE001 — 정적이 죽는 것도 차이다(옛 MS·SEQ 빌더가 그랬다)
        return f"\x00정적 오류: {type(e).__name__}: {e}"


def _app(vb, wf, ids: list[str], work: str) -> dict[str, str] | None:
    node = shutil.which("node")
    if not node or not os.path.exists(ROLLDOWN):
        print("준비 안 됨: node와 frontend/node_modules가 있어야 한다 — frontend에서 `npm ci`")
        return None
    entry, bundle = os.path.join(work, "entry.mjs"), os.path.join(work, "app.mjs")
    open(entry, "w", encoding="utf-8").write(ENTRY % {"index": json.dumps(VIEW_INDEX)})
    r = subprocess.run([ROLLDOWN, entry, "--file", bundle, "--format", "esm", "--platform", "node"],
                       cwd=FRONT, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(bundle):
        print("준비 안 됨: 앱 뷰를 묶지 못했다 —\n" + (r.stderr or r.stdout)[-2000:])
        return None
    docs = []
    for did in ids:
        d = vb.ALL[did]
        docs.append({"id": did, "type": d["fm"]["type"], "title": d["fm"].get("title", ""), "body": d["body"],
                     "downstream": {k: sorted(v) for k, v in vb.downstream_of(did).items()}, "base": wf.base_for(did)})
    inp = os.path.join(work, "input.json")
    json.dump({"docs": docs, "index": {k: list(v["items"]) for k, v in vb.ALL.items()},
               "titles": {k: v["fm"].get("title", "") for k, v in vb.ALL.items()}}, open(inp, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([node, bundle, inp], capture_output=True, text=True)
    if r.returncode != 0:
        print("준비 안 됨: 묶은 앱 뷰가 돌지 않았다 —\n" + r.stderr[-2000:])
        return None
    return json.loads(r.stdout)


def _show(a: list[str], b: list[str]) -> None:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    lo = max(0, i - 4)
    print(f"   처음 갈리는 곳: 토큰 {i} (정적 {len(a)} · 앱 {len(b)})")
    print("     정적: " + " ".join(a[lo:i + 6])[:360])
    print("     앱  : " + " ".join(b[lo:i + 6])[:360])


def main(argv: list[str]) -> int:
    specs = None
    if "--specs" in argv:
        i = argv.index("--specs")
        if i + 1 >= len(argv):
            print("--specs 뒤에 <저장소>/docs/specs를 준다")
            return 2
        specs = argv[i + 1]
    import view_build as vb
    import wf_build as wf

    work = tempfile.mkdtemp(prefix="check_view_html-")
    try:
        if specs:
            vb.use_root(specs, out_dir=os.path.join(work, "views"))
        ids = _docs(vb, fixtures=specs is None)
        app = _app(vb, wf, ids, work)
        if app is None:
            return 2
        same = 0
        for did in ids:
            a, b = canon(_static(vb, did)), canon(app.get(did, "\x00앱 결과 없음"))
            if a == b:
                same += 1
                continue
            print(f"✗  {did} ({vb.ALL[did]['fm']['type']})")
            _show(a, b)
        print(f"\n합계: {vb.CODE} · 문서 {len(ids)} · 같음 {same} · 다름 {len(ids) - same}")
        return 0 if same == len(ids) else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
