import json
import os
from pathlib import Path
from loguru import logger
import requests
from .config import COOKIE_PATH, URL_CHECK_AUTH

_DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'


class Auth:
    """SFACG cookie-based authentication manager.

    Login requires Tencent CAPTCHA, so password login is not supported.
    Import cookies from browser DevTools instead.

    Usage:
        auth = Auth()
        auth.load()                             # load saved cookies
        auth.import_cookies('name=val; ...')    # import from browser
        auth.validate(session)                  # check if still valid
        auth.apply(session)                     # apply to requests session
    """

    def __init__(self):
        self.is_logged_in: bool = False
        self.username: str = ''
        self._cookies: dict[str, str] = {}

    def load(self) -> bool:
        """Load saved cookies from file."""
        if not COOKIE_PATH.exists():
            return False

        try:
            data = json.loads(COOKIE_PATH.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'Invalid cookie file: {e}')
            return False

        self._cookies = data.get('cookies', {})
        self.username = data.get('username', '')
        self.is_logged_in = bool(self._cookies)

        if self.is_logged_in:
            logger.info(f'Loaded cookies for {self.username or "unknown user"}')
        return self.is_logged_in

    def save(self, cookies: dict[str, str], username: str = ''):
        """Save cookies to file."""
        self._cookies = cookies
        self.username = username
        self.is_logged_in = True

        COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_PATH.write_text(
            json.dumps({'cookies': cookies, 'username': username}, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        os.chmod(COOKIE_PATH, 0o600)
        logger.info(f'Cookies saved to {COOKIE_PATH}')

    def import_cookies(self, cookie_string: str) -> bool:
        """Import cookies from browser cookie string.

        Args:
            cookie_string: "name1=value1; name2=value2; ..." format
                           Copy from browser DevTools → Network → Request Headers → Cookie
        """
        cookies = {}
        for item in cookie_string.split(';'):
            item = item.strip()
            if '=' in item:
                key, _, value = item.partition('=')
                cookies[key.strip()] = value.strip()

        if not cookies:
            logger.error('No valid cookies found in string')
            return False

        self.save(cookies, 'imported')
        logger.info(f'Imported {len(cookies)} cookies')
        return True

    def validate(self, session: requests.Session) -> bool:
        """Check if saved cookies are still valid."""
        if not self._cookies:
            return False

        original_cookies = requests.cookies.RequestsCookieJar()
        for cookie in session.cookies:
            original_cookies.set_cookie(cookie)
        for name, value in self._cookies.items():
            session.cookies.set(name, value, domain='.sfacg.com')

        try:
            resp = session.get(
                URL_CHECK_AUTH,
                headers={'User-Agent': _DEFAULT_UA},
                timeout=10,
            )
            resp.raise_for_status()
            if resp.raise_for_status() is None and ('退出' in resp.text or 'logout' in resp.text.lower() or '我的' in resp.text):
                logger.info('Session cookies are valid')
                return True
            logger.info('Session cookies expired')
            session.cookies.clear()
            session.cookies.update(original_cookies)
            return False
        except Exception as e:
            logger.warning(f'Cookie validation failed: {e}')
            session.cookies.clear()
            session.cookies.update(original_cookies)
            return False

    def apply(self, session: requests.Session):
        """Apply loaded cookies to a requests session."""
        for name, value in self._cookies.items():
            session.cookies.set(name, value, domain='.sfacg.com')

    def logout(self):
        """Clear saved cookies."""
        self._cookies = {}
        self.is_logged_in = False
        self.username = ''
        try:
            if COOKIE_PATH.exists():
                COOKIE_PATH.unlink()
        except OSError as e:
            logger.warning(f'Failed to delete cookie file: {e}')
        logger.info('Logged out')
