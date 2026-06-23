import json
import re
from pathlib import Path
from html import escape as html_escape
from loguru import logger
from .base import _sanitize_filename
from .fetcher import Fetcher

_REPO_URL = 'https://github.com/light-nook-labs/sfacg'
_ORG_AVATAR = 'https://avatars.githubusercontent.com/u/light-nook-labs'


def _strip_md(text: str) -> str:
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            stripped = re.sub(r'^#{1,6}\s*', '', stripped)
        if stripped == '---' or stripped == '***' or stripped == '===':
            result.append('')
            continue
        stripped = re.sub(r'\*\*(.+?)\*\*', r'\1', stripped)
        stripped = re.sub(r'\*(.+?)\*', r'\1', stripped)
        stripped = re.sub(r'`(.+?)`', r'\1', stripped)
        result.append(stripped)
    return '\n'.join(result)


def _load_catalog(dir_path: Path) -> dict:
    catalog_path = dir_path / 'catalog.json'
    if not catalog_path.exists():
        raise FileNotFoundError(f'未找到 catalog.json: {dir_path}')
    return json.loads(catalog_path.read_text(encoding='utf-8'))


def _get_sections(catalog: dict) -> list[dict]:
    sections = catalog.get('sections', [])
    if sections:
        return sections

    volumes = catalog.get('volumes', {})
    if isinstance(volumes, dict) and volumes:
        return [{'idx': idx, 'title': title} for title, idx in sorted(volumes.items(), key=lambda x: x[1])]

    items_key = 'items' if 'items' in catalog else 'chapters'
    items = catalog.get(items_key, [])
    sec_map: dict[int, dict] = {}
    for item in items:
        idx = item.get('section_idx', 0)
        if idx not in sec_map:
            sec_map[idx] = {'idx': idx, 'title': item.get('section_title', '')}
    return sorted(sec_map.values(), key=lambda x: x['idx'])


def _get_items_by_section(catalog: dict) -> dict[int, list]:
    items_key = 'items' if 'items' in catalog else 'chapters'
    result: dict[int, list] = {}
    for item in catalog.get(items_key, []):
        sec_idx = item.get('section_idx', 0)
        if sec_idx not in result:
            result[sec_idx] = []
        result[sec_idx].append(item)
    return result


def _detect_content_type(dir_path: Path, items: list[dict]) -> str:
    for item in items[:5]:
        f = item.get('file', '')
        if not f:
            continue
        ext = Path(f).suffix.lower()
        if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            return 'comic'
        if ext in ('.md', '.txt'):
            return 'novel'
    return 'novel'


def _read_item_text(dir_path: Path, item: dict) -> str:
    f = item.get('file', '')
    if not f:
        return ''
    path = dir_path / f
    if not path.exists():
        return ''
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.md':
        text = _strip_md(text)
    return text


def convert_to_html(dir_path: str | Path, local_images: bool = True):
    dir_path = Path(dir_path)
    catalog = _load_catalog(dir_path)
    sections = _get_sections(catalog)
    items_by_sec = _get_items_by_section(catalog)
    title = catalog.get('title', dir_path.name)
    author = catalog.get('author', '')
    all_items = catalog.get('items', [])
    content_type = _detect_content_type(dir_path, all_items)
    cover_url = catalog.get('cover', '')

    css = """
:root {
  --bg: #fafaf9; --surface: #ffffff; --text: #1c1917; --text2: #57534e;
  --border: #e7e5e4; --accent: #b45309; --accent2: #d97706;
  --toc-w: 280px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
       background: var(--bg); color: var(--text); line-height: 1.9; }

.layout { display: flex; min-height: 100vh; }

/* TOC sidebar */
.toc { position: fixed; top: 0; left: 0; width: var(--toc-w); height: 100vh;
       overflow-y: auto; background: var(--surface); border-right: 1px solid var(--border);
       padding: 20px 16px; z-index: 100; transition: transform .3s; }
.toc-toggle { display: none; position: fixed; top: 12px; left: 12px; z-index: 200;
              background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
              padding: 6px 10px; cursor: pointer; font-size: 18px; }
.toc h2 { font-size: 14px; color: var(--text2); text-transform: uppercase; letter-spacing: .1em;
          margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.toc a { display: block; padding: 5px 8px; color: var(--text2); text-decoration: none;
         font-size: 13px; border-radius: 4px; white-space: nowrap; overflow: hidden;
         text-overflow: ellipsis; }
.toc a:hover { background: #f5f5f4; color: var(--text); }
.toc a.active { background: #fef3c7; color: var(--accent); font-weight: 600; }

/* Main content */
.main { margin-left: var(--toc-w); max-width: 800px; padding: 40px 32px; }

/* Header */
.novel-header { text-align: center; margin-bottom: 48px; padding-bottom: 32px;
                border-bottom: 1px solid var(--border); }
.novel-header h1 { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
.novel-header .author { font-size: 15px; color: var(--text2); }
.novel-header .meta { font-size: 12px; color: #a8a29e; margin-top: 8px; }
.novel-header .cover { max-width: 200px; margin: 16px auto; border-radius: 8px;
                       box-shadow: 0 4px 12px rgba(0,0,0,.1); }

/* Volume & Chapter */
.volume { margin-top: 48px; }
.volume > h2 { font-size: 20px; font-weight: 700; color: var(--accent);
               padding-bottom: 10px; border-bottom: 2px solid var(--accent2); margin-bottom: 20px; }
.chapter { margin-bottom: 32px; }
.chapter > h3 { font-size: 16px; font-weight: 600; color: var(--text); margin-bottom: 12px; }
.chapter p { text-indent: 2em; margin: 0.4em 0; }
.chapter img { max-width: 100%; height: auto; display: block; margin: 12px auto;
               border-radius: 4px; }

.generated { text-align: center; font-size: 12px; color: #a8a29e; margin-top: 20px; }
.generated a { color: #a8a29e; }

/* Print */
@media print {
  .toc, .toc-toggle { display: none !important; }
  .main { margin-left: 0; max-width: 100%; padding: 0; }
  .novel-header { page-break-after: always; }
  .volume > h2 { page-break-before: always; }
  .chapter { page-break-inside: avoid; }
  body { font-size: 11pt; line-height: 1.7; }
  a { color: var(--text); text-decoration: none; }
}
@media (max-width: 900px) {
  .toc { transform: translateX(-100%); }
  .toc.open { transform: translateX(0); box-shadow: 4px 0 20px rgba(0,0,0,.15); }
  .toc-toggle { display: block; }
  .main { margin-left: 0; }
}
"""

    html_parts = [f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_escape(title)}</title>
