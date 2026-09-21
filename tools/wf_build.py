#!/usr/bin/env python3
"""화면 문서(UI) 원본 MD → 사람용 뷰 (STD-002 V-UI, 카드 X).

화면 문서는 하나여도 둘이어도 같은 규약으로 읽는다(STD-001 2.7).
  · 화면 항목 `UI-N`은 헤딩 단계와 무관하게 잡는다(`#`~`#####`). 코드블록 안은 보지 않는다
  · 화면 블록은 다음 「같은 단계 이상」 헤딩 전까지. 이어진 화면 항목은 한 묶음(탭) — 묶음 안 번호순,
    묶음 간 문서 순서
  · 화면마다 갈리는 것은 배치(```html 코드블록) 유무다. 있으면 좌 배치 뼈대 / 우 요소 표·규칙·시나리오.
    우측 셋이 다 비면 좌측 전폭. 없으면 「설계만 있는 화면」 — 잇따른 것끼리 표 한 장에 행 하나씩
  · 화면 아닌 절은 문서 순서 그대로 산문으로 그린다(화면 목록·공통 틀·화면 흐름·미결사항 …)
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


def safe_layout(layout):
    """배치 HTML을 페이지에 넣기 전에 다듬는다 — SYNC-STD-002 6장(#19).

    `<script>`·`on*=`·`javascript:`는 지우고, `data-el`은 `data-wf`로 바꾼다.
    바꾸는 이유: 그대로 두면 문서 본문에서 나온 것과 화면 자신의 요소를 셀렉터로 구분할 수 없다.
    """
    layout = re.sub(r"<script\b[\s\S]*?</script\s*>", "", layout, flags=re.I)
    layout = re.sub(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", "", layout, flags=re.I)
    layout = re.sub(r"""\s(href|src)\s*=\s*(["']?)\s*javascript:[^"'>]*\2""", "", layout, flags=re.I)
    return re.sub(r"\bdata-el(-row)?=", r"data-wf\1=", layout)


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


def _screen_html(sc, vb, sid, i):
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
            f'<div class="split"><div class="left"><div class="wf">{sc["layout"]}</div></div>'
            f'<div class="right">{"".join(right)}</div></div>'
        )
    else:  # 우측 셋이 다 비면 좌측 전폭
        body = f'<div class="split full"><div class="left"><div class="wf">{sc["layout"]}</div></div></div>'
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


def _group_html(screens, vb, sid):
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
        shown = "".join(_screen_html(s, vb, sid, i) for i, s in enumerate(wired))
        out.append(f'<div class="stabs" role="tablist">{tabs}</div><div class="screens">{shown}</div>')
    return f'<div class="wfgroup">{"".join(out)}</div>'


def render_ui(blocks, sid):
    """블록 목록 → 본문 HTML (문서 순서). 페이지 틀·CSS·JS는 밖에서."""
    vb = _lib()
    out = []
    for kind, b in blocks:
        if kind == "prose":
            out.append(f'<div class="prose">{vb.render_blocks(b, sid)}</div>')
        else:
            out.append(_group_html(b, vb, sid))
    return "\n".join(out)


WF_JS = r"""
(function(){
  const root=document.currentScript.parentElement;
  root.querySelectorAll('section.screen').forEach(sec=>{
    const hi=no=>{
      sec.querySelectorAll('[data-wf],[data-wf-row]').forEach(n=>n.classList.remove('hi'));
      const el=sec.querySelector(`[data-wf="${no}"]`), row=sec.querySelector(`[data-wf-row="${no}"]`);
      if(el){el.classList.add('hi');el.scrollIntoView({block:'nearest'});}
      if(row){row.classList.add('hi');row.scrollIntoView({block:'nearest'});}
    };
    sec.querySelectorAll('[data-wf]').forEach(n=>n.addEventListener('click',e=>{e.stopPropagation();hi(n.dataset.wf);}));
    sec.querySelectorAll('[data-wf-row]').forEach(n=>n.addEventListener('click',()=>hi(n.dataset.wfRow)));
    sec.querySelectorAll('.eref').forEach(n=>n.addEventListener('click',()=>hi(n.dataset.ref)));
  });
  root.querySelectorAll('.wfgroup').forEach(g=>{
    const tabs=[...g.querySelectorAll('.stabs button')], secs=[...g.querySelectorAll(':scope > .screens > section.screen')];
    tabs.forEach((b,i)=>b.addEventListener('click',()=>{
      tabs.forEach((x,j)=>x.setAttribute('aria-selected',String(i===j)));
      secs.forEach((s,j)=>s.style.display=i===j?'':'none');
    }));
  });
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
.right{padding:0;max-height:88vh;overflow-y:auto}

/* 뼈대 (와이어프레임) 스타일 — 원본 HTML은 스타일이 없고 여기서만 입힌다 */
.wf{font-family:system-ui,sans-serif;font-size:12.5px;color:#222;background:#f4f4f4;border:1px solid #bbb}
.wf [data-wf]{position:relative;border:1.5px dashed #999;background:#fff;transition:background .12s,border-color .12s}
.wf [data-wf]::before{content:attr(data-wf);position:absolute;top:-8px;left:5px;font:600 9.5px/1 ui-monospace,monospace;background:#ffe58a;border:1px solid #c9a800;padding:2px 4px;border-radius:2px;z-index:2;cursor:pointer}
.wf [data-wf].hi{background:var(--hi);border-color:var(--hi-b);border-style:solid}
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
.wf .st.ok{background:#d6f0d6;color:#1a6}.wf .st.dr{background:#e8e8e8;color:#666}.wf .st.na{background:#fff;color:#bbb;border:1px dashed #ccc}
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
.wf .cell.ok{background:#d6f0d6;color:#1a6}.wf .cell.dr{background:#e8e8e8;color:#666}.wf .cell.na{background:#fff;border:1px dashed #ddd}
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
.wfgroup{margin-bottom:22px}
table.reassembled{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0 14px;background:var(--card);border:1.5px solid var(--ink)}
table.reassembled th{text-align:left;padding:6px 8px;border-bottom:1.5px solid var(--ink);background:var(--panel);font-weight:600}
table.reassembled td{padding:6px 8px;border-bottom:1px solid var(--hair);vertical-align:top}
table.reassembled td.iid{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;white-space:nowrap}
"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "specs", "07-UI", "SYNC-UI-002.md")
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/_wf.html"
    raw = open(src, encoding="utf-8").read()
    fmm = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    fm = {k.strip(): v.strip() for k, v in (l.partition(":")[::2] for l in fmm.group(1).split("\n"))} if fmm else {}
    body = raw[fmm.end():] if fmm else raw
    sid = fm.get("doc_id", "?")
    blocks = parse_ui(body)
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
<div id="ui">{render_ui(blocks, sid)}<script>{WF_JS}</script></div>
<footer>이 화면은 <code>{html.escape(os.path.basename(src))}</code>에서 생성된 사람용 뷰다. 배치 HTML·요소 표·규칙·시나리오가 모두 원본에 있고, 여기서는 나란히 놓고 연동만 한다.</footer>
</div></body></html>"""
    open(out, "w", encoding="utf-8").write(page)
    print("생성:", out, len(page), "바이트")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
