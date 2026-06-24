import pytest
from sfacglib.search import (
    _deduplicate,
    _parse_html_results,
    search_novel_api,
    get_related,
    get_author_works,
)
from sfacglib.models import SearchItem


def make_item(id: str, title: str = '', **kwargs) -> SearchItem:
    defaults = dict(id=id, title=title or f'Novel {id}', author='', cover='',
                    url=f'https://book.sfacg.com/Novel/{id}', snippet='',
                    updated='', type='novel', score=0.0)
    defaults.update(kwargs)
    return SearchItem(**defaults)


class TestDeduplicate:
    def test_empty(self):
        assert _deduplicate([]) == []

    def test_no_duplicates(self):
        items = [make_item('1'), make_item('2'), make_item('3')]
        result = _deduplicate(items)
        assert len(result) == 3
        assert [r.id for r in result] == ['1', '2', '3']

    def test_with_duplicates(self):
        items = [make_item('1'), make_item('2'), make_item('1'), make_item('3'), make_item('2')]
        result = _deduplicate(items)
        assert len(result) == 3
        assert [r.id for r in result] == ['1', '2', '3']

    def test_preserves_first_occurrence(self):
        items = [make_item('1', title='First'), make_item('1', title='Second')]
        result = _deduplicate(items)
        assert len(result) == 1
        assert result[0].title == 'First'


class TestParseHtmlResultsNovel:
    NOVEL_HTML = '''
    <html><body>
    <ul>
        <li><a href="https://book.sfacg.com/Novel/43708">Test Novel</a>
            <img src="//rs.sfacg.com/cover.jpg" /></li>
        <li>综合信息：AuthorName/2025/1/15<br/>This is a long snippet text that exceeds twenty chars easily</li>
    </ul>
    <ul>
        <li><a href="https://book.sfacg.com/Novel/12345">Another Novel</a></li>
        <li>综合信息：AnotherAuthor/2024/12/1</li>
    </ul>
    </body></html>
    '''

    def test_parses_novel_results(self):
        results = _parse_html_results(self.NOVEL_HTML, 'novel')
        assert len(results) == 2
        assert results[0].id == '43708'
        assert results[0].title == 'Test Novel'
        assert results[0].author == 'AuthorName'
        assert results[0].updated == '2025/1/15'
        assert results[0].type == 'novel'

    def test_parses_cover_url(self):
        results = _parse_html_results(self.NOVEL_HTML, 'novel')
        assert 'cover.jpg' in results[0].cover
        assert results[0].cover.startswith('https:')

    def test_parses_snippet(self):
        results = _parse_html_results(self.NOVEL_HTML, 'novel')
        assert len(results[0].snippet) > 0

    def test_skips_comic_links_for_novel(self):
        html = '''
        <html><body>
        <ul>
            <li><a href="https://manhua.sfacg.com/mh/12345">Comic</a></li>
            <li>综合信息：Author/2025/1/1</li>
        </ul>
        </body></html>
        '''
        results = _parse_html_results(html, 'novel')
        assert len(results) == 0

    def test_empty_html(self):
        results = _parse_html_results('<html><body></body></html>', 'novel')
        assert results == []


class TestParseHtmlResultsComic:
    COMIC_HTML = '''
    <html><body>
    <ul>
        <li><a href="https://manhua.sfacg.com/mh/abc123">Comic Title</a>
            <img src="//rs.sfacg.com/comic_cover.jpg" /></li>
        <li>综合信息：ComicAuthor/2025/3/20</li>
    </ul>
    </body></html>
    '''

    def test_parses_comic_results(self):
        results = _parse_html_results(self.COMIC_HTML, 'comic')
        assert len(results) == 1
        assert results[0].id == 'abc123'
        assert results[0].title == 'Comic Title'
        assert results[0].type == 'comic'

    def test_skips_novel_links_for_comic(self):
        html = '''
        <html><body>
        <ul>
            <li><a href="https://book.sfacg.com/Novel/43708">Novel</a></li>
            <li>综合信息：Author/2025/1/1</li>
        </ul>
        </body></html>
        '''
        results = _parse_html_results(html, 'comic')
        assert len(results) == 0


