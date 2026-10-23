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
#
# `--release <X.Y.Z>` cuts a release (#82): it collates as usual, then turns the
# collated `[Unreleased]` body into a `## [X.Y.Z] - YYYY-MM-DD` section and
# leaves a fresh empty `## [Unreleased]` above it. That versioned section is the
# one .github/workflows/release.yml tags. The date is today in UTC, or
# $RELEASE_DATE (YYYY-MM-DD) when set. See docs/RELEASING.md.
#
# Usage:
#   scripts/collate-changelog.sh                    collate and write
#   scripts/collate-changelog.sh --check            validate fragment names and bodies only
#   scripts/collate-changelog.sh --release X.Y.Z    collate, then cut version X.Y.Z
#
# Exit codes:
#   0  collated, or nothing pending, or --check passed, or the release was cut
#   1  a fragment is malformed, a path is a symlink or otherwise not the
#      required regular file/directory, CHANGELOG.md cannot be safely
#      re-rendered, or a release cannot be cut (nothing under [Unreleased], or
#      the version already has a section)
#   2  bad invocation: an unknown or extra argument, or a release version or
#      date that is not strict X.Y.Z / YYYY-MM-DD
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
  printf 'usage: %s [--check | --release X.Y.Z]\n' "${0##*/}"
}

# valid_date YYYY-MM-DD: the shape, and a real day of a real month (leap
# years included). Pure bash, so it behaves the same on GNU and BSD date.
valid_date() {
  [[ "$1" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})$ ]] || return 1
  local y=$((10#${BASH_REMATCH[1]})) m=$((10#${BASH_REMATCH[2]})) d=$((10#${BASH_REMATCH[3]})) max
  [ "$m" -ge 1 ] && [ "$m" -le 12 ] && [ "$d" -ge 1 ] || return 1
  case "$m" in
    4|6|9|11) max=30 ;;
    2) if { [ $((y % 4)) -eq 0 ] && [ $((y % 100)) -ne 0 ]; } || [ $((y % 400)) -eq 0 ]; then max=29; else max=28; fi ;;
    *) max=31 ;;
  esac
  [ "$d" -le "$max" ]
}

# num_cmp A B: -1, 0 or 1 for two non-negative decimal integers without
# leading zeros. Length first, then lexicographic, so a SemVer component of
# any size compares correctly without bash's fixed-width integer conversion.
num_cmp() {
  if [ "${#1}" -ne "${#2}" ]; then
    [ "${#1}" -lt "${#2}" ] && echo -1 || echo 1
  elif [ "$1" = "$2" ]; then
    echo 0
  elif [[ "$1" < "$2" ]]; then
    echo -1
  else
    echo 1
  fi
}

# ver_newer A B: succeed when X.Y.Z A is strictly newer than B.
ver_newer() {
  local a1 a2 a3 b1 b2 b3 c
  IFS=. read -r a1 a2 a3 <<< "$1"
  IFS=. read -r b1 b2 b3 <<< "$2"
  c=$(num_cmp "$a1" "$b1"); [ "$c" = 0 ] || { [ "$c" = 1 ]; return; }
  c=$(num_cmp "$a2" "$b2"); [ "$c" = 0 ] || { [ "$c" = 1 ]; return; }
  c=$(num_cmp "$a3" "$b3"); [ "$c" = 1 ]
}

check_only=0
release=""
case "${1-}" in
  --check)
    check_only=1
    [ "$#" -le 1 ] || { printf 'error: too many arguments\n' >&2; usage >&2; exit 2; }
    ;;
  --release)
    if [ "$#" -ne 2 ]; then
      printf 'error: --release takes exactly one version argument\n' >&2
      usage >&2
      exit 2
    fi
    release="$2"
    # Same strict SemVer core as release.yml: no leading zeros, no prefix.
    if ! [[ "$release" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
      printf 'error: release version %s is not strict X.Y.Z (no "v" prefix, no leading zeros)\n' "$release" >&2
      exit 2
    fi
    release_date="${RELEASE_DATE:-$(date -u +%Y-%m-%d)}"
    if ! valid_date "$release_date"; then
      printf 'error: RELEASE_DATE %s is not a real YYYY-MM-DD calendar date\n' "$release_date" >&2
      exit 2
    fi
    ;;
  -h|--help) usage; exit 0 ;;
  "")
    [ "$#" -eq 0 ] || { usage >&2; exit 2; }
    ;;
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

