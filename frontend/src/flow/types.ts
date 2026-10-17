// 분석기(analyzer/)가 만들고 뷰어가 읽는 코드 그래프 형식.
// 포함 관계(폴더 ⊃ 파일 ⊃ 클래스 ⊃ 메서드)는 node.parent로, 호출 관계는 edges로 나타낸다.
// 타입만 둔다: 분석기(Node, CommonJS 판정)와 뷰어(Next) 양쪽에서 그대로 import 하기 위해서.

// py·ts 는 전용 분석기, 나머지는 글자 분석(analyzer/generic.mts)
export type Lang = 'py' | 'ts' | 'java' | 'kotlin' | 'scala' | 'go' | 'rust' | 'csharp' | 'php' | 'ruby' | 'swift' | 'c' | 'cpp' | 'vue' | 'svelte'
export type Layer = 'backend' | 'frontend'

export type NodeKind =
  | 'project'
  | 'dir'
  | 'file'
  | 'class'
  | 'function'
  | 'method'
  | 'component'
  | 'hook'
  | 'infra' // 인프라 장비(graph.infra 의 것을 뷰어가 노드처럼 다룬다)

export type HttpRoute = {
  method: string // GET, POST, ... (알 수 없으면 '*')
  path: string // 전체 경로. 경로 변수는 {name}
}

/** 함수 안에서 일어나는 일 하나: 호출, 반환, 예외. 실행 순서대로 정렬돼 있다. */
export type Step =
  | {
      kind: 'call'
      line: number
      label: string // 코드에 적힌 호출 모양, 예: "service.create"
      target?: string // 프로젝트 안 함수면 그 노드 id
      edge?: 'calls' | 'http' | 'depends' | 'renders'
      confidence?: Confidence
      awaited?: boolean
      deferred?: boolean // 콜백·이벤트 핸들러 안에서 나중에 실행됨
      via?: string // deferred일 때 그 콜백 이름, 예: handleClick, useEffect, onChange
      lib?: string // 프로젝트 밖 패키지 호출이면 그 패키지(sqlalchemy, openai, boto3 …) — 인프라로 가는지 판단에 쓴다
      infra?: string // 인프라 장비로 가는 호출이면 그 장비 id(분석기 infra.mts 가 채움)
    }
  | { kind: 'return'; line: number; label: string }
  | { kind: 'raise'; line: number; label: string }

export type Confidence = 'exact' | 'inferred'

export type GraphNode = {
  id: string
  kind: NodeKind
  name: string
  parent: string | null
  path: string // 프로젝트 루트 기준 상대 경로
  lang?: Lang
  layer?: Layer
  line?: number
  endLine?: number
  signature?: string
  returns?: string
  decorators?: string[]
  doc?: string
  route?: HttpRoute // 웹 핸들러(FastAPI·Express·Spring …)
  http?: HttpRoute[] // 프론트에서 보내는 요청
  steps?: Step[]
  loc?: number // 파일·함수 줄 수
  fields?: Array<{ name: string; type: string; optional?: boolean }> // 클래스 필드(pydantic·dataclass): 요청 본문 뼈대
  imports?: string[] // 파일: 가져다 쓰는 프로젝트 밖 패키지(최상위 이름)
}

export type EdgeKind = 'calls' | 'http' | 'depends' | 'renders' | 'imports'

export type GraphEdge = {
  from: string
  to: string
  kind: EdgeKind
  line?: number
  confidence: Confidence
}

export type CodeGraph = {
  version: number
  project: { name: string; root: string; generatedAt: string }
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: Record<string, number>
  specs?: SpecOverlay // 저장소 안 싱크독 명세(docs/specs)가 있으면
  infra?: InfraMap // 코드가 쓰는 장비(브라우저·서버·DB·외부 API …)와 그 연결
  stack?: StackInfo // 실행 단위(백엔드 서버·프론트 개발 서버)와 실행 명령
}

// ---------------------------------------------------------------------------- 스택
// 분석기(stack.mts)가 저장소에서 찾은 실행 단위. 뷰어의 「실행 기록 켜기」와 pnpm attach 가 쓴다.

export type StackPart = {
  id: string // backend(하나뿐) · backend:<폴더> · frontend:<폴더>
  role: 'backend' | 'frontend' | 'worker'
  dir: string // 프로젝트 루트 기준 폴더('' = 루트)
  lang: Lang
  framework: string // FastAPI · Express · Spring Boot · Vite · Next.js …
  entry?: string // 앱을 만드는 파일
  run?: { cmd: string; cwd: string; from: string } // 실행 명령, 실행 위치(루트 기준), 근거
  port?: number
  trace: 'ready' | 'soon' | 'none' // 실행 기록: 지금 가능 · 다음 단계 · 아직 없음
  needs?: string // 기록에 필요한데 이 PC 에 없는 도구(JDK 11+ · Go · Rust(cargo))
  serves?: 'frontend' | 'routes' // 이 서버가 화면도 낸다(Express+Vite) · 라우트 핸들러도 있다(Next)
  proxyTo?: number // 프론트 개발 서버가 /api 를 넘기는 포트
}

