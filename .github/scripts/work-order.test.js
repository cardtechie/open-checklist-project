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

const NO_MINT = () => { throw new Error('must not mint'); };

test('planIdentity mints only when the API lookup says the set is absent', () => {
  const plan = wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, apiLookup: 'absent', mint: () => 'minted' });
  assert.equal(plan.uuid, 'minted');
  assert.equal(plan.uuidSource, 'minted');
});

test('planIdentity defers the UUID on an issue event (no API lookup yet)', () => {
  const plan = wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, mint: NO_MINT });
  assert.equal(plan.action, 'write');
  assert.equal(plan.uuid, null);
  assert.equal(plan.uuidSource, 'deferred');
  assert.deepEqual(plan.changed, ['set_id']);

  const pinnedSlug = wo.planIdentity({ title: '', body: FORM_BODY, pinned: { setId: 'kept' }, mint: NO_MINT });
  assert.equal(pinnedSlug.action, 'noop');

  const fromBody = wo.planIdentity({ title: TABLE_TITLE, body: TABLE_BODY, pinned: {}, mint: NO_MINT });
  assert.equal(fromBody.uuid, UUID);
  assert.deepEqual(fromBody.changed, ['set_id', 'uuid']);
});

test('planIdentity reuses the existing API set UUID for Prizm Draft Picks (#77) and mints nothing', () => {
  const plan = wo.planIdentity({
    title: TABLE_TITLE, body: TABLE_BODY, pinned: {}, apiLookup: 'found', apiUuid: UUID, mint: NO_MINT,
  });
  assert.equal(plan.action, 'write');
  assert.equal(plan.uuid, 'a1e7c40a-d72f-47ca-860d-6d4f603b876f');
  assert.equal(plan.uuidSource, 'api');
  assert.deepEqual(plan.changed, ['set_id', 'uuid']);
});

test('planIdentity reuses the API set UUID even when the body records none', () => {
  const plan = wo.planIdentity({
    title: '', body: FORM_BODY, pinned: {}, apiLookup: 'found', apiUuid: UUID, mint: NO_MINT,
  });
  assert.equal(plan.uuid, UUID);
  assert.equal(plan.uuidSource, 'api');
});

test('planIdentity stops when the API set UUID disagrees with a pinned or body UUID', () => {
  const other = '00000000-0000-4000-8000-000000000000';
  const vsBody = wo.planIdentity({ title: TABLE_TITLE, body: TABLE_BODY, pinned: {}, apiLookup: 'found', apiUuid: other, mint: NO_MINT });
  assert.equal(vsBody.action, 'stop');
  assert.match(vsBody.reason, /Trading Card API/);
  const vsPinned = wo.planIdentity({ title: '', body: FORM_BODY, pinned: { uuid: other }, apiLookup: 'found', apiUuid: UUID, mint: NO_MINT });
  assert.equal(vsPinned.action, 'stop');
});

test('planIdentity stops when the lookup found a set but gave no valid UUID, or the result is unknown', () => {
  assert.equal(wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, apiLookup: 'found', mint: NO_MINT }).action, 'stop');
  assert.equal(wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, apiLookup: 'found', apiUuid: 'nope', mint: NO_MINT }).action, 'stop');
  assert.equal(wo.planIdentity({ title: '', body: FORM_BODY, pinned: {}, apiLookup: 'maybe', mint: NO_MINT }).action, 'stop');
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
const BOT = { login: 'github-actions[bot]', type: 'Bot' };
const context = { repo: { owner: 'cardtechie', repo: 'open-checklist-project' } };
const core = { notice() {}, info() {}, warning() {} };
const issue77 = { number: 77, title: TABLE_TITLE, body: TABLE_BODY, labels: [], type: { name: 'Work Order' } };

