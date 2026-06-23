import os
import re
import json
import time
from pathlib import Path
from threading import Thread
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from sfacglib.novel import Novel
from sfacglib.comic import Comic
from sfacglib.audio import Audio
from sfacglib.fetcher import Fetcher
from sfacglib.progress import ProgressTracker

DEFAULT_DOWNLOAD = Path.home() / 'Download'
DEFAULT_DOWNLOAD.mkdir(exist_ok=True)

app = FastAPI(title='SFACG Downloader')

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))

fetcher = Fetcher()
active_tasks: dict[str, dict] = {}


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')


@app.post('/api/novel')
async def download_novel(request: Request):
    data = await request.json()
    nid_text = data.get('nid', '')
    file_type = data.get('format', 'epub')
    output = data.get('output', str(DEFAULT_DOWNLOAD))
    download_reviews = data.get('reviews', False)

    match = re.search(r'(\d+)', nid_text)
    if not match:
        raise HTTPException(400, '无法提取小说ID')

    nid = int(match.group(1))
    task_id = f'novel_{nid}'

    if task_id in active_tasks and active_tasks[task_id]['status'] == 'running':
        raise HTTPException(409, '任务已在运行中')

    active_tasks[task_id] = {'status': 'running', 'progress': 0, 'total': 0, 'title': ''}

    def _download():
        try:
            tracker = ProgressTracker()
            novel = Novel(nid, fetcher=fetcher)
            active_tasks[task_id]['title'] = novel.title
            novel.download_novel(
                path=output,
                file_type=file_type,
                tracker=tracker,
                download_reviews=download_reviews,
            )
            tracker.close()
            active_tasks[task_id]['status'] = 'done'
        except Exception as e:
            active_tasks[task_id]['status'] = 'error'
            active_tasks[task_id]['error'] = str(e)

    Thread(target=_download, daemon=True).start()
    return {'task_id': task_id, 'message': '下载已开始'}


@app.post('/api/comic')
async def download_comic(request: Request):
    data = await request.json()
    url = data.get('url', '')
    output = data.get('output', str(DEFAULT_DOWNLOAD))

    if not url:
        raise HTTPException(400, '请输入漫画URL')

    task_id = f'comic_{hash(url) % 10000}'

    if task_id in active_tasks and active_tasks[task_id]['status'] == 'running':
        raise HTTPException(409, '任务已在运行中')

    active_tasks[task_id] = {'status': 'running', 'progress': 0, 'total': 0, 'title': ''}

    def _download():
        try:
            tracker = ProgressTracker()
            comic = Comic(url, fetcher=fetcher)
            active_tasks[task_id]['title'] = comic.title
            comic.download(path=output, tracker=tracker)
            tracker.close()
            active_tasks[task_id]['status'] = 'done'
        except Exception as e:
            active_tasks[task_id]['status'] = 'error'
            active_tasks[task_id]['error'] = str(e)

    Thread(target=_download, daemon=True).start()
    return {'task_id': task_id, 'message': '下载已开始'}


@app.post('/api/audio')
async def download_audio(request: Request):
    data = await request.json()
    id_text = data.get('id', '')
    output = data.get('output', str(DEFAULT_DOWNLOAD))

    if not id_text:
        raise HTTPException(400, '请输入有声小说ID')

    try:
        audio_id = int(id_text)
    except ValueError:
        raise HTTPException(400, '无效的ID')

    task_id = f'audio_{audio_id}'

    if task_id in active_tasks and active_tasks[task_id]['status'] == 'running':
        raise HTTPException(409, '任务已在运行中')

    active_tasks[task_id] = {'status': 'running', 'progress': 0, 'total': 0, 'title': ''}

    def _download():
        try:
            tracker = ProgressTracker()
            audio = Audio(audio_id, fetcher=fetcher)
            active_tasks[task_id]['title'] = audio.title
            audio.download(path=output, tracker=tracker)
            tracker.close()
            active_tasks[task_id]['status'] = 'done'
        except Exception as e:
            active_tasks[task_id]['status'] = 'error'
            active_tasks[task_id]['error'] = str(e)

    Thread(target=_download, daemon=True).start()
    return {'task_id': task_id, 'message': '下载已开始'}


@app.get('/api/tasks')
async def list_tasks():
    return active_tasks


@app.get('/api/tasks/{task_id}')
async def get_task(task_id: str):
    if task_id not in active_tasks:
        raise HTTPException(404, '任务不存在')
    return active_tasks[task_id]


@app.post('/api/cookie')
async def import_cookie(request: Request):
    data = await request.json()
    cookie = data.get('cookie', '')

    if not cookie:
        raise HTTPException(400, '请输入Cookie')

    try:
        fetcher.import_cookies(cookie)
        return {'message': '导入成功'}
    except Exception as e:
        raise HTTPException(500, f'导入失败: {e}')


@app.get('/api/library')
async def list_library(path: str = str(DEFAULT_DOWNLOAD)):
    base = Path(path)
    if not base.exists():
        return []

    items = []
    for item in sorted(base.iterdir()):
        if item.is_dir():
            catalog = item / 'catalog.json'
            if catalog.exists():
                try:
                    meta = json.loads(catalog.read_text(encoding='utf-8'))
                    items.append({
                        'name': item.name,
                        'path': str(item),
                        'title': meta.get('title', item.name),
                        'type': 'novel' if 'nid' in meta else 'comic',
                        'has_chapters': 'chapters' in meta or 'items' in meta,
                    })
                except:
                    items.append({'name': item.name, 'path': str(item), 'title': item.name, 'type': 'unknown'})
    return items


@app.get('/api/reader/novel/{path:path}')
async def read_novel(path: str):
    dir_path = Path(path)
    catalog_path = dir_path / 'catalog.json'

    if not catalog_path.exists():
        raise HTTPException(404, '未找到小说')

    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

    chapters = []
    items_key = 'items' if 'items' in catalog else 'chapters'
    for ch in catalog.get(items_key, []):
        ch_path = dir_path / ch['file']
        if ch_path.exists():
            content = ch_path.read_text(encoding='utf-8')
            chapters.append({
                'title': ch.get('item_title', ch.get('ch_title', '')),
                'section': ch.get('section_title', ch.get('vol_title', '')),
                'content': content,
            })

    return {
        'title': catalog.get('title', ''),
        'author': catalog.get('author', ''),
        'chapters': chapters,
    }


@app.get('/api/reader/comic/{path:path}')
async def read_comic(path: str):
    dir_path = Path(path)
    catalog_path = dir_path / 'catalog.json'

    if not catalog_path.exists():
        raise HTTPException(404, '未找到漫画')

    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

    pages = []
    items_key = 'items' if 'items' in catalog else 'chapters'
    for item in catalog.get(items_key, []):
        img_path = dir_path / item['file']
        if img_path.exists():
            pages.append({
                'title': item.get('item_title', ''),
                'section': item.get('section_title', ''),
                'url': f'/api/file/{img_path}',
            })

    return {
        'title': catalog.get('title', ''),
        'pages': pages,
    }


@app.get('/api/file/{path:path}')
async def serve_file(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(404, '文件不存在')
    return FileResponse(file_path)


def run_web(host='127.0.0.1', port=8888, open_browser=True):
    if open_browser:
        import webbrowser
        Thread(target=lambda: (time.sleep(1), webbrowser.open(f'http://{host}:{port}')), daemon=True).start()

    print(f'SFACG Web UI: http://{host}:{port}')
    uvicorn.run(app, host=host, port=port, log_level='info')
