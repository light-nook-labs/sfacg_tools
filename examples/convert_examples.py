import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.convert import convert, convert_to_html, convert_to_epub, convert_to_pdf


def demo_convert_batch():
    """批量转换（自动检测小说/漫画）"""
    dir_path = Path('./output/落樱之剑')
    if not dir_path.exists():
        print(f'目录不存在: {dir_path}')
        print('请先下载小说: uv run python main.py novel 43708 -o ./output/')
        return

    results = convert(str(dir_path), formats=['html', 'epub'])
    print('转换结果:')
    for fmt, path in results.items():
        print(f'  {fmt}: {path}')
    return results


def demo_convert_to_html():
    """转换为 HTML"""
    dir_path = Path('./output/落樱之剑')
    if not dir_path.exists():
        print(f'目录不存在: {dir_path}')
        return

    output = convert_to_html(str(dir_path), local_images=True)
    print(f'HTML 已生成: {output}')
    return output


def demo_convert_to_epub():
    """转换为 EPUB"""
    dir_path = Path('./output/落樱之剑')
    if not dir_path.exists():
        print(f'目录不存在: {dir_path}')
        return

    output = convert_to_epub(str(dir_path))
    print(f'EPUB 已生成: {output}')
    return output


def demo_convert_to_pdf():
    """漫画转换为 PDF"""
    dir_path = Path('./output/漫画目录')
    if not dir_path.exists():
        print(f'目录不存在: {dir_path}')
        print('请先下载漫画: uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -o ./output/')
        return

    output = convert_to_pdf(str(dir_path))
    print(f'PDF 已生成: {output}')
    return output


if __name__ == '__main__':
    demo_convert_batch()
