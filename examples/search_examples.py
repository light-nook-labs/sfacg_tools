import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.search import search_novel, search_comic, search_api, get_related, get_author_works
from sfacglib.models import SearchItem


def demo_search_novel():
    """HTML 搜索小说"""
    results = search_novel('魔法少女')
    print(f'找到 {len(results)} 本小说:')
    for idx, r in enumerate(results, start=1):
        print(f'[{idx}] {r.title}#{r.id} - {r.author}')
        if r.snippet:
            print(f'{r.snippet[:10]}...')
        print()

def demo_search_comic():
    """HTML 搜索漫画"""
    results = search_comic('魔法')
    print(f'找到 {len(results)} 部漫画:')
    for idx, r in enumerate(results, start=1):
        print(f'[{idx}] {r.title} - {r.author}')


def demo_search_api():
    """JSON API 搜索（带评分）"""
    results = search_api('转生')
    print(f'API 搜索找到 {len(results)} 本:')
    for r in results:
        score = r.score or '无评分'
        print(f'  [{r.id}] {r.title} - {r.author} (评分: {score})')


def demo_get_related():
    """获取相关推荐"""
    novel_id = '43708'
    results = get_related(novel_id)
    print(f'小说 {novel_id} 的相关推荐 ({len(results)} 本):')
    for r in results:
        print(f'  [{r.id}] {r.title} - {r.author}')


def demo_get_author_works():
    """获取作者其他作品"""
    novel_id = '43708'
    results = get_author_works(novel_id)
    print(f'小说 {novel_id} 作者的其他作品 ({len(results)} 本):')
    for r in results:
        print(f'  [{r.id}] {r.title}')


if __name__ == '__main__':
    # demo_search_novel()
    # demo_search_comic()
    # demo_search_api()
    demo_get_related()
    demo_get_author_works()