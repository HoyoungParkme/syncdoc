#!/usr/bin/env python3
"""싱크독 사람용 뷰 생성기. STD-002 뷰 규약의 구현.
사용: view_build.py [--specs <저장소>/docs/specs] (--all | <원본.md>…) · --selftest
  --all       그 뿌리의 문서 전부 + index.html
  <원본.md>   그 문서만. --specs 없이 경로만 주면 그 문서가 있는 docs/specs를 색인한다
  다른 저장소의 뷰는 싱크독 docs/views/{코드}/에 쓴다 — 그 저장소를 건드리지 않는다 (#126)
frontmatter type을 보고 V-* 모듈로 본문을 그린다. 공통 틀은 한 곳."""
import re, json, html, sys, glob, os, pathlib

# 스크립트로 돌면 이 파일은 __main__이다. wf_build가 안에서 `import view_build`를 하면 모듈이 한 벌 더
# 떠서 색인(ALL)을 따로 든다 — 다른 저장소를 색인해도 화면 문서의 참조가 싱크독 색인으로 판정됐다 (#126)
if __name__ == "__main__":
    sys.modules.setdefault("view_build", sys.modules[__name__])

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "docs", "specs")
OUT_DIR = os.path.join(ROOT, "docs", "views")
os.makedirs(OUT_DIR, exist_ok=True)
STATUS_KO = {"draft": "초안", "review": "검토중", "approved": "승인"}
STAGE = {"RFQ": 1, "PRD": 2, "SCN": 3, "UC": 4, "INFRA": 5, "DOM": 6, "UI": 7, "API": 8, "SEQ": 9, "MS": 10, "CODE": 11, "STD": None}

# ───────────────────────── 전체 문서 인덱스 (참조·하위 계산용) ─────────────────────────
def parse_doc(raw, path):
    """원본 MD → {fm, body, items, refs, file, path}. frontmatter가 없으면 None"""
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m: return None
    fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in m.group(1).split("\n"))}
    body = raw[m.end():]
    nocode = re.sub(r"```.*?```", "", body, flags=re.S); nocode = re.sub(r"`[^`]*`", "", nocode)
    items = []
    for h in re.findall(r"^(#{1,6}) (.+)$", nocode, re.M):
        tok = h[1].split(" ")[0]
        if not re.match(r"^\d", tok) and re.match(r"^[A-Za-z]", tok): items.append((tok, h[1][len(tok):].strip()))
    refs = re.findall(r"\[\[([^\]]+)\]\]", nocode)
    return {"fm": fm, "body": body, "items": dict(items), "refs": refs, "file": os.path.basename(path), "path": path}

def load_all():
    docs = {}
    for f in glob.glob(os.path.join(SRC_DIR, "*", "*.md")):
        if "/_templates/" in f: continue
        d = parse_doc(open(f, encoding="utf-8").read(), f)
        if d: docs[d["fm"]["doc_id"]] = d
    return docs
ALL = load_all()
# 프로젝트 코드는 문서 이름에서 읽는다 — 한 저장소 = 한 프로젝트 (STD-004 4장, #57)
CODE = sorted({d.split("-")[0] for d in ALL})[0] if ALL else "?"

def use_root(specs_dir, out_dir=None):
    """명세 뿌리를 바꾼다 — 기본값만 자기 저장소다 (STD-004, #126).
    싱크독 자기 뿌리면 출력은 docs/views/, 다른 뿌리면 docs/views/{코드}/ — 그 저장소를 건드리지 않는다.
    그때 배치의 상대 경로(<base>)는 그 저장소 docs/specs를 file:// 절대 경로로 가리킨다"""
    global SRC_DIR, OUT_DIR, CODE
    import wf_build as wf
    SRC_DIR = os.path.abspath(specs_dir)
    ALL.clear(); ALL.update(load_all())
    CODE = sorted({d.split("-")[0] for d in ALL})[0] if ALL else "?"
    own = SRC_DIR == os.path.join(ROOT, "docs", "specs")
    OUT_DIR = out_dir or (os.path.join(ROOT, "docs", "views") if own else os.path.join(ROOT, "docs", "views", CODE))
    wf.SPECS_BASE = "../specs/" if own else pathlib.Path(SRC_DIR).as_uri() + "/"
    os.makedirs(OUT_DIR, exist_ok=True)

def view_href(doc_id): return f"view_{doc_id}.html"

# ───────────────────────── 인라인 마크다운 ─────────────────────────
def esc(s): return html.escape(s or "")
def inline(s, self_id):
    s = esc(s)
    codes = []
    def keep(m): codes.append(m.group(1)); return f"\x00{len(codes)-1}\x00"
    s = re.sub(r"`([^`]+)`", keep, s)   # 코드 스팬은 참조·강조 처리에서 제외 (STD-001 1.4)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    def ref(m):
        r = m.group(1); d, _, it = r.partition("#"); d = d or self_id
        exists = d in ALL and (not it or it in ALL[d]["items"])
        label = r if d != self_id else ("#" + it)
        href = view_href(d) + (f"#item-{it}" if it else "")
        cls = "ref" if exists else "ref missing"
        return f'<a class="{cls}" href="{href}">{esc(label)}</a>'
    s = re.sub(r"\[\[([^\]]+)\]\]", ref, s)
    s = re.sub(r"(?<![\w/])(https?://[^\s<]+)", r'<a href="\1">\1</a>', s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s

# ───────────────────────── 블록 마크다운 → HTML (공통 렌더러) ─────────────────────────
# 문단을 끊는 줄 — 헤딩·코드블록·표·목록·인용·구분선. 시나리오 단계의 첫 문단도 여기서 끊는다
BLOCK_START = re.compile(r"^(#{1,6} |```|\||\s*- |\d+\. |> |---$)")

def render_blocks(text, self_id, item_pat=None, common=""):
    """헤딩·문단·목록·표·코드블록. 항목 헤딩은 뱃지. mermaid는 <pre class=mermaid>.
    common = 그 문서 공통 틀 html — 화면 「그 밖」의 둘째 html 블록만 준다(STD-002 V-UI, #152). 나머지 html 블록은 공통 틀 없이"""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            lang = l[3:].strip(); j = i + 1; code = []
            while j < len(lines) and not lines[j].startswith("```"): code.append(lines[j]); j += 1
            src = "\n".join(code)
            if lang == "mermaid": out.append(f'<div class="mer"><pre class="mermaid">{esc(src)}</pre></div>')
            elif lang == "html":
                # html 블록은 iframe에 격리한다(STD-002 V-UI, 카드 Z). 스타일·링크뿐이면 코드로 보인다
                import wf_build as wf
                layout = wf.safe_layout(src)
                if wf.split_common(layout)[1]: out.append(wf.frame_html(layout, common, wf.base_for(self_id)))
                else: out.append(f'<pre class="code" data-lang="html"><code>{esc(src)}</code></pre>')
            else: out.append(f'<pre class="code" data-lang="{esc(lang)}"><code>{esc(src)}</code></pre>')
            i = j + 1; continue
        h = re.match(r"^(#{1,6}) (.+)$", l)
        if h:
            lvl = len(h.group(1)); text_ = h.group(2); tok = text_.split(" ")[0]
            is_item = item_pat and re.fullmatch(item_pat, tok) and not re.match(r"^\d", tok)
            if is_item:
                title = text_[len(tok):].strip()
                out.append(f'<h{lvl} class="item" id="item-{esc(tok)}"><span class="iid">{esc(tok)}</span>{inline(title, self_id)}</h{lvl}>')
            else:
                out.append(f'<h{lvl} id="sec-{esc(re.sub(r"[^\w]", "", text_))}">{inline(text_, self_id)}</h{lvl}>')
            i += 1; continue
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            if rows:
                th = "".join(f"<th>{inline(c, self_id)}</th>" for c in rows[0])
                tb = "".join("<tr>" + "".join(f"<td>{inline(c, self_id)}</td>" for c in r) + "</tr>" for r in rows[1:])
                out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue
        if re.match(r"^\s*- \[[ x]\] ", l):
            items = []
            while i < len(lines) and re.match(r"^\s*- \[[ x]\] ", lines[i]):
                chk = "x" in lines[i][:8]; items.append((chk, inline(re.sub(r"^\s*- \[[ x]\] ", "", lines[i]), self_id))); i += 1
            out.append('<ul class="ac">' + "".join(f'<li class="{"done" if c else ""}"><span class="box">{"✓" if c else ""}</span>{t}</li>' for c, t in items) + "</ul>"); continue
        if re.match(r"^\s*- ", l):
            items = []
            while i < len(lines) and re.match(r"^\s*- ", lines[i]):
                ind = len(lines[i]) - len(lines[i].lstrip()); items.append((ind, inline(re.sub(r"^\s*- ", "", lines[i]), self_id))); i += 1
            out.append("<ul>" + "".join(f'<li style="margin-left:{ind//2*14}px">{t}</li>' for ind, t in items) + "</ul>"); continue
        if re.match(r"^\d+\. ", l):
            items = []
            while i < len(lines) and (re.match(r"^\d+[a-z]?\. ", lines[i]) or lines[i].startswith("   ")):
                if re.match(r"^\d+[a-z]?\. ", lines[i]): items.append(inline(re.sub(r"^\d+[a-z]?\. ", "", lines[i]), self_id))
                elif items: items[-1] += "<br>" + inline(lines[i].strip(), self_id)
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"); continue
        if l.startswith("> "):
            q = []
            while i < len(lines) and lines[i].startswith("> "): q.append(inline(lines[i][2:], self_id)); i += 1
            out.append('<blockquote>' + "<br>".join(q) + "</blockquote>"); continue
        if l.strip() == "---": out.append("<hr>"); i += 1; continue
        if l.strip() == "": i += 1; continue
        para = []
        while i < len(lines) and lines[i].strip() and not BLOCK_START.match(lines[i]):
            para.append(lines[i]); i += 1
        out.append(f"<p>{inline(' '.join(para), self_id)}</p>")
    return "\n".join(out)

def split_sections(body):
    """## 절 단위로 자른다 → [(제목, 본문)]"""
    parts = re.split(r"^## ", body, flags=re.M)
    out = []
    for p in parts[1:]:
        title, _, rest = p.partition("\n"); out.append((title.strip(), rest))
    return out

def split_items(body, pat):
    """본문을 원본 순서대로 가른다 → [("text", md) | ("item", (id, title, level, text))].
    항목 블록은 헤딩 다음 줄부터 같은 레벨 이상 다음 헤딩 직전까지. 항목 밖 문장(절 머리·소절 제목·
    소절 머리)도 "text"로 남는다 — 버리면 유저용 탭에서 조용히 사라진다 (STD-002 V-PRD, #120)"""
    lines = body.split("\n"); out = []; buf = []; i = 0
    while i < len(lines):
        h = re.match(r"^(#{1,6}) (\S+)(?: (.*))?$", lines[i])
        if h and re.fullmatch(pat, h.group(2)) and not re.match(r"^\d", h.group(2)):
            if buf: out.append(("text", "\n".join(buf))); buf = []
            lvl = len(h.group(1)); j = i + 1
            while j < len(lines):
                h2 = re.match(r"^(#{1,6}) ", lines[j])
                if h2 and len(h2.group(1)) <= lvl: break
                j += 1
            out.append(("item", (h.group(2), h.group(3) or "", lvl, "\n".join(lines[i + 1:j])))); i = j
        else: buf.append(lines[i]); i += 1
    if buf: out.append(("text", "\n".join(buf)))
    return out

def item_blocks(body, pat):
    """항목 헤딩 블록 → [(id, title, level, text)]. split_items에서 항목만"""
    return [x for k, x in split_items(body, pat) if k == "item"]

# ───────────────────────── 공통 틀 ─────────────────────────
def downstream_of(doc_id):
    """다른 문서가 이 문서(또는 항목)를 참조한 것 → {문서ID: [항목ID들]}"""
    out = {}
    for d, info in ALL.items():
        if d == doc_id: continue
        for r in info["refs"]:
            td, _, ti = r.partition("#"); td = td or d
            if td == doc_id: out.setdefault(d, set()).add(ti or "(문서)")
        if doc_id in info["fm"].get("upstream", ""): out.setdefault(d, set()).add("(frontmatter)")
    return out

def shell(doc, body_html, extra_nav=""):
    fm = doc["fm"]; did = fm["doc_id"]
    # 프로젝트 코드를 박지 않는다 — `SYNC-`로 고정돼 있어 남의 프로젝트에서는 실패하지
    # 않고 상위 링크만 통째로 비었다 (STD-004 4장, #57)
    ups = re.findall(r"[A-Z]{1,4}-[A-Z]+-\d+", fm.get("upstream", ""))
    up_html = " · ".join(f'<a class="ref" href="{view_href(u)}">{u}</a>' for u in ups) or "—"
    downs = downstream_of(did)
    down_html = " · ".join(f'<a class="ref" href="{view_href(d)}" title="{esc(", ".join(sorted(v)))}">{d}</a>' for d, v in sorted(downs.items())) or "—"
    first_p = ""
    m = re.search(r"## 0\. .*?\n\n(.+?)\n", doc["body"], re.S)
    if m: first_p = inline(m.group(1), did)
    stage = STAGE.get(fm["type"]); stage_txt = f"{stage}단계 {fm['type']}" if stage else f"단계 밖 {fm['type']}"
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(fm['title'])}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
<script>window.__mermaidReady=new Promise(r=>{{const t=s=>{{if(!s.length)return r(false);const x=document.createElement("script");x.src=s[0];x.onload=()=>r(true);x.onerror=()=>t(s.slice(1));document.head.appendChild(x);}};t(["https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js","https://unpkg.com/mermaid@11/dist/mermaid.min.js"]);}});</script>
</head><body><div class="wrap">
<header class="tb">
  <div class="tb-main">
    <div class="tb-kicker"><a href="index.html">싱크독</a> · {stage_txt}</div>
    <h1>{esc(fm['title'])}</h1>
    <p>{first_p}</p>
  </div>
  <div class="tb-meta">
    <div>문서</div><div class="mono">{did}</div>
    <div>상태</div><div><span class="st st-{fm['status']}">{STATUS_KO[fm['status']]}</span></div>
    <div>상위</div><div>{up_html}</div>
    <div>하위</div><div>{down_html}</div>
    <div>항목</div><div>{len(doc['items'])}개</div>
  </div>
