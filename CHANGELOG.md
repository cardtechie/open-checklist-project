# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed

- **[Issue #80]** Make the validate check report on every pull request and run on merge-queue groups.

## [0.1.0] - 2026-10-17

### Added

- **[Issue #82]** Adopt semantic versioning with a changelog-driven release workflow and document the bump rules.
- **[Issue #88]** Run the work-order.js node tests in CI.
- **[Issue #78]** Add Stage A Discover: backfill work-order identity (reusing an existing API set UUID) and post the Discover block so a work order passes the producer precondition check.
- **[Issue #65]** Add the Stage A producer contract, a work-order precondition checker and the produce-set skill for unattended Source→Normalize.
