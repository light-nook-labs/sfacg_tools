import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.ocr_fast import ocr_image, ocr_gif, remove_pinyin


def demo_ocr_image():
    """OCR 识别单张图片"""
    image_path = Path(__file__).parent.parent / 'common.gif'
    if not image_path.exists():
        print(f'测试图片不存在: {image_path}')
        return

    text = ocr_image(str(image_path))
    print(f'OCR 结果 ({len(text)} 字符):')
    print(text[:500])
    return text


def demo_ocr_gif():
    """OCR 识别 VIP GIF（多帧）"""
    gif_path = Path(__file__).parent.parent / 'common.gif'
    if not gif_path.exists():
        print(f'测试 GIF 不存在: {gif_path}')
        return

    gif_bytes = gif_path.read_bytes()
    text = ocr_gif(gif_bytes)
    print(f'GIF OCR 结果 ({len(text)} 字符):')
    print(text[:500])
    return text


def demo_remove_pinyin():
    """去除 VIP GIF 中的拼音标注"""
    gif_path = Path(__file__).parent.parent / 'common.gif'
    if not gif_path.exists():
        print(f'测试 GIF 不存在: {gif_path}')
        return

    gif_bytes = gif_path.read_bytes()
    # 返回去除拼音后的 PIL Image 列表（每帧一张）
    frames = remove_pinyin(gif_bytes)
    print(f'处理完成，共 {len(frames)} 帧')
    # 保存第一帧查看效果
    if frames:
        output = Path('./output/pinyin_removed.png')
        output.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(str(output))
        print(f'已保存到: {output}')
    return frames


if __name__ == '__main__':
    demo_ocr_image()
    print()
    demo_remove_pinyin()
