from unittest.mock import MagicMock

from sfacglib.fetcher import Fetcher
from sfacglib.models import SearchItem
from sfacglib.search import (
    _deduplicate,
    _parse_html_results,
    _parse_info_text,
    search_comic_api,
    search_lolobun,
    search_lolobun_comic,
    search_lolobun_novel,
    search_novel_api,
)


def make_item(id: str, title: str = '', **kwargs) -> SearchItem:
    defaults = dict(
        id=id,
        title=title or f'Novel {id}',
        author='',
        cover='',
        url=f'https://book.sfacg.com/Novel/{id}',
        snippet='',
        updated='',
        type='novel',
        score=0.0,
    )
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


class TestParseInfoText:
    def test_normal(self):
        author, date = _parse_info_text('综合信息：AuthorName/2025/1/15')
        assert author == 'AuthorName'
        assert date == '2025/1/15'

    def test_no_prefix(self):
        author, date = _parse_info_text('some random text')
        assert author == ''
        assert date == ''

    def test_no_date(self):
        author, date = _parse_info_text('综合信息：AuthorName')
        assert author == 'AuthorName'
        assert date == ''

    def test_colon_variant(self):
        author, date = _parse_info_text('综合信息:AuthorName/2025/1/1')
        assert author == 'AuthorName'
        assert date == '2025/1/1'


class TestParseHtmlResultsNovel:
    NOVEL_HTML = """
    <html><body>
    <ul>
        <li><a href="https://book.sfacg.com/Novel/43708">Test Novel</a>
            <img src="//rs.sfacg.com/cover.jpg" /></li>
        <li>综合信息：AuthorName/2025/1/15</li>
    </ul>
    <ul>
        <li><a href="https://book.sfacg.com/Novel/12345">Another Novel</a></li>
        <li>综合信息：AnotherAuthor/2024/12/1</li>
    </ul>
    </body></html>
    """

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

    def test_skips_comic_links_for_novel(self):
        html = """
        <html><body>
        <ul>
            <li><a href="https://manhua.sfacg.com/mh/12345">Comic</a></li>
            <li>综合信息：Author/2025/1/1</li>
        </ul>
        </body></html>
        """
        results = _parse_html_results(html, 'novel')
        assert len(results) == 0

    def test_empty_html(self):
        results = _parse_html_results('<html><body></body></html>', 'novel')
        assert results == []


class TestParseHtmlResultsComic:
    COMIC_HTML = """
    <html><body>
    <ul>
        <li><a href="https://manhua.sfacg.com/mh/abc123">Comic Title</a>
            <img src="//rs.sfacg.com/comic_cover.jpg" /></li>
        <li>综合信息：ComicAuthor/2025/3/20</li>
    </ul>
    </body></html>
    """

    def test_parses_comic_results(self):
        results = _parse_html_results(self.COMIC_HTML, 'comic')
        assert len(results) == 1
        assert results[0].id == 'abc123'
        assert results[0].title == 'Comic Title'
        assert results[0].type == 'comic'

    def test_skips_novel_links_for_comic(self):
        html = """
        <html><body>
        <ul>
            <li><a href="https://book.sfacg.com/Novel/43708">Novel</a></li>
            <li>综合信息：Author/2025/1/1</li>
        </ul>
        </body></html>
        """
        results = _parse_html_results(html, 'comic')
        assert len(results) == 0


