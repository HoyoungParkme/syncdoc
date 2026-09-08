import os
#!/usr/bin/env python3
"""MINISPEC MD → 검토용 HTML (뷰 규약 V-MS). 함수 목록을 모듈별 표로, 함수마다 카드."""
import re, json, html, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs") + "/MS/SYNC-MS-001.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_ms.html"
raw = open(SRC, encoding="utf-8").read()
fmb = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
fm = dict((l.partition(":")[0].strip(), l.partition(":")[2].strip()) for l in fmb.group(1).split("\n"))
body = raw[fmb.end():]

def esc(s): return html.escape(s or "")
def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[\[#([^\]]+)\]\]", r'<a class="jump" data-jump="\1">\1</a>', s)
    s = re.sub(r"\[\[([^\]#]+)#([^\]]+)\]\]", r'<span class="ref">\1#\2</span>', s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r'<span class="ref">\1</span>', s)
    return s

def md_block(text):
    out, lines, i = [], text.strip("\n").split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            lang = l[3:].strip(); j = i + 1; code = []
            while j < len(lines) and not lines[j].startswith("```"): code.append(lines[j]); j += 1
            out.append(f'<pre class="code"><code>{esc(chr(10).join(code))}</code></pre>'); i = j + 1; continue
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            th = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"); continue
        if re.match(r"^\d+\. ", l):
            items = []
            while i < len(lines) and (re.match(r"^\d+\. ", lines[i]) or lines[i].startswith("   ")):
                if re.match(r"^\d+\. ", lines[i]): items.append(inline(re.sub(r"^\d+\. ", "", lines[i])))
                else: items[-1] += "<br>" + inline(lines[i].strip())
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"); continue
        if l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "): items.append(inline(lines[i][2:])); i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"); continue
        if l.strip() == "": i += 1; continue
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("|", "- ", "```")) and not re.match(r"^\d+\. ", lines[i]):
            para.append(lines[i]); i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)

# 함수 블록
funcs = []
for m in re.finditer(r"^#### ([A-Za-z_]+\.[a-z_]+) (.+?)\n(.*?)(?=\n#### |\n## |\Z)", body, re.S | re.M):
    fid, title, blk = m.group(1), m.group(2).strip(), m.group(3)
    parts = {}
    # **부분** 이름으로 자름
    for pm in re.finditer(r"\*\*(시그니처|근거|입력|처리|출력|예외|호출하는 것|테스트 관점)\*\*[ ：:]*(.*?)(?=\n\*\*(?:시그니처|근거|입력|처리|출력|예외|호출하는 것|테스트 관점)\*\*|\Z)", blk, re.S):
        parts[pm.group(1)] = pm.group(2).strip()
    # 근거는 '근거:' 줄로도 옴
    if "근거" not in parts:
        rm = re.search(r"^근거: (.+)$", blk, re.M)
        if rm: parts["근거"] = rm.group(1)
    mod, name = fid.split(".", 1)
    sig = parts.get("시그니처", "")
    sigline = re.sub(r"```python\n|\n```", "", sig).strip()
    funcs.append({"id": fid, "mod": mod, "name": name, "title": title, "sig": sigline,
                  "parts": {k: md_block(v) if k != "시그니처" else md_block(v) for k, v in parts.items()},
                  "brief": len(parts) <= 4})
# 4장·5장
tail = {}
for sec in ["3. 미결사항"]:
    m = re.search(r"## " + re.escape(sec) + r"\n(.*?)(?=\n## |\Z)", body, re.S)
    if m: tail[sec] = md_block(m.group(1))
intro = md_block(body.split("## 1. 함수 목록")[0].split("## 0. 이 문서가 다루는 것")[1])

