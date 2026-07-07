import json
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(data: dict, path: Path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
