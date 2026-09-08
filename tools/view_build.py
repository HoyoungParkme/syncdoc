#!/usr/bin/env python3
"""싱크독 사람용 뷰 생성기. STD-002 뷰 규약의 구현.
사용: view_build.py <원본.md> [출력.html]
frontmatter type을 보고 V-* 모듈로 본문을 그린다. 공통 틀은 한 곳."""
import re, json, html, sys, glob, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "docs", "specs")
OUT_DIR = os.path.join(ROOT, "docs", "views")
os.makedirs(OUT_DIR, exist_ok=True)
STATUS_KO = {"draft": "초안", "review": "검토중", "approved": "승인"}
STAGE = {"RFQ": 1, "PRD": 2, "SCN": 3, "UC": 4, "INFRA": 5, "DOM": 6, "UI": 7, "API": 8, "SEQ": 9, "MS": 10, "CODE": 11, "STD": None}

# ───────────────────────── 전체 문서 인덱스 (참조·하위 계산용) ─────────────────────────
def load_all():
    docs = {}
    for f in glob.glob(os.path.join(SRC_DIR, "*", "*.md")):
        if "/_templates/" in f: continue
        raw = open(f, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
        if not m: continue
        fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in m.group(1).split("\n"))}
        body = raw[m.end():]
        nocode = re.sub(r"```.*?```", "", body, flags=re.S); nocode = re.sub(r"`[^`]*`", "", nocode)
        items = []
        for h in re.findall(r"^(#{1,6}) (.+)$", nocode, re.M):
            tok = h[1].split(" ")[0]
            if not re.match(r"^\d", tok) and re.match(r"^[A-Za-z]", tok): items.append((tok, h[1][len(tok):].strip()))
        refs = re.findall(r"\[\[([^\]]+)\]\]", nocode)
        docs[fm["doc_id"]] = {"fm": fm, "body": body, "items": dict(items), "refs": refs, "file": os.path.basename(f)}
    return docs
