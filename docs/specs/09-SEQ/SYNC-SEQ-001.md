---
doc_id: SYNC-SEQ-001
type: SEQ
title: SEQUENCE — 싱크독
status: draft
upstream: [SYNC-DOM-002, SYNC-API-001, SYNC-API-002, SYNC-UC-001]
---

# SEQUENCE: 싱크독 (SyncDoc)

---

## 0. 이 문서가 다루는 것

유스케이스 흐름을 **객체 수준**으로 내린다. 누가 누굴 어떤 순서로 부르고, 어디서 갈라지는지. 생명선은 클래스 명세 4장의 서비스와 인프라 4.1의 구성 요소다.

**1장 대응표의 입구 전부(REST 37 엔드포인트 + MCP 도구)를 다룬다.** v1.0에서는 "단순 조회는 안 그린다"고 했으나, 그려보니 단순해 보이던 조회가 묶음을 넘는 호출을 숨기고 있었다(`get_document`의 미존재 참조, 프로젝트 목록의 건수). 시퀀스는 그런 걸 잡으려고 그리는 것이므로 빠뜨리면 안 된다.

**v2에서 협업 장치를 걷어냈다.** 전파·플래그·댓글·내 할 일·백업의 시퀀스(SEQ-3·6·16·17)는 은퇴했고 번호는 비워 둔다. 남은 것 중 그 장치를 부르던 단계는 지웠다.

**두 종류로 나눈다.**
- **고유 흐름** SEQ-1·2·4·5·7~15·18~24 — 분기가 있거나 묶음을 넘는 것. 각자 그림
- **공통 형태** SEQ-C1·C2·C3 — 정말로 `입구 → 서비스 하나 → DB → 반환`인 것과 모든 요청 앞에 붙는 인증. 그림 하나에 표로 어느 입구가 따르는지. **그려서 확인한 뒤에** 넣었다