</header>
{extra_nav}
<main class="body">{body_html}</main>
<footer>이 화면은 <code>{esc(doc['file'])}</code>에서 생성된 사람용 뷰(STD-002)다. 고치려면 원본을 고친다. 참조 링크는 다른 문서의 뷰로 간다.</footer>
</div>
<script>window.__mermaidReady.then(ok=>{{if(!ok||typeof mermaid==="undefined"){{document.querySelectorAll("pre.mermaid").forEach(p=>{{p.classList.add("nomer");}});return;}}mermaid.initialize({{startOnLoad:false,theme:"neutral"}});mermaid.run({{querySelector:"pre.mermaid"}}).catch(e=>console.warn(e));}});
document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{{const g=b.dataset.group;document.querySelectorAll(`[data-tab][data-group="${{g}}"]`).forEach(x=>x.classList.toggle("on",x===b));document.querySelectorAll(`[data-pane][data-group="${{g}}"]`).forEach(p=>p.style.display=p.dataset.pane===b.dataset.tab?"":"none");}});
</script></body></html>"""

# ───────────────────────── 항목 카드 (V-PRD 목표·요구사항, V-INFRA 제약) ─────────
def item_card(did, iid, title, inner, down, label, pills=""):
    """머리 ID 뱃지·제목·필·`하위 N` · 몸 · 바닥 "{label}: 문서들". 하위가 없으면 필·바닥을 안 그린다"""
    card = f'<article class="card" id="item-{iid}"><div class="card-h"><span class="iid">{iid}</span><b>{inline(title, did)}</b>{pills}'
    if down: card += f'<span class="pill soft">하위 {len(down)}</span>'
    card += "</div>" + inner
    if down: card += f'<div class="down">{label}: ' + " · ".join(f'<a class="ref" href="{view_href(d)}">{d}</a>' for d in down) + "</div>"
    return card + "</article>"

def item_cards(did, text, pat, label, dmap):
    """절 본문 → 항목 밖 문장은 그대로, 항목은 본문 전부를 몸으로 한 카드 (V-PRD 목표·V-INFRA 제약, #120)"""
    return "".join(render_blocks(x, did) if k == "text" else
                   item_card(did, x[0], x[1], render_blocks(x[3], did), sorted(d for d, v in dmap.items() if x[0] in v), label)
                   for k, x in split_items(text, pat))

def etc_block(lines, did, common=""):
    """「그 밖」 — 뷰가 조각으로 가르고 남은 줄을 항목 카드 끝에 원본 순서로 (STD-002 1장, #152).
    구분선·빈 줄뿐이면 그리지 않는다 — 문장이 아니라 절 사이 표시다(절 구분선 `---`이 마지막 항목 블록에 들어온다)"""
    if all(l.strip() in ("", "---") for l in lines): return ""
    return f'<div class="etc"><div class="etc-t">그 밖</div>{render_blocks(chr(10).join(lines), did, common=common)}</div>'

# ───────────────────────── V-PRD ─────────────────────────
def v_prd(doc):
    did = doc["fm"]["doc_id"]; body = doc["body"]; pat = r"G\d+|R\d+|N\d+"
    secs = split_sections(body); out = []; dmap = downstream_of(did)
    for title, text in secs:
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("목표"):
            out.append(f"<h2>{esc(title)}</h2>" + item_cards(did, text, r"G\d+", "이 목표를 근거로 삼은 문서", dmap))
            continue
        if name.startswith("요구사항"):
            out.append(f"<h2>{esc(title)}</h2>")
            # 절 머리·소절(### 3.1 …) 제목·소절 머리는 그대로, 항목은 카드
            for k, x in split_items(text, r"R\d+|N\d+"):
                if k == "text": out.append(render_blocks(x, did)); continue
                rid, rt, _, rb = x
                ac = re.findall(r"^- \[([ x])\] (.+)$", rb, re.M)
                done = sum(1 for c, _ in ac if c == "x")
                desc = re.sub(r"^- \[[ x]\] .+$", "", rb, flags=re.M).strip()
                inner = render_blocks(desc, did)
                if ac: inner += '<ul class="ac">' + "".join(f'<li class="{"done" if c=="x" else ""}"><span class="box">{"✓" if c=="x" else ""}</span>{inline(t, did)}</li>' for c, t in ac) + "</ul>"
                pills = f'<span class="pill">인수기준 {done}/{len(ac)}</span>' if ac else ""
                out.append(item_card(did, rid, rt, inner, sorted(d for d, v in dmap.items() if rid in v), "이 요구사항을 근거로 삼은 문서", pills))
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, pat))
    # 추적표 (원본에 없음. 참조 테이블에서)
    downs = downstream_of(did)
    if downs:
        rows = "".join(f'<tr><td><a class="ref" href="{view_href(d)}">{d}</a></td><td>{esc(ALL[d]["fm"]["title"])}</td><td>{esc(", ".join(sorted(v)))}</td></tr>' for d, v in sorted(downs.items()))
        out.append(f'<h2>추적표 — 이 문서를 근거로 삼은 문서</h2><p class="soft">원본에 없다. 다른 문서의 참조에서 계산했다.</p><table class="trace"><thead><tr><th>문서</th><th>제목</th><th>참조한 항목</th></tr></thead><tbody>{rows}</tbody></table>')
    return "\n".join(out)

# ───────────────────────── V-RFQ ─────────────────────────
def v_rfq(doc):
    """원본 순서 그대로. Q 항목에 뱃지. 인터뷰 기록이라 순서가 뜻이다. 끝에 추적표 — RFQ는 모든 것의 근거라 누가 무엇을 근거로 삼았는지가 값어치."""
    did = doc["fm"]["doc_id"]
    out = [render_blocks(doc["body"], did, r"Q\d+")]
    downs = downstream_of(did)
    if downs:
        # Q 항목별로 뒤집어 본다: 어느 요구가 어느 문서에서 근거로 쓰였나
        by_q = {}
        for d, v in downs.items():
            for it in v: by_q.setdefault(it, set()).add(d)
        rows = "".join(f'<tr><td class="iid">{esc(q)}</td><td>{inline(doc["items"].get(q, ""), did)}</td><td>{" · ".join(f"<a class=\"ref\" href=\"{view_href(d)}\">{d}</a>" for d in sorted(ds))}</td></tr>' for q, ds in sorted(by_q.items(), key=lambda x: (x[0]=="(문서)", x[0])))
        out.append(f'<h2>추적표 — 요구가 어디로 갔나</h2><p class="soft">원본에 없다. 다른 문서의 참조에서 계산했다. 어느 요구도 근거로 안 쓰였다면 그 요구는 구현 계획이 없는 것이다.</p><table class="trace"><thead><tr><th>요구</th><th>내용</th><th>근거로 삼은 문서</th></tr></thead><tbody>{rows}</tbody></table>')
        unused = [q for q in doc["items"] if q not in by_q]
        if unused: out.append(f'<p class="warn">근거로 쓰이지 않은 요구: {", ".join(unused)}</p>')
    return "\n".join(out)

# ───────────────────────── V-SCN ─────────────────────────
def scn_parts(text):
    """S 블록 → (머리, [단계], [변형], 꼬리, 그 밖) 줄 목록. 규약 조각대로 가르고 안 맞는 줄은 그 밖 (STD-002 V-SCN, #152).
    단계는 번호 줄 + 빈 줄 없이 이어진 줄·들여 쓴 줄. 변형은 `**변형` 줄부터 다음 변형·성공 조건·연관 줄 전까지 전부.
    꼬리는 `**성공 조건`·`**연관` 줄부터 다음 변형 전까지. 코드블록 안 줄은 여는 줄이 든 조각을 따른다"""
    head, steps, variants, tail, etc = [], [], [], [], []
    cur, mode, fence, blank = head, "head", False, False
    for l in text.split("\n"):
        if fence:
            cur.append(l); fence = not l.lstrip().startswith("```"); continue
        if l.startswith("**변형"): variants.append([]); cur, mode = variants[-1], "var"
        elif l.startswith(("**성공 조건", "**연관")): cur, mode = tail, "tail"
        elif mode in ("var", "tail"): pass
        elif re.match(r"^\d+\. ", l): steps.append([]); cur, mode = steps[-1], "steps"
        elif mode == "steps" and (not l.strip() or l[:1] in (" ", "\t") or not blank): pass
        elif mode in ("steps", "etc"): cur, mode = etc, "etc"
        cur.append(l)
        fence = l.lstrip().startswith("```"); blank = not l.strip()
    return head, steps, variants, tail, etc

def lead_rest(first, more, width):
    """목록 항목 하나 → (첫 문단, 나머지). 첫 문단은 빈 줄 없이 이어진 줄까지 공백으로 잇고, 나머지는 표시 너비만큼
    들여쓰기를 뗀다 — 시나리오 단계(V-SCN)·화면 규칙·화면 시나리오 단계(V-UI)가 같이 쓴다 (#152)"""
    rest = [re.sub("^ {1,%d}" % width, "", l) for l in more]
    lead = [first]
    while rest and rest[0].strip() and not BLOCK_START.match(rest[0]): lead.append(rest.pop(0))
    return " ".join(lead), "\n".join(rest)

def step_html(lines, did):
    """단계 하나 — 첫 문단은 번호 옆, 나머지(밑 목록·둘째 문단)는 그 아래. 한 줄 단계는 전과 같은 HTML이다 (#152)"""
    num = re.match(r"^\d+\. ", lines[0]).group(0)
    lead, rest = lead_rest(lines[0][len(num):], lines[1:], len(num))
    return inline(lead, did) + render_blocks(rest, did)

def variant_html(lines, did):
    """변형 하나 — 접힘. 이름은 summary, 첫 줄 나머지부터 다음 표시 줄 전까지가 몸. 한 줄 변형은 전과 같은 HTML (#152)"""
    m = re.match(r"\*\*(변형[^*]*)\*\*:?\s*(.*)", lines[0])
    name, first = (m.group(1), m.group(2)) if m else ("변형", lines[0])
    return f'<details class="variant"><summary>{esc(name)}</summary>{render_blocks(chr(10).join([first] + lines[1:]), did)}</details>'

def scn_card(did, sid, title, text):
    """S 카드 — 머리 ID·제목·`N단계` / 주체·상황 → 단계 타임라인 → 변형(접힘) → 성공 조건·연관 → 그 밖"""
    head, steps, variants, tail, etc = scn_parts(text)
    lis = "".join(f"<li>{step_html(s, did)}</li>" for s in steps)
    vars_ = "".join(variant_html(v, did) for v in variants)
    return (f'<article class="scard" id="item-{sid}"><div class="card-h"><span class="iid">{sid}</span><b>{inline(title, did)}</b><span class="pill soft">{len(steps)}단계</span></div>'
            f'{render_blocks(chr(10).join(head), did)}<ol class="steps">{lis}</ol>{vars_}{render_blocks(chr(10).join(tail), did)}{etc_block(etc, did)}</article>')

def v_scn(doc):
    """페르소나 P 카드 나란히 · 시나리오 S 카드(scn_card) · 대응표 그대로.
    항목 밖 문장(절 머리·소절 제목·소절 머리)은 원본 순서 그대로 — 항목 헤딩 단계와 무관하다. 전에는 절 머리를
    `### `·`#### ` 글자로 잘라, 항목 헤딩이 다른 단계면 절 전체가 한 번 더 그려졌다 (STD-002 V-SCN, #152)"""
    did = doc["fm"]["doc_id"]; out = []
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("페르소나"):
            body = grid = ""  # 이어진 P 카드끼리 한 그리드
            for k, x in split_items(text, r"P\d+"):
                if k == "item":
                    grid += f'<article class="pcard" id="item-{x[0]}"><div class="card-h"><span class="iid">{x[0]}</span><b>{inline(x[1], did)}</b></div>{render_blocks(x[3], did)}</article>'
                    continue
                if grid: body += f'<div class="pgrid">{grid}</div>'; grid = ""
                body += render_blocks(x, did)
            if grid: body += f'<div class="pgrid">{grid}</div>'
            out.append(f"<h2>{esc(title)}</h2>{body}"); continue
        if name.startswith("시나리오"):
            out.append(f"<h2>{esc(title)}</h2>" + "".join(render_blocks(x, did) if k == "text" else scn_card(did, x[0], x[1], x[3])
                                                         for k, x in split_items(text, r"S\d+")))
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"P\d+|S\d+"))
    return "\n".join(out)

