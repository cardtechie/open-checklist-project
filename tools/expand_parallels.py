import argparse
import re
import uuid
from pathlib import Path

import yaml


DATA_DIR = Path("data") / "baseball"


PARALLEL_PLANS = {
    "2026-topps-chrome-black": {
        "source_url": "https://baseballcardpedia.com/index.php/2026_Topps_Chrome_Black#Insertion_Ratios",
        "sections": {
            "Base": [
                ("Refractor", 199),
                ("Blue Refractor", 150),
                ("Green Refractor", 99),
                ("Purple Refractor", 75),
                ("Purple Mini-Diamond Refractor", 75),
                ("Purple Wave Refractor", 75),
                ("Gold Refractor", 50),
                ("Gold Mini Diamond Refractor", 50),
                ("Gold Wave Refractor", 50),
                ("Orange Refractor", 25),
                ("Orange Mini Diamond Refractor", 25),
                ("Orange Wave Refractor", 25),
                ("Rose Gold Refractor", 10),
                ("Rose Gold Mini Diamond Refractor", 10),
                ("Rose Gold Wave Refractor", 10),
                ("Red Refractor", 5),
                ("Red Mini Diamond Refractor", 5),
                ("Red Wave Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Base - Rookie Design Variations": [
                ("Purple Refractor", 75),
                ("Gold Refractor", 50),
                ("Orange Refractor", 25),
                ("Rose Gold Refractor", 10),
                ("Red Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Damascus": [("SuperFractor", 1)],
            "Nocturnal": [("SuperFractor", 1)],
            "Home Field": [("Black Refractor", 1)],
            "Depth Of Darkness": [
                ("Red Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Chrome Black Autographs": [
                ("Refractor", 199),
                ("Blue Refractor", 150),
                ("Green Refractor", 99),
                ("Purple Refractor", 75),
                ("Gold Refractor", 50),
                ("Gold Mini Diamond Refractor", 50),
                ("Orange Refractor", 25),
                ("Orange Mini Diamond Refractor", 25),
                ("Rose Gold Refractor", 10),
                ("Rose Gold Mini Diamond Refractor", 10),
                ("Red Refractor", 5),
                ("Red Mini Diamond Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Super Futures Autographs": [
                ("Gold Refractor", 50),
                ("Orange Refractor", 25),
                ("Rose Gold Refractor", 10),
                ("Red Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Ivory Autographs": [
                ("Orange Trim", 25),
                ("Red Trim", 5),
                ("SuperFractor", 1),
            ],
            "Paint It": [
                ("Red Refractor", 5),
                ("SuperFractor", 1),
            ],
            "Pitch Black Pairings Dual Autographs": [
                ("Orange Refractor", 25),
                ("Rose Gold Refractor", 10),
                ("Red Refractor", 5),
                ("SuperFractor", 1),
            ],
        },
    },
}


FIELD_ORDER = [
    "number",
    "uuid",
    "genre",
    "sport",
    "sports",
    "set_id",
    "subjects",
    "subset",
    "card_name",
    "description",
    "series",
    "variation",
    "parallel",
    "print_run",
    "rookie_card",
    "autograph",
    "relic",
    "serial_numbered",
    "release_date",
    "image_url",
    "external_links",
]


def slugify(value):
    value = str(value).lower().replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def yaml_quote(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_existing_uuid(path):
    if not path.exists():
        return None
    match = re.search(r'^uuid:\s*"?([0-9a-fA-F-]{36})"?\s*$', path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def write_card(path, data):
    lines = []
    for field in FIELD_ORDER:
        if field not in data:
            continue
        value = data[field]
        if field == "subjects":
            lines.append("subjects:")
            for subject in value:
                lines.append(f"  - name: {yaml_quote(subject['name'])}")
                if "role" in subject:
                    lines.append(f"    role: {yaml_quote(subject['role'])}")
                if "team" in subject:
                    lines.append(f"    team: {yaml_quote(subject['team'])}")
        elif field == "external_links":
            lines.append("external_links:")
            for link in value:
                lines.append(f"  - name: {yaml_quote(link['name'])}")
                lines.append(f"    url: {yaml_quote(link['url'])}")
        elif isinstance(value, bool):
            lines.append(f"{field}: {str(value).lower()}")
        elif isinstance(value, int):
            lines.append(f"{field}: {value}")
        elif isinstance(value, list):
            lines.append(f"{field}: [{', '.join(yaml_quote(item) for item in value)}]")
        else:
            lines.append(f"{field}: {yaml_quote(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def section_name(card):
    return card.get("subset", "Base")


def build_parallel_card(card, base_path, parallel, print_run, source_url):
    variant_path = base_path.with_name(f"{base_path.stem}-{slugify(parallel)}.yaml")
    variant = dict(card)
    variant["uuid"] = read_existing_uuid(variant_path) or str(uuid.uuid4())
    variant["parallel"] = parallel
    variant["print_run"] = print_run
    variant["serial_numbered"] = print_run is not None
    title = card.get("card_name", card["number"])
    if f" - {parallel}" not in title:
        variant["card_name"] = f"{title} - {parallel}"
    variant["description"] = f"{parallel} parallel of {card.get('description', title)}"
    image_root = card.get("image_url", "").rsplit("/", 1)[0]
    if image_root:
        variant["image_url"] = f"{image_root}/{variant_path.stem}.jpg"
    links = list(card.get("external_links", []))
    if not any(link.get("name") == "BaseballCardpedia" and link.get("url") == source_url for link in links):
        links.append({"name": "BaseballCardpedia", "url": source_url})
    variant["external_links"] = links
    return variant_path, variant


def update_set_count(set_dir):
    set_path = set_dir / "set.yaml"
    text = set_path.read_text(encoding="utf-8")
    count = len(list((set_dir / "cards").glob("*.yaml")))
    text = re.sub(r"^card_count:\s*\d+\s*$", f"card_count: {count}", text, flags=re.MULTILINE)
    set_path.write_text(text, encoding="utf-8")


def expand_set(set_id, limit):
    plan = PARALLEL_PLANS[set_id]
    set_dir = DATA_DIR / set_id
    cards_dir = set_dir / "cards"
    written = 0
    for path in sorted(cards_dir.glob("*.yaml")):
        card = read_yaml(path)
        if "parallel" in card:
            continue
        variants = plan["sections"].get(section_name(card), [])
        for parallel, print_run in variants:
            variant_path, variant = build_parallel_card(card, path, parallel, print_run, plan["source_url"])
            if variant_path.exists():
                continue
            write_card(variant_path, variant)
            written += 1
            if written >= limit:
                update_set_count(set_dir)
                return written
    update_set_count(set_dir)
    return written


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-id", choices=sorted(PARALLEL_PLANS), required=True)
    parser.add_argument("--limit", type=int, default=1000)
    return parser.parse_args()


def main():
    args = parse_args()
    written = expand_set(args.set_id, args.limit)
    print(f"Wrote {written} parallel cards for {args.set_id}")


if __name__ == "__main__":
    main()
