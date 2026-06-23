import re
from typing import Callable, TypeVar
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from bs4 import Tag
from loguru import logger
from .config import MOBILE_BASE

T = TypeVar('T')


def sanitize_filename(name: str) -> str:
    if not name:
        return ''
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = name.strip('_. ')
    encoded = name.encode('utf-8')[:200]
    while True:
        try:
            return encoded.decode('utf-8')
        except UnicodeDecodeError:
            encoded = encoded[:-1]


def build_url(base: str, path: str) -> str:
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if path.startswith('/'):
        return f'{base}{path}'
    return f'{base}/{path}'


def mobile_url(path: str) -> str:
    return build_url(MOBILE_BASE, path)


def parse_volume_ul(vol_tag: Tag) -> Tag | None:
    sibling = vol_tag.next_sibling
    while sibling:
        if hasattr(sibling, 'name') and sibling.name:
            return sibling.ul if hasattr(sibling, 'ul') and sibling.ul else sibling
        sibling = sibling.next_sibling
    return None


def run_tasks(
    tasks: dict[str, T],
    fn: Callable[[T], object],
    max_workers: int,
    desc: str = '',
    leave: bool = True,
    initial: int = 0,
) -> list[tuple[str, object]]:
    results_map: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fn, v): k for k, v in tasks.items()}
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc, leave=leave, initial=initial):
            key = futures[future]
            try:
                results_map[key] = future.result()
            except Exception as e:
                logger.error(f'{desc} failed: {key} - {e}')
                results_map[key] = None
    return [(k, results_map[k]) for k in tasks if k in results_map]
