"""
SFACG批量创建章节 - Playwright版本
每次创建一章后重启浏览器，避免session累积失效

用法:
    python playwright_batch.py --novel-id 681842 --volume-id 896483 --chapters "第7章 标题:path/to/ch7.md,第8章 标题:path/to/ch8.md"
    python playwright_batch.py --novel-id 681842 --volume-id 896483 --chapter-dir "path/to/chapters/"
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

USER_DATA_DIR = 'C:/Users/d111k/Desktop/sfacg_tools/.playwright_data'

INSERT_JS = """(content) => {
    const editor = window.wangEditor;
    if (!editor) return { error: 'wangEditor not found' };
    editor.focus();
    editor.selectAll();
    document.execCommand('delete');
    const ps = content.split('\\n').filter(p => p.trim());
    const html = ps.map(p => '<p>' + p + '</p>').join('');
    editor.dangerouslyInsertHtml(html);
    return { ok: true, chars: editor.getText().length };
}"""

FILL_TITLE_JS = """(title) => {
    const input = document.querySelector('input[placeholder*="章节号"]') ||
                  document.querySelector('input[placeholder*="章节名"]');
    if (!input) return { error: 'title input not found' };
    input.focus();
    input.value = '';
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputValueSetter.call(input, title);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, value: input.value };
}"""

CONFIRM_JS = """() => {
    const els = document.querySelectorAll('span, button, div');
    for (const el of els) {
        if (el.textContent.trim() === '确认编辑' && el.offsetParent !== null) {
            el.click();
            return { ok: true };
        }
    }
    return { error: 'confirm button not found' };
}"""

PUBLISH_JS = """() => {
    const els = document.querySelectorAll('span, button, div');
    for (const el of els) {
        if (el.textContent.trim() === '确定发布' && el.offsetParent !== null) {
            el.click();
            return { ok: true };
        }
    }
    return { error: 'publish button not found' };
}"""


async def create_single_chapter(novel_id: int, volume_id: int, title: str, content: str):
    """创建单章，每次启动新浏览器"""
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            editor_url = f'https://i.sfacg.com/MyNovel/v2/manage/{novel_id}/editor?volumeId={volume_id}'
            print(f'导航到: {editor_url}')

            await page.goto(editor_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            if 'passport.sfacg.com' in page.url:
                print('需要登录! 请在浏览器中扫码登录...')
                try:
                    await page.wait_for_url('**/editor**', timeout=120000)
                    print('登录成功!')
                except:
                    return {'title': title, 'success': False, 'error': 'Login timeout'}

            await page.wait_for_timeout(3000)

            # 插入内容
            insert_result = await page.evaluate(INSERT_JS, content)
            if insert_result.get('error'):
                return {'title': title, 'success': False, 'error': insert_result['error']}

            await page.wait_for_timeout(1000)

            # 设置标题
            await page.evaluate(FILL_TITLE_JS, title)
            await page.wait_for_timeout(500)

            # 确认编辑
            await page.evaluate(CONFIRM_JS)
            await page.wait_for_timeout(1500)

            # 发布
            await page.evaluate(PUBLISH_JS)
            await page.wait_for_timeout(2000)

            return {'title': title, 'success': True, 'chars': insert_result.get('chars')}

        except Exception as e:
            return {'title': title, 'success': False, 'error': str(e)}
        finally:
            await context.close()


async def batch_create(novel_id: int, volume_id: int, chapters: list[dict]):
    """
    批量创建章节

    Args:
        novel_id: 小说ID
        volume_id: 卷ID
        chapters: [{"title": "第7章 标题", "content_file": "path/to/file.md"}, ...]
    """
    results = []

    for i, chapter in enumerate(chapters):
        title = chapter['title']
        content_file = Path(chapter['content_file'])

        print(f'\n{"=" * 50}')
        print(f'[{i + 1}/{len(chapters)}] 创建: {title}')
        print(f'{"=" * 50}')

        # 读取内容
        content = content_file.read_text(encoding='utf-8')
        if content.startswith('# '):
            content = content.split('\n', 1)[1].strip()

        # 创建章节
        result = await create_single_chapter(novel_id, volume_id, title, content)
        results.append(result)

        print(f'结果: {"OK" if result.get("success") else "FAIL"}')

        # 等待2秒再创建下一章
        if i < len(chapters) - 1:
            print('等待2秒...')
            await asyncio.sleep(2)

    # 打印总结
    print(f'\n{"=" * 50}')
    print('总结:')
    for r in results:
        status = 'OK' if r.get('success') else 'FAIL'
        chars = r.get('chars', '?')
        print(f'  [{status}] {r.get("title")} ({chars}字)')
    print(f'{"=" * 50}')

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SFACG批量创建章节')
    parser.add_argument('--novel-id', type=int, required=True, help='小说ID')
    parser.add_argument('--volume-id', type=int, required=True, help='卷ID')
    parser.add_argument('--chapters', help="章节列表，格式: '标题1:文件路径1,标题2:文件路径2'")
    parser.add_argument('--chapter-dir', type=Path, help='章节目录，自动读取所有.md文件')
    args = parser.parse_args()

    chapters = []

    if args.chapters:
        # 解析命令行参数
        for item in args.chapters.split(','):
            title, file_path = item.split(':')
            chapters.append({'title': title.strip(), 'content_file': file_path.strip()})
    elif args.chapter_dir:
        # 从目录读取
        for f in sorted(args.chapter_dir.glob('*.md')):
            # 假设文件名格式: "第7章_标题.md" 或 "07_标题.md"
            title = f.stem.replace('_', ' ')
            if not title.startswith('第'):
                # 尝试从内容第一行提取标题
                content = f.read_text(encoding='utf-8')
                if content.startswith('# '):
                    title = content.split('\n')[0][2:].strip()
            chapters.append({'title': title, 'content_file': str(f)})
    else:
        print('必须提供 --chapters 或 --chapter-dir')
        exit(1)

    asyncio.run(batch_create(args.novel_id, args.volume_id, chapters))
