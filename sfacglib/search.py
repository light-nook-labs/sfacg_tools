import re
from time import time

from bs4 import BeautifulSoup
from loguru import logger

from .config import (
    API_BOOK,
    API_COMIC_PICS,
    API_HTML5,
    API_LOLOBUN,
    COMIC_BASE,
    COVER_BASE,
    LOLOBUN_BASE,
    LOLOBUN_COVER,
    MOBILE_BASE,
    PC_BASE,
    SEARCH_BASE,
)
from .fetcher import Fetcher
from .models import SearchItem
from .utils import fix_url_protocol

_NOVEL_ID_PATTERN = re.compile(r'/(\d+)')


def _deduplicate(results: list[SearchItem]) -> list[SearchItem]:
    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)
    return unique


def _parse_info_text(text: str) -> tuple[str, str]:
    prefix = '综合信息'
    if prefix not in text:
        return '', ''
    info_part = text.split(prefix, 1)[1].lstrip('：:').strip()
    parts = info_part.split('/', 1)
    author = parts[0].strip()
    date = parts[1].strip() if len(parts) > 1 else ''
    return author, date.split('<')[0].strip()


def _parse_html_results(html: str, search_type: str) -> list[SearchItem]:
    soup = BeautifulSoup(html, 'html.parser')
    results: list[SearchItem] = []

    for ul in soup.find_all('ul'):
        lis = ul.find_all('li', recursive=False)
        if len(lis) < 2:
            continue

        if search_type == 'comic':
            a = ul.select_one('a[href*="manhua.sfacg.com/mh/"]')
        else:
            a = ul.select_one('a[href*="book.sfacg.com/Novel/"]')
        if not a:
            continue

        href = a.get('href', '')
        title = a.get_text(strip=True)
        if not title:
            continue

        item_id = href.rstrip('/').rsplit('/', 1)[-1]
        if not item_id:
            continue

        cover = ''
        img = lis[0].find('img')
        if img:
            cover = fix_url_protocol(img.get('src', ''))

        info_text = lis[1].get_text()
        author, updated = _parse_info_text(info_text)

        snippet = ''
        for child in lis[1].children:
            if isinstance(child, str):
                s = child.strip()
                if s and len(s) > 20 and '综合信息' not in s:
                    snippet = s[:200]
                    break

        results.append(
            SearchItem(
                id=item_id,
                title=title,
                author=author,
                cover=cover,
                url=href,
                snippet=snippet,
                updated=updated,
                type=search_type,
                score=0.0,
            )
        )

    return _deduplicate(results)


def search(
    keyword: str,
    search_type: str = 'novel',
    params: dict | None = None,
    fetcher: Fetcher | None = None,
) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'Searching: {keyword}')
    query = {'Key': keyword, 'SS': '0', 'S': '1' if search_type == 'novel' else '0'}
    if params:
        query.update(params)
    html = fetcher.get_html(SEARCH_BASE, params=query)
    results = _parse_html_results(html, search_type)
    logger.info(f'Found {len(results)} {search_type}s for "{keyword}"')
    return results


