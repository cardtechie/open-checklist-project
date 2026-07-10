## [v0.3] - 2026-07-09
- Manifest form: set.yaml is now purely descriptive product / umbrella metadata.
- `uuid` is the product/umbrella id; each base set carries its own uuid in manifest.yaml.
- Made `source` (name + url) required; source attribution is no longer only in metadata.
- Removed `card_count` (now derived from the manifest expansion).
- Removed the `parallel` / `insert` / `autograph` / `relic` flags and `base_set` /
  `subset` (now expressed by manifest subsets' `type` list + `parallels`, and the
  base_sets/subsets structure).
- Removed set-level `print_run` (now per-parallel in the manifest).
- Structure/parallels/checklists moved to manifest.yaml + checklists/.

## [v0.2] - 2025-07-17
- Added card_count for set completeness tracking
- Added genre, category, and sports for comprehensive categorization
- Added season and years for flexible temporal handling
- Added boolean flags: parallel, insert, autograph, relic
- Added base_set UUID reference for relationships
- Added series_number for multi-series organization
- Made genre and category required fields

## [v0.1] - 2025-06-22
- Initial release of set schema
- Basic set metadata support (uuid, set_id, name)
- Release date and manufacturer fields
- Optional metadata object for extensibility