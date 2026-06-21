import re


def merge_wrapped_lines(text: str) -> str:
    lines = text.split('\n')
    result = []
    buffer = ''

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if buffer:
                result.append(buffer)
                buffer = ''
            result.append('')
            continue

        if not buffer:
            buffer = stripped
            continue

        if _should_merge(buffer, stripped):
            buffer += stripped
        else:
            result.append(buffer)
            buffer = stripped

    if buffer:
        result.append(buffer)

    return '\n'.join(result)


def _should_merge(prev: str, curr: str) -> bool:
    if not prev or not curr:
        return False

    prev_last = prev[-1]
    curr_first = curr[0]

    if prev_last in '。！？…"）】》':
        return False

    if curr_first in '""（【《':
        return False

    if re.match(r'^[A-Za-z]', curr):
        return False

    if curr_first in '，。、；：！？…':
        return True

    if prev_last in '，、；：':
        return True

    if _is_chinese(prev_last) and _is_chinese(curr_first):
        return True

    return False


def _is_chinese(char: str) -> bool:
    return '\u4e00' <= char <= '\u9fff'
