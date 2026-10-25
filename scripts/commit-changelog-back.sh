#!/usr/bin/env bash
#
# Cut a release's changelog section and commit it straight back to main (#98).
#
# Runs from .github/workflows/release.yml, after the merge and never inside a
# pull request. It is the only thing that writes CHANGELOG.md:
#
#   1. scripts/collate-changelog.sh --check validates every pending fragment,
#      so a malformed or symlinked fragment fails the run before any file is
#      touched.
#   2. scripts/collate-changelog.sh --release VERSION drains changelog.d/ into
#      a new `## [VERSION] - YYYY-MM-DD` section under a fresh, empty
#      `## [Unreleased]`, and deletes the fragments it consumed.
#   3. CHANGELOG.md plus the fragment deletions are committed as
#      cardtechie-ops-bot[bot] with the subject `docs: collate CHANGELOG for
#      VERSION` and pushed to BRANCH. The push is a plain fast-forward, never a
#      force push, so the org `non_fast_forward` rule does not reject it. A
#      rejected push fails the run, so no tag is ever created for a version
#      whose notes did not land.
#
# Resume: when CHANGELOG.md already has `## [VERSION]`, the run is refused,
# UNLESS HEAD is this script's own commit-back for VERSION. Then it writes
# nothing and reports release=true, so a rerun of the release workflow can
# finish tagging a version whose commit-back already landed. See
# head_is_own_commit_back below for what "own" means.
#
# `--output FILE` appends `release=true|false` and `sha=<HEAD>` to FILE (the
# workflow passes $GITHUB_OUTPUT). release=true means HEAD carries a
# `## [VERSION]` section to tag and publish.
#
# Usage:
#   scripts/commit-changelog-back.sh VERSION [--branch BRANCH] [--no-push] [--output FILE]
#
# Exit codes:
#   0  committed and pushed (or committed with --no-push), or resumed
#   1  the collation, commit or push failed, or VERSION already has a section
#      that is not this script's own commit-back at HEAD
#   2  bad invocation: an unknown or missing argument, a VERSION that is not
#      strict X.Y.Z, or a BRANCH that is not a valid branch name
#
# Written for bash 3.2 (macOS ships it), like scripts/collate-changelog.sh.

set -euo pipefail

COMMIT_SUBJECT_PREFIX="docs: collate CHANGELOG for "
# The cardtechie-ops-bot GitHub App's bot user (id from
# `gh api "/users/cardtechie-ops-bot[bot]" --jq .id`). release.yml pushes with
# that App's installation token, so the commit is attributed to the same actor.
BOT_NAME="cardtechie-ops-bot[bot]"
BOT_EMAIL="229868027+cardtechie-ops-bot[bot]@users.noreply.github.com"

CHANGELOG="CHANGELOG.md"
FRAGMENT_DIR="changelog.d"
BOOKKEEPING="README.md .gitkeep .markdownlint.json"

usage() {
  printf 'usage: %s VERSION [--branch BRANCH] [--no-push] [--output FILE]\n' "${0##*/}"
}

VERSION=""
BRANCH="main"
DO_PUSH=1
OUTPUT_FILE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf 'error: --branch requires a value\n' >&2; usage >&2; exit 2
      fi
      BRANCH="$2"; shift 2 ;;
    --no-push)
      DO_PUSH=0; shift ;;
    --output)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf 'error: --output requires a value\n' >&2; usage >&2; exit 2
      fi
      OUTPUT_FILE="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    -*)
      printf 'error: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *)
      if [ -n "$VERSION" ]; then
        printf 'error: unexpected extra argument: %s\n' "$1" >&2; usage >&2; exit 2
      fi
      VERSION="$1"; shift ;;
  esac
done

if [ -z "$VERSION" ]; then
  printf 'error: VERSION is required\n' >&2; usage >&2; exit 2
fi