# ───────────────────────── V-UC ─────────────────────────
UC_PAT = r"UC-[AHGS]\d+"
UC_ACTOR = {"A": "agent", "H": "human", "G": "github", "S": "system"}
UC_HEX = {"agent": "#12776A", "human": "#3A5BA0", "github": "#6B4A9E", "system": "#8A6D1F"}
UC_LABEL = {"agent": "에이전트", "human": "사람", "github": "GitHub", "system": "하위기능"}
UC_REL = ("패키지", "포함", "확장점", "일반화")
UC_FLOW = re.compile(r"^\*\*(기본 흐름[^*]*)\*\*(.*)$")
UC_EXT = re.compile(r"^\*\*(확장(?!점)[^*]*)\*\*(.*)$")
UC_NOTE = re.compile(r"^\*\*(사후조건 참고[^*]*)\*\*(.*)$")
UC_LINK = re.compile(r"^\*\*(연관[^*]*)\*\*(.*)$")
UC_EXT_ITEM = re.compile(r"^- \*\*(.+?)\*\*(.*)$")
UC_STEP = re.compile(r"^(\d+\.\s+)")
UC_CHIP = re.compile(r"(?<![A-Za-z0-9_#-])(UC-[AHGS]\d+|[AHGS]\d+)(?![A-Za-z0-9_])")  # 대응표 칩 — 맨몸 UC-A1·짧은 A1

def uc_key(k):
    """항목 표 행 이름 — 괄호 앞만 본다(`포함(include)` = `포함`)"""
    return re.sub(r"\s*\(.*\)\s*$", "", k).strip()

def _uc_after(s):
    """`**연관**: …`의 머리 뒤 글 — 쌍점과 빈칸을 뗀다"""
    return re.sub(r"^\s*:?\s*", "", s)

def uc_parts(text):
    """유스케이스 블록 하나를 줄 단위로 가른다(코드 펜스 인식) → {rows, flows, exts, note, links, etc} (STD-002 V-UC, #152).
    항목 표 = 첫 두 칸 표(머리 행은 뺀다). `**기본 흐름…**`·`**확장…**`·`**사후조건 참고**`·`**연관**` 줄이 조각을 연다 —
    흐름은 번호 줄이 단계, 확장은 `- **2a. 제목**` 줄이 한 확장이고, 빈 줄 없이 이어진 줄·들여 쓴 줄은 그 안.
    어디에도 안 맞는 줄은 etc(「그 밖」). frontend uc.ts ucParts와 같은 규칙"""
    import wf_build as wf
    lines = text.split("\n"); n = len(lines)
    fenced, _ = wf._fences(lines)
    used, rows = set(), []
    trows, a, b = wf._first_table(lines, fenced, 0, n)
    if len(trows) >= 2 and all(len(r) == 2 for r in trows):
        rows = [(r[0], r[1]) for r in trows[1:]]
        used.update(range(a, b))
    flows, exts, note, links = [], [], None, None
    mode, into, blank, fence = "", None, False, False
    for i in range(n):
        if i in used: continue
        l = lines[i]
        if fence:
            if into is not None: into.append(l); used.add(i)
            fence = not l.lstrip().startswith("```")
            continue
        if (m := UC_FLOW.match(l)):
            flows.append({"name": m.group(1).strip(), "lead": _uc_after(m.group(2)), "steps": []}); mode, into = "flow", None; used.add(i)
        elif (m := UC_EXT.match(l)):
            exts.append({"name": m.group(1).strip(), "lead": _uc_after(m.group(2)), "items": []}); mode, into = "ext", None; used.add(i)
        elif (m := UC_NOTE.match(l)):
            note = {"name": m.group(1).strip(), "lines": [_uc_after(m.group(2))]}; mode, into = "note", note["lines"]; used.add(i)
        elif (m := UC_LINK.match(l)):
            links = {"name": m.group(1).strip(), "lines": [_uc_after(m.group(2))]}; mode, into = "link", links["lines"]; used.add(i)
        elif mode == "flow" and UC_STEP.match(l):
            into = [l]; flows[-1]["steps"].append(into); used.add(i)
        elif mode == "ext" and (m := UC_EXT_ITEM.match(l)):
            it = {"on": m.group(1).strip(), "extra": m.group(2), "lines": []}; exts[-1]["items"].append(it); into = it["lines"]; used.add(i)
        elif into is not None and (not l.strip() or l[:1] in (" ", "\t") or not blank):
            into.append(l); used.add(i)  # 이어진 줄 — 빈 줄 없이 이어지거나 들여 쓴 줄
        else:
            into = None  # 그 밖 — 모드는 그대로(다음 번호 줄은 같은 흐름)
        fence = l.lstrip().startswith("```"); blank = not l.strip()
    etc, gap = [], False
    for i in range(n):
        if i in used: gap = True; continue
        if gap and etc and etc[-1].strip(): etc.append("")  # 쓰인 줄을 건너뛴 자리 — 앞뒤 문단이 붙지 않게
        gap = False; etc.append(lines[i])
    return {"rows": rows, "flows": flows, "exts": exts, "note": note, "links": links, "etc": etc}

def uc_inner(uid, p, did):
    """카드 몸 — 항목 표 → 기본 흐름 → 확장 → 사후조건 참고 → 연관 → 그 밖 (문서 순서, STD-002 V-UC)"""
    hexc = UC_HEX[UC_ACTOR.get(uid[3:4], "system")]
    h = ""
    if p["rows"]:
        trs = ""
        for k, v in p["rows"]:
            key = uc_key(k)
            # 표 칸 안 줄바꿈은 <br>로 쓴다(마크다운 표는 줄을 못 나눈다) — 예전 상세 칸처럼 줄바꿈으로 되살린다
            val = re.sub(r"&lt;br\s*/?&gt;", "<br>", inline(v, did))
            val = f'<span class="lv">{val}</span>' if key == "수준" else val
            trs += f'<tr{" class=\"rel\"" if key in UC_REL else ""}><th>{inline(k, did)}</th><td>{val}</td></tr>'
        h += f'<table class="attrs">{trs}</table>'
    for f in p["flows"]:
        h += f'<p class="sec-t">{esc(f["name"])}</p>' + (render_blocks(f["lead"], did) if f["lead"].strip() else "")
        lis = ""
        for st in f["steps"]:
            w = len(UC_STEP.match(st[0]).group(1))
            lead, rest = lead_rest(st[0][w:].strip(), st[1:], w)
            lis += f"<li>{inline(lead, did)}{render_blocks(rest, did)}</li>"
        h += f'<ol class="flow">{lis}</ol>'
    for e in p["exts"]:
        h += f'<p class="sec-t">{esc(e["name"])}</p>' + (render_blocks(e["lead"], did) if e["lead"].strip() else "")
        items = ""
        for it in e["items"]:
            m = re.match(r"^((?:\d+|\*)[a-z])\.\s*(.+)$", it["on"])
            title = (m.group(2) if m else it["on"]) + it["extra"]
            _, rest = lead_rest("", it["lines"], 2)
            items += (f'<div class="ext-item" style="border-left-color:{hexc}"><div class="ext-on"><span class="br">{esc(m.group(1)) if m else ""}</span>'
                      f'{inline(title, did)}</div>{render_blocks(rest, did)}</div>')
        h += f'<div class="ext">{items}</div>'
    for piece in (p["note"], p["links"]):
        if piece: h += f'<p class="sec-t">{esc(piece["name"])}</p><div class="note">{render_blocks(chr(10).join(piece["lines"]), did)}</div>'
    # 조각이 하나도 없는 항목(Cockburn이 아닌 문서)은 본문 전부를 그대로 — 「그 밖」 머리를 달지 않는다(V-SCN과 같다)
    return h + etc_block(p["etc"], did) if h else render_blocks(chr(10).join(p["etc"]), did)

def _map_text(h, fn):
    """HTML의 글자 조각에만 fn — 태그 속성과 <a> 안 글자는 건드리지 않는다"""
    out, depth = [], 0
    for tok in re.split(r"(<[^>]+>)", h):
        if tok.startswith("<"):
            if re.match(r"<a[\s>]", tok): depth += 1
            elif tok.startswith("</a"): depth = max(0, depth - 1)
            out.append(tok)
        else: out.append(fn(tok) if depth == 0 and tok else tok)
    return "".join(out)

def _uc_a(uid, did, cls, text):
    return f'<a class="{cls}" href="{view_href(did)}#item-{uid}">{esc(text)}</a>'

def uc_jumps(h, ids, did):
    """글자 속 맨몸 `UC-xx`(`#` 뒤 제외)를 그 카드로 가는 링크로. 있는 유스케이스만 (STD-002 V-UC)"""
    return _map_text(h, lambda t: re.sub(r"(?<![A-Za-z0-9_#-])(UC-[AHGS]\d+)(?![A-Za-z0-9_])",
                                         lambda m: _uc_a(m.group(1), did, "jump", m.group(1)) if m.group(1) in ids else m.group(1), t))

def uc_chips(h, ids, did):
    """대응표의 표마다 머리 칸에 「유스케이스」가 든 열의 `UC-A1`·`A1`을 칩으로. 다른 열은 글자 그대로 (사용자 결정, #152)"""
    def chip(m):
        uid = m.group(1) if m.group(1).startswith("UC-") else "UC-" + m.group(1)
        return _uc_a(uid, did, "chip", m.group(1)) if uid in ids else m.group(1)
    def table(tm):
        inner = tm.group(1)
        head = re.search(r"<thead>(.*?)</thead>", inner, re.S)
        cols = {j for j, c in enumerate(re.findall(r"<th>(.*?)</th>", head.group(1) if head else "", re.S)) if "유스케이스" in re.sub(r"<[^>]+>", "", c)}
        def row(rm):
            cells = re.findall(r"<td>(.*?)</td>", rm.group(1), re.S)
            return "<tr>" + "".join("<td>" + (_map_text(c, lambda t: UC_CHIP.sub(chip, t)) if j in cols else c) + "</td>" for j, c in enumerate(cells)) + "</tr>"
        body = re.sub(r"<tbody>(.*?)</tbody>", lambda bm: "<tbody>" + re.sub(r"<tr>(.*?)</tr>", row, bm.group(1), flags=re.S) + "</tbody>", inner, flags=re.S)
        return f"<table>{body}</table>"
    return re.sub(r"<table>(.*?)</table>", table, h, flags=re.S)

def uc_node(uid, name, p):
    """패키지 그림 한 개 — 항목 표에서 관계(행 이름 두 가지 다)"""
    row = lambda k: next((v for x, v in p["rows"] if uc_key(x) == k), "")
    return {"id": uid, "name": name, "actor": UC_ACTOR.get(uid[3:4], "system"), "package": row("패키지"),
            "include": row("포함"), "extPoint": row("확장점"), "general": row("일반화")}

def uc_actors(sec):
    """`액터` 절 표에서 코드(A·H·G·S) 칸이 있는 행의 이름. 없으면 기본 이름"""
    out = dict(UC_LABEL)
    for line in sec.split("\n"):
        if not line.strip().startswith("|"): continue
        cs = [c.strip() for c in line.strip().strip("|").split("|")]
        code = next((c for c in cs if re.fullmatch(r"[AHGS]", c)), None)
        label = next((c for c in cs if c and c != code), None)
        if code and label: out[UC_ACTOR[code]] = label
    return out

UC_LEGEND = """<div class="key">
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#5C6B73" stroke-width="1.2"/></svg>연결</span>
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="27" y2="5" stroke="#5C6B73" stroke-width="1.2" stroke-dasharray="6 4"/><path d="M27,1 L34,5 L27,9" fill="none" stroke="#5C6B73" stroke-width="1.2"/></svg>«include» / «extend»</span>
  <span><svg width="34" height="12"><line x1="0" y1="6" x2="24" y2="6" stroke="#5C6B73" stroke-width="1.2"/><path d="M24,1 L34,6 L24,11 Z" fill="#fff" stroke="#5C6B73" stroke-width="1.2"/></svg>일반화</span>
  <span><svg width="30" height="14"><ellipse cx="15" cy="7" rx="13" ry="6" fill="#F8F9F7" stroke="#5C6B73" stroke-width="1.4" stroke-dasharray="6 4"/></svg>추상·다른 패키지</span>
</div>"""

