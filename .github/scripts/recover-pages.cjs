'use strict';

const PAGES_WORKFLOW = 'pages build and deployment';
const MAX_ATTEMPTS = 3;

module.exports = async function recoverPages({ github, context, core }) {
  const repo = context.repo;
  const { data: repository } = await github.rest.repos.get(repo);
  const branch = repository.default_branch;
  const readHead = async () => (await github.rest.repos.getBranch({ ...repo, branch })).data.commit.sha;
  const head = await readHead();
  const { data } = await github.rest.actions.listWorkflowRunsForRepo({
    ...repo, branch, head_sha: head, per_page: 100,
  });
  const runs = data.workflow_runs.filter(run =>
    run.name === PAGES_WORKFLOW && run.head_sha === head &&
    run.head_branch === branch && run.head_repository?.full_name === repository.full_name);

  // Two branch-based Pages builds can exist for one commit. A successful or
  // active sibling makes a retry unnecessary; cancelled duplicates are ignored.
  if (runs.some(run => run.conclusion === 'success')) {
    core.info('Senaste versionen har publicerats.');
    return 'published';
  }
  if (runs.some(run => run.status !== 'completed')) {
    core.info('Publicering pågår redan.');
    return 'in_progress';
  }
  const failed = runs.filter(run => run.conclusion === 'failure' || run.conclusion === 'timed_out')
    .sort((a, b) => b.id - a.id)[0];
  if (!failed) {
    core.info('Ingen misslyckad Pages-körning för senaste versionen.');
    return 'nothing_to_retry';
  }
  // Read current state rather than trusting an old workflow_run event or list.
  const { data: current } = await github.rest.actions.getWorkflowRun({ ...repo, run_id: failed.id });
  if (current.status !== 'completed' || !['failure', 'timed_out'].includes(current.conclusion)) {
    return 'already_handled';
  }
  if (current.run_attempt >= MAX_ATTEMPTS) {
    core.setFailed(`Pages misslyckades efter ${MAX_ATTEMPTS} försök: ${current.html_url}`);
    return 'exhausted';
  }
  if (await readHead() !== head) {
    core.info('En nyare version finns; den äldre körningen startas inte om.');
    return 'superseded';
  }
  await github.rest.actions.reRunWorkflowFailedJobs({ ...repo, run_id: current.id });
  await core.summary.addRaw(`Pages startas om automatiskt: ${current.html_url} (försök ${current.run_attempt + 1}/${MAX_ATTEMPTS}).`).write();
  core.info(`Startade om misslyckade jobb i Pages-körning ${current.id}.`);
  return 'retried';
};
