import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const HERE = dirname(fileURLToPath(import.meta.url))
const require = createRequire(import.meta.url)
const pkgDir = (name: string) => dirname(require.resolve(`${name}/package.json`))
const versionOf = (name: string) => JSON.parse(readFileSync(join(pkgDir(name), 'package.json'), 'utf-8')).version as string

/** 글꼴을 앱이 담는다 — SYNC-UI-001 3.2 · SYNC-INFRA-001 3장(카드 BC). CDN을 부르지 않는다.
 *  설치된 npm 패키지(판 고정)에서 쓰는 파일만 `public/fonts/{패키지}-{판}/`로 옮긴다(gitignore). 경로에 판 번호가
 *  있어 서버가 1년 immutable로 준다. 화면 틀(index.html)에 링크를 넣고, 같은 주소를 `__FONT_CSS__`로 코드에 준다 —
 *  폐쇄망판 배치 iframe이 바깥 글꼴 링크를 이것으로 바꾼다(STD-002 V-UI). */
function appFonts(): Plugin {
  const sans = `pretendard-${versionOf('pretendard')}`
  const mono = `ibm-plex-mono-${versionOf('@fontsource/ibm-plex-mono')}`
  const css = { sans: `/fonts/${sans}/pretendardvariable-dynamic-subset.css`, mono: `/fonts/${mono}/mono.css` }
  const out = join(HERE, 'public', 'fonts')
  const copy = () => {
    rmSync(out, { recursive: true, force: true }) // 옛 판 폴더를 남기지 않는다
    // Pretendard — CDN이 주던 것과 같은 동적 부분집합(유니코드 범위마다 woff2 하나, 필요한 것만 받는다)
    const pv = join(pkgDir('pretendard'), 'dist', 'web', 'variable')
    mkdirSync(join(out, sans), { recursive: true })
    copyFileSync(join(pv, 'pretendardvariable-dynamic-subset.css'), join(out, sans, 'pretendardvariable-dynamic-subset.css'))
    cpSync(join(pv, 'woff2-dynamic-subset'), join(out, sans, 'woff2-dynamic-subset'), { recursive: true })
    // IBM Plex Mono — 쓰는 굵기 셋(UI-001 3.2)의 CSS를 하나로 잇고, 그 CSS가 부르는 파일만
    const md = pkgDir('@fontsource/ibm-plex-mono')
    const text = ['400', '500', '600'].map((w) => readFileSync(join(md, `${w}.css`), 'utf-8')).join('\n')
    mkdirSync(join(out, mono, 'files'), { recursive: true })
    writeFileSync(join(out, mono, 'mono.css'), text)
    for (const [, f] of text.matchAll(/url\(\.\/files\/([^)]+)\)/g)) copyFileSync(join(md, 'files', f), join(out, mono, 'files', f))
    // 글꼴 사용권(OFL) — 파일과 함께 둔다
    for (const [name, dir] of [
      ['pretendard', sans],
      ['@fontsource/ibm-plex-mono', mono],
    ]) {
      const lic = ['LICENSE', 'LICENSE.txt', 'dist/LICENSE.txt'].map((f) => join(pkgDir(name), f)).find(existsSync)
      if (lic) copyFileSync(lic, join(out, dir, 'LICENSE'))
    }
  }
  return {
    name: 'syncdoc-fonts',
    config: () => ({ define: { __FONT_CSS__: JSON.stringify(css) } }),
    buildStart: copy,
    transformIndexHtml: () => [
      { tag: 'link', attrs: { rel: 'stylesheet', href: css.sans }, injectTo: 'head' },
      { tag: 'link', attrs: { rel: 'stylesheet', href: css.mono }, injectTo: 'head' },
    ],
  }
}

// SYNC-INFRA-001 3·4장 — React 빌드 결과는 FastAPI가 `/`에서 서빙(syncdoc/web/static). 개발 중엔 :8000으로 프록시.
export default defineConfig({
  plugins: [react(), appFonts()],
  build: { outDir: '../backend/app/web/static', emptyOutDir: true },
  server: {
    proxy: { '/api': 'http://localhost:8000', '/auth': 'http://localhost:8000', '/mcp': 'http://localhost:8000' },
  },
})
