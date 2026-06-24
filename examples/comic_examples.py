import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.comic import Comic


def demo_get_info():
    """获取漫画信息"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    info_md, info_html = comic.get_info()
    print(f'标题: {comic.title}')
    print(f'作者: {comic.author}')
    print(f'封面: {comic.cover[:80]}...')
    return comic


def demo_get_sections():
    """获取漫画章节列表"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    comic.get_info()
    sections = comic.get_sections()
    print(f'{comic.title} - 共 {len(sections)} 卷:')
    for vol in sections:
        print(f'  第{vol.idx}卷 {vol.title}')
        for ch in vol.items[:3]:
            print(f'    {ch.idx}. {ch.title}')
        if len(vol.items) > 3:
            print(f'    ... 还有 {len(vol.items) - 3} 章')
    return sections


def demo_download_dir():
    """下载漫画为目录（默认）"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    output = Path('./output/comic_dir')
    comic.download(output, file_type='dir')
    print(f'漫画目录已保存到: {output}')


def demo_download_html():
    """下载漫画为 HTML"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    output = Path('./output/comic_html')
    comic.download(output, file_type='html')
    print(f'HTML 已保存到: {output}')


def demo_download_epub():
    """下载漫画为 EPUB"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    output = Path('./output/comic_epub')
    comic.download(output, file_type='epub')
    print(f'EPUB 已保存到: {output}')


def demo_download_pdf():
    """下载漫画为 PDF"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    output = Path('./output/comic_pdf')
    comic.download(output, file_type='pdf')
    print(f'PDF 已保存到: {output}')


def demo_export_html_remote():
    """导出漫画为 HTML（使用远程图片）"""
    comic = Comic('https://manhua.sfacg.com/mh/LYZJ/')
    output = Path('./output/comic_remote.html')
    comic.export_html(output, local_images=False)
    print(f'远程图片 HTML 已保存到: {output}')


if __name__ == '__main__':
    demo_get_info()
    print()
    demo_get_sections()