TPL = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{--paper:#EDEFEC;--panel:#F8F9F7;--card:#fff;--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;font-size:14.5px;line-height:1.65;-webkit-font-smoothing:antialiased}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em;background:#E4E8E4;padding:1px 5px;border-radius:2px}
pre.code{background:#1E2A30;color:#E8ECE8;padding:12px 14px;font:12.5px/1.55 ui-monospace,Menlo,monospace;overflow-x:auto;margin:6px 0 12px;border-radius:2px}
pre.code code{background:none;color:inherit;padding:0;font-size:inherit}
.mono{font-family:ui-monospace,Menlo,monospace}
.wrap{max-width:1500px;margin:0 auto;padding:28px 22px 80px}
header{border:1.5px solid var(--ink);background:var(--panel);display:grid;grid-template-columns:1fr auto}
.t-main{padding:20px 26px;border-right:1.5px solid var(--ink)}.t-main h1{margin:0;font-size:26px;font-weight:700;letter-spacing:-.02em}.t-main div{margin-top:8px;color:var(--soft);font-size:13.5px;max-width:70ch}
.t-meta{display:grid;grid-template-columns:auto auto;align-content:start;font-size:12px}.t-meta div{padding:8px 14px;border-bottom:1px solid var(--hair)}.t-meta div:nth-child(odd){color:var(--soft);border-right:1px solid var(--hair)}.t-meta div:nth-last-child(-n+2){border-bottom:none}
.layout{display:grid;grid-template-columns:270px 1fr;margin-top:22px;border:1.5px solid var(--ink);background:var(--card);min-height:80vh}
.nav{border-right:1.5px solid var(--ink);background:var(--panel);overflow-y:auto;max-height:88vh;position:sticky;top:0}
.nav .grp{padding:12px 14px 4px;font-size:11px;font-weight:700;color:var(--soft)}
.nav a{display:block;padding:7px 14px;font-size:13px;color:var(--ink);text-decoration:none;border-left:3px solid transparent;line-height:1.35}
.nav a:hover{background:#EAEEEA}.nav a.sel{border-left-color:var(--ink);background:#fff;font-weight:600}
.nav a .k{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--ink)}.nav a .t{color:var(--soft);font-size:12px;margin-left:6px}
.nav a.brief .k{color:var(--soft)}
.main{padding:26px 34px;overflow-x:auto}
.main h2{margin:0 0 4px;font-size:22px;font-weight:700;letter-spacing:-.02em}.main h2 .mod{color:var(--faint);font-weight:500;font-size:15px}
.main h3{font-size:13px;margin:22px 0 8px;padding-bottom:6px;border-bottom:1.5px solid var(--ink);color:var(--ink)}
.brief-tag{display:inline-block;font-size:11px;padding:1px 8px;border:1px solid var(--rule);background:var(--panel);color:var(--soft);margin-left:8px;vertical-align:middle}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 14px;background:#fff}
th{text-align:left;font-weight:600;color:var(--soft);padding:7px 9px;border-bottom:1.5px solid var(--ink);background:var(--panel)}
td{padding:7px 9px;border-bottom:1px solid var(--hair);vertical-align:top}
table.list td:first-child{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;white-space:nowrap}
table.list tr{cursor:pointer}table.list tr:hover td{background:#F2F4F1}
ol,ul{margin:4px 0 12px;padding-left:22px}li{margin:4px 0}
.ref{font-family:ui-monospace,Menlo,monospace;font-size:.88em;color:#1a5fb4}
a.jump{color:#1a5fb4;cursor:pointer;border-bottom:1px dashed #1a5fb4;font-family:ui-monospace,Menlo,monospace;font-size:.92em}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media (max-width:1000px){.layout{grid-template-columns:1fr}.nav{position:static;max-height:220px;border-right:none;border-bottom:1.5px solid var(--ink)}.two{grid-template-columns:1fr}}
footer{margin-top:20px;font-size:12.5px;color:var(--soft)}
</style></head><body><div class="wrap">
<header><div class="t-main"><h1>__TITLE__ (검토용)</h1><div>__INTRO__</div></div>
<div class="t-meta"><div>문서</div><div class="mono">__DOCID__</div><div>상태</div><div>__STATUS__</div><div>상위</div><div class="mono">__UP__</div><div>함수</div><div>__N__개</div></div></header>
<div class="layout"><nav class="nav" id="nav"></nav><main class="main" id="main"></main></div>
<footer>이 화면은 <code>__SRC__</code>에서 생성된 사람용 뷰(V-MS)다. 고치려면 원본을 고친다.</footer></div>
<script id="DATA" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById("DATA").textContent);
const nav=document.getElementById("nav"),main=document.getElementById("main");
const byId=Object.fromEntries(D.funcs.map(f=>[f.id,f]));
const mods=[...new Set(D.funcs.map(f=>f.mod))];
const a0=document.createElement("a");a0.href="#";a0.dataset.id="__list";a0.innerHTML='<span class="k">함수 목록</span>';a0.onclick=e=>{e.preventDefault();showList();};nav.appendChild(a0);

mods.forEach(m=>{const h=document.createElement("div");h.className="grp";h.textContent=m;nav.appendChild(h);
 D.funcs.filter(f=>f.mod===m).forEach(f=>{const a=document.createElement("a");a.href="#"+f.id;a.dataset.id=f.id;a.className=f.brief?"brief":"";a.innerHTML=`<span class="k">${f.name}</span><span class="t">${f.title}</span>`;a.onclick=e=>{e.preventDefault();show(f.id);};nav.appendChild(a);});});
const a9=document.createElement("a");a9.href="#";a9.dataset.id="__tail";a9.innerHTML='<span class="k">미결사항</span>';a9.onclick=e=>{e.preventDefault();showTail();};nav.appendChild(a9);
function sel(id){nav.querySelectorAll("a").forEach(a=>a.classList.toggle("sel",a.dataset.id===id));}
function wire(){main.querySelectorAll("a.jump").forEach(j=>j.onclick=e=>{e.preventDefault();show(j.dataset.jump);});}
function showList(){sel("__list");
 let h=`<h2>함수 목록</h2>`;
 mods.forEach(m=>{h+=`<h3>${m}</h3><table class="list"><thead><tr><th>함수</th><th>한 줄</th><th>시그니처</th><th>상세도</th></tr></thead><tbody>`;
  D.funcs.filter(f=>f.mod===m).forEach(f=>{h+=`<tr data-id="${f.id}"><td>${f.name}</td><td>${f.title}</td><td><code>${(f.sig||"").split("\n")[0].replace(/^(async )?def /,"").slice(0,90)}</code></td><td>${f.brief?"간략":"전체"}</td></tr>`;});
  h+=`</tbody></table>`;});
 main.innerHTML=h;main.querySelectorAll("tr[data-id]").forEach(r=>r.onclick=()=>show(r.dataset.id));main.scrollIntoView({block:"start"});}
function show(id){const f=byId[id];if(!f)return;sel(id);history.replaceState(null,"","#"+id);
 const P=f.parts;const sec=(k)=>P[k]?`<h3>${k}</h3>${P[k]}`:"";
 main.innerHTML=`<h2><span class="mod">${f.mod}.</span>${f.name} <span style="color:var(--soft);font-weight:500;font-size:16px"> — ${f.title}</span>${f.brief?'<span class="brief-tag">간략형</span>':''}</h2>
  ${sec("시그니처")}${sec("근거")}
  <div class="two"><div>${sec("입력")}${sec("처리")}</div><div>${sec("출력")}${sec("예외")}${sec("호출하는 것")}${sec("테스트 관점")}</div></div>`;
 wire();main.scrollIntoView({block:"start"});}
function showTail(){sel("__tail");main.innerHTML=Object.entries(D.tail).map(([k,v])=>`<h2>${k}</h2>${v}`).join("");wire();}
const h=location.hash.slice(1);if(h&&byId[h])show(h);else showList();
</script></body></html>"""
status = {"draft": "초안", "review": "검토중", "approved": "승인"}[fm["status"]]
out = (TPL.replace("__TITLE__", esc(fm["title"])).replace("__INTRO__", intro.split("</p>")[0].replace("<p>", ""))
       .replace("__DOCID__", fm["doc_id"]).replace("__STATUS__", status).replace("__UP__", esc(fm.get("upstream", "").strip("[]")))
       .replace("__N__", str(len(funcs))).replace("__SRC__", SRC.split("/")[-1])
       .replace("__DATA__", json.dumps({"funcs": funcs, "tail": tail}, ensure_ascii=False)))
open(OUT, "w", encoding="utf-8").write(out)
print(f"함수 {len(funcs)}개 (간략 {sum(f['brief'] for f in funcs)}) → {OUT}")
