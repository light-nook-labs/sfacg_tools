"""SFACG Spider - Modern UI with built-in reader.

Usage:
    uv run python app.py
    uv run flet run app.py --web
"""
import threading
import re
from pathlib import Path
import flet as ft
from loguru import logger

from sfacglib.fetcher import Fetcher
from sfacglib.auth import Auth
from sfacglib.config import COOKIE_PATH


class FileBrowser:
    def __init__(self, page: ft.Page, mode='file', extensions=None, on_select=None):
        self.page = page
        self.mode = mode
        self.extensions = extensions or []
        self.on_select = on_select
        self.current_path = Path.home()
        self.selected = ft.Text('', size=12, color=ft.Colors.WHITE54)
        self.file_list = ft.ListView(expand=True, spacing=2)
        self.path_field = ft.TextField(
            label='路径',
            value=str(self.current_path),
            expand=True,
            dense=True,
        )
        self.dialog = ft.AlertDialog(
            title=ft.Text('选择文件' if mode == 'file' else '选择文件夹'),
            content=ft.Container(
                ft.Column([
                    ft.Row([
                        self.path_field,
                        ft.IconButton(ft.Icons.ARROW_UPWARD, on_click=self.go_parent, tooltip='上级目录'),
                        ft.IconButton(ft.Icons.REFRESH, on_click=self.refresh, tooltip='刷新'),
                    ]),
                    ft.Divider(height=1),
                    self.file_list,
                    self.selected,
                ], spacing=4),
                width=500,
                height=400,
            ),
            actions=[
                ft.Button('确定', on_click=self.confirm),
                ft.Button('取消', on_click=self.cancel),
            ],
        )

    def show(self, start_path=None):
        if start_path:
            self.current_path = Path(start_path)
        self.page.overlay.append(self.dialog)
        self.dialog.open = True
        self.page.update()
        self.refresh()

    def hide(self):
        self.dialog.open = False
        self.page.update()
        if self.dialog in self.page.overlay:
            self.page.overlay.remove(self.dialog)
            self.page.update()

    def refresh(self, e=None):
        self.path_field.value = str(self.current_path)
        self.file_list.controls.clear()

        try:
            entries = sorted(self.current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            self.file_list.controls.append(ft.Text('无权限访问', color=ft.Colors.RED_300))
            self.page.update()
            return
        except Exception as ex:
            self.file_list.controls.append(ft.Text(f'错误: {ex}', color=ft.Colors.RED_300))
            self.page.update()
            return

        for entry in entries:
            if entry.name.startswith('.'):
                continue
            is_dir = entry.is_dir()
            if not is_dir and self.mode == 'file':
                if self.extensions and entry.suffix.lower() not in self.extensions:
                    continue
            if not is_dir and self.mode == 'folder':
                continue

            icon = ft.Icons.FOLDER if is_dir else ft.Icons.DESCRIPTION
            color = ft.Colors.AMBER_300 if is_dir else ft.Colors.WHITE70

            entry_path = str(entry)
            entry_is_dir = is_dir

            def on_click(e, path=entry_path, is_dir=entry_is_dir):
                if is_dir:
                    self.current_path = Path(path)
                    self.refresh()
                else:
                    self.selected.value = path
                    self.page.update()

            self.file_list.controls.append(
                ft.Container(
                    ft.Row([
                        ft.Icon(icon, color=color, size=18),
                        ft.Text(entry.name, size=12, color=color, expand=True, no_wrap=True),
                    ], spacing=8),
                    padding=ft.Padding(8, 4, 8, 4),
                    border_radius=4,
                    on_click=on_click,
                    ink=True,
                )
            )
        self.file_list.update()

    def go_parent(self, e):
        self.current_path = self.current_path.parent
        self.refresh()

    def confirm(self, e):
        if self.mode == 'folder':
            result = str(self.current_path)
        else:
            result = self.selected.value
        self.hide()
        if result and self.on_select:
            self.on_select(result)

    def cancel(self, e):
        self.hide()


class LogHandler:
    def __init__(self):
        self._page: ft.Page | None = None

    def set_page(self, page: ft.Page):
        self._page = page

    def write(self, msg: str):
        msg = msg.strip()
        if not msg:
            return
        if self._page:
            self._page.pubsub.send_all({'type': 'log', 'msg': msg})

    def flush(self):
        pass


log_handler = LogHandler()
logger.add(log_handler, format='{time:HH:mm:ss} | {level: <8} | {message}')


def main(page: ft.Page):
    page.title = 'SFACG Spider'
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    is_mobile = page.width < 600 if page.width else False

    fetcher = Fetcher()
    auth = Auth()
    if auth.load():
        if auth.validate(fetcher.session):
            auth.apply(fetcher.session)

    log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    def add_log(msg: str):
        color = ft.Colors.WHITE70
        if 'ERROR' in msg or '失败' in msg:
            color = ft.Colors.RED_300
        elif 'INFO' in msg:
            color = ft.Colors.GREEN_300
        elif 'WARNING' in msg:
            color = ft.Colors.AMBER_300
        log_list.controls.append(ft.Text(msg, size=12, color=color, selectable=True))
        if len(log_list.controls) > 500:
            log_list.controls = log_list.controls[-300:]
        page.update()

    page.pubsub.subscribe(lambda msg: add_log(msg['msg']) if msg.get('type') == 'log' else None)

    status_text = ft.Text('就绪', size=14)
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)

    def get_auth_status():
        if auth.is_logged_in:
            return f'已登录: {auth.username}', ft.Colors.GREEN_400
        return '未登录', ft.Colors.RED_400

    auth_status_text = ft.Text(get_auth_status()[0], color=get_auth_status()[1], size=13)

    def update_auth():
        text, color = get_auth_status()
        auth_status_text.value = text
        auth_status_text.color = color
        page.update()

    def run_download(func, *args):
        progress_bar.value = None
        progress_bar.visible = True
        status_text.value = '下载中...'
        page.update()

        def _run():
            try:
                func(*args)
                status_text.value = '完成'
            except Exception as e:
                logger.error(f'下载失败: {e}')
                status_text.value = f'错误: {e}'
            finally:
                progress_bar.visible = False
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    url_field = ft.TextField(
        label='URL / ID',
        hint_text='https://m.sfacg.com/b/43708/ 或 43708',
        expand=True,
        prefix_icon=ft.Icons.LINK,
    )
    format_dropdown = ft.Dropdown(
        label='格式',
        value='epub',
        options=[ft.dropdown.Option(f) for f in ['epub', 'md', 'html', 'txt']],
        width=120,
    )
    output_field = ft.TextField(
        label='保存路径',
        value='./',
        expand=True,
        prefix_icon=ft.Icons.FOLDER,
    )

    def build_download_page(title, fmt_options=None):
        if fmt_options:
            format_dropdown.options = [ft.dropdown.Option(f) for f in fmt_options]
            format_dropdown.value = fmt_options[0]
        return ft.Container(
            ft.Column([
                ft.Text(title, size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                url_field,
                ft.Row([format_dropdown, output_field], wrap=is_mobile),
                ft.Row([
                    ft.Button('开始下载', icon=ft.Icons.DOWNLOAD, on_click=lambda _: start_download()),
                    ft.Button('停止', icon=ft.Icons.STOP, on_click=lambda _: stop_download(),
                              style=ft.ButtonStyle(side=ft.BorderSide(1, ft.Colors.WHITE24))),
                ], spacing=10),
                ft.Row([progress_bar, status_text]),
            ], spacing=16, expand=True),
            padding=24,
            expand=True,
        )

    def stop_download():
        status_text.value = '已停止'
        page.update()

    nav_index = {'v': 0}
    content_area = ft.Container(expand=True)

    # ==================== NOVEL READER ====================
    def build_novel_reader():
        chapter_list = ft.ListView(expand=True, spacing=2)
        content_view = ft.Markdown(
            '',
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            expand=True,
        )
        chapter_title = ft.Text('', size=18, weight=ft.FontWeight.BOLD)
        nav_info = ft.Text('', size=12, color=ft.Colors.WHITE54)
        show_sidebar = [True]

        novel_state = {'chapters': [], 'idx': 0}

        def parse_epub(file_path: str) -> list[dict]:
            from ebooklib import epub
            book = epub.read_epub(file_path)
            chapters = []
            for item in book.get_items_of_type(9):
                html_content = item.get_content().decode('utf-8')
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                title = soup.h3.get_text() if soup.h3 else (soup.h2.get_text() if soup.h2 else item.get_name())
                md_lines = []
                for p in soup.find_all('p'):
                    text = p.get_text().strip()
                    if text:
                        md_lines.append(text)
                chapters.append({'title': title, 'content': '\n\n'.join(md_lines)})
            return chapters

        def parse_markdown(file_path: str) -> list[dict]:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            chapters = []
            current_title = ''
            current_lines = []
            for line in text.split('\n'):
                if line.startswith('### ') or line.startswith('## '):
                    if current_title and current_lines:
                        chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
                    current_title = line.lstrip('#').strip()
                    current_lines = []
                elif current_title:
                    current_lines.append(line)
            if current_title and current_lines:
                chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
            return chapters if chapters else [{'title': '全文', 'content': text}]

        def parse_html(file_path: str) -> list[dict]:
            from bs4 import BeautifulSoup
            with open(file_path, 'r', encoding='utf-8') as f:
                html = f.read()
            soup = BeautifulSoup(html, 'html.parser')
            chapters = []
            for ch_div in soup.find_all(class_='ch'):
                title = ch_div.h3.get_text() if ch_div.h3 else '未知章节'
                md_lines = []
                for p in ch_div.find_all('p'):
                    text = p.get_text().strip()
                    if text:
                        md_lines.append(text)
                chapters.append({'title': title, 'content': '\n\n'.join(md_lines)})
            return chapters if chapters else [{'title': '全文', 'content': soup.get_text()}]

        def scan_novels():
            base = Path(output_field.value.strip())
            if not base.exists():
                return []
            novels = []
            for entry in sorted(base.iterdir()):
                if entry.is_file() and entry.suffix.lower() in ('.epub', '.md', '.txt', '.html'):
                    novels.append(entry)
            return novels

        novel_dropdown = ft.Dropdown(
            label='选择小说',
            expand=True,
            options=[],
        )

        def refresh_novels(e=None):
            novels = scan_novels()
            novel_dropdown.options = [
                ft.dropdown.Option(str(n), text=n.name) for n in novels
            ]
            if novels:
                novel_dropdown.value = str(novels[0])
            page.update()

        def on_file_selected(path):
            novel_dropdown.value = path
            page.update()

        file_browser = FileBrowser(
            page, mode='file',
            extensions=['.epub', '.md', '.txt', '.html'],
            on_select=on_file_selected,
        )

        def open_browser(e):
            file_browser.show(output_field.value.strip())

        def load_file(e):
            file_path = novel_dropdown.value
            if not file_path or not Path(file_path).exists():
                return
            ext = file_path.rsplit('.', 1)[-1].lower()

            def _load():
                try:
                    if ext == 'epub':
                        chapters = parse_epub(file_path)
                    elif ext in ('md', 'txt'):
                        chapters = parse_markdown(file_path)
                    elif ext == 'html':
                        chapters = parse_html(file_path)
                    else:
                        logger.error(f'不支持的格式: {ext}')
                        return

                    novel_state['chapters'] = chapters
                    novel_state['idx'] = 0
                    chapter_list.controls.clear()
                    for i, ch in enumerate(chapters):
                        def make_click(idx):
                            return lambda _: show_chapter(idx)
                        chapter_list.controls.append(
                            ft.Container(
                                ft.Text(ch['title'], size=12),
                                padding=ft.Padding(16, 4, 16, 4),
                                border_radius=4,
                                on_click=make_click(i),
                                ink=True,
                            )
                        )
                    page.update()
                    if chapters:
                        show_chapter(0)
                except Exception as ex:
                    logger.error(f'加载失败: {ex}')

            threading.Thread(target=_load, daemon=True).start()

        def show_chapter(idx):
            chapters = novel_state['chapters']
            if idx < 0 or idx >= len(chapters):
                return
            novel_state['idx'] = idx
            ch = chapters[idx]
            chapter_title.value = ch['title']
            nav_info.value = f'{idx + 1} / {len(chapters)}'
            content_view.value = ch['content']
            if is_mobile:
                show_sidebar[0] = False
                update_layout()
            page.update()

        def prev_chapter(e):
            show_chapter(novel_state['idx'] - 1)

        def next_chapter(e):
            show_chapter(novel_state['idx'] + 1)

        def toggle_sidebar(e):
            show_sidebar[0] = not show_sidebar[0]
            update_layout()
            page.update()

        refresh_btn = ft.IconButton(ft.Icons.REFRESH, on_click=refresh_novels, tooltip='刷新列表')
        browse_btn = ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=open_browser, tooltip='浏览文件')
        load_btn = ft.Button('加载', icon=ft.Icons.SEARCH, on_click=load_file)

        sidebar = ft.Container(
            ft.Column([
                ft.Row([novel_dropdown, refresh_btn, browse_btn, load_btn]),
                ft.Divider(height=1),
                chapter_list,
            ], spacing=4),
            width=250,
            padding=8,
        )

        nav_bar = ft.Row([
            ft.IconButton(ft.Icons.MENU, on_click=toggle_sidebar, tooltip='目录'),
            chapter_title,
            ft.Container(expand=True),
            nav_info,
            ft.IconButton(ft.Icons.ARROW_BACK_IOS, on_click=prev_chapter, tooltip='上一章'),
            ft.IconButton(ft.Icons.ARROW_FORWARD_IOS, on_click=next_chapter, tooltip='下一章'),
        ])

        reader_content = ft.Container(
            ft.Column([
                nav_bar,
                ft.Divider(height=1),
                ft.Container(content_view, expand=True, padding=12),
            ], spacing=8, expand=True),
            expand=True,
        )

        main_row = ft.Row([sidebar, ft.VerticalDivider(width=1), reader_content], expand=True)

        def update_layout():
            if is_mobile:
                sidebar.visible = show_sidebar[0]
                main_row.controls = [sidebar, reader_content] if show_sidebar[0] else [reader_content]
            else:
                sidebar.visible = True
                main_row.controls = [sidebar, ft.VerticalDivider(width=1), reader_content]

        update_layout()
        refresh_novels()

        return ft.Container(main_row, expand=True)

    # ==================== COMIC READER ====================
    def build_comic_reader():
        chapter_list = ft.ListView(expand=True, spacing=2)
        chapter_title = ft.Text('', size=18, weight=ft.FontWeight.BOLD)
        show_sidebar = [True]
        comic_mode = ['strip']
        page_idx = [0]

        comic_state = {'chapters': [], 'current': -1}

        strip_view = ft.ListView(expand=True, spacing=0)
        page_view = ft.Container(expand=True, alignment=ft.Alignment(0, 0))
        page_num_text = ft.Text('', size=12, color=ft.Colors.WHITE54)

        def scan_comics():
            base = Path(output_field.value.strip())
            if not base.exists():
                return []
            comics = []
            for entry in sorted(base.iterdir()):
                if entry.is_dir():
                    has_images = any(
                        f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp')
                        for f in entry.rglob('*')
                        if f.is_file()
                    )
                    if has_images:
                        comics.append(entry)
            return comics

        comic_dropdown = ft.Dropdown(
            label='选择漫画',
            expand=True,
            options=[],
        )

        def refresh_comics(e=None):
            comics = scan_comics()
            comic_dropdown.options = [
                ft.dropdown.Option(str(c), text=c.name) for c in comics
            ]
            if comics:
                comic_dropdown.value = str(comics[0])
            page.update()

        def on_folder_selected(path):
            comic_dropdown.value = path
            page.update()

        folder_browser = FileBrowser(
            page, mode='folder',
            on_select=on_folder_selected,
        )

        def open_browser(e):
            folder_browser.show(output_field.value.strip())

        def load_comic(e):
            path = comic_dropdown.value
            if not path:
                return
            comic_path = Path(path)
            if not comic_path.exists():
                return

            chapters = []
            chapter_list.controls.clear()
            for entry in sorted(comic_path.iterdir()):
                if entry.is_dir():
                    images = sorted([f for f in entry.iterdir() if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp')])
                    if images:
                        chapters.append({'title': entry.name, 'path': entry, 'images': images})
                        idx = len(chapters) - 1
                        def make_click(i):
                            return lambda _: show_chapter(i)
                        chapter_list.controls.append(
                            ft.Container(
                                ft.Text(entry.name, size=12),
                                padding=ft.Padding(12, 6, 12, 6),
                                border_radius=4,
                                on_click=make_click(idx),
                                ink=True,
                            )
                        )
            comic_state['chapters'] = chapters
            page.update()
            if chapters:
                show_chapter(0)

        def show_chapter(idx):
            chapters = comic_state['chapters']
            if idx < 0 or idx >= len(chapters):
                return
            comic_state['current'] = idx
            page_idx[0] = 0
            ch = chapters[idx]
            chapter_title.value = ch['title']
            if comic_mode[0] == 'strip':
                show_strip(ch)
            else:
                show_page(ch, 0)
            if is_mobile:
                show_sidebar[0] = False
                update_layout()
            page.update()

        def show_strip(ch):
            strip_view.controls.clear()
            for img_path in ch['images']:
                strip_view.controls.append(
                    ft.Container(
                        ft.Image(
                            src=str(img_path),
                            fit=ft.BoxFit.FIT_WIDTH,
                        ),
                        alignment=ft.Alignment(0, 0),
                        padding=0,
                    )
                )
            content_area_inner.content = strip_view

        def show_page(ch, idx):
            images = ch['images']
            if idx < 0 or idx >= len(images):
                return
            page_idx[0] = idx
            page_num_text.value = f'{idx + 1} / {len(images)}'
            page_view.content = ft.Image(
                src=str(images[idx]),
                fit=ft.BoxFit.CONTAIN,
            )
            content_area_inner.content = page_view

        def prev_page(e):
            ch = comic_state['chapters'][comic_state['current']] if comic_state['current'] >= 0 else None
            if not ch:
                return
            if comic_mode[0] == 'page':
                show_page(ch, page_idx[0] - 1)
                page.update()

        def next_page(e):
            ch = comic_state['chapters'][comic_state['current']] if comic_state['current'] >= 0 else None
            if not ch:
                return
            if comic_mode[0] == 'page':
                show_page(ch, page_idx[0] + 1)
                page.update()

        def set_mode(mode):
            comic_mode[0] = mode
            mode_btn.text = '条漫' if mode == 'strip' else '页漫'
            ch = comic_state['chapters'][comic_state['current']] if comic_state['current'] >= 0 else None
            if ch:
                if mode == 'strip':
                    show_strip(ch)
                else:
                    show_page(ch, page_idx[0])
            page.update()

        def toggle_mode(e):
            set_mode('page' if comic_mode[0] == 'strip' else 'strip')

        def toggle_sidebar(e):
            show_sidebar[0] = not show_sidebar[0]
            update_layout()
            page.update()

        refresh_btn = ft.IconButton(ft.Icons.REFRESH, on_click=refresh_comics, tooltip='刷新列表')
        browse_btn = ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=open_browser, tooltip='浏览文件夹')
        load_btn = ft.Button('加载', icon=ft.Icons.SEARCH, on_click=load_comic)
        mode_btn = ft.Button('条漫', icon=ft.Icons.VIEW_DAY, on_click=toggle_mode)

        sidebar = ft.Container(
            ft.Column([
                ft.Row([comic_dropdown, refresh_btn, browse_btn, load_btn]),
                ft.Row([mode_btn]),
                ft.Divider(height=1),
                chapter_list,
            ], spacing=4),
            width=250,
            padding=8,
        )

        content_area_inner = ft.Container(expand=True)

        nav_bar = ft.Row([
            ft.IconButton(ft.Icons.MENU, on_click=toggle_sidebar, tooltip='目录'),
            chapter_title,
            ft.Container(expand=True),
            page_num_text,
            ft.IconButton(ft.Icons.ARROW_BACK_IOS, on_click=prev_page, tooltip='上一页'),
            ft.IconButton(ft.Icons.ARROW_FORWARD_IOS, on_click=next_page, tooltip='下一页'),
        ])

        reader_content = ft.Container(
            ft.Column([
                nav_bar,
                ft.Divider(height=1),
                content_area_inner,
            ], spacing=0, expand=True),
            expand=True,
        )

        main_row = ft.Row([sidebar, ft.VerticalDivider(width=1), reader_content], expand=True)

        def update_layout():
            if is_mobile:
                sidebar.visible = show_sidebar[0]
                main_row.controls = [sidebar, reader_content] if show_sidebar[0] else [reader_content]
            else:
                sidebar.visible = True
                main_row.controls = [sidebar, ft.VerticalDivider(width=1), reader_content]

        update_layout()
        refresh_comics()

        return ft.Container(main_row, expand=True)

    # ==================== OTHER PAGES ====================
    def get_auth_page():
        cookie_field = ft.TextField(
            label='从浏览器粘贴 Cookie',
            hint_text='name1=value1; name2=value2; ...',
            multiline=True,
            min_lines=3,
            max_lines=5,
            expand=True,
        )
        login_status = ft.Text('', size=13)

        def do_import_cookies(e):
            raw = cookie_field.value.strip()
            if raw and fetcher.import_cookies(raw):
                auth.load()
                auth.apply(fetcher.session)
                update_auth()
                login_status.value = '导入成功'
                login_status.color = ft.Colors.GREEN_400
            else:
                login_status.value = '导入失败，请检查格式'
                login_status.color = ft.Colors.RED_400
            page.update()

        def do_logout(e):
            auth.logout()
            update_auth()
            login_status.value = '已退出'
            login_status.color = ft.Colors.AMBER_400
            page.update()

        return ft.Container(
            ft.Column([
                ft.Text('账号', size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([ft.Icon(ft.Icons.ACCOUNT_CIRCLE), auth_status_text], spacing=8),
                ft.Divider(),
                ft.Text('导入 Cookie（从浏览器 DevTools 复制）', size=14),
                cookie_field,
                ft.Row([
                    ft.Button('导入', icon=ft.Icons.UPLOAD, on_click=do_import_cookies),
                    ft.Button('退出登录', icon=ft.Icons.LOGOUT, on_click=do_logout,
                              style=ft.ButtonStyle(side=ft.BorderSide(1, ft.Colors.WHITE24))),
                ]),
                login_status,
            ], spacing=16),
            padding=24,
            expand=True,
        )

    def get_settings_page():
        return ft.Container(
            ft.Column([
                ft.Text('设置', size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text('主题', size=14),
                ft.SegmentedButton(
                    selected=[page.theme_mode.value],
                    segments=[
                        ft.Segment('dark', label=ft.Text('深色'), icon=ft.Icon(ft.Icons.DARK_MODE)),
                        ft.Segment('light', label=ft.Text('浅色'), icon=ft.Icon(ft.Icons.LIGHT_MODE)),
                        ft.Segment('system', label=ft.Text('跟随系统'), icon=ft.Icon(ft.Icons.PHONE_ANDROID)),
                    ],
                    on_change=lambda e: set_theme(e.control.selected),
                ),
                ft.Divider(),
                ft.Text('当前状态', size=14),
                ft.Text(f'Cookie: {"已保存" if auth._cookies else "无"}', size=12, color=ft.Colors.WHITE54),
                ft.Text(f'Cookie 文件: {COOKIE_PATH}', size=12, color=ft.Colors.WHITE54),
            ], spacing=16),
            padding=24,
            expand=True,
        )

    def set_theme(selected):
        mode = selected.pop() if selected else 'dark'
        page.theme_mode = {'dark': ft.ThemeMode.DARK, 'light': ft.ThemeMode.LIGHT, 'system': ft.ThemeMode.SYSTEM}.get(mode, ft.ThemeMode.DARK)
        page.update()

    def get_log_page():
        return ft.Container(
            ft.Column([
                ft.Row([
                    ft.Text('日志', size=24, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.DELETE_SWEEP, tooltip='清空', on_click=lambda _: (log_list.controls.clear(), page.update())),
                ]),
                ft.Divider(),
                ft.Container(log_list, expand=True, border=ft.border.all(1, ft.Colors.WHITE12), border_radius=8, padding=8),
            ], spacing=8, expand=True),
            padding=24,
            expand=True,
        )

    # ==================== NAVIGATION ====================
    pages = {
        0: lambda: build_download_page('小说下载', ['epub', 'md', 'html', 'txt']),
        1: lambda: build_download_page('漫画下载', ['images']),
        2: lambda: build_download_page('有声小说', ['mp3']),
        3: lambda: build_download_page('评论下载', ['md']),
        4: lambda: build_novel_reader(),
        5: lambda: build_comic_reader(),
        6: lambda: get_auth_page(),
        7: lambda: get_settings_page(),
        8: lambda: get_log_page(),
    }

    download_funcs = {
        0: lambda: run_download(do_download_novel),
        1: lambda: run_download(do_download_comic),
        2: lambda: run_download(do_download_audio),
        3: lambda: run_download(do_download_review),
    }

    def start_download():
        func = download_funcs.get(nav_index['v'])
        if func:
            func()

    def do_download_novel():
        from sfacglib.book import Novel
        url = url_field.value.strip()
        nid_match = re.search(r'(\d+)', url)
        if not nid_match:
            logger.error('无法提取小说ID')
            return
        novel = Novel(int(nid_match.group(1)), fetcher=fetcher)
        novel.download_novel(path=output_field.value, file_type=format_dropdown.value)
        logger.info(f'完成: {novel.title}')

    def do_download_comic():
        from sfacglib.comic import Comic
        url = url_field.value.strip()
        comic = Comic(url, fetcher=fetcher)
        comic.download(path=output_field.value)
        logger.info(f'完成: {comic.title}')

    def do_download_audio():
        from sfacglib.audio import Audio
        url = url_field.value.strip()
        id_match = re.search(r'(\d+)', url)
        if not id_match:
            logger.error('请输入有声小说ID')
            return
        audio = Audio(int(id_match.group(1)), fetcher=fetcher)
        audio.download(path=output_field.value)
        logger.info(f'完成: {audio.title}')

    def do_download_review():
        import review as review_mod
        url = url_field.value.strip()
        reviews = review_mod.BookReviews(url, save_dir=output_field.value, fetcher=fetcher)
        reviews.download_reviews()
        logger.info(f'完成: {reviews.title}')

    def on_nav_change(e):
        idx = e if isinstance(e, int) else int(e.control.selected_index)
        nav_index['v'] = idx
        content_area.content = pages.get(idx, pages[0])()
        page.update()

    nav_items = [
        (ft.Icons.BOOK_OUTLINED, ft.Icons.BOOK, '小说'),
        (ft.Icons.IMAGE_OUTLINED, ft.Icons.IMAGE, '漫画'),
        (ft.Icons.AUDIOTRACK_OUTLINED, ft.Icons.AUDIOTRACK, '有声'),
        (ft.Icons.COMMENT_OUTLINED, ft.Icons.COMMENT, '评论'),
        (ft.Icons.AUTO_STORIES_OUTLINED, ft.Icons.AUTO_STORIES, '阅读'),
        (ft.Icons.PANORAMA_OUTLINED, ft.Icons.PANORAMA, '看漫画'),
        (ft.Icons.ACCOUNT_CIRCLE_OUTLINED, ft.Icons.ACCOUNT_CIRCLE, '账号'),
        (ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, '设置'),
        (ft.Icons.TERMINAL_OUTLINED, ft.Icons.TERMINAL, '日志'),
    ]

    if is_mobile:
        nav_bar = ft.NavigationBar(
            selected_index=0,
            destinations=[
                ft.NavigationBarDestination(icon=icon, selected_icon=sel_icon, label=label)
                for icon, sel_icon, label in nav_items
            ],
            on_change=lambda e: on_nav_change(e.control.selected_index),
        )
        page.add(
            ft.Column([
                ft.Container(content_area, expand=True),
                nav_bar,
            ], expand=True)
        )
    else:
        nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=80,
            min_extended_width=160,
            destinations=[
                ft.NavigationRailDestination(icon=icon, selected_icon=sel_icon, label=label)
                for icon, sel_icon, label in nav_items
            ],
            on_change=on_nav_change,
        )
        page.add(
            ft.Row([
                nav_rail,
                ft.VerticalDivider(width=1),
                ft.Container(content_area, expand=True),
            ], expand=True)
        )

    content_area.content = pages[0]()
    update_auth()


if __name__ == '__main__':
    ft.run(main)