def search_novel(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    return search(keyword, search_type='novel', fetcher=fetcher)


def search_comic(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    return search(keyword, search_type='comic', fetcher=fetcher)


def search_novel_api(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'API search novels: {keyword}')
    raw = fetcher.get_json(
        API_HTML5,
        params={
            'op': 'search',
            'keyword': keyword,
            '_': int(time() * 1000),
        },
    )
    items = raw.get('Novels', []) if isinstance(raw, dict) else []
    results = []
    for n in items:
        cover = n.get('NovelCover', '')
        if cover:
            cover = f'{COVER_BASE}/{cover}'
        nid = str(n.get('NovelID', ''))
        results.append(
            SearchItem(
                id=nid,
                title=n.get('NovelName', ''),
                author=n.get('AuthorName', ''),
                cover=cover,
                url=f'{PC_BASE}/Novel/{nid}',
                snippet='',
                updated='',
                type='novel',
                score=float(n.get('Point', 0)),
            )
        )
    logger.info(f'API found {len(results)} novels for "{keyword}"')
    return results


def search_comic_api(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'API search comics: {keyword}')
    resp = fetcher.post(API_COMIC_PICS, params={'op': 'search'}, data={'keyword': keyword})
    raw = resp.json()
    items = raw.get('comics', []) if isinstance(raw, dict) else []
    results = []
    for c in items:
        folder = c.get('FolderName', '')
        cid = str(c.get('ComicID', ''))
        results.append(
            SearchItem(
                id=cid,
                title=c.get('ComicName', ''),
                author=c.get('AuthorName', ''),
                cover=c.get('ComicCover', ''),
                url=f'{COMIC_BASE}/b/{folder}/',
                snippet=c.get('LastChapterTitle', ''),
                updated=c.get('LastUpdateDate', ''),
                type='comic',
                score=float(c.get('Point', 0)),
            )
        )
    logger.info(f'API found {len(results)} comics for "{keyword}"')
    return results


def get_related(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    url = f'{PC_BASE}/Novel/{novel_id}/'
    logger.info(f'Fetching related novels for {novel_id}')
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, 'html.parser')

    results: list[SearchItem] = []
    for item in soup.select('.read-list .item'):
        a = item.select_one('.book-img a[href*="/Novel/"]')
        if not a:
            continue
        href = a.get('href', '')
        nid = href.rstrip('/').rsplit('/', 1)[-1]
        if not nid:
            continue

        title_el = item.select_one('.book-name')
        title = title_el.get_text(strip=True) if title_el else ''

        cover = ''
        img = item.select_one('img')
        if img:
            cover = fix_url_protocol(img.get('src', ''))

        results.append(
            SearchItem(
                id=nid,
                title=title,
                author='',
                cover=cover,
                url=f'{PC_BASE}/Novel/{nid}',
                snippet='',
                updated='',
                type='novel',
                score=0.0,
            )
        )

    unique = _deduplicate(results)
    logger.info(f'Found {len(unique)} related novels for {novel_id}')
    return unique


def get_author_works(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    url = f'{PC_BASE}/Novel/{novel_id}/'
    logger.info(f'Fetching author works for {novel_id}')
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, 'html.parser')

    author_el = soup.select_one('.author-name')
    author = author_el.get_text(strip=True) if author_el else ''

    results: list[SearchItem] = []

    for title_el in soup.select('.article-list .figcaption'):
        figure = title_el.find_parent(class_='figure')
        if not figure:
            continue
        a = figure.select_one('.pic a[href*="/Novel/"]')
        if not a:
            continue
        href = a.get('href', '')
        nid = href.rstrip('/').rsplit('/', 1)[-1]
        if not nid:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        results.append(
            SearchItem(
                id=nid,
                title=title,
                author=author,
                cover='',
                url=f'{PC_BASE}/Novel/{nid}',
                snippet='',
                updated='',
                type='novel',
                score=0.0,
            )
        )

    unique = _deduplicate(results)
    logger.info(f'Found {len(unique)} author works for {novel_id}')
    return unique


def search_lolobun(
    keyword: str,
    search_type: str = 'novel',
    page: int = 0,
    fetcher: Fetcher | None = None,
) -> list[SearchItem]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'LoLoBun search {search_type}: {keyword}')
    resp = fetcher.get(
        API_LOLOBUN,
        params={'op': 'searchWorks', 'q': keyword, 'type': search_type, 'pi': page, '_': int(time() * 1000)},
        headers={**Fetcher.AJAX_HEADERS, 'Referer': f'{LOLOBUN_BASE}/search/result?q={keyword}'},
    )
    data = resp.json().get('data', {})
    items = data.get('Items', [])
    results = []
    for item in items:
        entity_id = str(item.get('EntityId', ''))
        url = item.get('Url', '')
        full_url = f'{LOLOBUN_BASE}{url}' if url.startswith('/') else url
        cover = item.get('Cover', '')
        if cover and not cover.startswith('http'):
            entity_type = item.get('EntityType', 'Novel')
            cover_base = (
                f'{LOLOBUN_COVER}/web/novel/images/NovelCover/Big'
                if entity_type == 'Novel'
                else f'{LOLOBUN_COVER}/web/comic/images/Logo'
            )
            cover = f'{cover_base}/{cover}'
        results.append(
            SearchItem(
                id=entity_id,
                title=item.get('Title', ''),
                author=item.get('AuthorName', ''),
                cover=cover,
                url=full_url,
                snippet=item.get('Intro', '')[:200],
                updated='',
                type=search_type,
                score=float(item.get('Weight', 0)),
            )
        )
    logger.info(f'LoLoBun found {len(results)} {search_type}s for "{keyword}"')
    return results


def search_lolobun_novel(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    return search_lolobun(keyword, search_type='novel', fetcher=fetcher)


def search_lolobun_comic(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    return search_lolobun(keyword, search_type='comic', fetcher=fetcher)


def predictive_novel(keyword: str, fetcher: Fetcher | None = None) -> list[str]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'Predictive novel search: {keyword}')
    headers = {
        **Fetcher.AJAX_HEADERS,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': MOBILE_BASE,
        'Referer': f'{MOBILE_BASE}/search.html',
    }
    resp = fetcher.post(
        API_BOOK,
        params={'op': 'searchreffer'},
        data={'keyword': keyword},
        headers=headers,
    )
    results = resp.json().get('keywords', [])
    logger.info(f'Predictive novel found {len(results)} suggestions for "{keyword}"')
    return results


def predictive_comic(keyword: str, fetcher: Fetcher | None = None) -> list[str]:
    fetcher = fetcher or Fetcher.no_auth()
    logger.info(f'Predictive comic search: {keyword}')
    headers = {
        **Fetcher.AJAX_HEADERS,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': MOBILE_BASE,
        'Referer': f'{MOBILE_BASE}/search.html',
    }
    resp = fetcher.post(
        API_COMIC_PICS,
        params={'op': 'getSearchReffer'},
        data={'keyword': keyword},
        headers=headers,
    )
    results = resp.json().get('keywords', [])
    logger.info(f'Predictive comic found {len(results)} suggestions for "{keyword}"')
    return results


class NovelItem:
    def __init__(self, nid: int, fetcher: Fetcher | None = None):
        self._id = nid
        self._fetcher = fetcher or Fetcher.no_auth()
        self._author: str | None = None
        self._same_author_works: list[SearchItem] | None = None

    def __repr__(self):
        s = f'<NovelItem(id={self._id}) '
        if self._author is None or self._same_author_works is None:
            s += 'Has not fetched data!'
        else:
            s += f'Author: {self._author}, Works num: {len(self._same_author_works)}'
        s += '>'
        return s

    @property
    def id(self) -> int:
        return self._id

    @property
    def author(self) -> str | None:
        return self._author

    @property
    def same_author_works(self) -> list[SearchItem] | None:
        return self._same_author_works

    def fetch_data(self) -> None:
        url = f'{MOBILE_BASE}/b/{self._id}/'
        headers = {**Fetcher.AJAX_HEADERS, 'Referer': f'{MOBILE_BASE}/b/{self._id}/'}
        try:
            resp = self._fetcher.get(url, headers=headers)
            resp.raise_for_status()
        except Exception:
            logger.warning(f'Failed to fetch novel detail for {self._id}')
            self._author = ''
            self._same_author_works = []
            return

        soup = BeautifulSoup(resp.text, 'html.parser')
        author_sec = soup.select_one('.book_Author')
        if author_sec is None:
            self._author = ''
            self._same_author_works = []
            return

        author_tag = author_sec.find('li')
        self._author = author_tag.get_text(strip=True) if author_tag else ''

        novels_div = author_sec.find('div')
        self._same_author_works = []
        if novels_div:
            for a_tag in novels_div.find_all('a'):
                title = a_tag.get_text(strip=True)
                href = a_tag.get('href', '')
                match = _NOVEL_ID_PATTERN.search(href)
                if match:
                    self._same_author_works.append(
                        SearchItem(
                            id=match.group(1),
                            title=title,
                            author=self._author or '',
                            url=f'{MOBILE_BASE}/b/{match.group(1)}/',
                            type='novel',
                        )
                    )
