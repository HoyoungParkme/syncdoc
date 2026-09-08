import os
#!/usr/bin/env python3
"""data.json으로 사람용 뷰(HTML)를 생성한다. 다이어그램은 패키지별, 표기는 UML 표준."""
import json, re

data = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json"), encoding="utf-8"))

HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>싱크독 유스케이스 명세</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{
  --paper:#EDEFEC; --panel:#F8F9F7; --card:#fff;
  --ink:#1E2A30; --soft:#5C6B73; --faint:#8A969C;
  --rule:#C9CFCB; --hair:#E1E5E1;
  --agent:#12776A; --human:#3A5BA0; --github:#6B4A9E; --system:#8A6D1F;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0; background:var(--paper); color:var(--ink);
  font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo",system-ui,sans-serif;
  font-feature-settings:"tnum"; -webkit-font-smoothing:antialiased; font-size:15px; line-height:1.65}
code,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
code{font-size:.88em; background:#E4E8E4; padding:1px 5px; border-radius:2px}
.wrap{max-width:1340px; margin:0 auto; padding:36px 26px 90px}

header{border:1.5px solid var(--ink); background:var(--panel); display:grid; grid-template-columns:1fr auto}
.t-main{padding:24px 28px 22px; border-right:1.5px solid var(--ink)}
.t-main h1{margin:0; font-size:30px; font-weight:700; letter-spacing:-.02em}
.t-main p{margin:10px 0 0; color:var(--soft); max-width:60ch; font-size:14.5px}
.t-meta{display:grid; grid-template-columns:auto auto; align-content:start; font-size:12.5px}
.t-meta div{padding:9px 16px; border-bottom:1px solid var(--hair)}
.t-meta div:nth-child(odd){color:var(--soft); border-right:1px solid var(--hair)}
.t-meta div:nth-last-child(-n+2){border-bottom:none}

h2{font-size:19px; font-weight:700; margin:44px 0 8px; letter-spacing:-.01em}
h2 .n{color:var(--faint); font-weight:500; margin-right:9px}
.lead{margin:0 0 16px; color:var(--soft); font-size:14px; max-width:76ch}

.tabs{display:flex; flex-wrap:wrap; border:1.5px solid var(--ink); border-bottom:none; background:var(--panel)}
.tabs button{font:inherit; font-size:14px; padding:11px 18px; background:none; border:none;
  border-right:1px solid var(--rule); cursor:pointer; color:var(--soft); position:relative}
.tabs button:last-child{border-right:none}
.tabs button[aria-selected="true"]{background:var(--card); color:var(--ink); font-weight:700}
.tabs button[aria-selected="true"]::after{content:""; position:absolute; left:0; right:0; bottom:-1.5px; height:3px; background:var(--ink)}
.tabs button:focus-visible{outline:2px solid var(--ink); outline-offset:-4px}
.tabs .cnt{color:var(--faint); font-size:12px; margin-left:6px; font-weight:400}
.canvas{border:1.5px solid var(--ink); background:var(--card); overflow-x:auto}
svg{display:block}

.uc-el{fill:#fff; stroke-width:1.6; transition:fill .12s}
.uc-el.abstract{stroke-dasharray:6 4; fill:var(--panel)}
.uc-t{font-size:12.5px; fill:var(--ink); text-anchor:middle; pointer-events:none}
.uc-k{font-size:10px; font-family:ui-monospace,Menlo,monospace; fill:var(--faint); text-anchor:middle; pointer-events:none}
.uc-xp{font-size:9.5px; fill:var(--soft); text-anchor:middle; pointer-events:none}
.uc-xp-h{font-size:9px; fill:var(--faint); text-anchor:middle; font-weight:600; pointer-events:none}
g.uc{cursor:pointer}
g.uc:hover .uc-el{fill:#F0F4F0}
g.uc.sel .uc-el{fill:#FFF6D9; stroke-width:2.6}
.assoc{stroke-width:1.2; fill:none}
.dep{stroke-dasharray:6 4; stroke-width:1.2; fill:none}
.gen{stroke-width:1.2; fill:none}
.stereo{font-size:10px; fill:var(--soft); font-style:italic; text-anchor:middle}
.a-name{font-size:13px; font-weight:600; text-anchor:middle}
.a-sub{font-size:10.5px; fill:var(--soft); text-anchor:middle}
.ext-only{font-size:11px; fill:var(--faint); font-style:italic}

.key{display:flex; flex-wrap:wrap; gap:20px; margin-top:10px; font-size:12.5px; color:var(--soft); align-items:center}
.key span{display:inline-flex; align-items:center; gap:7px}
.key svg{display:inline-block}

.spec{display:grid; grid-template-columns:250px 1fr; border:1.5px solid var(--ink); background:var(--card)}
.nav{border-right:1.5px solid var(--ink); background:var(--panel); max-height:78vh; overflow-y:auto}
.nav-grp{padding:13px 16px 5px; font-size:11.5px; font-weight:700; color:var(--soft); position:sticky; top:0; background:var(--panel)}
.nav a{display:block; padding:7px 16px; text-decoration:none; color:var(--ink); font-size:13.5px;
  border-left:3px solid transparent; line-height:1.4}
.nav a:hover{background:#EAEEEA}
.nav a.sel{border-left-color:currentColor; background:#fff; font-weight:600}
.nav a .k{font-family:ui-monospace,Menlo,monospace; font-size:11px; color:var(--faint); margin-right:7px}
.nav a.sel .k{color:inherit}
.detail{padding:28px 32px 34px; max-height:78vh; overflow-y:auto}
.d-head{display:flex; align-items:baseline; gap:11px; flex-wrap:wrap; margin-bottom:4px}
.d-id{font-family:ui-monospace,Menlo,monospace; font-size:14px; padding:2px 9px; border:1.5px solid currentColor}
.d-name{font-size:23px; font-weight:700; letter-spacing:-.02em; margin:0}
.d-links{font-size:12.5px; color:var(--soft); margin:0 0 20px}
table.attrs{border-collapse:collapse; width:100%; margin-bottom:26px; font-size:14px}
table.attrs th{text-align:left; vertical-align:top; width:158px; font-weight:600; color:var(--soft);
  padding:9px 14px 9px 0; border-bottom:1px solid var(--hair); white-space:nowrap}
table.attrs td{vertical-align:top; padding:9px 0; border-bottom:1px solid var(--hair)}
table.attrs tr:last-child th,table.attrs tr:last-child td{border-bottom:none}
table.attrs tr.rel th{background:#F4F7F3; padding-left:10px}
table.attrs tr.rel td{background:#F4F7F3; padding-right:10px}
.lv{display:inline-block; font-size:12px; padding:1px 9px; border:1px solid var(--rule); background:var(--panel)}
.sec-t{font-size:13px; font-weight:700; margin:0 0 11px; padding-bottom:7px; border-bottom:1.5px solid var(--ink)}
ol.flow{margin:0 0 26px; padding-left:0; list-style:none; counter-reset:f}
ol.flow li{counter-increment:f; position:relative; padding:6px 0 6px 38px; border-bottom:1px solid var(--hair)}
ol.flow li:last-child{border-bottom:none}
ol.flow li::before{content:counter(f); position:absolute; left:0; top:6px;
  font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--faint); width:24px; text-align:right}
.ext{margin-bottom:24px}
.ext-item{border-left:2.5px solid var(--rule); padding:2px 0 2px 15px; margin-bottom:14px}
.ext-on{font-weight:600; font-size:14px}
.ext-on .br{font-family:ui-monospace,Menlo,monospace; font-size:12.5px; color:var(--soft); margin-right:7px}
.ext-item ul{margin:5px 0 0; padding-left:17px; color:var(--soft); font-size:14px}
.note{background:var(--panel); border-left:2.5px solid var(--rule); padding:11px 15px; font-size:13.5px; color:var(--soft)}
.jump{cursor:pointer; border-bottom:1px dashed currentColor}

table.matrix{border-collapse:collapse; width:100%; font-size:13.5px; background:var(--card); border:1.5px solid var(--ink)}
table.matrix th,table.matrix td{padding:9px 13px; border-bottom:1px solid var(--hair); text-align:left; vertical-align:top}
table.matrix thead th{background:var(--panel); font-weight:700; border-bottom:1.5px solid var(--ink)}
table.matrix tr:last-child td{border-bottom:none}
table.matrix td:first-child{white-space:nowrap; font-weight:600; width:1%}
.chip{display:inline-block; font-family:ui-monospace,Menlo,monospace; font-size:11.5px;
  padding:1px 7px; margin:2px 3px 2px 0; border:1px solid var(--rule); background:var(--panel); cursor:pointer}
.chip:hover{border-color:var(--ink)}
footer{margin-top:34px; font-size:13px; color:var(--soft); max-width:80ch}
@media (max-width:900px){
  .spec{grid-template-columns:1fr}
  .nav{border-right:none; border-bottom:1.5px solid var(--ink); max-height:220px}
  .detail{max-height:none}
  header{grid-template-columns:1fr}
  .t-main{border-right:none; border-bottom:1.5px solid var(--ink)}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important; scroll-behavior:auto}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="t-main">
    <h1>싱크독 유스케이스 명세</h1>
    <p>유스케이스 30개. 목록은 액터로 묶고 다이어그램은 패키지로 나눈다. 액터는 유스케이스를 발견하는 축, 패키지는 발견된 것을 정리하는 축이다.</p>
  </div>
  <div class="t-meta">
    <div>문서</div><div class="mono">SYNC-UC-001</div>
    <div>상태</div><div>__STATUS__</div>
    <div>상위</div><div class="mono">SYNC-PRD-001</div>
    <div>작성</div><div>박호영 · 2026-09-06</div>
  </div>
</header>

<h2><span class="n">1</span>다이어그램</h2>
<p class="lead">패키지로 나눈 이유는 <code>UC-A6 → UC-S1~S5</code>처럼 액터 경계를 넘는 관계가 액터별로 자르면 두 장에 걸쳐 끊기기 때문이다. 타원을 누르면 아래에 전체 명세가 열린다.</p>
<div class="tabs" id="tabs" role="tablist"></div>
<div class="canvas"><svg id="dg" xmlns="http://www.w3.org/2000/svg"></svg></div>
<div class="key">
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#5C6B73" stroke-width="1.2"/></svg>연결</span>
  <span><svg width="34" height="10"><line x1="0" y1="5" x2="27" y2="5" stroke="#5C6B73" stroke-width="1.2" stroke-dasharray="6 4"/><path d="M27,1 L34,5 L27,9" fill="none" stroke="#5C6B73" stroke-width="1.2"/></svg>«include» / «extend»</span>
  <span><svg width="34" height="12"><line x1="0" y1="6" x2="24" y2="6" stroke="#5C6B73" stroke-width="1.2"/><path d="M24,1 L34,6 L24,11 Z" fill="#fff" stroke="#5C6B73" stroke-width="1.2"/></svg>일반화</span>
  <span><svg width="30" height="14"><ellipse cx="15" cy="7" rx="13" ry="6" fill="#F8F9F7" stroke="#5C6B73" stroke-width="1.4" stroke-dasharray="6 4"/></svg>추상 유스케이스</span>
</div>

<h2><span class="n">2</span>명세</h2>
<div class="spec" id="spec">
  <nav class="nav" id="nav" aria-label="유스케이스 목록"></nav>
  <article class="detail" id="detail" aria-live="polite"></article>
</div>

<h2><span class="n">3</span>추적표</h2>
<table class="matrix" id="mx1"></table>
<div style="height:18px"></div>
<table class="matrix" id="mx2"></table>

<footer>
  이 화면은 <code>USECASE_싱크독.md</code>에서 생성된 사람용 뷰다. 직접 고칠 수 없으며, 고치려면 원본 MD를 고쳐야 한다.
  다이어그램의 관계선은 원본 표의 <code>포함(include)</code>·<code>확장점</code>·<code>일반화</code> 항목에서 그려진다.
</footer>
</div>

<script id="DATA" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById("DATA").textContent);
const ACT={agent:{label:"에이전트",sub:"Claude Code · Codex · Gemini",hex:"#12776A"},
  human:{label:"사람",sub:"박호영 · 김민준",hex:"#3A5BA0"},
  github:{label:"GitHub",sub:"코드 저장소",hex:"#6B4A9E"},
  system:{label:"하위기능",sub:"저장 후 자동 실행",hex:"#8A6D1F"}};
const UCMAP=Object.fromEntries(D.ucs.map(u=>[u.id,u]));
const PKGS=["명세 조회","명세 작성","변경 추적","검토·확정","연동·표현"];
const md=s=>(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/&lt;br&gt;/g,"<br>").replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>")
  .replace(/`(.+?)`/g,"<code>$1</code>");
const linkUC=s=>md(s).replace(/(UC-[AHGS]\d+)/g,'<span class="jump" data-jump="$1">$1</span>');

const svg=document.getElementById("dg"), NS="http://www.w3.org/2000/svg";
const el=(t,a={})=>{const n=document.createElementNS(NS,t);for(const k in a)n.setAttribute(k,a[k]);return n;};
const RX=94, RY=30;
const parseIds=s=>(!s||s==="—")?[]:(s.match(/UC-[AHGS]\d+/g)||[]);
function edgePt(cx,cy,tx,ty,ry){
  const a=Math.atan2((ty-cy)*RX,(tx-cx)*(ry||RY));
  return [cx+RX*Math.cos(a), cy+(ry||RY)*Math.sin(a)];
}
function wrap(text,max){
  const words=text.split(" "); const lines=[]; let cur="";
  for(const w of words){ if((cur+" "+w).trim().length>max){if(cur.trim())lines.push(cur.trim());cur=w;} else cur+=" "+w; }
  if(cur.trim())lines.push(cur.trim());
  return lines.length?lines:[text];
}
function buildDefs(){
  const defs=el("defs");
  const m=el("marker",{id:"open",viewBox:"0 0 10 10",refX:"9.5",refY:"5",
    markerWidth:"9",markerHeight:"9",orient:"auto-start-reverse"});
  m.appendChild(el("path",{d:"M0,0 L10,5 L0,10",fill:"none",stroke:"#5C6B73","stroke-width":"1.3"}));
  defs.appendChild(m);
  const g=el("marker",{id:"tri",viewBox:"0 0 12 12",refX:"11",refY:"6",
    markerWidth:"13",markerHeight:"13",orient:"auto-start-reverse"});
  g.appendChild(el("path",{d:"M0,0.5 L11,6 L0,11.5 Z",fill:"#fff",stroke:"#5C6B73","stroke-width":"1.2"}));
  defs.appendChild(g);
  return defs;
}

let curPkg=PKGS[0], curId=null;

function drawPackage(pkg){
  svg.innerHTML=""; svg.appendChild(buildDefs());
  const ucs=D.ucs.filter(u=>u.package===pkg);
  const inPkg=new Set(ucs.map(u=>u.id));
  const outside=[];
  ucs.forEach(u=>[...parseIds(u.include),...parseIds(u.extPoint)].forEach(id=>{
    if(!inPkg.has(id)&&!outside.includes(id))outside.push(id);}));
  const abstracts=[...new Set(ucs.map(u=>(u.general||"").match(/UC-[AHGS]\d+/)?.[0]).filter(Boolean))];

  const actors=[...new Set(ucs.map(u=>u.actor))].filter(a=>a!=="system");
  const main=ucs.filter(u=>u.actor!=="system");
  const sub=ucs.filter(u=>u.actor==="system");
  const rowH=88, colMid=530, colRight=890;
  const P={}, RYs={};
  const ryOf=u=>(u&&u.extPoint&&u.extPoint!=="—")?RY+16:RY;
  main.forEach((u,i)=>{P[u.id]={x:colMid,y:110+i*rowH}; RYs[u.id]=ryOf(u);});
  let ry=110+main.length*rowH;
  abstracts.forEach((id,i)=>{P[id]={x:colMid,y:ry+i*rowH,abstract:true}; RYs[id]=RY;});
  const rightAll=[...sub.map(u=>u.id),...outside];
  rightAll.forEach((id,i)=>{P[id]={x:colRight,y:110+i*82,outside:!inPkg.has(id)}; RYs[id]=ryOf(UCMAP[id]);});

  const maxY=Math.max(...Object.values(P).map(p=>p.y),260)+100;
  const W=1150;
  svg.setAttribute("viewBox",`0 0 ${W} ${maxY}`);
  svg.setAttribute("style",`min-width:${W}px;height:${maxY}px`);

  svg.appendChild(el("rect",{x:300,y:56,width:790,height:maxY-100,fill:"none",stroke:"#1E2A30","stroke-width":"1.5"}));
  let t=el("text",{x:316,y:79,"font-size":"13.5","font-weight":"600",fill:"#1E2A30"});
  t.textContent="싱크독 · "+pkg; svg.appendChild(t);

  const anchors={};
  actors.forEach((k,i)=>{
    const a=ACT[k], x=155, y=150+i*(maxY>420?190:150), s={stroke:a.hex,"stroke-width":1.8,fill:"none"};
    const g=el("g");
    g.appendChild(el("circle",{cx:x,cy:y,r:10,...s,fill:"#fff"}));
    g.appendChild(el("line",{x1:x,y1:y+10,x2:x,y2:y+36,...s}));
    g.appendChild(el("line",{x1:x-16,y1:y+19,x2:x+16,y2:y+19,...s}));
    g.appendChild(el("line",{x1:x,y1:y+36,x2:x-13,y2:y+55,...s}));
    g.appendChild(el("line",{x1:x,y1:y+36,x2:x+13,y2:y+55,...s}));
    let n=el("text",{x,y:y+74,class:"a-name",fill:a.hex}); n.textContent=a.label; g.appendChild(n);
    n=el("text",{x,y:y+89,class:"a-sub"}); n.textContent=a.sub; g.appendChild(n);
    svg.appendChild(g); anchors[k]={x,y:y+22};
  });

  main.forEach(u=>{
    const a=anchors[u.actor], p=P[u.id]; if(!a)return;
    const [ex,ey]=edgePt(p.x,p.y,a.x,a.y,RYs[u.id]);
    svg.appendChild(el("line",{x1:a.x,y1:a.y,x2:ex,y2:ey,class:"assoc",stroke:ACT[u.actor].hex}));
  });

  function dep(from,to,label){
    const f=P[from], g=P[to]; if(!f||!g)return;
    const [sx,sy]=edgePt(f.x,f.y,g.x,g.y,RYs[from]), [tx,ty]=edgePt(g.x,g.y,f.x,f.y,RYs[to]);
    svg.appendChild(el("line",{x1:sx,y1:sy,x2:tx,y2:ty,class:"dep",stroke:"#5C6B73","marker-end":"url(#open)"}));
    const l=el("text",{x:(sx+tx)/2,y:(sy+ty)/2-6,class:"stereo"}); l.textContent=label; svg.appendChild(l);
  }
  ucs.forEach(u=>{
    parseIds(u.include).forEach(id=>dep(u.id,id,"«include»"));
    parseIds(u.extPoint).forEach(id=>dep(u.id,id,"«extend»"));
    const gi=(u.general||"").match(/UC-[AHGS]\d+/)?.[0];
    if(gi&&P[gi]){
      const f=P[u.id],g=P[gi];
      const [sx,sy]=edgePt(f.x,f.y,g.x,g.y,RYs[u.id]),[tx,ty]=edgePt(g.x,g.y,f.x,f.y,RYs[gi]);
      svg.appendChild(el("line",{x1:sx,y1:sy,x2:tx,y2:ty,class:"gen",stroke:"#5C6B73","marker-end":"url(#tri)"}));
    }
  });

  Object.entries(P).forEach(([id,p])=>{
    const u=UCMAP[id], isAbs=!!p.abstract, isOut=!!p.outside;
    const name=u?u.name:"명세를 조회한다";
    const color=u?ACT[u.actor].hex:"#5C6B73";
    const xp=u&&u.extPoint&&u.extPoint!=="—";
    const g=el("g",{class:"uc",...(u?{"data-uc":id,tabindex:"0",role:"button","aria-label":id+" "+name}:{})});
    g.appendChild(el("ellipse",{cx:p.x,cy:p.y,rx:RX,ry:RYs[id],class:"uc-el"+(isAbs?" abstract":""),
      stroke:color,...(isOut?{"stroke-dasharray":"3 3"}:{})}));
    let n=el("text",{x:p.x,y:p.y-(xp?18:13),class:"uc-k"});
    n.textContent=isAbs?"추상":id.replace("UC-",""); g.appendChild(n);
    const lines=wrap(name,13);
    lines.forEach((ln,i)=>{
      const y=p.y+(xp?-1:5)+i*15-(lines.length-1)*7;
      const tn=el("text",{x:p.x,y,class:"uc-t"}); tn.textContent=ln; g.appendChild(tn);
    });
    if(xp){
      let h=el("text",{x:p.x,y:p.y+24,class:"uc-xp-h"}); h.textContent="Extension Points"; g.appendChild(h);
      const cond=(u.extPoint.match(/`(.+?)`/)||[])[1]||"";
      let c=el("text",{x:p.x,y:p.y+36,class:"uc-xp"}); c.textContent=cond; g.appendChild(c);
    }
    if(u){
      g.addEventListener("click",()=>select(id,false));
      g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select(id,false);}});
    }
    svg.appendChild(g);
  });

  if(outside.length){
    const n=el("text",{x:colRight,y:maxY-46,class:"ext-only","text-anchor":"middle"});
    n.textContent="점선 타원은 다른 패키지의 유스케이스"; svg.appendChild(n);
  }
  refreshSel();
}

const tabs=document.getElementById("tabs");
PKGS.forEach((p,i)=>{
  const b=document.createElement("button");
  b.type="button"; b.setAttribute("role","tab"); b.dataset.pkg=p;
  b.setAttribute("aria-selected",String(i===0));
  b.innerHTML=p+`<span class="cnt">${D.ucs.filter(u=>u.package===p).length}</span>`;
  b.onclick=()=>{curPkg=p; tabs.querySelectorAll("button").forEach(x=>
    x.setAttribute("aria-selected",String(x.dataset.pkg===p))); drawPackage(p);};
  tabs.appendChild(b);
});

const nav=document.getElementById("nav");
["agent","human","github","system"].forEach(k=>{
  const list=D.ucs.filter(u=>u.actor===k);
  const h=document.createElement("div");
  h.className="nav-grp"; h.style.color=ACT[k].hex; h.textContent=ACT[k].label+" · "+list.length;
  nav.appendChild(h);
  list.forEach(u=>{
    const a=document.createElement("a");
    a.href="#"; a.dataset.uc=u.id; a.style.color=ACT[k].hex;
    a.innerHTML=`<span class="k">${u.short}</span><span style="color:var(--ink)">${u.name}</span>`;
    a.onclick=e=>{e.preventDefault(); select(u.id,false);};
    nav.appendChild(a);
  });
});

const detail=document.getElementById("detail");
function render(u){
  const c=ACT[u.actor].hex;
  const base=[["범위",md(u.scope)],["수준",`<span class="lv">${md(u.level)}</span>`],
    ["주 액터",md(u.primary)],["이해관계자와 관심사",md(u.stakeholders)],
    ["사전조건",md(u.pre)],["최소 보장",md(u.minGuarantee)],
    ["성공 보장",md(u.successGuarantee)],["트리거",md(u.trigger)]]
    .map(([k,v])=>`<tr><th>${k}</th><td>${v}</td></tr>`).join("");
  const rel=[["패키지",md(u.package)],["포함(include)",linkUC(u.include)],
    ["확장점",linkUC(u.extPoint)],["일반화",linkUC(u.general)]]
    .map(([k,v])=>`<tr class="rel"><th>${k}</th><td>${v}</td></tr>`).join("");
  const flow=u.flow.map(s=>`<li>${linkUC(s)}</li>`).join("");
  const ext=u.ext.map(e=>{
    const m=e.on.match(/^(\d+[a-z])\.\s*(.+)$/), br=m?m[1]:"", ti=m?m[2]:e.on;
    const steps=e.steps.map(s=>`<li>${linkUC(s)}</li>`).join("");
    return `<div class="ext-item" style="border-left-color:${c}">
      <div class="ext-on"><span class="br">${br}</span>${md(ti)}</div>
      ${steps?`<ul>${steps}</ul>`:""}</div>`;}).join("");
  detail.innerHTML=`
    <div class="d-head" style="color:${c}">
      <span class="d-id">${u.id}</span>
      <h3 class="d-name" style="color:var(--ink)">${u.name}</h3></div>
    <p class="d-links">연관 요구사항·시나리오 &nbsp;<span class="mono">${md(u.links)}</span></p>
    <table class="attrs">${base}${rel}</table>
    <p class="sec-t">기본 흐름</p><ol class="flow">${flow}</ol>
    <p class="sec-t">확장</p><div class="ext">${ext}</div>
    ${u.note?`<p class="sec-t">사후조건 참고</p><div class="note">${linkUC(u.note)}</div>`:""}`;
  detail.querySelectorAll("[data-jump]").forEach(j=>j.onclick=()=>select(j.dataset.jump,false));
}
function refreshSel(){
  svg.querySelectorAll("g.uc").forEach(g=>g.classList.toggle("sel",g.dataset.uc===curId));
}
function select(id,scroll){
  const u=UCMAP[id]; if(!u)return;
  curId=id; render(u);
  nav.querySelectorAll("a").forEach(a=>a.classList.toggle("sel",a.dataset.uc===id));
  const s=nav.querySelector("a.sel"); if(s)s.scrollIntoView({block:"nearest"});
  if(u.package!==curPkg){
    curPkg=u.package;
    tabs.querySelectorAll("button").forEach(x=>x.setAttribute("aria-selected",String(x.dataset.pkg===curPkg)));
    drawPackage(curPkg);
  } else refreshSel();
  if(scroll)document.getElementById("spec").scrollIntoView({block:"start"});
}

function matrix(elm,head,rows){
  const chips=s=>s.split(",").map(x=>{const k=x.trim();
    return UCMAP["UC-"+k]?`<span class="chip" data-jump="UC-${k}">${k}</span>`:`<span class="chip">${k}</span>`;}).join("");
  elm.innerHTML=`<thead><tr><th>${head[0]}</th><th>${head[1]}</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td>${r[0]}</td><td>${chips(r[1])}</td></tr>`).join("")+`</tbody>`;
  elm.querySelectorAll("[data-jump]").forEach(c=>c.onclick=()=>select(c.dataset.jump,true));
}
matrix(document.getElementById("mx1"),["시나리오","유스케이스"],D.scenarioMap);
matrix(document.getElementById("mx2"),["요구사항","유스케이스"],D.reqMap);

drawPackage(curPkg);
select(D.ucs.find(u=>u.package===curPkg).id,false);
</script>
</body>
</html>
"""

raw = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs") + "/UC/SYNC-UC-001.md", encoding="utf-8").read()
fmb = re.match(r"^---\n(.*?)\n---", raw, re.S).group(1)
status = {"draft":"초안","review":"검토중","approved":"승인"}[re.search(r"status: (\w+)", fmb).group(1)]
out = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__STATUS__", status)
open("/tmp/_uc.html", "w", encoding="utf-8").write(out)
print("생성:", len(out), "바이트")
