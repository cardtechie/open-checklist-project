# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Open Checklist Project is an open-data initiative providing standardized trading card checklist data. The project consists of:

- **YAML schemas** for cards and sets (in `schemas/`)
- **Curated data** organized by genre/sport/set (in `data/`)
- **Validation tools** to ensure data compliance
- **GitHub workflows** for automated validation

## Data Validation

### Running Validation

```bash
# Using Docker (recommended)
docker build -t open-checklist-validator .
docker run open-checklist-validator

# Using Python directly
pip install pyyaml jsonschema
python tools/validate.py
```

### Schema Versions

- Card schema: v0.1 (`schemas/card/schema.yaml` → `schemas/card/v0.1/schema.yaml`)
- Set schema: v0.2 (`schemas/set/schema.yaml` → `schemas/set/v0.2/schema.yaml`)
- Previous versions available in `schemas/{type}/v{version}/` directories
- Schema changes documented in respective `schemas/{type}/CHANGELOG.md` files

## Architecture

### Data Structure
```
data/
└── {genre}/                    # Sports, TCG, Non-Sport
    └── {set-identifier}/       # e.g., 2023-topps-series-1
        ├── set.yaml           # Set metadata (required fields: uuid, set_id, name, genre, category)
        └── cards/             # Individual card files
            └── {number}.yaml  # Card data (required fields: uuid, number, genre, subjects, set_id)
```

### Schema Requirements

**Set Schema (v0.2) - Required Fields:**
- `uuid`, `set_id`, `name`, `genre`, `category`
- `genre`: enum ["Sports", "TCG", "Non-Sport"]
- `category`: array of strings (e.g., ["MLB"])

**Card Schema (v0.1) - Required Fields:**
- `uuid`, `number`, `genre`, `subjects`, `set_id`
- `subjects`: array with at least one object containing `name`

### Validation Process

The validation script (`tools/validate.py`):
1. Loads schemas from `schemas/` directory
2. Validates all `set.yaml` files against set schema
3. Validates all `cards/*.yaml` files against card schema
4. Reports validation errors with detailed messages

## GitHub Integration

- **Validation workflow** runs on PR/push to `data/**/*.yaml` or `schemas/**/*.yaml`
- Uses Python 3.11 with `pyyaml` and `jsonschema` dependencies
- Validation must pass for data changes to be accepted