def v_uc(doc):
    """V-UC — 원본 순서로 펼친다. 절·소절 머리는 그대로, 유스케이스는 제자리에 카드, 대응표는 원본 표 + 「유스케이스」 열 칩,
    패키지 그림은 뷰 끝 (STD-002 V-UC, 카드 AM). frontend uc.ts vUc와 한 쌍.
    전에는 옛 parse.py가 옛 경로를 읽다 실패해 어느 문서를 넣든 낡은 싱크독 데이터(data.json)를 그렸다 (#152)"""
    did = doc["fm"]["doc_id"]; body = doc["body"]
    ids = {x[0] for x in item_blocks(body, UC_PAT)}
    dmap = downstream_of(did); out = []; nodes = []; actor_sec = ""
    for title, text in split_sections(body):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("액터"): actor_sec = text
        if name.startswith("대응표"):
            out.append(f"<h2>{esc(title)}</h2>" + uc_jumps(uc_chips(render_blocks(text, did), ids, did), ids, did)); continue
        html_ = ""
        for k, x in split_items(text, UC_PAT):
            if k == "text": html_ += uc_jumps(render_blocks(x, did), ids, did); continue
            parts = uc_parts(x[3]); nodes.append(uc_node(x[0], x[1], parts))
            html_ += item_card(did, x[0], x[1], uc_jumps(uc_inner(x[0], parts, did), ids, did),
                               sorted(d for d, v in dmap.items() if x[0] in v), "이 유스케이스를 근거로 삼은 문서")
        out.append(f"<h2>{esc(title)}</h2>{html_}")
    diagram = ("<h2>패키지 그림</h2>\n<p class=\"soft\">원본에 없다 — 항목 표의 패키지·포함·확장점·일반화 행과 주 액터(ID 글자)에서 그렸다. 타원을 누르면 그 유스케이스 카드로.</p>\n"
               "<div class=\"tabs\" id=\"tabs\" role=\"tablist\"></div>\n<div class=\"canvas\"><svg id=\"dg\" xmlns=\"http://www.w3.org/2000/svg\"></svg></div>\n" + UC_LEGEND)
    data = json.dumps({"ucs": nodes, "labels": uc_actors(actor_sec)}, ensure_ascii=False).replace("</", "<\\/")
    return (f'<style>{UC_CSS}</style><div class="v-uc">{chr(10).join(out)}\n{diagram}'
            f'<script type="application/json" id="uc-data">{data}</script><script>{UC_JS}</script></div>')

UC_CSS = r"""
.v-uc{
  --paper:#EDEFEC; --panel:#F8F9F7; --card:#fff;
  --ink:#1E2A30; --soft:#5C6B73; --faint:#8A969C;
  --rule:#C9CFCB; --hair:#E1E5E1;
  --agent:#12776A; --human:#3A5BA0; --github:#6B4A9E; --system:#8A6D1F;
  color:var(--ink); font-feature-settings:"tnum"; line-height:1.65}
.v-uc *{box-sizing:border-box}
.v-uc code,.v-uc .mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.v-uc code{font-size:.88em; background:#E4E8E4; padding:1px 5px; border-radius:2px}

.v-uc .tabs{display:flex; flex-wrap:wrap; border:1.5px solid var(--ink); border-bottom:none; background:var(--panel)}
.v-uc .tabs button{font:inherit; font-size:14px; padding:11px 18px; background:none; border:none;
  border-right:1px solid var(--rule); cursor:pointer; color:var(--soft); position:relative}
.v-uc .tabs button:last-child{border-right:none}
.v-uc .tabs button[aria-selected="true"]{background:var(--card); color:var(--ink); font-weight:700}
.v-uc .tabs button[aria-selected="true"]::after{content:""; position:absolute; left:0; right:0; bottom:-1.5px; height:3px; background:var(--ink)}
.v-uc .tabs button:focus-visible{outline:2px solid var(--ink); outline-offset:-4px}
.v-uc .tabs .cnt{color:var(--faint); font-size:12px; margin-left:6px; font-weight:400}
.v-uc .canvas{border:1.5px solid var(--ink); background:var(--card); overflow-x:auto}
.v-uc .canvas svg{display:block}

.v-uc .uc-el{fill:#fff; stroke-width:1.6; transition:fill .12s}
.v-uc .uc-el.abstract{stroke-dasharray:6 4; fill:var(--panel)}
.v-uc .uc-t{font-size:12.5px; fill:var(--ink); text-anchor:middle; pointer-events:none}
.v-uc .uc-k{font-size:10px; font-family:ui-monospace,Menlo,monospace; fill:var(--faint); text-anchor:middle; pointer-events:none}
.v-uc .uc-xp{font-size:9.5px; fill:var(--soft); text-anchor:middle; pointer-events:none}
.v-uc .uc-xp-h{font-size:9px; fill:var(--faint); text-anchor:middle; font-weight:600; pointer-events:none}
.v-uc g.uc{cursor:pointer}
.v-uc g.uc:hover .uc-el{fill:#F0F4F0}
.v-uc g.uc.sel .uc-el{fill:#FFF6D9; stroke-width:2.6}
.v-uc .assoc{stroke-width:1.2; fill:none}
.v-uc .dep{stroke-dasharray:6 4; stroke-width:1.2; fill:none}
.v-uc .gen{stroke-width:1.2; fill:none}
.v-uc .stereo{font-size:10px; fill:var(--soft); font-style:italic; text-anchor:middle}
.v-uc .a-name{font-size:13px; font-weight:600; text-anchor:middle}
.v-uc .ext-only{font-size:11px; fill:var(--faint); font-style:italic}

.v-uc .key{display:flex; flex-wrap:wrap; gap:20px; margin-top:10px; font-size:12.5px; color:var(--soft); align-items:center}
.v-uc .key span{display:inline-flex; align-items:center; gap:7px}
.v-uc .key svg{display:inline-block}

/* 유스케이스 카드 몸 — 항목 표 → 기본 흐름 → 확장 → 사후조건 참고·연관 (카드 AM) */
.v-uc table.attrs{border-collapse:collapse; width:100%; margin:4px 0 22px; font-size:14px; background:var(--card)}
.v-uc table.attrs th{text-align:left; vertical-align:top; width:158px; font-weight:600; color:var(--soft);
  padding:9px 14px 9px 0; border-bottom:1px solid var(--hair); white-space:nowrap}
.v-uc table.attrs td{vertical-align:top; padding:9px 0; border-bottom:1px solid var(--hair)}
.v-uc table.attrs tr:last-child th,.v-uc table.attrs tr:last-child td{border-bottom:none}
.v-uc table.attrs tr.rel th{background:#F4F7F3; padding-left:10px}
.v-uc table.attrs tr.rel td{background:#F4F7F3; padding-right:10px}
.v-uc .lv{display:inline-block; font-size:12px; padding:1px 9px; border:1px solid var(--rule); background:var(--panel)}
.v-uc .sec-t{font-size:13px; font-weight:700; margin:0 0 11px; padding-bottom:7px; border-bottom:1.5px solid var(--ink)}
.v-uc ol.flow{margin:0 0 22px; padding-left:0; list-style:none; counter-reset:f}
.v-uc ol.flow>li{counter-increment:f; position:relative; padding:6px 0 6px 38px; border-bottom:1px solid var(--hair)}
.v-uc ol.flow>li:last-child{border-bottom:none}
.v-uc ol.flow>li::before{content:counter(f); position:absolute; left:0; top:6px;
  font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--faint); width:24px; text-align:right}
.v-uc .ext{margin-bottom:22px}
.v-uc .ext-item{border-left:2.5px solid var(--rule); padding:2px 0 2px 15px; margin-bottom:14px}
.v-uc .ext-on{font-weight:600; font-size:14px}
.v-uc .ext-on .br{font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:var(--soft); margin-right:7px}
.v-uc .ext-item ul{margin:5px 0 0; padding-left:17px; color:var(--soft); font-size:14px}
.v-uc .note{background:var(--card); border-left:2.5px solid var(--rule); padding:11px 15px; margin-bottom:22px; font-size:13.5px; color:var(--soft)}
.v-uc .note p{margin:0}
/* 맨몸 UC-xx·대응표 칩 → 그 카드 */
.v-uc a.jump{color:inherit; text-decoration:none; cursor:pointer; border-bottom:1px dashed currentColor}
.v-uc a.chip{color:inherit; text-decoration:none}
.v-uc .chip{display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:11.5px;
  padding:1px 7px; margin:2px 3px 2px 0; border:1px solid var(--rule); background:var(--panel); cursor:pointer}
.v-uc .chip:hover{border-color:var(--ink)}
@media (prefers-reduced-motion:reduce){.v-uc *{transition:none!important}}
"""

