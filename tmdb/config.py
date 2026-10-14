"""Конфигурация для работы с TMDB API."""

import os
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_LANGUAGE = "ru-RU"


@dataclass
class TMDBConfig:
    """Настройки подключения к TMDB API.

    Токен можно передать явно или взять из переменной окружения
    TMDB_API_TOKEN (рекомендуемый способ).
    """

    api_token: str = field(
        default_factory=lambda: os.getenv("TMDB_API_TOKEN", "")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv("TMDB_BASE_URL", DEFAULT_BASE_URL)
    )
    language: str = field(
        default_factory=lambda: os.getenv("TMDB_LANGUAGE", DEFAULT_LANGUAGE)
    )
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if not self.api_token:
            raise ValueError(
                "Не задан TMDB API токен. Укажите его в переменной окружения "
                "TMDB_API_TOKEN или передайте в TMDBConfig(api_token=...)."
            )

    @property
    def headers(self) -> dict:
        """HTTP-заголовки для авторизации по Bearer-токену."""
        return {
            "accept": "application/json",
            "authorization": f"Bearer {self.api_token}",
        }