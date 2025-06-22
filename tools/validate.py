import os
import yaml
import jsonschema
from pathlib import Path

# Load schemas
def load_schema(schema_path):
    with open(schema_path, 'r') as f:
        return yaml.safe_load(f)

card_schema = load_schema('schemas/card.schema.yaml')
set_schema = load_schema('schemas/set.schema.yaml')

def validate_yaml_file(file_path, schema):
    with open(file_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
            jsonschema.validate(instance=data, schema=schema)
            print(f"✅ Valid: {file_path}")
        except yaml.YAMLError as e:
            print(f"❌ YAML error in {file_path}: {e}")
        except jsonschema.exceptions.ValidationError as e:
            print(f"❌ Schema error in {file_path}: {e.message}")

# Walk through all YAML files in data directory
for root, dirs, files in os.walk('data'):
    for file in files:
        if file.endswith('.yaml'):
            path = Path(root) / file
            if file == 'set.yaml':
                validate_yaml_file(path, set_schema)
            else:
                validate_yaml_file(path, card_schema)
