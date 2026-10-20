#!/usr/bin/env bash
#
# Collate changelog.d/ fragments into the `## [Unreleased]` section of CHANGELOG.md.
#
# This is the consumer half of the per-PR fragment convention described in
# changelog.d/README.md. Each PR writes one fragment at
# changelog.d/<issue>-<type>.md; this script drains the directory into
# CHANGELOG.md and deletes the fragments it consumed. It runs post-merge from
# .github/workflows/collate-changelog.yml, and is never run inside a PR.
#
# Fragments are written under `## [Unreleased]`, in the existing layout:
# `### Added|Changed|...` subsections, one `- **[Issue #N]** ...` bullet each.
# This repo cuts no tagged releases yet (#82); when it does, a `--release
# <version>` mode can rename [Unreleased] into a versioned section.
#
# Usage:
#   scripts/collate-changelog.sh            collate and write
#   scripts/collate-changelog.sh --check    validate fragment names and bodies only
#
# Exit codes:
#   0  collated, or nothing pending, or --check passed
#   1  a fragment is malformed, a path is a symlink or otherwise not the
#      required regular file/directory, or CHANGELOG.md cannot be safely
#      re-rendered
#   2  bad invocation: an unknown or extra argument
#
# Written for bash 3.2 (macOS ships it): no associative arrays, no mapfile.

set -euo pipefail

FRAGMENT_DIR="changelog.d"
CHANGELOG="CHANGELOG.md"
SECTION="## [Unreleased]"

# Keep-a-Changelog subsection order. Empty groups are skipped at render time.
TYPES="added changed deprecated removed fixed security"

# Files that live in changelog.d/ but are not fragments.
BOOKKEEPING="README.md .gitkeep .markdownlint.json"

usage() {
  printf 'usage: %s [--check]\n' "${0##*/}"
}

if [ "$#" -gt 1 ]; then
  printf 'error: too many arguments (expected at most one)\n' >&2
  usage >&2
  exit 2
fi

check_only=0
case "${1-}" in
  --check) check_only=1 ;;
  -h|--help) usage; exit 0 ;;
  "") ;;
  *)
    printf 'error: unknown argument: %s\n' "$1" >&2
    usage >&2
    exit 2
    ;;
esac

cd "$(git rev-parse --show-toplevel)"

# Refuse to collate through a symlinked fragment directory: the fragments it
# resolves to live outside the repo, so consuming (and deleting) them would
# reach outside the working tree.
if [ -L "$FRAGMENT_DIR" ]; then
  printf 'error: %s is a symlink; refusing to collate through it.\n' "$FRAGMENT_DIR" >&2
  exit 1
fi

# An existing non-directory must not take the "absent" branch below, or the
# workflow would report success having collated nothing.
if [ -e "$FRAGMENT_DIR" ] && [ ! -d "$FRAGMENT_DIR" ]; then
  printf 'error: %s exists but is not a directory; refusing to collate.\n' "$FRAGMENT_DIR" >&2
  exit 1
fi

if [ ! -d "$FRAGMENT_DIR" ]; then
  printf 'no pending fragments (%s does not exist)\n' "$FRAGMENT_DIR"
  exit 0
fi

is_bookkeeping() {
  for b in $BOOKKEEPING; do
    [ "$1" = "$b" ] && return 0
  done
  return 1
}

title_for() {
  case "$1" in
    added) printf 'Added' ;;
    changed) printf 'Changed' ;;
    deprecated) printf 'Deprecated' ;;
    removed) printf 'Removed' ;;
    fixed) printf 'Fixed' ;;
    security) printf 'Security' ;;
    *) printf 'error: unknown fragment type: %s\n' "$1" >&2; exit 1 ;;
  esac
}

