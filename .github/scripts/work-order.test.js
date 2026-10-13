// Tests for .github/scripts/work-order.js. Run: node --test .github/scripts/work-order.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const wo = require('./work-order.js');

const UUID = 'a1e7c40a-d72f-47ca-860d-6d4f603b876f';

// Shape of #77: filed from Trading Card API verification, outside the template.
const TABLE_BODY = [
  '**Set work-order** — filed from Trading Card API verification, not from discovery.',
  '',
  '| Field | Value |',
  '| --- | --- |',
  '| **Year** | `2025` |',
  '| **Genre** | `Football` |',
  `| Set UUID | \`${UUID}\` |`,
  '| Set name | 2025 Panini Prizm Draft Picks |',
  '| Brand | Prizm Draft Picks |',
].join('\n');
const TABLE_TITLE = '[Work Order] 2025 Panini Prizm Draft Picks (Football)';

// Shape of an issue-form submission.
const FORM_BODY = [
  '### Set name',
  '',
  '2026 Bowman',
  '',
  '### Manufacturer (optional)',
  '',
  '_No response_',
].join('\n');

test('parseBody reads the table shape', () => {
  assert.deepEqual(wo.parseBody(TABLE_BODY), { setName: '2025 Panini Prizm Draft Picks', uuid: UUID });
});

test('parseBody reads the form shape and ignores _No response_', () => {
  assert.deepEqual(wo.parseBody(FORM_BODY), { setName: '2026 Bowman', uuid: null });
  assert.deepEqual(wo.parseBody('### Set name\n\n_No response_\n'), { setName: null, uuid: null });
});

test('parseBody ignores an invalid UUID and accepts the Reserved set UUID label', () => {
  assert.equal(wo.parseBody('| Set UUID | not-a-uuid |').uuid, null);
  assert.equal(wo.parseBody(`| Reserved set UUID | ${UUID} |`).uuid, UUID);
});

test('deriveSetId prefers the body Set name over the title', () => {
  assert.equal(wo.deriveSetId(TABLE_TITLE, TABLE_BODY), '2025-panini-prizm-draft-picks');
  assert.equal(wo.deriveSetId('[Work Order] Something else', FORM_BODY), '2026-bowman');
});

test('deriveSetId falls back to the title, and returns null when nothing slugs', () => {
  assert.equal(wo.deriveSetId('[Work Order] 2026 Topps Chrome', ''), '2026-topps-chrome');
  assert.equal(wo.deriveSetId('[Work Order] ***', ''), null);
});

test('isWorkOrder accepts the label or the type', () => {
  assert.equal(wo.isWorkOrder({ labels: [{ name: 'work-order' }] }), true);
  assert.equal(wo.isWorkOrder({ labels: [], type: { name: 'Work Order' } }), true);
  assert.equal(wo.isWorkOrder({ labels: [{ name: 'automation' }], type: { name: 'Task' } }), false);
  assert.equal(wo.isWorkOrder(null), false);
});

test('planIdentity copies the body UUID instead of minting (#77)', () => {
  const plan = wo.planIdentity({
    title: TABLE_TITLE, body: TABLE_BODY, pinned: {},
    mint: () => { throw new Error('must not mint when the body records a UUID'); },
  });
  assert.equal(plan.action, 'write');
  assert.equal(plan.setId, '2025-panini-prizm-draft-picks');
  assert.equal(plan.uuid, UUID);
  assert.equal(plan.uuidSource, 'body');
  assert.deepEqual(plan.changed, ['set_id', 'uuid']);
});

test('planIdentity mints only when no UUID is pinned or recorded', () => {
  const plan = wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, mint: () => 'minted' });
  assert.equal(plan.uuid, 'minted');
  assert.equal(plan.uuidSource, 'minted');
});

test('planIdentity defers the UUID instead of minting when minting is not allowed', () => {
  const plan = wo.planIdentity({
    title: '', body: FORM_BODY, pinned: {}, allowMint: false,
    mint: () => { throw new Error('must not mint before the API lookup'); },
  });
  assert.equal(plan.action, 'write');
  assert.equal(plan.uuid, null);
  assert.equal(plan.uuidSource, 'deferred');
  assert.deepEqual(plan.changed, ['set_id']);

  const pinnedSlug = wo.planIdentity({ title: '', body: FORM_BODY, pinned: { setId: 'kept' }, allowMint: false });
  assert.equal(pinnedSlug.action, 'noop');

  const fromBody = wo.planIdentity({ title: TABLE_TITLE, body: TABLE_BODY, pinned: {}, allowMint: false });
  assert.equal(fromBody.uuid, UUID);
  assert.deepEqual(fromBody.changed, ['set_id', 'uuid']);
});

test('planIdentity never overwrites pinned values', () => {
  const plan = wo.planIdentity({
    title: TABLE_TITLE, body: TABLE_BODY, pinned: { setId: 'kept-slug', uuid: UUID },
  });
  assert.equal(plan.action, 'noop');
  assert.equal(plan.setId, 'kept-slug');
  assert.equal(plan.uuid, UUID);

  const partial = wo.planIdentity({ title: TABLE_TITLE, body: TABLE_BODY, pinned: { setId: 'kept-slug' } });
  assert.equal(partial.setId, 'kept-slug');
  assert.deepEqual(partial.changed, ['uuid']);
});

