import re
from html import escape as html_escape
from io import BytesIO
from pathlib import Path

from loguru import logger

from ..fetcher import Fetcher
from . import fix_url_protocol, load_json
from . import sanitize_filename as _sanitize_filename
from .epub import _MEDIA_TYPES

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


def _detect_content_type(dir_path: Path, sections: list[dict]) -> str:
    for sec in sections[:5]:
        if sec.get('image_urls'):
            return 'comic'
        if sec.get('dir'):
            ch_path = dir_path / sec['dir']
            if ch_path.exists():
                img_files = list(ch_path.glob('page_*.jpg'))
                if img_files:
                    return 'comic'
        for item in sec.get('items', [])[:5]:
            file = item.get('file')
            if not file:
                continue
            ext = Path(file).suffix.lower()
            if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                return 'comic'
            if ext in ('.md', '.txt'):
                return 'novel'
    return 'novel'


def _is_page_comic(dir_path: Path, sections: list[dict]) -> bool:
    """检测是否为页漫（宽高比相近）。条漫（长竖图）返回 False。"""

    from PIL import Image

    aspect_ratios = []
    sample_count = 0

    for sec in sections[:3]:
        ch_dir = sec.get('dir')
        if ch_dir:
            ch_path = dir_path / ch_dir
            if ch_path.exists():
                img_files = sorted(ch_path.glob('page_*.*'))[:3]
                for img_file in img_files:
                    try:
                        img = Image.open(img_file)
                        w, h = img.size
                        aspect_ratios.append(w / h)
                        sample_count += 1
                        if sample_count >= 9:
                            break
                    except Exception:
                        pass
        if sample_count >= 9:
            break

    if len(aspect_ratios) < 2:
        return True

    avg = sum(aspect_ratios) / len(aspect_ratios)
    variance = sum((r - avg) ** 2 for r in aspect_ratios) / len(aspect_ratios)
    std_dev = variance**0.5

    # 页漫：宽高比相近（标准差小），且不是极端竖图
    # 条漫：宽高比差异大，或平均宽高比极小（<0.3 表示高度是宽度的3倍以上）
    if avg < 0.3:
        return False
    if std_dev > 0.15:
        return False
    return True


def _read_item_text(dir_path: Path, item: dict) -> str:
    file = item.get('file')
    if not file:
        return ''
    path = dir_path / file
    if not path.exists():
        return ''
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.md':
        text = _strip_md(text)
    return text


