"""
SFACG单章创建/编辑 - Playwright版本
用于Chrome DevTools MCP触发风控时的备用方案

用法:
    python playwright_single.py --novel-id 681842 --volume-id 896483 --title "第7章 标题" --content-file "path/to/chapter.md"
    python playwright_single.py --novel-id 681842 --chapter-id 8215598 --title "第1章 标题" --content-file "path/to/chapter.md"
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

# 持久化用户数据目录
USER_DATA_DIR = 'C:/Users/d111k/Desktop/sfacg_tools/.playwright_data'

# JavaScript 模板
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


async def create_or_edit_chapter(
    novel_id: int,
    title: str,
    content_file: Path,
    chapter_id: int | None = None,
    volume_id: int | None = None,
):
    """
    创建或编辑单章

    Args:
        novel_id: 小说ID
        title: 章节标题 (格式: "第N章 标题")
        content_file: 内容文件路径
        chapter_id: 章节ID (编辑已有章节时使用)
        volume_id: 卷ID (创建新章节时使用)
    """
    if not chapter_id and not volume_id:
        return {'error': '必须提供 chapter_id 或 volume_id'}

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            # 读取内容
            content = content_file.read_text(encoding='utf-8')
            if content.startswith('# '):
                content = content.split('\n', 1)[1].strip()

            # 构建URL
            if chapter_id:
                editor_url = f'https://i.sfacg.com/MyNovel/v2/manage/{novel_id}/editor?chapterId={chapter_id}'
            else:
                editor_url = f'https://i.sfacg.com/MyNovel/v2/manage/{novel_id}/editor?volumeId={volume_id}'

            print(f'导航到: {editor_url}')
            await page.goto(editor_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)

            current_url = page.url
            print(f'当前URL: {current_url}')

            # 检查是否需要登录
            if 'passport.sfacg.com' in current_url:
                print('需要登录! 请在浏览器中扫码登录...')
                try:
                    await page.wait_for_url('**/editor**', timeout=120000)
                    print('登录成功!')
                except:
                    return {'error': '登录超时'}

            # 等待编辑器加载
            await page.wait_for_timeout(3000)

            # 插入内容
            print('插入内容...')
            insert_result = await page.evaluate(INSERT_JS, content)
            print(f'插入结果: {insert_result}')

            if insert_result.get('error'):
                return {'error': insert_result['error']}

            await page.wait_for_timeout(1000)

            # 设置标题
            print('设置标题...')
            title_result = await page.evaluate(FILL_TITLE_JS, title)
            print(f'标题结果: {title_result}')
            await page.wait_for_timeout(500)

            # 点击确认编辑
            print('点击确认编辑...')
            confirm_result = await page.evaluate(CONFIRM_JS)
            print(f'确认结果: {confirm_result}')
            await page.wait_for_timeout(1500)

            # 点击确定发布
            print('点击确定发布...')
            publish_result = await page.evaluate(PUBLISH_JS)
            print(f'发布结果: {publish_result}')
            await page.wait_for_timeout(2000)

            print(f'完成: {title}')
            return {'success': True, 'title': title, 'chars': insert_result.get('chars')}

        except Exception as e:
            print(f'错误: {e}')
            return {'error': str(e)}
        finally:
            await context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SFACG单章创建/编辑')
    parser.add_argument('--novel-id', type=int, required=True, help='小说ID')
    parser.add_argument('--chapter-id', type=int, help='章节ID (编辑已有章节)')
    parser.add_argument('--volume-id', type=int, help='卷ID (创建新章节)')
    parser.add_argument('--title', required=True, help='章节标题 (格式: 第N章 标题)')
    parser.add_argument('--content-file', type=Path, required=True, help='内容文件路径')
    args = parser.parse_args()

    result = asyncio.run(
        create_or_edit_chapter(
            novel_id=args.novel_id,
            title=args.title,
            content_file=args.content_file,
            chapter_id=args.chapter_id,
            volume_id=args.volume_id,
        )
    )

    print(f'\n结果: {result}')
