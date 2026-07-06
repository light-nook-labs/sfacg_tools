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

    return '\n\n'.join(result)


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
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0xF900 <= cp <= 0xFAFF
        or 0x2F800 <= cp <= 0x2FA1F
    )
