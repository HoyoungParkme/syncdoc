// 브라우저로 가는 모듈 코드(Vite가 TS·JSX를 JS로 바꾼 것)에 실행 기록 코드를 끼워 넣는다 (SYNC-INFRA-001 9.9, 카드 L29).
// view_arc web-instrument를 옮겼다. 함수는 이름으로 그래프 열쇠(`파일:줄`)를 찾는다 — 화면 모듈은 Vite가 다시 써서
// 줄이 원본과 다를 수 있다. 이름 표(byName: 파일 → 이름 → 열쇠)는 기록 도구가 서버의 범위에서 만든다.
//
// - 일반 함수·메서드: 진입·반환·예외를 기록한다.
// - 컴포넌트(대문자로 시작)·훅(use…): 렌더 자체는 너무 자주 일어나므로 감싸지 않고, 그 안의 콜백(onClick, useEffect …)을
//   "그 컴포넌트의 콜백"으로 기록한다. 이것이 사용자 상호작용의 시작점이 된다.
// 코드는 위치에 글자를 끼워 넣기만 한다(지우거나 바꾸지 않음).

import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const ts = require('typescript')

function defaultName(file) {
  const base = path.posix.basename(file).replace(/\.[^.]+$/, '')
  return base === 'index' ? path.posix.basename(path.posix.dirname(file)) || 'default' : base
}

function unwrapParens(expr) {
  while (ts.isParenthesizedExpression(expr) || ts.isAsExpression(expr) || ts.isSatisfiesExpression(expr)) expr = expr.expression
  return expr
}

/** () => {}, function () {}, memo(() => {}), forwardRef(function ...) 에서 함수를 꺼낸다 */
function unwrapFunction(expr, depth = 0) {
  expr = unwrapParens(expr)
  if (ts.isArrowFunction(expr) || ts.isFunctionExpression(expr)) return expr
  if (ts.isCallExpression(expr) && depth < 3) {
    const callee = expr.expression.getText()
    if (/(^|\.)(memo|forwardRef|observer|useCallback|withRouter)$/.test(callee))
      for (const arg of expr.arguments) {
        const fn = unwrapFunction(arg, depth + 1)
        if (fn) return fn
      }
  }
  return undefined
}

/** 콜백이 어디에 쓰였는지: 변수 이름, JSX 속성(onClick), 받는 함수(useEffect, .then) */
function callbackName(fn) {
  if (fn.name && ts.isIdentifier(fn.name)) return fn.name.text
  const parent = fn.parent
  if (ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) return parent.name.text
  if (ts.isPropertyAssignment(parent)) return ts.isStringLiteral(parent.name) ? parent.name.text : parent.name.getText()
  if (ts.isJsxExpression(parent) && ts.isJsxAttribute(parent.parent)) return parent.parent.name.getText()
  if (ts.isCallExpression(parent)) {
    let callee = parent.expression
    while (ts.isParenthesizedExpression(callee)) callee = callee.expression
    if (ts.isBinaryExpression(callee) && callee.operatorToken.kind === ts.SyntaxKind.CommaToken) callee = callee.right
    if (ts.isElementAccessExpression(callee) && ts.isStringLiteral(callee.argumentExpression)) return callee.argumentExpression.text
    if (ts.isPropertyAccessExpression(callee)) return '.' + callee.name.text
    const text = callee.getText()
    return text.length > 30 ? undefined : text
  }
  return undefined
}

const isFunctionLike = (n) =>
  ts.isFunctionDeclaration(n) || ts.isArrowFunction(n) || ts.isFunctionExpression(n) || ts.isMethodDeclaration(n) || ts.isConstructorDeclaration(n)

/** 컴포넌트·훅인가 — 대문자로 시작(.tsx·.jsx) · use + 대문자 */
const roleOf = (file, name) => (/^use[A-Z]/.test(name) ? 'hook' : /\.(tsx|jsx)$/.test(file) && /^[A-Z]/.test(name) ? 'component' : 'function')

/**
 * Vite처럼 파일 하나가 모듈 하나로 오는 경우. keyOf(파일, 이름) → 그래프 열쇠. 계측할 것이 없으면 null(그대로 보낸다)
 */