# Same strict SemVer core as collate-changelog.sh: no leading zeros, no "v".
# Validated before VERSION reaches any git command or pattern below.
if ! [[ "$VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  printf 'error: version %s is not strict X.Y.Z (no "v" prefix, no leading zeros)\n' "$VERSION" >&2
  exit 2
fi

if ! git check-ref-format --branch "$BRANCH" >/dev/null 2>&1 || [[ "$BRANCH" == -* ]]; then
  printf 'error: %s is not a valid branch name\n' "$BRANCH" >&2
  exit 2
fi

# Resolve a relative --output against the caller's directory before the cd.
if [ -n "$OUTPUT_FILE" ] && [[ "$OUTPUT_FILE" != /* ]]; then
  OUTPUT_FILE="$PWD/$OUTPUT_FILE"
fi

write_result() {
  if [ -n "$OUTPUT_FILE" ]; then
    printf 'release=%s\n' "$1" >> "$OUTPUT_FILE"
    printf 'sha=%s\n' "$(git rev-parse HEAD)" >> "$OUTPUT_FILE"
  fi
}

cd "$(git rev-parse --show-toplevel)"

if [ -L "$CHANGELOG" ] || [ ! -f "$CHANGELOG" ]; then
  printf 'error: %s is missing or not a regular file\n' "$CHANGELOG" >&2
  exit 1
fi

# has_section FILE: succeed when FILE has a `## [VERSION]` heading. awk reads
# the whole input before deciding, so there is no early-exit SIGPIPE to
# misread under pipefail.
has_section() {
  awk -v h="## [$VERSION]" 'index($0, h) == 1 { f = 1 } END { exit f ? 0 : 1 }' "$1"
}

# True when HEAD is this script's own commit-back for VERSION. Author and
# subject are free text anyone can put on a commit, so they are only a
# pre-filter. What makes a resume safe is the commit's content:
#   - HEAD has exactly one parent, and that parent has no `## [VERSION]`
#     section, so HEAD is the commit that introduced it (a PR cannot: the
#     Changelog fragment gate refuses any PR that edits CHANGELOG.md); and
#   - HEAD touches nothing outside CHANGELOG.md and changelog.d/, so tagging it
#     releases exactly its parent's code plus the notes.
# Only the branch tip counts: if anything landed after the commit-back, HEAD
# carries code the section does not describe.
head_is_own_commit_back() {
  local meta author email subject parents path tmp
  meta=$(git log -1 --format='%an%x09%ae%x09%s' HEAD 2>/dev/null) || return 1
  IFS=$'\t' read -r author email subject <<< "$meta"
  [ "$author" = "$BOT_NAME" ] && [ "$email" = "$BOT_EMAIL" ] \
    && [ "$subject" = "${COMMIT_SUBJECT_PREFIX}${VERSION}" ] || return 1

  parents=$(git rev-list --parents -n 1 HEAD | wc -w | tr -d ' ')
  [ "$parents" = "2" ] || return 1

  # To a temp file, not `git show | grep -q`: under pipefail grep's early exit
  # can SIGPIPE git show, and the check would misread exactly when it matters.
  tmp=$(mktemp)
  if ! git show "HEAD^:$CHANGELOG" > "$tmp" 2>/dev/null; then
    rm -f "$tmp"; return 1
  fi
  if has_section "$tmp"; then
    rm -f "$tmp"; return 1
  fi
  rm -f "$tmp"

  while IFS= read -r path; do
    [ -n "$path" ] || continue
    case "$path" in
      "$CHANGELOG"|"$FRAGMENT_DIR"/*) ;;
      *) return 1 ;;
    esac
  done < <(git diff-tree --no-commit-id --name-only -r HEAD^ HEAD)
  return 0
}

if has_section "$CHANGELOG"; then
  if head_is_own_commit_back; then
    printf '%s already has ## [%s] from this script'"'"'s commit-back at HEAD; resuming without re-collating.\n' \
      "$CHANGELOG" "$VERSION"
    write_result true
    exit 0
  fi
  printf 'error: %s already has a ## [%s] section that is not this script'"'"'s commit-back at HEAD; refusing to write it twice.\n' \
    "$CHANGELOG" "$VERSION" >&2
  printf '       If %s moved past an earlier commit-back, tag and release that commit by hand.\n' "$BRANCH" >&2
  exit 1
fi

COLLATOR="scripts/collate-changelog.sh"

# Validate before touching anything. The collator rejects empty, heading-only,
# non-bullet and symlinked fragments, and a symlinked changelog.d/.
bash "$COLLATOR" --check

# Refuses an empty release, and a version that is not newer than every
# version already in CHANGELOG.md.
bash "$COLLATOR" --release "$VERSION"

# Do not trust the collator's exit status alone: a fragment that survives
# collation is an entry that never reaches the changelog.
leftover=""
if [ -d "$FRAGMENT_DIR" ]; then
  for frag in "$FRAGMENT_DIR"/* "$FRAGMENT_DIR"/.[!.]*; do
    [ -e "$frag" ] || [ -L "$frag" ] || continue
    base="${frag##*/}"
    skip=0
    for b in $BOOKKEEPING; do [ "$base" = "$b" ] && skip=1; done
    [ "$skip" -eq 1 ] || leftover="$leftover $frag"
  done
fi
if [ -n "$leftover" ]; then
  printf 'error: fragment(s) survived collation:%s\n' "$leftover" >&2
  exit 1
fi

if ! has_section "$CHANGELOG"; then
  printf 'error: the collator reported success but %s has no ## [%s] section\n' "$CHANGELOG" "$VERSION" >&2
  exit 1
fi

# Clear the index so nothing staged earlier rides along in the commit-back,
# then stage the changelog and the fragment deletions only.
git reset -q
git add -A -- "$CHANGELOG"
if [ -e "$FRAGMENT_DIR" ] || git ls-files --error-unmatch "$FRAGMENT_DIR" >/dev/null 2>&1; then
  git add -A -- "$FRAGMENT_DIR"
fi

# Through the GIT_AUTHOR_*/GIT_COMMITTER_* variables rather than `-c user.*`:
# those variables outrank git config, so an inherited value would otherwise
# put someone else's name on the commit and defeat the resume check.
GIT_AUTHOR_NAME="$BOT_NAME" GIT_AUTHOR_EMAIL="$BOT_EMAIL" \
GIT_COMMITTER_NAME="$BOT_NAME" GIT_COMMITTER_EMAIL="$BOT_EMAIL" \
  git commit --quiet --no-verify -m "${COMMIT_SUBJECT_PREFIX}${VERSION}"
printf 'committed the collated %s for %s\n' "$CHANGELOG" "$VERSION"

if [ "$DO_PUSH" -eq 1 ]; then
  # No --force and no `|| true`: a refused push must fail the release before
  # anything is tagged.
  if ! git push origin "HEAD:refs/heads/$BRANCH"; then
    printf 'error: the commit-back push to %s was rejected; nothing was tagged or published.\n' "$BRANCH" >&2
    printf '       Most likely the %s ruleset does not list the cardtechie-ops-bot App as a bypass\n' "$BRANCH" >&2
    printf '       actor, or %s moved during the run. Fix that and re-run the Release workflow.\n' "$BRANCH" >&2
    exit 1
  fi
  printf 'pushed the commit-back to %s\n' "$BRANCH"
else
  printf -- '--no-push: committed only\n'
fi

write_result true