class TestSearchNovelApi:
    MOCK_DATA = {
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

    def test_parses_api_response(self, monkeypatch):
        mock_data = self.MOCK_DATA
        monkeypatch.setattr(Fetcher, 'get_json', lambda self, url, params=None: mock_data)
        results = search_novel_api('test')
        assert len(results) == 2
        assert results[0].id == '43708'
        assert results[0].title == 'Test Novel'
        assert results[0].score == 8.5
        assert 'cover.jpg' in results[0].cover
        assert results[1].score == 7.0

    def test_empty_api_response(self, monkeypatch):
        monkeypatch.setattr(Fetcher, 'get_json', lambda self, url, params=None: {})
        results = search_novel_api('nonexistent')
        assert results == []


class TestSearchComicApi:
    MOCK_DATA = {
        'comics': [
            {
                'ComicID': 999,
                'ComicName': 'Test Comic',
                'AuthorName': 'Comic Author',
                'ComicCover': 'https://example.com/cover.jpg',
                'FolderName': 'test-comic',
                'LastChapterTitle': 'Chapter 10',
                'LastUpdateDate': '2025/01/15',
                'Point': 9.0,
            },
        ]
    }

    def test_parses_api_response(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_DATA
        monkeypatch.setattr(Fetcher, 'post', lambda self, url, **kw: mock_resp)
        results = search_comic_api('test')
        assert len(results) == 1
        assert results[0].id == '999'
        assert results[0].title == 'Test Comic'
        assert results[0].score == 9.0
        assert results[0].type == 'comic'

    def test_empty_api_response(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        monkeypatch.setattr(Fetcher, 'post', lambda self, url, **kw: mock_resp)
        results = search_comic_api('nonexistent')
        assert results == []


class TestSearchLolobun:
    MOCK_DATA = {
        'status': {'errorCode': 200, 'msg': None},
        'data': {
            'Keyword': 'dragon',
            'Tab': 'novel',
            'PageIndex': 0,
            'PageSize': 20,
            'HasMore': True,
            'Items': [
                {
                    'EntityId': 5320155,
                    'EntityType': 'Novel',
                    'Title': 'Shut up, Evil Dragon',
                    'AuthorName': 'Milkshake Tail Tail Sauce',
                    'Cover': '2025/01/cc9769bc.jpg',
                    'TypeName': 'Magic',
                    'Intro': 'A story about dragons...',
                    'Url': '/n/5320155',
                    'Weight': 1230802,
                },
                {
                    'EntityId': 5320059,
                    'EntityType': 'Novel',
                    'Title': 'Reborn as a young dragon girl',
                    'AuthorName': 'Tangtang',
                    'Cover': '2023/02/68444fdb.jpg',
                    'TypeName': 'Magic',
                    'Intro': 'How many times...',
                    'Url': '/n/5320059',
                    'Weight': 17575,
                },
            ],
        },
    }

    MOCK_COMIC_DATA = {
        'status': {'errorCode': 200, 'msg': None},
        'data': {
            'Keyword': 'dragon',
            'Tab': 'comic',
            'PageIndex': 0,
            'PageSize': 20,
            'HasMore': False,
            'Items': [
                {
                    'EntityId': 20103,
                    'EntityType': 'Comic',
                    'Title': 'Shut up, Evil Dragon Comic',
                    'AuthorName': 'SFACG',
                    'Cover': '202502/75047ec3.jpg',
                    'TypeName': 'Magic',
                    'Intro': 'Comic intro...',
                    'Url': '/c/20103',
                    'Weight': 5909894,
                },
            ],
        },
    }

    def test_novel_search(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_DATA
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun('dragon', search_type='novel')
        assert len(results) == 2
        assert results[0].id == '5320155'
        assert results[0].title == 'Shut up, Evil Dragon'
        assert results[0].author == 'Milkshake Tail Tail Sauce'
        assert results[0].type == 'novel'
        assert results[0].score == 1230802.0
        assert 'lolobun.com' in results[0].url
        assert '/n/5320155' in results[0].url

    def test_comic_search(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_COMIC_DATA
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun('dragon', search_type='comic')
        assert len(results) == 1
        assert results[0].id == '20103'
        assert results[0].type == 'comic'
        assert '/c/20103' in results[0].url

    def test_cover_url_construction(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_DATA
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun('dragon')
        assert results[0].cover.startswith('https://')
        assert 'NovelCover' in results[0].cover

    def test_empty_results(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'data': {'Items': []}}
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun('nonexistent')
        assert results == []

    def test_novel_search_convenience(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_DATA
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun_novel('dragon')
        assert len(results) == 2

    def test_comic_search_convenience(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_COMIC_DATA
        monkeypatch.setattr(Fetcher, 'get', lambda self, url, **kw: mock_resp)
        results = search_lolobun_comic('dragon')
        assert len(results) == 1


class TestSearchItemModel:
    def test_create_with_defaults(self):
        item = SearchItem(id='1', title='Test', url='https://example.com')
        assert item.id == '1'
        assert item.title == 'Test'
        assert item.score == 0.0
        assert item.type == 'novel'

    def test_create_with_all_fields(self):
        item = SearchItem(
            id='1',
            title='Test',
            author='Author',
            cover='https://example.com/cover.jpg',
            url='https://example.com',
            snippet='snippet',
            updated='2025/1/1',
            type='comic',
            score=9.5,
        )
        assert item.score == 9.5
        assert item.type == 'comic'

    def test_serialization(self):
        item = SearchItem(id='1', title='Test', url='https://example.com')
        data = item.model_dump()
        assert data['id'] == '1'
        assert 'title' in data