# With no fragment directory there is nothing to collate, but a release still
# versions what an earlier collation put under [Unreleased], so only the plain
# and --check modes stop here.
if [ ! -d "$FRAGMENT_DIR" ] && [ -z "$release" ]; then
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
    /^- \*\*\[Issue #[1-9][0-9]*\]\*\*[[:space:]]+[^[:space:]]/ { next }
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
done < <(if [ -d "$FRAGMENT_DIR" ]; then find "$FRAGMENT_DIR" -path "$FRAGMENT_DIR/*" -prune -print0; fi)

if [ "$malformed" -ne 0 ]; then
  exit 1
fi

if [ "$check_only" -eq 1 ]; then
  printf '%s fragment(s) validated\n' "$pending"
  exit 0
fi

# A release still has work to do with nothing pending: it versions whatever an
# earlier collation already put under [Unreleased].
if [ "$pending" -eq 0 ] && [ -z "$release" ]; then
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
# 4. Write the file back. In release mode the collated groups go under the new
#    version heading and [Unreleased] is left empty above it, so the version
#    is the first bracketed `## [X.Y.Z]` heading, which is what release.yml reads.
# ---------------------------------------------------------------------------

if [ -n "$release" ]; then
  has_entries=0
  for t in $TYPES; do
    [ -s "$work/body.$t" ] && has_entries=1
  done
  if [ "$has_entries" -eq 0 ]; then
    printf 'error: nothing under %s and no pending fragments; refusing to cut an empty release %s.\n' \
      "$SECTION" "$release" >&2
    exit 1
  fi
  if [ -f "$CHANGELOG" ] && awk -v h="## [$release]" 'index($0, h) == 1 { f = 1 } END { exit f ? 0 : 1 }' "$CHANGELOG"; then
    printf 'error: %s already has a ## [%s] section; pick the next version.\n' "$CHANGELOG" "$release" >&2
    exit 1
  fi
  # The new section is written directly under [Unreleased]. It is the first
  # versioned heading, the one release.yml publishes, only when no versioned
  # section sits above [Unreleased]; refuse that layout rather than cut a
  # release that release.yml would never see.
  if grep -qE '^## \[[^]]+\]' "$before_file"; then
    printf 'error: %s has a versioned section above %s; move %s to the top before cutting a release.\n' \
      "$CHANGELOG" "$SECTION" "$SECTION" >&2
    exit 1
  fi
  # It must also be newer than every version already in the file, or
  # release.yml would publish an older number as the newest release.
  if [ -f "$CHANGELOG" ]; then
    while IFS= read -r existing; do
      [[ "$existing" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || continue
      if ! ver_newer "$release" "$existing"; then
        printf 'error: release %s is not newer than ## [%s] already in %s; pick a higher version.\n' \
          "$release" "$existing" "$CHANGELOG" >&2
        exit 1
      fi
    done < <(sed -nE 's/^## \[([^]]+)\].*/\1/p' "$CHANGELOG")
  fi
fi

{
  if [ -s "$before_file" ]; then
    cat "$before_file"
    # `before` is copied verbatim; add a separating blank line only if needed.
    if [ -n "$(tail -n 1 "$before_file")" ]; then
      printf '\n'
    fi
  fi

  printf '%s\n\n' "$SECTION"

  if [ -n "$release" ]; then
    printf '## [%s] - %s\n\n' "$release" "$release_date"
  fi

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

if [ -n "$release" ]; then
  printf 'collated %s fragment(s) and cut ## [%s] - %s in %s\n' "$pending" "$release" "$release_date" "$CHANGELOG"
else
  printf 'collated %s fragment(s) into %s under %s\n' "$pending" "$CHANGELOG" "$SECTION"
fi
