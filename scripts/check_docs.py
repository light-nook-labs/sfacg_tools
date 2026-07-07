"""Verify AGENTS.md and README.md are in sync with actual codebase structure.

Checks:
1. Key files exist on disk and are mentioned in docs
2. Import paths in README resolve to real modules
3. No stale references (files in docs that no longer exist)

Usage: uv run python scripts/check_docs.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / 'sfacglib'

# Files that MUST appear in architecture docs (critical modules)
KEY_FILES = {
    'config.py',
    'fetcher.py',
    'auth.py',
    'selectors.py',
    'novel.py',
    'comic.py',
    'audio.py',
    'search.py',
    'progress.py',
    'base.py',
}

# Directories that MUST appear
KEY_DIRS = {'models/', 'ocr/', 'utils/'}


def read_text(path):
    return path.read_text(encoding='utf-8')


def check_file_existence():
    """Check that key files/dirs exist on disk."""
    issues = []
    for name in KEY_FILES:
        if not (PACKAGE / name).is_file():
            issues.append(f'Missing on disk: sfacglib/{name}')
    for name in KEY_DIRS:
        if not (PACKAGE / name).is_dir():
            issues.append(f'Missing on disk: sfacglib/{name}')
    return issues


def check_agents_md():
    """Check AGENTS.md mentions key files and has no stale references."""
    text = read_text(ROOT / 'AGENTS.md')
    issues = []

    for name in KEY_FILES:
        if name not in text:
            issues.append(f'AGENTS.md: missing reference to {name}')

    for name in KEY_DIRS:
        dir_name = name.rstrip('/')
        if dir_name not in text:
            issues.append(f'AGENTS.md: missing reference to {dir_name}/')

    # Check that deleted root-level files are NOT referenced as standalone
    # (they may appear inside directory paths like utils/convert.py)
    stale_root_files = ['selectors.json', 'llm.py', 'web.py', 'ocr_fast.py', 'llm_vision.py', 'web_llm_vision.py']
    for name in stale_root_files:
        # Match as standalone filename (not preceded by / or .)
        pattern = rf'(?<![/\.]){re.escape(name)}(?!\w)'
        if re.search(pattern, text):
            issues.append(f'AGENTS.md: stale reference to {name}')

    return issues


def check_readme_imports():
    """Check import paths in README resolve to real modules."""
    text = read_text(ROOT / 'README.md')
    issues = []

    imports = re.findall(r'from sfacglib\.(\S+) import', text)
    for imp in imports:
        parts = imp.split('.')
        # Walk the package path
        current = PACKAGE
        valid = True
        for part in parts:
            if (current / part).is_dir():
                current = current / part
            elif (current / f'{part}.py').is_file():
                current = current / f'{part}.py'
            elif (current / part / '__init__.py').is_file():
                current = current / part
            else:
                valid = False
                break
        if not valid:
            issues.append(f'README.md: broken import: sfacglib.{imp}')

    return issues


def check_readme_stale():
    """Check README doesn't reference deleted modules."""
    text = read_text(ROOT / 'README.md')
    issues = []

    stale = ['selectors.json', 'ocr_fast.py', 'llm_vision.py']
    for name in stale:
        if name in text:
            issues.append(f'README.md: stale reference to {name}')

    return issues


def main():
    print('Checking docs sync...\n')
    all_issues = []

    all_issues.extend(check_file_existence())
    all_issues.extend(check_agents_md())
    all_issues.extend(check_readme_imports())
    all_issues.extend(check_readme_stale())

    if all_issues:
        print('ISSUES FOUND:\n')
        for issue in all_issues:
            print(f'  {issue}')
        print(f'\n{len(all_issues)} issue(s). Please update AGENTS.md and README.md.')
        sys.exit(1)
    else:
        print('All checks passed. Docs are in sync.')
        sys.exit(0)


if __name__ == '__main__':
    main()
