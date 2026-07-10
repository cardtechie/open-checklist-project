# Set Schema v0.3 (manifest form)

In the v0.3 manifest form, `set.yaml` is **purely descriptive product / umbrella
metadata**. All structure — base sets, subsets, parallels, sections — moved to
`manifest.yaml`, and card identities to `checklists/`. This schema no longer carries
`card_count`, the `parallel` / `insert` / `autograph` / `relic` / `base_set` / `subset`
flags, or a set-level `print_run`; those are expressed (or derived) in the manifest.

## Required Fields

- **`uuid`** — canonical identity of the **product / umbrella** (UUID v4). One product
  may hold several base sets, each of which carries its own `uuid` in `manifest.yaml`;
  this is the umbrella above them.
- **`set_id`** — stable slug; matches `manifest.yaml` and the data directory name.
- **`name`** — official product name.
- **`genre`** — `Sports` | `TCG` | `Non-Sport`.
- **`category`** — one or more subject/franchise/league tags (e.g. `["MLB"]`).
- **`source`** — attribution: `{ name, url, file? }`.

## Optional Fields

`sports`, `season`, `years`, `series` + `series_number` (for products that split into
Series 1 / 2 — omit for single-release sets), `manufacturer`, `release_date`,
`description`, `image_url` (real URLs only — never fabricated placeholders), and a
freeform `metadata` object.

## Example

```yaml
uuid: "454adae3-692f-42e6-8f6a-459079498348"
set_id: "2026-topps-series-2"
name: "2026 Topps Series 2"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
season: "2026"
years: [2026]
series: "2026 Topps Baseball"
series_number: 2
manufacturer: "Topps"
release_date: "2026-06-11"
source:
  name: "BaseballCardpedia"
  url: "https://baseballcardpedia.com/index.php/2026_Topps#Checklist"
```

## Migrating from v0.2

Removed / relocated:

- `card_count` → derived from the manifest expansion (checked by the review report).
- `parallel` / `insert` / `autograph` / `relic` → `manifest.yaml` subset `type` (a list)
  and `parallels`.
- `base_set` / `subset` → the manifest's `base_sets[]` / nested `subsets[]` structure.
- set-level `print_run` → per-parallel `print_run` in the manifest.
