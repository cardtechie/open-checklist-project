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

test('the comment names the PR and the escape label', () => {
  const c = g.buildComment(101);
  assert.match(c, /#101/);
  assert.match(c, /completes-work-order/);
});
