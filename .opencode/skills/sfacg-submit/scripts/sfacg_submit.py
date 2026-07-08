"""
SFACG Chapter Submission Helper

Reads a markdown file and outputs ready-to-execute commands for Chrome DevTools MCP.

Usage:
    python sfacg_submit.py <novelId> <chapterId> <markdown_file> <title>

Example:
    python sfacg_submit.py 662104 8020919 ToBeContinued_Rewrite/12_碎片.md "第12章 碎片"

Outputs:
    1. URL to navigate to
    2. JS to load sfacg helper (run once per page load)
    3. JS to insert content + fill title
    4. Click commands for confirm/publish
"""

import sys
from pathlib import Path


def read_chapter(filepath: str) -> str:
    """Read markdown file, strip title line."""
    p = Path(filepath)
    if not p.exists():
        print(f'ERROR: File not found: {p}', file=sys.stderr)
        sys.exit(1)
    content = p.read_text(encoding='utf-8')
    lines = content.strip().split('\n')
    if lines and lines[0].startswith('#'):
        content = '\n'.join(lines[1:]).strip()
    return content


def escape_js(s: str) -> str:
    """Escape string for JS template literal."""
    return s.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)

    novel_id = sys.argv[1]
    chapter_id = sys.argv[2]
    filepath = sys.argv[3]
    title = sys.argv[4]

    content = read_chapter(filepath)
    escaped = escape_js(content)

    editor_url = f'https://i.sfacg.com/MyNovel/v2/manage/{novel_id}/editor?chapterId={chapter_id}'
    management_url = f'https://i.sfacg.com/MyNovel/v2/manage/{novel_id}'

    print('=' * 60)
    print(f'Chapter: {title}')
    print(f'File: {filepath}')
    print(f'Content length: {len(content)} chars')
    print('=' * 60)

    print('\n--- Step 1: Navigate to editor ---')
    print(f'URL: {editor_url}')

    print('\n--- Step 2: Load sfacg helper (once per page) ---')
    print('Run: chrome-devtools_evaluate_script')
    print('Paste contents of: scripts/sfacg_editor.js')

    print('\n--- Step 3: Insert content + fill title ---')
    js_insert = f"""() => {{
  const r1 = sfacg.insert(`{escaped}`);
  if (r1.error) return r1;
  const r2 = sfacg.fillTitle("{title}");
  if (r2.error) return r2;
  return {{ inserted: r1.chars, title: r2.value }};
}}"""
    print('Run: chrome-devtools_evaluate_script')
    print(f'function="{js_insert}"')

    print('\n--- Step 4: Confirm ---')
    print('Run: chrome-devtools_evaluate_script')
    print('function="() => sfacg.confirm()"')
    print('Wait 1s')

    print('\n--- Step 5: Publish ---')
    print('Run: chrome-devtools_evaluate_script')
    print('function="() => sfacg.publish()"')
    print('Wait 1s')

    print('\n--- Step 6: Verify ---')
    print(f'Navigate to: {management_url}')
    print('Take snapshot to confirm')

    # Also output a combined single-command version
    print('\n' + '=' * 60)
    print('COMBINED COMMAND (for quick single-call):')
    print('=' * 60)
    combined = f"""() => {{
  const e = window.wangEditor;
  if (!e) return {{error:'no editor'}};
  e.focus(); e.selectAll(); document.execCommand('delete');
  const ps = `{escaped}`.split('\\n').filter(p=>p.trim());
  const html = ps.map(p=>'<p>'+p+'</p>').join('');
  e.dangerouslyInsertHtml(html);
  const input = document.querySelector('input[placeholder*="章节号"]') || document.querySelector('input[placeholder*="章节名"]');
  if (input) {{
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
    set.call(input, "{title}");
    input.dispatchEvent(new Event('input',{{bubbles:true}}));
  }}
  return {{ chars: e.getText().length, title: input?.value }};
}}"""
    print(f'function="{combined}"')


if __name__ == '__main__':
    main()
