---
doc_id: 
type: UI
title: 
status: draft
upstream: []
---

# 화면 설계·와이어프레임 — {프로젝트}

<!-- 템플릿. [[SYNC-STD-001]] 2.7의 UI 구조. doc_id는 서버가 채운다. 필수 절은 「미결사항」 하나 — 없으면 미완성 경고 -->
<!-- title에 「화면 설계」「와이어프레임」 중 하나가 들어가야 한다(없으면 위반). 둘 다 넣기를 권장 — 검사기 둘이 각각 다른 키워드로 이 문서를 찾는다 -->
<!-- 화면 설계와 와이어프레임을 한 문서에 써도 되고 둘로 나눠도 된다. 규약은 같다 -->
<!-- 만드는 법: 에이전트가 가진 디자인 도구(클로드 디자인 스킬, GPT·Gemini의 디자인 기능 등)로 화면을 만들고, 스타일까지 든 자기 완결 html(<style>·<link> 포함)을 아래 배치 블록에 그대로 넣는다. 뷰가 iframe으로 격리해 그리므로 모양이 그대로 보인다. 클로드 디자인 캔버스면 아트보드의 <x-dc> 안 html과 <helmet> 안 <style>을 꺼내 넣는다. 권장 1280×800 -->
<!-- 이미지·폰트 파일은 docs/specs/assets/ 에 두고 이 문서 폴더 기준 상대 경로(../assets/x.png)로 쓴다 -->
<!-- 커밋·PR에 에이전트 표시(Co-Authored-By·세션 링크·Generated with)를 남기지 않는다 — 규약 1.10 -->

## 0. 이 문서가 다루는 것

…

## 1. 유스케이스 대응

| 유스케이스 | 화면 |
|---|---|
| [[XXXX-UC-001#UC-H1]] | UI-1 |

## 2. 화면 목록

| 화면 | 경로 | 한 줄 목적 |
|---|---|---|
| UI-1 첫 화면 | `/` | … |

<!-- 화면마다 절 하나. 헤딩 단계는 자유(##~#####)지만 화면 헤딩이 그 안 소제목보다 상위여야 한다 -->

## UI-1 첫 화면

| 항목 | 내용 |
|---|---|
| 경로 | `/` |
| 주 유스케이스 | [[XXXX-UC-001#UC-H1]] |
| 진입 / 이탈 | … / … |

<!-- 배치는 필수. html 코드블록 하나 — 디자인 도구가 만든 자기 완결 html을 그대로. data-el 번호는 요소 표와 이으려면 붙인다 -->
### 배치
```html
<style>
  .hb{font-family:system-ui,sans-serif;padding:24px;background:#fbfaf6;color:#1d1c19}
  .hb h1{margin:0 0 12px;font-size:22px}
</style>
<div class="hb" data-el="1">
  <h1 data-el="1.1">첫 화면</h1>
  <button data-el="2">시작</button>
</div>
```

<!-- 아래 셋은 있으면 쓴다. 없어도 막지 않는다 -->
### 요소
| # | 이름 | 종류 | 보여주는 것 | 누르면 |
|---|---|---|---|---|
| 1 | … | … | … | … |

### 규칙
- …

### 시나리오
**S-1 …** — [[XXXX-UC-001#UC-H1]]
1. …

## 3. 공통 틀

<!-- 이 절의 첫 html 블록은 모든 화면 앞에 함께 들어간다 — 공통 <style>·<link>(폰트)·공통 부품. 없어도 된다 -->
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500&display=swap">
<style>
  body{font-family:"IBM Plex Sans KR",system-ui,sans-serif}
</style>
```

## 4. 화면 흐름

```mermaid
flowchart LR
    UI1[UI-1] --> UI2[UI-2]
```

## 5. 미결사항

- [ ] …
