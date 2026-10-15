import assert from 'node:assert/strict'

import { test } from 'vitest'

import { updateAllRefusal, updatesDisabledMessage } from './update-policy'

test('fixed-build update-all returns refused rows without dispatching updates', () => {
  const connections = [
    { id: 'local', label: 'Local', kind: 'local' },
    { id: 'ssh', label: 'Server', kind: 'ssh' },
    { id: 'remote', label: 'Remote', kind: 'remote' },
    { id: 'cloud', label: 'Cloud', kind: 'cloud' }
  ]

  const result = updateAllRefusal(connections, ['ssh'])

  assert.equal(result.ok, false)
  assert.deepEqual(result.results.map(row => row.connectionId), ['local', 'remote', 'cloud'])

  for (const row of result.results) {
    assert.equal(row.ok, false)
    assert.equal(row.skipped, true)
    assert.equal(row.reason, 'updates-disabled')
    assert.equal(row.detail, updatesDisabledMessage)
  }

  assert.deepEqual(updateAllRefusal([], []).results, [])
  assert.deepEqual(updateAllRefusal(connections, connections.map(row => row.id)).results, [])
})
