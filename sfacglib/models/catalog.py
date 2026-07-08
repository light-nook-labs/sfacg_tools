from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class CatalogItem(BaseModel):
    idx: int
    title: str
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
    cover_file: str = ''
    info_file: str = ''
    description: str = ''
    sections: list[CatalogSection] = []

    @classmethod
    def load(cls, path: str | Path) -> Catalog:
        path = Path(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls(**data)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.model_dump(exclude_none=True), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )


class NovelCatalogItem(CatalogItem):
    chapter_id: str = ''
    is_gif: bool = False


class NovelCatalogSection(CatalogSection):
    vol_id: str = ''
    items: list[NovelCatalogItem] = []


class NovelCatalog(Catalog):
    sections: list[NovelCatalogSection] = []


class ComicCatalogSection(CatalogSection):
    chapter_url: str = ''
    image_urls: list[str] = []


class ComicCatalog(Catalog):
    sections: list[ComicCatalogSection] = []


class AudioCatalogItem(CatalogItem):
    url: str = ''
    mp3_url: str | None = None


class AudioCatalogSection(CatalogSection):
    items: list[AudioCatalogItem] = []


class AudioCatalog(Catalog):
    sections: list[AudioCatalogSection] = []


class ReviewCatalogSection(CatalogSection):
    cid: str = ''


class ReviewCatalog(Catalog):
    sections: list[ReviewCatalogSection] = []


class LoLoBunNovelCatalogItem(CatalogItem):
    chapter_id: str = ''


class LoLoBunNovelCatalogSection(CatalogSection):
    items: list[LoLoBunNovelCatalogItem] = []


class LoLoBunNovelCatalog(Catalog):
    sections: list[LoLoBunNovelCatalogSection] = []


class LoLoBunComicCatalogSection(CatalogSection):
    chapter_id: str = ''
    image_urls: list[str] = []


class LoLoBunComicCatalog(Catalog):
    sections: list[LoLoBunComicCatalogSection] = []
