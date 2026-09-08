import os
#!/usr/bin/env python3
"""와이어프레임 원본 MD를 파싱해 화면별 좌우 배치 뷰(HTML)를 만든다.
왼쪽: 배치 뼈대 / 오른쪽: 요소 표·규칙·시나리오. 요소 번호로 양쪽이 연동된다."""
import re, json, html

import sys
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs") + "/UI/SYNC-UI-002.md"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_wf.html"
raw = open(SRC, encoding="utf-8").read()

screens = []
for sec in re.split(r"\n## (?=UI-\d+)", raw)[1:]:
    head = sec.split("\n", 1)[0].strip()
    sid, name = head.split(" ", 1)
    meta = dict(re.findall(r"^\| (.+?) \| (.+?) \|$", sec.split("### 배치")[0], re.M))
    layout = re.search(r"```html\n(.*?)\n```", sec, re.S).group(1)
    elem_block = sec.split("### 요소")[1].split("### 규칙")[0]
    elems = []
    for line in elem_block.strip().split("\n")[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 5:
            elems.append(dict(zip(["no","name","kind","shows","onclick"], cells)))
    rules_block = sec.split("### 규칙")[1].split("### 시나리오")[0]
    rules = [l[2:].strip() for l in rules_block.strip().split("\n") if l.startswith("- ")]
    scen_block = sec.split("### 시나리오")[1]
    scenarios = []
    for chunk in re.split(r"\n(?=\*\*S-\d+)", scen_block.strip()):
        m = re.match(r"\*\*(S-\d+) (.+?)\*\*(?: — (.+))?\n", chunk)
        if not m: continue
        steps = [re.sub(r"^\d+\.\s*", "", l).strip() for l in chunk.split("\n")[1:] if re.match(r"^\d+\.", l.strip())]
        scenarios.append({"id": m.group(1), "title": m.group(2), "uc": m.group(3) or "", "steps": steps})
    screens.append({"id": sid, "name": name, "meta": meta, "layout": layout,
                    "elems": elems, "rules": rules, "scenarios": scenarios})

screens.sort(key=lambda x: int(x["id"].split("-")[1]))
print(f"화면 {len(screens)}개:", [s["id"] for s in screens])
for s in screens:
    print(f"  {s['id']} 요소 {len(s['elems'])} 규칙 {len(s['rules'])} 시나리오 {len(s['scenarios'])}")

TPL = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>싱크독 와이어프레임</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{--paper:#EDEFEC;--panel:#F8F9F7;--card:#fff;--ink:#1E2A30;--soft:#5C6B73;--faint:#8A969C;--rule:#C9CFCB;--hair:#E1E5E1;--hi:#FFF1B8;--hi-b:#C9A800}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1560px;margin:0 auto;padding:28px 22px 80px}
header{border:1.5px solid var(--ink);background:var(--panel);display:grid;grid-template-columns:1fr auto}
.t-main{padding:20px 26px;border-right:1.5px solid var(--ink)}
.t-main h1{margin:0;font-size:26px;font-weight:700;letter-spacing:-.02em}
.t-main p{margin:8px 0 0;color:var(--soft);font-size:13.5px;max-width:64ch}
.t-meta{display:grid;grid-template-columns:auto auto;align-content:start;font-size:12px}
.t-meta div{padding:8px 14px;border-bottom:1px solid var(--hair)}
.t-meta div:nth-child(odd){color:var(--soft);border-right:1px solid var(--hair)}
.t-meta div:nth-last-child(-n+2){border-bottom:none}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
code{font-family:ui-monospace,Menlo,monospace;font-size:.88em;background:#E4E8E4;padding:1px 5px;border-radius:2px}

.stabs{display:flex;flex-wrap:wrap;margin-top:22px;border:1.5px solid var(--ink);border-bottom:none;background:var(--panel)}
.stabs button{font:inherit;font-size:13.5px;padding:10px 16px;background:none;border:none;border-right:1px solid var(--rule);cursor:pointer;color:var(--soft);position:relative}
.stabs button[aria-selected=true]{background:var(--card);color:var(--ink);font-weight:700}
.stabs button[aria-selected=true]::after{content:"";position:absolute;left:0;right:0;bottom:-1.5px;height:3px;background:var(--ink)}
.stabs .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}

.screen{border:1.5px solid var(--ink);background:var(--card)}
.s-head{display:flex;gap:18px;flex-wrap:wrap;padding:12px 18px;border-bottom:1.5px solid var(--ink);background:var(--panel);font-size:13px}
.s-head b{font-size:16px;margin-right:6px}
.s-head span{color:var(--soft)}
.s-head span b{font-size:13px;color:var(--ink);font-weight:600;margin-right:4px}
.split{display:grid;grid-template-columns:minmax(560px,1.15fr) minmax(420px,1fr)}
.left{padding:18px;border-right:1.5px solid var(--ink);background:#F2F3F0;overflow:auto}
.right{padding:0;max-height:88vh;overflow-y:auto}

/* 뼈대 (와이어프레임) 스타일 — 원본 HTML은 스타일이 없고 여기서만 입힌다 */
.wf{font-family:system-ui,sans-serif;font-size:12.5px;color:#222;background:#f4f4f4;border:1px solid #bbb}
.wf [data-el]{position:relative;border:1.5px dashed #999;background:#fff;transition:background .12s,border-color .12s}
.wf [data-el]::before{content:attr(data-el);position:absolute;top:-8px;left:5px;font:600 9.5px/1 ui-monospace,monospace;background:#ffe58a;border:1px solid #c9a800;padding:2px 4px;border-radius:2px;z-index:2;cursor:pointer}
.wf [data-el].hi{background:var(--hi);border-color:var(--hi-b);border-style:solid}
.wf .lbl{color:#777;font-size:11px}
.wf .topbar{display:flex;align-items:center;gap:12px;padding:8px 12px;background:#e8e8e8;border-bottom:1px solid #bbb}
.wf .grow{flex:1}
.wf .badge{display:inline-block;background:#d33;color:#fff;font-size:10px;padding:0 5px;border-radius:8px}
.wf .btn{padding:3px 8px;border:1px solid #666;background:#fafafa;display:inline-block}
.wf .docbar{display:flex;align-items:center;gap:12px;padding:7px 12px;background:#f0f0f0;border-bottom:1px solid #bbb}
.wf .tabs span{padding:3px 8px;border:1px solid #999;margin-right:-1px}
.wf .tabs span.on{background:#fff;font-weight:600}
.wf .body3{display:grid;grid-template-columns:150px 1fr 220px;gap:10px;padding:10px}
.wf .toc{padding:8px;line-height:1.8;height:fit-content}
.wf .toc .d1{padding-left:12px}
.wf .main{padding:14px 16px;min-height:420px}
.wf .banner{padding:6px 10px;background:#fff3cd;border:1px solid #d9a800;margin-bottom:10px}
.wf .item{padding:5px 8px;margin:10px 0 4px;background:#f7f7f7;border-left:3px solid #666}
.wf .item .id{font:600 11px ui-monospace,monospace;color:#555;margin-right:6px}
.wf .flag{display:inline-block;font-size:10px;padding:0 6px;border:1px solid #d33;color:#d33;margin-left:6px;border-radius:2px}
.wf .ref{color:#1a5fb4;border-bottom:1px dashed #1a5fb4}
.wf .line{position:relative;padding-right:24px;margin:4px 0}
.wf .cbtn{position:absolute;right:0;top:0;width:18px;height:18px;border:1px solid #999;font-size:10px;text-align:center;line-height:16px;color:#777;background:#fff}
.wf .cbtn.has{border-color:#1a5fb4;color:#1a5fb4;font-weight:600}
.wf .diagram{margin:12px 0;padding:10px;background:#fafafa;border:1px solid #ccc;text-align:center}
.wf .diagram .img{height:110px;background:repeating-linear-gradient(45deg,#eee 0 10px,#f8f8f8 10px 20px);border:1px solid #ddd;display:flex;align-items:center;justify-content:center;color:#888}
.wf .diagram .acts{margin-top:6px;text-align:right}
.wf .nav{display:flex;justify-content:space-between;margin-top:20px;padding-top:10px;border-top:1px solid #ddd}
.wf .panel{height:fit-content}
.wf .ptabs{display:flex;border-bottom:1px solid #999}
.wf .ptabs span{flex:1;text-align:center;padding:6px;border-right:1px solid #999}
.wf .ptabs span:last-child{border-right:none}
.wf .ptabs span.on{background:#fff;font-weight:600}
.wf .pbody{padding:10px}
.wf .pbody h4{margin:8px 0 4px;font-size:11px;color:#666}
.wf .pbody ul{margin:0 0 8px;padding-left:14px;line-height:1.7}
.wf h2{font-size:15px;margin:6px 0 10px}
.wf .body2{display:grid;grid-template-columns:1fr 240px;gap:10px;padding:10px}
.wf .editor{display:grid;grid-template-columns:28px 1fr;min-height:300px;background:#fff}
.wf .gutter{display:flex;flex-direction:column;background:#f0f0f0;color:#999;font:11px/1.55 ui-monospace,monospace;text-align:right;padding:8px 4px}
.wf .gutter .err{color:#d33;font-weight:700}.wf .gutter .del{color:#c60;font-weight:700}
.wf .code{margin:0;padding:8px;font:11.5px/1.55 ui-monospace,monospace;white-space:pre-wrap}
.wf .errline{background:#ffe0e0;display:block}.wf .delline{background:#fff0e0;display:block;text-decoration:line-through}
.wf .chk{margin:0 0 8px;padding-left:16px;line-height:1.6}
.wf .chk .bad{color:#b00}.wf .chk .ok{color:#3a7}.wf .chk .warn{color:#a60}
.wf .btn.sm{font-size:10px;padding:1px 6px;margin-top:3px}
.wf .dialog{margin:12px;border:2px solid #444;background:#fff;box-shadow:0 4px 18px rgba(0,0,0,.18)}
.wf .dhead{padding:7px 12px;background:#444;color:#fff;font-weight:600}
.wf .dbody{padding:12px}
.wf .diffbox{margin:8px 0;padding:8px;background:#fafafa;border:1px solid #ddd;font:11px/1.6 ui-monospace,monospace}
.wf .dl{color:#b00}.wf .dl.add{color:#080}
.wf .dacts{text-align:right;margin-top:8px}
.wf .rawwrap{margin:10px;background:#fff}
.wf .phead{display:flex;align-items:center;gap:14px;padding:10px 12px;background:#f0f0f0;border-bottom:1px solid #bbb}
.wf .stats{display:flex;gap:8px;padding:8px 12px}
.wf .stat{padding:5px 10px;border:1px solid #999;background:#fff}
.wf .stat b{font-size:14px;margin-right:4px}
.wf table.stages{border-collapse:collapse;width:100%;background:#fff;font-size:12px}
.wf table.stages td{padding:5px 8px;border-bottom:1px solid #e5e5e5;vertical-align:middle}
.wf table.stages tr.stg td{background:#f7f7f7;font-weight:600}
.wf table.stages tr.doc td{padding-left:14px;font-weight:400;color:#333}
.wf table.stages td.no{width:24px;color:#999;text-align:right}
.wf .st{display:inline-block;padding:1px 7px;border-radius:2px;font-size:10.5px;font-weight:600}
.wf .st.ok{background:#d6f0d6;color:#1a6}.wf .st.rv{background:#fff0b3;color:#960}.wf .st.dr{background:#e8e8e8;color:#666}.wf .st.na{background:#fff;color:#bbb;border:1px dashed #ccc}
.wf .gate{font-size:10px;color:#c60;border:1px solid #c60;padding:0 5px;margin-left:4px}
.wf .cm{font-size:10px;color:#1a5fb4;border:1px solid #1a5fb4;padding:0 5px;margin-left:4px}
.wf .err{font-size:10px;color:#b00;border:1px solid #b00;padding:0 5px;margin-left:4px}
.wf .recent{margin:0;padding-left:14px;line-height:1.5}
.wf .recent li{margin-bottom:6px}
.wf .todo{padding:10px 12px}
.wf .grp{margin-bottom:12px;background:#fff}
.wf .grp.dim{opacity:.6}
.wf .grp h4{margin:0;padding:6px 10px;background:#f0f0f0;font-size:12px;border-bottom:1px solid #ccc}
.wf .cnt{display:inline-block;background:#666;color:#fff;font-size:10px;padding:0 6px;border-radius:8px;margin-left:6px}
.wf .row{display:flex;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid #eee;font-size:12px}
.wf .row .k{font:600 11px ui-monospace,monospace;color:#444}
.wf .age{font-size:11px;color:#c60;font-weight:600;white-space:nowrap}
.wf .empty{padding:24px;text-align:center;color:#999;border:1px dashed #ccc;background:#fafafa}
.wf .stack{padding:10px 12px;display:flex;flex-direction:column;gap:10px}
.wf .cause,.wf .mine{background:#fff}
.wf .sech{display:flex;align-items:center;gap:8px;padding:6px 10px;background:#f0f0f0;border-bottom:1px solid #ccc;font-size:12px}
.wf .mybody{padding:10px 12px;font-size:12px;line-height:1.6}
.wf .mybody p{margin:4px 0}
.wf .acts{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#f7f7f7;border:1px solid #ccc}
.wf .dialog.wide{margin:18px 30px}
.wf .dhead{display:flex;align-items:center;gap:10px}
.wf .dhead .lbl{color:#ddd}
.wf .x{cursor:pointer;padding:0 6px}
.wf .propacts{display:flex;align-items:flex-end;gap:10px;margin-top:12px}
.wf .skipbox{display:flex;flex-direction:column;gap:5px}
.wf .inp{border:1px solid #999;padding:4px 8px;font-size:11px;width:260px;background:#fff}
.wf .body2.hist{grid-template-columns:1fr 1fr}
.wf table.vers{border-collapse:collapse;width:100%;background:#fff;font-size:11.5px}
.wf table.vers th{text-align:left;padding:5px 8px;background:#f0f0f0;border-bottom:1px solid #ccc;font-weight:600}
.wf table.vers td{padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}
.wf table.vers tr.cur td{background:#fffbe6}
.wf .diffpane{background:#fff}
.wf .hint{font-size:10px;color:#1a5fb4;border:1px solid #1a5fb4;padding:0 5px;margin-left:6px}
.wf table.grid{border-collapse:collapse;width:calc(100% - 24px);margin:10px 12px;background:#fff;font-size:11.5px}
.wf table.grid th{padding:6px 5px;background:#f0f0f0;border-bottom:1px solid #ccc;font-weight:600;font-size:10.5px;text-align:center}
.wf table.grid th:nth-child(2){text-align:left}
.wf table.grid td{padding:7px 5px;border-bottom:1px solid #eee;text-align:center;vertical-align:middle}
.wf table.grid td:nth-child(2){text-align:left}
.wf .cell{display:inline-block;width:26px;height:22px;line-height:22px;border-radius:2px;font-size:10.5px;font-weight:600;position:relative}
.wf .cell.ok{background:#d6f0d6;color:#1a6}.wf .cell.rv{background:#fff0b3;color:#960}.wf .cell.dr{background:#e8e8e8;color:#666}.wf .cell.na{background:#fff;border:1px dashed #ddd}
.wf .cell i{position:absolute;top:-6px;right:-6px;font-style:normal;font-size:9px;color:#c60}
.wf .warn{color:#c60;font-size:14px}
.wf .login{max-width:360px;margin:60px auto;padding:30px;background:#fff;text-align:center}
.wf .logo{font-size:20px;margin-bottom:10px}
.wf .btn.big{display:block;padding:10px;margin:14px 0;font-size:13px}
.wf .form{padding:12px}
.wf .form label{display:block;font-size:11px;font-weight:600;margin:10px 0 3px}
.wf .inp.wide{width:100%}
.wf .ferr{color:#b00;font-size:11px;margin-top:3px}
.wf .facts{margin-top:14px;text-align:right}
.wf .banner.err{background:#ffe0e0;border-color:#b00;margin:0 12px}
.wf .banner.warn{background:#e8f0ff;border-color:#3a5ba0}
.wf .btn.on{background:#fff;font-weight:600}
.wf .graph{display:flex;gap:18px;padding:14px 12px;background:#fff;margin:10px 12px;min-height:200px;position:relative}
.wf .col{display:flex;flex-direction:column;gap:6px;min-width:120px}
.wf .colh{font-size:10px;font-weight:700;color:#888;text-align:center;border-bottom:1px solid #ddd;padding-bottom:3px}
.wf .node{font:10.5px ui-monospace,monospace;padding:4px 6px;border:1.5px solid #3a5ba0;border-radius:12px;background:#eef2fa;text-align:center}
.wf .node.sel{background:#fff6d9;border-color:#c9a800}
.wf .node.iso{background:#fff;border-style:dashed;border-color:#999;color:#777}
.wf .edges{position:absolute;bottom:6px;left:12px}
.wf .legend{padding:0 12px 10px;display:flex;gap:14px}
.wf .steps{display:flex;gap:3px}
.wf .stp{font-size:10px;padding:2px 6px;border:1px solid #bbb;background:#fff}
.wf .stp.done{background:#d6f0d6;border-color:#8c8}.wf .stp.cur{background:#fff0b3;border-color:#c9a800;font-weight:700}.wf .stp.na{color:#bbb;border-style:dashed}
.wf .readbody{padding:10px 12px}
.wf .row.dimrow{opacity:.5}
.wf .tokbox{font:12px ui-monospace,monospace;padding:8px;background:#f4f4f4;border:1px solid #ccc;margin:8px 0}
.wf .mono{font-family:ui-monospace,monospace;font-size:11px}
.wf table.uptbl{border-collapse:collapse;width:100%;font-size:11.5px;margin:8px 0}
.wf table.uptbl th{text-align:left;padding:4px 6px;background:#f0f0f0;border-bottom:1px solid #ccc}
.wf table.uptbl td{padding:5px 6px;border-bottom:1px solid #eee}
.wf .rawbar{display:flex;align-items:center;gap:10px;padding:6px 10px;background:#f0f0f0;border-bottom:1px solid #bbb}

/* 오른쪽 */
.rsec{padding:16px 20px;border-bottom:1px solid var(--hair)}
.rsec:last-child{border-bottom:none}
.rsec h3{margin:0 0 10px;font-size:13px;font-weight:700;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}
table.el{border-collapse:collapse;width:100%;font-size:12.5px}
table.el th{text-align:left;font-weight:600;color:var(--soft);padding:6px 8px;border-bottom:1.5px solid var(--ink);background:var(--panel)}
table.el td{padding:7px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
table.el tr{cursor:pointer}
table.el tr:hover td{background:#F2F4F1}
table.el tr.hi td{background:var(--hi)}
table.el td.no{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;white-space:nowrap;width:1%}
table.el td.kind{color:var(--soft);white-space:nowrap}
.rules{margin:0;padding-left:18px;font-size:13px;line-height:1.75}
.scen{margin-bottom:14px}
.scen .st{font-weight:700;font-size:13.5px}
.scen .st .k{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--faint);margin-right:6px}
.scen .uc{font-size:11.5px;color:var(--soft);margin-left:6px;font-weight:400}
.scen ol{margin:4px 0 0;padding-left:22px;font-size:13px;line-height:1.7}
.scen ol li span.eref{font-family:ui-monospace,Menlo,monospace;font-size:11px;background:#EEF0EC;padding:0 5px;border-radius:2px;cursor:pointer;border:1px solid var(--hair)}
.scen ol li span.eref:hover{border-color:var(--ink)}
footer{margin-top:22px;font-size:12.5px;color:var(--soft);max-width:80ch}
@media (max-width:1100px){.split{grid-template-columns:1fr}.left{border-right:none;border-bottom:1.5px solid var(--ink)}.right{max-height:none}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="t-main"><h1>싱크독 와이어프레임</h1>
  <p>왼쪽은 배치 뼈대, 오른쪽은 요소·규칙·시나리오. 노란 번호나 표의 행을 누르면 양쪽이 서로 강조된다. 디자인이 아니라 배치와 동작만 본다.</p></div>
  <div class="t-meta">
    <div>문서</div><div class="mono">SYNC-UI-002</div>
    <div>상태</div><div>__STATUS__</div>
    <div>상위</div><div class="mono">SYNC-UI-001</div>
    <div>작성</div><div>박호영 · 2026-09-07</div>
  </div>
</header>
<div class="stabs" id="stabs" role="tablist"></div>
<div id="screens"></div>
<footer>이 화면은 <code>와이어프레임_싱크독.md</code>에서 생성된 사람용 뷰다. 배치 HTML·요소 표·규칙·시나리오가 모두 원본에 있고, 여기서는 나란히 놓고 연동만 한다.</footer>
</div>
<script id="DATA" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById("DATA").textContent);
const esc=s=>(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/`(.+?)`/g,"<code>$1</code>");
/* 시나리오 문장 속 "(7.1)" 같은 요소 번호를 클릭 가능한 칩으로 */
const chip=s=>esc(s).replace(/\((\d+(?:\.\d+)?[a-z]?)\)/g,'(<span class="eref" data-ref="$1">$1</span>)');

const stabs=document.getElementById("stabs"), host=document.getElementById("screens");
D.forEach((s,i)=>{
  const b=document.createElement("button"); b.setAttribute("role","tab"); b.setAttribute("aria-selected",String(i===0));
  b.innerHTML=`<span class="k">${s.id}</span>${s.name}`; b.onclick=()=>show(i); stabs.appendChild(b);

  const sec=document.createElement("section"); sec.className="screen"; sec.style.display=i===0?"":"none"; sec.dataset.i=i;
  const meta=Object.entries(s.meta).map(([k,v])=>`<span><b>${esc(k)}</b>${esc(v).replace(/\[\[(.+?)\]\]/g,'<span class="mono">$1</span>')}</span>`).join("");
  const rows=s.elems.map(e=>`<tr data-el-row="${e.no}"><td class="no">${e.no}</td><td>${esc(e.name)}</td><td class="kind">${esc(e.kind)}</td><td>${esc(e.shows)}</td><td>${esc(e.onclick)}</td></tr>`).join("");
  const rules=s.rules.map(r=>`<li>${chip(r)}</li>`).join("");
  const scen=s.scenarios.map(sc=>`<div class="scen"><div class="st"><span class="k">${sc.id}</span>${esc(sc.title)}${sc.uc?`<span class="uc">— ${esc(sc.uc)}</span>`:""}</div><ol>${sc.steps.map(st=>`<li>${chip(st)}</li>`).join("")}</ol></div>`).join("");
  sec.innerHTML=`
    <div class="s-head"><b>${s.id} ${esc(s.name)}</b>${meta}</div>
    <div class="split">
      <div class="left"><div class="wf">${s.layout}</div></div>
      <div class="right">
        <div class="rsec"><h3>요소</h3><table class="el"><thead><tr><th>#</th><th>이름</th><th>종류</th><th>보여주는 것</th><th>누르면</th></tr></thead><tbody>${rows}</tbody></table></div>
        <div class="rsec"><h3>규칙</h3><ul class="rules">${rules}</ul></div>
        <div class="rsec"><h3>시나리오</h3>${scen}</div>
      </div>
    </div>`;
  host.appendChild(sec);

  /* 연동 */
  const hi=no=>{
    sec.querySelectorAll("[data-el],[data-el-row]").forEach(n=>n.classList.remove("hi"));
    const el=sec.querySelector(`[data-el="${no}"]`), row=sec.querySelector(`[data-el-row="${no}"]`);
    if(el){el.classList.add("hi");el.scrollIntoView({block:"nearest"});}
    if(row){row.classList.add("hi");row.scrollIntoView({block:"nearest"});}
  };
  sec.querySelectorAll("[data-el]").forEach(n=>n.addEventListener("click",e=>{e.stopPropagation();hi(n.dataset.el);}));
  sec.querySelectorAll("[data-el-row]").forEach(n=>n.addEventListener("click",()=>hi(n.dataset.elRow)));
  sec.querySelectorAll(".eref").forEach(n=>n.addEventListener("click",()=>hi(n.dataset.ref)));
});
function show(i){stabs.querySelectorAll("button").forEach((b,j)=>b.setAttribute("aria-selected",String(i===j)));host.querySelectorAll(":scope > section.screen").forEach((s,j)=>s.style.display=i===j?"":"none");}
</script>
</body>
</html>
"""
fmb = re.match(r"^---\n(.*?)\n---", raw, re.S).group(1)
status = {"draft":"초안","review":"검토중","approved":"승인"}[re.search(r"status: (\w+)", fmb).group(1)]
out = TPL.replace("__DATA__", json.dumps(screens, ensure_ascii=False)).replace("__STATUS__", html.escape(status))
open(OUT, "w", encoding="utf-8").write(out)
print("생성:", OUT, len(out), "바이트")
