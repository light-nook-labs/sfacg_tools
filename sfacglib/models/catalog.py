from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class CatalogItem(BaseModel):
    idx: int
    title: str
    url: str = ''
    file: str = ''
    status: str = 'pending'  # pending | done | failed
    vip_mode: str = ''  # '' | 'encrypted' | 'image'
    error: str = ''


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
            sections_map[sec_idx].items.append(
                CatalogItem(
                    idx=item.get('item_idx', 0),
                    title=item.get('item_title', ''),
                    url=item.get('item_url', ''),
                    file=item.get('file', ''),
                )
            )

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

    @classmethod
    def from_sections(
        cls,
        id: str,
        title: str,
        sections: list,
        author: str = '',
        cover: str = '',
        intro: str = '',
        ext: str = 'md',
        item_prefix: str = 'item',
    ) -> Catalog:
        """Build catalog from Section objects before download starts."""
        from ..utils import sanitize_filename

        catalog_sections: list[CatalogSection] = []
        for section in sections:
            safe_section = sanitize_filename(section.title)
            dir_name = f'sec_{section.idx:03d}_{safe_section}'
            catalog_items: list[CatalogItem] = []
            for item in section.get_items():
                safe_title = sanitize_filename(item.title)
                if safe_title:
                    filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                else:
                    filename = f'{item_prefix}_{item.idx:03d}.{ext}'
                catalog_items.append(
                    CatalogItem(
                        idx=item.idx,
                        title=item.title,
                        url=item.url,
                        file=f'{dir_name}/{filename}',
                        status='pending',
                        vip_mode=getattr(item, 'vip_mode', ''),
                    )
                )
            catalog_sections.append(
                CatalogSection(
                    idx=section.idx,
                    title=section.title,
                    dir=dir_name,
                    items=catalog_items,
                )
            )
        return cls(
            id=id,
            title=title,
            author=author,
            cover=cover,
            intro=intro,
            sections=catalog_sections,
        )