ALL = load_all()

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
def render_blocks(text, self_id, item_pat=None):
    """헤딩·문단·목록·표·코드블록. 항목 헤딩은 뱃지. mermaid는 <pre class=mermaid>."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            lang = l[3:].strip(); j = i + 1; code = []
            while j < len(lines) and not lines[j].startswith("```"): code.append(lines[j]); j += 1
            src = "\n".join(code)
            if lang == "mermaid": out.append(f'<div class="mer"><pre class="mermaid">{esc(src)}</pre></div>')
            elif lang == "html": out.append(f'<div class="wfbox">{src}</div>')
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
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6} |```|\||\s*- |\d+\. |> |---$)", lines[i]):
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

def item_blocks(body, pat):
    """항목 헤딩 블록 → [(id, title, level, text)]"""
    lines = body.split("\n"); out = []; i = 0
    while i < len(lines):
        h = re.match(r"^(#{1,6}) (\S+)(?: (.*))?$", lines[i])
        if h and re.fullmatch(pat, h.group(2)) and not re.match(r"^\d", h.group(2)):
            lvl = len(h.group(1)); j = i + 1
            while j < len(lines):
                h2 = re.match(r"^(#{1,6}) ", lines[j])
                if h2 and len(h2.group(1)) <= lvl: break
                j += 1
            out.append((h.group(2), h.group(3) or "", lvl, "\n".join(lines[i + 1:j]))); i = j
        else: i += 1
    return out

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
    ups = re.findall(r"SYNC-[A-Z]+-\d+", fm.get("upstream", ""))
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

# ───────────────────────── V-PRD ─────────────────────────
def v_prd(doc):
    did = doc["fm"]["doc_id"]; body = doc["body"]; pat = r"G\d+|R\d+|N\d+"
    secs = split_sections(body); out = []
    for title, text in secs:
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("목표"):
            # G 항목 → 표로 재조립
            blocks = item_blocks(text, r"G\d+")
            rows = ""
            for gid, gt, _, gb in blocks:
                down = sum(1 for d, v in downstream_of(did).items() if gid in v)
                rows += f'<tr id="item-{gid}"><td class="iid">{gid}</td><td>{inline(gt, did)}</td><td class="num">{down or ""}</td></tr>'
            out.append(f'<h2>{esc(title)}</h2><table class="reassembled"><thead><tr><th>#</th><th>목표</th><th>하위 참조</th></tr></thead><tbody>{rows}</tbody></table>')
            continue
        if name.startswith("요구사항"):
            out.append(f"<h2>{esc(title)}</h2>")
            # 소절(### 3.1 …) 유지, 항목은 카드
            for sub in re.split(r"^### ", text, flags=re.M):
                if not sub.strip(): continue
                st, _, srest = sub.partition("\n")
                if not srest.strip() and "####" not in sub: continue
                if not sub.startswith("####"): out.append(f"<h3>{esc(st)}</h3>")
                for rid, rt, _, rb in item_blocks(("#### " + sub) if sub.startswith("####") else srest, r"R\d+|N\d+"):
                    ac = re.findall(r"^- \[([ x])\] (.+)$", rb, re.M)
                    done = sum(1 for c, _ in ac if c == "x")
                    desc = re.sub(r"^- \[[ x]\] .+$", "", rb, flags=re.M).strip()
                    down = sorted(d for d, v in downstream_of(did).items() if rid in v)
                    card = f'<article class="card" id="item-{rid}"><div class="card-h"><span class="iid">{rid}</span><b>{inline(rt, did)}</b>'
                    if ac: card += f'<span class="pill">인수기준 {done}/{len(ac)}</span>'
                    if down: card += f'<span class="pill soft">하위 {len(down)}</span>'
                    card += "</div>" + render_blocks(desc, did)
                    if ac: card += '<ul class="ac">' + "".join(f'<li class="{"done" if c=="x" else ""}"><span class="box">{"✓" if c=="x" else ""}</span>{inline(t, did)}</li>' for c, t in ac) + "</ul>"
                    if down: card += '<div class="down">이 요구사항을 근거로 삼은 문서: ' + " · ".join(f'<a class="ref" href="{view_href(d)}">{d}</a>' for d in down) + "</div>"
                    out.append(card + "</article>")
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
def v_scn(doc):
    """페르소나 P 카드 나란히 · 시나리오 S 항목마다 번호 흐름을 단계 목록으로, 변형은 접힘 · 대응표 그대로."""
    did = doc["fm"]["doc_id"]; out = []
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("페르소나"):
            cards = ""
            for pid, pt, _, pb in item_blocks(text, r"P\d+"):
                cards += f'<article class="pcard" id="item-{pid}"><div class="card-h"><span class="iid">{pid}</span><b>{inline(pt, did)}</b></div>{render_blocks(pb, did)}</article>'
            lead = re.split(r"^#### ", text, flags=re.M)[0]
            out.append(f"<h2>{esc(title)}</h2>{render_blocks(lead, did)}<div class=\"pgrid\">{cards}</div>"); continue
        if name.startswith("시나리오"):
            out.append(f"<h2>{esc(title)}</h2>" + render_blocks(re.split(r"^### ", text, flags=re.M)[0], did))
            for sid, st, _, sb in item_blocks(text, r"S\d+"):
                # 머리(주체·상황) / 번호 흐름 / 변형 / 성공 조건·연관
                head = []; steps = []; variants = []; tail = []
                mode = "head"
                for l in sb.split("\n"):
                    if re.match(r"^\d+\. ", l): mode = "steps"; steps.append(l)
                    elif l.startswith("**변형"): mode = "var"; variants.append(l)
                    elif l.startswith("**성공 조건") or l.startswith("**연관"): mode = "tail"; tail.append(l)
                    elif mode == "head": head.append(l)
                    elif mode == "steps" and l.strip() and not l.startswith("**"): steps[-1] += "\n" + l if steps else ""
                    elif mode == "var": variants.append(l)
                    elif mode == "tail": tail.append(l)
                var_html = ""
                for v in [x for x in variants if x.strip()]:
                    m = re.match(r"\*\*(변형[^*]*)\*\*:?\s*(.*)", v)
                    if m: var_html += f'<details class="variant"><summary>{esc(m.group(1))}</summary><p>{inline(m.group(2), did)}</p></details>'
                    else: var_html += f"<p>{inline(v, did)}</p>"
                out.append(f'<article class="scard" id="item-{sid}"><div class="card-h"><span class="iid">{sid}</span><b>{inline(st, did)}</b><span class="pill soft">{len(steps)}단계</span></div>'
                           f'{render_blocks(chr(10).join(head), did)}<ol class="steps">{"".join(f"<li>{inline(re.sub(chr(94)+chr(92)+"d+"+chr(92)+". ", "", x.split(chr(10))[0]), did)}</li>" for x in steps)}</ol>{var_html}{render_blocks(chr(10).join(tail), did)}</article>')
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"P\d+|S\d+"))
    return "\n".join(out)

# ───────────────────────── V-UC ─────────────────────────
def v_uc(doc):
    """1 액터 → 2 유스케이스 발견·명세(좌 목록 / 우 상세) → 3 패키지(탭 + UML 다이어그램) → 4 대응표.
    파싱과 다이어그램 JS는 기존 parse.py·build.py에서 가져온다."""
    import subprocess, importlib.util
    did = doc["fm"]["doc_id"]
    subprocess.run(["python3", os.path.join(os.path.dirname(__file__), "parse.py")], capture_output=True)
    data = json.load(open(os.path.join(os.path.dirname(__file__), "data.json"), encoding="utf-8"))
    bp = open(os.path.join(os.path.dirname(__file__), "build.py"), encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", bp, re.S).group(1)
    js = re.search(r'<script>\n(const D=JSON.*?)</script>\n</body>', bp, re.S).group(1)
    # 패키지 목록은 데이터에서
    pkgs = []
    for u in data["ucs"]:
        if u["package"] not in pkgs: pkgs.append(u["package"])
    js = js.replace('const PKGS=["명세 조회","명세 작성","변경 추적","검토·확정","연동·표현"];', "const PKGS=" + json.dumps(pkgs, ensure_ascii=False) + ";")
    # 상세 안 [[ ]] 참조를 링크로
    js = js.replace('const linkUC=s=>md(s).replace(/(UC-[AHGS]\\d+)/g,\'<span class="jump" data-jump="$1">$1</span>\');',
        'const linkUC=s=>md(s).replace(/\\[\\[#(UC-[AHGS]\\d+)\\]\\]/g,\'<span class="jump" data-jump="$1">$1</span>\').replace(/\\[\\[([A-Z]+-[A-Z]+-\\d+)#([^\\]]+)\\]\\]/g,\'<a class="ref" href="view_$1.html#item-$2">$1#$2</a>\').replace(/\\[\\[([A-Z]+-[A-Z]+-\\d+)\\]\\]/g,\'<a class="ref" href="view_$1.html">$1</a>\').replace(/(?<![\\w#-])(UC-[AHGS]\\d+)(?![\\w"])/g,\'<span class="jump" data-jump="$1">$1</span>\');')
    # 1. 액터 표 (원본 1장)
    actor_sec = next((t for n, t in split_sections(doc["body"]) if re.sub(r"^\d+\.\s*", "", n).startswith("액터")), "")
    # 3장 서문(하위기능 설명)
    body = f"""
