import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.audio import Audio


def demo_list_all():
    """列出所有缓存的有声小说"""
    audiobooks = Audio.list_all()
    print(f'共 {len(audiobooks)} 本有声小说:')
    for book in audiobooks[:10]:
        print(f'  [{book["id"]}] {book["title"]}')
    if len(audiobooks) > 10:
        print(f'  ... 还有 {len(audiobooks) - 10} 本')
    return audiobooks


def demo_scan():
    """扫描有声小说（耗时较长）"""
    # 扫描 ID 1-50 范围
    results = Audio.scan(start=0, end=50, workers=10)
    print(f'扫描完成，找到 {len(results)} 本:')
    for book in results:
        print(f'  [{book["id"]}] {book["title"]}')
    return results


def demo_download():
    """下载有声小说"""
    # 需要先确认 audiobooks.json 中存在该 ID
    audiobooks = Audio.list_all()
    if not audiobooks:
        print('请先运行 Audio.scan() 更新 audiobooks.json')
        return

    audio_id = audiobooks[0]['id']
    audio = Audio(audio_id)
    output = Path('./output/audio')
    audio.download(output)
    print(f'有声小说已保存到: {output}')


def demo_download_range():
    """下载指定章节范围"""
    audiobooks = Audio.list_all()
    if not audiobooks:
        print('请先运行 Audio.scan() 更新 audiobooks.json')
        return

    audio_id = audiobooks[0]['id']
    audio = Audio(audio_id)
    output = Path('./output/audio_range')
    audio.download(output, chapter_range='1-5')
    print(f'章节范围下载完成: {output}')


if __name__ == '__main__':
    demo_list_all()
