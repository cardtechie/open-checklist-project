# Open Checklist Project

![Validate Data](https://github.com/cardtechie/open-checklist-project/actions/workflows/validate.yml/badge.svg)

The **Open Checklist Project** is an open-data initiative to standardize and share trading card checklist data for collectors, developers, and the broader hobby ecosystem.

## Goals

- Make reliable, structured checklist data freely available
- Define open schemas for consistent use across tools and apps
- Foster a contributor-friendly ecosystem for managing and improving trading card data

## Contents

- ✅ Open YAML schemas — sets, manifests, and checklists (the v0.3 manifest form)
- 📦 Curated and contributed checklist data (organized by genre, sport, and set)
- 🛠 Tools for validating, transforming, and consuming data
- 🤝 GitHub workflows for contributor validation

## Schemas

The project uses standardized, independently-versioned schemas. As of **v0.3**, a set is
stored in the **manifest form** — a compact `set.yaml` + `manifest.yaml` + `checklists/`
from which the full per-card explosion is *derived* — replacing the older
one-file-per-card layout.

- **Set v0.3** (manifest form): [`schemas/set/schema.yaml`](schemas/set/schema.yaml) ([docs](schemas/set/README.md))
- **Manifest v0.1**: [`schemas/manifest/schema.yaml`](schemas/manifest/schema.yaml) ([docs](schemas/manifest/README.md))
- **Checklist v0.1**: [`schemas/checklist/schema.yaml`](schemas/checklist/schema.yaml) ([docs](schemas/checklist/README.md))

For the manifest form, the identity/UUID contract, versioning, validation, and examples,
see the [schemas directory](schemas/README.md).

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