def convert_to_html(dir_path: str | Path, local_images: bool = False):
    dir_path = Path(dir_path)
    catalog = load_json(dir_path / 'catalog.json')
    title = catalog.get('title') or dir_path.name
    author = catalog.get('author')
    cover_url = catalog.get('cover')

    sections = catalog.get('sections', [])
    content_type = _detect_content_type(dir_path, sections)

    css = """
:root {
  --bg: #fafaf9; --surface: #ffffff; --text: #1c1917; --text2: #57534e;
  --border: #e7e5e4; --accent: #b45309; --accent2: #d97706;
  --toc-w: 260px; --content-max: 720px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; scroll-behavior: smooth; }
body { font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
       background: var(--bg); color: var(--text); line-height: 1.9; }

.layout { display: flex; min-height: 100vh; }

.toc { position: fixed; top: 0; left: 0; width: var(--toc-w); height: 100vh;
       overflow-y: auto; background: var(--surface); border-right: 1px solid var(--border);
       padding: 20px 14px; z-index: 100; transition: transform .3s ease; }
.toc::-webkit-scrollbar { width: 4px; }
.toc::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.toc-toggle { display: none; position: fixed; top: 10px; left: 10px; z-index: 200;
              background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
              width: 40px; height: 40px; cursor: pointer; font-size: 20px;
              box-shadow: 0 2px 8px rgba(0,0,0,.08); line-height: 40px; text-align: center; }
.toc-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.3); z-index: 99; }
.toc h2 { font-size: 13px; color: var(--text2); text-transform: uppercase; letter-spacing: .08em;
          margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.toc a { display: block; padding: 4px 8px; color: var(--text2); text-decoration: none;
         font-size: 13px; border-radius: 4px; white-space: nowrap; overflow: hidden;
         text-overflow: ellipsis; transition: background .15s; }
.toc a:hover { background: #f5f5f4; color: var(--text); }
.toc a.active { background: #fef3c7; color: var(--accent); font-weight: 600; }

.toc .vol-group { margin-bottom: 2px; }
.toc .vol-toggle { display: flex; align-items: center; gap: 6px; padding: 5px 8px;
                   color: var(--text2); font-size: 13px; border-radius: 4px; cursor: pointer;
                   user-select: none; text-decoration: none; width: 100%; border: none;
                   background: none; font-family: inherit; text-align: left; }
.toc .vol-toggle:hover { background: #f5f5f4; color: var(--text); }
.toc .vol-toggle .arrow { font-size: 10px; transition: transform .2s; flex-shrink: 0;
                          display: inline-block; width: 12px; }
.toc .vol-toggle.open .arrow { transform: rotate(90deg); }
.toc .vol-chapters { display: none; padding-left: 16px; }
.toc .vol-chapters.open { display: block; }
.toc .vol-chapters a { font-size: 12px; padding: 3px 8px; }

.main { margin-left: var(--toc-w); flex: 1; min-width: 0; padding: 40px 48px 60px; }
.main-inner { max-width: var(--content-max); margin: 0 auto; }

.novel-header { text-align: center; margin-bottom: 48px; padding-bottom: 32px;
                border-bottom: 1px solid var(--border); }
.novel-header .cover { max-width: 180px; margin: 0 auto 16px; border-radius: 8px;
                       box-shadow: 0 4px 16px rgba(0,0,0,.12); display: block; }
.novel-header h1 { font-size: 26px; font-weight: 700; margin-bottom: 4px; }
.novel-header .author { font-size: 15px; color: var(--text2); }
.novel-header .meta { font-size: 12px; color: #a8a29e; margin-top: 12px;
                      display: flex; align-items: center; justify-content: center; gap: 6px; }
.novel-header .meta a { color: #a8a29e; text-decoration: none; display: inline-flex;
                        align-items: center; gap: 4px; }
.novel-header .meta a:hover { color: var(--text2); }
.novel-header .meta img.org-logo { width: 16px; height: 16px; border-radius: 50%;
                                    vertical-align: middle; }

.volume { margin-top: 48px; }
.volume > h2 { font-size: 19px; font-weight: 700; color: var(--accent);
               padding-bottom: 8px; border-bottom: 2px solid var(--accent2); margin-bottom: 16px; }
.chapter { margin-bottom: 28px; }
.chapter > h3 { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 10px; }
.chapter p { text-indent: 2em; margin: 0.35em 0; }
.chapter img { max-width: 100%; height: auto; display: block; margin: 12px auto;
               border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }

.warning { background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 8px;
           margin-bottom: 20px; font-size: 14px; }

@media (max-width: 1024px) {
  :root { --toc-w: 220px; }
  .main { padding: 32px 24px 48px; }
}
@media (max-width: 768px) {
  .toc { transform: translateX(-100%); width: 280px; }
  .toc.open { transform: translateX(0); box-shadow: 4px 0 24px rgba(0,0,0,.18); }
  .toc-overlay.open { display: block; }
  .toc-toggle { display: block; }
  .main { margin-left: 0; padding: 56px 16px 40px; }
  .novel-header h1 { font-size: 22px; }
  .volume > h2 { font-size: 17px; }
  .chapter > h3 { font-size: 14px; }
  .chapter p { text-indent: 1.5em; }
}
@media (max-width: 480px) {
  .main { padding: 52px 12px 32px; }
  .novel-header .cover { max-width: 120px; }
  .novel-header h1 { font-size: 20px; }
}

.print-toc { display: none; }
@media print {
  .print-hint { display: none !important; }
  .toc, .toc-toggle, .toc-overlay { display: none !important; }
  .main { margin-left: 0; max-width: 100%; padding: 0; }
  .main-inner { max-width: 100%; }
  .novel-header { page-break-after: always; }
  .print-toc { display: block; page-break-after: always; }
  .print-toc h2 { font-size: 18pt; margin-bottom: 16pt; border-bottom: 2pt solid #333; padding-bottom: 6pt; }
  .print-toc .ptoc-vol { font-size: 12pt; margin-bottom: 6pt; }
  .novel-header .cover { width: 100%; max-width: 100%; margin: 0 auto; }
  .chapter .img-wrap { break-inside: avoid; page-break-inside: avoid; margin: 12px 0; }
  .chapter .img-wrap img { max-width: 80%; display: block; margin: 0 auto; }
  .chapter p { break-inside: avoid; page-break-inside: avoid; }
  .volume > h2 { page-break-before: always; }
  .chapter > h3 { break-after: avoid; page-break-after: avoid; }
  body { font-size: 11pt; line-height: 1.7; }
  a { color: var(--text); text-decoration: none; }
}
"""

    html_parts = [
        f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_escape(title)}</title>