**표기** — `alt` 분기, `opt` 조건부, `loop` 반복. 실선 호출, 점선 반환. `DB`는 어느 묶음이든 자기 테이블. 트랜잭션은 `rect`. `Q`는 `core/queries.py` — 읽기 집계 조합자(되먹일 것 #12).

### 0.1 생명선

다이어그램에 나오는 것이 실제로 무엇인지. 약어는 다이어그램 안 표기.

| 생명선 | 약어 | 실체 | 종류 | 정의한 곳 |
|---|---|---|---|---|
| 사람 | U | 브라우저를 쓰는 팀원 | 액터 | USECASE 1장 |
| 에이전트 | A | Claude Code·Codex·Gemini | 액터 | USECASE 1장 |
| GitHub | GH | 원격 저장소 | 액터 | USECASE 1장 |
| routers/* | RP·RD·RR·RT·RC·RA | `web/routers/*.py` 함수 | Boundary | 클래스 3.1, API REST |
| web/hooks | H | `web/hooks.py` | Boundary | 인프라 4.1 |
| mcp/tools | T | `mcp/tools.py` | Boundary | 클래스 3.1, API MCP |
| mcp 서버 | M | MCP 전송·인증 계층 | Boundary | 인프라 5 |
| pipeline | P | `core/pipeline.py` — 쓰기 조율 | Control | 클래스 4.7 |
| queries | Q | `core/queries.py` — 읽기 조합 | Control | 되먹일 것 #12 |
| ProjectService | PS | `core/project/service.py` | Control | 클래스 4.1 |
| SpecService | S | `core/spec/service.py` | Control | 클래스 4.2 |
| ReferenceService | R | `core/reference/service.py` | Control | 클래스 4.3 |
| AccountService | AS·AC | `core/account/service.py` | Control | 클래스 4.4 |
| infra/git | G | `infra/git.py` — clone·commit·push·fetch | 어댑터 | 인프라 4.3 |
| infra/github | GHI | `infra/github.py` — OAuth·webhook 검증 | 어댑터 | 인프라 5 |
| infra/llm | LLM | `infra/llm.py` — 모델 호출 | 어댑터 | 인프라 5.3 |
| DB | DB | PostgreSQL. 어느 묶음이든 자기 테이블 | 저장소 | ERD·DD |
| 입구 (공통) | B | 라우터 또는 mcp/tools — 흐름이 웹·MCP 공통일 때 | Boundary | 클래스 3.1 |
| 서비스 (공통) | SV | 네 서비스 중 하나 — SEQ-C1의 표가 지정 | Control | 클래스 4장 |

---

## 1. 대응표 — 입구 → 시퀀스

| 입구 | 시퀀스 | 묶음 넘음 |
|---|---|---|
| GET /auth/github (인터넷판) | [[#SEQ-C1]] | |
| GET /auth/github/callback (인터넷판) | [[#SEQ-8]] | |
| POST /auth/logout (인터넷판) | [[#SEQ-C1]] | |
| POST /hooks/github (인터넷판) | [[#SEQ-2]] | ○ |
| 폐쇄망판 모든 웹 요청의 가드·사용자 | [[#SEQ-C3]] | |
| GET /specs/{path} | [[#SEQ-C1]] | |
| GET /api/projects | [[#SEQ-9]] | ○ |
| POST /api/projects · MCP init_project | [[#SEQ-4]] (GitHub 저장) · [[#SEQ-28]] (서버 저장) | ○ |
| GET /api/projects/{code} | [[#SEQ-9]] | ○ |
| GET /api/projects/{code}/docs · MCP list_documents | [[#SEQ-10]] | ○ |
| GET /api/projects/{code}/flags | [[#SEQ-18]] | ○ |
| GET /api/projects/{code}/graph | [[#SEQ-14]] | ○ |
| GET /api/docs/{docId} · MCP get_document | [[#SEQ-11]] | ○ |
| MCP get_item · GET /api/docs/{docId}/items/{itemId} | [[#SEQ-12]] | ○ |
| GET …/items/{itemId}/references · MCP get_references | [[#SEQ-13]] | ○ |
| POST /api/docs/{docId}/status | [[#SEQ-5]] | ○ |
| GET /api/docs/{docId}/versions | [[#SEQ-C1]] | |
| GET /api/docs/{docId}/diff | [[#SEQ-15]] | ○ |
| POST /api/docs/{docId}/revert | [[#SEQ-7]] | ○ |
| DELETE /api/docs/{docId} | [[#SEQ-22]] | ○ |
| POST /api/docs/{docId}/restore | [[#SEQ-23]] | ○ |
| POST /api/docs/{docId}/purge | [[#SEQ-22]] 끝 | ○ |
| GET /api/projects/{code}/trash | [[#SEQ-C1]] | |
| GET /api/me | [[#SEQ-C1]] | |
| GET · POST /api/me/tokens · DELETE …/{id} | [[#SEQ-C1]] | |
| GET /api/admin/repos | [[#SEQ-20]] | |
| POST /api/admin/repos/{code}/rebuild | [[#SEQ-21]] | ○ |
| POST /api/admin/repos/{code}/sync | [[#SEQ-25]] | ○ |
| POST /api/admin/repos/{code}/hook | [[#SEQ-4]] | |
| POST /api/admin/repos/{code}/move-to-server | [[#SEQ-33]] | ○ |
| POST /api/docs/{docId}/ask | [[#SEQ-24]] | ○ |
| POST /api/projects/{code}/code/ask | [[#SEQ-32]] | ○ |
| MCP create_document | [[#SEQ-19]] | ○ |
| MCP update_document | [[#SEQ-1]] | ○ |
| MCP delete_document | [[#SEQ-22]] | ○ |
| MCP restore_document | [[#SEQ-23]] | ○ |
| MCP change_status | [[#SEQ-5]] | ○ |
| MCP 모든 도구의 인증 | [[#SEQ-C2]] | |
| (커밋 처리·재구축 뒤) 코드 그래프 | [[#SEQ-26]] | ○ |
| GET /api/docs/{docId}/code · …/items/{itemId}/code · …/items/{itemId}/code/source | [[#SEQ-27]] | ○ |
| GET /api/projects/{code}/code-calls | [[#SEQ-27]] | ○ |
| MCP get_code_graph | [[#SEQ-27]] | ○ |
| GET·POST /git/{code}.git/* (서버 저장소 git 입구) | [[#SEQ-29]] | ○ |
| MCP upload_code | [[#SEQ-30]] | ○ |
| GET /api/projects/{code}/code-graph | [[#SEQ-31]] | ○ |
| GET /api/projects/{code}/code/source | [[#SEQ-31]] | ○ |

묶음을 넘는 것이 대응표 41행 중 29행이다(입구 여럿을 한 행에 묶은 것이 있다). v1.0에서 안 그린 조회 중 절반 이상이 묶음을 넘었다.

---

## SEQ-1 에이전트가 문서를 수정한다

[[SYNC-UC-001#UC-A6]] 기본 흐름 1~8, 확장 2a·4a·4b·5a·6a. MCP `update_document`.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트
    participant T as mcp/tools
    participant AC as AccountService
    participant P as pipeline
    participant S as SpecService
    participant R as ReferenceService
    participant G as infra/git
    participant DB

    A->>T: update_document(doc_id, body, expected_version, message, changed_items, confirm)
    T->>AC: authenticate_token(bearer)
    AC-->>T: User
    T->>P: save_pipeline(entry=mcp, doc_id, body, expected_version, author, confirm)

    P->>P: repo lock 획득
    P->>S: get_document(doc_id)
    S-->>P: Document (doc_type, current_version_no, current_body)
    P->>S: validate(body, doc_type)
    S->>DB: items where is_deleted (재사용 검사)
    S-->>P: violations[]
    alt violations 있음 (2a)
        P-->>T: convention-violation {violations}
        T-->>A: isError
    end

    alt expected_version != current_version_no (4a)
        P-->>T: version-conflict {current_version, current_body}
        T-->>A: isError
    end

    P->>S: detect_deleted_items(document, body)
    S-->>P: deleted_item_pks[]
    opt deleted 있음
        P->>R: downstream(item_pk) ×N
        R-->>P: refs[]
        alt downstream 있고 confirm=false (4b)
            P-->>T: item-deletion-needs-confirm {deleted_items}
            T-->>A: isError
        end
    end

    P->>G: commit_push(repo, path, body, "spec(doc_id): …", author)
    G->>AC: github_token_for(author.user)
    opt document.status == approved (6a)
        P->>P: body 의 `status:` 를 draft 로 — **push 전에** frontmatter를 맞춘다 (#47)
    end
    AC-->>G: token
    G->>G: write · commit · push
    alt push 거부
        G->>G: fetch · rebase · push 재시도
        alt 재시도 실패 (5a)
            G-->>P: PushFailed
            P-->>T: push-failed {reason}
            T-->>A: isError
        end
    end
    G-->>P: commit_hash

    rect rgb(240,244,240)
        Note over P,DB: 한 트랜잭션
        P->>S: save(document, body, commit_hash, author, deleted_item_pks)
        S->>DB: Version 생성 · Item 갱신(is_deleted) · Document.current_*
        opt status == approved (6a)
            S->>DB: Document.status=draft · StatusChange
            Note over S,DB: 본문은 이미 draft 로 밀었다 — 저장소·DB·응답이 같다
        end
        S-->>P: Version
        opt deleted 있음
            P->>R: mark_missing(deleted_item_pks)
            R->>DB: references where to_item in … → to_item·to_document NULL · is_missing=true
        end
        P->>R: extract(document_id, version_id, body)
        R->>DB: Reference 갱신 (사라진 것 삭제, 미존재 표시)
        P->>R: resolve_missing(document_id, item_pks)
        R->>DB: 이 문서·항목을 raw_target으로 기다리던 참조를 잇는다
        P->>DB: repositories.last_processed_commit = commit_hash (13a — 앱이 민 커밋은 곧 처리된 것. 그 사이 밖의 커밋이 끼었으면 그대로)
    end
    P->>P: repo lock 해제
    P-->>T: SaveResult {version_no, commit_hash, status, next_step}
    T-->>A: 결과
```

**읽을 때 볼 것**
- 검증(2a)·버전 충돌(4a)·삭제 확인(4b)은 **push 전에** 끝난다. push까지 갔으면 저장은 된다
- push가 DB 트랜잭션 **앞**이다. push가 실패하면 DB에 아무것도 안 남는다. 클래스 명세 4.7은 반대로 적혀 있었다 → 되먹일 것
- 삭제 확인은 `SpecService`가 아니라 `pipeline`이 한다. `SpecService`는 하위 참조를 모르기 때문이다(묶음 경계) → 되먹일 것
- **끊어진 참조는 표가 아니라 `references.is_missing`이다.** 항목이 지워지면 그것을 가리키던 참조가 미존재로 돌아가고(`mark_missing`), 대상이 다시 생기면 `resolve_missing`이 잇는다. 사람이 누르는 버튼이 없다 — 저장이 푼다
- **자동 강등(6a)은 push 전에 본문에도 쓴다.** DB에만 적으면 저장소 frontmatter가 `approved`로 남아 「`status`가 진실」이 깨지고, 다음 저장이 `frontmatter.status_change`로 막힌다 — 서버가 준 본문을 서버가 거부한다(#47). **서버가 에이전트의 본문을 고치는 유일한 자리다**

---

## SEQ-2 GitHub push를 받아 처리한다

[[SYNC-UC-001#UC-G1]] 기본 흐름 1~4, 확장 1a·1b·3a·3c. webhook 또는 폴링.

```mermaid
sequenceDiagram
    autonumber
    actor GH as GitHub
    participant H as web/hooks
    participant GHI as infra/github
    participant P as pipeline
    participant G as infra/git
    participant S as SpecService
    participant DB

    alt webhook
        GH->>H: POST /hooks/github {ref, after, repository}
        H->>GHI: verify_signature(X-Hub-Signature-256)
        alt 서명 불일치 · 비밀번호가 비어 있음
            H-->>GH: 401
        end
        alt push가 아님 · ref != refs/heads/main · 브랜치 삭제 (1c·1d)
            H-->>GH: 202 {ignored: 사유}
        end
        H-->>GH: 202
        H->>P: process_commit(repo, head_hash) (비동기)
        P->>P: 저장소 읽기 락 획득
    else 폴링 (1b) / 켜질 때 (1a)
        P->>P: 저장소 읽기 락 획득
        P->>G: fetch(repo)
        G-->>P: remote_head
        opt remote_head != last_processed_commit
            P->>P: process_commit(repo, remote_head, locked=True)
        end
    end

    Note over P: 웹훅·폴링·read_pending이 같은 읽기 락으로 한 줄로 선다 (#194)
    P->>DB: last_processed_commit 다시 읽기
    P->>G: fetch · rev_list_count(last..head)
    alt 0 — 이미 처리했거나 옛 head
        P-->>P: [] (처리 지점을 뒤로 돌리지 않는다)
    end
    P->>G: changed_files(last_processed_commit..head, "docs/specs/")
    G-->>P: [(path, commit_hash, author_login)]
    loop 변경 파일마다 (3c) — 파일마다 쓰기 락(save_pipeline 안)
        P->>G: read(path @ commit_hash)
        G-->>P: body
        P->>P: save_pipeline(entry=github, doc_id, body, expected_version=None, author=github(login), commit_hash)
        Note over P: entry=github는 SEQ-1과 이렇게 다르다
        Note over P,S: · 버전 검사 없음 (커밋이 진실)<br/>· push 없음 (이미 원격에 있음)<br/>· 규약 위반이면 저장은 하되 has_convention_error=true (3a)<br/>· 파일명 ≠ frontmatter doc_id면 규약 오류 (3b)
        opt 완료 문서인데 본문이 바뀜 (UC-A6 6a)
            P->>G: commit_push("status(문서ID): approved → draft")
            G-->>P: status_commit_hash
            Note over P,G: 커밋이 이미 저장소에 있어 본문만 고칠 수 없다.<br/>이 해시를 StatusChange에 적어야 다음 폴링이 걸러낸다 (#58)
        end
        P->>S: save(…, commit_hash, status_commit_hash)
        S->>DB: Version · Document · StatusChange
        Note over P: 이후 mark_missing · extract · resolve_missing은 SEQ-1과 같음
    end
    P->>DB: Repository.last_processed_commit = head
    P->>P: 저장소 읽기 락 해제
```

**읽을 때 볼 것**
- `author`는 커밋 작성자 GitHub 로그인으로 User를 찾는다. 등록 안 된 사람이면? → 되먹일 것
- 밀린 커밋이 여럿이면 `changed_files`가 범위 전체를 한 번에 준다. 커밋마다 돌지 않고 **최종 상태**만 저장한다. 중간 버전은 git에만 있다 → 되먹일 것
- **처리 전체가 저장소 읽기 락 안이다.** 전에는 웹훅·폴링이 락 없이 불렀다. 앱이 처리 도중 민 자동 강등 커밋의 웹훅이 두 번째 실행을 띄워, 같은 커밋을 강등 전 본문으로 한 번 더 저장했다(DB=approved · 저장소=draft, #194). 파일마다 잡는 쓰기 락과는 다른 락이다

---

## SEQ-4 프로젝트를 초기화한다

[[SYNC-UC-001#UC-A1]] 기본 흐름 1~6, 확장 2a·2b·3a·4a. 웹(UI-3)이든 MCP(`init_project`)든 같다. GitHub 저장의 흐름이다 — 서버 저장은 [[#SEQ-28]].

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람 또는 에이전트
    participant B as routers/projects 또는 mcp/tools
    participant PS as ProjectService
    participant G as infra/git
    participant AC as AccountService
    participant P as pipeline
    participant DB

    U->>B: init(remote_url, code, name, import_existing)
    B->>PS: init_project(remote_url, code, name, user, import_existing)
    PS->>PS: code 형식 검사
    alt 형식 위반 (2b)
        PS-->>B: project-code-invalid
    end
    PS->>DB: Project where code
    alt 중복 (2a)
        PS-->>B: project-code-conflict
    end
    PS->>G: clone(remote_url, workdir, token)
    G->>AC: github_token_for(user)
    AC-->>G: token
    alt clone 실패 (권한·주소)
        G-->>PS: CloneFailed
        PS-->>B: push-failed {reason: clone}
    end
    G-->>PS: workdir
    PS->>G: exists(workdir, "docs/specs/")
    G-->>PS: true | false

    alt 이미 있음 (3a)
        alt import_existing=false
            PS->>G: count(docs/specs/*.md)
            PS->>G: 작업 사본 삭제
            PS-->>B: existing-specs {doc_count}
        else import_existing=true (3a2)
            PS->>DB: Project · Repository 생성
            PS->>P: rebuild(code)
            P->>G: list(docs/specs/*.md) · git log
            loop 파일마다
                P->>P: validate · save(entry=rebuild) · extract
            end
            P-->>PS: RebuildResult
        end
    else 없음 (기본 흐름 4)
        PS->>G: mkdir 11단계 · README.md(규약 링크 — 사본 없음, 카드 AB)
        PS->>G: commit_push("chore: init syncdoc", author)
        alt push 실패 (4a)
            G-->>PS: PushFailed
            PS->>G: 작업 사본 삭제
            PS-->>B: push-failed
        end
        PS->>DB: Project · Repository(last_processed_commit=hash)
        PS->>GH: create_hook(push 통지) — 등록이 끝난 뒤. 실패해도 등록은 계속, 사유는 hook_error (UC-A1 4a, 카드 AF)
    end
    PS-->>B: ProjectSummary (11단계 미작성 또는 재구축 결과)
    B-->>U: 결과
```

**읽을 때 볼 것**
- `existing-specs`로 거부할 때 clone한 작업 사본을 지운다. 안 지우면 재요청 때 "이미 clone됨"이 된다
- 재구축(3a2)은 `rebuild`가 하고 `init_project`는 등록만. 같은 `rebuild`를 UI-14가 부른다

---

## SEQ-5 문서 상태를 바꾼다

[[SYNC-UC-001#UC-H8]] 기본 흐름 1~3, 확장 1a. UI-5 요소 3 · MCP `change_status`(카드 BE). 초안 ⇄ 완료 토글. 입구가 둘이고 그 뒤는 하나다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    actor A as 에이전트
    participant RD as routers/documents
    participant MT as mcp/tools
    participant S as SpecService
    participant P as pipeline
    participant G as infra/git
    participant DB

    alt 웹 토글
        U->>RD: POST /api/docs/{id}/status {to, reason?}
        RD->>P: change_status(doc_id, to, Author(human, user, None, web_status), reason)
    else MCP change_status — 사람이 시켰거나 에이전트가 다 썼다고 판단 (카드 BE)
        A->>MT: change_status(doc_id, to, reason?)
        MT->>P: change_status(doc_id, to, _agent_author(kind=agent, 지시자=발급자, via=mcp), reason)
    end
    P->>G: read_pending — fetch · 밀렸으면 process_commit (UC-H8 1d, #137)
    P->>S: get_document(doc_id)
    alt to=approved and (has_convention_error or incomplete_warnings or 미존재 참조) (1a)
        P-->>RD: status-blocked {convention_error_detail, warnings}
    end
    P->>G: read(경로, origin/main) — 원본이 진실 (DOM-001)
    P->>P: 그 본문의 frontmatter.status 줄만 교체 → new_body
    P->>P: save_pipeline(entry=web_status, doc_id, new_body, expected_version=current, author, reason) — 같은 세션
    Note over P: 상태 줄 하나만 바뀐다 — 본문은 저장소에서 읽은 그대로<br/>· validate (frontmatter만)<br/>· 버전 검사<br/>· push (message: "status(doc_id): from → to")<br/>· Version 생성 안 함 · extract 안 함
    P->>G: commit_push(…, "status(SYNC-PRD-001): draft → approved")
    G-->>P: commit_hash
    rect rgb(240,244,240)
        P->>DB: Document.status=to · current_body=new_body
        P->>DB: StatusChange(from, to, author.user, via=author.via 접음, reason, commit_hash)
    end
    P-->>RD: DocumentSummary
    RD-->>U: 상태 뱃지 갱신
    P-->>MT: DocumentSummary
    MT-->>A: 문서 요약 (status·version_no·last_author)
```

**읽을 때 볼 것**
- 상태 변경은 `pipeline.change_status`가 조율한다(B2 되먹임으로 SpecService에서 옮김). SpecService는 `get_document`·`apply_status`만
- 완료로 올리는 조건은 셋뿐이다 — 규약 오류·미완성·미존재 참조가 없을 것. 셋 다 한 문서만 보고 판정된다. 상위 대조·댓글 확인은 v2에서 사라졌다
- **쓰기 전에 읽는다 (#137).** 저장소에 아직 안 읽은 커밋이 있으면 먼저 읽어 반영하고(1단계), 커밋할 본문도 `origin/main`에서 읽는다. 예전에는 DB의 `current_body`로 본문을 만들어 커밋해서, 밀린 커밋의 내용이 통째로 되돌아갔다 — `git.commit_push`가 `reset --hard` 뒤에 덮어쓰므로 push가 거부되지도 않아 조용히 사라졌다. 저장소에 쓰는 다른 일(SEQ-7·SEQ-22·SEQ-23·SEQ-1)도 같은 읽기가 앞선다
- 상태 변경은 **Version을 만들지 않는다.** `StatusChange`가 커밋 해시를 갖는다. UI-7 이력에서 `status` 행은 `StatusChange`에서, `spec` 행은 `Version`에서 와서 시각순으로 합친다
- **입구가 둘, 조건은 하나(카드 BE).** 에이전트의 `change_status`도 같은 `pipeline.change_status`를 부른다 — 1a의 막는 조건·밀린 커밋 읽기·상태 커밋이 전부 같다. 다른 것은 `author`뿐이고, 그것이 `StatusChange.via`(`web`/`mcp`)로 남아 이력이 「에이전트 · 지시 {사람}」을 그린다. `entry=web_status`는 입구 이름이 아니라 「상태 줄만 바꾸는 모양」이다

---

## SEQ-7 이전 버전으로 되돌린다

[[SYNC-UC-001#UC-H7]] 기본 흐름 1~4, 확장 4a. UI-7 요소 2.2 → 4.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RD as routers/documents
    participant S as SpecService
    participant P as pipeline
    participant DB

    U->>RD: GET /api/docs/{id}/diff?from=current&to=target
    RD->>S: diff(doc_id, current, target)
    S-->>RD: Diff
    RD-->>U: UI-7 다이얼로그 4

    U->>RD: POST /api/docs/{id}/revert {to_version}
    RD->>P: revert(doc_id, to_version, user, confirm)
    P->>S: get_document · versions where version_no=to_version
    S-->>P: old_body
    P->>P: save_pipeline(entry=web_revert, doc_id, old_body, expected_version=current, author=human, confirm) — 같은 세션
    Note over P: SEQ-1과 같은 파이프라인. 차이는 입구뿐<br/>· validate — 옛 본문이 지금 규약을 위반하면 convention-violation (4a)<br/>· 삭제 감지 — 옛 본문에 없는 항목이 지금 있으면 4b와 같이 확인<br/>· push, save(새 Version), mark_missing, extract, resolve_missing
    P-->>RD: SaveResult
    RD-->>U: UI-5 (새 버전)
```

**읽을 때 볼 것**
- 되돌리기가 항목을 없애는 경우가 있다. 지금 v7에 있는 `#R15`가 v3엔 없으면 되돌리기 = 삭제. 웹엔 `confirm` 인자가 없으므로 `item-deletion-needs-confirm`이 오면 UI-7이 확인 다이얼로그를 띄우고 `confirm_item_deletion=true`로 재요청해야 한다 → 되먹일 것 (API에 그 인자가 없다)

---

## SEQ-8 GitHub로 로그인한다

인프라 5장. UI-1. **인터넷판만** — 폐쇄망판은 로그인이 없고 모든 웹 요청이 [[#SEQ-C3]]로 로컬 사용자가 된다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RA as routers/account
    participant AS as AccountService
    participant GHI as infra/github
    participant DB

    U->>RA: GET /auth/github?next=/p/SYNC
    RA->>RA: state 생성 · 세션에 next·state 저장
    RA->>RA: redirect_uri = auth.callback_url(request)
    RA-->>U: 302 GitHub 동의 화면 (scope=repo, redirect_uri)
    U->>RA: GET /auth/github/callback?code&state
    RA->>RA: state 대조
    alt state 불일치
        RA-->>U: 401
    end
    RA->>AS: login_github(code, state, redirect_uri)
    AS->>GHI: exchange_code(code, redirect_uri)
    Note over RA,GHI: redirect_uri는 authorize 때와 같은 값 — GitHub가 대조한다
    GHI-->>AS: access_token
    AS->>GHI: get_user(access_token)
    GHI-->>AS: {id, login, name}
    alt login이 허용 목록(ALLOWED_LOGINS) 밖 — 카드 BP
        AS-->>RA: login-not-allowed (사용자·토큰을 남기지 않는다)
        RA-->>U: 302 /login?denied=1
    end
    AS->>DB: User upsert by github_user_id (login 바뀌었으면 갱신)
    AS->>AS: encrypt(access_token, 앱 비밀키)
    AS->>DB: users.github_token_encrypted
    AS-->>RA: User
    RA->>RA: 세션 생성 (syncdoc_session 쿠키)
    RA-->>U: 302 next 또는 /
```

**읽을 때 볼 것** — 허용 목록은 GitHub이 알려 준 login으로 **upsert 전에** 본다 — 목록 밖 계정은 행도 토큰도 남지 않는다(카드 BP). 설정이 비면 누구나다. `github_user_id`로 upsert한다. 로그인 ID를 바꾼 사람도 같은 User다(DD users). `redirect_uri`를 보내므로 OAuth 앱 하나에 콜백을 여럿(로컬·공개) 등록해도 요청한 주소로 돌아온다(인프라 5장).

---

## SEQ-9 프로젝트 목록·상세를 본다

[[SYNC-UC-001#UC-H14]] 기본 흐름 1~3. UI-2, UI-4. 프로젝트마다 단계 요약과 건수를 모으느라 묶음 셋을 넘는다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RP as routers/projects
    participant Q as queries
    participant PS as ProjectService
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    U->>RP: GET /api/projects (또는 /api/projects/{code})
    RP->>Q: project_summary(user) (또는 project_detail(code))
    Q->>PS: list_projects() (또는 get(code))
    PS->>DB: projects · repositories
    PS-->>Q: Project[]
    loop 프로젝트마다
        Q->>S: list_by_project(project_id)
        S->>DB: documents where project
        S-->>Q: DocumentSummary[] (status, doc_type, has_convention_error)
        Q->>Q: 단계 11칸 계산 — 문서 여럿이면 가장 낮은 상태(1a), 없으면 null(3a), 앞 단계 미완료면 gate_warning(1b)
        Q->>R: count_missing_by_document(document_ids)
        R-->>Q: {document_id: n} → 합이 counts.broken_ref, 단계별 합이 broken_count
        Q->>Q: convention_errors = has_convention_error인 문서 수 · incomplete = 미완성 경고가 있는 문서 수
    end
    opt 상세
        Q->>S: recent_changes(project_id, n=10)
        S->>DB: versions ∪ status_changes order by created_at
        S-->>Q: Version[] (status 커밋 포함)
    end
    Q-->>RP: ProjectSummary[] | ProjectDetail
    RP-->>U: UI-2 | UI-4
```

**읽을 때 볼 것**
- 단계 11칸 계산은 `queries`가 한다. `ProjectService`는 `documents` 테이블을 모른다(spec 묶음). → 되먹일 것 #12·#13
- `recent_changes`가 `versions`와 `status_changes`를 합친다 → 되먹일 것 #6

---

## SEQ-10 문서 목록을 본다

[[SYNC-UC-001#UC-A5]], [[SYNC-UC-001#UC-H14]]·H16. REST `GET /api/projects/{code}/docs` · MCP `list_documents`.

```mermaid
sequenceDiagram
    autonumber
    actor A as 사람 또는 에이전트
    participant B as routers/projects 또는 mcp/tools
    participant Q as queries
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    A->>B: docs(code, stage?, status?)
    B->>Q: document_list(code, stage, status)
    Q->>S: list_by_project(project_id, stage, status)
    S->>DB: documents · 최근 version (last_author)
    S-->>Q: DocumentSummary[]
    Q->>R: count_missing_by_document(document_ids)
    R-->>Q: {document_id: broken_ref}
    Q-->>B: DocumentSummary[] (counts 채움)
    B-->>A: 목록 (MCP는 stages로 묶어서)
```

**읽을 때 볼 것** — 문서마다 건수 하나. 문서 N개면 쿼리 N번이 아니라 `document_ids`로 한 번에 묶어 묻는다 → MINISPEC.

---

## SEQ-11 문서를 본다

[[SYNC-UC-001#UC-A2]], [[SYNC-UC-001#UC-H2]]. REST `GET /api/docs/{docId}` · MCP `get_document`. 유저용·원본 탭 공통.

```mermaid
sequenceDiagram
    autonumber
    actor A as 사람 또는 에이전트
    participant B as routers/documents 또는 mcp/tools
    participant Q as queries
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    A->>B: get(doc_id)
    B->>Q: document_view(doc_id)
    Q->>S: get_document(doc_id)
    alt 없음 ([[SYNC-UC-001#UC-A2]] 1a)
        S-->>Q: NotFound
        Q-->>B: not-found
    end
    S->>DB: documents · items(is_deleted=false) · 최근 version
    S-->>Q: Document (body, status, version_no, items[], convention_error)
    Q->>R: upstream_of_document(document_id, include_missing=True)
    R->>DB: references where from document and is_missing
    R-->>Q: RefEdge[] → 항목별 missing_refs[raw_target]
    Q->>S: neighbors(doc_id)
    S->>DB: 같은 프로젝트에서 stage-1·stage+1의 첫 문서
    S-->>Q: prev_doc_id, next_doc_id
    Q-->>B: Document (items[].missing_refs 채움, prev/next)
    B-->>A: 유저용 탭은 React가 렌더링 · 원본 탭은 body 그대로 · MCP는 JSON
```

**읽을 때 볼 것**
- `items[].missing_refs`를 붙이려고 `ReferenceService`를 부른다. `SpecService`가 직접 부르면 묶음 경계 위반 → `queries`가 조합 (되먹일 것 #12)
- 규약 오류 문서는 에러가 아니라 정상 반환 + `has_convention_error`([[SYNC-UC-001#UC-A2]] 2a)

---

## SEQ-12 항목을 본다

[[SYNC-UC-001#UC-A3]]. MCP `get_item` · REST `GET /api/docs/{docId}/items/{itemId}`(UI-18 항목 미리보기, [[SYNC-UC-001#UC-H3]] 3, 카드 BH) — 입구만 다르고 `queries.item_view`부터는 같다.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트
    participant T as mcp/tools
    participant Q as queries
    participant S as SpecService
    participant DB

    A->>T: get_item(doc_id, item_id)
    T->>Q: item_view(doc_id, item_id)
    Q->>S: get_item(doc_id, item_id)
    S->>DB: documents · items where item_id
    alt 문서 없음
        S-->>Q: NotFound
    else 항목 없음 (1b)
        S->>DB: 문서의 items 목록
        S-->>Q: NotFound + available_items
    else 삭제됨 (1a)
        S-->>Q: ItemDeleted {deleted_at}
    end
    S->>S: current_body에서 항목 블록 잘라내기 (헤더부터 다음 항목 헤더 전까지)
    S-->>Q: ItemView (body 블록, doc_status, doc_version_no)
    Q-->>T: ItemView
    T-->>A: JSON
    Note over T,Q: 웹은 routers/references가 같은 item_view를 부른다 — UI-18이 블록을 유저용으로 그린다 (카드 BH)
```

**읽을 때 볼 것** — "항목 블록"의 경계를 어떻게 자르나가 MINISPEC 과제. 문서 타입마다 헤더 형식이 다르다(클래스 미결 `display_name`과 같은 문제).

---

## SEQ-13 항목의 참조를 본다

[[SYNC-UC-001#UC-A4]], [[SYNC-UC-001#UC-H3]]. REST `GET …/items/{itemId}/references` · MCP `get_references`. UI-5 패널 8.1.

```mermaid
sequenceDiagram
    autonumber
    actor A as 사람 또는 에이전트
    participant B as routers/references 또는 mcp/tools
    participant Q as queries
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    A->>B: references(doc_id, item_id)
    B->>Q: item_references_view(doc_id, item_id)
    Q->>S: resolve_item(doc_id, item_id) → item_pk
    alt 없음 · 삭제됨
        Q-->>B: not-found | item-deleted
    end
    Q->>R: upstream(item_pk)
    R->>DB: references where from_item=item_pk
    R-->>Q: [(to_item_pk | to_document_id, raw_target, is_missing)]
    Q->>R: downstream(item_pk)
    R->>DB: references where to_item=item_pk
    R-->>Q: [(from_item_pk | from_document_id, raw_target)]
    Note over Q,R: 문서 전체를 가리킨 참조는 항목의 하위가 아니다
    Q->>S: describe_items(item_pks)
    S-->>Q: {pk: (doc_id, item_id, display_name)}
    Q->>S: describe_documents(document_ids)
    S-->>Q: {id: (doc_id, title)}
    Q-->>B: ItemReferences {upstream, downstream}
    B-->>A: 패널 | JSON
```

**읽을 때 볼 것**
- `ReferenceService`는 pk만 안다. 사람이 읽을 `doc_id#item_id`와 표시 이름은 `SpecService.describe_items`로 채운다 → 되먹일 것 #14
- `item_id: null`은 문서다 — 상위에서는 문서 전체를 가리킨 참조, 하위에서는 항목 밖(절 본문·표)에서 이 항목을 건 참조의 출발 문서
- 이 문서 전체를 가리킨 참조(`[[문서]]`)는 어느 항목의 하위에도 섞지 않는다. 전에는 모든 항목 아래에 섞여 카드·관계도와 수가 달랐다(#160). 화면은 `GET …/downstream`의 `(문서)`로 따로 보인다(UI-5 8.10)

---

## SEQ-14 참조 그래프를 본다

[[SYNC-UC-001#UC-H4]]. UI-8.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RR as routers/references
    participant Q as queries
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    U->>RR: GET /api/projects/{code}/graph?stage&doc
    RR->>Q: graph_view(code, stage, doc)
    Q->>S: list_items_by_project(project_id, stage?, doc?) (is_deleted=false)
    S-->>Q: [(item_pk, doc_id, item_id, stage, display_name)]
    Q->>R: references_among(item_pks, include_document_targets=true)
    R->>DB: references where from in … or to in …
    R-->>Q: edges[]
    opt 범위를 좁힘 (2b)
        Q->>Q: 범위 밖 노드 중 범위 안과 이어진 것만 남김
        Q->>S: describe_items(추가된 pk)
    end
    Q->>Q: isolated = 간선이 하나도 없는 노드 (2a)
    Q-->>RR: Graph {nodes, edges} (좌표 없음)
    RR-->>U: UI-8이 배치
```

**읽을 때 볼 것** — 좌표는 서버가 안 준다. 노드·간선만. 배치는 브라우저(drawio 뺀 것과 같은 원칙).

---

## SEQ-15 두 버전의 diff를 본다

[[SYNC-UC-001#UC-H6]]. UI-7. 항목별로 묶고 하위 참조 건수를 붙인다(3a).

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RD as routers/documents
    participant Q as queries
    participant S as SpecService
    participant R as ReferenceService
    participant DB

    U->>RD: GET /api/docs/{id}/diff?from=5&to=7
    RD->>Q: diff_with_impact(doc_id, 5, 7)
    Q->>S: diff(doc_id, 5, 7)
    S->>DB: versions where version_no in (5,7) → body ×2
    S->>S: 줄 diff → 항목 헤더 기준으로 hunk 묶기
    S-->>Q: Diff {hunks[].item_id}
    Q->>S: resolve_items(doc_id, hunks[].item_id)
    S-->>Q: item_pks
    Q->>R: count_downstream(item_pks)
    R->>DB: references where to_item in … group by
    R-->>Q: {item_pk: n}
    Q-->>RD: Diff (hunks[].downstream_count 채움)
    RD-->>U: UI-7 요소 3
```

**읽을 때 볼 것** — `SpecService.diff`는 참조를 모른다. 건수는 `queries`가 붙인다.

---

## SEQ-18 프로젝트의 끊어진 참조·오류·미완성 목록을 본다

[[SYNC-UC-001#UC-H14]] 기본 흐름 4. UI-4 다이얼로그 6.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RP as routers/projects
    participant Q as queries
    participant R as ReferenceService
    participant S as SpecService

    U->>RP: GET /api/projects/{code}/flags?kind
    RP->>Q: project_items(code, kind)
    alt kind = broken_ref
        Q->>R: missing_in_project(project_id)
        Q->>S: describe_items(from pk)
        Q-->>RP: BrokenRefSummary[]
    else kind = convention_errors
        Q->>S: list_by_project(project_id, has_convention_error=true)
        Q-->>RP: DocumentSummary[]
    else kind = incomplete
        Q->>S: list_by_project(project_id) → incomplete_warnings가 있는 것
        Q-->>RP: DocumentSummary[]
    end
    RP-->>U: 다이얼로그
```

**읽을 때 볼 것** — `kind`로 두 서비스 중 하나로 갈린다. 경로 이름 `flags`는 v1의 것이 남은 것이다([[SYNC-API-001]] 3.3).

---

## SEQ-19 에이전트가 문서를 만든다

[[SYNC-UC-001#UC-A6]] (생성). MCP `create_document`. SEQ-1과 같은 파이프라인이되 앞부분이 다르다.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트
    participant T as mcp/tools
    participant AC as AccountService
    participant P as pipeline
    participant PS as ProjectService
    participant S as SpecService
    participant G as infra/git
    participant DB

    A->>T: create_document(project_code, doc_type, body)
    T->>AC: authenticate_token(bearer)
    T->>P: save_pipeline(entry=mcp, doc_id=None, doc_type, body, expected_version=None, author)
    P->>P: repo lock
    P->>PS: get(project_code) → project_id, repo
    P->>S: issue_doc_id(project_id, doc_type)
    S->>DB: max(number) where project·type
    S-->>P: "SYNC-PRD-002"
    P->>S: apply_frontmatter(body, doc_id, doc_type, status=draft)
    Note over S: 에이전트가 doc_id를 비워 보냈으면 채우고,<br/>적어 보냈으면 발급한 것과 같은지 확인
    S-->>P: body'
    opt doc_type == DOM (3a)
        P->>S: precondition(project_id, doc_type, title)
        S->>DB: documents where project·type (API 있나 · 클래스 명세 있나)
        alt 선행 문서 없음
            P-->>T: precondition-unmet {requires, have}
        end
    end
    P->>S: validate(body', doc_type)
    alt 위반 (2a)
        P-->>T: convention-violation
    end
    Note over P: 버전 검사 없음 (신규) · 삭제 검사 없음
    P->>G: commit_push(repo, "docs/specs/{type}/{doc_id}.md", body', "spec(doc_id): 생성", author)
    G-->>P: commit_hash
    rect rgb(240,244,240)
        P->>S: create(project_id, doc_id, doc_type, body', commit_hash, author)
        S->>DB: documents · items · versions(v1)
        P->>R: extract(document_id, version_id, body')
        P->>R: resolve_missing(document_id, item_pks) — 이 문서를 기다리던 참조를 잇는다
    end
    P->>P: lock 해제
    P-->>T: SaveResult {doc_id, version_no: 1, next_step}
    T-->>A: 결과
```

**읽을 때 볼 것**
- 파일 경로가 `docs/specs/{type}/{doc_id}.md`다. 11단계 디렉터리가 타입 코드다 → 인프라·PRD에 경로 규약이 없다 (되먹일 것 #16)
- `apply_frontmatter`가 새 메서드. 에이전트가 frontmatter를 비워도 서버가 채운다 → #17
- DOM 선행조건(3a)은 **push 전에** 끝난다. 존재만 본다 — 상태는 신호다([[SYNC-PRD-001#R6]]). `next_step`은 결과에 매번 실린다 — 문서 하나 쓰고 멈추라는 규약([[SYNC-STD-001]] 1.8)을 응답이 다시 말한다

---

## SEQ-20 저장소 동기화 상태를 본다

UI-14 표 2. [[SYNC-UC-001#UC-G1]] 1a·1b의 근거 데이터.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RA as routers/admin
    participant PS as ProjectService
    participant G as infra/git
    participant DB

    U->>RA: GET /api/admin/repos
    RA->>PS: repo_status()
    PS->>DB: repositories
    loop 저장소마다
        PS->>G: fetch(repo) (원격만 갱신, 작업 사본 안 건드림)
        PS->>G: rev_list_count(last_processed_commit..origin/main)
        G-->>PS: behind_by
    end
    PS-->>RA: RepoStatus[]
    RA-->>U: 표
```

**읽을 때 볼 것** — 화면 열 때마다 fetch를 저장소 수만큼 한다. 느리면 폴링이 갱신한 값을 DB에 캐시하고 여기서는 읽기만 → 미결.

---

## SEQ-21 인덱스를 재구축한다

[[SYNC-UC-001#UC-S6]]. UI-14 요소 3~5. 참조·버전·항목을 저장소에서 다시 만든다.

**README를 먼저 맞춘다(카드 AB).** 재구축이 저장소에 쓰는 유일한 것이다 — 인덱스를 다시 만들기 전에 `docs/specs/README.md`가 지금 판과 다르면 새 판으로 커밋한다. 먼저 하는 이유는 그 커밋이 뒤이은 `fetch`의 head에 들어가 밀림이 0으로 끝나기 때문이다. push가 실패하면 인덱스는 건드리지 않는다(UC-S6 1a).

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RA as routers/admin
    participant P as pipeline
    participant PS as ProjectService
    participant S as SpecService
    participant R as ReferenceService
    participant G as infra/git
    participant DB

    U->>RA: POST /api/admin/repos/{code}/rebuild
    RA->>PS: rebuild_index(code, user)
    PS->>PS: get_owned(code, user)
    PS->>G: sync_readme(workdir, author) — README가 낡았으면 새 판으로 커밋·push (카드 AB)
    G-->>PS: commit_hash 또는 None
    PS->>P: rebuild(code)
    P->>PS: get(code) → repo
    P->>P: repo lock
    P->>G: fetch · checkout origin/main
    rect rgb(240,244,240)
        Note over P,DB: 한 트랜잭션. 실패하면 전부 롤백
        P->>R: clear(project_id)
        R->>DB: delete references where project
        P->>S: clear_index(project_id)
        S->>DB: delete versions · status_changes(커밋 있는 것) where project (documents · items 행은 유지 — pk가 바뀌면 안 된다)
        P->>G: list("docs/specs/**/*.md")
        loop 파일마다
            P->>G: log(path) → [(commit_hash, author_login, date, message)]
            loop 커밋마다 (오래된 것부터)
                P->>G: read(path @ commit)
                P->>S: validate(body, doc_type)
                P->>S: save(document, body, commit_hash, author=github(login), rebuild=true)
                S->>DB: versions(version_no 순서대로) · items
                S-->>P: 새 version
            end
            P->>R: extract(document_id, 최신 version_id, body)
            P->>S: mark_convention_error(document_id, violations or none)
        end
        P->>R: resolve_missing(project_id) — 순서상 앞 문서가 뒤 문서를 가리킨 것을 잇는다
        P->>DB: repositories.last_processed_commit = HEAD
    end
    P->>P: lock 해제
    P-->>PS: RebuildResult {docs, items, references, versions, convention_errors[]}
    PS-->>RA: RebuildResult + readme_updated
    RA-->>U: 결과 표 5
```

**읽을 때 볼 것**
- `documents`·`items` 행은 지우지 않는다. 문서 pk는 상태 변경·휴지통이 물고 있고, 항목은 upsert한다 (되먹일 것 #18). v1에서는 플래그·댓글이 이 pk를 물어 재구축이 `relink`·`reassign` 두 단계를 더 가졌다 — v2에서 그 표가 사라지면서 `versions`를 가리키는 FK는 `references.extracted_version_id` 하나만 남았고, 지우고 다시 만드는 것으로 끝난다
- 커밋마다 돌아서 버전 이력을 복원한다. SEQ-2(밀린 커밋)는 최종 상태만 저장하는 것과 다르다

---

## SEQ-22 문서를 휴지통에 넣는다 · 완전히 지운다

[[SYNC-UC-001#UC-A7]] 기본 흐름 1~6 · [[SYNC-UC-001#UC-H18]] 1~3·6~8. MCP `delete_document` · `DELETE /api/docs/{docId}` · `POST …/purge`. 입구가 둘이고 파이프라인은 하나다.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트·사람
    participant T as mcp/tools · routers/documents
    participant P as pipeline
    participant S as SpecService
    participant R as ReferenceService
    participant G as infra/git
    participant DB

    A->>T: delete_document(doc_id, confirm) · DELETE /api/docs/{id}
    T->>P: trash_document(doc_id, author, confirm) — 웹은 confirm=true (다이얼로그 13이 받았다)
    P->>P: repo lock
    P->>S: get_document(doc_id)
    S-->>P: Document (trashed_at, items, version_count)
    alt trashed_at 있음 (1a)
        P-->>T: document-trashed
    end
    P->>R: inbound_of_document(document_id)
    alt confirm=false (2)
        P-->>T: document-deletion-needs-confirm {title, version_count, inbound_refs}
        T-->>A: isError — 사람에게 보여준다
    end
    P->>G: commit_push(repo, "spec(doc_id): 휴지통", author, delete=[path])
    G-->>P: commit_hash
    rect rgb(240,244,240)
        Note over P,DB: 한 트랜잭션 — push 뒤
        P->>S: trash(document, commit_hash, author)
        S->>DB: items.is_deleted · documents.status=draft·trashed_at·trashed_by · StatusChange(reason=휴지통, commit_hash)
        S-->>P: deleted item pks
        P->>R: mark_missing(deleted item pks)
        R->>DB: 이 문서 항목을 가리키던 참조 → to_item·to_document NULL · is_missing=true
    end
    P->>P: lock 해제
    P-->>T: TrashResult {doc_id, commit_hash, broken_refs, next_step}
    T-->>A: 결과

    Note over A,DB: 완전 삭제 — POST /api/docs/{id}/purge (웹만)
    A->>T: POST /api/docs/{id}/purge
    T->>P: purge_document(doc_id, author)
    P->>S: get_document — trashed_at 없으면 document-not-trashed
    P->>R: inbound_of_document (미존재로 남은 것 포함)
    alt 0이 아님 (7)
        P-->>T: document-has-history {inbound_refs}
    end
    P->>S: delete_document(document)
    S->>DB: 상태변경·references(from)·items·versions·documents 삭제
    P-->>T: 204
```

**읽을 때 볼 것**
- 휴지통 넣기는 **하드 삭제가 아니다.** GitHub에서 파일을 지워 push한 것(UC-G1 3d)과 같은 상태에 `trashed_at`만 더한 것이다 — 규약 오류로 세지 않고, 목록·단계 칸·그래프에서 빠지고, 저장·상태 변경이 `document-trashed`로 막힌다
- 삭제 커밋은 다음 폴링에 `D`로 온다. `trashed_at`이 있는 문서의 `D`는 앱이 만든 것이라 [[SYNC-MS-007#pipeline.process_commit]]이 건너뛴다
- 완전 삭제의 문지기는 하나 — 들어오는 참조(미존재로 남은 것 포함). 상태 변경·버전·항목·나가는 참조는 이 문서의 것이라 함께 지운다

---

## SEQ-23 휴지통에서 되살린다

[[SYNC-UC-001#UC-A8]] 기본 흐름 1~5 · [[SYNC-UC-001#UC-H18]] 4~5. MCP `restore_document` · `POST /api/docs/{docId}/restore`.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트·사람
    participant T as mcp/tools · routers/documents
    participant P as pipeline
    participant S as SpecService
    participant G as infra/git
    participant R as ReferenceService
    participant DB

    A->>T: restore_document(doc_id) · POST /api/docs/{id}/restore
    T->>P: restore_document(doc_id, author)
    P->>S: get_document — trashed_at 없으면 document-not-trashed (1a)
    P->>S: trash_commit(document_id)
    S-->>P: 휴지통 커밋 해시
    P->>G: read(repo, path, "{hash}^")
    G-->>P: 지우기 직전 본문
    P->>P: frontmatter status를 draft로 (DB가 draft다 — mcp 경로의 status_change 검사)
    P->>P: save_pipeline(entry=web_revert|mcp, doc_id, body, expected_version=current, message="spec(doc_id): 되살림 — 휴지통에서") — 같은 세션
    Note over P,S: validate — 휴지통 문서의 삭제 항목은 item.reused에서 뺀다(복구)<br/>save — 항목 is_deleted 되돌림 · trashed_at·trashed_by null
    Note over P,R: save_pipeline 안의 resolve_missing이 되살아난 문서·항목을 기다리던 참조를 다시 잇는다
    P-->>T: SaveResult
    T-->>A: 결과 (201)
```

**읽을 때 볼 것**
- 되살리기는 **새 버전**이다(되돌리기와 같은 원칙 — 이력을 안 지운다). 휴지통 사이의 시간도 이력에 남는다
- `save`가 `trashed_at`을 비운다 — **어느 입구든** 저장되면 휴지통에서 나온다. GitHub에서 파일을 되살려 push해도 같다
- 미존재 참조는 대상이 돌아왔으니 다시 잇는다(`resolve_missing`). 가리키던 쪽 문서는 손대지 않는다

---

## SEQ-24 읽다가 항목에 대해 묻는다

[[SYNC-UC-001#UC-H19]] 기본 흐름 1~4. `POST /api/docs/{docId}/ask` — 응답은 SSE(`text/event-stream`). **명세는 쓰지 않는다 — `pipeline`을 거치지 않는 유일한 외부 호출이다.** 모델이 도구로 같은 프로젝트를 읽는 ReAct 루프다(사용자 결정 2026-09-22). 질문·답·첨부는 **대화 표에 남는다**(2026-09-29, 카드 AQ·AR) — 명세 표가 아니라 `pipeline` 밖이다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RC as routers/conversations
    participant RD as routers/documents
    participant Q as queries
    participant C as ConversationService
    participant S as SpecService
    participant R as ReferenceService
    participant LLM as infra/llm
    participant DB

    U->>RC: POST /api/conversations/{id}/attachments (multipart) — 드롭·붙여넣기·「+」
    RC->>C: add_attachment(conv_id, user, name, mime, bytes)
    C->>C: 종류·상한 검사 (415·413·409) · 글자·PDF면 text_cache 추출
    C->>DB: attachments (turn_id null)
    RC-->>U: 201 AttachmentMeta — 칩(8.14)
    U->>RD: POST /api/docs/{id}/ask {conversation_id, question, item_id?, attachment_ids}
    RD->>Q: ask_item(doc_id, item_id, conversation_id, question, attachment_ids, user)
    Q->>Q: 키 없으면 llm-not-configured (2a) · get_owned
    Q->>C: get(conversation_id, user) · history(conv_id, LLM_MAX_TURNS) · add_turn(question, attachment_ids)
    C->>DB: conversations · turns · attachments(turn_id 채움)
    C-->>Q: 앞 대화 · 첨부 목록 · 이 턴의 이미지
    Q->>S: get_document(doc_id) — 제목·상태·버전·항목 ID·이름 (본문은 안 싣는다)
    S->>DB: documents · items
    S-->>Q: 시작 맥락 (+ 첨부 이름·종류·크기 한 줄)
    Q-->>RD: start {doc_id, item_id}
    RD-->>U: 200 text/event-stream — 이 앞의 오류는 상태 코드, 뒤는 error 이벤트
    loop 도구 8번 · 전체 120초 안
        Q->>LLM: step_stream(system, 대화록, tools) — 이 턴의 user 항목에 images (vision)
        Q-->>U: delta {text} — 모델이 쓰는 글자 조각을 바로 (카드 AW). 답인지 메모인지는 뒤 이벤트가 정한다
        LLM-->>Q: tool_calls 또는 답 문자열 — 실패하면 llm-unavailable → error 이벤트 (4a)
        Q-->>U: note {reason} — 무엇을 왜 읽는지
        Q->>Q: ask_tool(name, args, code, user, conversation_id)
        Q->>S: get_item · get_document · list
        Q->>R: upstream · downstream · 사슬
        Q->>C: attachment_text(conv_id, att_id) — read_attachment
        Q->>Q: code_graph → code_view · read_code → CodeGraphService.read · find_code → 그래프 함수 이름 찾기·불리는 곳 — 코드 대조·본문·찾기 (카드 AZ, #302)
        S-->>Q: 본문·목록 (없으면 「없음」 텍스트, 예외 아님 — 3c)
        R-->>Q: 참조 (문서는 제목·상태, 끊어진 건 「아직 없음」)
        C-->>Q: 첨부 글자 (이미지·남의 첨부면 「없음」)
        Q-->>U: read {tool, target}
    end
    Q->>LLM: 상한에 닿으면 마무리 호출 한 번 (tool_choice none) — 읽은 것으로 답하라 (3b)
    Q->>C: finish_turn(turn_id, answer | error, progress, context_item_ids)
    C->>DB: turns · conversations.updated_at
    Q->>Q: usage 로그 한 줄 (본문은 로그에 없다)
    Q->>S: list_items_by_project — 답 속 맨 문서ID#항목ID를 실제 항목과 맞춘다 (_answer_links, #290)
    Q-->>U: answer {answer, context_item_ids, missing_refs} — [[…]]로 바꾼 답, 읽은 대상, 없는 참조
```

**읽을 때 볼 것**
- **명세 표에는 쓰지 않는다.** 쓰는 것은 대화 세 표뿐이고 `ConversationService`가 닫는다. 턴은 질문을 받자마자 생기고(`add_turn`) 답이나 실패로 닫힌다(`finish_turn`) — 스트림이 끊겨도 턴은 실패로 남아 다음 질문에 안 실린다
- 앞 대화는 서버가 대화에서 만든다. 같은 질문을 두 번 보내면 턴이 둘 생긴다
- **답은 원문으로 저장하고 내보낼 때 링크로 바꾼다**(#290) — 맨 `문서ID#항목ID`를 그 문서의 가장 긴 실제 항목까지 `[[…]]`로, 없는 것은 `missing_refs`. 대화를 다시 열 때(`GET /api/conversations/{id}` → [[SYNC-MS-008#queries.conversation_view]])도 같은 규칙이라 나중에 항목이 생기면 그때부터 링크가 산다
- 첨부는 업로드(별도 요청)와 질문(`attachment_ids`)이 나뉜다 — 드롭·붙여넣기 순간 올라가 칩이 되고, 보낼 때 턴에 붙는다. 이미지는 이 턴의 `user` 항목에 `images`로 실려 `llm.step`이 파트 배열로 옮긴다([[SYNC-MS-009#llm.step]]); 뒤 턴에는 다시 안 실린다. 글자·PDF는 `read_attachment`로
- `queries`가 어댑터를 직접 부르는 유일한 자리다([[SYNC-DOM-002]] 3.2). 도구 실행도 `queries`가 이미 가진 조회로 닫힌다 — 명세 쓰기가 없어 `pipeline`을 거칠 이유가 없다
- **모델이 고른 것만 읽는다.** 시작 맥락에는 본문이 없다. 상한은 호출 수(8)와 시간(120초)이지 글자가 아니다([[SYNC-INFRA-001]] 5.3)
- **첫 이벤트(`start`) 전의 오류는 HTTP 상태 코드**(404·503)이고, 뒤의 오류는 `error` 이벤트다. 라우터가 제너레이터를 한 번 당겨 `start`를 받은 뒤에야 스트림을 연다
- 항목은 힌트다. 없어도 문서 전체로 묻는다(1a). 항목 ID가 문서에 없으면 `start` 전에 `not-found`


---

## SEQ-25 지금 가져오기

[[SYNC-UC-001#UC-G2]]. UI-14 요소 6. 주기 확인을 기다리지 않고 사람이 당긴다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RA as routers/admin
    participant PS as ProjectService
    participant P as pipeline
    participant G as infra/git
    participant DB

    U->>RA: POST /api/admin/repos/{code}/sync
    RA->>PS: sync_now(code, user)
    PS->>P: read_pending(code, user)
    P->>P: get_owned · 읽기 락
    P->>G: fetch → head
    alt head == last_processed_commit (2a)
        P->>DB: repositories.fetched_at = now
        P-->>PS: 0
    else 밀린 커밋이 있다
        P->>P: process_commit(repo, head) — SEQ-2 9~20과 같다
        P->>DB: last_processed_commit · behind_by=0 · fetched_at
        P-->>PS: 읽은 문서 수
    end
    PS-->>RA: SyncResult {docs, fetched_at}
    RA-->>U: 「N개를 읽었습니다」 또는 「이미 최신」
```

**읽을 때 볼 것**
- **새 흐름을 만들지 않았다.** 본체는 카드 AD가 만든 `read_pending` 그대로다 — 소유 검사·읽기 락·`process_commit`이 이미 그 안에 있다. 이 시퀀스는 그것을 사람이 부를 수 있게 문 하나를 낸 것이다
- 읽을 것이 없어도 **`fetched_at`은 새로 적는다.** 「지금 확인했다」가 이 동작의 절반이다 — 화면이 그 시각을 보여주므로(UI-14 2.4) 사람은 「최신」이 언제 기준인지 알게 된다
- 통지(SEQ-2)가 걸려 있으면 이 버튼을 누를 일이 거의 없다. 통지를 못 건 저장소와 통지가 유실된 경우를 위한 길이다

---

## SEQ-26 코드 그래프를 만든다

[[SYNC-UC-001#UC-S8]]. 입구가 없다 — 커밋 처리(SEQ-2·SEQ-25)와 재구축(SEQ-21)이 끝난 뒤 `pipeline`이 걸어 두고, 저장소 락 밖에서 돈다.

```mermaid
sequenceDiagram
    autonumber
    participant P as pipeline
    participant G as infra/git
    participant CG as codegraph/graph.py
    participant GF as infra/graphify
    participant CS as CodeGraphService
    participant DB

    P->>G: changed_paths(workdir, last..head) — process_commit 5a
    P->>CG: touches_code(paths)
    P->>CS: get(project_id) — 그래프가 아직 없나
    alt 코드가 바뀌었거나 그래프가 없다
        P->>P: schedule_code_graph(code, head) — 돌고 있으면 「다음」만 적는다
        P->>G: archive(workdir, head, 임시 폴더)
        P->>CG: load(임시 폴더)
        alt 저장소에 graphify-out/graph.json이 있다
            CG-->>P: ("repo", 그 파일)
        else 없다
            CG->>GF: extract(임시 폴더) — 환경변수를 비우고, 모델 없이
            GF-->>CG: graph.json 원형
            CG-->>P: ("server", 원형)
        end
        P->>CG: reduce(원형) → enrich(임시 폴더, 그래프) — 함수·호출 선만, 파이썬 보강
        P->>CG: communities(원형, 그래프) — graphify 군집, 함수마다 커뮤니티 (카드 BD)
        P->>CS: save(project_id, head, source, graph)
        CS->>DB: code_graphs 한 행 교체 · error 비움
        P->>P: 로그 한 줄 · 임시 폴더 삭제 · 「다음」이 있으면 한 번 더
    else 명세만 바뀌었다
        P->>P: 건너뛴다 — 대조는 읽을 때 계산한다
    end
    Note over P,CS: 2~4 어디서 실패하든 CS.fail(project_id, head, 이유) — 옛 그래프는 그대로
```

**읽을 때 볼 것**
- **쓰기 락 밖이다.** 추출에 수 초가 걸려도 명세 저장과 따라잡기를 막지 않는다. 대신 같은 프로젝트의 만들기가 겹치지 않게 하나씩 돌리고, 밀리면 가장 최근 커밋 하나만 더 만든다
- **작업 사본에서 돌지 않는다.** `git archive`로 그 커밋을 풀어 쓴다 — 작업 사본을 더럽히지 않고, 빌드 산출물이 섞이지 않는다
- 대조 결과는 저장하지 않는다. 명세의 「호출하는 것」은 읽을 때 명세에서 가져오므로, 명세만 고친 커밋은 다시 만들 필요가 없다

---

## SEQ-27 코드 탭에서 항목의 코드를 대조한다

[[SYNC-UC-001#UC-H20]]. UI-5 8.17~8.22 · UI-8 2.6. **대조는 부를 때 계산한다** — 그래프(코드 쪽)는 SEQ-26이 만들어 두고, 「호출하는 것」은 명세에서 읽는다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RC as routers/code
    participant Q as queries
    participant PS as ProjectService
    participant S as SpecService
    participant CS as CodeGraphService
    participant CG as codegraph/graph.py
    participant G as infra/git

    U->>RC: GET /api/docs/{doc}/items/{item}/code — 코드 탭(8.17)
    RC->>Q: code_view(doc, item, user)
    Q->>PS: get_owned — 남의 것이면 not-found
    Q->>S: get_document · resolve_item
    Q->>CS: get(project_id) — 없으면 graph null (1a)
    Q->>S: list_by_project(MINISPEC) · get_document · item_blocks — 「호출하는 것」 줄
    Q->>CG: spec_calls(items) → compare(graph, spec)
    alt MINISPEC 항목
        Q-->>RC: CodeView {function: 부르는 것(코드만·명세만·같음) · 불리는 곳}
    else 다른 항목
        Q->>Q: item_chain(doc, item) — 하위 폐포의 MINISPEC 항목
        Q-->>RC: CodeView {functions: 항목마다 어긋남 수}
    end
    U->>RC: GET …/items/{item}/code/source — 코드 보기(8.21)를 펼칠 때
    RC->>Q: code_source(doc, item, user)
    Q->>CG: compare(graph, {항목}) — 그 항목의 함수 자리
    Q->>CS: read(project_id, workdir, 파일, 시작, 끝)
    CS->>G: read(workdir, 파일, 그래프 커밋) — 커밋된 파일만, 비밀 꼴 거부
    Q-->>U: CodeText (300줄까지)
    U->>RC: GET /api/projects/{code}/code-calls — 관계도 코드 호출(2.6)
    RC->>Q: code_calls(code, user) → compare → 선(같음·코드만·명세만)
```

**읽을 때 볼 것**
- 대조 결과는 어디에도 저장하지 않는다. 명세만 고친 커밋은 그래프를 다시 만들지 않아도 다음 조회부터 바뀐다
- 코드 본문은 그래프를 만든 커밋에서 읽는다 — 작업 사본이 앞서 있어도 그래프와 본문이 같은 시점이다

---

## SEQ-28 서버 저장 프로젝트를 만든다

[[SYNC-UC-001#UC-A1]] 기본 흐름 1~6(서버 저장), 확장 1a·3b. 웹(UI-3 2.7)이든 MCP(`init_project` storage=server)든 같다. GitHub 저장은 [[#SEQ-4]].

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람 또는 에이전트
    participant B as routers/projects 또는 mcp/tools
    participant PS as ProjectService
    participant G as infra/git
    participant P as pipeline
    participant DB

    U->>B: init(storage=server, code, name, import_existing)
    B->>PS: init_project(None, code, name, user, import_existing, storage=server)
    PS->>PS: storage가 STORAGE_MODES에 있나
    alt 켜지 않은 방식 (1a)
        PS-->>B: storage-unavailable {storage, enabled}
    end
    PS->>PS: code 형식 · 중복 (2a·2b — SEQ-4와 같다)
    PS->>PS: 보관본 찾기 ORIGINS_DIR/_archive/{code}-*.git
    alt 보관본 있음 (3b)
        alt import_existing=false
            PS->>G: 가장 최근 보관본의 문서 수
            PS-->>B: existing-specs {doc_count, archived_at}
        else import_existing=true (3b2)
            PS->>PS: 가장 최근 보관본을 ORIGINS_DIR/{code}.git으로 옮긴다
            PS->>G: clone(원본, workdir) — 토큰 없음
            PS->>DB: Project · Repository(storage=server)
            PS->>P: rebuild(code)
            P-->>PS: RebuildResult
        end
    else 없음 (기본 흐름 3)
        PS->>G: init_bare(ORIGINS_DIR/{code}.git) — main, 앞당김·삭제 거부
        PS->>G: clone(원본, workdir) — 토큰 없음
        PS->>DB: Project · Repository(storage=server)
        PS->>G: init_specs · commit_push("chore: init syncdoc") — 원격이 서버 안이라 토큰을 안 구한다
        alt push 실패 (4a)
            PS->>G: 작업 사본 · 새 원본 삭제
            PS-->>B: push-failed
        end
        PS->>DB: Repository.last_processed_commit = hash
    end
    PS-->>B: Project
    B-->>U: ProjectSummary (storage=server, remote_url 없음)
```

**읽을 때 볼 것**
- 통지(webhook)를 걸지 않는다 — 서버 저장소는 밖에서 바뀌지 않는다([[SYNC-INFRA-001]] 7장)
- 새로 만든 원본은 등록이 실패하면 지운다. 되살린 보관본은 실패하면 보관 폴더로 돌려놓는다 — 원본을 잃지 않는다
- 해제([[SYNC-UC-001#UC-H17]])는 거꾸로 원본을 보관 폴더로 옮긴다([[SYNC-MS-001#ProjectService.delete_project]])

---

## SEQ-29 서버 저장소가 git push를 받는다

[[SYNC-UC-001#UC-H21]] 기본 흐름 1~4, 확장 2a·2b·3a·3b. clone·fetch(`git-upload-pack`)도 같은 입구다 — 처리(8~9)만 없다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람의 git
    participant R as routers/git
    participant AS as AccountService
    participant PS as ProjectService
    participant G as infra/git
    participant P as pipeline

    U->>R: GET info/refs?service=git-receive-pack (Basic — 비밀번호 칸에 개인 토큰)
    R->>AS: authenticate_token(비밀번호 칸)
    alt 토큰 없음·틀림 (2a)
        R-->>U: 401 WWW-Authenticate Basic — git이 다시 묻는다
    end
    R->>PS: server_origin(code, user)
    alt 남의 것·GitHub 저장·없음 (2b)
        PS-->>R: not-found
        R-->>U: 404
    end
    R->>G: http_backend(ORIGINS_DIR, env, 본문) — 참조 광고
    G-->>U: 200 advertisement
    U->>R: POST git-receive-pack (팩)
    R->>G: http_backend — 본문을 다 넘긴 뒤 응답 머리
    Note over G: 되감기·삭제는 저장소 config가 거절 (3b)
    G-->>U: 200 receive-pack 결과
    R->>P: 응답 뒤 read_pending(code, user) — main만 따라간다 (3a)
    P->>P: process_commit — 명세 파일은 버전, 코드가 바뀌었으면 schedule_code_graph
```

**읽을 때 볼 것**
- 인증은 매 요청이다 — git은 요청마다 같은 Basic을 보낸다. 세션을 만들지 않는다
- 처리는 응답을 다 보낸 뒤다. 읽기가 실패하거나 연결이 끊겨도 폴링이 메운다([[SYNC-INFRA-001]] 7장)

---

## SEQ-30 에이전트가 코드를 올린다

[[SYNC-UC-001#UC-A10]] 기본 흐름 1~5, 확장 1a·2a·2b·3a.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트
    participant M as mcp/tools
    participant P as pipeline
    participant PS as ProjectService
    participant G as infra/git

    A->>M: upload_code(project_code, files, delete, message)
    M->>P: upload_code(code, files, delete, message, author)
    P->>PS: get_owned(code, user)
    alt GitHub 저장 (1a)
        P-->>M: storage-mismatch
    end
    P->>P: 한도(UTF-8 합 5MB · 500개) · 경로 검사 — 락 밖
    alt 넘음 (2a) · 거절 경로 (2b)
        P-->>M: upload-too-large · upload-path-refused (아무것도 안 올림)
    end
    P->>P: read_pending — 먼저 읽는다 (DEV-19)
    P->>G: 쓰기 락 안에서 commit_push(files, delete) — 경로 가드
    alt 내용이 같다 (3a)
        G-->>P: 지금 HEAD (커밋 없음)
    end
    P->>P: read_pending — 처리 지점 전진, 코드면 schedule_code_graph
    P-->>M: UploadResult(commit, changed, files, deleted)
    M-->>A: 결과
```

**읽을 때 볼 것**
- 명세 경로는 받지 않으므로 이 커밋이 버전을 만들지 않는다 — 처리는 처리 지점을 옮기고 코드 그래프만 건다

---

## SEQ-31 코드 그래프 노드를 본다

[[SYNC-UC-001#UC-H20]] 기본 흐름 5. UI-17. 함수 전부·호출 선·커뮤니티를 한 번에 받고, 배치는 브라우저가 한다. 커뮤니티는 SEQ-26이 만들 때 붙였다 — 읽을 때 계산하지 않는다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RC as routers/code
    participant Q as queries
    participant PS as ProjectService
    participant CS as CodeGraphService
    participant S as SpecService
    participant CG as codegraph/graph.py

    U->>RC: GET /api/projects/{code}/code-graph — UI-4 2.3 · UI-5 8.23
    RC->>Q: code_nodes(code, user)
    Q->>PS: get_owned — 남의 것이면 not-found
    Q->>CS: get(project_id)
    alt 그래프 없음 (1a)
        Q-->>RC: CodeNodes {graph: null, 빈 목록}
    end
    Q->>S: list_by_project(MINISPEC) · get_document · item_blocks — 「호출하는 것」 줄
    Q->>CG: spec_calls(items) → compare(graph, spec) — 함수 key → 항목·상태
    Q->>S: list_by_project(DOM) · get_document — 클래스 명세 「폴더 구조」 절 (카드 BM)
    Q->>CG: layer_table(body) → layers(graph, rows) — 항목 없는 함수 key → 층
    Q-->>RC: CodeNodes {communities, functions(community·item·ms·status·layer), calls}
    RC-->>U: 응답 (수백 KB, 한 번)
    U->>U: 브라우저가 커뮤니티로 접어 d3-force로 배치하고 canvas에 그린다
    opt 함수를 고르면 — 패널 4.6 코드 (카드 BF)
        U->>RC: GET /api/projects/{code}/code/source?file&line
        RC->>Q: code_text(code, file, line, user)
        Q->>CS: get(project_id) → functions에서 file·line → read(workdir, file, start, end) — 그래프 커밋의 저장소
        Q-->>RC: CodeText (300줄까지 · 못 읽으면 not-found file)
        U->>RC: GET /api/docs/{doc}/items/{item}/references — 함수에 항목이 있을 때, SEQ-13과 같다 (패널 4.7 명세, 카드 BG)
    end
    opt 「코드 탭으로」(4.4)
        U->>RC: UI-5 코드 탭 — SEQ-27
    end
```

**읽을 때 볼 것**
- 대조 상태는 SEQ-27과 같은 `compare`다 — 코드 탭과 그림이 같은 판정을 보인다
- **층은 볼 때 명세에서 읽는다**(카드 BM) — 「호출하는 것」처럼 클래스 명세의 층 표만 고쳐도 다음 요청부터 바뀐다. 그래프에 저장하지 않는다
- 옛 그래프(커뮤니티 없음)는 `communities`가 비고 함수의 `community`가 null — 화면이 전부 펼쳐 보이고 다음 코드 push가 채운다(5a)
- **코드는 고를 때 읽는다**(카드 BF) — 함수 하나를 고를 때마다 `code/source` 한 번. 코드 탭 8.21과 같은 `CodeGraphService.read`라 둘이 같은 본문을 보인다. 파일 트리(6)는 `code_nodes`의 `functions[].file`로 브라우저가 만든다 — 요청이 없다. 항목 없는 함수의 「가까운 항목」도 `calls`와 `functions[].ms`로 브라우저가 센다(카드 BG)

---

## SEQ-C1 공통 형태 — 입구 → 서비스 하나 → DB

그려서 확인한 결과 정말로 묶음을 안 넘는 것들. 그림 하나로 대신한다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant B as 라우터
    participant SV as 서비스 하나
    participant DB

    U->>B: 요청
    B->>SV: 메서드(인자)
    SV->>DB: 조회 또는 갱신
    alt 없음
        SV-->>B: NotFound
        B-->>U: 404
    end
    SV-->>B: 결과
    B-->>U: 응답
```

| 입구 | 서비스.메서드 | 비고 |
|---|---|---|
| GET /auth/github | (라우터만) | state 생성, 302 |
| POST /auth/logout | (라우터만) | 세션 삭제 |
| GET /api/docs/{docId}/versions | SpecService.list_versions | `versions ∪ status_changes` 시각순 — 한 서비스 안이지만 두 테이블 |
| GET /api/me | (세션 User — 폐쇄망판은 로컬 사용자, [[#SEQ-C3]]) | `edition`·`storage_modes`는 설정 |
| GET /specs/{path} | (라우터만) | 이미지 안 `STD/`·`_templates/`만. 파일은 글자, 폴더는 목록. 공개 |
| GET /api/me/tokens | AccountService.list_tokens | 폐기된 것 포함 |
| POST /api/me/tokens | AccountService.issue_token | raw 생성 → sha256 저장 → raw는 응답에만 |
| DELETE /api/me/tokens/{id} | AccountService.revoke_token | 본인 것만. 아니면 404 |
| GET /api/projects/{code}/files/{path} | ProjectService.asset_path | 작업 사본 `docs/specs/` 아래만, 소유 검사. DB는 `get_owned`뿐, 파일은 디스크 |

**읽을 때 볼 것**
- 여기 있는 것은 전부 서비스 하나만 부른다. 두 번째 서비스가 필요해지는 순간 고유 시퀀스로 옮긴다
- `GET /api/docs/{docId}`는 처음엔 여기 넣으려 했으나 미존재 참조 뱃지 때문에 SEQ-11로. `GET /api/projects`도 건수 때문에 SEQ-9로

---

## SEQ-C2 공통 형태 — MCP 인증

모든 MCP 도구 호출 앞에 붙는다. SEQ-1·10·11·12·13·19에서 생략한 부분.

```mermaid
sequenceDiagram
    autonumber
    actor A as 에이전트
    participant M as mcp 서버
    participant AS as AccountService
    participant DB

    A->>M: POST /mcp (Authorization: Bearer raw) {tool, args}
    M->>AS: authenticate_token(raw)
    AS->>AS: sha256(raw)
    AS->>DB: access_tokens where token_hash and revoked_at is null and (expires_at is null or > now)
    alt 없음 · 폐기 · 만료
        AS-->>M: None
        M-->>A: isError {type: unauthorized}
    end
    AS->>DB: users where id
    AS-->>M: User
    M->>M: author = Author(kind=agent, user, instructed_by=user, via=mcp)
    M->>M: 도구 실행 (SEQ-xx)
```

**읽을 때 볼 것** — 토큰 원문은 요청 헤더에만 있고 서버 어디에도 안 남는다. 로그에도 남기지 않는다 → MINISPEC.

---

## SEQ-C3 공통 형태 — 폐쇄망판 웹 요청

폐쇄망판([[SYNC-PRD-001#R15]])의 모든 웹 요청 앞에 붙는다. 인터넷판의 세션 확인 자리다. 로그인이 없으니 **누가** 부르는지가 아니라 **어디서** 부르는지를 본다([[SYNC-INFRA-001]] 5장).

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant W as web 가드
    participant B as 라우터
    participant AS as AccountService
    participant DB

    U->>W: 요청 (Host, Origin)
    alt Host가 허용 목록 밖
        W-->>U: 403 forbidden-origin {host}
    end
    alt 쓰기 요청(POST·PUT·PATCH·DELETE)인데 Origin이 있고 이 서버가 아니다 — /mcp·/git은 보지 않는다
        W-->>U: 403 forbidden-origin {origin}
    end
    W->>B: 요청
    B->>AS: local_user()
    AS->>DB: users where kind=local
    AS-->>B: User
    B->>B: 그 입구의 흐름 (SEQ-xx) — 이 사람으로
    B-->>U: 응답
```

**읽을 때 볼 것** — 허용 목록은 `127.0.0.1`·`localhost`·`[::1]`과 `PUBLIC_BASE_URL`의 host다(포트는 보지 않는다). 127.0.0.1에만 열어도 가드가 필요하다 — 다른 사이트가 제 이름을 127.0.0.1로 풀리게 바꿔(DNS rebinding) 내 브라우저로 부르면 Host가 그 이름이라 여기서 막힌다. Origin 확인은 다른 사이트의 폼·fetch가 보내는 쓰기(CSRF)를 막는다 — 본문 없는 POST(되돌리기·재구축)는 미리 묻는 요청(preflight)도 없다. MCP·git은 토큰이 사람을 정하므로([[#SEQ-C2]]·[[#SEQ-29]]) Host만 본다.

---

## SEQ-32 코드 그래프에서 묻는다

[[SYNC-UC-001#UC-H19]] 기본 흐름 1~2(코드 그래프), 확장 1b·2b. `POST /api/projects/{code}/code/ask` — SSE. **루프는 SEQ-24와 같다** — 입구와 시작 맥락만 다르고, 도구 여덟·상한·대화 저장·이벤트 여섯은 그대로다(카드 BI).

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람
    participant RCG as routers/code
    participant Q as queries
    participant C as ConversationService
    participant CS as CodeGraphService
    participant S as SpecService
    participant LLM as infra/llm

    U->>RCG: POST /api/projects/{code}/code/ask {conversation_id, question, key?, attachment_ids} — UI-17 질문 열(7, 좁은 화면은 탭)
    RCG->>Q: ask_code(code, key, conversation_id, question, attachment_ids, user)
    Q->>Q: 키 없으면 llm-not-configured · get_owned
    Q->>C: get · history · add_turn (SEQ-24와 같다)
    Q->>CS: get(project_id) — 없으면 「코드 그래프 없음」 한 줄 (2b)
    Q->>S: list_by_project + describe_documents — 문서 목록(ID·제목·상태, 본문 없음)
    Q->>Q: key로 함수 → compare로 항목·대조 상태, 부르는 것·불리는 곳(각 20까지) → 시작 맥락. key가 그래프에 없으면 not-found function
    Q-->>RCG: start {doc_id: null, item_id: null, key}
    RCG-->>U: 200 text/event-stream
    loop SEQ-24의 루프 그대로 — _ask_loop
        Q->>LLM: step_stream(system, 대화록, tools)
        Q-->>U: delta · note · read … answer | error
    end
```

**읽을 때 볼 것**
- 입구가 둘(문서·코드 그래프)이고 그 뒤는 하나다 — `_ask_loop`. 대화는 프로젝트 것이라 문서에서 묻다 그래프로 와도 이어진다
- 시작 맥락에 함수 본문을 싣지 않는다 — 문서 본문을 안 싣는 것과 같은 원칙(사용자 결정 3). 모델이 `read_code`로 읽는다

---

## SEQ-33 GitHub 저장 프로젝트를 서버 저장으로 옮긴다

[[SYNC-UC-001#UC-H22]] 기본 흐름 1~7, 확장 2a~2c·4a·5a. `POST /api/admin/repos/{code}/move-to-server` — 화면이 없다(카드 BQ). **쓰기와 읽기를 함께 막고** 옮긴다 — 저장(`save_pipeline`)과 fetch(폴링·웹훅)가 끼어들면 옛 원격과 새 원격 사이에서 커밋이 샌다.

```mermaid
sequenceDiagram
    autonumber
    actor U as 사람(소유자)
    participant RA as routers/admin
    participant P as pipeline
    participant PS as ProjectService
    participant AS as AccountService
    participant G as infra/git
    participant GHI as infra/github
    participant DB

    U->>RA: POST /api/admin/repos/{code}/move-to-server
    RA->>P: move_to_server(code, user)
    P->>PS: get_owned(code, user) — 남의 것이면 not-found (2a)
    alt 이미 서버 저장 (2b)
        P-->>U: 409 storage-mismatch
    end
    P->>P: 자리 ORIGINS_DIR/{code}.git — 있으면 409 origin-exists (2c, 아무것도 안 지운다)
    P->>AS: github_token_for(user)
    P->>P: 읽기 락 → 쓰기 락
    P->>G: fetch(workdir, user) — 작업 사본을 원격 최신으로
    P->>G: clone_bare(remote_url, origin, token) — 가지·태그, 토큰은 남기지 않는다
    P->>G: rev_list_count(origin, 처리 지점) — 복제본에 있나
    alt 복제 실패 · 처리 지점 없음 (4a)
        P->>P: origin 지움 → 424 push-failed
    end
    P->>PS: remove_hook(code, user)
    PS->>GHI: delete_hook(token, owner, name, hook_id) — 실패는 상태로 (5a)
    P->>G: set_origin(workdir, origin) · fetch(workdir)
    P->>DB: repositories storage=server · remote_url=origin · hook 칸 비움
    P-->>RA: MoveResult {origin, head, hook}
    RA-->>U: 200
```

**읽을 때 볼 것**
- **DB는 건드리지 않는다** — 버전·상태 이력·대화·코드 그래프가 커밋 해시에 기대는데, 복제가 해시를 그대로 옮기므로 그대로 맞는다. 저장소 행의 저장 방식·원격·통지 칸만 바뀐다
- 락 순서는 읽기 → 쓰기 — `process_commit`(읽기 락)이 `save_pipeline`(쓰기 락)을 부르는 것과 같은 순서라 엇갈려 막히지 않는다
- 옮긴 뒤로는 그 프로젝트가 서버 저장이다 — 쓰기는 서버 저장소로, 코드는 git 입구로 push한다([[#SEQ-29]]). GitHub 저장소 보관(비공개·archive)은 운영이 한다

---

## 2. 되먹일 것

시퀀스를 그려서 드러난 구멍. **클래스 명세 v3, ERD·DD, API, 인프라, 와이어프레임에 반영했다** (#22는 다른 문서에서 닫혔다 — 아래 미결사항). 이 절은 v3가 왜 그렇게 됐는지의 기록이다. **기록이라 고치지 않는다** — `TrackingService`·`CommentService`와 그 메서드(#5·#15·#19·#20·#21)는 v2에서 걷어냈고 지금 코드에 없다.

### 저장 파이프라인 (v1.0에서 발견)

| # | 발견 | 고칠 문서 | 내용 |
|---|---|---|---|
| 1 | `pipeline`이 `SpecService.get_document`를 부른다 (doc_type·현재 버전) | 클래스 3.2 | 화살표 추가 |
| 2 | 삭제 확인을 `pipeline`이 한다. `SpecService`는 하위 참조를 모른다 | 클래스 4.2 | `sync_items` → `detect_deleted_items(document, body) list~int~`. `save`는 `deleted_item_pks`를 받아 `is_deleted`만 찍는다 |
| 3 | **push가 DB 트랜잭션 앞이다.** 실패 시 롤백할 게 없다 | 클래스 4.7, 6장 | "검증·버전검사·삭제검사 → push → 한 트랜잭션(save·extract·detect·relocate)" |
| 4 | 저장은 **저장소 단위 락** | 클래스 4.7, 인프라 4.2 | `pipeline`이 repo lock. 프로세스 내 락으로 충분 |
| 5 | `raise_flags`가 담당자를 정하려고 `SpecService.last_author(document_id)` | 클래스 3.2, 4.2 | 추가 |
| 6 | **상태 변경은 Version을 만들지 않는다.** `StatusChange`가 커밋을 갖는다 | ERD·DD, 클래스 4.2 | `status_changes.commit_hash`. `list_versions`·`recent_changes`는 두 테이블 합침 |
| 7 | `save_pipeline`의 `entry=web_status` 경로 | 클래스 4.7 | validate·push·StatusChange만 |
| 8 | GitHub 커밋 작성자가 미등록일 수 있다 | 클래스 4.6, ERD | **결정: 커밋 이메일 → login → 자리표시.** `commit_emails` 신설, `AccountService.user_for_commit`. 자리표시면 `author.unknown`으로 승인만 막는다 |
| 9 | 밀린 커밋 여럿은 최종 상태만 저장 | 인프라 7장 | 명시. 재구축(SEQ-21)은 커밋마다 |
| 10 | 되돌리기가 삭제를 일으키는데 웹 API에 `confirm`이 없다 | API REST, UI-7 | `POST /revert`에 `confirm_item_deletion`. UI-7 확인 다이얼로그 |
| 11 | `save_pipeline(entry=github)`는 `commit_hash`를 갖고 들어온다 | 클래스 4.7 | 인자 추가 |

### 읽기 집계 (v1.1에서 발견)

| # | 발견 | 고칠 문서 | 내용 |
|---|---|---|---|
| 12 | **읽기에서 묶음을 넘는 조합이 9곳이다.** 서비스끼리 부르면 3.2 의존 그림이 거미줄이 된다 | 클래스 1장, 3.2, 4장 | **`core/queries.py` 신설.** `pipeline`이 쓰기 조율자면 `queries`는 읽기 조합자. 묶음 밖에 두고 여러 서비스를 ID로 부른다. 라우터·MCP 도구는 집계가 필요하면 `queries`를, 아니면 서비스를 직접 부른다. 함수: `project_summary` `project_detail` `document_list` `document_view` `item_view` `item_references_view` `graph_view` `diff_with_impact` `todo` `project_items` |
| 13 | `ProjectService`가 `documents` 테이블을 알면 안 된다 | 클래스 4.1·4.2 | `SpecService.list_by_project(project_id, stage?, status?, has_convention_error?)` 추가. `get_stage_summary`는 `queries`로 이동 |
| 14 | `ReferenceService`는 pk만 안다. 표시용 이름이 없다 | 클래스 4.2·4.3 | `SpecService.describe_items(pks) dict`, `resolve_item(doc_id, item_id) int`, `list_items_by_project(...)`, `neighbors(doc_id)` 추가. `ReferenceService.references_among(pks)`, `count_downstream(pks)` 추가 |
| 15 | `CommentService.add`가 본문을 직접 읽으면 안 된다 | 클래스 4.5 | `add(document_id, line_no, line_text, body, user, parent_id)` — `line_text`를 인자로 |
| 16 | 파일 경로 규약이 없다 | 인프라 4.3, PRD R5 | `docs/specs/{TYPE}/{doc_id}.md`. `_templates/`, `assets/` |
| 17 | 생성 시 frontmatter를 서버가 채운다 | 클래스 4.2 | `SpecService.apply_frontmatter(body, doc_id, doc_type, status) str` |
| 18 | 재구축이 `items`를 지우면 플래그가 끊긴다 | 클래스 4.7 rebuild, ERD | `items`는 upsert. `versions`·`references`만 지운다 |
| 19 | `TrackingService`에 집계용 메서드가 없다 | 클래스 4.4 | `count_flags(project_id)`, `count_flags_by_document(ids)`, `flags_for_items(pks)`, `flags_for_assignee(user_id)`, `flags_unassigned()`, `flags_in_project(project_id, kind)`, `pending_decisions_for(user_id)` |
| 20 | `CommentService`에 집계용 메서드가 없다 | 클래스 4.5 | `count_unresolved(project_id)`, `count_unresolved_by_document(ids)`, `unresolved_in(doc_ids)` |
| 21 | `SpecService`에 내 할 일용 조회가 없다 | 클래스 4.2 | `versions_instructed_by(ids, user_id)`, `convention_error_docs_by(user_id)`, `documents_authored_by(user_id)`, `recent_changes(project_id, n)` |
| 22 | `ProjectService.repo_status`가 저장소마다 fetch한다 | 인프라 7장, 클래스 4.1 | 폴링이 `behind_by`를 DB에 갱신하고 화면은 읽기만 — **미결** |

**12번이 v1.1의 핵심이야.** v1.0 되먹임이 "쓰기 조율은 pipeline이 한다"였다면, v1.1은 "읽기 조합은 queries가 한다"다. 둘 다 묶음 밖에 있고, 그래서 서비스는 자기 묶음만 알면 된다. 3.2 의존 그림에 서비스→서비스 화살표가 `TrackingService → ReferenceService·SpecService` 둘만 남는다(detect_impact·raise_flags). 나머지는 전부 `pipeline`이나 `queries`를 거친다.

---

## 3. 미결사항

- [x] #8 — 미등록 GitHub 사용자의 push — 결정: 커밋 이메일(`commit_emails`)로 먼저 잇고, 못 찾으면 `github_login`, 그것도 없으면 자리표시 User + `author.unknown`으로 승인만 막는다. git 커밋이 남기는 신원 중 계정으로 이어지는 것은 이메일뿐이다. 앞으로의 커밋은 GitHub 메일 비공개(noreply)로 로그인 ID가 바로 잡힌다. 이미 쌓인 것은 인덱스 재구축으로 옮긴다 ([[SYNC-DOM-002]] 5장 결정 3, [[SYNC-MS-006#AccountService.user_for_commit]])
- [x] #4 — 락 범위. 저장소 단위 vs 문서 단위 — 결정: 저장소(프로젝트 코드) 단위. `core/pipeline.py`의 `_lock(code)`. 파일 단위로 좁히는 건 경합이 실제로 보일 때 ([[SYNC-DOM-002]] 7장에서 이미 닫힌 것의 사본이었다)
- [x] #22 — 저장소 동기화 상태를 실시간 fetch할지 캐시할지 — 결정: DB에서 읽는다. 폴링이 `behind_by`·`fetched_at`을 갱신하고 `repo_status`는 조회만 ([[SYNC-MS-001#ProjectService.repo_status]]에서 이미 닫힌 것의 사본이었다)
- [x] SEQ-12 항목 블록 경계 — 문서 타입별 헤더 형식. 템플릿 규약과 함께 — 결정(2026-09-30): 타입별 헤더 형식은 두지 않는다. [[SYNC-STD-001]] 1.3 하나로 모든 타입을 가른다 — ID로 시작하는 헤딩이 항목이고 레벨은 상관없으며, 다음 같은 레벨 이상 헤딩까지가 블록이다. 코드(`item_blocks`)도 그렇게 동작한다
