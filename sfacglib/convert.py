import json
from pathlib import Path
from bs4 import BeautifulSoup
from loguru import logger
from .base import _sanitize_filename
from .fetcher import Fetcher


def _load_catalog(dir_path: Path) -> dict:
    catalog_path = dir_path / 'catalog.json'
    if not catalog_path.exists():
        raise FileNotFoundError(f'未找到 catalog.json: {dir_path}')
    return json.loads(catalog_path.read_text(encoding='utf-8'))


def _get_sections(catalog: dict) -> list[dict]:
    sections = catalog.get('sections', [])
    if not sections:
        sec_map: dict[int, dict] = {}
        for item in catalog.get('items', []):
            idx = item.get('section_idx', 0)
            if idx not in sec_map:
                sec_map[idx] = {'idx': idx, 'title': item.get('section_title', '')}
        sections = sorted(sec_map.values(), key=lambda x: x['idx'])
    return sections


def _get_items_by_section(catalog: dict) -> dict[int, list]:
    result: dict[int, list] = {}
    for item in catalog.get('items', []):
        sec_idx = item.get('section_idx', 0)
        if sec_idx not in result:
            result[sec_idx] = []
        result[sec_idx].append(item)
    return result


def convert_to_html(dir_path: str | Path, local_images: bool = True):
    dir_path = Path(dir_path)
    catalog = _load_catalog(dir_path)
    sections = _get_sections(catalog)
    items_by_sec = _get_items_by_section(catalog)
    title = catalog.get('title', dir_path.name)

    html_parts = [f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
h1 {{ text-align: center; color: #333; }}
h2 {{ color: #666; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
.chapter {{ margin-bottom: 40px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
img {{ max-width: 100%; height: auto; display: block; margin: 10px auto; }}
.toc {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
.toc a {{ display: block; padding: 8px; color: #0066cc; text-decoration: none; }}
.toc a:hover {{ background: #f0f0f0; }}
.warning {{ background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>{title}</h1>
"""]

    if not local_images:
        html_parts.append('<div class="warning">⚠️ 本文件使用远程图片URL，链接随时可能失效。</div>')

    html_parts.append('<div class="toc"><h2>目录</h2>')
    for sec in sections:
        html_parts.append(f'<a href="#ch_{sec["idx"]:03d}">{sec["title"]}</a>')
    html_parts.append('</div>')

    for sec in sections:
        html_parts.append(f'<div class="chapter" id="ch_{sec["idx"]:03d}">')
        html_parts.append(f'<h2>{sec["title"]}</h2>')
        for item in items_by_sec.get(sec['idx'], []):
            if local_images:
                src = item.get('file', '')
            else:
                src = item.get('item_url', '')
            html_parts.append(f'<img src="{src}" alt="" loading="lazy">')
        html_parts.append('</div>')

    html_parts.append('</body></html>')

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
    fetcher = fetcher or Fetcher()

    book = epub.EpubBook()
    book.set_identifier(str(dir_path))
    book.set_title(title)
    book.set_language('zh')

    cover_url = catalog.get('cover', '')
    if cover_url:
        try:
            book.set_cover('cover.jpg', fetcher.get_binary(cover_url))
        except Exception:
            pass

    spine = ['nav']
    toc = []

    for sec in sections:
        ch_items = items_by_sec.get(sec['idx'], [])
        if not ch_items:
            continue

        ch_html = f'<h2>{sec["title"]}</h2>'
        for item in ch_items:
            img_path = dir_path / item.get('file', '')
            if img_path.exists():
                img_data = img_path.read_bytes()
                fname = f'img_{sec["idx"]:03d}_{item.get("item_idx", 0):03d}.jpg'
                book.add_item(epub.EpubImage(
                    file_name=f'images/{fname}',
                    media_type='image/jpeg',
                    content=img_data,
                ))
                ch_html += f'<img src="images/{fname}" alt="">'

        page = epub.EpubHtml(
            title=sec['title'],
            file_name=f'ch_{sec["idx"]:03d}.xhtml',
            lang='zh',
            content=ch_html,
        )
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


def convert_to_pdf(dir_path: str | Path, padding: int = 0):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        logger.error('需要安装 reportlab: uv add reportlab')
        return None

    dir_path = Path(dir_path)
    catalog = _load_catalog(dir_path)
    sections = _get_sections(catalog)
    items_by_sec = _get_items_by_section(catalog)
    title = catalog.get('title', dir_path.name)

    pdf_path = dir_path / f'{_sanitize_filename(title)}.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    for sec in sections:
        ch_items = items_by_sec.get(sec['idx'], [])
        if not ch_items:
            continue

        c.setFont('Helvetica-Bold', 16)
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


def convert_comic(dir_path: str | Path, formats: list[str] | None = None, fetcher: Fetcher | None = None, padding: int = 0):
    if formats is None:
        formats = ['html', 'epub', 'pdf']

    results = {}
    for fmt in formats:
        if fmt == 'html':
            results['html'] = convert_to_html(dir_path, local_images=True)
        elif fmt == 'epub':
            results['epub'] = convert_to_epub(dir_path, fetcher)
        elif fmt == 'pdf':
            results['pdf'] = convert_to_pdf(dir_path, padding=padding)
        else:
            logger.warning(f'不支持的格式: {fmt}')

    return results
