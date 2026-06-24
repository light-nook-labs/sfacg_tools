from time import time

from loguru import logger
from bs4 import BeautifulSoup

from .fetcher import Fetcher
from .config import SEARCH_BASE, API_HTML5, API_COMIC_PICS, PC_BASE, COMIC_BASE, COVER_BASE
from .models import SearchItem
from .utils import fix_url_protocol


def _deduplicate(results: list[SearchItem]) -> list[SearchItem]:
    seen = set()
    unique = []
    for r in results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)
    return unique


def _parse_info_text(text: str) -> tuple[str, str]:
    """Parse '综合信息：author/date' into (author, date)."""
    prefix = "综合信息"
    if prefix not in text:
        return "", ""
    info_part = text.split(prefix, 1)[1].lstrip("：:").strip()
    parts = info_part.split("/", 1)
    author = parts[0].strip()
    date = parts[1].strip() if len(parts) > 1 else ""
    return author, date


def _parse_html_results(html: str, search_type: str) -> list[SearchItem]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchItem] = []

    for ul in soup.find_all("ul"):
        lis = ul.find_all("li", recursive=False)
        if len(lis) < 2:
            continue

        if search_type == "comic":
            a = ul.select_one('a[href*="manhua.sfacg.com/mh/"]')
        else:
            a = ul.select_one('a[href*="book.sfacg.com/Novel/"]')
        if not a:
            continue

        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not title:
            continue

        item_id = href.rstrip("/").rsplit("/", 1)[-1]
        if not item_id:
            continue

        cover = ""
        img = lis[0].find("img")
        if img:
            cover = fix_url_protocol(img.get("src", ""))

        info_text = lis[1].get_text()
        author, updated = _parse_info_text(info_text)

        snippet = ""
        for child in lis[1].children:
            if isinstance(child, str):
                s = child.strip()
                if s and len(s) > 20 and "综合信息" not in s:
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
    fetcher: Fetcher | None = None,
    params: dict | None = None,
) -> list[SearchItem]:
    fetcher = fetcher or Fetcher()
    logger.info(f"Searching: {keyword}")
    query = {"Key": keyword, "SS": "0"}
    if params:
        query.update(params)
    html = fetcher.get_html(SEARCH_BASE, params=query)
    return html


def search_novel(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    html = search(keyword, fetcher, params={"S": "1"})
    results = _parse_html_results(html, "novel")
    logger.info(f'Found {len(results)} novels for "{keyword}"')
    return results


def search_comic(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    html = search(keyword, fetcher, params={"S": "0"})
    results = _parse_html_results(html, "comic")
    logger.info(f'Found {len(results)} comics for "{keyword}"')
    return results


def search_api(
    keyword: str,
    fetcher: Fetcher | None = None,
    method: str = "GET",
    params: dict | None = None,
    data: dict | None = None,
) -> dict | list:
    fetcher = fetcher or Fetcher()
    logger.info(f"API search: {keyword}")
    if method.upper() == "POST":
        resp = fetcher.post(API_HTML5, params=params, data=data)
        return resp.json()
    else:
        return fetcher.get_json(API_HTML5, params=params)


def search_novel_api(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    raw = search_api(keyword, fetcher, params={
        "op": "search", "keyword": keyword, "_": int(time() * 1000),
    })
    items = raw.get("Novels", []) if isinstance(raw, dict) else []
    results = []
    for n in items:
        cover = n.get("NovelCover", "")
        if cover:
            cover = f"{COVER_BASE}/{cover}"
        nid = str(n.get("NovelID", ""))
        results.append(SearchItem(
            id=nid,
            title=n.get("NovelName", ""),
            author=n.get("AuthorName", ""),
            cover=cover,
            url=f"{PC_BASE}/Novel/{nid}",
            snippet="",
            updated="",
            type="novel",
            score=float(n.get("Point", 0)),
        ))
    logger.info(f'API found {len(results)} novels for "{keyword}"')
    return results


def search_comic_api(keyword: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    raw = search_api(keyword, fetcher, method="POST", url=API_COMIC_PICS,
                     params={"op": "search"}, data={"keyword": keyword})
    items = raw.get("comics", []) if isinstance(raw, dict) else []
    results = []
    for c in items:
        folder = c.get("FolderName", "")
        cid = str(c.get("ComicID", ""))
        results.append(SearchItem(
            id=cid,
            title=c.get("ComicName", ""),
            author=c.get("AuthorName", ""),
            cover=c.get("ComicCover", ""),
            url=f"{COMIC_BASE}/b/{folder}/",
            snippet=c.get("LastChapterTitle", ""),
            updated=c.get("LastUpdateDate", ""),
            type="comic",
            score=float(c.get("Point", 0)),
        ))
    logger.info(f'API found {len(results)} comics for "{keyword}"')
    return results


def get_related(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher()
    url = f"{PC_BASE}/Novel/{novel_id}/"
    logger.info(f"Fetching related novels for {novel_id}")
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, "html.parser")

    results: list[SearchItem] = []
    for item in soup.select(".read-list .item"):
        a = item.select_one(".book-img a[href*='/Novel/']")
        if not a:
            continue
        href = a.get("href", "")
        nid = href.rstrip("/").rsplit("/", 1)[-1]
        if not nid:
            continue

        title_el = item.select_one(".book-name")
        title = title_el.get_text(strip=True) if title_el else ""

        cover = ""
        img = item.select_one("img")
        if img:
            cover = fix_url_protocol(img.get("src", ""))

        results.append(
            SearchItem(
                id=nid,
                title=title,
                author="",
                cover=cover,
                url=f"{PC_BASE}/Novel/{nid}",
                snippet="",
                updated="",
                type="novel",
                score=0.0,
            )
        )

    unique = _deduplicate(results)
    logger.info(f"Found {len(unique)} related novels for {novel_id}")
    return unique


def get_author_works(novel_id: str, fetcher: Fetcher | None = None) -> list[SearchItem]:
    fetcher = fetcher or Fetcher()
    url = f"{PC_BASE}/Novel/{novel_id}/"
    logger.info(f"Fetching author works for {novel_id}")
    html = fetcher.get_html(url)
    soup = BeautifulSoup(html, "html.parser")

    author_el = soup.select_one(".author-name")
    author = author_el.get_text(strip=True) if author_el else ""

    results: list[SearchItem] = []

    for title_el in soup.select(".article-list .figcaption"):
        figure = title_el.find_parent(class_="figure")
        if not figure:
            continue
        a = figure.select_one(".pic a[href*='/Novel/']")
        if not a:
            continue
        href = a.get("href", "")
        nid = href.rstrip("/").rsplit("/", 1)[-1]
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
                cover="",
                url=f"{PC_BASE}/Novel/{nid}",
                snippet="",
                updated="",
                type="novel",
                score=0.0,
            )
        )

    unique = _deduplicate(results)
    logger.info(f"Found {len(unique)} author works for {novel_id}")
    return unique
