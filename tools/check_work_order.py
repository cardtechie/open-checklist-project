#!/usr/bin/env python3
"""Check whether a set work order meets the Stage A producer precondition.

The Stage A producer (docs/PRODUCER.md) may start on a work order only when it is
Ready. This script is the deterministic half of that decision: it reads the work
order (issue, pinned issue fields, comments), checks the four precondition items,
and prints a JSON verdict with the normalized inputs the producer needs.

    python tools/check_work_order.py 77
    python tools/check_work_order.py 77 --repo cardtechie/open-checklist-project
    python tools/check_work_order.py --from-json work-order.json

`--from-json` reads a file shaped {"issue": {...}, "field_values": [...],
"comments": [...]} -- the same three payloads the GitHub API returns -- so the check
can run offline and in tests.

It never writes to GitHub. Exit 0 = ready, 10 = not ready, 2 = usage or read error.
"""
import argparse
import ipaddress
import json
import re
import subprocess
import sys
import uuid as uuidlib
from pathlib import Path
from urllib.parse import urlparse

import yaml

DEFAULT_REPO = "cardtechie/open-checklist-project"
WORK_ORDER_TYPE = "Work Order"
DISCOVER_MARKER = "<!-- ocp-discover:v1 -->"
DISCOVER_STOP_MARKER = "<!-- ocp-discover-stop:v1 -->"
# An operator's ruling on a Discover source-disagreement stop (docs/PRODUCER.md ->
# Source comparison -> Recovery after a disagreement). Discover never writes one.
DISCOVER_RULING_MARKER = "<!-- ocp-discover-ruling:v1 -->"
RULING_REASON = "source-disagreement"
# Written by .github/workflows/reserve-work-order.yml (.github/scripts/work-order.js):
# RESERVE_MARKER on a successful reservation, RESERVE_STOP_MARKER when it stopped on an
# identity conflict and wrote nothing.
RESERVE_MARKER = "<!-- ocp-reserve:v1 -->"
RESERVE_STOP_MARKER = "<!-- ocp-reserve-stop:v1 -->"
STOP_REASON_RE = re.compile(r"^reason:[ \t]*(\S+)", re.MULTILINE)
# A reserve comment's `run:` tag. Only a lookup run (a Discover dispatch carrying a fresh
# Trading Card API lookup) clears a reserve stop; an issue-event run did no lookup, so its
# reserve comment (`run: issue-event`, or an untagged one) never does.
RESERVE_RUN_RE = re.compile(r"^run:[ \t]*(\S+)", re.MULTILINE)
RESERVE_RUN_LOOKUP = "api-lookup"

# Pinned issue fields are resolved by NAME. The numeric ids (the same ones
# .github/workflows/reserve-work-order.yml writes) are a fallback for a payload that
# carries no name.
FIELD_SET_ID = ("set_id", 44649933)
FIELD_UUID = ("Reserved set UUID", 44650144)

# Only a comment from someone with write access to the repo can carry the Discover
# block. Anyone can comment on a public issue, and the block decides which URL the
# producer fetches and which count it trusts.
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}