export function instrument(code, file, keyOf, scriptPath) {
  const sf = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS)
  const inserts = []
  let wrapped = 0
  let fid = 0

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

  const wrapReturns = (node, depth) => {
    ts.forEachChild(node, (child) => {
      if (isFunctionLike(child) || ts.isClassLike(child)) return
      if (ts.isReturnStatement(child) && child.expression) {
        const pair = ++fid
        inserts.push({ pos: child.expression.getStart(sf), text: '__va.r(__vaT,(', open: true, depth: depth + 0.5, fid: pair })
        inserts.push({ pos: child.expression.getEnd(), text: '))', open: false, depth: depth + 0.5, fid: pair })
      }
      wrapReturns(child, depth)
    })
  }

  const wrap = (fn, id, via, depth) => {
    if (!fn.body || fn.asteriskToken || ts.isConstructorDeclaration(fn)) return
    if (ts.isBlock(fn.body) && fn.body.statements.length === 0) return
    wrapped++
    const pair = ++fid
    const from = sf.getLineAndCharacterOfPosition(fn.getStart(sf)).line + 1
    const to = sf.getLineAndCharacterOfPosition(fn.getEnd()).line + 1
    const head = `const __vaT=__va.e(${JSON.stringify(id)},${JSON.stringify(via)},${argsObject(fn)},${JSON.stringify(scriptPath)},${from},${to});try{`
    const tail = '}catch(__vaE){__va.x(__vaT,__vaE);throw __vaE}finally{__va.f(__vaT)}'
    if (ts.isBlock(fn.body)) {
      inserts.push({ pos: fn.body.getStart(sf) + 1, text: head, open: true, depth, fid: pair })
      inserts.push({ pos: fn.body.getEnd() - 1, text: tail, open: false, depth, fid: pair })
      wrapReturns(fn.body, depth)
    } else {
      inserts.push({ pos: fn.body.getStart(sf), text: `{${head}return __va.r(__vaT,(`, open: true, depth, fid: pair })
      inserts.push({ pos: fn.body.getEnd(), text: `))${tail}}`, open: false, depth, fid: pair })
    }
  }

  const wrapCallbacks = (node, owner, depth) => {
    ts.forEachChild(node, (child) => {
      if (ts.isClassLike(child)) return
      if (isFunctionLike(child)) {
        wrap(child, owner, callbackName(child) ?? 'callback', depth)
        if (child.body) wrapCallbacks(child.body, owner, depth + 1)
        return
      }
      wrapCallbacks(child, owner, depth)
    })
  }

  const visit = (name, fn, ...alt) => {
    const id = [name, ...alt].map((n) => keyOf(file, n)).find(Boolean)
    if (!id) return
    const role = roleOf(file, name.split('.').pop())
    if (role === 'component' || role === 'hook') {
      if (fn.body) wrapCallbacks(fn.body, id, 1)
    } else wrap(fn, id, null, 0)
  }

  for (const stmt of sf.statements) {
    if (ts.isFunctionDeclaration(stmt) && stmt.body) visit(stmt.name?.text ?? defaultName(file), stmt)
    else if (ts.isVariableStatement(stmt)) {
      for (const decl of stmt.declarationList.declarations) {
        if (!ts.isIdentifier(decl.name) || !decl.initializer) continue
        const fn = unwrapFunction(decl.initializer)
        if (fn) {
          visit(decl.name.text, fn)
          continue
        }
        const obj = unwrapParens(decl.initializer)
        if (!ts.isObjectLiteralExpression(obj)) continue
        for (const p of obj.properties) {
          if (ts.isMethodDeclaration(p) && p.body && ts.isIdentifier(p.name)) visit(`${decl.name.text}.${p.name.text}`, p, p.name.text)
          else if (ts.isPropertyAssignment(p) && ts.isIdentifier(p.name)) {
            const inner = unwrapFunction(p.initializer)
            if (inner) visit(`${decl.name.text}.${p.name.text}`, inner, p.name.text)
          }
        }
      }
    } else if (ts.isClassDeclaration(stmt)) {
      const cls = stmt.name?.text ?? defaultName(file)
      for (const member of stmt.members) {
        if (ts.isMethodDeclaration(member) && member.body && member.name) visit(`${cls}.${member.name.getText(sf)}`, member, member.name.getText(sf))
        else if (ts.isPropertyDeclaration(member) && member.initializer && member.name) {
          const fn = unwrapFunction(member.initializer)
          if (fn) visit(`${cls}.${member.name.getText(sf)}`, fn, member.name.getText(sf))
        }
      }
    }
  }
  if (!wrapped) return null
  // 뒤에서부터 끼운다 — 같은 짝이면 닫는 것을 먼저, 다른 짝이면 여는 것을 먼저, 여는 것끼리는 안쪽부터
  inserts.sort((a, b) => {
    if (a.pos !== b.pos) return b.pos - a.pos
    if (a.fid === b.fid) return a.open ? 1 : -1
    if (a.open !== b.open) return a.open ? -1 : 1
    return a.open ? b.depth - a.depth : a.depth - b.depth
  })
  let out = code
  for (const ins of inserts) out = out.slice(0, ins.pos) + ins.text + out.slice(ins.pos)
  return out
}
