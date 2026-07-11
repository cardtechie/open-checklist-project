> **DEPRECATED (2026-07-11)** — the exploded one-file-per-card format is superseded by
> the v0.3 manifest form (manifest + checklist schemas). Retained only to validate
> not-yet-migrated exploded data; removed once migration completes. Tracking: #33.

## [v0.1] - 2025-06-22
- Initial release of card schema
- Added support for sports and TCG genres
- Required fields: uuid, number, genre, subjects, set_id
- Support for multiple subjects per card with name, role, team metadata
- Optional fields for card details (description, series, variation, etc.)
- Support for TCG-specific fields (attacks, abilities)
- Boolean flags for special card types (autograph, relic, rookie_card, etc.)