<style>{css}</style>
</head>
<body>
<button class="toc-toggle" onclick="document.querySelector('.toc').classList.toggle('open')">&#9776;</button>
<div class="layout">
<nav class="toc">
<h2>{html_escape(title)}</h2>
"""]

    for sec in sections:
        html_parts.append(f'<a href="#sec_{sec["idx"]:03d}">{html_escape(sec["title"])}</a>')
    html_parts.append('</nav><div class="main">')

    html_parts.append('<div class="novel-header">')
    if cover_url:
        html_parts.append(f'<img class="cover" src="{html_escape(cover_url)}" alt="{html_escape(title)}">')
    html_parts.append(f'<h1>{html_escape(title)}</h1>')
    if author:
        html_parts.append(f'<p class="author">{html_escape(author)}</p>')
    html_parts.append(f'<p class="meta">Generated by <a href="{_REPO_URL}">SFACG Spider</a></p>')
    html_parts.append('</div>')

    if content_type == 'comic' and not local_images:
        html_parts.append('<div class="warning">本文件使用远程图片URL，链接随时可能失效。</div>')

    for sec in sections:
        html_parts.append(f'<div class="volume" id="sec_{sec["idx"]:03d}">')
        html_parts.append(f'<h2>{html_escape(sec["title"])}</h2>')
        for item in items_by_sec.get(sec['idx'], []):
            ch_title = item.get('item_title', '')
            if ch_title:
                html_parts.append(f'<div class="chapter"><h3>{html_escape(ch_title)}</h3>')
            else:
                html_parts.append('<div class="chapter">')

            if content_type == 'comic':
                if local_images:
                    src = item.get('file', '')
                else:
                    src = item.get('item_url', '')
                html_parts.append(f'<img src="{html_escape(src)}" alt="" loading="lazy">')
            else:
                text = _read_item_text(dir_path, item)
                if text:
                    for para in text.split('\n'):
                        para = para.strip()
                        if not para:
                            continue
                        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', para)
                        if img_match:
                            alt, src = img_match.group(1), img_match.group(2)
                            if src.startswith('//'):
                                src = 'https:' + src
                            html_parts.append(f'<img src="{html_escape(src)}" alt="{html_escape(alt)}" loading="lazy">')
                        else:
                            html_parts.append(f'<p>{html_escape(para)}</p>')
            html_parts.append('</div>')
        html_parts.append('</div>')

    html_parts.append('</div></div></body></html>')

    html_file = dir_path / f'{_sanitize_filename(title)}.html'
    html_file.write_text('\n'.join(html_parts), encoding='utf-8')
    logger.bind(force=True).info(f'HTML: {html_file}')
    return html_file


def convert_to_epub(dir_path: str | Path, fetcher: Fetcher | None = None):
    try:
        from ebooklib import epub
    except ImportError:
        logger.error('需要安装 ebooklib: uv add ebooklib')
        return None

    dir_path = Path(dir_path)
    catalog = _load_catalog(dir_path)
    sections = _get_sections(catalog)
    items_by_sec = _get_items_by_section(catalog)
    title = catalog.get('title', dir_path.name)
    author = catalog.get('author', '')
    all_items = catalog.get('items', [])
    content_type = _detect_content_type(dir_path, all_items)
    fetcher = fetcher or Fetcher()

    book = epub.EpubBook()
    book.set_identifier(str(dir_path))
    book.set_title(title)
    book.set_language('zh')
    if author:
        book.add_author(author)

    cover_url = catalog.get('cover', '')
    if cover_url:
        try:
            book.set_cover('cover.jpg', fetcher.get_binary(cover_url))
        except Exception as e:
            logger.warning(f'封面下载失败: {e}')

    css = epub.EpubItem(
        uid='style', file_name='style/default.css', media_type='text/css',
        content=b'body { font-family: serif; line-height: 1.8; } h2 { margin-top: 2em; } p { text-indent: 2em; margin: 0.3em 0; }',
    )
    book.add_item(css)

    spine = ['nav']
    toc = []

    for sec in sections:
        ch_items = items_by_sec.get(sec['idx'], [])
        if not ch_items:
            continue

        ch_html = f'<h2>{html_escape(sec["title"])}</h2>'

        if content_type == 'comic':
            for item in ch_items:
                img_path = dir_path / item.get('file', '')
                if img_path.exists():
                    img_data = img_path.read_bytes()
                    fname = f'img_{sec["idx"]:03d}_{item.get("item_idx", 0):03d}{img_path.suffix}'
                    suffix = img_path.suffix.lower()
                    media_type = {
                        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.png': 'image/png', '.gif': 'image/gif',
                        '.webp': 'image/webp',
                    }.get(suffix, 'image/jpeg')
                    book.add_item(epub.EpubImage(
                        file_name=f'images/{fname}',
                        media_type=media_type,
                        content=img_data,
                    ))
                    ch_html += f'<img src="images/{fname}" alt="">'
        else:
            for item in ch_items:
                text = _read_item_text(dir_path, item)
                if text:
                    ch_title = item.get('item_title', '')
                    if ch_title:
                        ch_html += f'<h3>{html_escape(ch_title)}</h3>'
                    for para in text.split('\n'):
                        para = para.strip()
                        if para:
                            ch_html += f'<p>{html_escape(para)}</p>'

        page = epub.EpubHtml(
            title=sec['title'],
            file_name=f'ch_{sec["idx"]:03d}.xhtml',
            lang='zh',
            content=ch_html,
        )
        page.add_item(css)
        book.add_item(page)
        spine.append(page)
        toc.append(page)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub_path = dir_path / f'{_sanitize_filename(title)}.epub'
    epub.write_epub(str(epub_path), book)
    logger.bind(force=True).info(f'EPUB: {epub_path}')
    return epub_path


def convert_to_pdf(dir_path: str | Path, padding: int = 0, fetcher: Fetcher | None = None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    except ImportError:
        logger.error('需要安装 reportlab: uv add reportlab')
        return None

    dir_path = Path(dir_path)
    catalog = _load_catalog(dir_path)
    sections = _get_sections(catalog)
    items_by_sec = _get_items_by_section(catalog)
    title = catalog.get('title', dir_path.name)
    all_items = catalog.get('items', [])
    content_type = _detect_content_type(dir_path, all_items)

    if content_type != 'comic':
        logger.warning('PDF 仅支持漫画，小说请使用 txt/epub/html')
        return None

    pdf_path = dir_path / f'{_sanitize_filename(title)}.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    for sec in sections:
        ch_items = items_by_sec.get(sec['idx'], [])
        if not ch_items:
            continue
        c.setFont('STSong-Light', 16)
        c.drawCentredString(width / 2, height - 50, sec['title'])
        c.showPage()
        for item in ch_items:
            img_path = dir_path / item.get('file', '')
            if img_path.exists():
                try:
                    img = ImageReader(str(img_path))
                    img_width, img_height = img.getSize()
                    usable_width = width - 2 * padding
                    usable_height = height - 2 * padding
                    scale = min(usable_width / img_width, usable_height / img_height)
                    draw_width = img_width * scale
                    draw_height = img_height * scale
                    x = (width - draw_width) / 2
                    y = (height - draw_height) / 2
                    c.drawImage(img, x, y, draw_width, draw_height)
                    c.showPage()
                except Exception as e:
                    logger.warning(f'图片处理失败: {e}')
    c.save()
    logger.bind(force=True).info(f'PDF: {pdf_path}')
    return pdf_path


def convert(dir_path: str | Path, formats: list[str] | None = None, fetcher: Fetcher | None = None, padding: int = 0):
    if formats is None:
        formats = ['html', 'epub', 'pdf']

    results = {}
    for fmt in formats:
        if fmt == 'html':
            results['html'] = convert_to_html(dir_path, local_images=True)
        elif fmt == 'epub':
            results['epub'] = convert_to_epub(dir_path, fetcher)
        elif fmt == 'pdf':
            results['pdf'] = convert_to_pdf(dir_path, padding=padding, fetcher=fetcher)
        else:
            logger.warning(f'不支持的格式: {fmt}')

    return results


convert_comic = convert
