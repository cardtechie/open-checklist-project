// Tests for .github/scripts/work-order-close-guard.js.
// Run: node --test .github/scripts/work-order-close-guard.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('./work-order-close-guard.js');

const base = {
  issueTypeName: 'Work Order',
  isPullRequest: false,
  closer: { __typename: 'PullRequest', number: 101 },
  labels: [],
};

test('a work order closed by a PR is reopened', () => {
  assert.deepEqual(g.decide(base), { action: 'reopen', pr: 101 });
});

test('a closing PR labelled completes-work-order leaves it closed', () => {
  const d = g.decide({ ...base, labels: ['other', 'completes-work-order'] });
  assert.equal(d.action, 'leave');
});

test('a hand close (null closer) is left closed', () => {
  assert.equal(g.decide({ ...base, closer: null }).action, 'leave');
});

test('a non-work-order closed by a PR is untouched', () => {
  assert.equal(g.decide({ ...base, issueTypeName: 'Task' }).action, 'leave');
  assert.equal(g.decide({ ...base, issueTypeName: undefined }).action, 'leave');
});

test('a Commit closer is not a PR and is left closed', () => {
  const d = g.decide({ ...base, closer: { __typename: 'Commit' } });
  assert.equal(d.action, 'leave');
});

test('a pull request item is ignored', () => {
  assert.equal(g.decide({ ...base, isPullRequest: true }).action, 'leave');
});

test('the comment names the PR and the escape label, under the event marker', () => {
  const c = g.buildComment(101, 'CE_1');
  assert.ok(c.startsWith(g.markerFor('CE_1')));
  assert.match(c, /#101/);
  assert.match(c, /completes-work-order/);
});

// Fake github-script context for run(). Records every write in order.
function harness({ labels = [], totalCount, comments = [], failComment = false, failUpdate = false } = {}) {
  const calls = [];
  const github = {
    rest: {
      issues: {
        get: async () => ({ data: { state: 'closed', type: { name: 'Work Order' } } }),
        listComments: 'listComments',
        createComment: async (args) => {
          calls.push(['comment', args]);
          if (failComment) throw new Error('comment failed');
        },
        update: async (args) => {
          calls.push(['update', args]);
          if (failUpdate) throw new Error('update failed');
        },
      },
    },
    paginate: async () => comments,
    graphql: async () => ({
      repository: {
        issue: {
          timelineItems: {
            nodes: [
              {
                id: 'CE_1',
                closer: {
                  __typename: 'PullRequest',
                  number: 101,
                  labels: {
                    totalCount: totalCount === undefined ? labels.length : totalCount,
                    nodes: labels.map((name) => ({ name })),
                  },
                },
              },
            ],
          },
        },
      },
    }),
  };
  const context = { repo: { owner: 'o', repo: 'r' }, payload: { issue: { number: 7 } } };
  const core = { notice() {}, info() {} };
  return { calls, args: { github, context, core } };
}

test('run comments before it reopens', async () => {
  const h = harness();
  await g.run(h.args);
  assert.deepEqual(h.calls.map((c) => c[0]), ['comment', 'update']);
  assert.ok(h.calls[0][1].body.startsWith(g.markerFor('CE_1')));
  assert.equal(h.calls[1][1].state, 'open');
});

test('a failed comment leaves the work order closed, so a rerun can repair it', async () => {
  const h = harness({ failComment: true });
  await assert.rejects(g.run(h.args), /comment failed/);
  assert.deepEqual(h.calls.map((c) => c[0]), ['comment']);
});

test('a rerun after a failed reopen reopens without a second comment', async () => {
  const comments = [{ user: { login: 'github-actions[bot]' }, body: g.buildComment(101, 'CE_1') }];
  const h = harness({ comments });
  await g.run(h.args);
  assert.deepEqual(h.calls.map((c) => c[0]), ['update']);
});

test('a marker posted by anyone other than the workflow does not suppress the comment', async () => {
  const comments = [{ user: { login: 'someone' }, body: g.markerFor('CE_1') }];
  const h = harness({ comments });
  await g.run(h.args);
  assert.deepEqual(h.calls.map((c) => c[0]), ['comment', 'update']);
});

test('a marker for an earlier close does not suppress the comment for this close', async () => {
  const comments = [{ user: { login: 'github-actions[bot]' }, body: g.buildComment(99, 'CE_0') }];
  const h = harness({ comments });
  await g.run(h.args);
  assert.deepEqual(h.calls.map((c) => c[0]), ['comment', 'update']);
});

test('the escape label is honoured when it is the 100th label', async () => {
  const labels = Array.from({ length: 99 }, (_, i) => `l${i}`).concat('completes-work-order');
  const h = harness({ labels });
  await g.run(h.args);
  assert.deepEqual(h.calls, []);
});

test('a label list larger than was read fails instead of deciding', async () => {
  const h = harness({ labels: ['a'], totalCount: 101 });
  await assert.rejects(g.run(h.args), /partial list/);
  assert.deepEqual(h.calls, []);
});
