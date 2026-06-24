import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sfacglib.fetcher import Fetcher


def demo_get_html():
    """获取页面 HTML"""
    fetcher = Fetcher()
    html = fetcher.get_html('https://book.sfacg.com/Novel/43708/')
    print(f'HTML 长度: {len(html)} 字符')
    print(f'前 200 字符: {html[:200]}...')
    return html


def demo_get_json():
    """获取 JSON 数据"""
    fetcher = Fetcher()
    # SFACG 搜索 API 返回 JSON
    url = 'https://s.sfacg.com/novelspace/result/?q=魔法&sort=0'
    data = fetcher.get_json(url)
    print(f'JSON 类型: {type(data).__name__}')
    return data


def demo_auto_auth():
    """自动加载并验证 Cookie"""
    fetcher = Fetcher()
    success = fetcher.auto_auth()
    if success:
        print(f'登录成功 (用户: {fetcher.auth.username})')
    else:
        print('未登录或 Cookie 已过期')
    return fetcher


def demo_import_cookies():
    """导入浏览器 Cookie"""
    fetcher = Fetcher()
    cookie_string = '你的cookie字符串; key2=value2'
    success = fetcher.import_cookies(cookie_string)
    if success:
        print('Cookie 导入成功')
    return fetcher


def demo_set_domain_delay():
    """自定义域名请求间隔"""
    fetcher = Fetcher()
    # 设置 vip.sfacg.com 的请求间隔为 2 秒
    fetcher.set_domain_delay('vip.sfacg.com', 2.0)
    print('已设置 vip.sfacg.com 延迟为 2s')
    return fetcher


def demo_get_binary():
    """下载二进制内容（图片等）"""
    fetcher = Fetcher()
    # 下载一张封面图
    url = 'https://rs.sfacg.com/images/bookimg/43708.jpg'
    data = fetcher.get_binary(url)
    print(f'下载了 {len(data)} 字节')
    return data


if __name__ == '__main__':
    demo_get_html()
    print()
    demo_auto_auth()