# 패키지 그림 — frontend uc.ts mount를 그대로 옮긴 것(옛 build.py JS 대신, 카드 AM). 고치면 둘 다 고친다
UC_JS = r"""
(function(){
  const root=document.currentScript.parentElement;
  const DATA=JSON.parse(root.querySelector('#uc-data').textContent);
  const ucs=DATA.ucs;
  const svg=root.querySelector('#dg'), tabs=root.querySelector('#tabs');
  if(!svg||!tabs||!ucs.length)return;
  const HEX={agent:'#12776A',human:'#3A5BA0',github:'#6B4A9E',system:'#8A6D1F'};
  const ACT={};for(const k of ['agent','human','github','system'])ACT[k]={label:DATA.labels[k],hex:HEX[k]};
  const NS='http://www.w3.org/2000/svg', RX=94, RY=30;
  const el=(t,a={})=>{const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,String(a[k]));return n;};
  const parseIds=s=>(!s||s==='—')?[]:(s.match(/UC-[AHGS]\d+/g)||[]);
  const firstId=s=>{const m=/UC-[AHGS]\d+/.exec(s||'');return m?m[0]:undefined;};
  const edgePt=(cx,cy,tx,ty,ry)=>{if(ry===undefined)ry=RY;const a=Math.atan2((ty-cy)*RX,(tx-cx)*ry);return [cx+RX*Math.cos(a),cy+ry*Math.sin(a)];};
  const wrap=(text,max)=>{const lines=[];let cur='';for(const w of text.split(' ')){if((cur+' '+w).trim().length>max){if(cur.trim())lines.push(cur.trim());cur=w;}else cur+=' '+w;}if(cur.trim())lines.push(cur.trim());return lines.length?lines:[text];};
  const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  function buildDefs(){
    const defs=el('defs');
    const m=el('marker',{id:'open',viewBox:'0 0 10 10',refX:'9.5',refY:'5',markerWidth:'9',markerHeight:'9',orient:'auto-start-reverse'});
    m.appendChild(el('path',{d:'M0,0 L10,5 L0,10',fill:'none',stroke:'#5C6B73','stroke-width':'1.3'}));defs.appendChild(m);
    const g=el('marker',{id:'tri',viewBox:'0 0 12 12',refX:'11',refY:'6',markerWidth:'13',markerHeight:'13',orient:'auto-start-reverse'});
    g.appendChild(el('path',{d:'M0,0.5 L11,6 L0,11.5 Z',fill:'#fff',stroke:'#5C6B73','stroke-width':'1.2'}));defs.appendChild(g);
    return defs;
  }
  const UCMAP=Object.fromEntries(ucs.map(u=>[u.id,u]));
  const PKGS=[];for(const u of ucs)if(!PKGS.includes(u.package))PKGS.push(u.package);
  let curPkg=PKGS[0]||'', curId=null;
  function drawPackage(pkg){
    svg.innerHTML='';svg.appendChild(buildDefs());
    const list=ucs.filter(u=>u.package===pkg), inPkg=new Set(list.map(u=>u.id)), outside=[];
    list.forEach(u=>[...parseIds(u.include),...parseIds(u.extPoint)].forEach(id=>{if(!inPkg.has(id)&&!outside.includes(id))outside.push(id);}));
    const abstracts=[...new Set(list.map(u=>firstId(u.general)).filter(x=>!!x))];
    const actors=[...new Set(list.map(u=>u.actor))].filter(a=>a!=='system');
    const main=list.filter(u=>u.actor!=='system'), sub=list.filter(u=>u.actor==='system');
    const rowH=88, colMid=530, colRight=890, P={}, RYs={};
    const ryOf=u=>(u&&u.extPoint&&u.extPoint!=='—')?RY+16:RY;
    main.forEach((u,i)=>{P[u.id]={x:colMid,y:110+i*rowH};RYs[u.id]=ryOf(u);});
    const ry0=110+main.length*rowH;
    abstracts.forEach((id,i)=>{P[id]={x:colMid,y:ry0+i*rowH,abstract:true};RYs[id]=RY;});
    [...sub.map(u=>u.id),...outside].forEach((id,i)=>{P[id]={x:colRight,y:110+i*82,outside:!inPkg.has(id)};RYs[id]=ryOf(UCMAP[id]);});
    const maxY=Math.max(...Object.values(P).map(p=>p.y),260)+100, W=1150;
    svg.setAttribute('viewBox',`0 0 ${W} ${maxY}`);svg.setAttribute('style',`min-width:${W}px;height:${maxY}px`);
    svg.appendChild(el('rect',{x:300,y:56,width:790,height:maxY-100,fill:'none',stroke:'#1E2A30','stroke-width':'1.5'}));
    const title=el('text',{x:316,y:79,'font-size':'13.5','font-weight':'600',fill:'#1E2A30'});title.textContent=pkg;svg.appendChild(title);
    const anchors={};
    actors.forEach((k,i)=>{
      const a=ACT[k], x=155, y=150+i*(maxY>420?190:150), s={stroke:a.hex,'stroke-width':1.8,fill:'none'}, g=el('g');
      g.appendChild(el('circle',Object.assign({cx:x,cy:y,r:10},s,{fill:'#fff'})));
      g.appendChild(el('line',Object.assign({x1:x,y1:y+10,x2:x,y2:y+36},s)));
      g.appendChild(el('line',Object.assign({x1:x-16,y1:y+19,x2:x+16,y2:y+19},s)));
      g.appendChild(el('line',Object.assign({x1:x,y1:y+36,x2:x-13,y2:y+55},s)));
      g.appendChild(el('line',Object.assign({x1:x,y1:y+36,x2:x+13,y2:y+55},s)));
      const n=el('text',{x,y:y+74,class:'a-name',fill:a.hex});n.textContent=a.label;g.appendChild(n);
      svg.appendChild(g);anchors[k]={x,y:y+22};
    });
    main.forEach(u=>{const a=anchors[u.actor], p=P[u.id];if(!a)return;const [ex,ey]=edgePt(p.x,p.y,a.x,a.y,RYs[u.id]);
      svg.appendChild(el('line',{x1:a.x,y1:a.y,x2:ex,y2:ey,class:'assoc',stroke:ACT[u.actor].hex}));});
    const dep=(from,to,label)=>{const f=P[from], g=P[to];if(!f||!g)return;
      const [sx,sy]=edgePt(f.x,f.y,g.x,g.y,RYs[from]), [tx,ty]=edgePt(g.x,g.y,f.x,f.y,RYs[to]);
      svg.appendChild(el('line',{x1:sx,y1:sy,x2:tx,y2:ty,class:'dep',stroke:'#5C6B73','marker-end':'url(#open)'}));
      const l=el('text',{x:(sx+tx)/2,y:(sy+ty)/2-6,class:'stereo'});l.textContent=label;svg.appendChild(l);};
    list.forEach(u=>{parseIds(u.include).forEach(id=>dep(u.id,id,'«include»'));parseIds(u.extPoint).forEach(id=>dep(u.id,id,'«extend»'));
      const gi=firstId(u.general);
      if(gi&&P[gi]){const f=P[u.id], g=P[gi];const [sx,sy]=edgePt(f.x,f.y,g.x,g.y,RYs[u.id]), [tx,ty]=edgePt(g.x,g.y,f.x,f.y,RYs[gi]);
        svg.appendChild(el('line',{x1:sx,y1:sy,x2:tx,y2:ty,class:'gen',stroke:'#5C6B73','marker-end':'url(#tri)'}));}});
    Object.entries(P).forEach(([id,p])=>{
      const u=UCMAP[id], isAbs=!!p.abstract, isOut=!!p.outside, name=u?u.name:id, color=u?ACT[u.actor].hex:'#5C6B73';
      const xp=!!(u&&u.extPoint&&u.extPoint!=='—');
      const g=el('g',Object.assign({class:'uc'},u?{'data-uc':id,tabindex:'0',role:'button','aria-label':id+' '+name}:{}));
      g.appendChild(el('ellipse',Object.assign({cx:p.x,cy:p.y,rx:RX,ry:RYs[id],class:'uc-el'+(isAbs?' abstract':''),stroke:color},isOut?{'stroke-dasharray':'3 3'}:{})));
      const k=el('text',{x:p.x,y:p.y-(xp?18:13),class:'uc-k'});k.textContent=isAbs?'추상':id.replace('UC-','');g.appendChild(k);
      const lines=wrap(name,13);
      lines.forEach((ln,i)=>{const tn=el('text',{x:p.x,y:p.y+(xp?-1:5)+i*15-(lines.length-1)*7,class:'uc-t'});tn.textContent=ln;g.appendChild(tn);});
      if(xp&&u){const h=el('text',{x:p.x,y:p.y+24,class:'uc-xp-h'});h.textContent='Extension Points';g.appendChild(h);
        const c=el('text',{x:p.x,y:p.y+36,class:'uc-xp'});const mm=/`(.+?)`/.exec(u.extPoint);c.textContent=mm?mm[1]:'';g.appendChild(c);}
      svg.appendChild(g);
    });
    if(outside.length){const n=el('text',{x:colRight,y:maxY-46,class:'ext-only','text-anchor':'middle'});n.textContent='점선 타원은 다른 패키지의 유스케이스';svg.appendChild(n);}
    refreshSel();
  }
  PKGS.forEach((p,i)=>{const b=document.createElement('button');b.type='button';b.setAttribute('role','tab');b.dataset.pkg=p;
    b.setAttribute('aria-selected',String(i===0));b.innerHTML=esc(p||'(패키지 없음)')+`<span class="cnt">${ucs.filter(u=>u.package===p).length}</span>`;tabs.appendChild(b);});
  const setTab=p=>{curPkg=p;tabs.querySelectorAll('button').forEach(x=>x.setAttribute('aria-selected',String(x.dataset.pkg===p)));drawPackage(p);};
  function refreshSel(){svg.querySelectorAll('g.uc').forEach(g=>g.classList.toggle('sel',g.dataset.uc===curId));}
  function select(id,scroll){const u=UCMAP[id];if(!u)return;curId=id;if(u.package!==curPkg)setTab(u.package);else refreshSel();
    if(scroll){const c=root.querySelector('#item-'+id);if(c)c.scrollIntoView({block:'start'});}}
  root.addEventListener('click',e=>{const t=e.target;if(!(t instanceof Element))return;
    const b=t.closest('#tabs button[data-pkg]');if(b){setTab(b.dataset.pkg);return;}
    const g=t.closest('g.uc[data-uc]');if(g)select(g.dataset.uc,true);});
  root.addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==' ')return;const t=e.target;if(!(t instanceof Element))return;
    const g=t.closest('g.uc[data-uc]');if(g){e.preventDefault();select(g.dataset.uc,true);}});
  drawPackage(curPkg);
  const hm=/^#item-(UC-[AHGS]\d+)$/.exec(location.hash);if(hm&&UCMAP[hm[1]])select(hm[1],false);
})();
"""

# ───────────────────────── V-INFRA ─────────────────────────
def v_infra(doc):
    """제약 C 항목 → 카드(ID·제목·하위 N · 본문 전부 · 이 제약을 근거로 삼은 문서). 절 머리 그대로.
    마지막 제약 뒤 문단은 그 제약의 본문이다 — 특정 문장으로 꼬리를 알아보지 않는다(#120).
    구성도·시퀀스 mermaid 그대로. 나머지 원본 순서."""
    did = doc["fm"]["doc_id"]; out = []; dmap = downstream_of(did)
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("제약"):
            out.append(f"<h2>{esc(title)}</h2>" + item_cards(did, text, r"C\d+", "이 제약을 근거로 삼은 문서", dmap))
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"C\d+"))
    return "\n".join(out)

# ───────────────────────── 기존 생성기 흡수 (와이어프레임·시퀀스·MINISPEC) ─────────────────────────
def absorb(script, src, tmp):
    """기존 빌더를 돌려 결과 HTML에서 style·본문·script를 뽑아 공통 틀에 넣는다."""
    import subprocess
    subprocess.run(["python3", os.path.join(os.path.dirname(__file__), script), src, tmp], capture_output=True)
    h = open(tmp, encoding="utf-8").read()
    style = "".join(re.findall(r"<style>(.*?)</style>", h, re.S))
    # 본문: <div class="layout"> 또는 <div class="stabs"> 부터 <footer> 전까지
    m = re.search(r'(<div class="(?:stabs|layout)"[\s\S]*?)<footer>', h)
    body = m.group(1) if m else ""
    scripts = "".join(re.findall(r'<script(?: id="DATA" type="application/json")?>(?!window\.__mermaidReady)(.*?)</script>', h, re.S))
    data = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', h, re.S)
    js = re.findall(r'<script>\n?((?!window\.__mermaidReady)[\s\S]*?)</script>', h)
    js = [x for x in js if "JSON.parse" in x]
    out = f'<style>{style}</style>{body}'
    if data: out += f'<script id="DATA" type="application/json">{data.group(1)}</script>'
    for x in js: out += f"<script>{x}</script>"
    os.remove(tmp)
    return out

def v_ui(doc):
    """V-UI — 화면 문서는 하나여도 둘이어도 같은 렌더러(카드 X). 규칙은 wf_build.py에."""
    import wf_build as wf
    blocks = wf.parse_ui(doc["body"])
    sid = doc["fm"]["doc_id"]
    ui = wf.render_ui(blocks, sid, wf.common_block(doc["body"]), wf.base_for(sid))
    return f'<style>{wf.WF_CSS}</style><div class="uiview">{ui}<script>{wf.WF_JS}</script></div>'

def v_seq(doc):
    return absorb("seq_build.py", doc["path"], "/tmp/_seq.html")

def v_ms(doc):
    return absorb("ms_build.py", doc["path"], "/tmp/_ms.html")

# ───────────────────────── V-DOM ─────────────────────────
def v_dom(doc):
    did = doc["fm"]["doc_id"]; t = doc["fm"]["title"]
    if "도메인" in t:
        out = []
        for title, text in split_sections(doc["body"]):
            name = re.sub(r"^\d+\.\s*", "", title)
            if name.startswith("개념별"):
                lead = re.split(r"^#### ", text, flags=re.M)[0]
                cards = ""
                for cid, ct, _, cb in item_blocks(text, r"[A-Z][A-Za-z]+"):
                    cards += f'<article class="pcard" id="item-{cid}"><div class="card-h"><span class="iid">{cid}</span><b>{inline(ct, did)}</b></div>{render_blocks(cb, did)}</article>'
                out.append(f'<h2>{esc(title)}</h2>{render_blocks(lead, did)}<div class="pgrid dom">{cards}</div>'); continue
            out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"[A-Z][A-Za-z]+"))
        return "\n".join(out)
    if "클래스" in t:
        # 2장 엔티티: 묶음(### 2.x)마다 클래스 조각 mermaid를 하나로 합친다 (STD-002 V-DOM)
        out = []
        for title, text in split_sections(doc["body"]):
            name = re.sub(r"^\d+\.\s*", "", title)
            if name.startswith("엔티티"):
                out.append(f"<h2>{esc(title)}</h2>" + render_blocks(re.split(r"^### ", text, flags=re.M)[0], did))
                for grp in re.split(r"^### ", text, flags=re.M)[1:]:
                    gt, _, gb = grp.partition("\n")
                    classes = re.findall(r"```mermaid\nclassDiagram\n(.*?)\n```", gb, re.S)
                    rels = []
                    for cid, ct, _, cb in item_blocks(gb, r"[A-Z][A-Za-z]+"):
                        for l in re.findall(r"^- `(\w+)` ([^—]+) — ([^`]+) `(\w+)`(?: \((.+)\))?", cb, re.M):
                            a, ca, cb_, b, lab = l
                            rels.append(f'    {a} "{ca.strip()}" -- "{cb_.strip()}" {b}' + (f" : {lab}" if lab else ""))
                    if not classes:
                        out.append(f"<h3>{esc(gt)}</h3>" + render_blocks(gb, did, r"[A-Z][A-Za-z]+")); continue
                    merged = "classDiagram\n" + "\n".join(classes) + "\n" + "\n".join(sorted(set(rels)))
                    out.append(f'<h3>{esc(gt)}</h3><p class="soft">클래스 {len(classes)}개의 조각을 합친 묶음 다이어그램 — 뷰가 만든다(V-DOM). 원본은 클래스마다 따로.</p><div class="mer"><pre class="mermaid">{esc(merged)}</pre></div>')
                    # 각 클래스 항목: 헤딩 + 관계·테이블 링크 (조각 다이어그램은 합쳤으니 생략)
                    for cid, ct, _, cb in item_blocks(gb, r"[A-Z][A-Za-z]+"):
                        rest = re.sub(r"```mermaid\n.*?\n```\n?", "", cb, flags=re.S)
                        out.append(f'<div class="card" id="item-{cid}"><div class="card-h"><span class="iid">{cid}</span><b>{inline(ct, did)}</b></div>{render_blocks(rest, did)}</div>')
                continue
            out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"[A-Z][A-Za-z]+"))
        return "\n".join(out)
    # ERD·DD: 원본 순서 (ERD mermaid + 테이블 항목마다 DD 표)
    return render_blocks(doc["body"], did, r"[a-z][a-z0-9_]+")

