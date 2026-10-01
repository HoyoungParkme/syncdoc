---
doc_id: SYNC-DOM-003
type: DOM
title: ERD·DD — 싱크독
status: draft
upstream: [SYNC-DOM-002, SYNC-DOM-001]
---

# ERD·DD: 싱크독 (SyncDoc)

---

## 0. 이 문서가 다루는 것

클래스 명세의 엔티티 클래스를 **테이블**로 옮긴다. ERD는 그림, DD는 컬럼마다 의미·타입·제약을 적은 설명서다. 둘은 한 세트다.

ORM 모델 = 도메인 객체로 정했으므로 이 문서의 테이블은 [[SYNC-DOM-002]]의 엔티티 클래스와 1:1이다. 클래스가 바뀌면 이 문서도 같이 고친다.

**전제**
- 기본키는 대리키(int 자동 증가). 사람이 부르는 ID는 unique 제약
- 버전 테이블에 본문 전체를 둔다
- 열거형은 DB enum이 아니라 varchar + 앱 검증
- 알림 테이블 없음

---

## 1. ERD

```mermaid
erDiagram
    projects ||--|| repositories : has
    projects ||--o{ documents : contains
    documents ||--o{ items : contains
    documents ||--o{ versions : history
    documents ||--o{ status_changes : history
    items ||--o{ references : from
    items ||--o{ references : to_item
    documents ||--o{ references : to_document
    users ||--o{ versions : author
    users ||--o{ versions : instructed
    users ||--o{ status_changes : changed_by
    users ||--o{ access_tokens : owns
    users ||--o{ commit_emails : owns
    users ||--o{ projects : owns
    projects ||--o{ conversations : keeps
    users ||--o{ conversations : owns
    conversations ||--o{ turns : ordered
    conversations ||--o{ attachments : holds
    turns |o--o{ attachments : attached
    projects ||--o| code_graphs : graphed

    projects {
        int id PK
        varchar code UK
        varchar name
        int owner_user_id FK
        timestamptz created_at
    }
    repositories {
        int id PK
        int project_id FK,UK
        varchar storage
        varchar remote_url
        varchar workdir_path
        varchar last_processed_commit
        int registered_by_user_id FK
        timestamptz synced_at
        varchar fetch_error
        int hook_id
        varchar hook_error
    }
    documents {
        int id PK
        int project_id FK
        varchar doc_id UK
        varchar doc_type
        varchar status
        text current_body
        int current_version_no
        boolean has_convention_error
        text convention_error_detail
        text incomplete_warnings
        timestamptz updated_at
    }
    items {
        int id PK
        int document_id FK
        varchar item_id
        varchar display_name
        boolean is_deleted
        timestamptz deleted_at
    }
    versions {
        int id PK
        int document_id FK
        int version_no
        varchar commit_hash
        text body
        varchar author_kind
        int author_user_id FK
        int instructed_by_user_id FK
        varchar via
        text message
        timestamptz created_at
    }
    status_changes {
        int id PK
        int document_id FK
        varchar from_status
        varchar to_status
        int changed_by_user_id FK
        text reason
        varchar commit_hash
        timestamptz changed_at
    }
    references {
        int id PK
        int from_item_id FK
        int from_document_id FK
        int to_item_id FK
        int to_document_id FK
        varchar raw_target
        boolean is_missing
        int extracted_version_id FK
    }
    users {
        int id PK
        varchar github_login UK
        bigint github_user_id UK
        varchar kind
        varchar display_name
        bytea github_token_encrypted
        timestamptz created_at
    }
    commit_emails {
        int id PK
        int user_id FK
        varchar email UK
        timestamptz added_at
    }
    access_tokens {
        int id PK
        int user_id FK
        varchar token_hash UK
        varchar label
        timestamptz issued_at
        timestamptz expires_at
        timestamptz revoked_at
    }
    conversations {
        int id PK
        int project_id FK
        int user_id FK
        varchar title
        timestamptz created_at
        timestamptz updated_at
    }
    turns {
        int id PK
        int conversation_id FK
        int seq
        text question
        text answer
        jsonb progress
        jsonb context_item_ids
        varchar error
        timestamptz created_at
    }
    attachments {
        int id PK
        int conversation_id FK
        int turn_id FK
        int user_id FK
        varchar name
        varchar mime
        int size
        bytea bytes
        text text_cache
        timestamptz created_at
    }
    code_graphs {
        int project_id PK,FK
        varchar commit_hash
        varchar source
        jsonb graph
        int function_count
        int call_count
        timestamptz built_at
        varchar error
    }
```