# The reserve workflow comments as GitHub Actions, whose comments carry no trusted
# author_association, so its own comments are trusted by account. No other account
# can comment as github-actions[bot].
ACTIONS_BOT_LOGIN = "github-actions[bot]"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FENCE_RE = re.compile(r"^```ya?ml[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
UUID_TEXT_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
UUID_IN_YAML_RE = re.compile(
    r"\buuid:\s*['\"]?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
GENRES = {"Sports", "TCG", "Non-Sport"}

EXIT_READY, EXIT_NOT_READY, EXIT_USAGE = 0, 10, 2


class ReadError(Exception):
    pass


# --------------------------------------------------------------------------- reading

def _gh_json(args):
    try:
        out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise ReadError("gh CLI not found") from e
    except subprocess.CalledProcessError as e:
        raise ReadError(f"gh api {' '.join(args)} failed: {e.stderr.strip()}") from e
    return out.stdout


def _decode(text, what):
    """Decode one JSON document from the GitHub API, or raise ReadError."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ReadError(f"{what}: malformed JSON from the GitHub API: {e}") from e


def fetch_work_order(repo, num):
    """Read the three payloads for issue <num> through the gh CLI.

    Every decode and shape check raises ReadError, so a malformed or unexpected
    response exits 2 like any other read failure instead of with a traceback.
    """
    base = f"repos/{repo}/issues/{num}"
    issue = _decode(_gh_json([base]), f"issue #{num}")
    if not isinstance(issue, dict):
        raise ReadError(f"issue #{num}: expected a JSON object")
    fields = _decode(_gh_json([f"{base}/issue-field-values"]) or "[]", f"issue #{num} field values")
    if not isinstance(fields, list):
        raise ReadError(f"issue #{num} field values: expected a JSON array")
    # --paginate with --jq '.[]' emits one JSON object per line across all pages.
    raw = _gh_json(["--paginate", f"{base}/comments", "--jq", ".[]"])
    comments = []
    for n, line in enumerate((l for l in raw.splitlines() if l.strip()), 1):
        c = _decode(line, f"issue #{num} comment {n}")
        if not isinstance(c, dict):
            raise ReadError(f"issue #{num} comment {n}: expected a JSON object")
        comments.append(c)
    return {"issue": issue, "field_values": fields, "comments": comments}


def load_json_payload(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ReadError(f"cannot read {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("issue"), dict):
        raise ReadError(f"{path}: expected an object with an 'issue' object")
    return data


# --------------------------------------------------------------------------- helpers

def field_value(field_values, field):
    """Return a pinned field's value, matched by name, then by numeric id."""
    name, fid = field
    values = [f for f in (field_values or []) if isinstance(f, dict)]
    for f in values:
        if f.get("issue_field_name") == name:
            return f.get("value")
    for f in values:
        if f.get("issue_field_id") == fid:
            return f.get("value")
    return None


def issue_type_name(issue):
    t = issue.get("type")
    if isinstance(t, dict):
        return t.get("name")
    return t if isinstance(t, str) else None


def existing_set_ids(data_dir):
    root = Path(data_dir)
    if not root.is_dir():
        return set()
    return {p.name for genre in root.iterdir() if genre.is_dir()
            for p in genre.iterdir() if p.is_dir()}


def existing_uuids(data_dir):
    """Every `uuid:` value committed anywhere under data/ (lower-cased)."""
    found = set()
    root = Path(data_dir)
    if not root.is_dir():
        return found
    for path in root.rglob("*.y*ml"):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        found.update(m.lower() for m in UUID_IN_YAML_RE.findall(text))
    return found


def is_positive_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def is_http_url(v):
    if not isinstance(v, str):
        return False
    try:
        p = urlparse(v.strip())
    except ValueError:  # e.g. an unterminated bracketed host: http://[::1
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


# Host names that never point at a public source. The producer fetches every accepted
# URL unattended, so a source must not reach loopback, link-local (cloud metadata),
# private or otherwise non-global addresses.
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
NUMERIC_HOST_RE = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+))*$", re.IGNORECASE)


