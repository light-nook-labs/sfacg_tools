from pydantic import BaseModel


class SearchItem(BaseModel):
    id: str
    title: str
    author: str = ''
    cover: str = ''
    url: str
    snippet: str = ''
    updated: str = ''
    type: str = 'novel'
    score: float = 0.0
