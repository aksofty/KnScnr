import asyncio

from database import Database
from tmdb.async_client import AsyncTMDBClient

GENRES = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Family": 10751,
    "Fantasy": 14,
    "History": 36,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Science Fiction": 878,
    "TV Movie": 10770,
    "Thriller": 53,
    "War": 10752,
    "Western": 37,
}

MOVIE_FIELDS = (
    "id",
    "title",
    "original_title",
    "release_date",
    "overview",
    "vote_average",
    "vote_count",
    "popularity",
)

PAGE_DELAY_SECONDS = 2


def _select_movie(movie: dict) -> dict:
    return {field: movie.get(field) for field in MOVIE_FIELDS}


def _collect_movies(movies: list, blacklisted_ids: set) -> list:
    return [
        _select_movie(movie)
        for movie in movies
        if movie["id"] not in blacklisted_ids
    ]


async def get_candidates(
    client: AsyncTMDBClient,
    db: Database,
    params: dict,
    page_limit: int = 5,
    blacklist_limit: int = 100,
) -> str:
    published_films = await db.get_agent_researcher_memory(limit=blacklist_limit)
    blacklisted_ids = {film.tmdb_id for film in published_films}

    request_params = dict(params)
    response = await client.discover_movie(params=request_params)
    all_movies = _collect_movies(response.get("results", []), blacklisted_ids)

    max_page = min(response.get("total_pages", 1), page_limit)
    for page in range(2, max_page + 1):
        await asyncio.sleep(PAGE_DELAY_SECONDS)
        request_params["page"] = page
        response = await client.discover_movie(params=request_params)
        all_movies.extend(_collect_movies(response.get("results", []), blacklisted_ids))

    return "\n".join(map(str, all_movies))


def get_genres_string(genres_names: list) -> str:
    genre_ids = [GENRES[name] for name in genres_names if name in GENRES]
    return "|".join(map(str, genre_ids))