test('reserveIdentity writes both fields and comments once', async () => {
  const github = stubGithub();
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  const put = github.calls.find(([r]) => r.startsWith('POST'));
  assert.deepEqual(put[1].issue_field_values, [
    { field_id: wo.F_SETID, value: '2025-panini-prizm-draft-picks' },
    { field_id: wo.F_UUID, value: UUID },
  ]);
  const created = github.calls.filter(([r]) => r === 'createComment');
  assert.equal(created.length, 1);
  assert.ok(created[0][1].body.startsWith(wo.RESERVE_MARKER));
});

test('reserveIdentity writes only the identity fields, never the other field values (#87)', async () => {
  const github = stubGithub({
    fieldValues: [
      { issue_field_id: 19561085, data_type: 'date', issue_field_name: 'Target date', value: '2026-10-01' },
      { issue_field_id: wo.F_REL, data_type: 'date', issue_field_name: 'Release Date', value: '2026-09-28' },
      { issue_field_id: 19561086, data_type: 'single_select', issue_field_name: 'Effort', value: 'Medium' },
    ],
  });
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(plan.action, 'write');
  const writes = github.calls.filter(([r]) => r.startsWith('POST') || r.startsWith('PUT'));
  assert.equal(writes.length, 1);
  assert.equal(writes[0][0], 'POST /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values');
  assert.deepEqual(writes[0][1].issue_field_values, [
    { field_id: wo.F_SETID, value: '2025-panini-prizm-draft-picks' },
    { field_id: wo.F_UUID, value: UUID },
  ]);
});

test('reserveIdentity writes only the missing field when one is already pinned', async () => {
  const github = stubGithub({
    fieldValues: [{ issue_field_id: wo.F_SETID, data_type: 'text', value: 'kept-slug' }],
  });
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  const post = github.calls.find(([r]) => r.startsWith('POST'));
  assert.deepEqual(post[1].issue_field_values, [{ field_id: wo.F_UUID, value: UUID }]);
});

test('identityValues is empty when nothing changed, so no empty array is ever sent', () => {
  assert.deepEqual(wo.identityValues({ changed: [] }), []);
});

test('reserveIdentity on Discover dispatch for #77 pins the existing API UUID', async () => {
  const github = stubGithub();
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77, apiLookup: 'found', apiUuid: UUID });
  assert.equal(plan.uuidSource, 'api');
  const put = github.calls.find(([r]) => r.startsWith('POST'));
  assert.deepEqual(put[1].issue_field_values, [
    { field_id: wo.F_SETID, value: '2025-panini-prizm-draft-picks' },
    { field_id: wo.F_UUID, value: 'a1e7c40a-d72f-47ca-860d-6d4f603b876f' },
  ]);
});

test('reserveIdentity ignores another bot account\'s reserve marker and posts its own', async () => {
  const github = stubGithub({
    comments: [{ id: 9, body: `${wo.RESERVE_MARKER}\nspoofed`, user: { login: 'evil-app[bot]', type: 'Bot' } }],
  });
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(github.calls.filter(([r]) => r === 'updateComment').length, 0);
  assert.equal(github.calls.filter(([r]) => r === 'createComment').length, 1);
});

test('stopInEffect ignores markers from any account but github-actions[bot] with type Bot', () => {
  const otherBot = { ...STOP_COMMENT, user: { login: 'evil-app[bot]', type: 'Bot' } };
  assert.equal(wo.stopInEffect([otherBot]), false);
  const spoofedType = { ...STOP_COMMENT, user: { login: 'github-actions[bot]', type: 'User' } };
  assert.equal(wo.stopInEffect([spoofedType]), false);
  // Another bot's later reserve comment must not supersede the real stop.
  const otherOk = { id: 5, body: `${wo.RESERVE_MARKER}\nok`, user: { login: 'evil-app[bot]', type: 'Bot' }, created_at: '2026-10-09T00:00:00Z' };
  assert.equal(wo.stopInEffect([STOP_COMMENT, otherOk]), true);
});

test('reserveIdentity updates its own earlier comment instead of adding one', async () => {
  const github = stubGithub({
    comments: [{ id: 9, body: `${wo.RESERVE_MARKER}\nold`, user: BOT }],
  });
  await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(github.calls.filter(([r]) => r === 'createComment').length, 0);
  assert.equal(github.calls.filter(([r]) => r === 'updateComment').length, 1);
});

