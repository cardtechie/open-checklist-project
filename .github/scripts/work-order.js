// Shared work-order identity logic (#52, #55, #56, #78).
//
// Used by .github/workflows/reserve-work-order.yml through actions/github-script.
// Reserves a work order's identity into its pinned issue fields: `set_id` (a slug of
// the set name) and `Reserved set UUID`. Discover (#78) reuses this rather than a
// second implementation.
//
// Rules:
// - A value already pinned is never overwritten.
// - A UUID recorded in the issue body (`| Set UUID | ... |`) is copied unchanged
//   instead of minting a fresh one. When the set already exists in the Trading Card
//   API, that UUID is the set's identity, and a fresh one would make the downstream
//   upsert create a duplicate set (tradingcardapi-tools#1051).
// - If a pinned UUID and a body UUID disagree, nothing is written and the work order
//   gets a stop comment (`ocp-reserve-stop:v1`) naming both, with a machine-readable
//   `reason: <code>` line. tools/check_work_order.py treats that stop as making the work
//   order not Ready.
// - Only a lookup run supersedes a stop: a Discover dispatch that carries a fresh Trading
//   Card API lookup (`absent`, or `found` with a valid lowercase `apiUuid`). It rewrites
//   the reserve comment after the stop, tagged `run: api-lookup`. An issue event
//   (opened/labeled/typed) does no API lookup, so it can never prove an API conflict is
//   resolved: while a stop is in effect it writes nothing at all, and the reserve comment
//   it writes otherwise is tagged `run: issue-event`, which the checker never lets clear a
//   stop.
// - A UUID is reserved only after Discover has looked the set up in the Trading Card
//   API, and the dispatch says what it found (`apiLookup`):
//   - `found`: the set exists, and its UUID (`apiUuid`) is the reserved UUID. Nothing
//     is minted. A pinned or body UUID that disagrees with it is a stop.
//   - `absent`: the set is new, so a UUID is minted unless one is already pinned or
//     recorded in the body.
//   An automatic issue event (opened/labeled/typed) fires before that lookup, so it
//   carries no `apiLookup`: it reserves `set_id` (and a body-recorded UUID) only and
//   never mints. Minting there would pin a fresh UUID for a set the API may already
//   hold, and the no-overwrite rule would then make the conflict unrecoverable.
// - Only the identity fields being set are written, through the additive
//   `POST .../issue-field-values` endpoint, which sets the fields it is given and leaves
//   every other field value on the issue alone. The replacing `PUT` is never used: it
//   would write back every value from the earlier GET snapshot and so overwrite a field
//   a person changed in between. The API offers no conditional write, so a concurrent
//   write to `set_id` or `Reserved set UUID` itself between the GET and the POST is not
//   detected; the workflow's per-issue concurrency group keeps its own runs serial.
//
// The issue body is untrusted text. It is only parsed here, never executed or passed
// to a shell.

const crypto = require('crypto');

// Org issue field IDs (from `GET /orgs/<org>/issue-fields`).
// If the fields are ever recreated, update these three ids (and FIELD_* in
// tools/check_work_order.py).
const F_SETID = 44649933; // set_id (text)
const F_UUID = 44650144; // Reserved set UUID (text)
const F_REL = 44650123; // Release Date (date)

const WORK_ORDER_LABEL = 'work-order';
const WORK_ORDER_TYPE = 'Work Order';
const RESERVE_MARKER = '<!-- ocp-reserve:v1 -->';
const RESERVE_STOP_MARKER = '<!-- ocp-reserve-stop:v1 -->';
// The `run:` tag on a reserve comment. Only RUN_LOOKUP clears a stop (here and in
// tools/check_work_order.py).
const RUN_LOOKUP = 'api-lookup';
const RUN_ISSUE_EVENT = 'issue-event';
const RUN_TAG_RE = /^run:[ \t]*(\S+)/m;

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// The exact form a Trading Card API set UUID must take before Discover's dispatch input
// is used: lowercase and hyphenated, nothing else (#78).
const API_UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

// Strip markdown decoration from a table cell or form answer.
function clean(value) {
  return String(value || '')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .trim();
}

// Value of a `| Label | value |` table row, matched case-insensitively on the label.
function tableValue(body, labels) {
  for (const line of body.split('\n')) {
    const cells = line.split('|').map((c) => c.trim());
    // A row `| a | b |` splits into ['', 'a', 'b', ''].
    if (cells.length < 4 || cells[0] !== '') continue;
    const label = clean(cells[1]).toLowerCase();
    if (labels.includes(label)) {
      const v = clean(cells[2]);
      if (v) return v;
    }
  }
  return null;
}

