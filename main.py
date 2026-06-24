"""SFACG Spider - CLI entry point.

Usage:
    uv run python main.py novel <nid> [--format epub|md|html|txt] [--output DIR]
    uv run python main.py chapter <url> [--format md|html]
    uv run python main.py comic <url> [--output DIR]
    uv run python main.py audio <id> [--output DIR]
    uv run python main.py review <url> [--output DIR]
    uv run python main.py audiolist [--start ID] [--end ID]
    uv run python main.py status
    uv run python main.py cleanup
    uv run python main.py app
"""
import sys
import re
import argparse
from pathlib import Path
from loguru import logger
from sfacglib.fetcher import Fetcher
from sfacglib.progress import ProgressTracker
from sfacglib.utils import sanitize_filename


def _get_fetcher() -> Fetcher:
    f = Fetcher()
    f.auto_auth()
    return f


def cmd_novel(args):
    from sfacglib.novel import Novel
    f = _get_fetcher()
    tracker = ProgressTracker()
    novel = Novel(args.nid, fetcher=f)
    novel.download_novel(
        path=args.output,
        file_type=args.format,
        tracker=tracker,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        chapter_range=args.chapters,
        volume_filter=args.volumes,
        download_reviews=args.reviews,
    )
    tracker.close()
    logger.bind(force=True).info(f'Done: {novel.title}')


def cmd_chapter(args):
    from sfacglib.novel import NovelChapter
    f = _get_fetcher()
    ch = NovelChapter(url=args.url, fetcher=f)
    md, html = ch.get_chapter_content()
    content = md if args.format == 'md' else html
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f'{sanitize_filename(ch.title)}.{args.format}'
    path.write_text(content, encoding='utf-8')
    logger.bind(force=True).info(f'Done: {path}')


def cmd_comic(args):
    from sfacglib.comic import Comic
    f = _get_fetcher()
    tracker = ProgressTracker()
    comic = Comic(args.url, fetcher=f)
    comic.download(
        path=args.output,
        file_type=args.format,
        local_images=not args.url_mode,
        tracker=tracker,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        chapter_range=args.chapters,
    )
    tracker.close()
    logger.bind(force=True).info(f'Done: {comic.title}')


def cmd_convert(args):
    from sfacglib.convert import convert_comic
    f = _get_fetcher()
    formats = args.formats.split(',') if args.formats else ['html', 'epub', 'pdf']
    convert_comic(args.dir, formats=formats, fetcher=f, padding=args.padding)


def cmd_audio(args):
    from sfacglib.audio import Audio
    f = _get_fetcher()
    tracker = ProgressTracker()
    audio = Audio(args.id, fetcher=f)
    audio.download(
        path=args.output,
        tracker=tracker,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        chapter_range=args.chapters,
        volume_filter=args.volumes,
    )
    tracker.close()
    logger.bind(force=True).info(f'Done: {audio.title}')


def cmd_review(args):
    from sfacglib.novel import Novel
    f = _get_fetcher()
    nid_match = re.search(r'(\d+)', args.url)
    if not nid_match:
        logger.error('无法提取小说ID')
        return
    novel = Novel(int(nid_match.group(1)), fetcher=f)
    novel.download_novel(
        path=args.output,
        file_type='md',
        download_reviews=True,
    )
    logger.bind(force=True).info(f'Done: {novel.title}')


def cmd_audiolist(args):
    from sfacglib.audio import Audio
    f = _get_fetcher()
    result = Audio.scan(start=args.start, end=args.end, fetcher=f)
    logger.bind(force=True).info(f'Found {len(result)} audiobooks')


def cmd_status(args):
    tracker = ProgressTracker()
    tasks = tracker.list_tasks()
    if not tasks:
        print('No tasks')
    else:
        print(f'{"ID":<20} {"Type":<8} {"Title":<25} {"Done":>6} {"Total":>6} {"Status":<8}')
        print('-' * 80)
        for t in tasks:
            print(f'{t["id"]:<20} {t["type"]:<8} {t["title"][:25]:<25} {t["done"]:>6} {t["total"]:>6} {t["status"]:<8}')
    tracker.close()


def cmd_cleanup(args):
    tracker = ProgressTracker()
    count = tracker.cleanup_done()
    tracker.close()
    logger.bind(force=True).info(f'清理完成，删除 {count} 个已完成任务')


def cmd_app(args):
    from sfacglib.ui import run_pc
    run_pc()