<style>{css}</style>
</head>
<body>
<div class="toc-overlay" onclick="document.querySelector('.toc').classList.remove('open');this.classList.remove('open')"></div>
<button class="toc-toggle" onclick="document.querySelector('.toc').classList.toggle('open');document.querySelector('.toc-overlay').classList.toggle('open')">&#9776;</button>
<div class="layout">
<nav class="toc">
<h2><a href="#" style="color:inherit;text-decoration:none">{html_escape(title)}</a></h2>
"""
    ]

    for sec in catalog.get('sections', []):
        vol_title = sec.get('title', '')
        vol_display = re.sub(r'^【[^】]+】\s*', '', vol_title)
        sec_id = f'sec_{sec.get("idx", 0):03d}'
        ch_count = sum(1 for it in sec.get('items', []) if it.get('title'))
        html_parts.append('<div class="vol-group">')
        if ch_count > 0:
            html_parts.append(
                f'<button class="vol-toggle" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><span class="arrow">&#9654;</span>{html_escape(vol_display)}</button>'
            )
            html_parts.append('<div class="vol-chapters">')
            for it in sec.get('items', []):
                if it.get('title'):
                    html_parts.append(f'<a href="#{sec_id}_{it.get("idx", 0):03d}">{html_escape(it["title"])}</a>')
            html_parts.append('</div>')
        else:
            html_parts.append(
                f'<a href="#{sec_id}" class="vol-toggle" style="display:block">{html_escape(vol_display)}</a>'
            )
        html_parts.append('</div>')
    html_parts.append('</nav><div class="main"><div class="main-inner">')

    html_parts.append('<div class="novel-header">')
    if cover_url:
        html_parts.append(f'<img class="cover" src="{html_escape(cover_url)}" alt="{html_escape(title)}">')
    html_parts.append(f'<h1>{html_escape(title)}</h1>')
    if author:
        html_parts.append(f'<p class="author">{html_escape(author)}</p>')
    html_parts.append(
        f'<p class="meta">Generated by <a href="{_REPO_URL}"><img class="org-logo" src="https://github.com/light-nook-labs.png" alt="">SFACG Spider</a></p>'
    )
    html_parts.append('<p class="meta print-hint">按 Ctrl+P 可直接在浏览器中打印为 PDF</p>')
    html_parts.append('</div>')

    html_parts.append('<div class="print-toc"><h2>目录</h2>')
    for sec in catalog.get('sections', []):
        vol_display = re.sub(r'^【[^】]+】\s*', '', sec.get('title', ''))
        html_parts.append(f'<div class="ptoc-vol">{html_escape(vol_display)}</div>')
    html_parts.append('</div>')

    if content_type == 'comic' and not local_images:
        html_parts.append('<div class="warning">本文件使用远程图片URL，链接随时可能失效。</div>')

    for sec in catalog.get('sections', []):
        vol_display = re.sub(r'^【[^】]+】\s*', '', sec.get('title', ''))
        html_parts.append(f'<div class="volume" id="sec_{sec.get("idx", 0):03d}">')
        html_parts.append(f'<h2>{html_escape(vol_display)}</h2>')

        if content_type == 'comic':
            ch_dir = sec.get('dir')
            image_urls = sec.get('image_urls', [])
            if local_images:
                if ch_dir:
                    ch_path = dir_path / ch_dir
                    if ch_path.exists():
                        img_files = sorted(ch_path.glob('page_*.jpg'))
                        for img_file in img_files:
                            src = f'{ch_dir}/{img_file.name}'
                            html_parts.append(
                                f'<div class="img-wrap"><img src="{html_escape(src)}" alt="" loading="lazy"></div>'
                            )
            else:
                for url in image_urls:
                    html_parts.append(
                        f'<div class="img-wrap"><img src="{html_escape(url)}" alt="" loading="lazy"></div>'
                    )
        else:
            for item in sec.get('items', []):
                ch_id = f'sec_{sec.get("idx", 0):03d}_{item.get("idx", 0):03d}'
                if item.get('title'):
                    html_parts.append(f'<div class="chapter" id="{ch_id}"><h3>{html_escape(item["title"])}</h3>')
                else:
                    html_parts.append(f'<div class="chapter" id="{ch_id}">')

                text = _read_item_text(dir_path, item)
                if text:
                    for para in text.split('\n'):
                        para = para.strip()
                        if not para:
                            continue
                        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', para)
                        if img_match:
                            alt, src = img_match.group(1), img_match.group(2)
                            src = fix_url_protocol(src)
                            html_parts.append(
                                f'<div class="img-wrap"><img src="{html_escape(src)}" alt="{html_escape(alt)}" loading="lazy"></div>'
                            )
                        else:
                            html_parts.append(f'<p>{html_escape(para)}</p>')
                html_parts.append('</div>')
        html_parts.append('</div>')

    html_parts.append('</div></div></div></body></html>')

    html_file = dir_path.parent / f'{_sanitize_filename(title)}.html'
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
    catalog = load_json(dir_path / 'catalog.json')
    title = catalog.get('title') or dir_path.name
    author = catalog.get('author')
    fetcher = fetcher or Fetcher()
    local_images = True  # EPUB must use local images

    sections = catalog.get('sections', [])
    content_type = _detect_content_type(dir_path, sections)

    if content_type == 'comic' and not _is_page_comic(dir_path, sections):
        logger.warning('条漫无法生成 EPUB，跳过')
        return None

    book = epub.EpubBook()
    book.set_identifier(str(dir_path))
    book.set_title(title)
    book.set_language('zh')
    if author:
        book.add_author(author)

    if catalog.get('cover'):
        cover_file = catalog.get('cover_file', '')
        if cover_file:
            cover_path = dir_path / cover_file
            if cover_path.exists():
                try:
                    book.set_cover(cover_file, cover_path.read_bytes())
                except Exception as e:
                    logger.warning(f'封面加载失败: {e}')
            else:
                try:
                    book.set_cover('cover.jpg', fetcher.get_binary(catalog['cover']))
                except Exception as e:
                    logger.warning(f'封面下载失败: {e}')
        else:
            try:
                book.set_cover('cover.jpg', fetcher.get_binary(catalog['cover']))
            except Exception as e:
                logger.warning(f'封面下载失败: {e}')

    css = epub.EpubItem(
        uid='style',
        file_name='style/default.css',
        media_type='text/css',
        content=b'body { font-family: serif; line-height: 1.8; } h2 { margin-top: 2em; } p { text-indent: 2em; margin: 0.3em 0; }',
    )
    book.add_item(css)

    spine = ['nav']
    toc = []

    for sec in catalog.get('sections', []):
        ch_body = f'<h2>{html_escape(sec.get("title", ""))}</h2>'

        if content_type == 'comic':
            ch_dir = sec.get('dir')
            image_urls = sec.get('image_urls', [])
            if local_images:
                if ch_dir:
                    ch_path = dir_path / ch_dir
                    if ch_path.exists():
                        img_files = sorted(ch_path.glob('page_*.*'))
                        for img_file in img_files:
                            img_data = img_file.read_bytes()
                            fname = f'img_{sec.get("idx", 0):03d}_{img_file.name}'
                            suffix = img_file.suffix.lower()
                            media_type = _MEDIA_TYPES.get(suffix, 'image/jpeg')
                            book.add_item(
                                epub.EpubImage(
                                    file_name=f'images/{fname}',
                                    media_type=media_type,
                                    content=img_data,
                                )
                            )
                            ch_body += f'<img src="images/{fname}" alt=""/>'
            else:
                for url in image_urls:
                    try:
                        img_data = fetcher.get_binary(url)
                        fname = url.split('/')[-1]
                        suffix = Path(fname).suffix.lower() or '.jpg'
                        media_type = _MEDIA_TYPES.get(suffix, 'image/jpeg')
                        sec_idx = sec.get('idx', 0)
                        epub_fname = f'img_{sec_idx:03d}_{fname}'
                        book.add_item(
                            epub.EpubImage(
                                file_name=f'images/{epub_fname}',
                                media_type=media_type,
                                content=img_data,
                            )
                        )
                        ch_body += f'<img src="images/{epub_fname}" alt=""/>'
                    except Exception as e:
                        logger.warning(f'图片下载失败: {url}: {e}')
        else:
            for item in sec.get('items', []):
                text = _read_item_text(dir_path, item)
                if text:
                    if item.get('title'):
                        ch_body += f'<h3>{html_escape(item["title"])}</h3>'
                    for para in text.split('\n'):
                        para = para.strip()
                        if para:
                            ch_body += f'<p>{html_escape(para)}</p>'

        ch_html = f"""<html><head><style>{css.content.decode('utf-8')}</style></head><body>{ch_body}</body></html>"""
        page = epub.EpubHtml(
            title=sec.get('title', ''),
            file_name=f'ch_{sec.get("idx", 0):03d}.xhtml',
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

    epub_path = dir_path.parent / f'{_sanitize_filename(title)}.epub'
    epub.write_epub(str(epub_path), book)
    logger.bind(force=True).info(f'EPUB: {epub_path}')
    return epub_path


def convert_to_pdf(dir_path: str | Path, padding: int = 0, fetcher: Fetcher | None = None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas

        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    except ImportError:
        logger.error('需要安装 reportlab: uv add reportlab')
        return None

    dir_path = Path(dir_path)
    catalog = load_json(dir_path / 'catalog.json')
    title = catalog.get('title') or dir_path.name

    sections = catalog.get('sections', [])
    content_type = _detect_content_type(dir_path, sections)

    if content_type != 'comic':
        logger.warning('PDF 仅支持漫画，小说请使用 txt/epub/html')
        return None

    if not _is_page_comic(dir_path, sections):
        logger.warning('条漫无法生成 PDF，跳过')
        return None

    fetcher = fetcher or Fetcher()
    pdf_path = dir_path.parent / f'{_sanitize_filename(title)}.pdf'
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4

    if catalog.get('cover'):
        cover_file = catalog.get('cover_file', '')
        cover_data = None
        if cover_file:
            cover_path = dir_path / cover_file
            if cover_path.exists():
                cover_data = cover_path.read_bytes()
        if not cover_data:
            try:
                cover_data = fetcher.get_binary(catalog['cover'])
            except Exception as e:
                logger.warning(f'封面下载失败: {e}')
        if cover_data:
            try:
                cover_img = ImageReader(BytesIO(cover_data))
                img_width, img_height = cover_img.getSize()
                max_cover_height = height * 0.5
                max_cover_width = width * 0.4
                scale = min(max_cover_width / img_width, max_cover_height / img_height)
                draw_width = img_width * scale
                draw_height = img_height * scale
                x = (width - draw_width) / 2
                y = height * 0.55
                c.drawImage(cover_img, x, y, draw_width, draw_height)

                c.setFont('STSong-Light', 28)
                c.drawCentredString(width / 2, height * 0.42, title)

                if catalog.get('author'):
                    c.setFont('STSong-Light', 16)
                    c.drawCentredString(width / 2, height * 0.37, f'作者：{catalog["author"]}')

                c.setFont('STSong-Light', 10)
                c.drawCentredString(width / 2, height * 0.05, 'Generated by SFACG Spider')

                c.showPage()
            except Exception as e:
                logger.warning(f'封面处理失败: {e}')

    for sec in catalog.get('sections', []):
        c.setFont('STSong-Light', 24)
        c.drawCentredString(width / 2, height / 2, sec.get('title', ''))
        c.showPage()

        if content_type == 'comic':
            ch_dir = sec.get('dir')
            if ch_dir:
                ch_path = dir_path / ch_dir
                if ch_path.exists():
                    img_files = sorted(ch_path.glob('page_*.jpg'))
                    for img_file in img_files:
                        try:
                            img = ImageReader(str(img_file))
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
        else:
            for item in sec.get('items', []):
                file = item.get('file')
                if not file:
                    continue
                img_path = dir_path / file
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


def convert_to_txt(dir_path: str | Path):
    dir_path = Path(dir_path)
    catalog = load_json(dir_path / 'catalog.json')
    title = catalog.get('title') or dir_path.name

    parts = []
    for sec in catalog.get('sections', []):
        vol_title = sec.get('title', '')
        if vol_title:
            parts.append('## ' + vol_title)
        for item in sec.get('items', []):
            ch_title = item.get('title', '')
            if ch_title:
                parts.append('### ' + ch_title)
            text = _read_item_text(dir_path, item)
            if text:
                parts.append(text)

    txt_content = '\n\n'.join(parts)
    txt_path = dir_path.parent / f'{_sanitize_filename(title)}.txt'
    txt_path.write_text(txt_content, encoding='utf-8')
    logger.bind(force=True).info(f'TXT: {txt_path}')
    return txt_path


def convert(dir_path: str | Path, formats: list[str] | None = None, fetcher: Fetcher | None = None, padding: int = 0):
    if formats is None:
        formats = ['html', 'epub', 'pdf']

    results = {}
    for fmt in formats:
        if fmt == 'html':
            results['html'] = convert_to_html(dir_path, local_images=False)
        elif fmt == 'epub':
            results['epub'] = convert_to_epub(dir_path, fetcher)
        elif fmt == 'pdf':
            results['pdf'] = convert_to_pdf(dir_path, padding=padding, fetcher=fetcher)
        elif fmt == 'txt':
            results['txt'] = convert_to_txt(dir_path)
        else:
            logger.warning(f'不支持的格式: {fmt}')

    return results