def source_url_problem(v):
    """Return why a source URL may not be fetched, or None when it is acceptable.

    This is the deterministic half of the policy: it judges the URL text only. A
    public host name can still resolve to, or redirect to, a private address, so the
    fetch step (docs/PRODUCER.md step b) checks the resolved address and every
    redirect target too.
    """
    if not is_http_url(v):
        return "is missing or not http/https"
    p = urlparse(v.strip())
    if p.username is not None or p.password is not None:
        return "must not carry credentials"
    try:
        host = (p.hostname or "").rstrip(".").lower()
        p.port  # raises ValueError on a malformed port
    except ValueError:
        return "has a malformed host or port"
    if not host:
        return "has no host"
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES) or "." not in host:
        return f"host '{host}' is not a public host name"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Integer, hex and short dotted forms (http://2130706433/, http://0x7f.1/) are
        # read as IP addresses by many clients, so they are refused outright.
        if NUMERIC_HOST_RE.match(host):
            return f"host '{host}' is a non-standard numeric address"
        return None
    if not ip.is_global:
        return f"host {host} is not a public address"
    return None


def marked_comments(comments, marker):
    """Comments whose first line is `marker`, oldest first (by created_at)."""
    blocks = []
    for i, c in enumerate(comments or []):
        if not isinstance(c, dict):
            continue
        body = (c.get("body") or "").replace("\r\n", "\n")
        if body.lstrip().split("\n", 1)[0].strip() == marker:
            blocks.append((c.get("created_at") or "", i, c, body))
    blocks.sort(key=lambda b: (b[0], b[1]))
    return blocks


def discover_blocks(comments):
    """Comments whose first line is the Discover marker, oldest first."""
    return marked_comments(comments, DISCOVER_MARKER)


def last_written(comment_):
    """When a comment was last written. Discover PATCHes its block and its stop
    comment in place on a re-run, so updated_at (not created_at) orders them."""
    return comment_.get("updated_at") or comment_.get("created_at") or ""


def is_trusted(comment_):
    return comment_.get("author_association") in TRUSTED_ASSOCIATIONS


def is_from_actions(comment_):
    """A comment written by GitHub Actions (github-actions[bot])."""
    user = comment_.get("user") if isinstance(comment_.get("user"), dict) else {}
    return user.get("login") == ACTIONS_BOT_LOGIN and user.get("type") == "Bot"


def is_trusted_reserve(comment_):
    """A reserve-workflow comment: from GitHub Actions, or from a trusted author."""
    return is_from_actions(comment_) or is_trusted(comment_)


def latest_written(blocks):
    """The block written last (by last_written, then position), or None."""
    return max(blocks, key=lambda b: (last_written(b[2]), b[1])) if blocks else None


def stop_reason(body):
    m = STOP_REASON_RE.search(body)
    return m.group(1) if m else "unspecified"


def is_lookup_reserve(body):
    """True when a reserve comment was written by a lookup run (`run: api-lookup`)."""
    m = RESERVE_RUN_RE.search(body)
    return bool(m) and m.group(1) == RESERVE_RUN_LOOKUP


def reserve_stop_summary(body):
    """One line of a reserve stop comment, for the verdict: its text after the marker
    (and after its `reason:` line), prefixed with the reason code when there is one."""
    rest = body.split("\n", 1)[1] if "\n" in body else ""
    line = next((l.strip() for l in rest.split("\n")
                 if l.strip() and not STOP_REASON_RE.match(l.strip())), "")
    line = re.sub(r"^\W*\*\*Identity not reserved\*\*\s*\W\s*", "", line)
    line = line.split(". Nothing was written", 1)[0]
    line = (line[:200] + "...") if len(line) > 200 else (line or "unspecified")
    m = STOP_REASON_RE.search(rest)
    return f"{m.group(1)}: {line}" if m else line


def parse_discover(body, reasons):
    """Parse one Discover block body into a dict, appending reasons on failure."""
    m = FENCE_RE.search(body)
    if not m:
        reasons.append("discover block has no fenced yaml block")
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        first = str(e).splitlines()[0] if str(e) else "parse error"
        reasons.append(f"discover block yaml is malformed: {first}")
        return None
    if not isinstance(data, dict):
        reasons.append("discover block yaml is not a mapping")
        return None

    out = {}
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        reasons.append("discover block has no sources")
        sources = []
    out["sources"] = []
    for n, s in enumerate(sources, 1):
        if not isinstance(s, dict):
            reasons.append(f"source {n} is not a mapping")
            continue
        problem = source_url_problem(s.get("url"))
        if problem:
            reasons.append(f"source {n} url {problem}")
        if not is_positive_int(s.get("card_count")):
            reasons.append(f"source {n} card_count must be a positive integer")
        entry = {"url": s.get("url"), "card_count": s.get("card_count")}
        if "parallels_listed" in s:
            if not isinstance(s["parallels_listed"], bool):
                reasons.append(f"source {n} parallels_listed must be true or false")
            entry["parallels_listed"] = s["parallels_listed"]
        out["sources"].append(entry)

    for key in ("name", "genre"):
        if key in data and not (isinstance(data[key], str) and data[key].strip()):
            reasons.append(f"discover block {key} must be a non-empty string")
    if isinstance(data.get("genre"), str) and data["genre"] not in GENRES:
        reasons.append(f"discover block genre must be one of {sorted(GENRES)}")
    for key in ("sports", "category"):
        v = data.get(key)
        if key in data and not (isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)):
            reasons.append(f"discover block {key} must be a non-empty list of strings")
    if "year" in data and not is_positive_int(data["year"]):
        reasons.append("discover block year must be a positive integer")
    for key in ("name", "genre", "sports", "category", "year"):
        out[key] = data.get(key)
    return out


