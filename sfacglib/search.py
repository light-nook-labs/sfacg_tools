import re
from dataclasses import dataclass
from loguru import logger
from bs4 import BeautifulSoup, Tag
from .fetcher import Fetcher
from .config import SEARCH_BASE, API_HTML5, PC_BASE


COVER_BASE = 'https://rs.sfacg.com/web/novel/images/NovelCover/Big'


@dataclass
class SearchResult:
    id: str
    title: str
    author: str
    cover: str
    url: str
    snippet: str
    updated: str
    type: str
    score: float


def _parse_html_results(html: str, search_type: str) -> list[SearchResult]:
    soup = BeautifulSoup(html, 'html.parser')
    results: list[SearchResult] = []

    for ul in soup.find_all('ul'):
        items = ul.find_all('li', recursive=False)
        if len(items) < 2:
            continue

        if search_type == 'comic':
            a = ul.select_one('a[href*="manhua.sfacg.com/mh/"]')
        else:
            a = ul.select_one('a[href*="book.sfacg.com/Novel/"]')
        if not a:
            continue

        href = a.get('href', '')
        if search_type == 'comic':
            match = re.search(r'/mh/(\w+)', href)
            novel_id = match.group(1) if match else ''
        else:
            match = re.search(r'/Novel/(\d+)', href)
            novel_id = match.group(1) if match else ''
        if not novel_id:
            continue

        title = a.get_text(strip=True)
        if not title:
            continue

        cover = ''
        img = items[0].find('img')
        if img:
            src = img.get('src', '')
            if src.startswith('//'):
                src = 'https:' + src
            cover = src

        text = items[1].get_text()
        author = ''
        updated = ''
        info_match = re.search(r'综合信息[：:]\s*(.+?)/(\d{4}/\d{1,2}/\d{1,2})', text)
        if info_match:
            author = info_match.group(1).strip()
            updated = info_match.group(2).strip()

        snippet = ''
        for child in items[1].children:
            if isinstance(child, str):
                s = child.strip()
                if s and len(s) > 20 and '综合信息' not in s:
                    snippet = s[:200]
                    break

        results.append(SearchResult(
            id=novel_id, title=title, author=author, cover=cover,
            url=href, snippet=snippet, updated=updated,
            type=search_type, score=0.0,
        ))

    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)
    return unique


def search_novel(keyword: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    url = f'{SEARCH_BASE}/?Key={keyword}&S=1&SS=0'
    logger.info(f'Searching novels: {keyword}')
    html = fetcher.get_html(url)
    results = _parse_html_results(html, 'novel')
    logger.info(f'Found {len(results)} novels for "{keyword}"')
    return results


def search_comic(keyword: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    url = f'{SEARCH_BASE}/?Key={keyword}&S=0&SS=0'
    logger.info(f'Searching comics: {keyword}')
    html = fetcher.get_html(url)
    results = _parse_html_results(html, 'comic')
    logger.info(f'Found {len(results)} comics for "{keyword}"')
    return results


def search(keyword: str, search_type: str = 'novel', fetcher: Fetcher | None = None) -> list[SearchResult]:
    if search_type == 'comic':
        return search_comic(keyword, fetcher)
    return search_novel(keyword, fetcher)


def search_api(keyword: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    logger.info(f'API search: {keyword}')
    data = fetcher.get_json(API_HTML5, params={'op': 'search', 'keyword': keyword})
    novels = data.get('Novels', []) if isinstance(data, dict) else []
    results = []
    for n in novels:
        cover = n.get('NovelCover', '')
        if cover:
            cover = f'{COVER_BASE}/{cover}'
        results.append(SearchResult(
            id=str(n.get('NovelID', '')),
            title=n.get('NovelName', ''),
            author=n.get('AuthorName', ''),
            cover=cover,
            url=f'{PC_BASE}/Novel/{n.get("NovelID", "")}',
            snippet='',
            updated='',
            type='novel',
            score=float(n.get('Point', 0)),
        ))
    logger.info(f'API found {len(results)} novels for "{keyword}"')
    return results


def get_related(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    url = f'{PC_BASE}/Novel/{novel_id}/'
    logger.info(f'Fetching related novels for {novel_id}')
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, 'html.parser')

    results: list[SearchResult] = []

    for item in soup.select('.read-list .item'):
        a = item.select_one('a[href*="/Novel/"]')
        if not a:
            continue
        match = re.search(r'/Novel/(\d+)', a.get('href', ''))
        if not match:
            continue
        nid = match.group(1)
        title_el = item.select_one('.book-name')
        title = title_el.get_text(strip=True) if title_el else ''
        img = item.select_one('img')
        cover = ''
        if img:
            src = img.get('src', '')
            if src.startswith('//'):
                src = 'https:' + src
            cover = src

        results.append(SearchResult(
            id=nid, title=title, author='', cover=cover,
            url=f'{PC_BASE}/Novel/{nid}', snippet='',
            updated='', type='novel', score=0.0,
        ))

    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)

    logger.info(f'Found {len(unique)} related novels for {novel_id}')
    return unique


def get_author_works(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    fetcher = fetcher or Fetcher()
    url = f'{PC_BASE}/Novel/{novel_id}/'
    logger.info(f'Fetching author works for {novel_id}')
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, 'html.parser')

    results: list[SearchResult] = []
    for h3 in soup.select('h3'):
        if '作者' not in h3.get_text() or '作品' not in h3.get_text():
            continue
        container = h3.find_parent('div', class_='common-title')
        if not container:
            continue
        sibling = container.find_next_sibling()
        if not sibling:
            continue
        for a in sibling.select('a[href*="/Novel/"]'):
            match = re.search(r'/Novel/(\d+)', a.get('href', ''))
            if not match:
                continue
            nid = match.group(1)
            title = a.get_text(strip=True)
            if not title:
                continue
            results.append(SearchResult(
                id=nid, title=title, author='', cover='',
                url=f'{PC_BASE}/Novel/{nid}', snippet='',
                updated='', type='novel', score=0.0,
            ))

    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)

    logger.info(f'Found {len(unique)} author works for {novel_id}')
    return unique


def _split_sections(soup: BeautifulSoup) -> list[tuple[str, Tag]]:
    sections = []
    for h3 in soup.select('h3 .main-title'):
        parent = h3.find_parent('h3')
        if not parent:
            continue
        container = parent.find_parent('div')
        if container:
            sections.append((h3.get_text(strip=True), container))
    return sections