<h2><span class="n">1</span>액터 식별</h2>
{render_blocks(actor_sec, did)}

<h2><span class="n">2</span>유스케이스 발견·명세</h2>
<p class="soft">왼쪽에서 고르면 오른쪽에 Cockburn 12행 표 + 기본 흐름 + 확장. 흐름 안 <span class="jump">UC-xx</span>를 누르면 그리로.</p>
<div class="spec" id="spec">
  <nav class="nav" id="nav"></nav>
  <article class="detail" id="detail" aria-live="polite"></article>
</div>

<h2><span class="n">3</span>패키지</h2>
<p class="soft">유스케이스를 기능 영역으로 묶은 것. 다이어그램의 관계선은 원본 표의 <code>포함</code>·<code>확장점</code>·<code>일반화</code>에서 그려진다. 타원을 누르면 2번 명세로.</p>
<div class="tabs" id="tabs" role="tablist"></div>
<div class="canvas"><svg id="dg" xmlns="http://www.w3.org/2000/svg"></svg></div>
<div class="key">
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#5C6B73" stroke-width="1.2"/></svg>연결</span>
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="27" y2="5" stroke="#5C6B73" stroke-width="1.2" stroke-dasharray="6 4"/><path d="M27,1 L34,5 L27,9" fill="none" stroke="#5C6B73" stroke-width="1.2"/></svg>«include» / «extend»</span>
  <span><svg width="34" height="12"><line x1="0" y1="6" x2="24" y2="6" stroke="#5C6B73" stroke-width="1.2"/><path d="M24,1 L34,6 L24,11 Z" fill="#fff" stroke="#5C6B73" stroke-width="1.2"/></svg>일반화</span>
  <span><svg width="30" height="14"><ellipse cx="15" cy="7" rx="13" ry="6" fill="#F8F9F7" stroke="#5C6B73" stroke-width="1.4" stroke-dasharray="6 4"/></svg>추상·다른 패키지</span>
