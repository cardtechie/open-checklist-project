# Schemas

This directory contains YAML schemas for the Open Checklist Project data structures.

## Current Versions

- **Card Schema**: v0.1 ([`card/schema.yaml`](card/schema.yaml)) - [Documentation](card/README.md)
- **Set Schema**: v0.2 ([`set/schema.yaml`](set/schema.yaml)) - [Documentation](set/README.md)

## Directory Structure

```
schemas/
├── card/
│   ├── schema.yaml      # Symlink to latest version
│   ├── README.md        # Latest documentation
│   ├── CHANGELOG.md     # Version history
│   └── v0.1/           # Version-specific files
│       ├── schema.yaml
│       └── README.md
└── set/
    ├── schema.yaml      # Symlink to latest version
    ├── README.md        # Latest documentation  
    ├── CHANGELOG.md     # Version history
    ├── v0.1/           # Initial version
    │   ├── schema.yaml
    │   └── README.md
    └── v0.2/           # Current version
        ├── schema.yaml
        └── README.md
```

## Versioning

Each schema maintains independent versioning:
- **Breaking changes** increment the major version (v0.1 → v1.0)
- **New optional fields** increment the minor version (v0.1 → v0.2)
- **Documentation updates** don't change the schema version

## Using Schemas

### For Validation
The validation script automatically uses the latest versions via symlinks:
```bash
python tools/validate.py
```

### For Specific Versions
Reference version-specific schemas for backward compatibility:
```python
# Load specific version
schema = load_schema("schemas/set/v0.1/schema.yaml")
```

### Migration
When schemas change, existing data may need migration:
1. Check the CHANGELOG.md for breaking changes
2. Use version-specific documentation for field mappings
3. Update data files to match new required fields

## Version History

### Card Schema ([changelog](card/CHANGELOG.md))
- **v0.1** ([schema](card/v0.1/schema.yaml), [documentation](card/v0.1/README.md)) - Initial release with core card fields

### Set Schema ([changelog](set/CHANGELOG.md))
- **v0.2** ([schema](set/v0.2/schema.yaml), [documentation](set/v0.2/README.md)) - Added required `genre` and `category` fields, enhanced temporal handling
- **v0.1** ([schema](set/v0.1/schema.yaml), [documentation](set/v0.1/README.md)) - Initial basic set structure

---

# Detailed Schema Documentation

## Architecture

The schemas follow a hierarchical relationship where:
- **Sets** represent collections of trading cards (e.g., "2023 Topps Baseball Series 1")
- **Cards** belong to sets and reference them via `set_id`
- **Sets** can reference other sets via `base_set` for parallels and inserts

## Set Schema (v0.2)

### Purpose
Defines the structure for trading card set objects across all genres including Sports, Trading Card Games (TCG), and Non-Sport entertainment cards.

### Required Fields

#### `uuid` (string, UUID format)
Globally unique identifier for the set using UUID v4 format.
- **Purpose**: Ensures unique identification across all systems
- **Example**: `"550e8400-e29b-41d4-a716-446655440000"`

#### `set_id` (string)
Human-readable unique identifier for the set.
- **Purpose**: User-friendly reference for the set
- **Format**: Typically follows pattern like "year-manufacturer-product"
- **Example**: `"2023-topps-baseball-series1"`

#### `name` (string)
Official name of the trading card set.
- **Purpose**: Display name used by collectors and manufacturers
- **Example**: `"2023 Topps Baseball Series 1"`

#### `genre` (string, enum)
Broad categorization of the card set type.
- **Values**: `Sports`, `TCG`, `Non-Sport`
- **Purpose**: Top-level classification for filtering and organization
- **Examples**: 
  - Sports: Baseball, Basketball, Football cards
  - TCG: Pokemon, Magic: The Gathering, Yu-Gi-Oh
  - Non-Sport: Star Wars, Marvel, Disney

