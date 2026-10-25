#!/usr/bin/env bash
#
# Tests for scripts/commit-changelog-back.sh. Runs it against throwaway git
# repos, each with a bare `origin`, so it never touches this repo's
# CHANGELOG.md, changelog.d/ or remote.
#
# Usage: bash scripts/commit-changelog-back.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/commit-changelog-back.sh"
COLLATOR="$HERE/collate-changelog.sh"
BOT="cardtechie-ops-bot[bot]"
BOT_EMAIL="229868027+cardtechie-ops-bot[bot]@users.noreply.github.com"
fails=0
count=0

pass() { count=$((count + 1)); printf 'ok   %s\n' "$1"; }
fail() { count=$((count + 1)); fails=$((fails + 1)); printf 'FAIL %s\n' "$1"; }

# Keep the fixtures' commits independent of the caller's git identity and
# config, and never sign them.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=Tester GIT_AUTHOR_EMAIL=tester@example.com
export GIT_COMMITTER_NAME=Tester GIT_COMMITTER_EMAIL=tester@example.com
export RELEASE_DATE=2026-10-24

# new_repo: a clone of a fresh bare origin whose main carries the current
# CHANGELOG shape and both scripts; cd into the clone. $ORIGIN is the bare repo.
new_repo() {
  root=$(mktemp -d)
  ORIGIN="$root/origin.git"
  git init -q --bare "$ORIGIN"
  git -C "$ORIGIN" symbolic-ref HEAD refs/heads/main
  git init -q -b main "$root/work" 2>/dev/null || { git init -q "$root/work" && git -C "$root/work" checkout -q -b main; }
  cd "$root/work" || exit 1
  mkdir -p scripts changelog.d
  cp "$SRC" scripts/commit-changelog-back.sh
  cp "$COLLATOR" scripts/collate-changelog.sh
  echo '# Changelog fragments' > changelog.d/README.md
  cat > CHANGELOG.md <<'CL'
# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- **[Issue #1]** First entry.
CL
  git add -A
  git commit -q -m "initial"
  git remote add origin "$ORIGIN"
  git push -q origin HEAD:refs/heads/main
}

run() { bash scripts/commit-changelog-back.sh "$@" >"$OUT" 2>&1; echo $?; }
OUT=$(mktemp)
RES=$(mktemp)

# 1. pending fragments: one commit, bot author, expected subject, pushed.
new_repo
echo '- **[Issue #7]** New thing.' > changelog.d/7-added.md
echo '- **[Issue #8]** Fixed thing.' > changelog.d/8-fixed.md
git add -A && git commit -q -m "add fragments" && git push -q origin HEAD:refs/heads/main
base=$(git rev-parse HEAD)
: > "$RES"
rc=$(run 0.1.0 --output "$RES")
[ "$rc" = 0 ] && pass "commit-back exits 0" || { fail "commit-back exit ($rc)"; cat "$OUT"; }
[ "$(git rev-list --count "$base..HEAD")" = 1 ] && pass "exactly one commit" || fail "commit count"
[ "$(git log -1 --format=%s)" = "docs: collate CHANGELOG for 0.1.0" ] && pass "subject" || fail "subject ($(git log -1 --format=%s))"
[ "$(git log -1 --format='%an <%ae>')" = "$BOT <$BOT_EMAIL>" ] && pass "authored by the bot" || fail "author ($(git log -1 --format='%an <%ae>'))"
grep -qx '## \[0.1.0\] - 2026-10-24' CHANGELOG.md && pass "versioned section written" || fail "section"
grep -qx -- '- \*\*\[Issue #7\]\*\* New thing.' CHANGELOG.md && grep -qx -- '- \*\*\[Issue #1\]\*\* First entry.' CHANGELOG.md \
  && pass "fragments and existing [Unreleased] entries collated" || fail "collated content"
[ ! -e changelog.d/7-added.md ] && [ ! -e changelog.d/8-fixed.md ] && [ -e changelog.d/README.md ] \
  && pass "fragments consumed, bookkeeping kept" || fail "fragment consumption"
[ "$(git diff-tree --no-commit-id --name-only -r HEAD | LC_ALL=C sort | tr '\n' ' ')" = "CHANGELOG.md changelog.d/7-added.md changelog.d/8-fixed.md " ] \
  && pass "commit touches only CHANGELOG.md and changelog.d/" || fail "commit paths"
[ "$(git -C "$ORIGIN" rev-parse refs/heads/main)" = "$(git rev-parse HEAD)" ] && pass "pushed to origin main" || fail "push"
grep -qx 'release=true' "$RES" && grep -qx "sha=$(git rev-parse HEAD)" "$RES" && pass "outputs release=true and sha" || fail "outputs ($(cat "$RES"))"
[ -z "$(git status --porcelain)" ] && pass "tree clean afterwards" || fail "tree dirty"

# 2. resume: rerunning the same version on its own commit-back writes nothing.
head_before=$(git rev-parse HEAD)
: > "$RES"
rc=$(run 0.1.0 --output "$RES")
[ "$rc" = 0 ] && [ "$(git rev-parse HEAD)" = "$head_before" ] && grep -qx 'release=true' "$RES" \
  && pass "resume on own HEAD commit writes nothing, reports release=true" || { fail "resume ($rc)"; cat "$OUT"; }

# 3. resume refused once main moved past the commit-back.
echo x > other.txt && git add other.txt && git commit -q -m "later work"
rc=$(run 0.1.0); [ "$rc" = 1 ] && pass "resume refused when HEAD is not the commit-back" || fail "resume past HEAD ($rc)"

