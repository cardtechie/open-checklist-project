// Close guard for work orders (#136). A PR linked to a work order closes it on merge,
// and GitHub has no non-closing link into the default branch, so a work order closed by
// a PR is reopened here unless that PR carries the completes-work-order label.
// Run by .github/workflows/work-order-close-guard.yml through actions/github-script.
// Tests: node --test .github/scripts/work-order-close-guard.test.js

const WORK_ORDER_TYPE = 'Work Order';
const ESCAPE_LABEL = 'completes-work-order';
// GitHub allows at most 100 labels on an issue or pull request, so one page of 100 is
// the whole set. run() still checks totalCount and fails rather than decide on a partial list.
const LABEL_PAGE = 100;
const COMMENT_AUTHOR = 'github-actions[bot]';

// Pure decision. closer is { __typename, number?, labels? } or null (a hand close).
// labels is a list of label names. Returns { action: 'reopen', pr } or
// { action: 'leave', reason }.
function decide({ issueTypeName, isPullRequest, closer, labels }) {
  if (isPullRequest) return { action: 'leave', reason: 'item is a pull request' };
  if (issueTypeName !== WORK_ORDER_TYPE) return { action: 'leave', reason: 'not a work order' };
  if (!closer) return { action: 'leave', reason: 'closed by hand' };
  if (closer.__typename !== 'PullRequest') {
    return { action: 'leave', reason: `closer is a ${closer.__typename}, not a pull request` };
  }
  if ((labels || []).includes(ESCAPE_LABEL)) {
    return { action: 'leave', reason: `closing PR carries ${ESCAPE_LABEL}` };
  }
  return { action: 'reopen', pr: closer.number };
}

// Hidden marker keyed on the ClosedEvent, so a rerun can tell this close was already
// commented on and does not post a second comment.
function markerFor(eventId) {
  return `<!-- work-order-close-guard:v1 event=${eventId} -->`;
}

function buildComment(pr, eventId) {
  return (
    `${markerFor(eventId)}\n` +
    `Reopened: #${pr} merged and was linked to this work order. Work orders close when ` +
    `the Set Pipeline marks the set done. To close a work order from a PR, label the PR ` +
    `\`${ESCAPE_LABEL}\`.`
  );
}

const CLOSER_QUERY = `query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      timelineItems(itemTypes: CLOSED_EVENT, last: 1) {
        nodes {
          ... on ClosedEvent {
            id
            closer {
              __typename
              ... on PullRequest { number labels(first: ${LABEL_PAGE}) { totalCount nodes { name } } }
            }
          }
        }
      }
    }
  }
}`;

async function run({ github, context, core }) {
  const { owner, repo } = context.repo;
  const number = context.payload.issue.number;
  // The payload is a snapshot: re-read the issue so the type and state are current.
  const issue = (await github.rest.issues.get({ owner, repo, issue_number: number })).data;
  if (issue.pull_request || issue.type?.name !== WORK_ORDER_TYPE) {
    core.notice(`#${number} is not a work order; nothing to guard.`);
    return;
  }
  if (issue.state !== 'closed') {
    core.notice(`#${number} is already open; nothing to guard.`);
    return;
  }
  const res = await github.graphql(CLOSER_QUERY, { owner, repo, number });
  const event = res.repository.issue.timelineItems.nodes[0];
  const closer = event ? event.closer : null;
  if (closer && closer.labels && closer.labels.totalCount > closer.labels.nodes.length) {
    throw new Error(
      `PR #${closer.number} has ${closer.labels.totalCount} labels but only ` +
        `${closer.labels.nodes.length} were read; refusing to decide on a partial list.`,
    );
  }
  const labels = closer && closer.labels ? closer.labels.nodes.map((l) => l.name) : [];
  const decision = decide({
    issueTypeName: issue.type?.name,
    isPullRequest: Boolean(issue.pull_request),
    closer,
    labels,
  });
  if (decision.action !== 'reopen') {
    core.info(`#${number} left closed: ${decision.reason}.`);
    return;
  }
  // Comment first, then reopen. The issue stays closed until both writes have landed,
  // so a failure at either step leaves the run retryable: a rerun finds the issue still
  // closed, sees this close's marker if the comment already landed, and only reopens.
  const marker = markerFor(event.id);
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner,
    repo,
    issue_number: number,
    per_page: 100,
  });
  const alreadyCommented = comments.some(
    (c) => c.user && c.user.login === COMMENT_AUTHOR && (c.body || '').startsWith(marker),
  );
  if (!alreadyCommented) {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: number,
      body: buildComment(decision.pr, event.id),
    });
  }
  await github.rest.issues.update({ owner, repo, issue_number: number, state: 'open' });
  core.info(`#${number} reopened: closed by PR #${decision.pr}.`);
}

module.exports = { WORK_ORDER_TYPE, ESCAPE_LABEL, decide, markerFor, buildComment, run };