# ───────────────────────── V-API ─────────────────────────
def v_api(doc):
    did = doc["fm"]["doc_id"]; t = doc["fm"]["title"]
    if "REST" in t:
        import yaml
        out = []; ops = []
        for title, text in split_sections(doc["body"]):
            name = re.sub(r"^\d+\.\s*", "", title)
            if name.startswith("엔드포인트"):
                out.append(f"<h2>{esc(title)}</h2>" + render_blocks(re.split(r"^### ", text, flags=re.M)[0], did))
                # 경로별 표로 재조립 + 각 항목은 접힘
                rows = ""; details = ""
                for grp in re.split(r"^### ", text, flags=re.M)[1:]:
                    gt, _, gb = grp.partition("\n")
                    rows += f'<tr class="grp"><td colspan="5">{esc(gt)}</td></tr>'
                    for eid, et, _, eb in item_blocks(gb, r"(GET|POST|PUT|PATCH|DELETE)/\S+"):
                        meth, path = eid.split("/", 1); path = "/" + path
                        meta = eb.strip().split("\n")[0] if not eb.strip().startswith("```") else ""
                        rows += f'<tr><td><span class="meth m-{meth.lower()}">{meth}</span></td><td class="mono"><a href="#item-{esc(eid)}">{esc(path)}</a></td><td>{inline(et, did)}</td><td class="small">{inline(meta, did)}</td></tr>'
                        y = re.search(r"```yaml\n(.*?)\n```", eb, re.S)
                        if y: ops.append(y.group(1))
                        details += f'<details class="ep" id="item-{esc(eid)}"><summary><span class="meth m-{meth.lower()}">{meth}</span> <span class="mono">{esc(path)}</span> — {inline(et, did)}</summary>{render_blocks(eb, did)}</details>'
                out.append(f'<table class="reassembled eps"><thead><tr><th></th><th>경로</th><th>요약</th><th>화면 · 유스케이스 · 서비스</th></tr></thead><tbody>{rows}</tbody></table><h3>엔드포인트 상세</h3>{details}')
                continue
            if name.startswith("스키마"):
                y = re.search(r"```yaml\n(.*?)\n```", text, re.S)
                merged = ""
                try:
                    base = yaml.safe_load(y.group(1)) if y else {}
                    paths = {}
                    for o in ops:
                        d = yaml.safe_load(o)
                        for pth, v in d.items(): paths.setdefault(pth, {}).update(v)
                    base["paths"] = paths
                    merged = yaml.safe_dump(base, allow_unicode=True, sort_keys=False, width=120)
                except Exception as e: merged = f"# 합치기 실패: {e}"
                out.append(f'<h2>{esc(title)}</h2>' + render_blocks(re.split(r"```", text)[0], did) +
                           f'<details class="ep"><summary>공통 스키마 (components) 펼치기</summary>{render_blocks(text, did)}</details>'
                           f'<h3>OpenAPI 전체 — 뷰가 조각 {len(ops)}개를 합쳤다</h3><p class="soft">원본은 엔드포인트마다 조각. 이건 뷰가 만든 것(V-API). 그대로 저장하면 Swagger에 넣을 수 있다.</p><details class="ep"><summary>openapi.yaml 펼치기</summary><pre class="code"><code>{esc(merged)}</code></pre></details>')
                continue
            out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did))
        return "\n".join(out)
    # MCP: 도구 카드 (inputSchema를 표로)
    out = []
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("도구 정의"):
            out.append(f"<h2>{esc(title)}</h2>")
            for tid, tt, _, tb in item_blocks(text, r"[a-z][a-z_]+"):
                j = re.search(r"```json\n(\{\s*\"name\".*?)\n```", tb, re.S)
                schema_tbl = ""
                if j:
                    try:
                        d = json.loads(j.group(1)); props = d["inputSchema"].get("properties", {}); req = set(d["inputSchema"].get("required", []))
                        schema_tbl = f'<p class="desc">{esc(d["description"])}</p><table class="schema"><thead><tr><th>인자</th><th>타입</th><th>필수</th><th>설명</th></tr></thead><tbody>' + "".join(f'<tr><td class="mono">{esc(k)}</td><td class="mono">{esc(v.get("type","") + ("["+v["items"]["type"]+"]" if v.get("type")=="array" and "items" in v else "") + (" "+"|".join(v["enum"]) if "enum" in v else ""))}</td><td>{"○" if k in req else ""}</td><td>{esc(v.get("description",""))}</td></tr>' for k, v in props.items()) + "</tbody></table>"
                    except Exception: schema_tbl = ""
                rest = re.sub(r"```json\n\{\s*\"name\".*?\n```\n?", "", tb, count=1, flags=re.S)
                out.append(f'<article class="card" id="item-{tid}"><div class="card-h"><span class="iid">{tid}</span><b>{inline(tt, did)}</b></div>{schema_tbl}{render_blocks(rest, did)}</article>')
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"[a-z][a-z_]+"))
    return "\n".join(out)

def v_std(doc): return render_blocks(doc["body"], doc["fm"]["doc_id"], r"[A-Z]+-\d+|V-[A-Z]+")

# ───────────────────────── 기본(원본 순서) ─────────────────────────
def v_plain(doc, pat):
    return render_blocks(doc["body"], doc["fm"]["doc_id"], pat)

VIEWS = {"PRD": v_prd, "RFQ": v_rfq, "SCN": v_scn, "UC": v_uc, "INFRA": v_infra, "DOM": v_dom, "UI": v_ui, "API": v_api, "SEQ": v_seq, "MS": v_ms, "STD": v_std}
ITEM_PAT = {"RFQ": r"Q\d+", "PRD": r"G\d+|R\d+|N\d+", "SCN": r"P\d+|S\d+", "UC": r"UC-[AHGS]\d+", "INFRA": r"C\d+",
            "DOM": r"[A-Za-z][A-Za-z0-9_]+", "UI": r"UI-\d+", "API": r"(GET|POST|PUT|PATCH|DELETE)/\S+|[a-z][a-z_]+",
            "SEQ": r"SEQ-\d+|SEQ-C\d+", "MS": r"[A-Za-z_]+\.[a-z_]+", "STD": r"[A-Z]+-\d+|V-[A-Z]+"}

CSS = r"""
:root{--paper:#EDEFEC;--panel:#F8F9F7;--card:#fff;--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--hi:#FFF1B8;--blue:#1a5fb4}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;font-size:14.5px;line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:1200px;margin:0 auto;padding:28px 22px 80px}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em;background:#E4E8E4;padding:1px 5px;border-radius:2px}
pre.code{background:#1E2A30;color:#E8ECE8;padding:12px 14px;font:12.5px/1.55 ui-monospace,Menlo,monospace;overflow-x:auto;margin:8px 0 16px;border-radius:2px}pre.code code{background:none;color:inherit;padding:0;font-size:inherit}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:.92em}
.tb{border:1.5px solid var(--ink);background:var(--panel);display:grid;grid-template-columns:1fr auto}
.tb-main{padding:20px 26px;border-right:1.5px solid var(--ink)}.tb-kicker{font-size:12px;color:var(--soft);margin-bottom:6px}.tb-kicker a{color:var(--soft);text-decoration:none}
.tb h1{margin:0;font-size:25px;font-weight:700;letter-spacing:-.02em}.tb p{margin:8px 0 0;color:var(--soft);font-size:13.5px;max-width:66ch}
.tb-meta{display:grid;grid-template-columns:auto minmax(200px,340px);align-content:start;font-size:12px}
.tb-meta div{padding:8px 14px;border-bottom:1px solid var(--hair)}.tb-meta div:nth-child(odd){color:var(--soft);border-right:1px solid var(--hair);white-space:nowrap}.tb-meta div:nth-last-child(-n+2){border-bottom:none}
.st{display:inline-block;padding:1px 8px;border-radius:2px;font-size:11.5px;font-weight:600}.st-draft{background:#e8e8e8;color:#555}.st-review{background:#fff0b3;color:#960}.st-approved{background:#d6f0d6;color:#1a6}
.body{border:1.5px solid var(--ink);border-top:none;background:var(--card);padding:26px 34px}
.body h2{font-size:19px;margin:30px 0 12px;padding-bottom:8px;border-bottom:1.5px solid var(--ink);letter-spacing:-.01em}.body h2:first-child{margin-top:0}
.body h3{font-size:15.5px;margin:22px 0 8px}.body h4{font-size:14px;margin:18px 0 6px}
.body h1{display:none}
h2.item,h3.item,h4.item,h5.item{display:flex;align-items:center;gap:10px}
.iid{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;font-weight:600;background:#FFE58A;border:1px solid #C9A800;padding:1px 7px;border-radius:2px;white-space:nowrap}
a.ref{font-family:ui-monospace,Menlo,monospace;font-size:.88em;color:var(--blue);text-decoration:none;border-bottom:1px dashed var(--blue)}a.ref.missing{color:#999;border-bottom-color:#bbb}a.ref.missing::after{content:" ?"}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 16px;background:#fff}th{text-align:left;font-weight:600;color:var(--soft);padding:7px 9px;border-bottom:1.5px solid var(--ink);background:var(--panel)}td{padding:7px 9px;border-bottom:1px solid var(--hair);vertical-align:top}
table.reassembled td.iid,table.trace td:first-child{white-space:nowrap}td.num{text-align:right;color:var(--soft);font-family:ui-monospace,Menlo,monospace}
.card{border:1px solid var(--rule);background:var(--panel);padding:14px 18px;margin:14px 0}
.card-h{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:15px}.card-h b{flex:1}
.pill{font-size:11px;padding:1px 8px;border:1px solid var(--ink);border-radius:10px;white-space:nowrap}.pill.soft{border-color:var(--rule);color:var(--soft)}
ul.ac{list-style:none;padding:0;margin:8px 0 0}ul.ac li{display:flex;gap:8px;align-items:flex-start;margin:4px 0;font-size:13.5px}ul.ac .box{display:inline-block;width:16px;height:16px;border:1.5px solid var(--ink);border-radius:2px;font-size:11px;line-height:13px;text-align:center;flex:none;margin-top:4px;background:#fff}ul.ac li.done{color:var(--soft)}
.pgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:10px 0 20px}.pcard{border:1px solid var(--rule);background:var(--panel);padding:14px 16px}.pcard ul{margin:4px 0}
.scard{border:1px solid var(--rule);background:#fff;padding:16px 20px;margin:14px 0}.scard ol.steps{counter-reset:s;list-style:none;padding:0;margin:10px 0}.scard ol.steps>li{counter-increment:s;position:relative;padding:6px 0 6px 38px;border-left:2px solid var(--rule);margin-left:12px}.scard ol.steps>li::before{content:counter(s);position:absolute;left:-13px;top:6px;width:24px;height:24px;border-radius:50%;background:var(--ink);color:#fff;font-size:11.5px;text-align:center;line-height:24px;font-weight:600}
.variant{margin:8px 0;border:1px dashed var(--rule);padding:6px 12px;background:var(--panel)}.variant summary{cursor:pointer;font-weight:600;font-size:13px}.variant p{margin:6px 0 2px;font-size:13.5px}.variant ul,.variant ol{font-size:13.5px}
.pgrid.dom{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.meth{display:inline-block;font:600 10.5px ui-monospace,monospace;padding:1px 6px;border-radius:2px;color:#fff;background:#666}.m-get{background:#2b7a4b}.m-post{background:#2a5db0}.m-delete{background:#b03030}.m-put,.m-patch{background:#a06a00}
table.eps tr.grp td{background:var(--panel);font-weight:600;color:var(--soft)}td.small{font-size:12px;color:var(--soft)}
details.ep{border:1px solid var(--rule);margin:8px 0;background:#fff}details.ep summary{cursor:pointer;padding:8px 12px;font-size:13.5px}details.ep>*:not(summary){padding:0 14px 8px}
.desc{color:var(--soft);font-size:13.5px}table.schema{font-size:12.5px}
.down{margin-top:10px;padding-top:8px;border-top:1px dashed var(--rule);font-size:12.5px;color:var(--soft)}
.etc{margin-top:10px;padding-top:8px;border-top:1px dashed var(--rule)}.etc-t{font-size:12px;font-weight:600;color:var(--soft)}
ul,ol{margin:6px 0 12px;padding-left:22px}li{margin:3px 0}blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--ink);background:var(--panel);color:var(--soft)}
hr{border:none;border-top:1px solid var(--hair);margin:22px 0}
.soft{color:var(--soft)}.warn{color:#b00;font-size:13px;border:1px solid #b00;padding:6px 10px;background:#fff5f5}.mer{background:#fff;border:1px solid var(--rule);padding:10px;margin:8px 0 16px;overflow-x:auto}pre.mermaid{margin:0;font:12px ui-monospace,monospace;white-space:pre-wrap}pre.mermaid.nomer::before{content:"mermaid.js를 불러오지 못해 코드로 표시";display:block;color:#b00;margin-bottom:6px}
.wfbox{margin:8px 0}
footer{margin-top:20px;font-size:12.5px;color:var(--soft)}
.tabs{display:flex;border:1.5px solid var(--ink);border-top:none;background:var(--panel)}.tabs button{font:inherit;font-size:13px;padding:9px 16px;background:none;border:none;border-right:1px solid var(--rule);cursor:pointer;color:var(--soft)}.tabs button.on{background:#fff;color:var(--ink);font-weight:600}
@media (max-width:860px){.tb{grid-template-columns:1fr}.tb-main{border-right:none;border-bottom:1.5px solid var(--ink)}.body{padding:18px}}
"""

