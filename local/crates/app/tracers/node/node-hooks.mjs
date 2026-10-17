// 싱크독 Node 로더 훅(module.register 로 등록, 별도 스레드에서 돈다) — view_arc에서 옮겼다(카드 L29).
// 프로젝트 서버 파일(그래프에 함수가 있는 파일)을 읽을 때 원본(TS·JS)에 기록 코드를 끼운다.
// node-tracer.mjs 가 다른 로더(tsx 등)보다 먼저 등록하므로, 여기서 받는 것은 변환 전 원본이고
// 끼운 뒤에 tsx·Node 타입 제거가 이어서 JS 로 바꾼다.

import { fileURLToPath } from 'node:url'
import { instrumentNode } from './node-instrument.mjs'

let FILES = {}

export async function initialize(data) {
  FILES = data?.files ?? {}
}

export async function load(url, context, nextLoad) {
  const result = await nextLoad(url, context)
  if (!url.startsWith('file:') || result.source == null) return result
  let file
  try {
    file = fileURLToPath(url)
  } catch {
    return result
  }
  const spans = FILES[file]
  if (!spans) return result
  try {
    const source = typeof result.source === 'string' ? result.source : Buffer.from(result.source).toString('utf8')
    const out = instrumentNode(source, file, spans)
    if (out) return { ...result, source: out }
  } catch (error) {
    process.stderr.write(`[syncdoc] 계측하지 못해 원본으로 실행: ${file} (${error?.message ?? error})\n`)
  }
  return result
}
