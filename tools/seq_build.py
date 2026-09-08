import os
#!/usr/bin/env python3
"""SEQUENCE MD → 검토용 HTML. mermaid는 브라우저가 렌더링한다."""
import re, json, html

import sys
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs") + "/SEQ/SYNC-SEQ-001.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_seq.html"
raw = open(SRC, encoding="utf-8").read()

def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[\[(.+?)\]\]", r'<span class="ref">\1</span>', s)
    s = re.sub(r"(SEQ-\d\d|SEQ-C\d)", r'<a class="jump" data-jump="\1">\1</a>', s)
    return s

def md_block(text):
    """문단·불릿·표만 처리하는 작은 변환기"""
    out, lines, i = [], text.strip("\n").split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]
            th = "".join(f"<th>{md_inline(c)}</th>" for c in rows[0])
            tb = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue
        if l.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(md_inline(lines[i][2:])); i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        if l.startswith("### "):
            out.append(f"<h4>{md_inline(l[4:])}</h4>"); i += 1; continue
        if l.strip() == "":
            i += 1; continue
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("|", "- ", "### ")):
            para.append(lines[i]); i += 1
        out.append(f"<p>{md_inline(' '.join(para))}</p>")
    return "\n".join(out)

# 생명선 표 (0장) → {약어: (이름, 실체, 종류, 정의)}
LIFE = {}
lt = raw.split("### 0.1 생명선")[1].split("\n---\n")[0]
for row in re.findall(r"^\| (.+?) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$", lt, re.M):
    if row[0] in ("생명선",) or set(row[0]) <= set("-: "): continue
    for ab in re.split(r"[·,]\s*", row[1]):
        LIFE[ab.strip()] = {"name": row[0], "what": row[2], "kind": row[3], "where": row[4]}

def parse_mermaid(mer):
    """participant 목록과 단계(화살표) 목록. alt/opt/loop 문맥도 붙인다."""
    parts, steps, ctx = [], [], []
    for line in mer.split("\n"):
        t = line.strip()
        m = re.match(r"(?:participant|actor) (\w+)(?: as (.+))?$", t)
        if m:
            ab = m.group(1); label = (m.group(2) or ab).replace("<br/>", " ")
            parts.append({"ab": ab, "label": label}); continue
        m = re.match(r"(alt|opt|loop|rect) (.*)$", t)
        if m: ctx.append((m.group(1), m.group(2))); continue
        m = re.match(r"else (.*)$", t)
        if m and ctx: ctx[-1] = (ctx[-1][0], m.group(1)); continue
        if t == "end" and ctx: ctx.pop(); continue
        m = re.match(r"(\w+)\s*(-->>|->>|-->|->|-x)\s*(\w+):\s*(.*)$", t)
        if m:
            steps.append({"from": m.group(1), "arrow": m.group(2), "to": m.group(3), "msg": m.group(4),
                          "ctx": " › ".join(f"{k} {v}" for k, v in ctx if k != "rect")})
    return parts, steps

sections = []
# 0장·1장
intro = raw.split("## 0. 이 문서가 다루는 것")[1].split("## 1. 입구")[0]
table = raw.split("## 1. 대응표 — 입구 → 시퀀스")[1].split("\n---\n")[0]
sections.append({"id": "overview", "title": "개요 · 대응표", "kind": "text",
                 "html": md_block(intro) + "<h3>입구 → 시퀀스 대응표</h3>" + md_block(table)})

for m in re.finditer(r"## (SEQ-\w+) (.+?)\n(.*?)(?=\n---\n\n## |\Z)", raw, re.S):
    sid, title, body = m.group(1), m.group(2).strip(), m.group(3)
    lead = body.split("```mermaid")[0]
    mer = re.search(r"```mermaid\n(.*?)\n```", body, re.S).group(1)
    after = body.split("```\n", 1)[1] if "```\n" in body else ""
    # C1은 표가 after에, 나머지는 '읽을 때 볼 것'
    parts, steps = parse_mermaid(mer)
    life = []
    for p in parts:
        info = LIFE.get(p["ab"]) or LIFE.get(p["label"].split(" ")[0]) or {}
        life.append({"ab": p["ab"], "label": p["label"], "what": info.get("what",""), "kind": info.get("kind",""), "where": info.get("where","")})
    labels = {p["ab"]: p["label"] for p in parts}
    for st in steps:
        st["from_l"] = labels.get(st["from"], st["from"]); st["to_l"] = labels.get(st["to"], st["to"])
        st["ret"] = st["arrow"].startswith("--")
    sections.append({"id": sid, "title": f"{sid} {title}", "kind": "seq",
                     "lead": md_block(lead), "mermaid": mer, "after": md_block(after),
                     "life": life, "steps": steps})

