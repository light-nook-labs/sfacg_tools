import random
from threading import Lock
from time import sleep
from urllib.parse import urlparse

import requests
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import COOKIE_DOMAIN, DEFAULT_DELAY, MAX_RETRIES, TIMEOUT, USER_AGENTS


class RateLimiter:
    """Per-domain rate limiter with optional concurrency limit.

    Allows up to `max_concurrent` simultaneous requests per domain.
    When the limit is reached, threads block until a slot frees.
    After each request, waits `delay` seconds before allowing the next.
    """

    def __init__(self, default_delay: float = DEFAULT_DELAY, max_concurrent: int = 0):
        self._delays: dict[str, float] = {}
        self._default_delay = default_delay
        self._max_concurrent = max_concurrent
        self._active: dict[str, int] = {}
        self._active_lock = Lock()
        self._domain_locks: dict[str, Lock] = {}
        self._domain_lock_lock = Lock()

    def _get_domain_lock(self, domain: str) -> Lock:
        with self._domain_lock_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = Lock()
            return self._domain_locks[domain]

    def set_delay(self, domain: str, delay: float):
        self._delays[domain] = delay

    def wait(self, domain: str):
        delay = self._delays.get(domain, self._default_delay)

        if self._max_concurrent > 0:
            while True:
                with self._active_lock:
                    count = self._active.get(domain, 0)
                    if count < self._max_concurrent:
                        self._active[domain] = count + 1
                        break
                sleep(0.01)

        dlock = self._get_domain_lock(domain)
        with dlock:
            if delay > 0:
                sleep(delay)

    def release(self, domain: str):
        if self._max_concurrent > 0:
            with self._active_lock:
                count = self._active.get(domain, 1)
                self._active[domain] = max(0, count - 1)


class Fetcher:
    """Smart HTTP fetcher with rotating UA, retry, dual sessions (public + auth).

    Usage:
        fetcher = Fetcher()
        html = fetcher.get_html('https://m.sfacg.com/b/43708/')
        fetcher.auto_auth()  # load saved cookies for VIP

        # Public content (no cookies, no rate limit):
        html = fetcher.get_html(url, vip=False)

        # VIP content (cookies, rate limited):
        html = fetcher.get_html(url, vip=True)
    """

    AJAX_HEADERS = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    def __init__(
        self,
        default_delay: float | None = None,
        max_retries: int = MAX_RETRIES,
        timeout: tuple[int, int] | None = None,
        rotate_ua: bool = True,
        no_auth: bool = False,
    ):
        self.timeout = timeout or TIMEOUT
        self.rotate_ua = rotate_ua
        self.auth = None
        self._ua = random.choice(USER_AGENTS) if rotate_ua else USER_AGENTS[0]

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET', 'POST'],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.public_session = requests.Session()
        self.public_session.mount('https://', adapter)
        self.public_session.mount('http://', adapter)
        self.public_rate_limiter = RateLimiter(default_delay=0)

        self.auth_session = requests.Session()
        self.auth_session.mount('https://', adapter)
        self.auth_session.mount('http://', adapter)
        self.auth_rate_limiter = RateLimiter(default_delay=default_delay or DEFAULT_DELAY, max_concurrent=10)

    @classmethod
    def no_auth(cls, **kwargs) -> 'Fetcher':
        """Create a Fetcher without loading saved cookies (for search, public pages)."""
        return cls(no_auth=True, **kwargs)

    def auto_auth(self) -> bool:
        """Load saved cookies and validate session."""
        from .auth import Auth

        self.auth = Auth()
        if self.auth.load():
            if self.auth.validate(self.auth_session):
                self.auth.apply(self.auth_session)
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
            self.auth.apply(self.auth_session)
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

    def _pick(self, vip: bool) -> tuple[requests.Session, RateLimiter]:
        if vip:
            return self.auth_session, self.auth_rate_limiter
        return self.public_session, self.public_rate_limiter

    def get(self, url: str, params: dict | None = None, vip: bool = False, **kwargs) -> requests.Response:
        """GET request with rate limiting, UA rotation, and retry."""
        session, limiter = self._pick(vip)
        domain = self._extract_domain(url)
        limiter.wait(domain)
        headers = {**self._get_headers(), **kwargs.get('headers', {})}
        timeout = kwargs.get('timeout', self.timeout)
        kwargs = {k: v for k, v in kwargs.items() if k not in ('headers', 'timeout')}

        logger.debug(f'GET {url}')
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        finally:
            limiter.release(domain)

    def post(self, url: str, vip: bool = False, **kwargs) -> requests.Response:
        """POST request with rate limiting, UA rotation, and retry."""
        session, limiter = self._pick(vip)
        domain = self._extract_domain(url)
        limiter.wait(domain)
        headers = {**self._get_headers(), **kwargs.get('headers', {})}
        timeout = kwargs.get('timeout', self.timeout)
        kwargs = {k: v for k, v in kwargs.items() if k not in ('headers', 'timeout')}

        logger.debug(f'POST {url}')
        try:
            resp = session.post(url, headers=headers, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        finally:
            limiter.release(domain)

    def get_html(self, url: str, params: dict | None = None, vip: bool = False, encoding: str = '') -> str:
        """Fetch page HTML as string."""
        resp = self.get(url, params=params, vip=vip)
        if encoding:
            resp.encoding = encoding
        return resp.text

    def get_json(self, url: str, params: dict | None = None, vip: bool = False) -> dict | list:
        """Fetch JSON response."""
        resp = self.get(url, params=params, vip=vip)
        try:
            return resp.json()
        except ValueError as e:
            logger.error(f'Invalid JSON response from {url}: {e}')
            logger.debug(f'Response text: {resp.text[:500]}')
            raise

    def get_binary(self, url: str, vip: bool = False) -> bytes:
        """Fetch binary content (images, audio, etc)."""
        resp = self.get(url, vip=vip)
        return resp.content

    def set_domain_delay(self, domain: str, delay: float):
        """Set custom rate limit delay for a specific domain."""
        self.public_rate_limiter.set_delay(domain, delay)
        self.auth_rate_limiter.set_delay(domain, delay)

    def set_cookies(self, cookies: dict[str, str], domain: str = COOKIE_DOMAIN):
        """Set cookies for session persistence."""
        for name, value in cookies.items():
            self.auth_session.cookies.set(name, value, domain=domain)
