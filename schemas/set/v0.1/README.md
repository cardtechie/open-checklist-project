# Set Schema v0.1

This schema defines the basic structure for trading card set metadata in the Open Checklist Project.

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

## Optional Fields

### Series Information
```yaml
series: "2023 Topps Baseball"     # Umbrella series name
```

### Production Details
```yaml
release_date: "2023-03-15"
manufacturer: "Topps"
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
```

## Complete Example

```yaml
uuid: "64532873-a2d3-4d78-ab91-fe9af8410def"
set_id: "2023-topps-series-1"
name: "Topps Series 1"
series: "MLB"
release_date: "2023-03-15"
manufacturer: "Topps"
print_run: 5000000
subset: "Base Set"
description: "2023 Topps Series 1 baseball release with rookies and inserts"
image_url: "https://example.com/images/2023-topps-series-1.jpg"
metadata:
  language: "en"
  year: 2023
```

## Migration to v0.2

v0.2 adds required fields for better categorization:
- `genre` and `category` are now required
- Added `sports`, `season`, `years` for temporal handling
- Added boolean flags for set types (`parallel`, `insert`, etc.)
- See v0.2 documentation for details