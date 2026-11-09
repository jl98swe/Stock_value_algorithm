'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const recover = require('../.github/scripts/recover-pages.cjs');

function fixture(overrides = {}, options = {}) {
  const failed = { id: 42, name: 'pages build and deployment', head_sha: 'latest',
    head_branch: 'main', head_repository: { full_name: 'owner/repo' },
    status: 'completed', conclusion: 'failure', run_attempt: 1,
    html_url: 'https://github.com/owner/repo/actions/runs/42', ...overrides };
  const calls = [], errors = [];
  let reads = 0;
  const github = { rest: {
    repos: {
      get: async () => ({ data: { default_branch: 'main', full_name: 'owner/repo' } }),
      getBranch: async () => ({ data: { commit: { sha: ++reads > 1 && options.newHead ? 'newer' : 'latest' } } }),
    },
    actions: {
      listWorkflowRunsForRepo: async () => ({ data: { workflow_runs: options.runs || [failed] } }),
      getWorkflowRun: async () => ({ data: options.current || failed }),
      reRunWorkflowFailedJobs: async args => calls.push(args),
    },
  } };
  const core = { info() {}, setFailed: message => errors.push(message),
    summary: { addRaw() { return this; }, async write() {} } };
  return { run: () => recover({ github, core, context: { repo: { owner: 'owner', repo: 'repo' } } }), calls, errors, failed };
}

test('retries only failed jobs, preserving the existing Pages artifact', async () => {
  const f = fixture();
  assert.equal(await f.run(), 'retried');
  assert.deepEqual(f.calls, [{ owner: 'owner', repo: 'repo', run_id: 42 }]);
});
test('a service timeout is retried too', async () => {
  const f = fixture({ conclusion: 'timed_out', run_attempt: 2 });
  assert.equal(await f.run(), 'retried');
});
test('stops after three attempts and reports failure', async () => {
  const f = fixture({ run_attempt: 3 });
  assert.equal(await f.run(), 'exhausted');
  assert.equal(f.calls.length, 0);
  assert.match(f.errors[0], /3 försök/);
});
for (const [label, overrides] of Object.entries({
  'older commit': { head_sha: 'older' },
  'other branch': { head_branch: 'feature' },
  'other repository': { head_repository: { full_name: 'other/repo' } },
  'unrelated workflow': { name: 'Daglig marknadsuppdatering' },
  'cancelled duplicate': { conclusion: 'cancelled' },
})) {
  test(`does not retry ${label}`, async () => {
    const f = fixture(overrides);
    assert.equal(await f.run(), 'nothing_to_retry');
    assert.equal(f.calls.length, 0);
  });
}
test('successful sibling means the version is already published', async () => {
  const { failed } = fixture();
  const f = fixture({}, { runs: [failed, { ...failed, id: 43, conclusion: 'success' }] });
  assert.equal(await f.run(), 'published');
  assert.equal(f.calls.length, 0);
});
test('does not duplicate an active sibling publication', async () => {
  const { failed } = fixture();
  const f = fixture({}, { runs: [failed, { ...failed, id: 43, status: 'queued', conclusion: null }] });
  assert.equal(await f.run(), 'in_progress');
  assert.equal(f.calls.length, 0);
});
test('fresh state prevents replaying an already handled event', async () => {
  const f = fixture({}, { current: { status: 'in_progress', conclusion: null } });
  assert.equal(await f.run(), 'already_handled');
  assert.equal(f.calls.length, 0);
});
test('does not retry if main advances during the check', async () => {
  const f = fixture({}, { newHead: true });
  assert.equal(await f.run(), 'superseded');
  assert.equal(f.calls.length, 0);
});
