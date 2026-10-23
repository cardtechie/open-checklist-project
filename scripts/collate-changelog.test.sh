#!/usr/bin/env bash
#
# Tests for scripts/collate-changelog.sh. Runs the collator against throwaway
# git repos, so it never touches this repo's CHANGELOG.md or changelog.d/.
#
# Usage: bash scripts/collate-changelog.test.sh

set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/collate-changelog.sh"
fails=0
count=0

pass() { count=$((count + 1)); printf 'ok   %s\n' "$1"; }
fail() { count=$((count + 1)); fails=$((fails + 1)); printf 'FAIL %s\n' "$1"; }

# new_repo: make a fixture repo with the current CHANGELOG shape; cd into it.
new_repo() {
  dir=$(mktemp -d)
  cd "$dir" || exit 1
  git init -q .
  mkdir -p scripts changelog.d
  cp "$SRC" scripts/collate-changelog.sh
  cat > CHANGELOG.md <<'CL'
# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- **[Issue #2]** Second entry.
- **[Issue #1]** First entry.
CL
}

run() { bash scripts/collate-changelog.sh "$@" >"$OUT" 2>&1; echo $?; }
OUT=$(mktemp)

# 1. collate appends under the matching subsection, in ascending issue order.
new_repo
echo '- **[Issue #20]** Later.' > changelog.d/20-added.md
echo '- **[Issue #10]** Earlier.' > changelog.d/10-added.md
rc=$(run)
expected=$(cat <<'CL'
# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- **[Issue #2]** Second entry.
- **[Issue #1]** First entry.
- **[Issue #10]** Earlier.
- **[Issue #20]** Later.
CL
)
[ "$rc" = 0 ] && [ "$(cat CHANGELOG.md)" = "$expected" ] && pass "appends in ascending order, existing lines untouched" || fail "append layout"
[ ! -e changelog.d/10-added.md ] && [ ! -e changelog.d/20-added.md ] && pass "consumed fragments are deleted" || fail "fragments deleted"

# 2. repeat collation is a no-op.
before=$(cat CHANGELOG.md)
rc=$(run)
[ "$rc" = 0 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && pass "repeat collation changes nothing" || fail "repeat collation"

# 3. new subsection is created in Keep-a-Changelog order.
new_repo
echo '- **[Issue #5]** Fix it.' > changelog.d/5-fixed.md
echo '- **[Issue #6]** Change it.' > changelog.d/6-changed.md
rc=$(run)
order=$(grep '^### ' CHANGELOG.md | tr '\n' ' ')
[ "$rc" = 0 ] && [ "$order" = "### Added ### Changed ### Fixed " ] && pass "new subsections created in order" || fail "subsection order ($order)"

# 4. released sections after [Unreleased] are preserved verbatim.
new_repo
printf '\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- Old thing.\n' >> CHANGELOG.md
echo '- **[Issue #7]** New.' > changelog.d/7-added.md
rc=$(run)
tail -n 5 CHANGELOG.md | grep -q -- '- Old thing.' && grep -q '^## \[1.0.0\] - 2026-01-01$' CHANGELOG.md \
  && [ "$(grep -c '^## ' CHANGELOG.md)" = 2 ] && [ "$rc" = 0 ] && pass "released sections preserved" || fail "released sections"

# 5. no [Unreleased] section: one is created before the first section.
new_repo
printf '# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- Old.\n' > CHANGELOG.md
echo '- **[Issue #8]** New.' > changelog.d/8-added.md
rc=$(run)
[ "$rc" = 0 ] && [ "$(grep '^## ' CHANGELOG.md | head -1)" = "## [Unreleased]" ] && pass "creates [Unreleased] when absent" || fail "create [Unreleased]"

# 6. --check validates without writing.
new_repo
echo '- **[Issue #9]** Entry.' > changelog.d/9-added.md
before=$(cat CHANGELOG.md)
rc=$(run --check)
[ "$rc" = 0 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && [ -e changelog.d/9-added.md ] && pass "--check writes nothing" || fail "--check"

# 7. bad names fail --check and collation, and consume nothing.
new_repo
echo '- **[Issue #9]** Entry.' > changelog.d/9-added.md
echo 'x' > changelog.d/oops.md
rc=$(run --check); [ "$rc" = 1 ] && pass "--check rejects a misnamed fragment" || fail "--check bad name"
rc=$(run); [ "$rc" = 1 ] && [ -e changelog.d/9-added.md ] && pass "collation rejects a misnamed fragment and consumes nothing" || fail "collate bad name"

# 8. unknown type is rejected.
new_repo
echo 'x' > changelog.d/3-improved.md
rc=$(run --check); [ "$rc" = 1 ] && pass "unknown type rejected" || fail "unknown type"

# 9. empty body is rejected.
new_repo
printf '\n\n' > changelog.d/4-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "empty body rejected" || fail "empty body"

# 10. symlinked fragment is rejected.
new_repo
echo 'x' > target.txt
ln -s ../target.txt changelog.d/4-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "symlinked fragment rejected" || fail "symlinked fragment"

# 11. symlinked changelog.d is rejected.
new_repo
rm -rf changelog.d; mkdir real; ln -s real changelog.d
rc=$(run --check); [ "$rc" = 1 ] && pass "symlinked changelog.d rejected" || fail "symlinked changelog.d"

# 12. bookkeeping files are ignored; no fragments is a clean no-op.
new_repo
echo '# readme' > changelog.d/README.md
touch changelog.d/.gitkeep
rc=$(run); [ "$rc" = 0 ] && grep -q 'no pending fragments' "$OUT" && pass "bookkeeping ignored, nothing pending" || fail "bookkeeping"

# 13. hand-edited [Unreleased] with an unknown subheading is refused.
new_repo
printf '\n### Misc\n\n- Hand edit.\n' >> CHANGELOG.md
echo '- **[Issue #3]** New.' > changelog.d/3-added.md
rc=$(run); [ "$rc" = 1 ] && [ -e changelog.d/3-added.md ] && pass "unrecognised subheading refused, fragment kept" || fail "unknown subheading"

# 14. bad invocation exits 2.
new_repo
rc=$(run --bogus); [ "$rc" = 2 ] && pass "unknown argument exits 2" || fail "bad invocation"

# 15. a fragment body that is not a bullet is rejected and kept.
new_repo
printf '### Misc\n\n- **[Issue #4]** Heading first.\n' > changelog.d/4-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "heading-bearing fragment rejected" || fail "heading fragment"
new_repo
printf -- '- **[Issue #5]** Fine.\n### Misc\n' > changelog.d/5-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "heading after a bullet rejected" || fail "heading after bullet"
new_repo
printf 'Loose prose.\n' > changelog.d/6-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "prose-only fragment rejected" || fail "prose fragment"

# 16. bullet with indented sub-bullets and continuation is accepted.
new_repo
printf -- '- **[Issue #7]** Main line.\n  - Caveat.\n    continued.\n' > changelog.d/7-changed.md
rc=$(run --check); [ "$rc" = 0 ] && pass "bullet with sub-bullets accepted" || fail "sub-bullets"

# 17. a hand-edited subheading with extra text is refused, not rewritten.
new_repo
sed -i.bak 's/^### Added$/### Added (2026)/' CHANGELOG.md && rm -f CHANGELOG.md.bak
echo '- **[Issue #8]** New.' > changelog.d/8-added.md
rc=$(run); [ "$rc" = 1 ] && [ -e changelog.d/8-added.md ] && pass "decorated subheading refused, fragment kept" || fail "decorated subheading"

# 18. a top-level bullet without the issue prefix is rejected, even after a valid one.
new_repo
printf -- '- **[Issue #9]** Valid.\n- not an issue entry\n' > changelog.d/9-added.md
rc=$(run --check); [ "$rc" = 1 ] && pass "top-level bullet without issue prefix rejected" || fail "unprefixed bullet"

# 19. --release collates pending fragments and cuts the version below an empty [Unreleased].
new_repo
printf '\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- Old thing.\n' >> CHANGELOG.md
echo '- **[Issue #30]** Fix it.' > changelog.d/30-fixed.md
rc=$(RELEASE_DATE=2026-10-23 run --release 0.2.0)
expected=$(cat <<'CL'
# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.2.0] - 2026-10-23

### Added

- **[Issue #2]** Second entry.
- **[Issue #1]** First entry.

### Fixed

- **[Issue #30]** Fix it.

## [0.1.0] - 2026-01-01

### Added

- Old thing.
CL
)
[ "$rc" = 0 ] && [ "$(cat CHANGELOG.md)" = "$expected" ] && [ ! -e changelog.d/30-fixed.md ] \
  && pass "--release collates and cuts the version under an empty [Unreleased]" || fail "--release layout"

# 20. the cut version is the first bracketed heading, the one release.yml selects.
first=$(sed -nE 's/^## \[([^]]+)\].*/\1/p' CHANGELOG.md | grep -v '^Unreleased$' | head -n 1)
[ "$first" = "0.2.0" ] && pass "release.yml would select the cut version" || fail "first version ($first)"

# 21. collating after a release fills the fresh [Unreleased] and leaves the release alone.
echo '- **[Issue #31]** Next.' > changelog.d/31-added.md
rc=$(run)
[ "$rc" = 0 ] && [ "$(sed -n '5,9p' CHANGELOG.md)" = "$(printf '## [Unreleased]\n\n### Added\n\n- **[Issue #31]** Next.')" ] \
  && grep -q '^## \[0.2.0\] - 2026-10-23$' CHANGELOG.md && pass "post-release collation lands in the new [Unreleased]" || fail "post-release collation"

# 22. --release with nothing pending versions what is already under [Unreleased].
new_repo
rc=$(RELEASE_DATE=2026-10-23 run --release 0.1.0)
[ "$rc" = 0 ] && grep -q '^## \[0.1.0\] - 2026-10-23$' CHANGELOG.md && pass "--release with no pending fragments versions [Unreleased]" || fail "--release no pending"

# 23. --release refuses an empty release, an existing version, and a bad version.
new_repo
printf '# Changelog\n\n## [Unreleased]\n' > CHANGELOG.md
before=$(cat CHANGELOG.md)
rc=$(run --release 0.1.0); [ "$rc" = 1 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && pass "--release refuses an empty release" || fail "empty release"
new_repo
printf '\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- Old thing.\n' >> CHANGELOG.md
echo '- **[Issue #32]** New.' > changelog.d/32-added.md
rc=$(run --release 0.1.0); [ "$rc" = 1 ] && [ -e changelog.d/32-added.md ] && pass "--release refuses an existing version and consumes nothing" || fail "existing version"
new_repo
printf '\n## [0.2.0] - 2026-02-01\n\n### Added\n\n- Newer.\n\n## [0.10.0] - 2026-01-01\n\n### Added\n\n- Odd order.\n' >> CHANGELOG.md
before=$(cat CHANGELOG.md)
rc=$(run --release 0.1.1); [ "$rc" = 1 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && pass "--release refuses an older version" || fail "older version"
rc=$(run --release 0.9.0); [ "$rc" = 1 ] && pass "--release compares numerically against every version, not just the first" || fail "numeric compare"
rc=$(RELEASE_DATE=2026-10-23 run --release 0.10.1); [ "$rc" = 0 ] && grep -q '^## \[0.10.1\] - 2026-10-23$' CHANGELOG.md && pass "--release accepts a newer version" || fail "newer version"
new_repo
printf '\n## [999999999999999999999.0.0] - 2026-01-01\n\n### Added\n\n- Huge.\n' >> CHANGELOG.md
rc=$(run --release 1.0.0); [ "$rc" = 1 ] && pass "--release compares components wider than a bash integer" || fail "huge component"
rc=$(RELEASE_DATE=2026-10-23 run --release 1000000000000000000000.0.0); [ "$rc" = 0 ] && pass "--release accepts a newer huge version" || fail "huge newer"
new_repo
printf '# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- Old.\n\n## [Unreleased]\n\n### Added\n\n- **[Issue #1]** New.\n' > CHANGELOG.md
before=$(cat CHANGELOG.md)
rc=$(run --release 0.2.0); [ "$rc" = 1 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && pass "--release refuses a versioned section above [Unreleased]" || fail "section above [Unreleased]"
new_repo
for d in 2026-99-99 2026-02-29 2026-04-31 2026-00-10; do
  rc=$(RELEASE_DATE=$d run --release 1.0.0); [ "$rc" = 2 ] && pass "RELEASE_DATE $d rejected" || fail "RELEASE_DATE $d accepted"
done
rc=$(RELEASE_DATE=2028-02-29 run --release 1.0.0); [ "$rc" = 0 ] && pass "leap-day RELEASE_DATE accepted" || fail "leap day"
new_repo
rmdir changelog.d
rc=$(RELEASE_DATE=2026-10-23 run --release 0.1.0)
[ "$rc" = 0 ] && grep -q '^## \[0.1.0\] - 2026-10-23$' CHANGELOG.md && pass "--release versions [Unreleased] when changelog.d/ is absent" || fail "--release without changelog.d"
new_repo
rmdir changelog.d
before=$(cat CHANGELOG.md)
rc=$(run); [ "$rc" = 0 ] && [ "$(cat CHANGELOG.md)" = "$before" ] && pass "plain collation without changelog.d/ is still a no-op" || fail "plain without changelog.d"
for bad in v1.0.0 01.2.3 1.2; do
  rc=$(run --release "$bad"); [ "$rc" = 2 ] && pass "--release rejects $bad" || fail "--release accepted $bad"
done
rc=$(run --release); [ "$rc" = 2 ] && pass "--release without a version exits 2" || fail "--release missing version"
rc=$(RELEASE_DATE=tomorrow run --release 1.0.0); [ "$rc" = 2 ] && pass "bad RELEASE_DATE exits 2" || fail "bad RELEASE_DATE"

printf '\n%s test(s), %s failure(s)\n' "$count" "$fails"
[ "$fails" -eq 0 ]
