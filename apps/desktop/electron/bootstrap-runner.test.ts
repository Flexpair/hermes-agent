import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import https from 'node:https'
import os from 'node:os'
import path from 'node:path'
import { Readable } from 'node:stream'

import { test, vi } from 'vitest'

import {
  buildPinArgs,
  buildPosixPinArgs,
  cachedScriptPath,
  cleanInstallerLogLine,
  hasExistingGitCheckout,
  installRefForStamp,
  isPinnedCommit,
  resolveInstallScript,
  resolveMarkerPinnedCommit,
  runBootstrap
} from './bootstrap-runner'

const SCRIPT_NAME = process.platform === 'win32' ? 'install.ps1' : 'install.sh'
const ZERO_COMMIT = '0000000000000000000000000000000000000000'

function mkTmpHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-bootstrap-test-'))
}

test('runBootstrap bails immediately when the signal is already aborted', async () => {
  const controller = new AbortController()
  controller.abort()

  const events = []

  const result = await runBootstrap({
    installStamp: null,
    activeRoot: '/tmp/hermes-runner-test',
    sourceRepoRoot: null,
    hermesHome: '/tmp/hermes-runner-test',
    logRoot: '/tmp/hermes-runner-test',
    onEvent: ev => events.push(ev),
    abortSignal: controller.signal
  })

  // Cancelled before any install script is spawned.
  assert.deepEqual(result, { ok: false, cancelled: true })
  assert.ok(
    events.some(ev => ev.type === 'failed' && /cancelled/i.test(ev.error)),
    'should emit a cancelled failure event'
  )
})

test('existing checkout detection requires git metadata', () => {
  const home = mkTmpHome()

  try {
    const activeRoot = path.join(home, 'hermes-agent')
    assert.equal(hasExistingGitCheckout(activeRoot), false)

    fs.mkdirSync(path.join(activeRoot, '.git'), { recursive: true })
    assert.equal(hasExistingGitCheckout(activeRoot), true)
  } finally {
    fs.rmSync(home, { recursive: true, force: true })
  }
})

test('fresh bootstrap args include the packaged commit pin', () => {
  const installStamp = { commit: 'a'.repeat(40), branch: 'main' }

  assert.deepEqual(buildPinArgs(installStamp), ['-Commit', installStamp.commit, '-Branch', 'main'])
  assert.deepEqual(
    buildPosixPinArgs({
      installStamp,
      activeRoot: '/tmp/hermes-agent',
      hermesHome: '/tmp/hermes'
    }),
    ['--dir', '/tmp/hermes-agent', '--hermes-home', '/tmp/hermes', '--branch', 'main', '--commit', installStamp.commit]
  )
})

