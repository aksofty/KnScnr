"""Исключения модуля TMDB."""


class TMDBError(Exception):
    """Базовое исключение для всех ошибок модуля TMDB."""


class TMDBRequestError(TMDBError):
    """Ошибка при выполнении HTTP-запроса к TMDB API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"TMDB API вернул ошибку {status_code}: {message}")


class TMDBAuthError(TMDBRequestError):
    """Ошибка авторизации: неверный или отсутствующий токен (401/403)."""


class TMDBNotFoundError(TMDBRequestError):
    """Запрошенный ресурс не найден (404)."""


class TMDBRateLimitError(TMDBRequestError):
    """Превышен лимит запросов (429)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(status_code, message)
        self.retry_after = retry_after


class TMDBServerError(TMDBRequestError):
    """Ошибка на стороне TMDB (5xx)."""


class TMDBConnectionError(TMDBError):
    """Ошибка соединения с TMDB API: сеть, DNS, таймаут."""