def cmd_mobile(args):
    from sfacglib.ui import run_mobile
    run_mobile(target=args.target)


def cmd_web(args):
    from sfacglib.ui import run_web
    run_web(host=args.host, port=args.port)


def cmd_search(args):
    from sfacglib.search import search, search_api, get_related, get_author_works
    if args.related:
        results = get_related(args.keyword)
    elif args.author_works:
        results = get_author_works(args.keyword)
    elif args.api:
        results = search_api(args.keyword)
    else:
        search_type = 'comic' if args.comic else 'novel'
        results = search(args.keyword, search_type)
    if not results:
        logger.bind(force=True).info('No results found')
        return
    for i, r in enumerate(results, 1):
        score = f' ({r.score})' if r.score else ''
        print(f'{i:2}. [{r.id}] {r.title}{score}')
        if r.author:
            print(f'    Author: {r.author}  Updated: {r.updated}')
        if r.snippet:
            print(f'    {r.snippet[:80]}...')
        print(f'    {r.url}')
        print()


def cmd_ocr(args):
    from sfacglib.ocr_fast import ocr_image
    text = ocr_image(args.source, workers=args.workers)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        logger.bind(force=True).info(f'Done: {out}')
    else:
        print(text)


def cmd_ocr_preprocess(args):
    from sfacglib.ocr_fast import remove_pinyin_gif
    source = Path(args.source)
    if not source.exists():
        logger.error(f'Not found: {source}')
        return
    gif_bytes = source.read_bytes()
    img = remove_pinyin_gif(gif_bytes)
    out = Path(args.output) if args.output else source.with_name(source.stem + '_de_pinyin.png')
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    logger.bind(force=True).info(f'Done: {out} ({img.width}x{img.height})')


def cmd_chat(args):
    from sfacglib.chatbot import interactive_chat
    interactive_chat()


def cmd_ocr_fix(args):
    from sfacglib.chatbot import ChatBot
    bot = ChatBot()
    target = Path(args.target)
    if target.is_file():
        out = bot.correct_ocr_file(str(target), args.output or '', args.context)
        logger.bind(force=True).info(f'Done: {out}')
    elif target.is_dir():
        results = bot.correct_ocr_dir(str(target), args.pattern, args.context)
        logger.bind(force=True).info(f'Done: {len(results)} files corrected')
    else:
        logger.error(f'Not found: {target}')


