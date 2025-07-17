# Set Schema v0.2

This schema defines the structure for trading card set metadata in the Open Checklist Project.

## Required Fields

### `uuid` (string, UUID format)
Globally unique identifier for this set (UUID v4).
```yaml
uuid: "64532873-a2d3-4d78-ab91-fe9af8410def"
```

### `set_id` (string)
Unique identifier for the set, typically following a consistent naming pattern.
```yaml
set_id: "2023-topps-series-1"
set_id: "2024-pokemon-sv4"
set_id: "1993-topps-gold"
```

### `name` (string)
Official name of the set as marketed by the manufacturer.
```yaml
name: "Topps Series 1"
name: "Pokemon Scarlet & Violet - Paradox Rift"
```

### `genre` (string)
Broad category of the set. Must be one of:
- `Sports` - Athletic/sports cards
- `TCG` - Trading card games
- `Non-Sport` - Entertainment, movies, etc.

```yaml
genre: "Sports"
```

### `category` (array)
One or more categories describing the set's subject matter, franchise, or league.
```yaml
category: ["MLB"]                    # Major League Baseball
category: ["Pokemon"]                # Pokemon TCG
category: ["Star Wars", "Movies"]    # Multi-category
category: ["Olympics", "Multi-Sport"] # Olympic cards
```

## Optional Fields

### Sport Classification
For sports sets, specify which sports are covered:
```yaml
sports: ["Baseball"]                 # Single sport
sports: ["Baseball", "Football"]     # Multi-sport set
```

Supported sports: Baseball, Basketball, Football, Hockey, Soccer, Golf, Boxing, Wrestling, Tennis, Racing, MMA, Olympics, Cricket, Lacrosse, Pickleball, Bowling

### Temporal Information
```yaml
season: "2023"        # Single year
season: "2021-22"     # Multi-year season
years: [2023]         # Years covered by set
years: [2021, 2022]   # Multi-year coverage
```

### Set Relationships
```yaml
parallel: true        # This is a parallel version of another set
insert: true         # This is an insert/chase set
base_set: "uuid-of-base-set"  # UUID reference to base set
```

### Set Properties
```yaml
autograph: true      # Set consists primarily of autographed cards
relic: true         # Set consists primarily of memorabilia cards
```

### Series Information
```yaml
series: "2023 Topps Baseball"     # Umbrella series name
series_number: 1                  # Sequential number (Series 1, 2, etc.)
```

### Production Details
```yaml
release_date: "2023-03-15"
manufacturer: "Topps"
card_count: 330                   # Total cards in set
print_run: 5000000               # Known production quantity
```

### Additional Metadata
```yaml
subset: "Base Set"
description: "2023 Topps Series 1 baseball release with rookies and inserts"
image_url: "https://example.com/images/2023-topps-series-1.jpg"
metadata:
  language: "en"
  year: 2023
  hobby_exclusive: false
```

## Set Type Examples

### Base Sports Set
```yaml
uuid: "64532873-a2d3-4d78-ab91-fe9af8410def"
set_id: "2023-topps-series-1"
name: "Topps Series 1"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
season: "2023"
years: [2023]
series: "2023 Topps Baseball"
series_number: 1
release_date: "2023-03-15"
manufacturer: "Topps"
card_count: 330
```

### Parallel Set
```yaml
uuid: "another-uuid-here"
set_id: "2023-topps-series-1-gold"
name: "Topps Series 1 Gold Parallel"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
parallel: true
base_set: "64532873-a2d3-4d78-ab91-fe9af8410def"
series: "2023 Topps Baseball"
card_count: 330
```

### Insert Set
```yaml
uuid: "insert-uuid-here"
set_id: "2023-topps-chrome-rookie-autographs"
name: "Chrome Rookie Autographs"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
insert: true
autograph: true
base_set: "64532873-a2d3-4d78-ab91-fe9af8410def"
card_count: 50
```

### TCG Set
```yaml
uuid: "tcg-uuid-here"
set_id: "2024-pokemon-sv4"
name: "Scarlet & Violet - Paradox Rift"
genre: "TCG"
category: ["Pokemon"]
series: "Scarlet & Violet"
series_number: 4
release_date: "2024-11-03"
manufacturer: "Pokemon Company"
card_count: 266
```

## Validation Notes

- `genre` and `category` are required fields as of v0.2
- If `parallel: true` or `insert: true`, consider including `base_set` UUID
- For sports sets, include relevant `sports` array
- `years` array should match the temporal scope indicated by `season`
- `card_count` helps with set completion tracking