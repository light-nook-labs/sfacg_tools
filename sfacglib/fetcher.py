import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger
from time import sleep, time
from threading import Lock
from pathlib import Path
from urllib.parse import urlparse
import random

from .config import DEFAULT_DELAY, MAX_RETRIES, TIMEOUT, COOKIE_DOMAIN, USER_AGENTS


class RateLimiter:
    """Per-domain rate limiter."""

    def __init__(self, default_delay: float = DEFAULT_DELAY):
        self._delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._lock = Lock()
        self._default_delay = default_delay

    def set_delay(self, domain: str, delay: float):
        self._delays[domain] = delay

    def wait(self, domain: str):
        delay = self._delays.get(domain, self._default_delay)
        sleep_time = 0.0
        with self._lock:
            now = time()
            last = self._last_request.get(domain, 0.0)
            elapsed = now - last
            if elapsed < delay:
                sleep_time = delay - elapsed
            self._last_request[domain] = now + sleep_time
        if sleep_time > 0:
            sleep(sleep_time)


class Fetcher:
    """Smart HTTP fetcher with rotating UA, retry, session cookies, rate limiting.

    Usage:
        fetcher = Fetcher()
        html = fetcher.get_html('https://m.sfacg.com/b/43708/')
        fetcher.auto_auth()  # load saved cookies
        fetcher.import_cookies('name=val; ...')  # import from browser
    """

    def __init__(
        self,
        default_delay: float | None = None,
        max_retries: int = MAX_RETRIES,
        timeout: tuple[int, int] | None = None,
        rotate_ua: bool = True,
    ):
        self.timeout = timeout or TIMEOUT
        self.rotate_ua = rotate_ua
        self.rate_limiter = RateLimiter(default_delay or DEFAULT_DELAY)
        self.session = requests.Session()
        self.auth = None
        self._ua = random.choice(USER_AGENTS) if rotate_ua else USER_AGENTS[0]

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET', 'POST'],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

    def auto_auth(self) -> bool:
        """Load saved cookies and validate session."""
        from .auth import Auth

        self.auth = Auth()
        if self.auth.load():
            if self.auth.validate(self.session):
                self.auth.apply(self.session)
                return True
            logger.info('Saved cookies expired')

        logger.info('No valid session. Use import_cookies() to import from browser.')
        return False

    def import_cookies(self, cookie_string: str) -> bool:
        """Import cookies from browser cookie string."""
        if not self.auth:
            from .auth import Auth
            self.auth = Auth()

        if self.auth.import_cookies(cookie_string):
            self.auth.apply(self.session)
            return True
        return False

    def _get_headers(self) -> dict[str, str]:
        return {
            'User-Agent': self._ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    def _extract_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def get(self, url: str, params: dict | None = None, **kwargs) -> requests.Response:
        """GET request with rate limiting, UA rotation, and retry."""
        domain = self._extract_domain(url)
        self.rate_limiter.wait(domain)
        headers = {**self._get_headers(), **kwargs.get('headers', {})}
        timeout = kwargs.get('timeout', self.timeout)
        kwargs = {k: v for k, v in kwargs.items() if k not in ('headers', 'timeout')}

        logger.debug(f'GET {url}')
        resp = self.session.get(url, headers=headers, params=params, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with rate limiting, UA rotation, and retry."""
        domain = self._extract_domain(url)
        self.rate_limiter.wait(domain)
        headers = {**self._get_headers(), **kwargs.get('headers', {})}
        timeout = kwargs.get('timeout', self.timeout)
        kwargs = {k: v for k, v in kwargs.items() if k not in ('headers', 'timeout')}

        logger.debug(f'POST {url}')
        resp = self.session.post(url, headers=headers, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def get_html(self, url: str, params: dict | None = None, encoding: str = '') -> str:
        """Fetch page HTML as string."""
        resp = self.get(url, params=params)
        if encoding:
            resp.encoding = encoding
        return resp.text

    def get_json(self, url: str, params: dict | None = None) -> dict | list:
        """Fetch JSON response."""
        resp = self.get(url, params=params)
        try:
            return resp.json()
        except ValueError as e:
            logger.error(f'Invalid JSON response from {url}: {e}')
            logger.debug(f'Response text: {resp.text[:500]}')
            raise

    def get_binary(self, url: str) -> bytes:
        """Fetch binary content (images, audio, etc)."""
        resp = self.get(url)
        return resp.content

    def set_domain_delay(self, domain: str, delay: float):
        """Set custom rate limit delay for a specific domain."""
        self.rate_limiter.set_delay(domain, delay)

    def set_cookies(self, cookies: dict[str, str], domain: str = COOKIE_DOMAIN):
        """Set cookies for session persistence."""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=domain)
