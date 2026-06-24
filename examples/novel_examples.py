import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.novel import Novel


def demo_get_info():
    """获取小说信息"""
    novel = Novel(43708)
    info_md, info_html = novel.get_info()
    print(f'标题: {novel.title}')
    print(f'作者: {novel.author}')
    print(f'封面: {novel.cover[:80]}...')
    print(f'简介: {novel.intro[:100]}...')
    return novel


def demo_get_sections():
    """获取章节目录"""
    novel = Novel(43708)
    novel.get_info()
    sections = novel.get_sections()
    print(f'{novel.title} - 共 {len(sections)} 卷:')
    for vol in sections:
        items = vol.get_items()
        print(f'  第{vol.idx}卷 {vol.title} ({len(items)} 章)')
        for ch in items[:3]:
            vip_tag = ' [VIP]' if ch.vip else ''
            print(f'    {ch.idx}. {ch.title}{vip_tag}')
        if len(items) > 3:
            print(f'    ... 还有 {len(items) - 3} 章')
    return sections


def demo_download_epub():
    """下载小说为 EPUB"""
    novel = Novel(43708)
    output = Path('./output/novel_epub')
    novel.download(output, file_type='epub')
    print(f'EPUB 已保存到: {output}')


def demo_download_md():
    """下载小说为 Markdown 目录"""
    novel = Novel(43708)
    output = Path('./output/novel_md')
    novel.download(output, file_type='md')
    print(f'MD 目录已保存到: {output}')


def demo_download_html():
    """下载小说为 HTML"""
    novel = Novel(43708)
    output = Path('./output/novel_html')
    novel.download(output, file_type='html')
    print(f'HTML 已保存到: {output}')


def demo_download_txt():
    """下载小说为 TXT"""
    novel = Novel(43708)
    output = Path('./output/novel_txt')
    novel.download(output, file_type='txt')
    print(f'TXT 已保存到: {output}')


def demo_download_range():
    """只下载指定章节范围"""
    novel = Novel(43708)
    output = Path('./output/novel_range')
    novel.download(output, file_type='md', start_chapter='第一章', end_chapter='第十章')
    print(f'章节范围下载完成: {output}')


if __name__ == '__main__':
    demo_get_info()
    print()
    demo_get_sections()