**설계 규칙**
- 모든 테이블 PK는 `int` 자동 증가. 사람이 부르는 ID(`doc_id`, `item_id`, `code`)는 UK
- 시각은 전부 `timestamptz`
- 열거형은 DB enum이 아니라 `varchar` + 앱 검증. 값 추가 시 마이그레이션을 피하기 위해서
- 삭제 컬럼은 `items`에만 있다. 문서·버전은 삭제하지 않는다 — 문서는 `documents.trashed_at`으로 **휴지통**에 넣는다(행은 남는다). **행까지 지우는 것**은 휴지통 안에서 다른 문서가 가리키지 않을 때만([[SYNC-MS-002#SpecService.delete_document]]) — 그 문서에 딸린 상태변경은 같이 지운다
- **대화 세 표(`conversations`·`turns`·`attachments`)는 명세 표와 선이 없다.** `projects`·`users`를 FK로 가리킬 뿐 `documents`·`items`를 가리키지 않는다 — 문서 ID는 턴의 글자 속에만 있다. 재구축이 건드리지 않고, 프로젝트 행이 지워지면(`ProjectService.delete_project`) `ON DELETE CASCADE`로 함께 사라진다. 대화를 지우면 턴·첨부도 같은 cascade. 리비전 `0014_conversations`가 세 표를 한 번에 만든다(카드 AQ) — 첨부 행은 AR가 채우지만 표는 대화와 같이 있어야 대화 조회가 한 모양이다
- **`code_graphs`는 명세 표와 선이 없다**(카드 AX). `projects`만 가리키고 PK가 곧 `project_id`라 프로젝트마다 한 행이다. 항목 ID는 `graph` 안의 글자다. 재구축이 지우지 않는다 — 재구축 뒤 새로 만들어 바꿔 끼운다([[SYNC-UC-001#UC-S8]])
- **재구축(UC-S6)은 `versions`·`references`만 지운다.** `documents`·`items`는 지우지 않는다 — 항목 ID 재사용 금지의 근거(`items.is_deleted`)와 휴지통 상태(`documents.trashed_at`)가 거기 산다. `items`는 upsert
- 상태 변경은 `versions` 행을 만들지 않는다. `status_changes.commit_hash`가 그 커밋을 가리킨다
- `references`의 `to_item_id`와 `to_document_id`는 CHECK로 하나만 채워지게 한다. `is_missing=true`면 둘 다 null
- **끊어진 참조는 별도 표가 아니다.** 대상 항목이 삭제되면 그것을 가리키던 참조의 `to_*`를 비우고 `is_missing=true`로 되돌린다([[SYNC-MS-003#ReferenceService.mark_missing]]). `raw_target`이 남아 있어 상대가 돌아오면 `resolve_missing`이 다시 잇는다. v1의 `flags`·`propagation_decisions`·`comments`는 v2에서 뺐다([[SYNC-DOM-001]] 3.3) — 리비전 0011이 세 표를 지운다. `downgrade`는 0001·0007·0008의 정의를 복원하지만 데이터는 돌아오지 않는다. 옛 행은 각 저장소의 `backup/tracking.json`과 태그 `v1-collab`의 `import_tracking`으로만 되살릴 수 있다
- **`repositories.hook_id`·`hook_error`는 리비전 `0013_add_repo_hook`이 둘 다 nullable로 더한다**(카드 AF). 기본값 없이 비운 채 시작한다 — 「아직 안 걸어 본 것」이 맞는 초기 상태다. `downgrade`는 두 컬럼을 지운다
- **`users.kind`는 리비전 `0017_add_users_kind`가 기본 `github`로 더하고, `github_user_id`가 빈 행을 `placeholder`로 채운다**(카드 BC). 그때까지 자리표시를 `github_user_id IS NULL`로 가렸으므로 그 판정을 그대로 옮긴 것이다. `downgrade`는 컬럼을 지운다 — 로컬 사용자 행은 다시 자리표시처럼 보인다
- **`repositories.storage`는 리비전 `0016_add_repositories_storage`가 `server_default 'github'`로 더한다**(카드 BA). 그때까지의 저장소는 전부 GitHub라 기본값이 곧 백필이다. `downgrade`는 컬럼을 지운다 — 서버 저장 행이 있으면 그 행의 `remote_url`이 서버 안 경로라 뜻이 어긋나므로, 내리기 전에 서버 저장 프로젝트를 해제해야 한다
- **소유는 `projects.owner_user_id` 한 컬럼이다.** 별도 권한 표가 없다. 리비전 `0012_add_projects_owner`가 nullable로 더하고 `repositories.registered_by_user_id`(없으면 `min(users.id)`)로 채운 뒤 not null·FK로 조인다(0004 선례). `downgrade`는 컬럼을 지운다

---

## 2. DD (데이터 사전)

주요 컬럼만. 이름으로 뜻이 드러나는 것(`created_at`, `*_user_id`)은 뺐다.

### projects

클래스: [[SYNC-DOM-002#Project]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| code | varchar(4) | UK, `^[A-Z]{1,4}$` | 프로젝트 코드. 문서 ID 앞부분 | `SYNC` |
| name | varchar(100) | not null | 표시 이름 | `싱크독` |
| owner_user_id | int | FK not null | **소유자.** 등록한 사람이고 바뀌지 않는다([[SYNC-PRD-001#R12]]). 소유자가 아니면 이 프로젝트는 목록에도 없고 주소로 열어도 not-found — `ProjectService.get_owned`가 이 컬럼 하나로 판정한다. 자리표시 User는 앉을 수 없다(등록에 토큰이 필요). `repositories.registered_by_user_id`와 값이 같아도 뜻이 다르다([[SYNC-DOM-002]] 5장 결정 6) | |

### repositories

클래스: [[SYNC-DOM-002#Repository]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| storage | varchar(8) | not null, 기본 `github` | **저장 방식** — `github` 또는 `server`([[SYNC-PRD-001#R14]]). 만들 때 정하고 바뀌지 않는다 | `server` |
| remote_url | varchar(300) | not null | 원격. GitHub 저장이면 GitHub 저장소 주소, 서버 저장이면 **서버 안 원본의 경로**(`ORIGINS_DIR/{코드}.git`) — 이 경로는 입구가 밖으로 내보내지 않는다 | `https://github.com/dfocus/syncdoc` · `/var/syncdoc/origins/ABC.git` |
| workdir_path | varchar(300) | not null | 노트북의 작업 사본 경로 | `/var/syncdoc/repos/SYNC` |
| last_processed_commit | varchar(40) | null 허용 | 파이프라인이 마지막으로 처리한 커밋. 밀린 커밋 따라잡기 기준 | `a1b2c3…` |
| registered_by_user_id | int | FK not null | **push 토큰의 주인**(서버 저장은 토큰이 없어 등록한 사람을 적을 뿐). GitHub 경로 자동 강등 커밋을 이 사람 토큰으로 민다. private 저장소를 지원할 때 fetch에 쓸 토큰의 주인이기도 하다. 소유자가 아니다 — 소유는 `projects.owner_user_id` — 폴링·재구축은 요청한 사람이 없거나 다른 사람일 수 있다. **v1은 public만 쓰므로 fetch에 토큰이 필요 없다**(MS-009 미결) | |
| synced_at | timestamptz | null 허용 | 마지막으로 원격을 받아온 시각. 폴링이 갱신 | |
| behind_by | int | null 허용 | 원격이 앞선 커밋 수. 0이면 최신, null이면 아직 못 받아봄 | `0` |
| fetched_at | timestamptz | null 허용 | `behind_by`를 잰 시각. 화면이 "언제 기준인지" 보여준다 | |
| fetch_error | varchar(300) | null 허용 | **마지막 폴링이 실패한 이유.** 성공하면 비운다. 폴링은 저장소 하나가 죽어도 다음을 계속하고 로그만 남기므로([[SYNC-MS-007#scheduler.catch_up]]), 이 값이 없으면 **사람은 「아무도 push를 안 했나 보다」로 읽는다**(#46) | `git rev-parse origin/main: fatal…` |
| hook_id | int | null 허용 | **GitHub이 준 push 통지 번호**(카드 AF). 있으면 이 저장소에 통지가 걸려 있다 — 반영이 몇 초다. 없으면 주기 확인(최대 5분)에만 기댄다. 앱은 만들기만 하고 지우지 않는다 | `512345678` |
| hook_error | varchar(300) | null 허용 | **통지를 걸지 못한 이유.** 권한이 없거나(`admin:repo_hook`), 공개 주소·비밀번호가 비었거나, GitHub이 거절했을 때. 성공하면 비운다. 이 값이 없고 `hook_id`도 없으면 **아직 안 걸어 본 것**이다 | `admin:repo_hook 권한이 없다` |

### documents

클래스: [[SYNC-DOM-002#Document]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| doc_id | varchar(30) | UK | 사람이 부르는 문서 ID | `SYNC-PRD-001` |
| doc_type | varchar(10) | DocType 중 하나 | 11단계 타입 코드 | `PRD` |
| status | varchar(10) | DocStatus (`draft` · `approved`) | frontmatter의 status와 같아야 한다. DB는 사본 | `approved` |
| current_body | text | not null | 현재 버전 본문 캐시. `versions.body`와 같다. **조회용이다 — 저장소에 쓸 본문의 출처로 쓰지 않는다**([[SYNC-STD-004#DEV-19]], #137) | |
| current_version_no | int | not null, ≥1 | 낙관적 잠금용. save 시 대조 | `7` |
| has_convention_error | boolean | default false | GitHub 경로로 들어온 규약 위반 문서 | |
| convention_error_detail | text | null 허용 | 어느 규약을 어떻게 어겼는지. STD-001 3장 rule | `frontmatter.field: status` |
| incomplete_warnings | text | null 허용 | 미완성 경고(STD-001 4장). 있으면 `approved` 불가. JSON 배열 | `["section.missing: 성공지표"]` |
| trashed_at | timestamptz | null 허용 | 휴지통에 넣은 시각. null이면 살아 있는 문서. 목록·단계 칸·그래프에서 빠지고 저장·상태 변경이 막힌다(`document-trashed`). 되살리면 null | |
| trashed_by_user_id | int | FK users, null 허용 | 누가 넣었나 | |

### items

클래스: [[SYNC-DOM-002#Item]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| item_id | varchar(50) | (document_id, item_id) UK | `#` 뒤 부분. 문서 내 유일 | `R12`, `POST/orders` |
| display_name | varchar(200) | null 허용 | 항목이 붙은 줄의 제목. 본문에서 추출 | `문서를 조회한다` |
| is_deleted | boolean | default false | 본문에서 사라진 항목. 행은 남긴다 — ID 재사용 금지 검증용 | |

### versions

클래스: [[SYNC-DOM-002#Version]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| version_no | int | (document_id, version_no) UK | 문서 안 순번. 1부터 | `7` |
| commit_hash | varchar(40) | not null | 이 버전을 만든 git 커밋 | |
| body | text | not null | 본문 전체. diff·되돌리기용 | |
| author_kind | varchar(10) | AuthorKind | 사람이 썼나 에이전트가 썼나 | `agent` |
| author_user_id | int | FK not null | 커밋 작성자. 에이전트면 토큰 발급자 | |
| instructed_by_user_id | int | FK null 허용 | 에이전트에게 시킨 사람. 사람이 직접 썼으면 null | |
| via | varchar(8) | not null | 어느 입구로 저장됐나 — `mcp` / `web`(되돌리기) / `github`. `Author.via`를 접은 것. 이력 화면이 구분한다. **`github`는 저장소로 들어온 커밋이다** — 서버 저장소의 git push도 같은 값이고, 화면이 저장 방식을 보고 「git push」로 적는다(카드 BB) | `web` |
| message | text | not null | 커밋 메시지 전문. 첫 줄 요약, 둘째 줄부터 이유(STD-001 1.7). git에도 있지만 이력 화면·최근 변경이 DB만으로 그리려고 사본 | `spec(SYNC-PRD-001): R12 …` |

### status_changes

클래스: [[SYNC-DOM-002#StatusChange]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| from_status | varchar(10) | DocStatus, null 허용 | 이전 상태. 문서 생성 시 첫 행은 null | `draft` |
| to_status | varchar(10) | DocStatus not null | 바뀐 상태 | `approved` |
| via | varchar(8) | not null, 기본 `web` | 어느 길로 바뀌었나 — `web`(토글) / `mcp`(에이전트 `change_status`, 카드 BE) / `github`(저장소로 들어온 `status(...)` 커밋 · 재구축). `versions.via`와 같은 값. `mcp`면 이력이 「에이전트 · 지시 {changed_by}」로 보인다. 자동 강등·휴지통·파일 삭제 행은 그 커밋이 들어온 길 | `mcp` |
| reason | text | null 허용 | 강등 사유 등. 완료 문서 수정으로 자동 강등되면 시스템이 채운다. 휴지통은 `휴지통`으로 적어 되살리기가 그 행의 커밋을 찾는다 | `본문 수정으로 자동 강등` |
| commit_hash | varchar(40) | null 허용 | 상태 변경으로 생긴 `status(...)` 커밋. 자동 강등(본문 커밋에 딸림)이면 null. 이력 화면이 `versions`와 합쳐 보여준다 | |

### references

클래스: [[SYNC-DOM-002#Reference]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| from_item_id | int | FK null 허용 | 참조를 적은 항목 (하위). 항목 밖(절 본문)이나 frontmatter `upstream`이면 null | |
| from_document_id | int | FK not null | 참조가 있는 문서. `from_item_id`가 null일 때 출발점 | |
| to_item_id | int | FK, to_document_id와 배타 | 가리키는 항목 (상위) | |
| to_document_id | int | FK, to_item_id와 배타 | 문서 전체를 가리킬 때 | |
| raw_target | varchar(100) | not null | 본문에 적힌 문자열 그대로. 미존재·끊어진 참조는 이걸로 표시 | `SYNC-PRD-001#R12` |
| is_missing | boolean | default false | 대상이 아직 없거나 삭제됐음. true면 to_*는 null | |
| extracted_version_id | int | FK | 어느 버전 저장 때 추출됐나 | |

### users

클래스: [[SYNC-DOM-002#User]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| github_login | varchar(50) | UK | GitHub 아이디. **자리표시 User에서는 아이디가 아닐 수 있다** — 커밋 이메일이 noreply가 아니면 `%an`(사람 이름)이 대체값으로 들어간다([[SYNC-DOM-002]] 5장 결정 3) | `hoyoung-park` |
| github_user_id | bigint | UK | GitHub 숫자 ID. 아이디 변경에 대비 | |
| kind | varchar(12) | not null, 기본 `github` | 사용자 종류 — `github` · `local`(폐쇄망판 로컬 사용자) · `placeholder`(커밋으로만 알려진 사람). **자리표시 판정은 이 칸이다**(카드 BC) | `local` |
| github_token_encrypted | bytea | null 허용 | OAuth 토큰. 앱 비밀키로 암호화. push에 사용. **null이면 미등록** — GitHub 직접 push로만 알려진 사람(자리표시). 로그인하면 채워진다 | |

### commit_emails

클래스: [[SYNC-DOM-002#CommitEmail]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| email | varchar(255) | UK | git 커밋의 `%ae`. **소문자로 정규화해 저장한다** — git 이메일은 대소문자가 흔들린다. UK인 이유는 이메일 하나가 사람 하나여야 작성자 판정이 답을 하나로 내기 때문이다 | `you@example.com` |
| added_at | timestamptz | not null | 등록 시각. 사람이 UI-13 2.6에서 직접 등록한다 — 시스템이 추측해 넣지 않는다 | |

### access_tokens

클래스: [[SYNC-DOM-002#AccessToken]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| token_hash | varchar(64) | UK | 토큰 원문의 SHA-256. 원문은 저장 안 함 | |
| label | varchar(50) | | 사용자가 붙인 이름 | `Claude Code 노트북` |
| issued_at | timestamptz | not null | 발급 시각 | |
| expires_at | timestamptz | null 허용 | 만료 시각. **v1은 항상 null**(인프라 9장 — 만료 없음). 컬럼과 검증 분기는 정책이 바뀔 때를 위해 남겨 둔다 | |
| revoked_at | timestamptz | null 허용 | 폐기 시각. null이면 유효 | |
| last_used_at | timestamptz | null 허용 | 이 토큰으로 마지막에 들어온 시각. null이면 한 번도 안 씀. 만료가 없으므로 안 쓰는 토큰을 찾는 단서가 이것뿐이다(UI-13 3.5) | |

### conversations

클래스: [[SYNC-DOM-002#Conversation]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| project_id | int | FK not null, ON DELETE CASCADE | 어느 프로젝트의 대화인가. 프로젝트 해제와 함께 사라진다 | |
| user_id | int | FK not null | 소유자. `projects.owner_user_id`와 같은 사람이지만 따로 둔다 — 소유 검사는 프로젝트로, 이 컬럼은 「누가 물었나」 | |
| title | varchar(80) | not null | 첫 질문의 앞 40자. 빈 대화면 `새 대화` | `이 요구사항의 근거가 뭐라고 했어?` |
| updated_at | timestamptz | not null | 마지막 턴이 끝난 시각. 목록 정렬 기준 | |

### turns

클래스: [[SYNC-DOM-002#Turn]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| conversation_id | int | FK not null, ON DELETE CASCADE | | |
| seq | int | not null, UK(conversation_id, seq) | 대화 안 순번 1부터 | `3` |
| question | text | not null | 사람이 쓴 질문 | |
| answer | text | null 허용 | 모델의 답. 실패한 턴은 null | |
| progress | jsonb | not null, default `[]` | 진행 줄 `[{kind: note\|read, text}]` — 화면 8.9가 다시 그린다 | |
| context_item_ids | jsonb | not null, default `[]` | 실제로 읽은 것(`DOC#ITEM`·`DOC`·`첨부:이름`), 부른 순서 | |
| error | varchar(300) | null 허용 | 답을 못 받은 이유. 있으면 다음 질문의 history에 안 실린다 | `llm-unavailable` |

### attachments

클래스: [[SYNC-DOM-002#Attachment]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| conversation_id | int | FK not null, ON DELETE CASCADE | 어느 대화에 붙였나 | |
| turn_id | int | FK null 허용, ON DELETE CASCADE | 보낸 턴. **null이면 아직 안 보낸 것**(입력 칸에 올려 둔 상태) — 대화를 지우면 같이 사라진다 | |
| user_id | int | FK not null | 올린 사람 | |
| name | varchar(200) | not null | 원래 파일 이름 | `회의록.pdf` |
| mime | varchar(80) | not null | 종류. 받는 것만 — `image/png` `image/jpeg` `image/webp` `image/gif` `text/markdown` `text/plain` `text/csv` `application/json` `application/yaml` `application/pdf` | `application/pdf` |
| size | int | not null | 바이트 수. 이미지 ≤10MB, 나머지 ≤1MB — 서비스가 막는다 | `348211` |
| bytes | bytea | not null | 파일 그대로. 이미지는 모델에 data URL로 실리고 사람에겐 미리보기로 | |
| text_cache | text | null 허용 | 글자 파일은 본문 그대로, PDF는 `pypdf`로 뽑은 글자. 이미지는 null. 모델이 `read_attachment`로 읽는 것 | |

---

### code_graphs

클래스: [[SYNC-DOM-002#CodeGraph]]

| 컬럼 | 타입 | 제약 | 의미 | 예시 |
|---|---|---|---|---|
| project_id | int | PK, FK not null, ON DELETE CASCADE | 어느 프로젝트의 그래프인가. 프로젝트마다 하나 | |
| commit_hash | varchar(40) | null | 이 그래프를 만든 커밋. 첫 빌드부터 실패했으면 null | `2e243f4…` |
| source | varchar(10) | null | `repo`(저장소에 커밋된 graphify 결과) · `server`(서버가 추출). 앱 검증 | `server` |
| graph | jsonb | not null | 줄인 모양 `{functions, calls, communities}`([[SYNC-MS-011]] 0장). 함수마다 `community`(없으면 null). **2026-10-01 이전에 만든 행에는 `communities`가 없다** — 읽는 쪽이 빈 것으로 보고, 다음 코드 push가 채운다(마이그레이션 없음 — JSONB 안 키다, 카드 BD). 코드 본문 없음 | |
| function_count | int | not null, default 0 | 함수 수. 관리·로그용 | `1471` |
| call_count | int | not null, default 0 | 호출 선 수 | `2192` |
| built_at | timestamptz | not null | 마지막으로 성공하거나 실패한 시각 | |
| error | varchar(300) | null | 마지막 빌드가 실패한 이유(`커밋7자: 이유`). 성공하면 비운다 | `2e243f4: 시간 초과` |

## 3. 인덱스와 정규화

[[SYNC-STD-004#DEV-8]] — 인덱스는 여기 적힌 것만. FK와 unique는 전부 인덱스(생략). 아래는 조회 패턴에서 온 추가 인덱스.

| 테이블 | 인덱스 | 이유 (어느 쿼리) |
|---|---|---|
| projects | `(owner_user_id)` | FK 컬럼(DEV-8) · `list_owned` |
| documents | `(project_id, doc_type)` | 단계별 목록 · `list_by_project(stage)` |
| documents | `(has_convention_error) where true` 부분 | 규약 오류 문서 · `convention_error_docs_by` |
| documents | `(trashed_by_user_id)` | FK 컬럼(DEV-8). 휴지통 목록은 프로젝트 단위라 `(project_id, doc_type)`로 충분 |
| items | `(document_id, is_deleted)` | 현재 항목 목록 · `detect_deleted_items` · `item_blocks` 대조 |
| versions | `(document_id, version_no desc)` | 최근 버전 · `last_author` · `current` |
| versions | `(author_user_id, created_at)` · `(instructed_by_user_id)` | FK 컬럼(DEV-8) · 작성자별 이력 |
| references | `(from_item_id)` · `(to_item_id)` · `(to_document_id)` · `(from_document_id)` | 상·하위 조회 전부 |
| references | `(is_missing) where true` 부분 | `resolve_missing` |
| status_changes | `(document_id, changed_at)` | 이력 병합 |
| access_tokens | `(token_hash)` unique — 이미 | MCP 인증 |
| conversations | `(project_id, user_id)` · `(user_id)` | 프로젝트의 내 대화 목록 · FK 컬럼(DEV-8) |
| turns | `(conversation_id, seq)` unique | 순번 유일 + 대화의 턴 차례 |
| attachments | `(conversation_id)` · `(turn_id)` · `(user_id)` | 대화의 첨부 메타 · 턴의 이미지 · FK 컬럼(DEV-8) |
| code_graphs | PK `(project_id)` — 이미 | 프로젝트의 그래프 하나. 다른 조회가 없다 |

**정규화** — 전 테이블 3NF. 의도적 비정규화 하나([[SYNC-STD-004#DEV-9]]): `documents.current_body`(조회 캐시, `versions.body`와 같음 — **읽기 전용 캐시다**, DEV-19). `versions.body` 전체 저장은 비정규화가 아니라 git 사본이다.

## 4. 판단이 필요한 지점

**1. `documents.status`와 frontmatter의 동기화.** 둘이 어긋나면 어느 쪽이 맞나? 원칙은 frontmatter. 파이프라인이 저장 때마다 frontmatter를 읽어 `status`를 덮어쓴다.

---

## 5. 미결사항

- [x] `versions.body`가 커지면 압축할지 — 지금은 안 함 — 결정: 압축하지 않는다. PostgreSQL이 2KB 넘는 텍스트를 TOAST로 밖에 빼 이미 압축한다(마크다운은 서너 배). 실측: 명세 40개 740KB, 전체 덤프 420KB. **전체 덤프가 100MB를 넘거나 한 프로젝트의 버전이 수천 개가 되면 다시 본다** — 그때는 압축보다 오래된 버전의 본문을 비우는 쪽(원본은 git에 있다)
- [x] DB 유실 시 복구 불가 항목(플래그·전파결정·댓글)의 백업 — 인프라 미결사항과 같음 — 결정: DB 덤프를 저장소에 커밋한다 ([[SYNC-INFRA-001]] 6장) → **v2에서 세 표를 뺐다**(카드 V). 복구 불가 항목이 없어졌으므로 백업도 없다