</div>

<h2><span class="n">4</span>대응표</h2>
<table class="matrix" id="mx1"></table>
<div style="height:18px"></div>
<table class="matrix" id="mx2"></table>

<style>{css}</style>
<script id="DATA" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>
<script>{js.replace('if(scroll)document.getElementById("spec").scrollIntoView({block:"start"});','if(scroll)document.getElementById("spec").scrollIntoView({block:"start"});')}</script>
"""
    return body

# ───────────────────────── V-INFRA ─────────────────────────
def v_infra(doc):
    """제약 C 항목 → 표로 재조립(ID·내용·출처·이 제약을 근거로 삼은 문서). 구성도·시퀀스 mermaid 그대로. 나머지 원본 순서."""
    did = doc["fm"]["doc_id"]; out = []
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("제약"):
            lead = re.split(r"^#### ", text, flags=re.M)[0]
            rows = ""
            for cid, ct, _, cb in item_blocks(text, r"C\d+"):
                src = re.search(r"^출처: (.+)$", cb, re.M)
                downs = sorted(d for d, v in downstream_of(did).items() if cid in v)
                rows += f'<tr id="item-{cid}"><td class="iid">{cid}</td><td>{inline(ct, did)}</td><td>{inline(src.group(1), did) if src else ""}</td><td>{" · ".join(f"<a class=\"ref\" href=\"{view_href(d)}\">{d}</a>" for d in downs)}</td></tr>'
            tail = text[text.rfind("\n\n**"):] if "\n\n**" in text and "이 설계의 두 축" in text else ""
            out.append(f'<h2>{esc(title)}</h2>{render_blocks(lead, did)}<table class="reassembled"><thead><tr><th>#</th><th>제약</th><th>출처 (근거)</th><th>이 제약을 근거로 삼은 곳</th></tr></thead><tbody>{rows}</tbody></table>{render_blocks(tail, did)}')
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
    did = doc["fm"]["doc_id"]
    if "와이어프레임" in doc["fm"]["title"]:
        return absorb("wf_build.py", os.path.join(SRC_DIR, "UI", doc["file"]), "/tmp/_wf.html").replace('.wrap{max-width:1560px;margin:0 auto;padding:28px 22px 80px}', '')
    # 화면 설계: UI 항목 표로 재조립 + 나머지 원본
    out = []
    for title, text in split_sections(doc["body"]):
        name = re.sub(r"^\d+\.\s*", "", title)
        if name.startswith("화면 목록"):
            rows = ""
            for uid, ut, _, ub in item_blocks(text, r"UI-\d+"):
                first = ub.strip().split("\n")[0]
                kind = first.split(".")[0] if "." in first else ""
                uc = re.search(r"주 유스케이스: (.+)$", first)
                downs = sorted(d for d, v in downstream_of(did).items() if uid in v)
                rows += f'<tr id="item-{uid}"><td class="iid">{uid}</td><td>{inline(ut, did)}</td><td>{esc(kind)}</td><td>{inline(first.split(". ",1)[1].split(" 주 유스케이스")[0] if ". " in first else first, did)}</td><td>{inline(uc.group(1), did) if uc else ""}</td><td>{" · ".join(f"<a class=\"ref\" href=\"{view_href(d)}\">{d}</a>" for d in downs)}</td></tr>'
            lead = re.split(r"^#### ", text, flags=re.M)[0]
            out.append(f'<h2>{esc(title)}</h2>{render_blocks(lead, did)}<table class="reassembled"><thead><tr><th>#</th><th>화면</th><th>종류</th><th>목적</th><th>주 유스케이스</th><th>참조한 곳</th></tr></thead><tbody>{rows}</tbody></table>')
            continue
        out.append(f"<h2>{esc(title)}</h2>" + render_blocks(text, did, r"UI-\d+"))
    return "\n".join(out)

def v_seq(doc):
    return absorb("seq_build.py", os.path.join(SRC_DIR, "SEQ", doc["file"]), "/tmp/_seq.html")

def v_ms(doc):
    return absorb("ms_build.py", os.path.join(SRC_DIR, "MS", doc["file"]), "/tmp/_ms.html")

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
.scard{border:1px solid var(--rule);background:#fff;padding:16px 20px;margin:14px 0}.scard ol.steps{counter-reset:s;list-style:none;padding:0;margin:10px 0}.scard ol.steps li{counter-increment:s;position:relative;padding:6px 0 6px 38px;border-left:2px solid var(--rule);margin-left:12px}.scard ol.steps li::before{content:counter(s);position:absolute;left:-13px;top:6px;width:24px;height:24px;border-radius:50%;background:var(--ink);color:#fff;font-size:11.5px;text-align:center;line-height:24px;font-weight:600}
.variant{margin:8px 0;border:1px dashed var(--rule);padding:6px 12px;background:var(--panel)}.variant summary{cursor:pointer;font-weight:600;font-size:13px}.variant p{margin:6px 0 2px;font-size:13.5px}
.pgrid.dom{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.meth{display:inline-block;font:600 10.5px ui-monospace,monospace;padding:1px 6px;border-radius:2px;color:#fff;background:#666}.m-get{background:#2b7a4b}.m-post{background:#2a5db0}.m-delete{background:#b03030}.m-put,.m-patch{background:#a06a00}
table.eps tr.grp td{background:var(--panel);font-weight:600;color:var(--soft)}td.small{font-size:12px;color:var(--soft)}
details.ep{border:1px solid var(--rule);margin:8px 0;background:#fff}details.ep summary{cursor:pointer;padding:8px 12px;font-size:13.5px}details.ep>*:not(summary){padding:0 14px 8px}
.desc{color:var(--soft);font-size:13.5px}table.schema{font-size:12.5px}
.down{margin-top:10px;padding-top:8px;border-top:1px dashed var(--rule);font-size:12.5px;color:var(--soft)}
ul,ol{margin:6px 0 12px;padding-left:22px}li{margin:3px 0}blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--ink);background:var(--panel);color:var(--soft)}
hr{border:none;border-top:1px solid var(--hair);margin:22px 0}
.soft{color:var(--soft)}.warn{color:#b00;font-size:13px;border:1px solid #b00;padding:6px 10px;background:#fff5f5}.mer{background:#fff;border:1px solid var(--rule);padding:10px;margin:8px 0 16px;overflow-x:auto}pre.mermaid{margin:0;font:12px ui-monospace,monospace;white-space:pre-wrap}pre.mermaid.nomer::before{content:"mermaid.js를 불러오지 못해 코드로 표시";display:block;color:#b00;margin-bottom:6px}
.wfbox{border:1px dashed var(--rule);padding:10px;background:#f4f4f4;margin:8px 0 16px;font-size:12px}
footer{margin-top:20px;font-size:12.5px;color:var(--soft)}
.tabs{display:flex;border:1.5px solid var(--ink);border-top:none;background:var(--panel)}.tabs button{font:inherit;font-size:13px;padding:9px 16px;background:none;border:none;border-right:1px solid var(--rule);cursor:pointer;color:var(--soft)}.tabs button.on{background:#fff;color:var(--ink);font-weight:600}
@media (max-width:860px){.tb{grid-template-columns:1fr}.tb-main{border-right:none;border-bottom:1.5px solid var(--ink)}.body{padding:18px}}
"""

