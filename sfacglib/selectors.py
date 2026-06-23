import json
from pathlib import Path
from loguru import logger
from bs4 import BeautifulSoup, Tag, ResultSet
from .config import SELECTORS_PATH


class SelectorError(Exception):
    """Raised when a CSS selector fails to match any element."""

    def __init__(self, page: str, field: str, selector: str, url: str = '', description: str = ''):
        self.page = page
        self.field = field
        self.selector = selector
        self.url = url
        self.description = description
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        msg = f'Selector failed: [{self.page}.{self.field}] -> "{self.selector}"'
        if self.description:
            msg += f' ({self.description})'
        if self.url:
            msg += f'\n  Page: {self.url}'
        msg += (
            f'\n  The page structure may have changed.'
            f'\n  Use chrome-devtools-mcp to navigate to the page and find the correct selector.'
            f'\n  Then update sfacglib/selectors.json -> "{self.page}" -> "{self.field}"'
        )
        return msg


class Selectors:
    """Centralized CSS selector registry.

    Loads selectors from selectors.json and provides methods to find elements
    with automatic error reporting when selectors break.
    """

    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else SELECTORS_PATH
        self._data: dict = {}
        self.reload()

    def reload(self):
        """Reload selectors from JSON file."""
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        except FileNotFoundError:
            logger.error(f'Selectors file not found: {self._path}')
            self._data = {}
        except json.JSONDecodeError as e:
            logger.error(f'Selectors JSON parse error: {self._path}: {e}')
            raise

    def get_selector(self, page: str, field: str) -> dict:
        """Get raw selector config for a page.field combination."""
        page_selectors = self._data.get(page)
        if not page_selectors:
            raise KeyError(f'Unknown page type: "{page}". Available: {list(self._data.keys())}')
        field_config = page_selectors.get(field)
        if not field_config:
            raise KeyError(f'Unknown field: "{page}.{field}". Available: {list(page_selectors.keys())}')
        return field_config

    def find(
        self,
        soup: BeautifulSoup,
        page: str,
        field: str,
        url: str = '',
        required: bool = True,
    ) -> Tag | None:
        """Find a single element using selector from config."""
        config = self.get_selector(page, field)
        selector = config['selector']
        result = soup.select_one(selector)

        if result is None and required:
            raise SelectorError(
                page=page, field=field, selector=selector,
                url=url, description=config.get('description', ''),
            )
        return result

    def find_all(
        self,
        soup: BeautifulSoup,
        page: str,
        field: str,
        url: str = '',
        required: bool = True,
    ) -> ResultSet:
        """Find all matching elements using selector from config."""
        config = self.get_selector(page, field)
        selector = config['selector']
        results = soup.select(selector)

        if not results and required:
            raise SelectorError(
                page=page, field=field, selector=selector,
                url=url, description=config.get('description', ''),
            )
        return results

    def find_attr(
        self,
        soup: BeautifulSoup,
        page: str,
        field: str,
        url: str = '',
        required: bool = True,
    ) -> str | None:
        """Find an element and extract its attribute value."""
        config = self.get_selector(page, field)
        attr_name = config.get('attr', 'href')
        element = self.find(soup, page, field, url=url, required=required)
        if element is None:
            return None
        value = element.get(attr_name)
        if value is None and required:
            raise SelectorError(
                page=page, field=field, selector=config['selector'],
                url=url, description=f'{config.get("description", "")} (attribute "{attr_name}" missing)',
            )
        return value

    def find_text(
        self,
        soup: BeautifulSoup,
        page: str,
        field: str,
        url: str = '',
        required: bool = True,
    ) -> str | None:
        """Find an element and extract its text content."""
        element = self.find(soup, page, field, url=url, required=required)
        if element is None:
            return None
        return element.get_text(strip=True)

    def validate_page(self, soup: BeautifulSoup, page: str, url: str = '') -> dict[str, bool]:
        """Validate all selectors for a given page type."""
        page_selectors = self._data.get(page, {})
        results = {}
        for field, config in page_selectors.items():
            if field.startswith('_'):
                continue
            if not isinstance(config, dict) or 'selector' not in config:
                continue
            selector = config['selector']
            found = soup.select_one(selector) is not None
            results[field] = found
            if not found:
                logger.warning(f'Selector missing: [{page}.{field}] -> "{selector}" ({config.get("description", "")})')
        return results

    @property
    def pages(self) -> list[str]:
        """List all available page types."""
        return [k for k in self._data if not k.startswith('_')]
