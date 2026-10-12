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
//   gets a stop comment naming both.
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

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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
// stored. Returns { action: 'write' | 'noop' | 'stop', setId, uuid, uuidSource,
// changed, reason }.
function planIdentity({ title, body, pinned, mint = () => crypto.randomUUID() }) {
  const { uuid: bodyUuid } = parseBody(body);
  const pinnedSetId = pinned && pinned.setId ? String(pinned.setId) : null;
  const pinnedUuid = pinned && pinned.uuid ? String(pinned.uuid) : null;

  if (pinnedUuid && bodyUuid && pinnedUuid.trim().toLowerCase() !== bodyUuid.toLowerCase()) {
    return {
      action: 'stop',
      reason: `the pinned \`Reserved set UUID\` (\`${pinnedUuid}\`) differs from the Set UUID recorded in the body (\`${bodyUuid}\`)`,
    };
  }

  const setId = pinnedSetId || deriveSetId(title, body);
  if (!setId) {
    return { action: 'stop', reason: 'no `set_id` could be derived: the body has no Set name and the title does not slug to a valid `set_id`' };
  }

  let uuid = pinnedUuid;
  let uuidSource = 'pinned';
  if (!uuid) {
    if (bodyUuid) {
      uuid = bodyUuid;
      uuidSource = 'body';
    } else {
      uuid = mint();
      uuidSource = 'minted';
    }
  }

  const changed = [];
  if (!pinnedSetId) changed.push('set_id');
  if (!pinnedUuid) changed.push('uuid');
  return { action: changed.length ? 'write' : 'noop', setId, uuid, uuidSource, changed };
}

// Create the comment carrying `marker`, or update this workflow's existing one.
async function upsertComment({ github, owner, repo, issue_number, marker, body }) {
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner, repo, issue_number, per_page: 100,
  });
  const mine = comments.find(
    (c) => (c.body || '').startsWith(marker) && c.user && c.user.type === 'Bot',
  );
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
async function reserveIdentity({ github, context, core, issue }) {
  const { owner, repo } = context.repo;
  const issue_number = issue.number;

  if (!isWorkOrder(issue)) {
    core.notice(`#${issue_number} is not a work order (no \`${WORK_ORDER_LABEL}\` label or \`${WORK_ORDER_TYPE}\` type); nothing to reserve.`);
    return { action: 'skip' };
  }

  // Current pinned values (PUT replaces the whole set, so we merge).
  const cur = await github.request(
    'GET /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values',
    { owner, repo, issue_number },
  );
  const byId = Object.fromEntries((cur.data || []).map((f) => [f.issue_field_id, f.value]));

  const plan = planIdentity({
    title: issue.title,
    body: issue.body,
    pinned: { setId: byId[F_SETID], uuid: byId[F_UUID] },
  });

  if (plan.action === 'stop') {
    await upsertComment({
      github, owner, repo, issue_number, marker: RESERVE_STOP_MARKER,
      body: `⏸ **Identity not reserved** — ${plan.reason}. Nothing was written. Resolve it on the issue and re-run the workflow.`,
    });
    core.warning(`#${issue_number}: ${plan.reason}`);
    return plan;
  }
  if (plan.action === 'noop') {
    core.info(`#${issue_number}: set_id and Reserved set UUID already pinned; nothing to do.`);
    return plan;
  }

  const values = [
    { field_id: F_SETID, value: plan.setId },
    { field_id: F_UUID, value: plan.uuid },
  ];
  if (byId[F_REL]) values.push({ field_id: F_REL, value: byId[F_REL] });

  await github.request(
    'PUT /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values',
    { owner, repo, issue_number, issue_field_values: values },
  );

  const parts = [];
  if (plan.changed.includes('set_id')) parts.push('`set_id`: `' + plan.setId + '`');
  if (plan.changed.includes('uuid')) {
    const how = plan.uuidSource === 'body' ? ' (copied from the Set UUID in the body)' : ' (newly minted)';
    parts.push('`Reserved set UUID`: `' + plan.uuid + '`' + how);
  }
  await upsertComment({
    github, owner, repo, issue_number, marker: RESERVE_MARKER,
    body: '🔖 Reserved identity — ' + parts.join(' · ') +
      '. Committed unchanged into `set.yaml` when the filling PR lands.',
  });
  return plan;
}

module.exports = {
  F_SETID,
  F_UUID,
  F_REL,
  RESERVE_MARKER,
  RESERVE_STOP_MARKER,
  parseBody,
  deriveSetId,
  isWorkOrder,
  planIdentity,
  reserveIdentity,
};
