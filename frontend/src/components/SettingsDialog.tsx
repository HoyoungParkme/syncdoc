/** UI-13 설정 — SYNC-UI-002#UI-13. 어느 화면 위에서든 뜨는 다이얼로그. 닫으면 보던 화면 그대로.
 *  1 다이얼로그 · 2 내 계정(2.1 로그인 ID, 2.2 로그아웃, 2.3 커밋 이메일 행, 2.4 삭제, 2.5 입력, 2.6 추가)
 *  3 MCP 토큰(3.1 행, 3.2 폐기, 3.3 이름, 3.4 발급 열기, 3.5 마지막 사용, 3.6 발급)
 *  4 토큰 원문 상자(4.1 원문, 4.2 복사) · 5 관리 카드(5.1 열기) · 6 관리 영역(UI-14) · 7 닫기(✕) · 8 클라이언트 설정(8.1 스니펫) · 9 닫기
 *  싱크독_로컬 설치형만(카드 L16) — 10 이 PC(10.1 이름 · 10.2 모델 주소 · 10.3 모델 키 · 10.4 모델 이름 · 10.5 저장하고 다시 켜기 ·
 *  10.6 자동 시작 · 10.7 데이터 자리 · 10.8 새 자리 · 10.9 옮기기 · 10.10 마지막 다시 켜기) · 11 백업(11.1 폴더 · 11.2 암호 ·
 *  11.3 저장하고 다시 켜기 · 11.4 지금 백업 · 11.5 마지막 백업 · 11.6 백업 행 · 11.7 되살리기 · 11.8 되살리기 암호) · 12 다시 켜는 중 */
import { useEffect, useState } from 'react'
import {
  ago,
  api,
  ApiError,
  MCP_NAME,
  type AccessToken,
  type CommitEmail,
  type LocalInfo,
  type Me,
} from '../api/client'
import { Admin } from '../pages/Admin'
import { useEscape } from './ui'

const day = (iso: string) => iso.slice(0, 10)

