"""Асинхронный клиент для работы с TMDB API."""

import asyncio
import json
import logging
from typing import Any, Optional

import aiohttp

from tmdb.config import TMDBConfig
from tmdb.exceptions import (
    TMDBAuthError,
    TMDBConnectionError,
    TMDBNotFoundError,
    TMDBRateLimitError,
    TMDBRequestError,
    TMDBServerError,
)

logger = logging.getLogger(__name__)


def _extract_message(text: str) -> str:
    """Извлечь сообщение об ошибке из тела ответа TMDB."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text

    if isinstance(data, dict):
        return data.get("status_message") or data.get("message") or text
    return text


class AsyncTMDBClient:
    """Асинхронный клиент TMDB API на базе aiohttp.

    Пример использования:
        async with AsyncTMDBClient() as client:
            movies = await client.search_movie("action", year=2025)
    """

    def __init__(
        self,
        config: Optional[TMDBConfig] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.config = config or TMDBConfig()
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Вернуть (при необходимости создав) HTTP-сессию."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.config.headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Закрыть HTTP-сессию, если она создана этим клиентом."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "AsyncTMDBClient":
        await self._get_session()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._owns_session:
            await self.close()

    async def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Выполнить GET-запрос к API и вернуть JSON."""
        session = await self._get_session()
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"

        request_params = {"language": self.config.language}
        if params:
            request_params.update(params)

        try:
            async with session.get(url, params=request_params) as response:
                if response.status == 200:
                    return await response.json()

                message = _extract_message(await response.text())

                if response.status in (401, 403):
                    raise TMDBAuthError(response.status, message)
                if response.status == 404:
                    raise TMDBNotFoundError(response.status, message)
                if response.status == 429:
                    raise TMDBRateLimitError(
                        response.status,
                        message,
                        retry_after=response.headers.get("Retry-After"),
                    )
                if response.status >= 500:
                    raise TMDBServerError(response.status, message)

                raise TMDBRequestError(response.status, message)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("Ошибка соединения с TMDB (%s): %s", url, exc)
            raise TMDBConnectionError(
                f"Не удалось соединиться с TMDB API ({url}): {exc}"
            ) from exc

    async def search_movie(
        self,
        query: str,
        year: Optional[int] = None,
        min_rating: Optional[float] = None,
    ) -> dict:
        """Поиск фильмов.

        :param query: поисковый запрос.
        :param year: фильтр по году выпуска.
        :param min_rating: минимальный средний рейтинг (vote_average.gte).
        """
        params: dict = {"query": query}
        if year is not None:
            params["year"] = year
        if min_rating is not None:
            params["vote_average.gte"] = min_rating

        return await self._get("search/movie", params)

    async def discover_movie(self, params: Optional[dict] = None) -> dict:
        """Discover-запрос фильмов с произвольными параметрами."""
        return await self._get("discover/movie", params or {})

    async def get_movie(self, movie_id: int) -> dict:
        """Получить детали фильма по id."""
        return await self._get(f"movie/{movie_id}")

    async def get_movie_images(self, movie_id: int) -> dict:
        """Получить фото фильма по id."""
        return await self._get(f"movie/{movie_id}/images?include_image_language=null")

    async def get_movie_reviews(self, movie_id: int) -> dict:
        return await self._get(f"movie/{movie_id}/reviews")

    async def get_movie_videos(self, movie_id: int, language:str = None) -> dict:
        if language is not None:
            return await self._get(f"movie/{movie_id}/videos", params={"language": language})
        
        return await self._get(f"movie/{movie_id}/videos")

    async def get_movie_credits(self, movie_id: int) -> dict:
        return await self._get(f"movie/{movie_id}/credits")

    

    async def get_popular_movies(self, page: int = 1) -> dict:
        """Получить список популярных фильмов."""
        return await self._get("movie/popular", {"page": page})

    async def get_person(self, person_id: int) -> dict:
        """Получить данные актера по id."""
        return await self._get(f"person/{person_id}")

    async def get_person_images(self, person_id: int) -> dict:
        """Получить фото актера по id."""
        return await self._get(f"person/{person_id}/images")

    async def get_person_movie_credits(self, person_id: int) -> dict:
        """Получить фильмы актера по id."""
        return await self._get(f"person/{person_id}/movie_credits")

    async def keyword_search(self, query: str = None, page: int = 1) -> dict:
            """Поиск ключевых слов."""
            if query is None:
                raise ValueError("query is required")
            return await self._get("search/keyword", {"query": query, "page": page})
    
    async def keywords_search(self, keywords: list = None) -> dict:
        """Поиск ключевых слов."""
        if keywords is None:
            raise ValueError("keywords is required")
        keywords_ids = []
        for keyword in keywords:
            result = await self.keyword_search(keyword)
            results = result.get('results')
            if results and 'id' in results[0]:
                keywords_ids.append(results[0]['id'])
            
        return keywords_ids
                    