fb = raw.split("## 되먹일 것")[1].split("\n---\n\n## 미결사항")[0]
sections.append({"id": "feedback", "title": "되먹일 것", "kind": "text", "html": md_block(fb)})
pend = raw.split("## 미결사항")[1]
sections.append({"id": "pending", "title": "미결사항", "kind": "text", "html": md_block(pend)})

fmb = re.match(r"^---\n(.*?)\n---", raw, re.S).group(1)
status = {"draft":"초안","review":"검토중","approved":"승인"}[re.search(r"status: (\w+)", fmb).group(1)]

TPL = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>싱크독 시퀀스</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<script>
  // mermaid는 있으면 좋고 없어도 문서는 보인다. jsdelivr → unpkg 순으로 시도
  window.__mermaidReady = new Promise(res => {
    const tryLoad = (srcs) => {
      if (!srcs.length) return res(false);
      const sc = document.createElement("script"); sc.src = srcs[0];
      sc.onload = () => res(true); sc.onerror = () => tryLoad(srcs.slice(1));
      document.head.appendChild(sc);
    };
    tryLoad(["https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js","https://unpkg.com/mermaid@11/dist/mermaid.min.js"]);
  });
</script>
<style>
:root{--paper:#EDEFEC;--panel:#F8F9F7;--card:#fff;--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--hi:#FFF1B8}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;font-size:14.5px;line-height:1.65;-webkit-font-smoothing:antialiased}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em;background:#E4E8E4;padding:1px 5px;border-radius:2px}
.mono{font-family:ui-monospace,Menlo,monospace}
.wrap{max-width:1500px;margin:0 auto;padding:28px 22px 80px}
header{border:1.5px solid var(--ink);background:var(--panel);display:grid;grid-template-columns:1fr auto}
.t-main{padding:20px 26px;border-right:1.5px solid var(--ink)}
.t-main h1{margin:0;font-size:26px;font-weight:700;letter-spacing:-.02em}
.t-main p{margin:8px 0 0;color:var(--soft);font-size:13.5px;max-width:66ch}
.t-meta{display:grid;grid-template-columns:auto auto;align-content:start;font-size:12px}
.t-meta div{padding:8px 14px;border-bottom:1px solid var(--hair)}
.t-meta div:nth-child(odd){color:var(--soft);border-right:1px solid var(--hair)}
.t-meta div:nth-last-child(-n+2){border-bottom:none}

.layout{display:grid;grid-template-columns:250px 1fr;margin-top:22px;border:1.5px solid var(--ink);background:var(--card);min-height:80vh}
.nav{border-right:1.5px solid var(--ink);background:var(--panel);overflow-y:auto;max-height:88vh;position:sticky;top:0}
.nav a{display:block;padding:8px 14px;font-size:13px;color:var(--ink);text-decoration:none;border-left:3px solid transparent;line-height:1.35}
.nav a:hover{background:#EAEEEA}
.nav a.sel{border-left-color:var(--ink);background:#fff;font-weight:600}
.nav a .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}
.nav .grp{padding:12px 14px 4px;font-size:11px;font-weight:700;color:var(--soft)}
.main{padding:26px 34px;overflow-x:auto}
.main h2{margin:0 0 6px;font-size:22px;font-weight:700;letter-spacing:-.02em}
.main h2 .k{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--faint);margin-right:8px;font-weight:500}
.main h3{font-size:15px;margin:26px 0 10px;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}
.main h4{font-size:13.5px;margin:20px 0 8px;color:var(--soft)}
.lead{color:var(--soft);font-size:14px;margin-bottom:14px}
.lead p{margin:0 0 6px}
.dia{border:1px solid var(--rule);background:#fff;padding:14px;margin:12px 0 20px;overflow-x:auto}
.dia svg{display:block;max-width:none}
.dia .err{color:#b00;font:12px ui-monospace,monospace;white-space:pre-wrap}
.dia pre.code{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;margin:8px 0 0;color:var(--ink)}
.after h4,.after p{margin-top:8px}
.notes{background:var(--panel);border-left:3px solid var(--ink);padding:12px 16px;margin-top:6px}
.notes ul{margin:0;padding-left:18px}
.notes li{margin:4px 0}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 14px;background:#fff}
th{text-align:left;font-weight:600;color:var(--soft);padding:7px 9px;border-bottom:1.5px solid var(--ink);background:var(--panel);white-space:nowrap}
td{padding:7px 9px;border-bottom:1px solid var(--hair);vertical-align:top}
.ref{font-family:ui-monospace,Menlo,monospace;font-size:.88em;color:#1a5fb4}
a.jump{color:#1a5fb4;cursor:pointer;border-bottom:1px dashed #1a5fb4;font-family:ui-monospace,Menlo,monospace;font-size:.92em}
.zoom{display:flex;gap:6px;justify-content:flex-end;margin-bottom:-6px}
.split{display:grid;grid-template-columns:minmax(520px,1.4fr) minmax(360px,1fr);gap:16px;align-items:start}
.steps{position:sticky;top:12px;max-height:82vh;overflow-y:auto}
.steps table{font-size:12.5px;margin:0}
.steps td.no{font-family:ui-monospace,Menlo,monospace;color:var(--faint);width:1%;white-space:nowrap}
.steps td.who{white-space:nowrap;font-weight:600}
.steps .arr{color:var(--soft);font-weight:400;margin:0 3px}
.steps .arr.ret{color:#1a5fb4}
.steps tr.ret td{color:var(--soft)}
.steps tr.ctx td{background:#EEF0EC;color:var(--soft);font-size:11.5px;font-weight:600;padding:5px 9px}
table.life td.kind{white-space:nowrap;color:var(--soft)}
.soft{color:var(--soft)}
@media (max-width:1200px){.split{grid-template-columns:1fr}.steps{position:static;max-height:none}}
.zoom button{font:inherit;font-size:12px;padding:3px 9px;border:1px solid var(--rule);background:var(--panel);cursor:pointer}
footer{margin-top:20px;font-size:12.5px;color:var(--soft)}
@media (max-width:900px){.layout{grid-template-columns:1fr}.nav{position:static;max-height:220px;border-right:none;border-bottom:1.5px solid var(--ink)}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="t-main"><h1>싱크독 시퀀스 (검토용)</h1>
  <p>왼쪽에서 흐름을 고르면 다이어그램과 "읽을 때 볼 것"이 나온다. 다이어그램 안 화살표 번호가 유스케이스 흐름 번호와 다른 건 정상이다 — 이건 객체 수준이라 더 잘게 쪼개져 있다.</p></div>
  <div class="t-meta">
    <div>문서</div><div class="mono">SYNC-SEQ-001</div>
    <div>상태</div><div>__STATUS__</div>
    <div>상위</div><div class="mono">SYNC-DOM-002 · API-001 · API-002</div>
    <div>작성</div><div>박호영 · 2026-09-08</div>
  </div>
</header>

<div class="layout">
  <nav class="nav" id="nav"></nav>
  <main class="main" id="main"></main>
</div>
<footer>이 화면은 <code>SEQUENCE_싱크독.md</code>에서 생성된 사람용 뷰다. 다이어그램은 원본의 mermaid 코드블록을 브라우저가 렌더링한다. 고치려면 원본을 고친다.</footer>
</div>

<script id="DATA" type="application/json">__DATA__</script>
<script>
let MERMAID_OK=false;
window.__mermaidReady.then(ok=>{ MERMAID_OK=ok && typeof mermaid!=="undefined";
  if(MERMAID_OK) mermaid.initialize({ startOnLoad:false, theme:"neutral", sequence:{ actorFontFamily:"Pretendard Variable, sans-serif", messageFontFamily:"Pretendard Variable, sans-serif", noteFontFamily:"Pretendard Variable, sans-serif", mirrorActors:false, wrap:true, width:220, noteMargin:12, messageMargin:40, boxMargin:8 } });
  const cur=location.hash.slice(1); if(cur && byId[cur] && byId[cur].kind==="seq") show(cur); });
const D=JSON.parse(document.getElementById("DATA").textContent);
const esc=x=>String(x||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const nav=document.getElementById("nav"), main=document.getElementById("main");
const groups=[["개요",["overview"]],["저장 파이프라인",["SEQ-1","SEQ-2","SEQ-5","SEQ-7","SEQ-19"]],["판단·처리",["SEQ-3","SEQ-6","SEQ-17","SEQ-18"]],["조회",["SEQ-9","SEQ-10","SEQ-11","SEQ-12","SEQ-13","SEQ-14","SEQ-15"]],["프로젝트·계정·운영",["SEQ-4","SEQ-8","SEQ-16","SEQ-20","SEQ-21"]],["공통 형태",["SEQ-C1","SEQ-C2"]],["정리",["feedback","pending"]]];
const byId=Object.fromEntries(D.map(s=>[s.id,s]));
groups.forEach(([g,ids])=>{
  const h=document.createElement("div"); h.className="grp"; h.textContent=g; nav.appendChild(h);
  ids.forEach(id=>{ const s=byId[id]; if(!s) return;
    const a=document.createElement("a"); a.href="#"+id; a.dataset.id=id;
    const m=s.title.match(/^(SEQ-\w+) (.+)$/);
    a.innerHTML=m?`<span class="k">${m[1]}</span>${m[2]}`:s.title;
    a.onclick=e=>{e.preventDefault(); show(id);}; nav.appendChild(a); });
});
const rendered={};
async function show(id){
  const s=byId[id]; if(!s) return;
  nav.querySelectorAll("a").forEach(a=>a.classList.toggle("sel",a.dataset.id===id));
  history.replaceState(null,"","#"+id);
  const m=s.title.match(/^(SEQ-\w+) (.+)$/);
  if(s.kind==="text"){
    main.innerHTML=`<h2>${s.title}</h2>${s.html}`;
  } else {
    const lifeRows=s.life.map(l=>`<tr><td class="mono">${l.ab}</td><td><b>${esc(l.label)}</b></td><td>${esc(l.what)}</td><td class="kind">${esc(l.kind)}</td><td class="soft">${esc(l.where)}</td></tr>`).join("");
    let lastCtx=null;
    const stepRows=s.steps.map((st,i)=>{
      const ctxRow=(st.ctx!==lastCtx)?`<tr class="ctx"><td colspan="3">${st.ctx?esc(st.ctx):"기본 흐름"}</td></tr>`:"";
      lastCtx=st.ctx;
      const who=st.ret?`${esc(st.from_l)} <span class="arr ret">⇢</span> ${esc(st.to_l)}`:`${esc(st.from_l)} <span class="arr">→</span> ${esc(st.to_l)}`;
      return ctxRow+`<tr class="${st.ret?"ret":""}" data-step="${i+1}"><td class="no">${i+1}</td><td class="who">${who}</td><td>${esc(st.msg)}</td></tr>`;
    }).join("");
    main.innerHTML=`<h2><span class="k">${m[1]}</span>${m[2]}</h2>
      <div class="lead">${s.lead}</div>
      <h3>생명선 — 이 그림에 나오는 것</h3>
      <table class="life"><thead><tr><th>약어</th><th>이름</th><th>실체</th><th>종류</th><th>정의</th></tr></thead><tbody>${lifeRows}</tbody></table>
      <h3>흐름</h3>
      <div class="split">
        <div>
          <div class="zoom"><button data-z="-">－</button><button data-z="0">100%</button><button data-z="+">＋</button></div>
          <div class="dia" id="dia"><span class="err">렌더링 중…</span></div>
        </div>
        <div class="steps"><table><thead><tr><th>#</th><th>누가 → 누구</th><th>무엇</th></tr></thead><tbody>${stepRows}</tbody></table>
          <div class="soft" style="font-size:12px;margin-top:6px">→ 호출 · ⇢ 반환. 회색 줄은 분기(alt)·조건(opt)·반복(loop) 안이라는 뜻. 번호는 그림의 번호와 같다.</div></div>
      </div>
      <div class="after">${s.after.replace(/<p><strong>읽을 때 볼 것<\/strong>/, '<h3>읽을 때 볼 것</h3><p>')}</div>`;
    const box=document.getElementById("dia");
    if(!MERMAID_OK){ box.innerHTML=`<div class="err">mermaid.js를 불러오지 못해 코드로 표시합니다 (인터넷 연결 필요)</div><pre class="code">${s.mermaid.replace(/&/g,"&amp;").replace(/</g,"&lt;")}</pre>`; }
    else try{
      if(!rendered[id]){ const {svg}=await mermaid.render("m_"+id.replace(/\W/g,"_"), s.mermaid); rendered[id]=svg; }
      box.innerHTML=rendered[id];
      let scale=1; const svg=box.querySelector("svg");
      main.querySelectorAll(".zoom button").forEach(b=>b.onclick=()=>{ scale=b.dataset.z==="+"?scale*1.2:b.dataset.z==="-"?scale/1.2:1; svg.style.transform=`scale(${scale})`; svg.style.transformOrigin="0 0"; box.style.height=(svg.getBBox().height*scale+40)+"px"; });
    }catch(e){ box.innerHTML=`<div class="err">mermaid 오류:\n${e.message||e}</div>`; }
  }
  main.querySelectorAll("a.jump").forEach(j=>j.onclick=e=>{e.preventDefault(); show(j.dataset.jump);});
  main.scrollIntoView({block:"start"});
}
show(location.hash.slice(1)||"overview");
</script>
</body>
</html>
"""
out = TPL.replace("__DATA__", json.dumps(sections, ensure_ascii=False)).replace("__STATUS__", html.escape(status))
open(OUT, "w", encoding="utf-8").write(out)
print("섹션", len(sections), "개 / 생성", len(out), "바이트")
