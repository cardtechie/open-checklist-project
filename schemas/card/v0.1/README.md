# Card Schema v0.1

This schema defines the structure for individual trading card data in the Open Checklist Project.

## Required Fields

### `uuid` (string, UUID format)
Globally unique identifier for this specific card.
```yaml
uuid: "11111111-1111-1111-1111-111111111111"
```

### `number` (string)
The printed card number or identifier as it appears on the card.
```yaml
number: "1"        # Standard numbering
number: "RC-5"     # Rookie card subset
number: "SP-A"     # Special parallel
```

### `genre` (string)
Broad category of the card. Must be one of:
- `Sports` - Athletic/sports cards
- `TCG` - Trading card games (Pokemon, Magic, etc.)
- `Non-Sport` - Entertainment, movies, etc.

```yaml
genre: "Sports"
```

### `subjects` (array)
Array of people, characters, or entities featured on the card. Must contain at least one subject.

**Required subject fields:**
- `name` (string) - Name of the subject

**Optional subject fields:**
- `role` (string) - Role or position (e.g., "Player", "Coach")
- `team` (string) - Team affiliation
- `metadata` (object) - Additional freeform data
- `attacks` (array) - For TCG cards, combat abilities
- `abilities` (array) - For TCG cards, special abilities

```yaml
subjects:
  - name: "Aaron Judge"
    role: "Player" 
    team: "New York Yankees"
  - name: "Giancarlo Stanton"
    role: "Player"
    team: "New York Yankees"
```

### `set_id` (string)
Reference to the set this card belongs to. Must match a set's `set_id` field.
```yaml
set_id: "2023-topps-series-1"
```

## Optional Fields

### Sport Classification
Use `sport` for single-sport cards or `sports` array for multi-sport cards:
```yaml
sport: "Baseball"           # Single sport
# OR
sports: ["Baseball", "Football"]  # Multi-sport
```

Supported sports: Baseball, Basketball, Football, Hockey, Soccer, Golf, Boxing, Wrestling, Tennis, Racing, MMA, Olympics, Cricket, Lacrosse, Pickleball, Bowling

### Card Details
```yaml
card_name: "Aaron Judge - Base"
description: "Base card featuring 2022 AL MVP Aaron Judge"
series: "Series 1"
set_number: "1"
subset: "Base Set"
variation: "Photo Variation"
parallel: "Rainbow Foil"
```

### Card Properties
```yaml
print_run: 50000           # Known print quantity
serial_numbered: true      # Card has serial number
autograph: true           # Card is autographed
relic: true              # Card contains memorabilia
rookie_card: true        # Player's rookie card
```

### Metadata
```yaml
release_date: "2023-03-15"
image_url: "https://example.com/cards/judge-2023.jpg"
external_links:
  - name: "COMC"
    url: "https://comc.com/cards/baseball/..."
metadata:
  hall_of_fame: true
  mvp_years: [2022]
```

## TCG-Specific Fields

For Trading Card Game cards, subjects can include game mechanics:

```yaml
subjects:
  - name: "Pikachu"
    attacks:
      - name: "Thunder Shock"
        damage: "20"
        cost: ["Electric"]
      - name: "Agility" 
        damage: "0"
        cost: ["Colorless"]
    abilities:
      - name: "Static"
        description: "If this Pokémon is your Active Pokémon..."
```

## Complete Example

```yaml
uuid: "11111111-1111-1111-1111-111111111111"
number: "1"
genre: "Sports"
sport: "Baseball"
set_id: "2023-topps-series-1"
subjects:
  - name: "Aaron Judge"
    role: "Player"
    team: "New York Yankees"
card_name: "Aaron Judge - Base"
description: "Base card featuring 2022 AL MVP Aaron Judge"
series: "Series 1"
rookie_card: false
autograph: false
serial_numbered: false
release_date: "2023-03-15"
image_url: "https://example.com/cards/judge-2023.jpg"
```