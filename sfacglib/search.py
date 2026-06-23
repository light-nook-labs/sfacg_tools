import re
from dataclasses import dataclass
from loguru import logger
from bs4 import BeautifulSoup
from .fetcher import Fetcher
from .config import SEARCH_BASE


@dataclass
class SearchResult:
    id: str
    title: str
    author: str
    cover: str
    url: str
    snippet: str
    updated: str


def search_novel(keyword: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    url = f'{SEARCH_BASE}/?Key={keyword}&S=1&SS=0'
    logger.info(f'Searching: {keyword}')

    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, 'html.parser')

    results: list[SearchResult] = []

    for a in soup.select('a[href*="book.sfacg.com/Novel/"]'):
        href = a.get('href', '')
        match = re.search(r'/Novel/(\d+)', href)
        if not match:
            continue

        novel_id = match.group(1)
        title = a.get_text(strip=True)
        if not title:
            continue

        parent = a.find_parent('div') or a.find_parent('li')
        cover = ''
        snippet = ''
        author = ''
        updated = ''

        if parent:
            img = parent.find('img')
            if img:
                src = img.get('src', '')
                if src.startswith('//'):
                    src = 'https:' + src
                cover = src

            text = parent.get_text()
            info_match = re.search(r'综合信息[：:]\s*(.+?)/(\d{4}/\d{1,2}/\d{1,2})', text)
            if info_match:
                author = info_match.group(1).strip()
                updated = info_match.group(2).strip()

            for br in parent.find_all('br'):
                next_text = br.next_sibling
                if next_text and hasattr(next_text, 'strip'):
                    s = next_text.strip()
                    if s and len(s) > 20 and '综合信息' not in s:
                        snippet = s[:200]
                        break
                elif isinstance(next_text, str):
                    s = next_text.strip()
                    if s and len(s) > 20 and '综合信息' not in s:
                        snippet = s[:200]
                        break

        results.append(SearchResult(
            id=novel_id,
            title=title,
            author=author,
            cover=cover,
            url=f'https://book.sfacg.com/Novel/{novel_id}',
            snippet=snippet,
            updated=updated,
        ))

    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)

    logger.info(f'Found {len(unique)} results for "{keyword}"')
    return unique
