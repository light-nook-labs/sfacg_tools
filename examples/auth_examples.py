import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import requests
from sfacglib.auth import Auth


def demo_import_cookies():
    """从浏览器导入 Cookie"""
    # 从浏览器 DevTools → Network → Request Headers → Cookie 复制
    cookie_string = '你的cookie字符串; key2=value2'
    auth = Auth()
    success = auth.import_cookies(cookie_string)
    if success:
        print(f'导入成功，共 {len(auth._cookies)} 个 cookie')
    return auth


def demo_load():
    """加载已保存的 Cookie"""
    auth = Auth()
    loaded = auth.load()
    if loaded:
        print(f'已加载 Cookie (用户: {auth.username})')
    else:
        print('没有已保存的 Cookie')
    return auth


def demo_validate():
    """验证 Cookie 是否有效"""
    auth = Auth()
    if not auth.load():
        print('没有已保存的 Cookie')
        return

    session = requests.Session()
    valid = auth.validate(session)
    if valid:
        print(f'Cookie 有效 (用户: {auth.username})')
    else:
        print('Cookie 已过期，请重新导入')
    return auth


def demo_apply():
    """将 Cookie 应用到 Session"""
    auth = Auth()
    if not auth.load():
        print('没有已保存的 Cookie')
        return

    session = requests.Session()
    auth.apply(session)
    print(f'Cookie 已应用到 Session (用户: {auth.username})')
    # 现在可以用这个 session 访问需要登录的页面
    return session


def demo_logout():
    """登出并清除 Cookie"""
    auth = Auth()
    auth.logout()
    print('已登出')


if __name__ == '__main__':
    demo_load()
    print()
    demo_validate()
