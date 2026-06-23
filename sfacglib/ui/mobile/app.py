import re
from threading import Thread
import flet as ft


def main(page: ft.Page):
    page.title = 'SFACG Downloader'
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20

    def log(output: ft.Text, msg: str):
        output.value += msg + '\n'
        page.update()

    def download_novel(e):
        btn.disabled = True
        page.update()

        nid_text = nid_field.value.strip()
        match = re.search(r'(\d+)', nid_text)
        if not match:
            log(novel_output, '错误: 无法提取小说ID')
            btn.disabled = False
            page.update()
            return

        nid = int(match.group(1))
        file_type = format_dropdown.value
        output = output_field.value.strip() or './output/'
        reviews = review_check.value

        def _download():
            try:
                from sfacglib.novel import Novel
                from sfacglib.fetcher import Fetcher
                from sfacglib.progress import ProgressTracker

                log(novel_output, f'开始下载: {nid}')

                fetcher = Fetcher()
                tracker = ProgressTracker()
                novel = Novel(nid, fetcher=fetcher)
                novel.download_novel(
                    path=output,
                    file_type=file_type,
                    tracker=tracker,
                    download_reviews=reviews,
                )
                tracker.close()

                log(novel_output, f'下载完成: {novel.title}')
            except Exception as ex:
                log(novel_output, f'错误: {ex}')
            finally:
                btn.disabled = False
                page.update()

        Thread(target=_download, daemon=True).start()

    def download_comic(e):
        comic_btn.disabled = True
        page.update()

        url = comic_url_field.value.strip()
        if not url:
            log(comic_output, '错误: 请输入漫画URL')
            comic_btn.disabled = False
            page.update()
            return

        output = comic_output_field.value.strip() or './output/'

        def _download():
            try:
                from sfacglib.comic import Comic
                from sfacglib.fetcher import Fetcher
                from sfacglib.progress import ProgressTracker

                log(comic_output, f'开始下载: {url}')

                fetcher = Fetcher()
                tracker = ProgressTracker()
                comic = Comic(url, fetcher=fetcher)
                comic.download(path=output, tracker=tracker)
                tracker.close()

                log(comic_output, f'下载完成: {comic.title}')
            except Exception as ex:
                log(comic_output, f'错误: {ex}')
            finally:
                comic_btn.disabled = False
                page.update()

        Thread(target=_download, daemon=True).start()

    def download_audio(e):
        audio_btn.disabled = True
        page.update()

        id_text = audio_id_field.value.strip()
        if not id_text:
            log(audio_output, '错误: 请输入有声小说ID')
            audio_btn.disabled = False
            page.update()
            return

        try:
            audio_id = int(id_text)
        except ValueError:
            log(audio_output, '错误: 无效的ID')
            audio_btn.disabled = False
            page.update()
            return

        output = audio_output_field.value.strip() or './output/'

        def _download():
            try:
                from sfacglib.audio import Audio
                from sfacglib.fetcher import Fetcher
                from sfacglib.progress import ProgressTracker

                log(audio_output, f'开始下载: {audio_id}')

                fetcher = Fetcher()
                tracker = ProgressTracker()
                audio = Audio(audio_id, fetcher=fetcher)
                audio.download(path=output, tracker=tracker)
                tracker.close()

                log(audio_output, f'下载完成: {audio.title}')
            except Exception as ex:
                log(audio_output, f'错误: {ex}')
            finally:
                audio_btn.disabled = False
                page.update()

        Thread(target=_download, daemon=True).start()

    def import_cookie(e):
        cookie = cookie_field.value.strip()
        if not cookie:
            settings_status.value = '请输入Cookie'
            page.update()
            return

        try:
            from sfacglib.fetcher import Fetcher
            fetcher = Fetcher()
            fetcher.import_cookies(cookie)
            settings_status.value = '导入成功'
            settings_status.color = ft.colors.GREEN
        except Exception as ex:
            settings_status.value = f'导入失败: {ex}'
            settings_status.color = ft.colors.RED
        page.update()

    # Novel tab
    nid_field = ft.TextField(label='小说ID或URL', hint_text='输入小说ID或URL')
    format_dropdown = ft.Dropdown(label='格式', value='epub', options=[
        ft.dropdown.Option('epub'),
        ft.dropdown.Option('md'),
        ft.dropdown.Option('txt'),
        ft.dropdown.Option('html'),
    ])
    output_field = ft.TextField(label='输出目录', value='./output/')
    review_check = ft.Checkbox(label='下载评论', value=False)
    btn = ft.ElevatedButton('下载', on_click=download_novel)
    novel_output = ft.Text(selectable=True, size=12)

    # Comic tab
    comic_url_field = ft.TextField(label='漫画URL', hint_text='输入漫画URL')
    comic_output_field = ft.TextField(label='输出目录', value='./output/')
    comic_btn = ft.ElevatedButton('下载', on_click=download_comic)
    comic_output = ft.Text(selectable=True, size=12)

    # Audio tab
    audio_id_field = ft.TextField(label='有声小说ID', hint_text='输入有声小说ID')
    audio_output_field = ft.TextField(label='输出目录', value='./output/')
    audio_btn = ft.ElevatedButton('下载', on_click=download_audio)
    audio_output = ft.Text(selectable=True, size=12)

    # Settings tab
    cookie_field = ft.TextField(label='Cookie', hint_text='粘贴Cookie', multiline=True, min_lines=3)
    settings_btn = ft.ElevatedButton('导入Cookie', on_click=import_cookie)
    settings_status = ft.Text()

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(
                text='小说',
                content=ft.Column([
                    nid_field,
                    format_dropdown,
                    output_field,
                    review_check,
                    btn,
                    ft.Container(
                        content=novel_output,
                        bgcolor=ft.colors.BLACK12,
                        padding=10,
                        border_radius=8,
                        expand=True,
                    ),
                ], scroll=ft.ScrollMode.AUTO),
            ),
            ft.Tab(
                text='漫画',
                content=ft.Column([
                    comic_url_field,
                    comic_output_field,
                    comic_btn,
                    ft.Container(
                        content=comic_output,
                        bgcolor=ft.colors.BLACK12,
                        padding=10,
                        border_radius=8,
                        expand=True,
                    ),
                ], scroll=ft.ScrollMode.AUTO),
            ),
            ft.Tab(
                text='有声',
                content=ft.Column([
                    audio_id_field,
                    audio_output_field,
                    audio_btn,
                    ft.Container(
                        content=audio_output,
                        bgcolor=ft.colors.BLACK12,
                        padding=10,
                        border_radius=8,
                        expand=True,
                    ),
                ], scroll=ft.ScrollMode.AUTO),
            ),
            ft.Tab(
                text='设置',
                content=ft.Column([
                    cookie_field,
                    settings_btn,
                    settings_status,
                ]),
            ),
        ],
        expand=True,
    )

    page.add(tabs)


def run_mobile(target='app'):
    if target == 'apk':
        ft.app(target='flet_app')
    else:
        ft.app(target='web_browser')