export type StackInfo = { parts: StackPart[] }

// ---------------------------------------------------------------------------- 인프라
// 분석기(infra.mts)가 코드의 라이브러리·docker-compose·설정의 접속 주소(호스트만)로 찾는다.

export type InfraKind = 'browser' | 'backend' | 'db' | 'cache' | 'storage' | 'queue' | 'search' | 'api'
/** local: 이 PC 프로세스·파일, container: 이 PC 의 도커 컨테이너, external: 다른 컴퓨터·클라우드 */
export type InfraWhere = 'local' | 'container' | 'external'

export type InfraNode = {
  id: string // infra:db, infra:openai … 백엔드가 여럿이면 infra:backend:<폴더>
  kind: InfraKind
  name: string // 사람이 읽는 이름: PostgreSQL (pgvector), OpenAI API …
  where: InfraWhere
  host?: string // 접속 주소의 호스트:포트(계정·비밀번호는 저장하지 않는다)
  evidence: string[] // 찾은 근거(코드 · compose · 설정)
  uses: number // 이 장비로 가는 호출이 있는 함수 수
  dir?: string // 코드를 얹는 장비(백엔드 서버)면 그 코드 폴더(루트 기준, '' = 루트)
}

export type InfraLink = { from: string; to: string; protocol: string } // 장비 사이 연결(HTTP, SQL, Redis, S3, HTTPS …)

export type InfraMap = { nodes: InfraNode[]; links: InfraLink[] }

// ---------------------------------------------------------------------------- 싱크독 명세
// docs/specs/ 의 MD 문서. 함수 단위 명세(MS, MINISPEC)는 항목 하나 = 함수 하나이고
// "호출하는 것"에 부를 함수가 적혀 있다. 분석기가 실제 코드 호출과 대조한다.

export type SpecDoc = { id: string; type: string; title: string; status: string; path: string; items: number }

export type SpecItem = {
  id: string // SYNC-MS-001#ProjectService.get
  doc: string
  name: string // ProjectService.get
  title: string
  signature?: string
  node?: string // 짝지은 함수 노드 id
  match?: 'docstring' | 'name' // 어떻게 짝지었나
  calls: string[] // 명세의 "호출하는 것" 항목 id
  status: 'ok' | 'diff' | 'no-code'
  onlySpec: string[] // 명세에는 있는데 코드가 부르지 않는 항목 id
  onlyCode: string[] // 코드가 부르는데 명세에 없는 함수 노드 id(명세가 있는 함수만)
}

export type SpecOverlay = { root: string; docs: SpecDoc[]; items: SpecItem[] }

/** 분석기 하나가 돌려주는 결과. 폴더 노드는 합칠 때 만든다. */
export type PartialGraph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  /** 아직 백엔드와 짝짓지 않은 프론트 요청: 보내는 함수 id와 요청 */
  requests?: Array<{ from: string; line: number; route: HttpRoute; confidence: Confidence }>
}

// ---------------------------------------------------------------------------- 실행 기록
// analyzer/runtime/view_arc_tracer.py 가 요청마다 남기는 기록(traces/<slug>/<id>.json).

/** 함수 호출 하나: 시작·끝을 한 줄에. parent는 부르는 쪽 호출 번호(-1이면 맨 위). */
export type RuntimeEvent = {
  i: number
  parent: number
  fn: string // 그래프 노드 id와 같은 꼴: py:<경로>::<클래스.함수>, ts:<경로>::<함수>. 브라우저 요청은 '@fetch'
  name?: string
  line?: number // 함수 정의 줄(백엔드)
  callLine?: number | null // 부르는 쪽에서 부른 줄(백엔드)
  args?: Record<string, string> | null
  kind?: 'call' | 'resume'
  via?: string // 브라우저: 컴포넌트 안 콜백 이름(handleSubmit, onClick, useEffect …). fn은 그 컴포넌트
  fetch?: { method: string; url: string; path: string; status?: number } // 브라우저 요청
  infra?: { kind: 'db' | 'http' | 'redis' | 's3'; target: string; op: string } // 백엔드: DB·외부로 나간 호출(fn = '@infra')
  t0: number // 기록 시작부터 ms
  t1?: number
  ret?: string
  exc?: string
  yield?: boolean
}

export type RuntimeSummary = {
  id: string
  kind?: 'front' | 'back' | 'job' // front: 브라우저 상호작용(클릭 …), job: 작업(Celery·봇·배치), 없으면 백엔드 요청
  method: string
  path: string
  status: number | null
  error: string | null
  startedAt: string
  ms: number
  calls: number
  root: string | null // 엔드포인트 함수 id
  sig?: string // 실제로 간 길(부른 쪽 → 불린 쪽 쌍들)의 지문. 같으면 같은 갈래(목록 서버가 채운다)
}

export type RuntimeRecord = Omit<RuntimeSummary, 'calls' | 'root' | 'sig'> & {
  version: number
  query?: string
  page?: string // 브라우저: 기록한 페이지 경로
  truncated: boolean
  events: RuntimeEvent[]
}