def parse_ruling(body):
    """Parse an operator-ruling comment body, or return None when it is malformed.

    A ruling names the authoritative source of a source-disagreement stop and,
    optionally, sources to drop. A malformed ruling is not an error for the checker:
    it adds no reason, because a ruling never decides readiness (the Discover block a
    re-run writes does). Discover refuses to act on a ruling this returns None for.
    """
    m = FENCE_RE.search(body or "")
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except (yaml.YAMLError, ValueError, TypeError, OverflowError, RecursionError):
        # The loader raises the non-YAMLError ones itself, exactly as
        # tools/compare_sources.py's _read_yaml handles them: an integer over CPython's
        # 4300-digit limit, an impossible date such as 2025-02-30, or nesting deeper
        # than the recursion limit. A ruling is untrusted input however trusted its
        # author, so any of them is a malformed ruling, never a checker failure.
        return None
    if not isinstance(data, dict) or data.get("reason") != RULING_REASON:
        return None
    authoritative = data.get("authoritative")
    if source_url_problem(authoritative):
        return None
    drop = data.get("drop", [])
    if drop is None:
        drop = []
    if not isinstance(drop, list) or any(
            not isinstance(u, str) or source_url_problem(u) for u in drop):
        return None
    # Same normalization the comparator applies to a source url, so padding cannot
    # hide the authoritative source inside its own drop list.
    authoritative = authoritative.strip()
    drop = list(dict.fromkeys(u.strip() for u in drop))
    if authoritative in drop:
        return None  # a ruling cannot both keep and drop its authoritative source
    return {"authoritative": authoritative, "drop": drop}


def effective_ruling(comments):
    """The newest trusted ruling comment, parsed, or None (informational only)."""
    latest = latest_written([b for b in marked_comments(comments, DISCOVER_RULING_MARKER)
                             if is_trusted(b[2])])
    if not latest:
        return None
    parsed = parse_ruling(latest[3])
    if parsed is None:
        return None
    return {"comment_id": latest[2].get("id"), **parsed}


# --------------------------------------------------------------------------- check

