# Open Checklist Project

![Validate Data](https://github.com/cardtechie/open-checklist-project/actions/workflows/validate.yml/badge.svg)

The **Open Checklist Project** is an open-data initiative to standardize and share trading card checklist data for collectors, developers, and the broader hobby ecosystem.

## Goals

- Make reliable, structured checklist data freely available
- Define open schemas for consistent use across tools and apps
- Foster a contributor-friendly ecosystem for managing and improving trading card data

## Contents

- ✅ JSON/YAML schemas for cards and sets
- 📦 Curated and contributed checklist data (organized by genre, sport, and set)
- 🛠 Tools for validating, transforming, and consuming data
- 🤝 GitHub workflows for contributor validation

## Schemas

The project includes standardized schemas for consistent data structure:

- **Card Schema v0.1**: [`schemas/card/schema.yaml`](schemas/card/schema.yaml) ([Latest Documentation](schemas/card/README.md))
- **Set Schema v0.2**: [`schemas/set/schema.yaml`](schemas/set/schema.yaml) ([Latest Documentation](schemas/set/README.md))

For detailed schema documentation, version history, and examples, see the [schemas directory](schemas/README.md).

## Validation

To validate your data against the schemas, you can use Docker:

```bash
# Build the validation container
docker build -t open-checklist-validator .

# Run validation on all data files
docker run open-checklist-validator
```

Alternatively, if you have Python 3.11+ installed:

```bash
pip install pyyaml jsonschema
python tools/validate.py
```

## Learn More

- [Website](https://openchecklistproject.org)
- [API Access](https://tradingcardapi.com)
- [Documentation (coming soon)]()

## License

Open data is licensed under Creative Commons (TBD). Schema and code under MIT.