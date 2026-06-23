from __future__ import annotations
from pydantic import BaseModel, Field


class SearchItem(BaseModel):
    id: str
    title: str
    author: str = ''
    cover: str = ''
    url: str
    snippet: str = ''
    updated: str = ''
    type: str = 'novel'
    score: float = 0.0


class CatalogItem(BaseModel):
    idx: int
    title: str
    url: str = ''
    file: str = ''


class CatalogSection(BaseModel):
    idx: int
    title: str
    dir: str = ''
    items: list[CatalogItem] = []


class Catalog(BaseModel):
    id: str
    title: str
    author: str = ''
    cover: str = ''
    intro: str = ''
    sections: list[CatalogSection] = []

    @classmethod
    def load(cls, path) -> Catalog:
        from pathlib import Path
        import json
        path = Path(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls._migrate(data)

    @classmethod
    def _migrate(cls, data: dict) -> Catalog:
        if 'sections' in data and isinstance(data['sections'], list) and data['sections']:
            if isinstance(data['sections'][0], dict) and 'items' in data['sections'][0]:
                return Catalog(**data)

        items_key = 'items' if 'items' in data else 'chapters'
        flat_items = data.get(items_key, [])
        volumes_map = data.get('volumes', {})

        sections_map: dict[int, CatalogSection] = {}
        for item in flat_items:
            sec_idx = item.get('section_idx', 0)
            if sec_idx not in sections_map:
                sec_title = item.get('section_title', '')
                sections_map[sec_idx] = CatalogSection(
                    idx=sec_idx,
                    title=sec_title,
                    dir='',
                    items=[],
                )
            sections_map[sec_idx].items.append(CatalogItem(
                idx=item.get('item_idx', 0),
                title=item.get('item_title', ''),
                url=item.get('item_url', ''),
                file=item.get('file', ''),
            ))

        sections = sorted(sections_map.values(), key=lambda s: s.idx)

        return Catalog(
            id=str(data.get('id', data.get('nid', ''))),
            title=data.get('title', ''),
            author=data.get('author', ''),
            cover=data.get('cover', ''),
            intro=data.get('intro', data.get('info', '')),
            sections=sections,
        )

    def save(self, path) -> None:
        from pathlib import Path
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2),
            encoding='utf-8',
        )

    def flat_items(self) -> list[tuple[CatalogSection, CatalogItem]]:
        result = []
        for section in self.sections:
            for item in section.items:
                result.append((section, item))
        return result