def build(src):
    """문서 하나 → OUT_DIR/view_{ID}.html. 색인에 없는 문서면 안내 한 줄과 1 (전에는 KeyError, #126)"""
    raw = open(src, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in m.group(1).split("\n"))} if m else {}
    doc = ALL.get(fm.get("doc_id", ""))
    if doc is None:
        print(f"모르는 문서 {fm.get('doc_id') or os.path.basename(src)} — 그 문서가 있는 docs/specs를 --specs로 준다 (지금 뿌리: {SRC_DIR})")
        return 1
    typ = fm["type"]
    fn = VIEWS.get(typ)
    body_html = fn(doc) if fn else v_plain(doc, ITEM_PAT.get(typ, r"\S+"))
    out = shell(doc, body_html)
    path = os.path.join(OUT_DIR, view_href(fm["doc_id"]))
    open(path, "w", encoding="utf-8").write(out)
    print(f"{fm['doc_id']} ({typ}, {'V-'+typ if fn else '원본 순서'}) → {os.path.basename(path)}")
    return 0

def build_index():
    order = ["RFQ","PRD","SCN","UC","INFRA","DOM","UI","API","SEQ","MS","CODE","STD"]
    rows = ""
    for typ in order:
        ds = sorted((d for d in ALL.values() if d["fm"]["type"] == typ), key=lambda d: d["fm"]["doc_id"])
        for d in ds:
            fm = d["fm"]; st = STAGE.get(typ)
            rows += f'<tr><td class="num">{st or "—"}</td><td class="mono"><a href="{view_href(fm["doc_id"])}">{fm["doc_id"]}</a></td><td>{esc(fm["title"])}</td><td><span class="st st-{fm["status"]}">{STATUS_KO[fm["status"]]}</span></td><td class="num">{len(d["items"])}</td></tr>'
    html_ = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>싱크독 — 문서</title><style>{CSS}</style></head><body><div class="wrap">
<header class="tb"><div class="tb-main"><div class="tb-kicker">싱크독 · {CODE}</div><h1>명세 체인 — 문서 {len(ALL)}개</h1><p>11단계 + 단계 밖 STD. 클릭하면 사람용 뷰. 이 목록이 웹 UI-4 프로젝트 상세의 정적 판이다.</p></div>
<div class="tb-meta"><div>프로젝트</div><div class="mono">{CODE}</div><div>항목</div><div>{sum(len(d["items"]) for d in ALL.values())}개</div><div>참조</div><div>{sum(len(d["refs"]) for d in ALL.values())}개</div></div></header>
<main class="body"><table><thead><tr><th>단계</th><th>문서</th><th>제목</th><th>상태</th><th>항목</th></tr></thead><tbody>{rows}</tbody></table></main>
<footer>생성: _tools/view_build.py</footer></div></body></html>"""
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(html_)
    print("index.html")

_SELF_PRD = """---
doc_id: T-PRD-001
type: PRD
title: 시험 PRD
status: draft
upstream: []
---

# 시험 PRD

## 1. 목표

목표 절 머리 문장.

#### G1 첫 목표