class TestSearchApi:
    def test_parses_api_response(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        mock_data = {
            'Novels': [
                {
                    'NovelID': 43708,
                    'NovelName': 'Test Novel',
                    'AuthorName': 'Author',
                    'NovelCover': 'cover.jpg',
                    'Point': 8.5,
                },
                {
                    'NovelID': 12345,
                    'NovelName': 'Another',
                    'AuthorName': 'Writer',
                    'NovelCover': '',
                    'Point': 7.0,
                },
            ]
        }

        def mock_get_json(self, url, params=None):
            return mock_data

        monkeypatch.setattr(Fetcher, 'get_json', mock_get_json)
        results = search_novel_api('test')
        assert len(results) == 2
        assert results[0].id == '43708'
        assert results[0].title == 'Test Novel'
        assert results[0].score == 8.5
        assert 'cover.jpg' in results[0].cover
        assert results[1].score == 7.0

    def test_empty_api_response(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_json(self, url, params=None):
            return {}

        monkeypatch.setattr(Fetcher, 'get_json', mock_get_json)
        results = search_novel_api('nonexistent')
        assert results == []

    def test_api_response_no_novels_key(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_json(self, url, params=None):
            return {'error': 'something'}

        monkeypatch.setattr(Fetcher, 'get_json', mock_get_json)
        results = search_novel_api('test')
        assert results == []


class TestGetRelated:
    RELATED_HTML = '''
    <html><body>
    <div class="read-list">
        <div class="item">
            <a href="https://book.sfacg.com/Novel/111">
                <img src="//rs.sfacg.com/img1.jpg" />
            </a>
            <span class="book-name">Related Novel 1</span>
        </div>
        <div class="item">
            <a href="https://book.sfacg.com/Novel/222">
                <img src="//rs.sfacg.com/img2.jpg" />
            </a>
            <span class="book-name">Related Novel 2</span>
        </div>
    </div>
    </body></html>
    '''

    def test_parses_related_novels(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_html(self, url):
            return TestGetRelated.RELATED_HTML

        monkeypatch.setattr(Fetcher, 'get_html', mock_get_html)
        results = get_related('43708')
        assert len(results) == 2
        assert results[0].id == '111'
        assert results[0].title == 'Related Novel 1'
        assert results[1].id == '222'

    def test_empty_related(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_html(self, url):
            return '<html><body></body></html>'

        monkeypatch.setattr(Fetcher, 'get_html', mock_get_html)
        results = get_related('43708')
        assert results == []


class TestGetAuthorWorks:
    AUTHOR_HTML = '''
    <html><body>
    <div class="common-title">
        <h3>作者的其他作品</h3>
    </div>
    <div>
        <a href="https://book.sfacg.com/Novel/333">Work 1</a>
        <a href="https://book.sfacg.com/Novel/444">Work 2</a>
    </div>
    </body></html>
    '''

    def test_parses_author_works(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_html(self, url):
            return TestGetAuthorWorks.AUTHOR_HTML

        monkeypatch.setattr(Fetcher, 'get_html', mock_get_html)
        results = get_author_works('43708')
        assert len(results) == 2
        assert results[0].id == '333'
        assert results[0].title == 'Work 1'
        assert results[1].id == '444'

    def test_no_author_section(self, monkeypatch):
        from sfacglib.fetcher import Fetcher

        def mock_get_html(self, url):
            return '<html><body><h3>无关内容</h3></body></html>'

        monkeypatch.setattr(Fetcher, 'get_html', mock_get_html)
        results = get_author_works('43708')
        assert results == []


class TestSearchItemModel:
    def test_create_with_defaults(self):
        item = SearchItem(id='1', title='Test', url='https://example.com')
        assert item.id == '1'
        assert item.title == 'Test'
        assert item.score == 0.0
        assert item.type == 'novel'

    def test_create_with_all_fields(self):
        item = SearchItem(
            id='1', title='Test', author='Author', cover='https://example.com/cover.jpg',
            url='https://example.com', snippet='snippet', updated='2025/1/1',
            type='comic', score=9.5,
        )
        assert item.score == 9.5
        assert item.type == 'comic'

    def test_serialization(self):
        item = SearchItem(id='1', title='Test', url='https://example.com')
        data = item.model_dump()
        assert data['id'] == '1'
        assert 'title' in data

    def test_from_dict(self):
        data = {'id': '1', 'title': 'Test', 'url': 'https://example.com', 'score': 5.0}
        item = SearchItem(**data)
        assert item.id == '1'
        assert item.score == 5.0