#### `category` (array of strings)
Specific categories that describe the set's subject matter, franchise, or league.
- **Purpose**: Granular grouping beyond genre (e.g., specific leagues, franchises)
- **Min Items**: 1
- **Examples**:
  - Sports: `["MLB"]`, `["NBA"]`, `["Olympics"]`
  - TCG: `["Pokemon"]`, `["Magic: The Gathering"]`
  - Non-Sport: `["Star Wars"]`, `["Marvel"]`, `["Disney"]`

### Optional Fields

#### `sports` (array of strings, enum)
Specific sports covered by the set (used when genre is Sports).
- **Purpose**: Identifies actual sports disciplines, especially for multi-sport sets
- **Available Values**: Baseball, Basketball, Football, Hockey, Soccer, Golf, Boxing, Wrestling, Tennis, Racing, MMA, Olympics, Cricket, Lacrosse, Pickleball, Bowling
- **Examples**:
  - Single sport: `["Baseball"]`
  - Olympics set: `["Swimming", "Track", "Gymnastics"]`
  - Multi-sport: `["Baseball", "Basketball", "Football"]`

#### `season` (string)
Official season designation for the set.
- **Purpose**: Captures season information, especially for sports that span multiple years
- **Examples**: `"2021-22"`, `"2023"`, `"2020-21"`

#### `years` (array of integers)
All years the set covers, with validation bounds of 1800-2030.
- **Purpose**: Enables year-based searching across season boundaries
- **Examples**:
  - Single year: `[2023]`
  - Multi-year season: `[2021, 2022]`

#### `card_count` (integer, minimum: 1)
Total number of cards in the set.
- **Purpose**: Essential for completion tracking and set validation
- **Note**: Optional in case count is unknown for vintage or incomplete sets

#### Boolean Characteristics

##### `parallel` (boolean)
True if this set is a parallel version of a base set.
- **Purpose**: Identifies sets with different foiling, colors, or numbering of base cards
- **Example**: "2023 Topps Chrome Baseball" as parallel to "2023 Topps Baseball"

##### `insert` (boolean)
True if this set consists primarily of insert/chase cards.
- **Purpose**: Identifies special cards found within base set products
- **Example**: "1993 SP Foil" inserts within regular packs

##### `autograph` (boolean)
True if this set consists primarily of autographed cards.
- **Purpose**: Identifies signature card sets
- **Example**: "2023 Topps Five Star Autographs"

##### `relic` (boolean)
True if this set consists primarily of memorabilia/relic cards.
- **Purpose**: Identifies game-used memorabilia card sets
- **Example**: "2023 Museum Collection Relics"

#### Relationship Fields

##### `base_set` (string, UUID format)
UUID reference to the base set for parallel and insert sets.
- **Purpose**: Establishes hierarchical relationships between sets
- **Note**: Optional to allow for cases where base set is not yet defined
- **Example**: Chrome parallel references the base Topps set

##### `series` (string)
Series or umbrella grouping the set belongs to.
- **Purpose**: Groups related sets under common product line
- **Examples**: `"2024 Topps Baseball"`, `"Pokemon Scarlet & Violet"`

##### `series_number` (integer, minimum: 1)
Sequential number within the series.
- **Purpose**: Indicates ordering within a series
- **Examples**: `1` for Series 1, `2` for Series 2

#### Additional Information

##### `release_date` (string, date format)
Official release date of the set in YYYY-MM-DD format.

##### `manufacturer` (string)
Company that produced the set.
- **Examples**: `"Topps"`, `"Panini"`, `"Upper Deck"`, `"Pokemon Company"`

##### `print_run` (integer, minimum: 0)
Known print run quantity for the set.
- **Purpose**: Indicates rarity and production scale

##### `subset` (string)
Subset or insert group name.
- **Purpose**: Further categorization within sets

##### `description` (string)
Human-readable summary of the set.

##### `image_url` (string, URI format)
URL for a set logo or representative image.

##### `metadata` (object)
Freeform key-value metadata for additional set information.
- **Purpose**: Extensibility for future requirements or custom data

## Card Schema (v0.1)