G1 본문 문장. 근거: [[T-PRD-001#R1]]

#### G2 제목뿐인 목표

## 2. 비목표

없음.

## 3. 요구사항

요구사항 절 머리 문장.

### 3.1 기능

소절 머리 문장.

#### R1 첫 기능

R1 설명.

- [ ] 인수기준 하나

### 3.2 비워 둔 소절

## 4. 성공지표

없음.
"""
_SELF_INFRA = """---
doc_id: T-INFRA-001
type: INFRA
title: 시험 INFRA
status: draft
upstream: [T-PRD-001]
---

# 시험 INFRA

## 1. 제약

제약 절 머리 문장.

#### C1 첫 제약

출처: [[T-PRD-001#G1]]

C1 설명 문장.

#### C2 마지막 제약

출처: RFQ

C2 뒤 문단.

## 2. 구성도

없음.
"""

def _selftest():
    """V-PRD·V-INFRA가 원본 문장을 버리지 않는지 (#120). 앱 포트(views.ts)는 대조하지 않는다(#153).

    사용: view_build.py --selftest
    """
    saved = dict(ALL)
    for raw, name in ((_SELF_PRD, "T-PRD-001.md"), (_SELF_INFRA, "T-INFRA-001.md")):
        d = parse_doc(raw, name); ALL[d["fm"]["doc_id"]] = d
    try: p, i = v_prd(ALL["T-PRD-001"]), v_infra(ALL["T-INFRA-001"])
    finally: ALL.clear(); ALL.update(saved)
    c2 = i.find('id="item-C2"')
    cases = [
        ("목표 절 머리", "목표 절 머리 문장" in p),
        ("G 본문", "G1 본문 문장" in p),
        ("G 카드·앵커(본문 없는 G도)", 'class="card" id="item-G1"' in p and 'class="card" id="item-G2"' in p),
        ("G 하위·바닥 줄", "이 목표를 근거로 삼은 문서" in p and 'href="view_T-INFRA-001.html"' in p),
        ("요구사항 절 머리", "요구사항 절 머리 문장" in p),
        ("소절 제목·소절 머리", "3.1 기능</h3>" in p and "소절 머리 문장" in p and "3.2 비워 둔 소절</h3>" in p),
        ("빈 소제목 없음", "<h3></h3>" not in p),
        ("R 카드 그대로", 'id="item-R1"' in p and "인수기준 0/1" in p and "R1 설명." in p),
        ("제약 절 머리", "제약 절 머리 문장" in i),
        ("C 본문·출처 줄", "C1 설명 문장" in i and "출처: " in i and 'class="card" id="item-C1"' in i),
        ("마지막 제약 뒤 문단은 그 카드 안", 0 <= c2 < i.find("C2 뒤 문단") < i.find("</article>", c2)),
        ("목표·제약을 표로 모으지 않음", 'class="reassembled"' not in p + i),
    ]
    bad = [name for name, ok in cases if not ok]
    for name in bad:
        print("✗ ", name)
    print("V-PRD·V-INFRA: 통과" if not bad else f"V-PRD·V-INFRA: {len(bad)} 실패")
    return 0 if not bad else 1

_SELF_SCN = """---
doc_id: T-SCN-001
type: SCN
title: 시험 시나리오
status: draft
upstream: []
---

# 시험 시나리오

## 1. 페르소나

페르소나 절 머리 문장.

### P1 첫 사람

- 역할 문장.

## 2. 시나리오

시나리오 절 머리 문장.

#### S1 첫 시나리오

**주체**: [[#P1]]
**상황**: 상황 문장.

1. 첫 단계
2. 둘째 단계 첫 줄
   - 둘째 단계 밑 목록
3. 셋째 단계
이어 쓴 줄.

흐름 뒤 문단.

**참고**: 모르는 굵은 머리.

**변형 — 여러 줄**: 변형 첫 줄.

변형 둘째 문단.

1. 변형 안 번호 줄

**변형 — 한 줄**: 한 줄 변형.

**성공 조건**: 성공 문장.
**연관 요구사항**: 연관 문장.

### 2.1 둘째 묶음

소절 머리 문장.

#### S2 코드블록

1. 코드를 넣는다

```text
1. 코드블록 안 번호 줄
```

#### S3 구분선뿐

1. 한 단계

---

## 3. 대응표

없음.
"""

def _selftest_scn():
    """V-SCN이 원본 문장을 버리지 않고 절을 두 번 그리지 않는지 (#152). 앱 포트(views.ts)는 대조하지 않는다(#153)"""
    saved = dict(ALL)
    d = parse_doc(_SELF_SCN, "T-SCN-001.md"); ALL[d["fm"]["doc_id"]] = d
    try: h = v_scn(d)
    finally: ALL.clear(); ALL.update(saved)
    card = {m.group(1): m.group(0) for m in re.finditer(r'<article class="scard" id="item-(S\d+)">.*?</article>', h, re.S)}
    s1, s2, s3 = card.get("S1", ""), card.get("S2", ""), card.get("S3", "")
    steps = s1[s1.find('<ol class="steps">'):s1.find("</ol>")]
    many = s1[s1.find("<summary>변형 — 여러 줄</summary>"):]
    many = many[:many.find("</details>")]
    etc = s1.find('class="etc"')
    cases = [
        ("페르소나 절 머리", "페르소나 절 머리 문장" in h),
        ("P가 ###여도 페르소나 절은 한 번", h.count("역할 문장") == 1 and 'class="pcard" id="item-P1"' in h),
        ("S가 ####여도 시나리오 절은 한 번", h.count("상황 문장") == 1 and h.count("흐름 뒤 문단") == 1),
        ("절 머리·소절 제목·소절 머리", "시나리오 절 머리 문장" in h and "2.1 둘째 묶음</h3>" in h and "소절 머리 문장" in h),
        ("단계 밑 목록은 그 단계 안", '<li>둘째 단계 첫 줄<ul><li style="margin-left:0px">둘째 단계 밑 목록</li></ul></li>' in steps),
        ("빈 줄 없이 이어 쓴 줄은 그 단계", "<li>셋째 단계 이어 쓴 줄.</li>" in steps),
        ("필은 주 흐름만 센다", '<span class="pill soft">3단계</span>' in s1),
        ("흐름 뒤 문단·모르는 굵은 머리는 끝의 그 밖", 0 <= s1.rfind("</details>") < etc < s1.find("흐름 뒤 문단") and "모르는 굵은 머리" in s1[etc:]),
        ("그 밖 머리", '<div class="etc-t">그 밖</div>' in s1),
        ("여러 줄 변형은 접힌 칸 안", "변형 첫 줄." in many and "변형 둘째 문단." in many and "<li>변형 안 번호 줄</li>" in many),
        ("한 줄 변형은 전과 같은 HTML", '<details class="variant"><summary>변형 — 한 줄</summary><p>한 줄 변형.</p></details>' in s1),
        ("성공 조건·연관은 변형 뒤 그 밖 앞", s1.rfind("</details>") < s1.find("성공 문장") < s1.find("연관 문장") < etc),
        ("코드블록 안 번호 줄은 단계가 아니다", '<span class="pill soft">1단계</span>' in s2 and "<code>1. 코드블록 안 번호 줄</code>" in s2),
        ("구분선뿐이면 그 밖을 그리지 않음", 'class="etc"' not in s3 and "<hr>" not in s3),
    ]
    bad = [name for name, ok in cases if not ok]
    for name in bad:
        print("✗ ", name)
    print("V-SCN: 통과" if not bad else f"V-SCN: {len(bad)} 실패")
    return 0 if not bad else 1

_SELF_UI = """---
doc_id: T-UI-001
type: UI
title: 시험 화면 설계·와이어프레임
status: draft
upstream: []
---

# 시험 화면

## 1. 화면 목록

목록 절 머리 문장.

#### UI-1 설계만 있는 화면

페이지. 첫 문단 문장.

- **진입** 목록 한 줄
- **이탈** 목록 둘째 줄

| 상태 | 모습 |
|---|---|
| 기본 | 빈 목록 칸 |

#### UI-2 둘째 설계 화면

둘째 화면 문장.

마지막 설계 화면 뒤 문단.

## UI-3 배치 있는 화면

| 항목 | 내용 |
|---|---|
| 경로 | `/x` |

머리 설명 문장.

### 배치

배치 앞 글.

```html
<div class="box" data-el="1">상자</div>
```

배치 뒤 글.

### 요소

| # | 이름 | 보여주는 것 | 누르면 |
|---|---|---|---|
| 1 | 상자 | 상자 설명 | — |
| 2 | 칸 모자란 행 |

요소 표 뒤 문단.

### 규칙

- 첫 규칙 (1)
  이어 쓴 둘째 줄 (2)
  - 규칙 밑 목록
- 둘째 규칙

규칙 뒤 문단.

### 시나리오

**S-1 첫 시나리오** . [[#UI-1]]
1. 첫 단계 (1)
   단계 둘째 줄
2. 둘째 단계

시나리오 뒤 문단.

### 예외 상태

모르는 소절 문장.

```html
<div class="box">둘째 배치</div>
```

---

## UI-4 구분선만 남는 화면

```html
<div>넷째 배치</div>
```

---

## 3. 공통 틀

모든 화면 앞에 들어가는 틀.

```html
<style>.box{border:1px solid red}</style>
```

## 4. 미결사항

- [ ] 없음
"""
_SELF_UI_REF = """---
doc_id: T-API-001
type: API
title: 시험 참조
status: draft
upstream: []
---

# 시험 참조

근거 [[T-UI-001#UI-1]]
"""

def _selftest_ui():
    """V-UI가 원본 문장을 버리지 않는지 (#152). 앱 포트(wireframe.ts)는 대조하지 않는다(#153)"""
    saved = dict(ALL)
    for raw, name in ((_SELF_UI, "T-UI-001.md"), (_SELF_UI_REF, "T-API-001.md")):
        d = parse_doc(raw, name); ALL[d["fm"]["doc_id"]] = d
    try: h = v_ui(ALL["T-UI-001"])
    finally: ALL.clear(); ALL.update(saved)
    card = {m.group(1): m.group(0) for m in re.finditer(r'<article class="card" id="item-(UI-\d+)">.*?</article>', h, re.S)}
    scr = {m.group(1): m.group(0) for m in re.finditer(r'<section class="screen" id="item-(UI-\d+)".*?</section>', h, re.S)}
    c1, c2, s3, s4 = card.get("UI-1", ""), card.get("UI-2", ""), scr.get("UI-3", ""), scr.get("UI-4", "")
    etc = s3[s3.find('class="etc"'):] if 'class="etc"' in s3 else ""
    rules = s3[s3.find('<ul class="rules">'):s3.find("</ul></div>", s3.find('<ul class="rules">'))]
    order = ["배치 앞 글", "배치 뒤 글", "요소 표 뒤 문단", "규칙 뒤 문단", "시나리오 뒤 문단", "예외 상태", "모르는 소절 문장", "둘째 배치"]
    at = [etc.find(x) for x in order]
    frames = re.findall(r'srcdoc="([^"]*)"', etc)
    cases = [
        ("설계 화면은 카드(표 없음)", c1 != "" and c2 != "" and 'class="reassembled"' not in h),
        ("설계 카드 몸 전부", all(x in c1 for x in ("첫 문단 문장", "목록 한 줄", "목록 둘째 줄", "빈 목록 칸"))),
        ("마지막 설계 화면 뒤 문단은 그 카드", "마지막 설계 화면 뒤 문단" in c2),
        ("하위 N과 바닥 줄", "하위 1" in c1 and "이 화면을 근거로 삼은 문서" in c1 and 'href="view_T-API-001.html"' in c1),
        ("메타·머리 설명", "<b>경로</b>" in s3 and '<div class="s-desc"><p>머리 설명 문장.</p></div>' in s3),
        ("요소 표는 문서 머리·칸 그대로", "<th>보여주는 것</th>" in s3 and "<th>종류</th>" not in s3 and "칸 모자란 행" in s3 and 'class="kind"' not in s3),
        ("규칙 이어진 줄·밑 목록·칩", "이어 쓴 둘째 줄" in rules and "규칙 밑 목록</li></ul>" in rules and 'data-ref="2"' in rules),
        ("시나리오 머리 뒤는 유스케이스 자리", '<span class="uc">— <a class="ref" href="view_T-UI-001.html#item-UI-1">#UI-1</a></span>' in s3),
        ("시나리오 단계 둘째 줄", "첫 단계 (<span" in s3 and "단계 둘째 줄" in s3),
        ("그 밖은 원본 순서", all(x >= 0 for x in at) and at == sorted(at)),
        ("둘째 html은 공통 틀과 함께", len(frames) == 1 and ".box{border:1px solid red}" in html.unescape(frames[0]) and "둘째 배치" in html.unescape(frames[0])),
        ("구분선만 남은 화면은 그 밖 없음", s4 != "" and 'class="etc"' not in s4 and "<hr>" not in s4),
    ]
    bad = [name for name, ok in cases if not ok]
    for name in bad:
        print("✗ ", name)
    print("V-UI: 통과" if not bad else f"V-UI: {len(bad)} 실패")
    return 0 if not bad else 1

_SELF_UC = """---
doc_id: T-UC-001
type: UC
title: 시험 유스케이스
status: draft
upstream: []
---

# 시험 유스케이스

## 0. 이 문서의 형식

형식 문장.

## 1. 액터

| 코드 | 액터 |
|---|---|
| H | 운영자 |

## 2. 사용자 목표 수준 유스케이스

### 2.1 첫 묶음

묶음 머리 문장.

#### UC-H1 첫 유스케이스

| 항목 | 내용 |
|---|---|
| 범위 | 시험 범위 |
| 수준 | 사용자 목표 |
| 주 액터 | 운영자<br>둘째 줄 |
| 패키지 | 첫 패키지 |
| 포함 | [[#UC-S1]] |
| 확장점 | `조건` → [[#UC-H2]] |
| 새 행 | 모르는 행 값 |

표 뒤 문단.

**기본 흐름 — 넣기**
1. 첫 단계 UC-S1을 부른다
   단계 둘째 줄
2. 둘째 단계

**기본 흐름 — 빼기**
1. 빼는 단계

**확장**
- **1a. 첫 확장** — 머리 뒤 설명
  - 1a1. 확장 단계
- **2a. 둘째 확장**
  - 2a1. 둘째 확장 단계

**사후조건 참고**: 사후 첫 줄
사후 둘째 줄

**연관**: 연관 문장

**왜 있나.** 모르는 굵은 머리 문단.

#### UC-H2 둘째 유스케이스

**주 액터** 운영자 · **선행** 없음
1. 표 없는 흐름 단계

## 3. 하위기능 수준 유스케이스

#### UC-S1 하위 기능

| 항목 | 내용 |
|---|---|
| 패키지 | 첫 패키지 |

---

## 4. 대응표

| 시나리오 | 유스케이스 | 비고 |
|---|---|---|
| S1 시나리오 | H1, S1 | S1 글자 |

## 5. 미결사항

- [ ] 없음
"""

def _selftest_uc():
    """V-UC가 원본 문장을 버리지 않는지 — 원본 순서·카드·대응표 칩 (#152). 앱 포트(uc.ts)는 대조하지 않는다(#153)"""
    saved = dict(ALL)
    d = parse_doc(_SELF_UC, "T-UC-001.md"); ALL[d["fm"]["doc_id"]] = d
    try: h = v_uc(d)
    finally: ALL.clear(); ALL.update(saved)
    card = {m.group(1): m.group(0) for m in re.finditer(r'<article class="card" id="item-(UC-[AHGS]\d+)">.*?</article>', h, re.S)}
    h1, h2_, s1 = card.get("UC-H1", ""), card.get("UC-H2", ""), card.get("UC-S1", "")
    rows = re.findall(r"<tr(?: class=\"rel\")?><th>(.*?)</th>", h1)
    rel = re.findall(r'<tr class="rel"><th>(.*?)</th>', h1)
    data = json.loads(re.search(r'<script type="application/json" id="uc-data">(.*?)</script>', h, re.S).group(1).replace("<\\/", "</"))
    node = next((u for u in data["ucs"] if u["id"] == "UC-H1"), {})
    matrix = h[h.find("4. 대응표"):h.find("5. 미결사항")]
    at = [h1.find(x) for x in ("기본 흐름 — 넣기", "기본 흐름 — 빼기", "첫 확장", "사후 첫 줄", "연관 문장", 'class="etc"')]
    cases = [
        ("항목 밖 문장이 제자리", all(x in h for x in ("형식 문장", "2.1 첫 묶음</h3>", "묶음 머리 문장", "5. 미결사항</h2>"))
         and h.find("형식 문장") < h.find("묶음 머리 문장") < h.find('id="item-UC-H1"')),
        ("유스케이스는 카드", h1 != "" and h2_ != "" and s1 != ""),
        ("표 칸 <br>은 줄바꿈", "운영자<br>둘째 줄" in h1),
        ("원문 표 순서·모르는 행·머리 행 없음", rows == ["범위", "수준", "주 액터", "패키지", "포함", "확장점", "새 행"] and "모르는 행 값" in h1),
        ("규약 이름도 관계 행과 그림", rel == ["패키지", "포함", "확장점"] and "UC-S1" in node.get("include", "") and "UC-H2" in node.get("extPoint", "")),
        ("기본 흐름 둘과 단계 둘째 줄", "기본 흐름 — 빼기" in h1 and "단계 둘째 줄" in h1 and "빼는 단계" in h1),
        ("확장 머리 뒤 글·번호 글자", "머리 뒤 설명" in h1 and "1a1. 확장 단계" in h1 and '<span class="br">2a</span>' in h1),
        ("사후조건 둘째 줄", "사후 둘째 줄" in h1),
        ("조각은 문서 순서", all(x >= 0 for x in at) and at == sorted(at)),
        ("그 밖 — 표 뒤 문단·모르는 굵은 머리", h1.find('class="etc"') < h1.find("표 뒤 문단") and "왜 있나." in h1[h1.find('class="etc"'):]),
        ("표 없는 항목은 본문 그대로(그 밖 머리 없이)", "선행" in h2_ and "표 없는 흐름 단계" in h2_ and 'class="etc"' not in h2_),
        ("맨몸 UC-S1은 그 카드로", '<a class="jump" href="view_T-UC-001.html#item-UC-S1">UC-S1</a>' in h1),
        ("칩은 「유스케이스」 열만", '>H1</a>' in matrix and '>S1</a>' in matrix and "<td>S1 시나리오</td>" in matrix and "<td>S1 글자</td>" in matrix),
        ("구분선뿐인 카드는 그 밖 없음", 'class="etc"' not in s1 and "<hr>" not in s1),
        ("옛 싱크독 데이터가 안 나온다", "UC-A1" not in h and data["labels"]["human"] == "운영자"),
    ]
    bad = [name for name, ok in cases if not ok]
    for name in bad:
        print("✗ ", name)
    print("V-UC: 통과" if not bad else f"V-UC: {len(bad)} 실패")
    return 0 if not bad else 1

_ROOT_PRD = """---
doc_id: TX-PRD-001
type: PRD
title: 다른 저장소 PRD
status: draft
upstream: []
---

# 다른 저장소 PRD

## 1. 목표

#### G1 첫 목표
"""
_ROOT_UI = """---
doc_id: TX-UI-001
type: UI
title: 화면 설계 — 다른 저장소
status: draft
upstream: [TX-PRD-001]
---

# 화면 설계

## UI-1 첫 화면

```html
<div data-el="1"><img src="../assets/a.png">상자</div>
```

### 요소

| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | 상자 | 영역 | 근거 [[TX-PRD-001#G1]] | — |
"""

def _selftest_root():
    """다른 저장소의 docs/specs를 색인하는지 (#126). 임시 폴더에 문서 둘 — 전역은 끝나면 되돌린다"""
    global SRC_DIR, OUT_DIR, CODE
    import io, tempfile, contextlib, wf_build as wf
    saved = (SRC_DIR, OUT_DIR, CODE, dict(ALL), wf.SPECS_BASE)
    cases = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            specs = os.path.join(tmp, "docs", "specs")
            for sub, name, raw in (("02-PRD", "TX-PRD-001.md", _ROOT_PRD), ("07-UI", "TX-UI-001.md", _ROOT_UI)):
                os.makedirs(os.path.join(specs, sub))
                open(os.path.join(specs, sub, name), "w", encoding="utf-8").write(raw)
            out = os.path.join(tmp, "views")
            use_root(specs, out)
            with contextlib.redirect_stdout(io.StringIO()):
                ok_ui = build(os.path.join(specs, "07-UI", "TX-UI-001.md"))
                own_doc = build(os.path.join(ROOT, "docs", "specs", "02-PRD", "SYNC-PRD-001.md"))
            page = open(os.path.join(out, "view_TX-UI-001.html"), encoding="utf-8").read() if ok_ui == 0 else ""
            cases = [
                ("그 뿌리만 색인", sorted(ALL) == ["TX-PRD-001", "TX-UI-001"] and CODE == "TX"),
                ("배치 기준은 file:// 절대 경로", wf.base_for("TX-UI-001") == pathlib.Path(specs).as_uri() + "/07-UI/" and "file://" in page),
                ("화면 문서의 참조도 그 뿌리로 판정", 'class="ref" href="view_TX-PRD-001.html#item-G1"' in page),
                ("색인 밖 문서는 KeyError 대신 1", own_doc == 1),
            ]
    finally:
        SRC_DIR, OUT_DIR, CODE, all_, wf.SPECS_BASE = saved
        ALL.clear(); ALL.update(all_)
    bad = [name for name, ok in cases if not ok] or ([] if cases else ["돌지 못함"])
    for name in bad:
        print("✗ ", name)
    print("다른 저장소 뿌리: 통과" if not bad else f"다른 저장소 뿌리: {len(bad)} 실패")
    return 0 if not bad else 1

def main(argv):
    """[--specs <저장소>/docs/specs] (--all | <원본.md>…) · --selftest"""
    if argv == ["--selftest"]:
        return _selftest() | _selftest_scn() | _selftest_ui() | _selftest_uc() | _selftest_root()
    specs = None
    if "--specs" in argv:
        i = argv.index("--specs")
        if i + 1 >= len(argv):
            print("--specs 뒤에 <저장소>/docs/specs를 준다"); return 2
        specs, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    files = [a for a in argv if a != "--all"]
    if specs is None and files:
        # 경로만 주면 그 문서가 있는 docs/specs — 파일은 docs/specs/{NN-TYPE}/{ID}.md다 (STD-001 1.1)
        roots = {os.path.dirname(os.path.dirname(os.path.abspath(f))) for f in files}
        if len(roots) > 1:
            print("한 번에 준 문서들은 같은 저장소여야 한다 — 뿌리: " + " · ".join(sorted(roots))); return 2
        specs = roots.pop()
    if specs is not None:
        use_root(specs)
    if "--all" in argv:
        for d in ALL.values(): build(d["path"])
        build_index()
        return 0
    return max([build(f) for f in files], default=0)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
