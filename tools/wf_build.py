#!/usr/bin/env python3
"""화면 문서(UI) 원본 MD → 사람용 뷰 (STD-002 V-UI, 카드 X).

화면 문서는 하나여도 둘이어도 같은 규약으로 읽는다(STD-001 2.7).
  · 화면 항목 `UI-N`은 헤딩 단계와 무관하게 잡는다(`#`~`#####`). 코드블록 안은 보지 않는다
  · 화면 블록은 다음 「같은 단계 이상」 헤딩 전까지. 이어진 화면 항목은 한 묶음(탭) — 묶음 안 번호순,
    묶음 간 문서 순서
  · 화면마다 갈리는 것은 배치(```html 코드블록) 유무다. 있으면 좌 배치(iframe 격리) / 우 요소 표·규칙·시나리오.
    우측 셋이 다 비면 좌측 전폭. 없으면 「설계만 있는 화면」 — 잇따른 것끼리 표 한 장에 행 하나씩
  · 화면 아닌 절은 문서 순서 그대로 산문으로 그린다(화면 목록·공통 틀·화면 흐름·미결사항 …)
  · 배치는 iframe(srcdoc, allow-same-origin)에 넣는다 — 사이트 CSS가 안 스며든다. 「공통 틀」 절의 첫
    html 블록이 모든 화면 앞에 함께 들어간다. FRAME_CSS·SANDBOX는 frontend/src/view/frame.ts와 같아야
    한다(check_view_css.py가 대조)
frontend/src/view/wireframe.ts가 같은 규칙을 웹에서 그린다.

사용: wf_build.py <원본.md> [출력.html]   — 혼자 돌리면 페이지 틀까지 만든다.
      view_build.py는 parse_ui·render_ui만 가져다 쓴다.
"""
import html
import json
import os
import re
import sys

SCREEN = re.compile(r"^(#{1,6}) (UI-\d+)\b(?: (.*))?$", re.M)
HEAD = re.compile(r"^(#{1,6}) (.*)$", re.M)
SUB = re.compile(r"^#{1,6} (요소|규칙|시나리오)\s*$", re.M)
HTML_BLOCK = re.compile(r"```html\n(.*?)\n```", re.S)


SANDBOX = "allow-same-origin"

FRAME_CSS = r"""html,body{margin:0}
[data-el]{position:relative}
[data-el]::before{content:attr(data-el);position:absolute;top:-8px;left:5px;font:600 9.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;background:#ffe58a;border:1px solid #c9a800;color:#222;padding:2px 4px;border-radius:2px;z-index:2147483000;pointer-events:none}
[data-el].hi{outline:2px solid #c9a800;outline-offset:1px}
a{cursor:default}"""

COMMON_HEAD = re.compile(r"^#{1,6} (?:\d+(?:\.\d+)*\.?\s+)?공통 틀\s*$", re.M)
TYPE_STAGE = {"RFQ": 1, "PRD": 2, "SCN": 3, "UC": 4, "INFRA": 5, "DOM": 6, "UI": 7, "API": 8, "SEQ": 9, "MS": 10, "CODE": 11}