test('reserveIdentity writes nothing on a UUID conflict', async () => {
  const github = stubGithub({
    fieldValues: [{ issue_field_id: wo.F_UUID, data_type: 'text', value: '00000000-0000-4000-8000-000000000000' }],
  });
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77 });
  assert.equal(plan.action, 'stop');
  assert.equal(github.calls.filter(([r]) => r.startsWith('POST')).length, 0);
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

test('API_UUID_RE accepts only an exact lowercase hyphenated UUID', () => {
  assert.ok(wo.API_UUID_RE.test(UUID));
  for (const bad of [
    UUID.toUpperCase(),
    `${UUID}\n`,
    ` ${UUID}`,
    `${UUID}; rm -rf /`,
    `$(id)${UUID}`,
    UUID.replace(/-/g, ''),
    `{${UUID}}`,
    '',
  ]) {
    assert.equal(wo.API_UUID_RE.test(bad), false, JSON.stringify(bad));
  }
});

const STOP_COMMENT = { id: 4, body: `${wo.RESERVE_STOP_MARKER}\nconflict`, user: BOT, created_at: '2026-10-05T00:00:00Z' };
const PINNED = [
  { issue_field_id: wo.F_SETID, data_type: 'text', value: '2025-panini-prizm-draft-picks' },
  { issue_field_id: wo.F_UUID, data_type: 'text', value: UUID },
];
const now = () => '2026-10-12T00:00:00.000Z';

test('stopInEffect: a reserve stop counts until a reserve comment is written after it', () => {
  assert.equal(wo.stopInEffect([]), false);
  assert.equal(wo.stopInEffect([STOP_COMMENT]), true);
  const older = { id: 3, body: `${wo.RESERVE_MARKER}\nok`, user: BOT, created_at: '2026-10-01T00:00:00Z' };
  assert.equal(wo.stopInEffect([older, STOP_COMMENT]), true);
  const newer = { ...older, updated_at: '2026-10-06T00:00:00Z' };
  assert.equal(wo.stopInEffect([newer, STOP_COMMENT]), false);
  const human = { ...STOP_COMMENT, user: { type: 'User' } };
  assert.equal(wo.stopInEffect([human]), false);
});

test('reserveIdentity noop after a corrected conflict rewrites the reserve comment to supersede the stop', async () => {
  const github = stubGithub({ fieldValues: PINNED, comments: [STOP_COMMENT] });
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77, now });
  assert.equal(plan.action, 'noop');
  assert.equal(github.calls.filter(([r]) => r.startsWith('POST')).length, 0);
  const created = github.calls.filter(([r]) => r === 'createComment');
  assert.equal(created.length, 1);
  assert.ok(created[0][1].body.startsWith(wo.RESERVE_MARKER));
  assert.match(created[0][1].body, /Supersedes the earlier `ocp-reserve-stop:v1` comment/);
  assert.match(created[0][1].body, /2026-10-12T00:00:00\.000Z/);
});

test('reserveIdentity noop with no stop in effect writes no comment', async () => {
  const github = stubGithub({ fieldValues: PINNED });
  const plan = await wo.reserveIdentity({ github, context, core, issue: issue77, now });
  assert.equal(plan.action, 'noop');
  assert.equal(github.calls.filter(([r]) => r === 'createComment' || r === 'updateComment').length, 0);
});

test('reserveIdentity write after a stop notes that it supersedes the stop', async () => {
  const github = stubGithub({ comments: [STOP_COMMENT] });
  await wo.reserveIdentity({ github, context, core, issue: issue77, now });
  const created = github.calls.filter(([r]) => r === 'createComment');
  assert.equal(created.length, 1);
  assert.ok(created[0][1].body.startsWith(wo.RESERVE_MARKER));
  assert.match(created[0][1].body, /Supersedes the earlier/);
});
