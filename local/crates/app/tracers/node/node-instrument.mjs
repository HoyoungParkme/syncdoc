// Node 서버 코드(TS·JS 원본)에 실행 기록 코드를 끼워 넣는다(view_arc에서 옮김, 카드 L29). node-hooks.mjs(ESM)와 node-tracer.mjs(CommonJS)가 쓴다.
// 어느 함수를 감쌀지는 분석 그래프의 줄 범위로 정한다(이름 규칙을 다시 만들지 않는다): 함수(또는 그것을 담은 선언)의
// 시작·끝 줄이 그래프 노드의 line·endLine 과 같으면 그 노드 id 로 감싼다.
//
//   function f(a) { 몸통 }  →  function f(a) {const __vaT=__va.e("id",{a});return __va.run(__vaT,()=>{ 몸통 })}
//
// 몸통을 화살표 함수로 옮겨 AsyncLocalStorage 문맥 안에서 돌린다(부모 = 지금 문맥의 함수, 동시 실행에도 섞이지 않음).
// 글자를 끼워 넣기만 하므로 줄 위치는 그대로다. 생성자·제너레이터는 감싸지 않는다.
//
// Next(Turbopack) 서버 묶음은 instrumentBundle: 묶음 안 함수의 시작 위치를 소스맵으로 원본 파일·줄로 바꿔 같은 범위 표와 맞춘다.

import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const ts = require('typescript')

const isFn = (n) =>
  ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) || ts.isMethodDeclaration(n) || ts.isConstructorDeclaration(n)

/** 함수를 담은 선언(변수·클래스 속성·객체 속성): 그래프는 이 줄 범위로 노드를 둔다 */
function holderOf(fn) {
  for (let h = fn.parent, k = 0; h && k < 4; h = h.parent, k++) {
    if (ts.isVariableDeclaration(h) || ts.isPropertyDeclaration(h) || ts.isPropertyAssignment(h)) return h
    if (isFn(h) || ts.isBlock(h)) return undefined
  }
  return undefined
}

/** spans: [[시작 줄, 끝 줄, id], …]. 감쌀 것이 없으면 null */
export function instrumentNode(source, file, spans) {
  if (!spans?.length) return null
  const kind = /\.tsx$/.test(file) ? ts.ScriptKind.TSX : /\.[cm]?ts$/.test(file) ? ts.ScriptKind.TS : /\.jsx$/.test(file) ? ts.ScriptKind.JSX : ts.ScriptKind.JS
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, kind)
  const byRange = new Map(spans.map(([a, b, id]) => [`${a}:${b}`, id]))
  const lineOf = (pos) => sf.getLineAndCharacterOfPosition(pos).line + 1
  const rangeOf = (n) => `${lineOf(n.getStart(sf))}:${lineOf(n.getEnd())}`
  return wrapFunctions(source, sf, (fn) => {
    const own = byRange.get(rangeOf(fn))
    if (own) return own
    const h = holderOf(fn)
    // 변수는 파일 맨 위 것만(지역 변수에 담긴 콜백은 그 함수의 일부)
    const top = h?.parent?.parent?.parent
    if (!h || (ts.isVariableDeclaration(h) && !(top && ts.isSourceFile(top)))) return undefined
    return byRange.get(rangeOf(h))
  })
}

/**
 * Next(Turbopack) 서버 묶음: module.exports = ["[project]/경로 [app-route] (ecmascript)", (ctx) => { 모듈 }, …].
 * 함수 시작 위치 → 소스맵 → 원본 (절대 경로, 줄) → spansByFile 의 시작 줄과 같은 id. 맞는 것이 없으면 null
 */
export function instrumentBundle(source, file, spansByFile, map) {
  if (!source.includes('"[project]/')) return null
  const byStart = new Map()
  for (const [abs, spans] of Object.entries(spansByFile)) for (const [a, , id] of spans) byStart.set(`${abs}:${a}`, id)
  if (!byStart.size) return null
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
  const origin = (node) => {
    const { line, character } = sf.getLineAndCharacterOfPosition(node.getStart(sf))
    const e = map.findEntry(line, character)
    if (!e?.originalSource) return undefined
    const abs = e.originalSource.startsWith('file://') ? fileURLToPath(e.originalSource) : e.originalSource
    return byStart.get(`${abs}:${e.originalLine + 1}`)
  }
  return wrapFunctions(source, sf, (fn) => {
    const own = origin(fn)
    if (own) return own
    const h = holderOf(fn)
    return h ? origin(h) : undefined
  })
}

/** pick(함수) → id 인 함수의 몸통을 감싼다. 하나도 없으면 null */
function wrapFunctions(source, sf, pick) {
  const used = new Set()
  const inserts = [] // [위치, 글자, 닫기?, 깊이]
  const argsObject = (fn) => {
    const names = []
    const collect = (name) => {
      if (ts.isIdentifier(name)) {
        if (name.text !== 'this') names.push(name.text)
      } else for (const el of name.elements) if (!ts.isOmittedExpression(el)) collect(el.name)
    }
    fn.parameters.forEach((p) => collect(p.name))
    return names.length ? `{${names.join(',')}}` : 'null'
  }
  const wrap = (fn, id, depth) => {
    const isAsync = !!fn.modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)
    const head = `const __vaT=__va.e(${JSON.stringify(id)},${argsObject(fn)});return __va.run(__vaT,${isAsync ? 'async ' : ''}()=>`
    if (ts.isBlock(fn.body)) {
      inserts.push([fn.body.getStart(sf) + 1, head + '{', false, depth])
      inserts.push([fn.body.getEnd() - 1, '})', true, depth])
    } else {
      inserts.push([fn.body.getStart(sf), `{${head}(`, false, depth])
      inserts.push([fn.body.getEnd(), '))}', true, depth])
    }
  }
  const visit = (node, depth) => {
    if (isFn(node) && node.body && !node.asteriskToken && !ts.isConstructorDeclaration(node)) {
      const id = pick(node)
      if (id && !used.has(id)) {
        used.add(id)
        wrap(node, id, depth)
      }
      ts.forEachChild(node, (c) => visit(c, depth + 1))
      return
    }
    ts.forEachChild(node, (c) => visit(c, depth))
  }
  visit(sf, 0)
  if (!inserts.length) return null
  // 같은 자리: 닫기 먼저(안쪽부터), 그다음 열기(바깥부터)
  inserts.sort((a, b) => a[0] - b[0] || (a[2] === b[2] ? (a[2] ? b[3] - a[3] : a[3] - b[3]) : a[2] ? -1 : 1))
  let out = ''
  let at = 0
  for (const [pos, text] of inserts) {
    out += source.slice(at, pos) + text
    at = pos
  }
  return out + source.slice(at)
}
