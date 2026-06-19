from ebooklib import epub
from ebooklib.epub import EpubHtml
from bs4 import BeautifulSoup, Tag
from uuid import uuid4
from pathlib import Path
from loguru import logger
from urllib.parse import urlparse
from .fetcher import Fetcher
from .config import WORKERS_EPUB_IMG
from .utils import run_tasks

_MEDIA_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
}


def _detect_media_type(url: str, fallback: str = 'image/jpeg') -> str:
    ext = urlparse(url).path.rsplit('.', 1)[-1].lower() if '.' in urlparse(url).path else ''
    return _MEDIA_TYPES.get(f'.{ext}', fallback)


def _process_images(
    book: epub.EpubBook,
    container: Tag,
    fetcher: Fetcher,
) -> None:
    img_tasks: list[tuple[Tag, str]] = []
    for img in container.find_all('img'):
        img_url = img.get('src', '')
        if img_url:
            img_tasks.append((img, img_url))

    if not img_tasks:
        return

    tasks = {url: url for _, url in img_tasks}

    def _fetch(url: str) -> bytes:
        try:
            return fetcher.get_binary(url)
        except Exception as e:
            logger.warning(f'图片下载失败: {url}: {e}')
            return b''

    results_list = run_tasks(tasks, _fetch, WORKERS_EPUB_IMG, 'Images', leave=False)
    results: dict[str, bytes] = {url: data for url, data in results_list if data}

    for img, url in img_tasks:
        if url not in results:
            continue
        fname = f'image_{str(uuid4())[:8]}'
        media_type = _detect_media_type(url)
        ext = media_type.split('/')[-1].replace('jpeg', 'jpg')
        book.add_item(epub.EpubImage(
            uid=str(uuid4()),
            file_name=f'images/{fname}.{ext}',
            media_type=media_type,
            content=results[url],
        ))
        img['src'] = f'images/{fname}.{ext}'


def download_epub(
    html: str,
    title: str,
    author: str,
    desc: str,
    cover: str,
    path: str | Path = './',
    fetcher: Fetcher | None = None,
) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or Fetcher()

    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title(title)
    book.set_language('zh')
    book.add_author(author)
    book.add_metadata('DC', 'description', desc)

    try:
        book.set_cover('cover.jpg', fetcher.get_binary(cover))
    except Exception as e:
        logger.warning(f'封面下载失败: {e}')

    spine: list[str | EpubHtml] = ['nav']
    toc: list = []

    soup = BeautifulSoup(html, 'html.parser')
    vol_tags = soup.find_all(class_='vol')

    info_page = None
    vol_sections = []

    for vol_tag in vol_tags:
        vol_title = vol_tag.h2.get_text() if vol_tag.h2 else ''
        ch_tags = vol_tag.find_all(class_='ch')

        if not ch_tags:
            _process_images(book, vol_tag, fetcher)
            page = epub.EpubHtml(
                title=vol_title or title,
                file_name=f'intro_{str(uuid4())[:8]}.xhtml',
                lang='zh',
                content=str(vol_tag),
            )
            book.add_item(page)
            spine.append(page)
            info_page = page
        else:
            _process_images(book, vol_tag, fetcher)

            vol_page = epub.EpubHtml(
                title=vol_title,
                file_name=f'vol_{str(uuid4())[:8]}.xhtml',
                lang='zh',
                content=str(vol_tag.h2) if vol_tag.h2 else '',
            )
            book.add_item(vol_page)
            spine.append(vol_page)

            chapters = []
            for ch_tag in ch_tags:
                if not ch_tag.h3:
                    continue
                ch_title = ch_tag.h3.get_text()
                ch_page = epub.EpubHtml(
                    title=ch_title,
                    file_name=f'ch_{str(uuid4())[:8]}.xhtml',
                    lang='zh',
                    content=str(ch_tag),
                )
                chapters.append(ch_page)
                book.add_item(ch_page)
                spine.append(ch_page)

            vol_sections.append((epub.Section(vol_title), tuple(chapters)))

    if info_page:
        toc.append(info_page)
    toc.extend(vol_sections)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    safe_title = title.replace('/', '_').replace('\\', '_')
    epub_path = path / f'{safe_title}.epub'
    try:
        epub.write_epub(name=str(epub_path), book=book)
        logger.bind(force=True).info(f'电子书生成成功: {epub_path}')
    except Exception as e:
        logger.error(f'生成电子书失败: {e}')