def safe_layout(layout):
    """배치 HTML을 iframe에 넣기 전에 다듬는다 — SYNC-STD-002 1장(#19, 카드 Z).

    문서가 넣은 동작은 지운다: `<script>`, `on*=`, `href/src`의 `javascript:`. iframe 안에서 또 iframe이
    열리거나 자동 이동이 일어나지 않게 `<iframe>`·`<object>`·`<embed>`·`<meta http-equiv>`도 지우고,
    `<form>`은 태그만 벗긴다(안의 배치는 남긴다). `data-el`은 그대로 둔다 — iframe이라 페이지의
    `data-el`과 다른 문서여서 셀렉터가 부딪히지 않는다.
    """
    layout = re.sub(r"<script\b[\s\S]*?</script\s*>", "", layout, flags=re.I)
    layout = re.sub(r"<(iframe|object)\b[\s\S]*?</\1\s*>", "", layout, flags=re.I)
    layout = re.sub(r"<(?:iframe|object|embed)\b[^>]*/?>", "", layout, flags=re.I)
    layout = re.sub(r"<meta\b[^>]*http-equiv[^>]*>", "", layout, flags=re.I)
    layout = re.sub(r"</?form\b[^>]*>", "", layout, flags=re.I)
    layout = re.sub(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", "", layout, flags=re.I)
    layout = re.sub(r"""\s(href|src)\s*=\s*(["']?)\s*javascript:[^"'>]*\2""", "", layout, flags=re.I)
    return layout


def split_common(common_html):
    """공통 틀 html → (head, body). `<link>`·`<style>`은 head로, 나머지 마크업은 body 앞으로."""
    head = "".join(re.findall(r"<link\b[^>]*>|<style\b[\s\S]*?</style\s*>", common_html, flags=re.I))
    body = re.sub(r"<link\b[^>]*>|<style\b[\s\S]*?</style\s*>", "", common_html, flags=re.I).strip()
    return head, body


def common_block(body):
    """「공통 틀」 절(번호 접두 허용, 헤딩 단계 무관)의 첫 ```html 블록. 없으면 ''.

    STD-001 2.7 — 이 블록은 그 문서 모든 화면의 iframe 앞에 함께 들어간다.
    """
    masked = mask_code(body)
    m = COMMON_HEAD.search(masked)
    if not m:
        return ""
    level = len(m.group(0)) - len(m.group(0).lstrip("#"))
    end = len(body)
    for h in HEAD.finditer(masked, m.end()):
        if len(h.group(1)) <= level:
            end = h.start()
            break
    lm = HTML_BLOCK.search(body, m.end(), end)
    return safe_layout(lm.group(1)) if lm else ""


def spec_dir(doc_id):
    """문서 ID → docs/specs 아래 폴더 이름 (`07-UI`, `STD`)."""
    typ = doc_id.split("-")[1] if "-" in doc_id else ""
    n = TYPE_STAGE.get(typ)
    return f"{n:02d}-{typ}" if n else typ


def base_for(doc_id):
    """정적 뷰(docs/views/)에서 문서 폴더 기준 상대 경로가 맞도록 하는 `<base href>`."""
    return f"../specs/{spec_dir(doc_id)}/"


def frame_html(layout, common, base):
    """배치 html → 격리된 iframe 조각 (STD-002 V-UI, 카드 Z).

    srcdoc 문서: `<base>`(문서 폴더) → 공통 틀의 `<link>`·`<style>` → 뷰의 FRAME_CSS(배지·강조만) →
    공통 틀 마크업 → 배치. sandbox에 allow-scripts가 없어 스크립트는 돌지 않는다 — 높이·강조·클릭은
    부모 문서가 contentDocument로 한다.
    """
    head, body = split_common(common or "")
    doc = (
        f'<!doctype html><html><head><meta charset="utf-8"><base href="{html.escape(base, quote=True)}">'
        f"{head}<style>{FRAME_CSS}</style></head><body>{body}{layout}</body></html>"
    )
    return (
        f'<div class="wfframe"><iframe class="wfframe-if" sandbox="{SANDBOX}" '
        f'srcdoc="{html.escape(doc, quote=True)}"></iframe></div>'
    )


def mask_code(text):
    """코드 펜스 안을 같은 길이의 공백으로 — 위치는 그대로, 헤딩·표만 안 보이게."""
    return re.sub(r"```.*?(?:```|\Z)", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(row):
    return all(set(c) <= set("-: ") for c in row)


def _table_rows(text):
    """첫 표의 행들 (구분선 제외). 없으면 []"""
    rows = []
    for line in text.split("\n"):
        if line.strip().startswith("|"):
            r = _cells(line)
            if not _is_sep(r):
                rows.append(r)
        elif rows:
            break
    return rows


def _sub(masked, name):
    """소제목 `^#{1,6} 요소` 뒤 ~ 다음 헤딩 앞. 없으면 ''"""
    for m in SUB.finditer(masked):
        if m.group(1) == name:
            nxt = HEAD.search(masked, m.end())
            return masked[m.end() : nxt.start() if nxt else len(masked)]
    return ""


def parse_screen(block, level):
    """화면 블록 하나 → dict. block은 헤딩 줄을 뺀 본문. frontend wireframe.ts와 같은 규칙."""
    masked = mask_code(block)
    lm = HTML_BLOCK.search(block)  # 배치 = 블록 안 첫 html 펜스
    head = masked[: lm.start()] if lm else masked
    first_head = HEAD.search(head)
    head = head[: first_head.start()] if first_head else head  # 소제목 전까지가 머리
    meta = [r[:2] for r in _table_rows(head)[1:] if len(r) >= 2]  # html 앞 첫 표
    desc = "\n".join(l for l in head.split("\n") if l.strip() and not l.strip().startswith("|"))
    rows = _table_rows(_sub(masked, "요소"))
    if rows and len(rows[0]) < 5:  # 요소 표는 5열부터
        rows = []
    rules = [l[2:].strip() for l in _sub(masked, "규칙").split("\n") if l.startswith("- ")]
    scenarios = []
    for chunk in re.split(r"\n(?=\*\*S-\d+)", _sub(masked, "시나리오").strip()):
        m = re.match(r"\*\*(S-\d+) (.+?)\*\*(?: — (.+))?\n", chunk + "\n")
        if not m:
            continue
        steps = [
            re.sub(r"^\d+\.\s*", "", l).strip()
            for l in chunk.split("\n")[1:]
            if re.match(r"^\d+\.", l.strip())
        ]
        scenarios.append({"id": m.group(1), "title": m.group(2), "uc": m.group(3) or "", "steps": steps})
    first = next((l.strip() for l in head.split("\n") if l.strip()), "")
    return {
        "level": level,
        "meta": meta,
        "desc": desc,
        "layout": safe_layout(lm.group(1)) if lm else None,
        "elems": {"header": rows[0] if rows else [], "rows": rows[1:]},
        "rules": rules,
        "scenarios": scenarios,
        "first": first,
    }


def parse_ui(body):
    """본문 → 블록 목록 [("prose", md) | ("group", [screen, …])] 문서 순서.

    화면 항목은 펜스 밖 어느 단계든 잡고, 블록은 같은 단계 이상 헤딩 전까지.
    이어진 화면 항목은 한 묶음(묶음 안 번호순, 묶음 간 문서 순서) — TBL처럼 `### 2.1` 아래 몇 개,
    `### 2.2` 아래 몇 개면 묶음이 여럿이다.
    """
    masked = mask_code(body)
    heads = list(SCREEN.finditer(masked))
    blocks, pos, group = [], 0, []

    def flush():
        if group:
            group.sort(key=lambda x: int(x["id"].split("-")[1]))
            blocks.append(("group", list(group)))
            group.clear()

    for m in heads:
        level = len(m.group(1))
        end = len(body)
        for h in HEAD.finditer(masked, m.end()):
            if len(h.group(1)) <= level:
                end = h.start()
                break
        gap = body[pos : m.start()]
        if gap.strip():
            flush()
            blocks.append(("prose", gap))
        sc = parse_screen(body[m.end() : end], level)
        sc["id"], sc["name"] = m.group(2), (m.group(3) or "").strip()
        group.append(sc)
        pos = end
    flush()
    if body[pos:].strip():
        blocks.append(("prose", body[pos:]))
    return blocks


# ───────────────────────── HTML ─────────────────────────

def _lib():
    """view_build의 공통 렌더러 — 늦게 가져온다(순환 import 방지)."""
    import view_build as vb
    return vb


def _chip(s, vb, sid):
    """문장 속 "(7.1)" 같은 요소 번호를 클릭 가능한 칩으로"""
    return re.sub(r"\((\d+(?:\.\d+)?[a-z]?)\)", r'(<span class="eref" data-ref="\1">\1</span>)', vb.inline(s, sid))


def _screen_html(sc, vb, sid, i, common, base):
    esc, inline = vb.esc, vb.inline
    meta = "".join(f"<span><b>{esc(k)}</b>{inline(v, sid)}</span>" for k, v in sc["meta"])
    desc = f'<div class="s-desc">{vb.render_blocks(sc["desc"], sid)}</div>' if sc["desc"] else ""
    right = []
    hdr, rows = sc["elems"]["header"], sc["elems"]["rows"]
    if rows:
        th = "".join(f"<th>{inline(c, sid)}</th>" for c in hdr)
        tb = "".join(
            f'<tr data-wf-row="{esc(r[0])}"><td class="no">{esc(r[0])}</td>'
            + "".join(f"<td>{inline(c, sid)}</td>" for c in r[1:])
            + "</tr>"
            for r in rows
        )
        right.append(
            f'<div class="rsec"><h3>요소</h3><table class="el"><thead><tr>{th}</tr></thead>'
            f"<tbody>{tb}</tbody></table></div>"
        )
    if sc["rules"]:
        right.append(
            '<div class="rsec"><h3>규칙</h3><ul class="rules">'
            + "".join(f"<li>{_chip(r, vb, sid)}</li>" for r in sc["rules"])
            + "</ul></div>"
        )
    if sc["scenarios"]:
        scen = "".join(
            f'<div class="scen"><div class="st"><span class="k">{esc(x["id"])}</span>{inline(x["title"], sid)}'
            + (f'<span class="uc">— {inline(x["uc"], sid)}</span>' if x["uc"] else "")
            + "</div><ol>"
            + "".join(f"<li>{_chip(st, vb, sid)}</li>" for st in x["steps"])
            + "</ol></div>"
            for x in sc["scenarios"]
        )
        right.append(f'<div class="rsec"><h3>시나리오</h3>{scen}</div>')
    if right:
        body = (
            f'<div class="split"><div class="left">{frame_html(sc["layout"], common, base)}</div>'
            f'<div class="right">{"".join(right)}</div></div>'
        )
    else:  # 우측 셋이 다 비면 좌측 전폭
        body = f'<div class="split full"><div class="left">{frame_html(sc["layout"], common, base)}</div></div>'
    hidden = "" if i == 0 else ' style="display:none"'
    return (
        f'<section class="screen" id="item-{esc(sc["id"])}" data-item="{esc(sc["id"])}" data-i="{i}"{hidden}>'
        f'<div class="s-head"><b>{esc(sc["id"])} {esc(sc["name"])}</b>{meta}</div>{desc}{body}</section>'
    )


def _design_table(screens, vb, sid):
    """배치가 없는 화면들 — 표 한 장에 행 하나씩 (옛 화면 설계 뷰의 재조립 표)."""
    rows = ""
    for sc in screens:
        first = sc["first"]
        kind = first.split(".")[0] if "." in first else ""
        uc = re.search(r"주 유스케이스: (.+)$", first)
        goal = first.split(". ", 1)[1].split(" 주 유스케이스")[0] if ". " in first else first
        downs = sorted(d for d, v in vb.downstream_of(sid).items() if sc["id"] in v)
        links = " · ".join(f'<a class="ref" href="{vb.view_href(d)}">{d}</a>' for d in downs)
        rows += (
            f'<tr id="item-{vb.esc(sc["id"])}"><td class="iid">{vb.esc(sc["id"])}</td>'
            f'<td>{vb.inline(sc["name"], sid)}</td><td>{vb.esc(kind)}</td><td>{vb.inline(goal, sid)}</td>'
            f'<td>{vb.inline(uc.group(1), sid) if uc else ""}</td><td>{links}</td></tr>'
        )
    return (
        '<table class="reassembled"><thead><tr><th>#</th><th>화면</th><th>종류</th><th>목적</th>'
        f"<th>주 유스케이스</th><th>참조한 곳</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _group_html(screens, vb, sid, common, base):
    """묶음 하나: 배치 없는 화면은 표, 배치 있는 화면은 탭 + 화면들."""
    out = []
    plain = [s for s in screens if s["layout"] is None]
    if plain:
        out.append(_design_table(plain, vb, sid))
    wired = [s for s in screens if s["layout"] is not None]
    if wired:
        tabs = "".join(
            f'<button type="button" role="tab" aria-selected="{"true" if i == 0 else "false"}" data-i="{i}">'
            f'<span class="k">{vb.esc(s["id"])}</span>{vb.esc(s["name"])}</button>'
            for i, s in enumerate(wired)
        )
        shown = "".join(_screen_html(s, vb, sid, i, common, base) for i, s in enumerate(wired))
        out.append(f'<div class="stabs" role="tablist">{tabs}</div><div class="screens">{shown}</div>')
    return f'<div class="wfgroup">{"".join(out)}</div>'


def render_ui(blocks, sid, common="", base=""):
    """블록 목록 → 본문 HTML (문서 순서). 페이지 틀·CSS·JS는 밖에서.

    common = 공통 틀 절의 첫 html 블록(common_block), base = 문서 폴더 `<base href>`.
    공통 틀은 화면에만 앞선다 — 산문 자리의 html 블록은 render_blocks가 공통 틀 없이 iframe으로.
    """
    vb = _lib()
    out = []
    for kind, b in blocks:
        if kind == "prose":
            out.append(f'<div class="prose">{vb.render_blocks(b, sid)}</div>')
        else:
            out.append(_group_html(b, vb, sid, common, base))
    return "\n".join(out)


WF_JS = r"""
(function(){
  const root=document.currentScript.parentElement;
  // 배치는 iframe(srcdoc, allow-same-origin)에 격리돼 있다 — 높이·축소·강조·클릭은 전부 여기(부모)가 한다.
  const frames=()=>[...root.querySelectorAll('iframe.wfframe-if')];
  const docOf=f=>{try{return f.contentDocument;}catch(e){return null;}};
  const fit=f=>{
    const d=docOf(f); if(!d||!d.documentElement) return;
    const wrap=f.parentElement, avail=wrap.clientWidth;
    if(!avail) return;
    f.style.width='100%'; f.style.transform=''; wrap.style.height='';
    const de=d.documentElement, first=d.body&&d.body.firstElementChild;
    let h=Math.max(de.scrollHeight, first?first.getBoundingClientRect().bottom+de.scrollTop:0);
    const w=de.scrollWidth;
    const big=w>avail+1, shrink=big&&f.dataset.orig!=='1';
    if(big){f.style.width=w+'px';}
    if(shrink){const k=avail/w; f.style.transformOrigin='0 0'; f.style.transform=`scale(${k})`; wrap.style.height=Math.ceil(h*k)+'px';}
    else if(big){wrap.style.overflowX='auto';}
    if(f.dataset.h!==String(h)){f.dataset.h=String(h); f.style.height=h+'px';}
    let b=wrap.querySelector('.orig');
    if(big&&!b){b=document.createElement('button');b.type='button';b.className='orig';wrap.appendChild(b);b.addEventListener('click',()=>{f.dataset.orig=f.dataset.orig==='1'?'0':'1';fit(f);});}
    if(b){b.textContent=f.dataset.orig==='1'?'맞춤':'원래 크기';b.style.display=big?'':'none';}
  };
  const secOf=f=>f.closest('section.screen');
  const hi=(sec,no)=>{
    const f=sec.querySelector('iframe.wfframe-if'), d=f&&docOf(f);
    if(d) d.querySelectorAll('[data-el].hi').forEach(n=>n.classList.remove('hi'));
    sec.querySelectorAll('[data-wf-row].hi').forEach(n=>n.classList.remove('hi'));
    const el=d&&d.querySelector(`[data-el="${CSS.escape(no)}"]`), row=sec.querySelector(`[data-wf-row="${CSS.escape(no)}"]`);
    if(el){el.classList.add('hi'); const left=f.closest('.left'); if(left){const k=parseFloat((f.style.transform.match(/scale\(([\d.]+)\)/)||[])[1]||'1'); left.scrollTop=Math.max(0,el.getBoundingClientRect().top*k+f.offsetTop-40);}}
    if(row){row.classList.add('hi');row.scrollIntoView({block:'nearest'});}
  };
  const wire=f=>{
    const d=docOf(f); if(!d||f.dataset.wired) return; f.dataset.wired='1';
    try{new ResizeObserver(()=>fit(f)).observe(d.documentElement);}catch(e){}
    fit(f);
    d.addEventListener('click',e=>{
      const a=e.target.closest&&e.target.closest('a[href]'); if(a) e.preventDefault();
      const el=e.target.closest&&e.target.closest('[data-el]'); const sec=secOf(f);
      if(el&&sec){e.stopPropagation();hi(sec,el.getAttribute('data-el'));}
    });
  };
  frames().forEach(f=>{const d=docOf(f); if(d&&d.readyState==='complete'&&d.body) wire(f); f.addEventListener('load',()=>wire(f));});
  root.querySelectorAll('section.screen').forEach(sec=>{
    sec.querySelectorAll('[data-wf-row]').forEach(n=>n.addEventListener('click',()=>hi(sec,n.dataset.wfRow)));
    sec.querySelectorAll('.eref').forEach(n=>n.addEventListener('click',()=>hi(sec,n.dataset.ref)));
  });
  root.querySelectorAll('.wfgroup').forEach(g=>{
    const tabs=[...g.querySelectorAll('.stabs button')], secs=[...g.querySelectorAll(':scope > .screens > section.screen')];
    tabs.forEach((b,i)=>b.addEventListener('click',()=>{
      tabs.forEach((x,j)=>x.setAttribute('aria-selected',String(i===j)));
      secs.forEach((s,j)=>s.style.display=i===j?'':'none');
      secs[i]&&secs[i].querySelectorAll('iframe.wfframe-if').forEach(fit);
    }));
  });
  window.addEventListener('resize',()=>frames().forEach(fit));
})();
"""

WF_CSS = r"""
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
.split.full{grid-template-columns:1fr}
.split.full .left{border-right:none}
.left{padding:18px;border-right:1.5px solid var(--ink);background:#F2F3F0;overflow:auto}
/* 배치는 iframe에 격리 — 사이트 CSS가 스며들지 않는다 (STD-002 V-UI, 카드 Z) */
.wfframe{position:relative;background:#fff;border:1px solid #bbb;overflow:hidden}
.wfframe-if{display:block;border:0;width:100%;min-height:40px}
.wfframe .orig{position:absolute;top:6px;right:6px;font:600 11px/1 ui-monospace,Menlo,monospace;padding:4px 7px;background:#fff;border:1px solid var(--ink);cursor:pointer;z-index:3;opacity:.85}
.wfframe .orig:hover{opacity:1}
.right{padding:0;max-height:88vh;overflow-y:auto}


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

/* 화면 아닌 절 — 문서 순서대로 */
.prose{padding:6px 2px 14px}
.prose h2{font-size:18px;margin:26px 0 8px;padding-bottom:6px;border-bottom:1.5px solid var(--ink)}
.prose h3{font-size:15px;margin:18px 0 6px}
.prose h4,.prose h5{font-size:13.5px;margin:14px 0 4px}
.prose p{margin:6px 0;max-width:80ch}
.prose ul,.prose ol{margin:4px 0 8px;padding-left:22px;line-height:1.7}
.prose table{border-collapse:collapse;font-size:12.5px;margin:8px 0}
.prose th{text-align:left;padding:5px 8px;border-bottom:1.5px solid var(--ink);background:var(--panel)}
.prose td{padding:5px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
.prose .mer{margin:10px 0}
.prose a.ref{color:#1a5fb4}.prose a.ref.missing{color:#b00;border-bottom:1px dashed #b00}
.screen{margin-top:14px}
.s-desc{padding:8px 18px;border-bottom:1px solid var(--hair);font-size:13px;color:var(--soft)}
.s-desc p{margin:2px 0}
table.reassembled{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0 14px;background:var(--card);border:1.5px solid var(--ink)}
table.reassembled th{text-align:left;padding:6px 8px;border-bottom:1.5px solid var(--ink);background:var(--panel);font-weight:600}
table.reassembled td{padding:6px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
table.reassembled td.iid{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;white-space:nowrap}
"""


def _selftest():
    """safe_layout이 지워야 할 것을 지우는지 — iframe에 allow-scripts가 없어도 이것이 첫 방어다.

    사용: wf_build.py --selftest
    """
    cases = [
        ('<div><script >alert(1)</script ></div>', "<script"),
        ('<p><SCRIPT src="x"></SCRIPT></p>', "SCRIPT"),
        ('<a href="#" onclick = "x()">a</a>', "onclick"),
        ('<a href=" javascript:alert(1)">a</a>', "javascript"),
        ('<div><iframe src="x"></iframe></div>', "<iframe"),
        ('<form action="/x"><input></form>', "<form"),
        ('<meta http-equiv="refresh" content="0;url=x">', "http-equiv"),
        ('<object data="x"><p>y</p></object>', "<object"),
    ]
    bad = [(src, tok) for src, tok in cases if tok.lower() in safe_layout(src).lower()]
    kept = safe_layout('<form><div data-el="1" style="color:red">x</div></form>')
    if 'data-el="1"' not in kept or "style=" not in kept or "<div" not in kept:
        bad.append((kept, "keep"))
    for src, tok in bad:
        print("✗ ", tok, "남음:", src)
    print("safe_layout: 통과" if not bad else f"safe_layout: {len(bad)} 실패")
    return 0 if not bad else 1


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs", "07-UI", "SYNC-UI-002.md")
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_wf.html"
    raw = open(src, encoding="utf-8").read()
    fmm = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in fmm.group(1).split("\n"))} if fmm else {}
    body = raw[fmm.end():] if fmm else raw
    sid = fm.get("doc_id", "?")
    blocks = parse_ui(body)
    common = common_block(body)
    groups = [b for k, b in blocks if k == "group"]
    screens = [s for g in groups for s in g]
    masked = mask_code(body)
    nonscreen = sum(1 for h in re.finditer(r"^## (.*)$", masked, re.M) if not SCREEN.match(h.group(0)))
    print(f"묶음 {len(groups)} · 화면 {len(screens)}개:", [s["id"] for s in screens], f"· 비화면 절 {nonscreen}")
    for s in screens:
        print(f"  {s['id']} 배치 {'있음' if s['layout'] is not None else '없음'} 요소 {len(s['elems']['rows'])} 규칙 {len(s['rules'])} 시나리오 {len(s['scenarios'])}")
    status = {"draft": "초안", "approved": "완료"}.get(fm.get("status", ""), fm.get("status", ""))
    page = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(fm.get("title", sid))}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{WF_CSS}</style></head><body><div class="wrap">
<header><div class="t-main"><h1>{html.escape(fm.get("title", sid))}</h1>
<p>화면마다 왼쪽은 배치 뼈대, 오른쪽은 요소·규칙·시나리오. 노란 번호나 표의 행을 누르면 양쪽이 서로 강조된다. 배치가 없는 화면은 표 한 행이다. 이어진 화면은 한 묶음이고 탭으로 오간다.</p></div>
<div class="t-meta"><div>문서</div><div class="mono">{html.escape(sid)}</div><div>상태</div><div>{html.escape(status)}</div>
<div>상위</div><div class="mono">{html.escape(fm.get("upstream", ""))}</div></div></header>
<div id="ui">{render_ui(blocks, sid, common, base_for(sid))}<script>{WF_JS}</script></div>
<footer>이 화면은 <code>{html.escape(os.path.basename(src))}</code>에서 생성된 사람용 뷰다. 배치 HTML·요소 표·규칙·시나리오가 모두 원본에 있고, 여기서는 나란히 놓고 연동만 한다.</footer>
</div></body></html>"""
    open(out, "w", encoding="utf-8").write(page)
    print("생성:", out, len(page), "바이트")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(_selftest()) if "--selftest" in sys.argv else main()