# Strip leading and trailing blank lines. Reads a file, writes to stdout.
trim_blanks() {
  awk '
    { lines[NR] = $0 }
    END {
      first = 0; last = 0
      for (i = 1; i <= NR; i++)
        if (lines[i] ~ /[^[:space:]]/) { if (first == 0) first = i; last = i }
      for (i = first; i <= last && first > 0; i++) print lines[i]
    }
  ' "$1"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# ---------------------------------------------------------------------------
# 1. Collect and validate fragments.
#
# Every non-bookkeeping entry is validated. A non-conforming name is a hard
# failure, never a silent skip: a skipped fragment is an entry that never
# reaches the changelog, which is the failure this script exists to remove.
# ---------------------------------------------------------------------------

malformed=0
pending=0

while IFS= read -r -d '' path; do
  [ -n "$path" ] || continue
  base="${path##*/}"

  is_bookkeeping "$base" && continue

  if [ -L "$path" ]; then
    printf 'error: %s is a symlink; fragments must be regular files.\n' "$path" >&2
    malformed=1
    continue
  fi

  if [ -d "$path" ]; then
    printf 'error: %s is a directory; %s holds fragments only.\n' "$path" "$FRAGMENT_DIR" >&2
    malformed=1
    continue
  fi

  # A fifo or device node named like a fragment would block awk forever.
  if [ ! -f "$path" ]; then
    printf 'error: %s is not a regular file; %s holds regular files only.\n' "$path" "$FRAGMENT_DIR" >&2
    malformed=1
    continue
  fi

  # bash's own =~ matches the whole string; grep matches per line and would
  # accept a name with a newline in it.
  if ! [[ "$base" =~ ^[1-9][0-9]*-(added|changed|fixed|security|removed|deprecated)\.md$ ]]; then
    printf 'error: %s does not match <issue>-<type>.md (type one of added|changed|fixed|security|removed|deprecated).\n' \
      "$path" >&2
    malformed=1
    continue
  fi

  if [ -z "$(trim_blanks "$path")" ]; then
    printf 'error: %s is empty; a blank fragment would render as nothing.\n' "$path" >&2
    malformed=1
    continue
  fi

  # The documented shape is a bullet, optionally followed by more bullets or
  # indented sub-bullet/continuation lines. Anything else (a heading, loose
  # prose) would be copied into [Unreleased], consumed, and then make the next
  # run refuse the section it just wrote, so reject it while it is still a
  # recoverable fragment.
  if ! body_err=$(trim_blanks "$path" | awk '
    NR == 1 && $0 !~ /^- / { print "first line must start with \"- \""; exit 1 }
    /^[[:space:]]*$/ { next }
    /^- \*\*\[Issue #[1-9][0-9]*\]\*\* / { next }
    /^- / { print "line " NR " is a top-level bullet without the \"- **[Issue #N]** \" prefix: " $0; exit 1 }
    /^[[:space:]]+[^[:space:]]/ { next }
    { print "line " NR " is not a bullet or an indented continuation: " $0; exit 1 }
  '); then
    printf 'error: %s has an invalid body (%s); expected a "- **[Issue #N]** ..." bullet with optional indented sub-bullets.\n' \
      "$path" "$body_err" >&2
    malformed=1
    continue
  fi

  num="${base%%-*}"
  type="${base#*-}"
  type="${type%.md}"

  printf '%s %s\n' "$num" "$path" >> "$work/list.$type"
  pending=$((pending + 1))
# NUL-delimited, and process substitution rather than a pipe, so the loop body
# stays in this shell and its counters survive it. `-path ... -prune` lists the
# directory's immediate children using only POSIX find primaries: -mindepth and
# -maxdepth are GNU extensions that macOS's BSD find lacks.
done < <(find "$FRAGMENT_DIR" -path "$FRAGMENT_DIR/*" -prune -print0)

if [ "$malformed" -ne 0 ]; then
  exit 1
fi

if [ "$check_only" -eq 1 ]; then
  printf '%s fragment(s) validated\n' "$pending"
  exit 0
fi

if [ "$pending" -eq 0 ]; then
  printf 'no pending fragments\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. Split CHANGELOG.md into: before [Unreleased] / the [Unreleased] section /
#    everything after it. `before` and `after` are copied through verbatim, so
#    existing released entries are never rewritten.
# ---------------------------------------------------------------------------

before_file="$work/before"
unrel_file="$work/unreleased"
after_file="$work/after"
: > "$before_file"
: > "$unrel_file"
: > "$after_file"

# -f follows symlinks, so a symlinked CHANGELOG.md would be read and then
# replaced by a regular file, publishing whatever it pointed at.
if [ -L "$CHANGELOG" ]; then
  printf 'error: %s is a symlink; refusing to collate into it.\n' "$CHANGELOG" >&2
  exit 1
fi

if [ -e "$CHANGELOG" ] && [ ! -f "$CHANGELOG" ]; then
  printf 'error: %s exists but is not a regular file; refusing to collate into it.\n' "$CHANGELOG" >&2
  exit 1
fi

if [ -f "$CHANGELOG" ]; then
  unrel_line=$(grep -n -F -x "$SECTION" "$CHANGELOG" | head -1 | cut -d: -f1 || true)
  if [ -n "$unrel_line" ]; then
    if [ "$unrel_line" -gt 1 ]; then
      head -n $((unrel_line - 1)) "$CHANGELOG" > "$before_file"
    fi
    tail -n +"$((unrel_line + 1))" "$CHANGELOG" > "$work/tail"
    next_rel=$(grep -n '^## ' "$work/tail" | head -1 | cut -d: -f1 || true)
    if [ -n "$next_rel" ]; then
      head -n $((next_rel - 1)) "$work/tail" > "$unrel_file"
      tail -n +"$next_rel" "$work/tail" > "$after_file"
    else
      cat "$work/tail" > "$unrel_file"
    fi
  else
    # No [Unreleased] section yet: insert one before the first existing section.
    first_section=$(grep -n '^## ' "$CHANGELOG" | head -1 | cut -d: -f1 || true)
    if [ -z "$first_section" ]; then
      cat "$CHANGELOG" > "$before_file"
    else
      if [ "$first_section" -gt 1 ]; then
        head -n $((first_section - 1)) "$CHANGELOG" > "$before_file"
      fi
      tail -n +"$first_section" "$CHANGELOG" > "$after_file"
    fi
  fi
else
  cat > "$before_file" <<'HDR'
# Changelog

All notable changes to this project are documented in this file.
HDR
fi

# Re-rendering [Unreleased] drops anything the parse cannot bucket, so refuse
# content it cannot preserve: a subheading outside the known set, or text above
# the first subheading. Both are only reachable by hand-editing.
awk -v types=" $TYPES " -v file="$CHANGELOG" '
  /^### / {
    t = tolower($2)
    if (NF != 2 || index(types, " " t " ") == 0) {
      printf "error: %s: unrecognised subheading \"%s\" in [Unreleased]; expected exactly \"### <Type>\".\n", file, $0 > "/dev/stderr"
      bad = 1
    }
    seen = 1
    next
  }
  /[^[:space:]]/ {
    if (!seen) {
      printf "error: %s: content above the first ### subheading in [Unreleased]: %s\n", file, $0 > "/dev/stderr"
      bad = 1
    }
  }
  END { exit bad ? 1 : 0 }
' "$unrel_file" || {
  printf 'error: %s [Unreleased] was hand-edited; refusing to re-render a section whose content cannot be preserved.\n' \
    "$CHANGELOG" >&2
  exit 1
}

awk -v dir="$work" '
  /^### / { t = tolower($2); next }
  { if (t != "") print >> (dir "/old." t) }
' "$unrel_file"

# ---------------------------------------------------------------------------
# 3. Build each type group: pre-existing bullets first, then this run's
#    fragments in ascending issue order.
# ---------------------------------------------------------------------------

for t in $TYPES; do
  body="$work/body.$t"
  : > "$body"

  if [ -s "$work/old.$t" ]; then
    trim_blanks "$work/old.$t" >> "$body"
  fi

  if [ -f "$work/list.$t" ]; then
    # Sort to a file: a failure inside a here-doc command substitution would be
    # discarded, rendering an empty group while step 5 still deleted fragments.
    sort -n "$work/list.$t" > "$work/sorted.$t"
    while IFS=' ' read -r _num path; do
      [ -n "$path" ] || continue
      trim_blanks "$path" >> "$body"
    done < "$work/sorted.$t"
  fi
done

# ---------------------------------------------------------------------------
# 4. Write the file back.
# ---------------------------------------------------------------------------

{
  if [ -s "$before_file" ]; then
    cat "$before_file"
    # `before` is copied verbatim; add a separating blank line only if needed.
    if [ -n "$(tail -n 1 "$before_file")" ]; then
      printf '\n'
    fi
  fi

  printf '%s\n\n' "$SECTION"

  first_group=1
  for t in $TYPES; do
    [ -s "$work/body.$t" ] || continue
    [ "$first_group" -eq 1 ] || printf '\n'
    first_group=0
    printf '### %s\n\n' "$(title_for "$t")"
    cat "$work/body.$t"
  done

  if [ -s "$after_file" ]; then
    printf '\n'
    cat "$after_file"
  fi
} > "$work/out"

mv "$work/out" "$CHANGELOG"

# ---------------------------------------------------------------------------
# 5. Consume the fragments.
# ---------------------------------------------------------------------------

for t in $TYPES; do
  [ -f "$work/list.$t" ] || continue
  while IFS=' ' read -r _num path; do
    [ -n "$path" ] || continue
    rm -f "$path"
  done < "$work/list.$t"
done

printf 'collated %s fragment(s) into %s under %s\n' "$pending" "$CHANGELOG" "$SECTION"