/** 이 PC의 시각 — `YYYY-MM-DD HH:MM` */
function when(iso: string): string {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** 크기 — MB(소수 하나), 1MB 아래는 KB */
function size(n: number): string {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
}

/** 문제의 `reason` — 없으면 문장 */
function reason(e: unknown): string {
  if (e instanceof ApiError) return String(e.problem.reason ?? e.message)
  return '실패했습니다'
}

/** 「이 PC」·「백업」 카드 — 싱크독_로컬 설치형(Rust)만. `/api/local`이 404면(파이썬 판) 그리지 않는다 (UI-13 10·11·12, 카드 L16) */
function LocalCards() {
  const [info, setInfo] = useState<LocalInfo | null>(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [key, setKey] = useState('')
  const [model, setModel] = useState('')
  const [moveTo, setMoveTo] = useState('')
  const [dir, setDir] = useState('')
  const [password, setPassword] = useState('')
  const [restorePw, setRestorePw] = useState('')
  const [busy, setBusy] = useState(false)
  // 다시 켜는 중(12) — 202 뒤 마지막 다시 켜기(10.10)의 시각이 바뀔 때까지
  const [restarting, setRestarting] = useState(false)
  const [error, setError] = useState<{ at: string; text: string } | null>(null)
  const fill = (v: LocalInfo) => {
    setInfo(v)
    setName(v.name)
    setUrl(v.llm_api_url)
    setModel(v.llm_model)
    setKey('')
    setDir(v.backup.dir)
    setPassword('')
  }
  useEffect(() => {
    api
      .get<LocalInfo>('/api/local')
      .then(fill)
      .catch(() => setInfo(null)) // 파이썬 판 — 없는 경로
  }, [])
  if (!info) return null

  async function restart(go: () => Promise<unknown>, at: string) {
    setError(null)
    const before = info?.last_op?.at ?? ''
    try {
      await go()
    } catch (e) {
      setError({ at, text: reason(e) })
      return
    }
    setRestarting(true)
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000))
      try {
        const v = await api.get<LocalInfo>('/api/local')
        if ((v.last_op?.at ?? '') !== before) {
          fill(v)
          break
        }
      } catch {
        // 내려가 있다 — 다시 뜰 때까지
      }
    }
    setRestarting(false)
  }
  const changed: Record<string, string> = {}
  if (name !== info.name) changed.name = name
  if (url !== info.llm_api_url) changed.llm_api_url = url
  if (key) changed.llm_api_key = key
  if (model !== info.llm_model) changed.llm_model = model
  const backupChanged: Record<string, string> = {}
  if (dir !== info.backup.dir) backupChanged.backup_dir = dir
  if (password) backupChanged.backup_password = password
  async function autostart(on: boolean) {
    setInfo(await api.put<LocalInfo>('/api/local/autostart', { on }))
  }
  async function backupNow() {
    setBusy(true)
    try {
      await api.post('/api/local/backups')
    } catch {
      // 실패는 마지막 백업(11.5)에 남는다
    } finally {
      fill(await api.get<LocalInfo>('/api/local'))
      setBusy(false)
    }
  }
  function move() {
    // 규칙: 옮기기는 확인을 받는다
    if (!confirm(`데이터를 ${moveTo}로 옮기고 다시 켤까요? 옛 폴더는 지우지 않습니다.`)) return
    restart(() => api.post('/api/local/move', { dir: moveTo }), 'move')
  }
  function restore(file: string) {
    // 규칙: 되살리기는 확인을 받는다 — 성공하면 백업 뒤의 일이 사라진다
    if (!confirm(`${file} 때로 되돌릴까요? 그 뒤에 쌓인 명세·대화는 사라집니다.`)) return
    restart(() => api.post('/api/local/restore', restorePw ? { name: file, password: restorePw } : { name: file }), 'restore')
  }
  const last = info.backup.last
  return (
    <>
      {restarting && (
        <div className="tokbox" data-el="12">
          <b>다시 켜는 중…</b>화면이 저절로 돌아옵니다.
        </div>
      )}
      <section className="card" data-el="10">
        <div className="cardh">
          <b>이 PC</b>
        </div>
        <p className="lbl">이 PC에서만 쓰는 값입니다. 저장하면 싱크독_로컬이 다시 켜집니다(몇 초).</p>
        {info.last_op && (
          <div className="row" data-el="10.10">
            <span className={info.last_op.ok ? 'lbl' : 'lbl warn'}>
              마지막 다시 켜기 — {info.last_op.message} · {when(info.last_op.at)}
            </span>
          </div>
        )}
        <div className="row">
          <span className="two">
            <b>이름</b>
            <span className="lbl">아이디 {info.login} · 커밋 작성자</span>
          </span>
          <input className="inp wide" data-el="10.1" placeholder={info.login} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="row">
          <b>모델 주소</b>
          <input
            className="inp wide mono"
            data-el="10.2"
            placeholder="https://llm.사내/v1/chat/completions"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
        <div className="row">
          <b>모델 키</b>
          <input
            className="inp wide mono"
            type="password"
            data-el="10.3"
            placeholder={info.llm_api_key_set ? '정해 둠 — 바꿀 때만' : '없음'}
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </div>
        <div className="row">
          <b>모델 이름</b>
          <input className="inp wide mono" data-el="10.4" placeholder="gpt-4o" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className="row">
          <span className="grow" />
          <button
            className="btn sm solid"
            type="button"
            data-el="10.5"
            disabled={restarting || Object.keys(changed).length === 0}
            onClick={() => restart(() => api.put('/api/local/settings', changed), 'settings')}
          >
            저장하고 다시 켜기
          </button>
        </div>
        {error?.at === 'settings' && <p className="lbl warn">{error.text}</p>}
        <div className="row">
          <label>
            <input type="checkbox" data-el="10.6" checked={info.autostart} onChange={(e) => autostart(e.target.checked)} /> 로그인할 때
            트레이로 켜기
          </label>
        </div>
        <div className="row">
          <span className="two">
            <b>데이터 자리</b>
            <span className="lbl mono" data-el="10.7">
              {info.data_dir}
            </span>
          </span>
        </div>
        <div className="row">
          <input className="inp wide mono" data-el="10.8" placeholder="새 폴더 — 없거나 빈 폴더" value={moveTo} onChange={(e) => setMoveTo(e.target.value)} />
          <button className="btn sm" type="button" data-el="10.9" disabled={restarting || !moveTo.trim()} onClick={move}>
            옮기기
          </button>
        </div>
        {error?.at === 'move' && <p className="lbl warn">{error.text}</p>}
      </section>

      <section className="card" data-el="11">
        <div className="cardh">
          <b>백업</b>
          <span className="grow" />
          <button className="btn sm solid" type="button" data-el="11.4" disabled={busy || restarting || !info.backup.dir} onClick={backupNow}>
            {busy ? '백업 중…' : '지금 백업'}
          </button>
        </div>
        <p className="lbl">
          하루 한 번 이 폴더에 DB와 서버 저장소를 묶어 둡니다. 최근 {info.backup.keep}개만 남깁니다. 암호를 잃으면 백업을 풀 수 없습니다 — 이 PC
          밖에도 적어 두세요.
        </p>
        <div className="row">
          <b>폴더</b>
          <input className="inp wide mono" data-el="11.1" placeholder="D:\백업\syncdoc" value={dir} onChange={(e) => setDir(e.target.value)} />
        </div>
        <div className="row">
          <b>암호</b>
          <input
            className="inp wide"
            type="password"
            data-el="11.2"
            placeholder={info.backup.encrypted ? '정해 둠 — 바꿀 때만' : '없음 — 암호 없이 저장'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="row">
          <span className="grow" />
          <button
            className="btn sm solid"
            type="button"
            data-el="11.3"
            disabled={restarting || Object.keys(backupChanged).length === 0}
            onClick={() => restart(() => api.put('/api/local/settings', backupChanged), 'backup')}
          >
            저장하고 다시 켜기
          </button>
        </div>
        {error?.at === 'backup' && <p className="lbl warn">{error.text}</p>}
        {last && (
          <div className="row" data-el="11.5">
            <span className={last.error ? 'lbl warn' : 'lbl'}>
              {last.error ? `마지막 백업 실패 — ${last.error}` : `마지막 백업 ${when(last.at)} · ${last.name}`}
            </span>
          </div>
        )}
        {info.backup.files.length > 0 && (
          <div className="row">
            <b>되살리기 암호</b>
            <input
              className="inp wide"
              type="password"
              data-el="11.8"
              placeholder="비우면 설정의 암호"
              value={restorePw}
              onChange={(e) => setRestorePw(e.target.value)}
            />
          </div>
        )}
        {info.backup.files.map((f) => (
          <div className="row" data-el="11.6" key={f.name}>
            <span className="two">
              <b className="mono">{f.name}</b>
              <span className="lbl">{size(f.size)}</span>
            </span>
            <span className="grow" />
            <button className="btn sm danger" type="button" data-el="11.7" disabled={restarting} onClick={() => restore(f.name)}>
              되살리기
            </button>
          </div>
        ))}
        {error?.at === 'restore' && <p className="lbl warn">{error.text}</p>}
      </section>
    </>
  )
}