def main():
    parser = argparse.ArgumentParser(description='SFACG Spider')
    sub = parser.add_subparsers(dest='command')

    p_novel = sub.add_parser('novel', help='Download novel')
    p_novel.add_argument('nid', type=int, help='Novel ID')
    p_novel.add_argument('--format', '-f', default='epub', choices=['epub', 'md', 'html', 'txt'])
    p_novel.add_argument('--output', '-o', default='./')
    p_novel.add_argument('--start-chapter', '-sc', help='Start from this chapter (title or ID)')
    p_novel.add_argument('--end-chapter', '-ec', help='End at this chapter (title or ID)')
    p_novel.add_argument('--chapters', '-c', help='Chapter range: "1,3-5,10" or "title1,title2"')
    p_novel.add_argument('--volumes', '-v', help='Volume filter: "vol1,vol2"')
    p_novel.add_argument('--reviews', '-r', action='store_true', help='Download reviews along with novel')
    p_novel.set_defaults(func=cmd_novel)

    p_ch = sub.add_parser('chapter', help='Download single chapter')
    p_ch.add_argument('url', help='Chapter URL')
    p_ch.add_argument('--format', '-f', default='md', choices=['md', 'html'])
    p_ch.add_argument('--output', '-o', default='./')
    p_ch.set_defaults(func=cmd_chapter)

    p_comic = sub.add_parser('comic', help='Download comic')
    p_comic.add_argument('url', help='Comic URL')
    p_comic.add_argument('--format', '-f', default='dir', choices=['dir', 'html', 'epub', 'pdf'], help='Output format')
    p_comic.add_argument('--url-mode', action='store_true', help='Use URL instead of local images (HTML only, URLs may expire)')
    p_comic.add_argument('--output', '-o', default='./')
    p_comic.add_argument('--start-chapter', '-sc', help='Start from this chapter (title or ID)')
    p_comic.add_argument('--end-chapter', '-ec', help='End at this chapter (title or ID)')
    p_comic.add_argument('--chapters', '-c', help='Chapter range: "1,3-5,10" or "title1,title2"')
    p_comic.set_defaults(func=cmd_comic)

    p_convert = sub.add_parser('convert', help='Convert downloaded comic to other formats')
    p_convert.add_argument('dir', help='Comic directory path')
    p_convert.add_argument('--formats', '-f', default='html,epub,pdf', help='Output formats, comma separated')
    p_convert.add_argument('--padding', '-p', type=int, default=0, help='PDF padding in points (default: 0)')
    p_convert.set_defaults(func=cmd_convert)

    p_audio = sub.add_parser('audio', help='Download audiobook')
    p_audio.add_argument('id', type=int, help='Audiobook ID')
    p_audio.add_argument('--output', '-o', default='./')
    p_audio.add_argument('--start-chapter', '-sc', help='Start from this chapter (title or ID)')
    p_audio.add_argument('--end-chapter', '-ec', help='End at this chapter (title or ID)')
    p_audio.add_argument('--chapters', '-c', help='Chapter range: "1,3-5,10" or "title1,title2"')
    p_audio.add_argument('--volumes', '-v', help='Volume filter: "vol1,vol2"')
    p_audio.set_defaults(func=cmd_audio)

    p_review = sub.add_parser('review', help='Download reviews')
    p_review.add_argument('url', help='Novel URL')
    p_review.add_argument('--output', '-o', default='./')
    p_review.set_defaults(func=cmd_review)

    p_alist = sub.add_parser('audiolist', help='Scan audiobook list')
    p_alist.add_argument('--start', type=int, default=0)
    p_alist.add_argument('--end', type=int, default=500)
    p_alist.set_defaults(func=cmd_audiolist)

    p_status = sub.add_parser('status', help='Show download progress')
    p_status.set_defaults(func=cmd_status)

    p_cleanup = sub.add_parser('cleanup', help='Clean up completed tasks')
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_app = sub.add_parser('app', help='Launch PC GUI')
    p_app.set_defaults(func=cmd_app)

    p_mobile = sub.add_parser('mobile', help='Launch mobile UI (Flet/Flutter)')
    p_mobile.add_argument('--target', default='app', choices=['app', 'apk'], help='Target: app (web) or apk (Flutter)')
    p_mobile.set_defaults(func=cmd_mobile)

    p_web = sub.add_parser('web', help='Launch web UI')
    p_web.add_argument('--host', default='127.0.0.1', help='Host to bind')
    p_web.add_argument('--port', type=int, default=8888, help='Port to bind')
    p_web.set_defaults(func=cmd_web)

    p_search = sub.add_parser('search', help='Search novels or comics by keyword')
    p_search.add_argument('keyword', help='Search keyword or novel ID (for --related/--author-works)')
    p_search.add_argument('--comic', '-c', action='store_true', help='Search comics instead of novels')
    p_search.add_argument('--api', action='store_true', help='Use JSON API (faster, returns scores)')
    p_search.add_argument('--related', '-r', action='store_true', help='Get related novels (keyword = novel ID)')
    p_search.add_argument('--author-works', '-a', action='store_true', help='Get author works (keyword = novel ID)')
    p_search.set_defaults(func=cmd_search)

    p_ocr = sub.add_parser('ocr', help='OCR image to text')
    p_ocr.add_argument('source', help='Image URL or local path')
    p_ocr.add_argument('--output', '-o', help='Output file path')
    p_ocr.add_argument('--workers', type=int, default=4, help='OCR threads')
    p_ocr.set_defaults(func=cmd_ocr)

    p_pre = sub.add_parser('ocr-preprocess', help='Remove pinyin from VIP GIF (no OCR, fast)')
    p_pre.add_argument('source', help='GIF file path')
    p_pre.add_argument('--output', '-o', help='Output image path (default: *_de_pinyin.png)')
    p_pre.set_defaults(func=cmd_ocr_preprocess)

    p_chat = sub.add_parser('chat', help='Interactive chat with LLM (tool-calling agent)')
    p_chat.set_defaults(func=cmd_chat)

    p_ocrfix = sub.add_parser('ocr-fix', help='Correct OCR text using LLM')
    p_ocrfix.add_argument('target', help='File or directory to correct')
    p_ocrfix.add_argument('--output', '-o', help='Output file path (single file mode)')
    p_ocrfix.add_argument('--pattern', default='*.txt', help='File glob pattern for dir mode (default: *.txt)')
    p_ocrfix.add_argument('--context', '-c', default='', help='Context about the content (genre, names, etc.)')
    p_ocrfix.set_defaults(func=cmd_ocr_fix)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