def check(payload, data_dir="data"):
    """Return the verdict dict for a work-order payload."""
    issue = payload.get("issue") or {}
    reasons = []

    # 1. An open issue of type Work Order (keyed on the type, never the label: #79).
    if issue.get("pull_request"):
        reasons.append("ref is a pull request, not an issue")
    if issue.get("state") != "open":
        reasons.append(f"issue is not open (state: {issue.get('state')})")
    if issue_type_name(issue) != WORK_ORDER_TYPE:
        reasons.append(f"issue type is not '{WORK_ORDER_TYPE}' (got: {issue_type_name(issue)})")

    # 2. set_id: present, a slug, no existing data dir.
    # The pinned value is checked as written: the producer may not edit pinned
    # fields, so surrounding whitespace is refused rather than silently stripped.
    set_id = field_value(payload.get("field_values"), FIELD_SET_ID)
    set_id = set_id if isinstance(set_id, str) else None
    if not (set_id and set_id.strip()):
        set_id = None
        reasons.append("pinned field set_id is empty")
    elif set_id != set_id.strip():
        reasons.append(f"set_id {set_id!r} has surrounding whitespace")
    elif not SLUG_RE.match(set_id):
        reasons.append(f"set_id '{set_id}' is not a lowercase slug")
    elif set_id in existing_set_ids(data_dir):
        reasons.append(f"set_id '{set_id}' already has a data directory")

    # 3. Reserved set UUID: present, a valid UUID, not already used.
    raw_uuid = field_value(payload.get("field_values"), FIELD_UUID)
    reserved = None
    if not (isinstance(raw_uuid, str) and raw_uuid.strip()):
        reasons.append("pinned field Reserved set UUID is empty")
    else:
        # The producer commits the reserved UUID unchanged, so the verdict returns the
        # field text as written (only trimmed) and canonicalizes solely to compare for
        # collisions. Only the hyphenated 8-4-4-4-12 form is accepted: uuid.UUID also
        # takes braces, urn: and bare-hex forms, which must not reach a committed file.
        text = raw_uuid.strip()
        try:
            if not UUID_TEXT_RE.match(text):
                raise ValueError(text)
            canonical = str(uuidlib.UUID(text))
        except ValueError:
            reasons.append(f"Reserved set UUID '{text}' is not a valid UUID")
        else:
            reserved = text
            if canonical in existing_uuids(data_dir):
                reasons.append(f"Reserved set UUID {reserved} is already used under {data_dir}/")

    # 4. Exactly one effective Discover block (last-written trusted one wins), not revoked
    # by a Discover stop or a reservation stop. A trusted `<!-- ocp-discover-stop:v1 -->`
    # comment written at or after the effective block revokes it: a re-run that stopped
    # (e.g. source-disagreement, api-mismatch) must not leave an earlier block usable.
    # A trusted `<!-- ocp-reserve-stop:v1 -->` (the reserve workflow found a pinned, body
    # or API UUID conflict and wrote nothing) makes the issue not ready until GitHub
    # Actions writes its `<!-- ocp-reserve:v1 -->` comment after the stop from a lookup
    # run (tagged `run: api-lookup`: a Discover dispatch with a fresh API lookup). Only
    # that clears it. A Discover block written after the stop does not: Discover posts
    # its block before its dispatch re-checks the UUID, so the block alone would read
    # ready in the window before the reserve run. A reserve comment from an issue-event
    # run never clears it either, since that run did no lookup and so cannot show an
    # API conflict is resolved, and nor does one from any author but github-actions[bot].
    comments = payload.get("comments")
    blocks = discover_blocks(comments)
    trusted = [b for b in blocks if is_trusted(b[2])]
    latest_stop = latest_written([b for b in marked_comments(comments, DISCOVER_STOP_MARKER)
                                  if is_trusted(b[2])])
    latest_reserve_stop = latest_written([b for b in marked_comments(comments, RESERVE_STOP_MARKER)
                                          if is_trusted_reserve(b[2])])
    latest_reserve = latest_written([b for b in marked_comments(comments, RESERVE_MARKER)
                                     if is_from_actions(b[2]) and is_lookup_reserve(b[3])])
    # The effective block is the trusted one written last: a re-run PATCHes an
    # existing block in place, so the older-by-created_at block can be the newest.
    effective = max(trusted, key=lambda b: (last_written(b[2]), b[0], b[1])) if trusted else None
    effective_at = last_written(effective[2]) if effective else ""
    reserve_stopped = bool(latest_reserve_stop) and (
        not latest_reserve or last_written(latest_reserve_stop[2]) >= last_written(latest_reserve[2]))
    discover = None
    if reserve_stopped:
        reasons.append(f"identity reservation stopped ({reserve_stop_summary(latest_reserve_stop[3])}) "
                       "and no api-lookup reservation was written after the stop")
    if latest_stop and (not effective or last_written(latest_stop[2]) >= effective_at):
        reasons.append(f"discover stopped ({stop_reason(latest_stop[3])}) and no discover "
                       "block was written after the stop")
    elif not blocks:
        reasons.append("no discover block comment (first line <!-- ocp-discover:v1 -->)")
    elif not trusted:
        reasons.append("discover block is not from a repo owner, member or collaborator")
    elif not reserve_stopped:
        discover = parse_discover(effective[3], reasons)

    title = issue.get("title") or ""
    block_name = discover.get("name") if discover else None
    name = block_name if isinstance(block_name, str) and block_name.strip() else \
        re.sub(r"^\[Work Order\]\s*", "", title, flags=re.IGNORECASE).strip()

    return {
        "ready": not reasons,
        "reasons": reasons,
        "number": issue.get("number"),
        "set_id": set_id,
        "reserved_uuid": reserved,
        "name": name or None,
        "name_source": "discover-block" if block_name else "title",
        "genre": discover.get("genre") if discover else None,
        "sports": discover.get("sports") if discover else None,
        "category": discover.get("category") if discover else None,
        "year": discover.get("year") if discover else None,
        "sources": discover.get("sources") if discover else [],
        # Informational: the newest trusted operator ruling on a source-disagreement
        # stop. It never changes `reasons` or `ready`.
        "ruling": effective_ruling(comments),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("number", nargs="?", type=int, help="work-order issue number")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/repo (default {DEFAULT_REPO})")
    ap.add_argument("--from-json", help="read the issue/field_values/comments payload from a file")
    ap.add_argument("--data-dir", default="data", help="data directory for collision checks")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else 0
    if (args.number is None) == (args.from_json is None):
        print("error: give exactly one of <number> or --from-json", file=sys.stderr)
        return EXIT_USAGE
    if args.number is not None and args.number < 1:
        print("error: number must be a positive integer", file=sys.stderr)
        return EXIT_USAGE
    if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", args.repo):
        print(f"error: invalid --repo {args.repo!r}", file=sys.stderr)
        return EXIT_USAGE
    try:
        payload = load_json_payload(args.from_json) if args.from_json \
            else fetch_work_order(args.repo, args.number)
    except ReadError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
    verdict = check(payload, args.data_dir)
    print(json.dumps(verdict, indent=2))
    return EXIT_READY if verdict["ready"] else EXIT_NOT_READY


if __name__ == "__main__":
    sys.exit(main())