export function SettingsDialog({ user, onClose }: { user: Me; onClose: () => void }) {
  // 폐쇄망판 — 로그인이 없고 모든 커밋이 로컬 사용자라 로그아웃·커밋 이메일이 없다 (UI-13 규칙, 카드 BC)
  const closed = user.edition === 'closed'
  useEscape(onClose) // 1.1 — 재구축 확인(UI-14 4)이 위에 떠 있으면 그것이 먼저 닫힌다
  const [tokens, setTokens] = useState<AccessToken[]>([])
  const [label, setLabel] = useState('')
  const [issued, setIssued] = useState<AccessToken | null>(null)
  // 발급 폼은 접혀 있다. 기본 상태의 카드는 제목 + 발급 + 토큰 목록만 보인다
  const [naming, setNaming] = useState(false)
  // 규칙: 관리는 접힌 채로 연다. 인덱스 재구축이 위험한 동작이라 한 번 더 눌러야 보인다
  const [adminOpen, setAdminOpen] = useState(false)
  const [emails, setEmails] = useState<CommitEmail[]>([])
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState('')
  const load = () => api.get<AccessToken[]>('/api/me/tokens').then(setTokens)
  const loadEmails = () => api.get<CommitEmail[]>('/api/me/emails').then(setEmails)
  useEffect(() => {
    load()
    if (!closed) loadEmails()
  }, [closed])
  async function issue() {
    const t = await api.post<AccessToken>('/api/me/tokens', { label })
    setIssued(t)
    setLabel('')
    setNaming(false)
    load()
  }
  async function revoke(t: AccessToken) {
    // 규칙: 폐기는 확인을 받는다. 되돌릴 수 없고 그 토큰을 쓰던 에이전트가 즉시 끊긴다
    if (!confirm(`'${t.label}' 토큰을 폐기할까요? 그 토큰으로 오는 MCP 요청이 거부됩니다.`)) return
    await api.del(`/api/me/tokens/${t.id}`)
    load()
  }
  async function addEmail() {
    try {
      await api.post<CommitEmail>('/api/me/emails', { email })
      setEmail('')
      setEmailError('')
      loadEmails()
    } catch (e) {
      setEmailError(e instanceof ApiError ? e.message : '등록하지 못했습니다')
    }
  }
  async function removeEmail(e: CommitEmail) {
    // 규칙: 삭제는 확인을 받는다. 다음 재구축에서 그 이메일 커밋이 자리표시로 돌아간다
    if (!confirm(`${e.email}을 지울까요? 다음 인덱스 재구축에서 그 이메일로 온 커밋이 내 것이 아니게 됩니다.`)) return
    await api.del(`/api/me/emails/${e.id}`)
    loadEmails()
  }
  const logout = () => {
    api.post('/auth/logout', {}).finally(() => (window.location.href = '/login'))
  }
  // 서버 이름은 판 이름 — 서버가 알리는 이름과 같게 (UI-13 8.1, 카드 BU)
  const snippet = `{
  "mcpServers": {
    "${MCP_NAME[user.edition ?? 'internet']}": {
      "url": "${window.location.origin}/mcp",
      "headers": { "Authorization": "Bearer syncdoc_pat_…" }
    }
  }
}`
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog setdlg" data-el="1">
        <div className="dhead">
          <span>설정</span>
          <span className="grow" />
          <span className="x" data-el="7" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <section className="card" data-el="3">
            <div className="cardh">
              <b>MCP 토큰</b>
              <span className="grow" />
              <button className="btn sm solid" type="button" data-el="3.4" onClick={() => setNaming((o) => !o)}>
                + 발급
              </button>
            </div>
            {/* 설명은 제목 줄이 아니라 아래 줄 — 헤더는 제목과 동작만 든다 */}
            <p className="lbl">에이전트가 싱크독에 붙을 때 씁니다. 남에게 주면 그 사람 작업이 내 이름으로 남습니다.</p>
            {naming && (
              <div className="row">
                <input
                  className="inp wide"
                  data-el="3.3"
                  placeholder="이름 — 예: Gemini 노트북"
                  value={label}
                  autoFocus
                  onChange={(e) => setLabel(e.target.value)}
                />
                <button className="btn sm solid" type="button" data-el="3.6" disabled={!label.trim()} onClick={issue}>
                  발급
                </button>
              </div>
            )}
            {/* 원문은 발급 직후 여기서만 보인다. 서버는 해시만 저장해 다시 보여줄 수 없다 */}
            {issued?.token && (
              <div className="tokbox" data-el="4">
                <b>한 번만 보입니다. 지금 복사하세요.</b>
                <div className="tok" data-el="4.1">
                  {issued.token}
                </div>
                <button className="btn sm" type="button" data-el="4.2" onClick={() => navigator.clipboard.writeText(issued.token ?? '')}>
                  복사
                </button>
              </div>
            )}
            {/* 두 줄이다 — 이름과, 그 아래 고정폭으로 발급일. 식별자를 다루는 목록임이 보여야 한다 */}
            {tokens.map((t) => (
              <div className={`row${t.revoked_at ? ' dimrow' : ''}`} data-el="3.1" key={t.id}>
                <span className="two">
                  <b>{t.label}</b>
                  <span className="lbl mono">
                    발급 {day(t.issued_at)}
                    {t.revoked_at && <s> · 폐기됨 {day(t.revoked_at)}</s>}
                  </span>
                </span>
                <span className="grow" />
                {/* 만료가 없어 안 쓰는 토큰을 찾는 단서가 이것뿐이다 */}
                <span className="lbl" data-el="3.5">
                  마지막 사용 {t.last_used_at ? ago(t.last_used_at) : '없음'}
                </span>
                {!t.revoked_at && (
                  <button className="btn sm danger" type="button" data-el="3.2" onClick={() => revoke(t)}>
                    폐기
                  </button>
                )}
              </div>
            ))}
          </section>

          <section className="card" data-el="8">
            <div className="cardh">
              <b>클라이언트 설정</b>
            </div>
            <p className="lbl">Claude Code · Codex · Gemini CLI가 같은 엔드포인트를 씁니다.</p>
            <pre className="snippet" data-el="8.1">{snippet}</pre>
          </section>

          {closed && <LocalCards />}

          <section className="card" data-el="5">
            <div className="cardh">
              <b>관리</b> <span className="lbl">인덱스 재구축 · 저장소 동기화</span>
              <span className="grow" />
              <button className="btn sm" type="button" data-el="5.1" onClick={() => setAdminOpen((o) => !o)}>
                {adminOpen ? '접기' : '열기'}
              </button>
            </div>
            {adminOpen && (
              <div className="admin" data-el="6">
                <Admin />
              </div>
            )}
          </section>

          {closed ? (
            <section className="card" data-el="2">
              <div className="cardh">
                <b>내 계정</b>
              </div>
              <div className="row">
                <span data-el="2.1">{user.github_login}</span> <span className="lbl">로그인 없음 · 이 PC · {user.display_name}</span>
              </div>
            </section>
          ) : (
          <section className="card" data-el="2">
            <div className="cardh">
              <b>내 계정</b>
            </div>
            <div className="row">
              <span data-el="2.1">{user.github_login}</span> <span className="lbl">GitHub · {user.display_name}</span>
              <span className="grow" />
              <button className="btn sm" type="button" data-el="2.2" onClick={logout}>
                로그아웃
              </button>
            </div>
            <p className="lbl">
              커밋 이메일 — GitHub에서 바로 push한 커밋을 내 계정으로 잇습니다. 등록한 뒤 관리에서 인덱스 재구축을 한 번 돌리세요.
            </p>
            {emails.map((e) => (
              <div className="row" key={e.id} data-el="2.3">
                <span className="mono">{e.email}</span>
                <span className="grow" />
                <button className="btn sm danger" type="button" data-el="2.4" onClick={() => removeEmail(e)}>
                  삭제
                </button>
              </div>
            ))}
            <div className="row">
              <input
                className="inp wide"
                data-el="2.5"
                placeholder="you@example.com"
                value={email}
                onChange={(ev) => setEmail(ev.target.value)}
              />
              <button className="btn sm" type="button" data-el="2.6" disabled={!email.trim()} onClick={addEmail}>
                추가
              </button>
            </div>
            {emailError && <p className="lbl warn">{emailError}</p>}
          </section>
          )}
        </div>

        <div className="dfoot">
          <span className="grow" />
          <button className="btn solid" type="button" data-el="9" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </>
  )
}
