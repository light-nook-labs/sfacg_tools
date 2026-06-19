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


def _get_fetcher() -> Fetcher:
    f = Fetcher()
    f.auto_auth()
    return f


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def cmd_novel(args):
    from sfacglib.book import Novel
    f = _get_fetcher()
    tracker = ProgressTracker()
    novel = Novel(args.nid, fetcher=f)
    novel.download_novel(path=args.output, file_type=args.format, tracker=tracker)
    tracker.close()
    logger.bind(force=True).info(f'Done: {novel.title}')


def cmd_chapter(args):
    from sfacglib.ch import Chapter
    f = _get_fetcher()
    ch = Chapter(args.url, fetcher=f)
    md, html = ch.get_chapter_content()
    content = md if args.format == 'md' else html
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f'{_sanitize_filename(ch.title)}.{args.format}'
    path.write_text(content, encoding='utf-8')
    logger.bind(force=True).info(f'Done: {path}')


def cmd_comic(args):
    from sfacglib.comic import Comic
    f = _get_fetcher()
    comic = Comic(args.url, fetcher=f)
    comic.download(path=args.output)
    logger.bind(force=True).info(f'Done: {comic.title}')


def cmd_audio(args):
    from sfacglib.audio import Audio
    f = _get_fetcher()
    audio = Audio(args.id, fetcher=f)
    audio.download(path=args.output)
    logger.bind(force=True).info(f'Done: {audio.title}')


def cmd_review(args):
    import review as review_mod
    f = _get_fetcher()
    reviews = review_mod.BookReviews(args.url, save_dir=args.output, fetcher=f)
    reviews.download_reviews()


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
    import app
    app.main()


def main():
    parser = argparse.ArgumentParser(description='SFACG Spider')
    sub = parser.add_subparsers(dest='command')

    p_novel = sub.add_parser('novel', help='Download novel')
    p_novel.add_argument('nid', type=int, help='Novel ID')
    p_novel.add_argument('--format', '-f', default='epub', choices=['epub', 'md', 'html', 'txt'])
    p_novel.add_argument('--output', '-o', default='./')
    p_novel.set_defaults(func=cmd_novel)

    p_ch = sub.add_parser('chapter', help='Download single chapter')
    p_ch.add_argument('url', help='Chapter URL')
    p_ch.add_argument('--format', '-f', default='md', choices=['md', 'html'])
    p_ch.add_argument('--output', '-o', default='./')
    p_ch.set_defaults(func=cmd_chapter)

    p_comic = sub.add_parser('comic', help='Download comic')
    p_comic.add_argument('url', help='Comic URL')
    p_comic.add_argument('--output', '-o', default='./')
    p_comic.set_defaults(func=cmd_comic)

    p_audio = sub.add_parser('audio', help='Download audiobook')
    p_audio.add_argument('id', type=int, help='Audiobook ID')
    p_audio.add_argument('--output', '-o', default='./')
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

    p_app = sub.add_parser('app', help='Launch GUI')
    p_app.set_defaults(func=cmd_app)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