def build(src):
    raw = open(src, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in m.group(1).split("\n"))}
    doc = ALL[fm["doc_id"]]
    typ = fm["type"]
    fn = VIEWS.get(typ)
    body_html = fn(doc) if fn else v_plain(doc, ITEM_PAT.get(typ, r"\S+"))
    out = shell(doc, body_html)
    path = os.path.join(OUT_DIR, view_href(fm["doc_id"]))
    open(path, "w", encoding="utf-8").write(out)
    print(f"{fm['doc_id']} ({typ}, {'V-'+typ if fn else '원본 순서'}) → {os.path.basename(path)}")

def build_index():
    order = ["RFQ","PRD","SCN","UC","INFRA","DOM","UI","API","SEQ","MS","CODE","STD"]
    rows = ""
    for typ in order:
        ds = sorted((d for d in ALL.values() if d["fm"]["type"] == typ), key=lambda d: d["fm"]["doc_id"])
        for d in ds:
            fm = d["fm"]; st = STAGE.get(typ)
            rows += f'<tr><td class="num">{st or "—"}</td><td class="mono"><a href="{view_href(fm["doc_id"])}">{fm["doc_id"]}</a></td><td>{esc(fm["title"])}</td><td><span class="st st-{fm["status"]}">{STATUS_KO[fm["status"]]}</span></td><td class="num">{len(d["items"])}</td></tr>'
    html_ = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>싱크독 — 문서</title><style>{CSS}</style></head><body><div class="wrap">
<header class="tb"><div class="tb-main"><div class="tb-kicker">싱크독 · SYNC</div><h1>명세 체인 — 문서 {len(ALL)}개</h1><p>11단계 + 단계 밖 STD. 클릭하면 사람용 뷰. 이 목록이 웹 UI-4 프로젝트 상세의 정적 판이다.</p></div>
<div class="tb-meta"><div>프로젝트</div><div class="mono">SYNC</div><div>항목</div><div>{sum(len(d["items"]) for d in ALL.values())}개</div><div>참조</div><div>{sum(len(d["refs"]) for d in ALL.values())}개</div></div></header>
<main class="body"><table><thead><tr><th>단계</th><th>문서</th><th>제목</th><th>상태</th><th>항목</th></tr></thead><tbody>{rows}</tbody></table></main>
<footer>생성: _tools/view_build.py</footer></div></body></html>"""
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(html_)
    print("index.html")

if __name__ == "__main__":
    if sys.argv[1:] == ["--all"]:
        for d in ALL.values(): build(os.path.join(SRC_DIR, d["fm"]["type"], d["file"]))
        build_index()
    else:
        for s in sys.argv[1:]: build(s)
