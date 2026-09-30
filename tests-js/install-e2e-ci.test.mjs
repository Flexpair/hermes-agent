import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workflow = fs.readFileSync(path.join(root, '.github/workflows/install-e2e.yml'), 'utf8');
const script = path.join(root, 'scripts/sandbox/generate-e2e-matrix.mjs');

test('Flexpair checks update refusal instead of the unsupported release upgrade matrix', () => {
  const fork = workflow.split('  fork-update-refusal:\n')[1].split('  pick-releases:\n')[0];
  const picker = workflow.split('  pick-releases:\n')[1].split('  generate-matrix:\n')[0];
  const report = workflow.split('  report:\n')[1];
  assert.match(fork, /if: github\.repository == 'Flexpair\/hermes-agent'/);
  assert.match(fork, /uses: \.\/\.github\/workflows\/flexpair-linux-config\.yml/);
  assert.match(picker, /if: github\.repository != 'Flexpair\/hermes-agent'/);
  assert.match(report, /if: always\(\) && github\.repository != 'Flexpair\/hermes-agent'/);
});

test('release picker fetches complete tag history rather than shallow tag tips', () => {
  const pick = workflow.split('  pick-releases:\n')[1].split('  generate-matrix:\n')[0];
  assert.match(pick, /fetch-depth: 0/);
});

test('result chart renders a failed picker with missing tag annotations', () => {
  const output = execFileSync(process.execPath, [script, '--format', 'results', '--tags', ''], {
    cwd: root,
    input: '{"name":"Pick release tags","conclusion":"failure"}\n',
    encoding: 'utf8',
  });
  assert.match(output, /no legs found/);
});