test('planIdentity stops on a pinned/body UUID conflict and writes nothing', () => {
  const plan = wo.planIdentity({
    title: TABLE_TITLE, body: TABLE_BODY,
    pinned: { uuid: '00000000-0000-4000-8000-000000000000' },
  });
  assert.equal(plan.action, 'stop');
  assert.match(plan.reason, /differs/);
  assert.equal(plan.setId, undefined);
});

test('planIdentity treats a case-only UUID difference as the same UUID', () => {
  const plan = wo.planIdentity({ title: TABLE_TITLE, body: TABLE_BODY, pinned: { uuid: UUID.toUpperCase() } });
  assert.notEqual(plan.action, 'stop');
});

test('planIdentity stops when no set_id can be derived', () => {
  const plan = wo.planIdentity({ title: '[Work Order] !!!', body: '', pinned: {} });
  assert.equal(plan.action, 'stop');
});

// reserveIdentity against a stub client: the write path and the conflict path.
function stubGithub({ fieldValues = [], comments = [] } = {}) {
  const calls = [];
  const github = {
    calls,
    request: async (route, params) => {
      calls.push([route, params]);
      return route.startsWith('GET') ? { data: fieldValues } : { data: {} };
    },
    paginate: async () => comments,
    rest: {
      issues: {
        listComments: () => {},
        createComment: async (p) => calls.push(['createComment', p]),
        updateComment: async (p) => calls.push(['updateComment', p]),
      },
    },
  };
  return github;
}
const context = { repo: { owner: 'cardtechie', repo: 'open-checklist-project' } };
const core = { notice() {}, info() {}, warning() {} };
const issue77 = { number: 77, title: TABLE_TITLE, body: TABLE_BODY, labels: [], type: { name: 'Work Order' } };

test('reserveIdentity writes both fields and comments once', async () => {
  const github = stubGithub();
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  const put = github.calls.find(([r]) => r.startsWith('PUT'));
  assert.deepEqual(put[1].issue_field_values, [
    { field_id: wo.F_SETID, value: '2025-panini-prizm-draft-picks' },
    { field_id: wo.F_UUID, value: UUID },
  ]);
  const created = github.calls.filter(([r]) => r === 'createComment');
  assert.equal(created.length, 1);
  assert.ok(created[0][1].body.startsWith(wo.RESERVE_MARKER));
});

test('reserveIdentity carries every existing field value over in the PUT', async () => {
  const github = stubGithub({
    fieldValues: [
      { issue_field_id: 19561085, value: '2026-10-01' },
      { issue_field_id: wo.F_REL, value: '2026-09-28' },
    ],
  });
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  const put = github.calls.find(([r]) => r.startsWith('PUT'));
  assert.deepEqual(put[1].issue_field_values, [
    { field_id: 19561085, value: '2026-10-01' },
    { field_id: wo.F_REL, value: '2026-09-28' },
    { field_id: wo.F_SETID, value: '2025-panini-prizm-draft-picks' },
    { field_id: wo.F_UUID, value: UUID },
  ]);
});

test('reserveIdentity mints only when allowed, and never on an issue event', async () => {
  const formIssue = { number: 90, title: '[Work Order] 2026 Bowman', body: FORM_BODY, labels: [{ name: 'work-order' }] };

  const onEvent = stubGithub();
  const plan = await wo.reserveIdentity({ github: onEvent, context, core, issue: formIssue });
  assert.equal(plan.uuidSource, 'deferred');
  const put = onEvent.calls.find(([r]) => r.startsWith('PUT'));
  assert.deepEqual(put[1].issue_field_values, [{ field_id: wo.F_SETID, value: '2026-bowman' }]);

  const onDispatch = stubGithub({ fieldValues: [{ issue_field_id: wo.F_SETID, value: '2026-bowman' }] });
  const minted = await wo.reserveIdentity({ github: onDispatch, context, core, issue: formIssue, allowMint: true });
  assert.equal(minted.uuidSource, 'minted');
  const put2 = onDispatch.calls.find(([r]) => r.startsWith('PUT'));
  assert.equal(put2[1].issue_field_values.length, 2);
  assert.deepEqual(put2[1].issue_field_values[0], { field_id: wo.F_SETID, value: '2026-bowman' });
  assert.equal(put2[1].issue_field_values[1].field_id, wo.F_UUID);
});

test('reserveIdentity updates its own earlier comment instead of adding one', async () => {
  const github = stubGithub({
    comments: [{ id: 9, body: `${wo.RESERVE_MARKER}\nold`, user: { type: 'Bot' } }],
  });
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(github.calls.filter(([r]) => r === 'createComment').length, 0);
  assert.equal(github.calls.filter(([r]) => r === 'updateComment').length, 1);
});

test('reserveIdentity writes nothing on a UUID conflict', async () => {
  const github = stubGithub({
    fieldValues: [{ issue_field_id: wo.F_UUID, value: '00000000-0000-4000-8000-000000000000' }],
  });
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(plan.action, 'stop');
  assert.equal(github.calls.filter(([r]) => r.startsWith('PUT')).length, 0);
  const created = github.calls.filter(([r]) => r === 'createComment');
  assert.ok(created[0][1].body.startsWith(wo.RESERVE_STOP_MARKER));
});

test('reserveIdentity skips an issue that is not a work order', async () => {
  const github = stubGithub();
  const res = await wo.reserveIdentity({
    github, context, core, issue: { number: 5, title: 'x', body: '', labels: [], type: null },
  });
  assert.equal(res.action, 'skip');
  assert.equal(github.calls.length, 0);
});
