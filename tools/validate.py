import os
import sys
import json
import yaml
import jsonschema
from pathlib import Path

# Config
SCHEMA_DIR = Path("schemas")
DATA_DIR = Path("data")

def load_schema(schema_file):
    with open(schema_file, "r") as f:
        return yaml.safe_load(f)

def validate_file(file_path, schema):
    with open(file_path, "r") as f:
        try:
            data = yaml.safe_load(f)
            jsonschema.validate(instance=data, schema=schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Invalid YAML or unexpected error: {e}"

def main():
    errors_found = False

    # Load schemas
    card_schema = load_schema(SCHEMA_DIR / "card" / "schema.yaml")
    set_schema = load_schema(SCHEMA_DIR / "set" / "schema.yaml")

    # Validate sets
    print("🔍 Validating sets...")
    for set_file in DATA_DIR.rglob("*/set.yaml"):
        is_valid, error = validate_file(set_file, set_schema)
        if is_valid:
            print(f"✅ {set_file}")
        else:
            print(f"❌ {set_file}\n    {error}")
            errors_found = True

    # Validate cards
    print("\n🔍 Validating cards...")
    for card_file in DATA_DIR.rglob("cards/*.yaml"):
        is_valid, error = validate_file(card_file, card_schema)
        if is_valid:
            print(f"✅ {card_file}")
        else:
            print(f"❌ {card_file}\n    {error}")
            errors_found = True

    if errors_found:
        print("\n❌ Validation completed with errors.")
        sys.exit(1)
    else:
        print("\n✅ All files validated successfully.")
        sys.exit(0)

if __name__ == "__main__":
    main()

