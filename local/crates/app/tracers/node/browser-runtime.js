// 싱크독 브라우저 실행 기록기(view_arc에서 옮김). web-proxy.mjs 가 페이지 <head> 맨 앞에 넣는다(카드 L29).
// 계측된 함수(web-instrument.mts가 감싼 것)는 __va.e(진입) / __va.r(반환값) / __va.x(예외) / __va.f(끝)를 부른다.
// 사용자 상호작용 하나(클릭 → 핸들러 → API 함수 → fetch …)를 한 기록으로 묶어 /__syncdoc/ingest 로 보낸다.
;(() => {
  if (window.__va) return
  const INGEST = '/__syncdoc/ingest'
  const IDLE_MS = 400 // 열린 호출·요청이 없고 이만큼 조용하면 기록 하나를 닫는다
  const MAX_EVENTS = 3000
  const origFetch = window.fetch.bind(window)
  let current = null // 지금 쌓는 기록
  let seq = 0
  const open = [] // 끝나지 않은 호출 토큰(비동기라 스택이 아니라 열린 목록)

  const now = () => performance.now()
  Error.stackTraceLimit = Math.max(Error.stackTraceLimit || 10, 60)
  const FRAME = /(https?:\/\/[^\s()]+?):(\d+):\d+\)?\s*$/
  const SELF = '/__syncdoc/runtime.js'

  /**
   * 부모 = 지금 JS 호출 스택에서 가장 가까운, 아직 끝나지 않은 계측 함수.
   * 크롬은 await 뒤에 재개된 함수도 스택에 보여 주므로 비동기 흐름에서도 맞다.
   * own: 방금 들어온 함수 자신의 [주소, 시작 줄, 끝 줄] (스택 맨 위의 자기 자신은 건너뛴다)
   */
  function stackParent(own) {
    const stack = new Error().stack || ''
    let skippedSelf = !own
    for (const line of stack.split('\n')) {
      const m = FRAME.exec(line)
      if (!m) continue
      const url = pathOf(m[1])
      if (url.endsWith(SELF)) continue
      const n = Number(m[2])
      if (!skippedSelf && url === own[0] && n >= own[1] && n <= own[2]) {
        skippedSelf = true
        continue
      }
      let best = null
      for (let k = open.length - 1; k >= 0; k--) {
        const t = open[k]
        if (t.url === url && n >= t.from && n <= t.to && (!best || t.to - t.from < best.to - best.from)) best = t
      }
      if (best) return best
    }
    return null
  }

  function repr(value, depth = 0) {
    try {
      if (value === undefined) return 'undefined'
      if (value === null) return 'null'
      const t = typeof value
      if (t === 'string') return JSON.stringify(value.length > 60 ? value.slice(0, 59) + '…' : value)
      if (t === 'number' || t === 'boolean' || t === 'bigint') return String(value)
      if (t === 'function') return `ƒ ${value.name || 'anonymous'}`
      if (value instanceof Error) return `${value.name}: ${value.message}`
      if (typeof value.then === 'function') return 'Promise'
      if (typeof Event !== 'undefined' && value instanceof Event) return `${value.constructor.name}(${value.type})`
      if (typeof Node !== 'undefined' && value instanceof Node) return `<${value.nodeName.toLowerCase()}>`
      if (value.$$typeof) return '<ReactElement>'
      if (depth > 1) return Array.isArray(value) ? `Array(${value.length})` : '{…}'
      if (Array.isArray(value)) {
        const items = value.slice(0, 4).map((v) => repr(v, depth + 1))
        return `[${items.join(', ')}${value.length > 4 ? `, …(${value.length})` : ''}]`
      }
      const keys = Object.keys(value)
      const name = value.constructor && value.constructor !== Object ? value.constructor.name + ' ' : ''
      const body = keys.slice(0, 4).map((k) => `${k}: ${repr(value[k], depth + 1)}`)
      return `${name}{${body.join(', ')}${keys.length > 4 ? ', …' : ''}}`
    } catch {
      return '?'
    }
  }
  const short = (text) => (text.length > 120 ? text.slice(0, 119) + '…' : text)

  function begin(via) {
    const rec = {
      id: `${Date.now()}-${++seq}`,
      startedAt: new Date().toISOString(),
      t0: now(),
      events: [],
      openCount: 0,
      timer: 0,
      page: location.pathname,
      handler: !!via && /^(on|handle)/.test(via), // 사용자가 일으킨 것(onClick, handleSubmit …)
    }
    if (via) current = rec
    return rec
  }

  /**
   * 어느 기록에 붙일지: 스택의 부모가 있으면 그 기록, 없으면
   * - 콜백(via 있음)인데 진행 중인 상호작용이 있으면 거기(상태 변경 뒤 이어지는 effect 등)
   * - 그 밖(프레임 루프, 타이머, 렌더 중 도우미 호출)은 따로 새 기록 — 요청이 없으면 곧 버려진다
   */
  function enter(fn, via, args, url, from, to, extra) {
    url = url ? pathOf(String(url)) : null
    // 요청(fetch·XHR)은 라이브러리 안에서 비동기로 보내질 수 있어 스택에 없으면 가장 최근에 열린 호출로
    const parentTok = stackParent(url ? [url, from, to] : null) || (extra && extra.fetch && open.length ? open[open.length - 1] : null)
    const rec = parentTok ? parentTok.rec : via && current && current.openCount > 0 ? current : begin(via)
    clearTimeout(rec.timer)
    if (rec.events.length >= MAX_EVENTS) return null
    const ev = { i: rec.events.length, parent: parentTok && parentTok.rec === rec ? parentTok.i : -1, fn, t0: +(now() - rec.t0).toFixed(2) }
    if (via) ev.via = via
    if (args) {
      ev.args = {}
      for (const k of Object.keys(args)) ev.args[k] = short(repr(args[k]))
    }
    if (extra) Object.assign(ev, extra)
    rec.events.push(ev)
    rec.openCount++
    const tok = { rec, i: ev.i, url, from, to }
    open.push(tok)
    return tok
  }

  function finish(tok) {
    if (!tok || tok.done) return
    tok.done = true
    const rec = tok.rec
    const ev = rec.events[tok.i]
    ev.t1 = +(now() - rec.t0).toFixed(2)
    if (tok.err !== undefined) ev.exc = short(repr(tok.err))
    else if ('ret' in tok) ev.ret = short(repr(tok.ret))
    const k = open.lastIndexOf(tok)
    if (k >= 0) open.splice(k, 1)
    rec.openCount--
    if (rec.openCount > 0) return
    // 다 끝났는데 요청도 없고 사용자 핸들러도 아니면 바로 버린다(프레임 루프, 렌더 중 도우미 호출 등)
    if (!rec.handler && !rec.events.some((e) => e.fetch)) {
      if (current === rec) current = null
      return
    }
    clearTimeout(rec.timer)
    rec.timer = setTimeout(() => flush(rec), IDLE_MS)
  }

  function flush(rec) {
    if (rec.openCount > 0) return
    if (current === rec) current = null
    const fetches = rec.events.filter((e) => e.fetch)
    const root = rec.events.find((e) => e.parent === -1)
    if (!fetches.length && !(rec.handler && rec.events.length > 1)) return
    const first = fetches[0]
    const record = {
      version: 1,
      kind: 'front',
      id: rec.id,
      method: first ? first.fetch.method : 'UI',
      path: first ? first.fetch.path : root.via || root.fn,
      status: first ? first.fetch.status ?? null : null,
      error: null,
      startedAt: rec.startedAt,
      ms: +(now() - rec.t0 - IDLE_MS).toFixed(1),
      page: rec.page,
      truncated: rec.events.length >= MAX_EVENTS,
      events: rec.events,
    }
    origFetch(INGEST, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(record), keepalive: true }).catch(() => {})
  }

  // 개발 서버가 내주는 소스·자원(동적 import, CSS …)은 앱의 요청이 아니므로 기록하지 않는다
  const ASSET = /\.(tsx?|jsx?|mjs|cjs|css|map|svg|png|jpe?g|gif|webp|ico|woff2?)$/
  const isAsset = (path) =>
    ASSET.test(path) || path.startsWith('/@') || path.startsWith('/_next/') || path.includes('/node_modules/') || path.includes('/__syncdoc/')

  const pathOf = (url) => {
    try {
      const u = new URL(url, location.href)
      return u.pathname
    } catch {
      return String(url)
    }
  }

  // ---- 요청 가로채기: 요청은 지금 열린 호출의 자식으로 남는다
  window.fetch = function (input, init) {
    const url = typeof input === 'string' || input instanceof URL ? String(input) : input.url
    if (isAsset(pathOf(url)) || /[?&]_rsc=/.test(url)) return origFetch(input, init) // Next 화면 전환용 RSC 요청도 제외
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase()
    const tok = enter('@fetch', null, null, null, 0, 0, { fetch: { method, url: String(url).slice(0, 200), path: pathOf(url) } })
    return origFetch(input, init).then(
      (res) => {
        if (tok) {
          tok.rec.events[tok.i].fetch.status = res.status
          tok.ret = `Response(${res.status})`
        }
        finish(tok)
        return res
      },
      (err) => {
        if (tok) tok.err = err
        finish(tok)
        throw err
      }
    )
  }
  const XHR = XMLHttpRequest.prototype
  const xhrOpen = XHR.open
  const xhrSend = XHR.send
  // 끝남 표시는 open() 때 먼저 걸어 둔다: 라이브러리(axios 등)가 응답을 처리하며 다음 호출을 이어 가기 전에 닫히도록
  XHR.open = function (method, url) {
    const info = (this.__va = { method: String(method).toUpperCase(), url: String(url), tok: null })
    this.addEventListener('readystatechange', () => {
      if (this.readyState !== 4 || !info.tok) return
      info.tok.rec.events[info.tok.i].fetch.status = this.status
      info.tok.ret = `XHR(${this.status})`
      finish(info.tok)
    })
    return xhrOpen.apply(this, arguments)
  }
  XHR.send = function () {
    const info = this.__va
    if (info && !isAsset(pathOf(info.url)))
      info.tok = enter('@fetch', null, null, null, 0, 0, { fetch: { method: info.method, url: info.url.slice(0, 200), path: pathOf(info.url) } })
    return xhrSend.apply(this, arguments)
  }

  window.__va = {
    e: enter,
    r(tok, value) {
      if (tok) tok.ret = value
      return value
    },
    x(tok, err) {
      if (tok) tok.err = err
    },
    f: finish,
  }
})()
