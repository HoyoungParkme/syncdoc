// 화면 개발 서버(Vite) 앞에 서는 프록시 — `syncdoc-local trace-web`이 띄운다 (SYNC-INFRA-001 9.9, 카드 L29).
// view_arc web-proxy를 옮겼다. 프로젝트 코드·설정을 고치지 않고 브라우저 실행 기록을 켠다.
//
// - 페이지(HTML) <head> 맨 앞에 기록기(browser-runtime.js)를 넣는다.
// - 프로젝트 소스 모듈(JS로 바뀐 .ts/.tsx …)에 web-instrument.mjs 로 기록 코드를 끼운다.
// - 브라우저가 보낸 기록(/__syncdoc/ingest)을 SYNCDOC_TRACE_OUT 에 쓴다 — 기록 도구가 서버로 올린다.
// - HMR 웹소켓은 그대로 이어 준다.
//
// 환경변수: SYNCDOC_TRACE_OUT · SYNCDOC_TRACE_SPANS({byName: {상대 경로: {이름: 열쇠}}}) · SYNCDOC_TRACE_TARGET · SYNCDOC_TRACE_PORT

import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { instrument } from './web-instrument.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const SOURCE = /\.(tsx?|jsx?|mts|mjs|cts|cjs|vue|svelte)$/

const target = new URL(process.env.SYNCDOC_TRACE_TARGET || 'http://localhost:5173')
const port = Number(process.env.SYNCDOC_TRACE_PORT || '3124')
const out = process.env.SYNCDOC_TRACE_OUT
const spans = JSON.parse(fs.readFileSync(process.env.SYNCDOC_TRACE_SPANS, 'utf-8'))
const byName = spans.byName ?? {}
const files = Object.keys(byName)
const runtime = fs.readFileSync(path.join(here, 'browser-runtime.js'), 'utf-8')
const keyOf = (file, name) => byName[file]?.[name]

// 브라우저 주소의 경로 → 그래프의 파일 경로(저장소 뿌리 기준) — 끝이 같은 것 중 가장 짧은 것
const fileCache = new Map()
const resolveFile = (urlPath) => {
  if (fileCache.has(urlPath)) return fileCache.get(urlPath)
  let rel = null
  const clean = decodeURIComponent(urlPath)
  if (!clean.startsWith('/@') && !clean.includes('/node_modules/')) {
    const hits = files.filter((f) => f === clean.slice(1) || f.endsWith(clean))
    rel = hits.sort((a, b) => a.length - b.length)[0] ?? null
  } else if (clean.startsWith('/@fs/')) {
    const tail = clean.slice('/@fs'.length)
    rel = files.filter((f) => tail.endsWith('/' + f)).sort((a, b) => b.length - a.length)[0] ?? null
  }
  fileCache.set(urlPath, rel)
  return rel
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://x')
  if (url.pathname === '/__syncdoc/runtime.js') {
    res.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'no-store' })
    return res.end(runtime)
  }
  if (url.pathname === '/__syncdoc/ingest' && req.method === 'POST') return ingest(req, res)
  const headers = { ...req.headers, host: target.host, 'accept-encoding': 'identity' }
  delete headers['if-none-match']
  delete headers['if-modified-since']
  const upstream = http.request({ host: target.hostname, port: target.port, method: req.method, path: req.url, headers }, (up) => {
    const type = String(up.headers['content-type'] ?? '')
    const js = /javascript/.test(type)
    const file = js && SOURCE.test(url.pathname) ? resolveFile(url.pathname) : null
    const html = type.includes('text/html')
    if (!file && !html) {
      res.writeHead(up.statusCode ?? 502, up.headers)
      return up.pipe(res)
    }
    const chunks = []
    up.on('data', (c) => chunks.push(c))
    up.on('end', () => {
      let body = Buffer.concat(chunks).toString('utf-8')
      if (html) body = body.replace(/<head([^>]*)>/i, '<head$1><script src="/__syncdoc/runtime.js"></script>')
      else {
        try {
          body = instrument(body, file, keyOf, url.pathname) ?? body
        } catch (error) {
          console.error(`[syncdoc] 계측 실패(원본 그대로 보냄): ${url.pathname}: ${error.message}`)
        }
      }
      const outHeaders = { ...up.headers }
      delete outHeaders['content-length']
      delete outHeaders['content-encoding']
      delete outHeaders['transfer-encoding']
      delete outHeaders['etag']
      res.writeHead(up.statusCode ?? 200, { ...outHeaders, 'cache-control': 'no-store', 'content-length': Buffer.byteLength(body) })
      res.end(body)
    })
  })
  upstream.on('error', (error) => {
    res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end(`[syncdoc] 개발 서버(${target.origin})에 연결하지 못했습니다: ${error.message}`)
  })
  req.pipe(upstream)
})

server.on('upgrade', (req, socket, head) => {
  const up = net.connect(Number(target.port), target.hostname, () => {
    const lines = [`${req.method} ${req.url} HTTP/${req.httpVersion}`]
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const [k, v] = [req.rawHeaders[i], req.rawHeaders[i + 1]]
      lines.push(`${k}: ${k.toLowerCase() === 'host' ? target.host : v}`)
    }
    up.write(lines.join('\r\n') + '\r\n\r\n')
    if (head.length) up.write(head)
    socket.pipe(up).pipe(socket)
  })
  up.on('error', () => socket.destroy())
  socket.on('error', () => up.destroy())
})

/** 브라우저 기록 하나를 기록 폴더에 쓴다 — 기록 도구가 올린다 */
function ingest(req, res) {
  const chunks = []
  req.on('data', (c) => chunks.push(c))
  req.on('end', () => {
    try {
      const record = JSON.parse(Buffer.concat(chunks).toString('utf-8'))
      if (!/^[0-9-]+$/.test(record.id)) throw new Error('id')
      record.kind = 'front'
      fs.mkdirSync(out, { recursive: true })
      const tmp = path.join(out, `.${record.id}.tmp`)
      fs.writeFileSync(tmp, JSON.stringify(record))
      fs.renameSync(tmp, path.join(out, `${record.id}.json`))
      res.writeHead(204).end()
    } catch {
      res.writeHead(400).end()
    }
  })
}

server.listen(port, () => {
  console.log(`[syncdoc] 브라우저 실행 기록 — 앱은 여기서 여세요: http://localhost:${port}  (원래 주소 ${target.origin} 대신)`)
})
