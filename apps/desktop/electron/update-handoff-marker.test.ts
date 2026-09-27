import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..')
const POSIX_SCRIPT = path.join(REPO_ROOT, 'scripts', 'desktop-update', 'posix.sh')

function sandbox(tag: string) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), `hermes-handoff-marker-${tag}-`))
  const installRoot = path.join(home, 'hermes-agent')
  fs.mkdirSync(installRoot)

  return { home, installRoot }
}


function runPosix(installRoot: string, startedAt?: string) {
  const env: NodeJS.ProcessEnv = { ...process.env, HERMES_HOME: path.dirname(installRoot) }

  if (startedAt === undefined) {
    delete env.HERMES_UPDATE_STARTED_AT
  } else {
    env.HERMES_UPDATE_STARTED_AT = startedAt
  }

  return spawnSync(
    '/usr/bin/env',
    ['bash', POSIX_SCRIPT, '--daemonized', '--install-root', installRoot, '--self-test-marker'],
    {
      env,
      encoding: 'utf8'
    }
  )
}


test.skipIf(process.platform === 'win32')('POSIX hand-off refuses updates without creating a marker', () => {
  const { home, installRoot } = sandbox('disabled')
  const result = runPosix(installRoot, '1234567890')
  assert.equal(result.status, 2)
  assert.match(String(result.stderr), /Updates are disabled/)
  assert.equal(fs.existsSync(path.join(home, '.hermes-update-in-progress')), false)
})