### Purpose
Defines the structure for individual trading card objects that belong to sets.

### Required Fields

#### `uuid` (string, UUID format)
Unique identifier for the individual card.

#### `number` (string)
Printed card number or identifier as it appears on the card.

#### `genre` (string, enum)
Must match the parent set's genre: `Sports`, `TCG`, `Non-Sport`.

#### `subjects` (array of objects, minimum: 1)
People, characters, or entities featured on the card.
- **Required Properties**: `name`
- **Optional Properties**: `role`, `team`, `metadata`, `attacks`, `abilities`
- **Purpose**: Captures who/what is depicted on the card

#### `set_id` (string)
Reference to the set this card belongs to.
- **Purpose**: Establishes parent-child relationship with sets

### Optional Fields

The card schema includes many optional fields for specific card types:
- **Sports-specific**: `sport`, `sports`, `rookie_card`
- **TCG-specific**: `attacks`, `abilities` (within subjects)
- **Collectible features**: `autograph`, `relic`, `serial_numbered`
- **Variations**: `variation`, `parallel`, `print_run`
- **Metadata**: `description`, `image_url`, `external_links`, `metadata`

## Usage Examples

### Basic Sports Set
```yaml
uuid: "550e8400-e29b-41d4-a716-446655440000"
set_id: "2023-topps-baseball-series1"
name: "2023 Topps Baseball Series 1"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
season: "2023"
years: [2023]
card_count: 330
series: "2023 Topps Baseball"
series_number: 1
manufacturer: "Topps"
```

### Multi-Year Sports Set
```yaml
uuid: "550e8400-e29b-41d4-a716-446655440001"
set_id: "2021-22-upper-deck-series1"
name: "2021-22 Upper Deck Series 1"
genre: "Sports"
category: ["NHL"]
sports: ["Hockey"]
season: "2021-22"
years: [2021, 2022]
card_count: 250
manufacturer: "Upper Deck"
```

### TCG Set
```yaml
uuid: "550e8400-e29b-41d4-a716-446655440002"
set_id: "pokemon-scarlet-violet-base"
name: "Pokemon Scarlet & Violet Base Set"
genre: "TCG"
category: ["Pokemon"]
card_count: 198
series: "Pokemon Scarlet & Violet"
series_number: 1
manufacturer: "Pokemon Company"
```

### Parallel Set
```yaml
uuid: "550e8400-e29b-41d4-a716-446655440003"
set_id: "2023-topps-chrome-baseball"
name: "2023 Topps Chrome Baseball"
genre: "Sports"
category: ["MLB"]
sports: ["Baseball"]
parallel: true
base_set: "550e8400-e29b-41d4-a716-446655440000"
card_count: 330
manufacturer: "Topps"
```

## Data Validation

### Schema Validation
Both schemas use JSON Schema validation with:
- Type checking (string, integer, boolean, array, object)
- Format validation (UUID, date, URI)
- Enumeration constraints for controlled vocabularies
- Range validation for numeric fields
- Required field enforcement

### Application-Level Validation
Additional validation should be implemented at the application level:
- Referential integrity (set_id references valid sets)
- Circular reference prevention (base_set cannot reference self)
- Cross-field validation (sports field only when genre is Sports)

## Integration Guidelines

### Database Design
- Use UUIDs as primary keys for both sets and cards
- Index frequently queried fields: genre, category, sports, years
- Consider denormalization for read-heavy workloads

### API Design
- Support filtering by genre, category, sports, years
- Enable relationship traversal (cards ↔ sets, base_set ↔ parallels)
- Implement pagination for large result sets

### Data Migration
- Optional fields allow gradual data population
- Schema versioning enables backward compatibility
- Metadata fields provide escape hatches for unforeseen requirements

## Future Considerations

Future schema versions may include:
- Language and region fields for international releases
- Status fields for availability tracking
- Box configuration details
- Pricing information
- Enhanced relationship modeling

For questions or contributions, please refer to the main Open Checklist Project repository.