# 4. an existing ## [X.Y.Z] that a human wrote is a hard error.
new_repo
printf '\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- Old.\n' >> CHANGELOG.md
git commit -q -am "hand release"
rc=$(run 0.1.0); [ "$rc" = 1 ] && pass "non-bot ## [X.Y.Z] refused" || fail "non-bot section ($rc)"

# 5. a forged subject and author do not unlock a resume when the commit
#    touches more than the changelog.
new_repo
echo '- **[Issue #9]** Thing.' > changelog.d/9-added.md
bash scripts/collate-changelog.sh --release 0.2.0 >/dev/null
echo evil > payload.txt
git add -A
GIT_AUTHOR_NAME="$BOT" GIT_AUTHOR_EMAIL="$BOT_EMAIL" git commit -q -m "docs: collate CHANGELOG for 0.2.0"
rc=$(run 0.2.0); [ "$rc" = 1 ] && pass "forged commit-back touching other files refused" || fail "forged resume ($rc)"

# 6. nothing pending and an empty [Unreleased]: no empty release.
new_repo
cat > CHANGELOG.md <<'CL'
# Changelog

## [Unreleased]
CL
git commit -q -am "empty unreleased"
base=$(git rev-parse HEAD)
rc=$(run 0.1.0); [ "$rc" = 1 ] && [ "$(git rev-parse HEAD)" = "$base" ] && pass "empty release refused, no commit" || fail "empty release ($rc)"

# 7. malformed fragments fail before anything is touched.
for kind in empty heading symlink; do
  new_repo
  case "$kind" in
    empty) : > changelog.d/10-added.md ;;
    heading) echo '### Added' > changelog.d/10-added.md ;;
    symlink) echo '- **[Issue #10]** Elsewhere.' > "$root/outside.md"; ln -s "$root/outside.md" changelog.d/10-added.md ;;
  esac
  git add -A && git commit -q -m "bad fragment"
  base=$(git rev-parse HEAD)
  before=$(cat CHANGELOG.md)
  rc=$(run 0.1.0)
  [ "$rc" = 1 ] && [ "$(git rev-parse HEAD)" = "$base" ] && [ "$(cat CHANGELOG.md)" = "$before" ] \
    && pass "$kind fragment fails with no commit and CHANGELOG.md untouched" || fail "$kind fragment ($rc)"
done

# 8. a rejected push exits non-zero and reports no release.
new_repo
echo '- **[Issue #11]** Thing.' > changelog.d/11-added.md
git add -A && git commit -q -m "frag" && git push -q origin HEAD:refs/heads/main
printf '#!/bin/sh\necho "rejected by test hook" >&2\nexit 1\n' > "$ORIGIN/hooks/pre-receive"
chmod +x "$ORIGIN/hooks/pre-receive"
origin_before=$(git -C "$ORIGIN" rev-parse refs/heads/main)
: > "$RES"
rc=$(run 0.1.0 --output "$RES")
[ "$rc" = 1 ] && [ "$(git -C "$ORIGIN" rev-parse refs/heads/main)" = "$origin_before" ] && ! grep -q 'release=true' "$RES" \
  && pass "rejected push fails and reports no release" || { fail "rejected push ($rc)"; cat "$OUT"; }

# 9. --no-push commits without touching origin.
new_repo
echo '- **[Issue #12]** Thing.' > changelog.d/12-added.md
git add -A && git commit -q -m "frag" && git push -q origin HEAD:refs/heads/main
origin_before=$(git -C "$ORIGIN" rev-parse refs/heads/main)
rc=$(run 0.1.0 --no-push)
[ "$rc" = 0 ] && [ "$(git log -1 --format=%an)" = "$BOT" ] && [ "$(git -C "$ORIGIN" rev-parse refs/heads/main)" = "$origin_before" ] \
  && pass "--no-push commits only" || fail "--no-push ($rc)"

# 10. --branch pushes to the named branch.
new_repo
echo '- **[Issue #13]** Thing.' > changelog.d/13-added.md
git add -A && git commit -q -m "frag" && git push -q origin HEAD:refs/heads/main HEAD:refs/heads/stable
rc=$(run 0.1.0 --branch stable)
[ "$rc" = 0 ] && [ "$(git -C "$ORIGIN" rev-parse refs/heads/stable)" = "$(git rev-parse HEAD)" ] \
  && pass "--branch pushes to that branch" || fail "--branch ($rc)"

# 11. bad invocations exit 2 and change nothing.
new_repo
base=$(git rev-parse HEAD)
for bad in v1.0.0 01.2.3 1.2 '1.2.3;rm'; do
  rc=$(run "$bad"); [ "$rc" = 2 ] && pass "version $bad rejected" || fail "version $bad accepted ($rc)"
done
rc=$(run); [ "$rc" = 2 ] && pass "missing version exits 2" || fail "missing version ($rc)"
rc=$(run 1.0.0 --bogus); [ "$rc" = 2 ] && pass "unknown flag exits 2" || fail "unknown flag ($rc)"
rc=$(run 1.0.0 2.0.0); [ "$rc" = 2 ] && pass "extra argument exits 2" || fail "extra argument ($rc)"
rc=$(run 1.0.0 --branch 'bad..name'); [ "$rc" = 2 ] && pass "invalid branch exits 2" || fail "invalid branch ($rc)"
[ "$(git rev-parse HEAD)" = "$base" ] && [ -z "$(git status --porcelain)" ] && pass "bad invocations change nothing" || fail "bad invocation side effects"

printf '\n%s test(s), %s failure(s)\n' "$count" "$fails"
[ "$fails" -eq 0 ]