async function assertFreshDownloadedBootstrap(branch: string, useFlexpair: boolean, fallback = false) {
  const home = mkTmpHome()
  const activeRoot = path.join(home, 'checkout')
  const origin = path.join(home, 'origin')
  const git = (...args: string[]) => execFileSync('git', args, { cwd: origin, encoding: 'utf8' }).trim()
  const author = ['-c', 'user.name=Bootstrap Fixture', '-c', 'user.email=bootstrap@example.test', '-c', 'commit.gpgsign=false']
  const urls: string[] = []

  const installer = [
    '#!/usr/bin/env bash',
    'set -e',
    'printf "%s\\n" "$@" >> "$HERMES_HOME/invocations"',
    'printf "%s\\n" "---" >> "$HERMES_HOME/invocations"',
    'if [ "$1" = "--manifest" ]; then',
    '  printf "%s\\n" \'{"stages":[{"name":"checkout"}]}\'',
    'else',
    ...(useFlexpair
      ? ['  for arg in "$@"; do [ "$arg" != "--commit" ] || { echo "commit pin forbidden" >&2; exit 1; }; done']
      : []),
    '  branch="" dir="" commit=""',
    '  while [ "$#" -gt 0 ]; do',
    '    case "$1" in',
    '      --branch) branch="$2"; shift 2 ;;',
    '      --dir) dir="$2"; shift 2 ;;',
    '      --commit) commit="$2"; shift 2 ;;',
    '      *) shift ;;',
    '    esac',
    '  done',
    '  git clone -q --branch "$branch" "$HERMES_HOME/origin" "$dir"',
    '  if [ -n "$commit" ]; then git -C "$dir" checkout -q --detach "$commit"; fi',
    '  printf "%s\\n" \'{"ok":true,"stage":"checkout"}\'',
    'fi',
    ''
  ].join('\n')

  const getSpy = vi.spyOn(https, 'get').mockImplementation(((url: string, callback: (response: any) => void) => {
    urls.push(String(url))
    const response = Object.assign(Readable.from([installer]), { statusCode: 200 })
    process.nextTick(() => callback(response))

    return new EventEmitter()
  }) as unknown as typeof https.get)

  try {
    fs.mkdirSync(origin)
    git('init', '-q', '-b', branch)
    git(...author, 'commit', '--allow-empty', '-qm', 'packaged')
    const packagedCommit = git('rev-parse', 'HEAD')
    git(...author, 'commit', '--allow-empty', '-qm', 'branch head')
    const branchHead = git('rev-parse', 'HEAD')

    const result = await runBootstrap({
      installStamp: { commit: fallback ? ZERO_COMMIT : packagedCommit, branch },
      activeRoot,
      sourceRepoRoot: null,
      hermesHome: home,
      logRoot: home
    })

    assert.equal(result.ok, true, result.error)
    const installedGitHead = execFileSync('git', ['-C', activeRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
    assert.equal(installedGitHead, useFlexpair || fallback ? branchHead : packagedCommit)

    if (useFlexpair || fallback) {
      const installedBranch = execFileSync('git', ['-C', activeRoot, 'symbolic-ref', '--short', 'HEAD'], {
        encoding: 'utf8'
      }).trim()

      assert.equal(installedBranch, branch)
    }

    assert.equal(result.marker.pinnedCommit, installedGitHead)
    assert.equal(result.marker.pinnedBranch, branch)

    const ref = useFlexpair || fallback ? branch : packagedCommit
    const owner = useFlexpair ? 'Flexpair' : 'NousResearch'
    assert.deepEqual(urls, [`https://raw.githubusercontent.com/${owner}/hermes-agent/${ref}/scripts/install.sh`])

    const pinArgs = [
      '--dir', activeRoot,
      '--hermes-home', home,
      '--branch', branch,
      ...(useFlexpair || fallback ? [] : ['--commit', packagedCommit])
    ]

    const invocations = fs.readFileSync(path.join(home, 'invocations'), 'utf8')
      .split('---\n')
      .filter(Boolean)
      .map(invocation => invocation.trimEnd().split('\n'))

    assert.deepEqual(invocations, [
      ['--manifest', ...pinArgs],
      ['--stage', 'checkout', '--non-interactive', '--json', ...pinArgs]
    ])
  } finally {
    getSpy.mockRestore()
    fs.rmSync(home, { recursive: true, force: true })
  }
}

test.skipIf(process.platform === 'win32').each(['main', '2026-11-08-patched-extra', '2026-11-09-patched'])(
  'fresh upstream bootstrap pins %s and downloads from NousResearch',
  async branch => {
    await assertFreshDownloadedBootstrap(branch, false)
  }
)

test.skipIf(process.platform === 'win32')('fresh dated patched bootstrap follows the Linux Flexpair branch', async () => {
  await assertFreshDownloadedBootstrap('2026-11-08-patched', process.platform === 'linux')
})

test.skipIf(process.platform !== 'linux')('fallback stamp follows the Linux Flexpair branch', async () => {
  await assertFreshDownloadedBootstrap('2026-11-08-patched', true, true)
})

test.skipIf(process.platform !== 'linux')('fallback stamp on an upstream branch still uses NousResearch', async () => {
  await assertFreshDownloadedBootstrap('main', false, true)
})

test.skipIf(process.platform !== 'linux')('missing and malformed stamps cannot resolve the Flexpair installer', async () => {
  for (const installStamp of [
    null,
    { branch: '2026-11-08-patched' },
    { commit: '000000', branch: '2026-11-08-patched' },
    { commit: '0'.repeat(41), branch: '2026-11-08-patched' },
    { commit: 'not-a-commit', branch: '2026-11-08-patched' }
  ]) {
    await assert.rejects(
      resolveInstallScript({
        installStamp,
        sourceRepoRoot: null,
        hermesHome: '',
        emit: () => {},
        _download: async () => {
          throw new Error('unexpected download')
        }
      }),
      /no install stamp/
    )
  }
})

test('existing-checkout bootstrap args keep branch but skip the packaged commit pin', () => {
  const installStamp = { commit: 'a'.repeat(40), branch: 'main' }

  assert.deepEqual(buildPinArgs(installStamp, { pinCommit: false }), ['-Branch', 'main'])
  assert.deepEqual(
    buildPosixPinArgs({
      installStamp,
      activeRoot: '/tmp/hermes-agent',
      hermesHome: '/tmp/hermes',
      pinCommit: false
    }),
    ['--dir', '/tmp/hermes-agent', '--hermes-home', '/tmp/hermes', '--branch', 'main']
  )
})

test('fallback install stamps use an unpinned branch ref', () => {
  const stamp = { commit: ZERO_COMMIT, branch: 'main' }

  assert.equal(isPinnedCommit(ZERO_COMMIT), false)
  assert.deepEqual(installRefForStamp(stamp), {
    ref: 'main',
    cacheKey: 'branch-main',
    pinned: false
  })
  // Must NOT pass -Commit / --commit for the all-zero placeholder.
  assert.deepEqual(buildPinArgs(stamp), ['-Branch', 'main'])
  assert.deepEqual(
    buildPosixPinArgs({
      installStamp: stamp,
      activeRoot: '/tmp/hermes',
      hermesHome: '/tmp/home'
    }),
    ['--dir', '/tmp/hermes', '--hermes-home', '/tmp/home', '--branch', 'main']
  )
})

test('existing-checkout installer ref follows the branch instead of the packaged commit', () => {
  const stamp = { commit: 'a'.repeat(40), branch: 'main' }

  assert.deepEqual(installRefForStamp(stamp, { pinCommit: false }), {
    ref: 'main',
    cacheKey: 'branch-main',
    pinned: false
  })
  assert.deepEqual(installRefForStamp(stamp), {
    ref: stamp.commit,
    cacheKey: stamp.commit,
    pinned: true
  })
})

test('resolveMarkerPinnedCommit prefers installed checkout HEAD over the packaged artifact', () => {
  const realHead = 'c'.repeat(40)
  assert.equal(
    resolveMarkerPinnedCommit({ commit: ZERO_COMMIT, branch: 'main' }, '/tmp/checkout', {
      resolveHead: () => realHead
    }),
    realHead
  )
  assert.equal(
    resolveMarkerPinnedCommit({ commit: 'd'.repeat(40), branch: 'main' }, '/tmp/checkout', {
      resolveHead: () => realHead
    }),
    realHead,
    'the installed checkout owns source runtime identity'
  )
  assert.equal(
    resolveMarkerPinnedCommit({ commit: ZERO_COMMIT, branch: 'main' }, '/tmp/missing', {
      resolveHead: () => null
    }),
    null
  )
})

test('resolveInstallScript downloads fallback stamps by branch instead of zero commit', async () => {
  const home = mkTmpHome()

  try {
    const cached = cachedScriptPath(home, 'branch-main')
    fs.mkdirSync(path.dirname(cached), { recursive: true })
    fs.writeFileSync(cached, 'stale branch installer\n')

    const refs = []

    const result = await resolveInstallScript({
      installStamp: { commit: ZERO_COMMIT, branch: 'main' },
      sourceRepoRoot: null,
      hermesHome: home,
      emit: () => {},
      _download: async (ref, destPath) => {
        refs.push(ref)
        fs.mkdirSync(path.dirname(destPath), { recursive: true })
        fs.writeFileSync(destPath, '#!/bin/sh\necho fallback branch\n')

        return destPath
      }
    })

    assert.deepEqual(refs, ['main'])
    assert.equal(result.source, 'download')
    assert.equal(result.commit, null)
    assert.equal(result.path, cached)
    assert.match(fs.readFileSync(cached, 'utf8'), /fallback branch/)
  } finally {
    fs.rmSync(home, { recursive: true, force: true })
  }
})

test('resolveInstallScript refreshes the live branch for an existing checkout', async () => {
  const home = mkTmpHome()

  try {
    const commit = 'a'.repeat(40)
    const cached = cachedScriptPath(home, 'branch-main')
    fs.mkdirSync(path.dirname(cached), { recursive: true })
    fs.writeFileSync(cached, 'stale installer\n')

    const refs = []

    const result = await resolveInstallScript({
      installStamp: { commit, branch: 'main' },
      sourceRepoRoot: null,
      hermesHome: home,
      emit: () => {},
      pinCommit: false,
      _download: async (ref, destPath) => {
        refs.push(ref)
        fs.writeFileSync(destPath, 'fresh branch installer\n')

        return destPath
      }
    })

    assert.deepEqual(refs, ['main'])
    assert.equal(result.source, 'download')
    assert.equal(result.commit, null)
    assert.equal(result.path, cached)
    assert.equal(fs.readFileSync(cached, 'utf8'), 'fresh branch installer\n')
  } finally {
    fs.rmSync(home, { recursive: true, force: true })
  }
})

test('resolveInstallScript refreshes an immutable-pin cache on a fresh install', async () => {
  const home = mkTmpHome()

  try {
    const commit = 'a'.repeat(40)
    const cached = cachedScriptPath(home, commit)
    fs.mkdirSync(path.dirname(cached), { recursive: true })
    fs.writeFileSync(cached, 'stale installer\n')

    const refs = []

    const result = await resolveInstallScript({
      installStamp: { commit, branch: 'main' },
      sourceRepoRoot: null,
      hermesHome: home,
      emit: () => {},
      _download: async (ref, destPath) => {
        refs.push(ref)
        fs.writeFileSync(destPath, 'fresh pinned installer\n')

        return destPath
      }
    })

    assert.deepEqual(refs, [commit])
    assert.equal(result.source, 'download')
    assert.equal(result.commit, commit)
    assert.equal(result.path, cached)
    assert.equal(fs.readFileSync(cached, 'utf8'), 'fresh pinned installer\n')
  } finally {
    fs.rmSync(home, { recursive: true, force: true })
  }
})

test('resolveInstallScript fails closed instead of executing an installed stale script', async () => {
  const home = mkTmpHome()

  try {
    const commit = 'a'.repeat(40)
    const scriptsDir = path.join(home, 'hermes-agent', 'scripts')
    fs.mkdirSync(scriptsDir, { recursive: true })
    fs.writeFileSync(path.join(scriptsDir, SCRIPT_NAME), 'stale installed script\n')

    await assert.rejects(
      resolveInstallScript({
        installStamp: { commit, branch: 'main' },
        sourceRepoRoot: null,
        hermesHome: home,
        emit: () => {},
        _download: async () => {
          throw new Error('Failed to download install script: HTTP 404')
        }
      }),
      /HTTP 404/
    )
  } finally {
    fs.rmSync(home, { recursive: true, force: true })
  }
})

// #112675: install.sh colours its banners and curl/uv redraw progress with \r
// even into a pipe; the overlay renders lines as plain text, so the emitter
// must hand every consumer (log ring, Details panel, Copy output) the text a
// terminal would be left showing.
test('installer log lines reach the emitter without escape sequences; \\r redraws keep the last frame', () => {
  assert.equal(cleanInstallerLogLine('\u001b[0;32m✓\u001b[0m Detected: macos (macos)'), '✓ Detected: macos (macos)')
  assert.equal(cleanInstallerLogLine('\u001b[2K\u001b[1GCloning repository…\u001b[K'), 'Cloning repository…')
  assert.equal(cleanInstallerLogLine('\u001b]0;hermes\u0007Installing Hermes'), 'Installing Hermes')
  assert.equal(cleanInstallerLogLine('\r 12%\r 67%\r100%\u001b[K'), '100%')
  assert.equal(cleanInstallerLogLine('Resolving dependencies…\r'), 'Resolving dependencies…')
  // Only-escape frames drop entirely, so the caller emits nothing for them.
  assert.equal(cleanInstallerLogLine('\u001b[0m\r'), '')
  // Plain multi-byte text is untouched.
  assert.equal(cleanInstallerLogLine('Ready — café ✓ 中文'), 'Ready — café ✓ 中文')
})

test.skipIf(process.platform === 'win32')(
  'a manifest-step failure surfaces the installer tail without escape sequences',
  async () => {
    const home = mkTmpHome()
    fs.mkdirSync(path.join(home, 'scripts'))
    fs.writeFileSync(
      path.join(home, 'scripts', 'install.sh'),
      '#!/usr/bin/env bash\nprintf "\\033[0;31m\\xe2\\x9c\\x97\\033[0m manifest broke\\n" >&2\nexit 3\n'
    )

    const result = await runBootstrap({
      installStamp: null,
      activeRoot: home,
      sourceRepoRoot: home,
      hermesHome: home,
      logRoot: home,
      onEvent: () => {}
    })

    assert.equal(result.ok, false)
    assert.equal(result.error, 'install.sh --manifest failed: exit 3\n✗ manifest broke')
  }
)