// Value under a `### Label` heading, as GitHub renders an issue-form answer.
function formValue(body, label) {
  const lines = body.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().toLowerCase() !== `### ${label.toLowerCase()}`) continue;
    for (let j = i + 1; j < lines.length; j++) {
      const line = lines[j].trim();
      if (line.startsWith('### ')) break;
      if (!line) continue;
      const v = clean(line);
      return v && v !== '_No response_' ? v : null;
    }
  }
  return null;
}

// Read the set name and any recorded set UUID from a work-order body.
// Returns { setName, uuid }, each null when absent. A UUID that is not a valid
// hyphenated 8-4-4-4-12 UUID is ignored.
function parseBody(body) {
  const text = String(body || '').replace(/\r\n/g, '\n');
  const setName = formValue(text, 'Set name') || tableValue(text, ['set name']);
  const rawUuid = tableValue(text, ['set uuid', 'reserved set uuid']);
  const uuid = rawUuid && UUID_RE.test(rawUuid) ? rawUuid : null;
  return { setName: setName || null, uuid };
}

function slugify(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// set_id: a slug of the body's Set name when present, else of the title with the
// `[Work Order]` prefix stripped. Returns null when no valid slug results.
function deriveSetId(title, body) {
  const { setName } = parseBody(body);
  const name = setName || String(title || '').replace(/^\[Work Order\]\s*/i, '').trim();
  const slug = slugify(name);
  return SLUG_RE.test(slug) ? slug : null;
}

// True when the issue is a work order: the `work-order` label OR the `Work Order`
// issue type (a work order filed outside the template may carry only the type).
function isWorkOrder(issue) {
  if (!issue) return false;
  const labels = (issue.labels || []).map((l) => (typeof l === 'string' ? l : l && l.name));
  const type = issue.type && typeof issue.type === 'object' ? issue.type.name : issue.type;
  return labels.includes(WORK_ORDER_LABEL) || type === WORK_ORDER_TYPE;
}

// Decide what to write, without any I/O. `pinned` is { setId, uuid } as currently
// stored. `apiLookup` is 'found', 'absent', or null (an issue event: no lookup yet);
// `apiUuid` is the matched set's UUID when `apiLookup` is 'found'. Returns
// { action: 'write' | 'noop' | 'stop', setId, uuid, uuidSource, changed, code, reason }.
// A stop's `code` is a short machine-readable reason (e.g. `api-uuid-mismatch`).
// With no lookup and no pinned or body UUID, `uuid` is null and `uuidSource` is
// 'deferred': the UUID is left for Discover to reserve.
function planIdentity({ title, body, pinned, apiLookup = null, apiUuid = null, mint = () => crypto.randomUUID() }) {
  const { uuid: bodyUuid } = parseBody(body);
  const pinnedSetId = pinned && pinned.setId ? String(pinned.setId) : null;
  const pinnedUuid = pinned && pinned.uuid ? String(pinned.uuid).trim() : null;
  const same = (a, b) => a.toLowerCase() === b.toLowerCase();

  if (apiLookup !== null && apiLookup !== 'found' && apiLookup !== 'absent') {
    return { action: 'stop', code: 'api-lookup-invalid', reason: `the API lookup result must be \`found\` or \`absent\`, got \`${apiLookup}\`` };
  }
  let api = null;
  if (apiLookup === 'found') {
    api = apiUuid ? String(apiUuid).trim() : '';
    if (!API_UUID_RE.test(api)) {
      return { action: 'stop', code: 'api-uuid-invalid', reason: `the API lookup found the set but gave no valid set UUID (\`${api}\`)` };
    }
    if (pinnedUuid && !same(pinnedUuid, api)) {
      return { action: 'stop', code: 'api-uuid-mismatch', reason: `the pinned \`Reserved set UUID\` (\`${pinnedUuid}\`) differs from the Trading Card API set's UUID (\`${api}\`)` };
    }
    if (bodyUuid && !same(bodyUuid, api)) {
      return { action: 'stop', code: 'api-uuid-mismatch', reason: `the Set UUID recorded in the body (\`${bodyUuid}\`) differs from the Trading Card API set's UUID (\`${api}\`)` };
    }
  }

  if (pinnedUuid && bodyUuid && !same(pinnedUuid, bodyUuid)) {
    return {
      action: 'stop',
      code: 'pinned-body-mismatch',
      reason: `the pinned \`Reserved set UUID\` (\`${pinnedUuid}\`) differs from the Set UUID recorded in the body (\`${bodyUuid}\`)`,
    };
  }

  const setId = pinnedSetId || deriveSetId(title, body);
  if (!setId) {
    return { action: 'stop', code: 'no-set-id', reason: 'no `set_id` could be derived: the body has no Set name and the title does not slug to a valid `set_id`' };
  }

  let uuid = pinnedUuid;
  let uuidSource = 'pinned';
  if (!uuid) {
    if (api) {
      uuid = api;
      uuidSource = 'api';
    } else if (bodyUuid) {
      uuid = bodyUuid;
      uuidSource = 'body';
    } else if (apiLookup === 'absent') {
      uuid = mint();
      uuidSource = 'minted';
    } else {
      uuid = null;
      uuidSource = 'deferred';
    }
  }

  const changed = [];
  if (!pinnedSetId) changed.push('set_id');
  if (!pinnedUuid && uuid) changed.push('uuid');
  return { action: changed.length ? 'write' : 'noop', setId, uuid, uuidSource, changed };
}

// The POST body: only the identity values that were missing. Never empty for a
// 'write' plan; an empty array would clear every field value on the issue, so callers
// must not send one.
function identityValues(plan) {
  const values = [];
  if (plan.changed.includes('set_id')) values.push({ field_id: F_SETID, value: plan.setId });
  if (plan.changed.includes('uuid')) values.push({ field_id: F_UUID, value: plan.uuid });
  return values;
}

function listComments({ github, owner, repo, issue_number }) {
  return github.paginate(github.rest.issues.listComments, {
    owner, repo, issue_number, per_page: 100,
  });
}

// The account this workflow comments as. Only its comments are this workflow's own:
// tools/check_work_order.py trusts a reserve comment by this exact login (with type
// Bot), so a marker posted by any other bot account is ignored here too.
const ACTIONS_BOT_LOGIN = 'github-actions[bot]';

function isActionsBot(user) {
  return Boolean(user) && user.login === ACTIONS_BOT_LOGIN && user.type === 'Bot';
}

// This workflow's own comment carrying `marker`, or undefined.
function botComment(comments, marker) {
  return (comments || []).find(
    (c) => (c.body || '').startsWith(marker) && isActionsBot(c.user),
  );
}

function lastWritten(c) {
  return (c && (c.updated_at || c.created_at)) || '';
}

// The `run:` tag of a reserve comment, or null (an untagged comment).
function runTag(comment) {
  const m = RUN_TAG_RE.exec((comment && comment.body) || '');
  return m ? m[1] : null;
}

// True when a dispatch carried a fresh, validated API lookup: `absent`, or `found` with
// an exact lowercase hyphenated `apiUuid`. Only such a run may supersede a stop.
function isLookupRun(apiLookup, apiUuid) {
  if (apiLookup === 'absent') return true;
  return apiLookup === 'found' && API_UUID_RE.test(String(apiUuid || ''));
}

// True when this workflow's reserve stop is in effect: it exists and no reserve comment
// tagged `run: api-lookup` was written after it. A reserve comment from an issue-event
// run (or an untagged one) never clears a stop. tools/check_work_order.py applies the
// same rule.
function stopInEffect(comments) {
  const stop = botComment(comments, RESERVE_STOP_MARKER);
  if (!stop) return false;
  const ok = botComment(comments, RESERVE_MARKER);
  return !ok || runTag(ok) !== RUN_LOOKUP || lastWritten(stop) >= lastWritten(ok);
}

// Create the comment carrying `marker`, or update this workflow's existing one.
async function upsertComment({ github, owner, repo, issue_number, marker, body }) {
  const comments = await listComments({ github, owner, repo, issue_number });
  const mine = botComment(comments, marker);
  const full = `${marker}\n${body}`;
  if (mine) {
    if (mine.body !== full) {
      await github.rest.issues.updateComment({ owner, repo, comment_id: mine.id, body: full });
    }
  } else {
    await github.rest.issues.createComment({ owner, repo, issue_number, body: full });
  }
}

// Reserve the identity of one work-order issue. `issue` is the REST issue object.
// `apiLookup`/`apiUuid` come only from Discover's dispatch, after its Trading Card API
// lookup; an issue event passes neither. See the rules above.
// `now` stamps the note that supersedes an earlier stop, so that comment is always
// rewritten (and so written after the stop) rather than skipped as unchanged.
async function reserveIdentity({
  github, context, core, issue, apiLookup = null, apiUuid = null,
  now = () => new Date().toISOString(),
}) {
  const { owner, repo } = context.repo;
  const issue_number = issue.number;

  if (!isWorkOrder(issue)) {
    core.notice(`#${issue_number} is not a work order (no \`${WORK_ORDER_LABEL}\` label or \`${WORK_ORDER_TYPE}\` type); nothing to reserve.`);
    return { action: 'skip' };
  }

  // An issue-event run never supersedes a stop: it did no API lookup, so it cannot show
  // that the conflict the stop records is resolved. While a stop is in effect it writes
  // nothing (no field, no comment) and leaves the stop for Discover's next dispatch.
  const lookupRun = isLookupRun(apiLookup, apiUuid);
  const stopped = stopInEffect(await listComments({ github, owner, repo, issue_number }));
  if (stopped && !lookupRun) {
    core.notice(`#${issue_number}: a reservation stop is in effect; only a Discover dispatch with a fresh Trading Card API lookup can supersede it. Nothing written.`);
    return { action: 'held' };
  }

  // Current pinned values. They decide what is missing; nothing else is written back.
  const cur = await github.request(
    'GET /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values',
    { owner, repo, issue_number },
  );
  const existing = cur.data || [];
  const byId = Object.fromEntries(existing.map((f) => [f.issue_field_id, f.value]));

  const plan = planIdentity({
    title: issue.title,
    body: issue.body,
    pinned: { setId: byId[F_SETID], uuid: byId[F_UUID] },
    apiLookup,
    apiUuid,
  });

  if (plan.action === 'stop') {
    await upsertComment({
      github, owner, repo, issue_number, marker: RESERVE_STOP_MARKER,
      body: `reason: ${plan.code}\n⏸ **Identity not reserved** — ${plan.reason}. Nothing was written. Resolve it on the issue and re-run the workflow.`,
    });
    core.warning(`#${issue_number}: ${plan.reason}`);
    return plan;
  }
  // A successful lookup run (write or noop) supersedes this workflow's earlier stop, by
  // writing its reserve comment, tagged `run: api-lookup`, after the stop. Without that, a
  // corrected issue whose identity was already pinned would stay not Ready on a stop that
  // no longer applies. (Only a lookup run reaches here with a stop in effect.)
  const supersedes = stopped;
  const runLine = `run: ${lookupRun ? RUN_LOOKUP : RUN_ISSUE_EVENT}\n`;
  const supersedeNote = supersedes
    ? ` Supersedes the earlier \`ocp-reserve-stop:v1\` comment: the identity was checked again at ${now()} and no conflict remains.`
    : '';

  if (plan.action === 'noop') {
    core.info(plan.uuidSource === 'deferred'
      ? `#${issue_number}: set_id already pinned; Reserved set UUID is left for Discover to reserve after its API lookup.`
      : `#${issue_number}: set_id and Reserved set UUID already pinned; nothing to do.`);
    if (supersedes) {
      const uuidText = plan.uuid
        ? '`Reserved set UUID`: `' + plan.uuid + '`'
        : '`Reserved set UUID`: not yet reserved (Discover reserves it after the Trading Card API lookup)';
      await upsertComment({
        github, owner, repo, issue_number, marker: RESERVE_MARKER,
        body: runLine + '🔖 Identity confirmed — `set_id`: `' + plan.setId + '` · ' + uuidText + '.' + supersedeNote,
      });
    }
    return plan;
  }

  // Write only the missing identity fields. POST is additive: other field values on the
  // issue are left untouched, so a concurrent edit to them cannot be overwritten.
  const values = identityValues(plan);
  if (!values.length) {
    // Unreachable for a 'write' plan; guarded because an empty array clears every field.
    throw new Error(`#${issue_number}: refusing to POST an empty issue_field_values array`);
  }
  await github.request(
    'POST /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values',
    { owner, repo, issue_number, issue_field_values: values },
  );

  const parts = [];
  if (plan.changed.includes('set_id')) parts.push('`set_id`: `' + plan.setId + '`');
  if (plan.changed.includes('uuid')) {
    const how = {
      api: ' (the existing Trading Card API set)',
      body: ' (copied from the Set UUID in the body)',
      minted: ' (newly minted: the set is not in the Trading Card API)',
    }[plan.uuidSource] || '';
    parts.push('`Reserved set UUID`: `' + plan.uuid + '`' + how);
  } else if (plan.uuidSource === 'deferred') {
    parts.push('`Reserved set UUID`: not yet reserved (Discover reserves it after the Trading Card API lookup)');
  }
  await upsertComment({
    github, owner, repo, issue_number, marker: RESERVE_MARKER,
    body: runLine + '🔖 Reserved identity — ' + parts.join(' · ') +
      '. Committed unchanged into `set.yaml` when the filling PR lands.' + supersedeNote,
  });
  return plan;
}

module.exports = {
  F_SETID,
  F_UUID,
  F_REL,
  RESERVE_MARKER,
  RESERVE_STOP_MARKER,
  RUN_LOOKUP,
  RUN_ISSUE_EVENT,
  ACTIONS_BOT_LOGIN,
  API_UUID_RE,
  parseBody,
  stopInEffect,
  isLookupRun,
  runTag,
  deriveSetId,
  isWorkOrder,
  planIdentity,
  identityValues,
  reserveIdentity,
};
