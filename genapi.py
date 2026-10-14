"""Асинхронный клиент для работы с GenAPI."""

import json
import logging
from typing import Any, Callable, Optional

import aiohttp


logger = logging.getLogger(__name__)


class GenAPIError(Exception):
    """Ошибка при работе с GenAPI."""


class GenAPIResponseFormatError(GenAPIError):
    """Ответ GenAPI имеет неподдерживаемый формат или содержит некорректный JSON."""


class GenAPIClient:
    """Асинхронный клиент GenAPI в синхронном режиме."""

    BASE_URL = "https://api.gen-api.ru/api/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2-5-flash-lite",
        *,
        timeout: int = 180,
    ) -> None:
        if not api_key:
            raise ValueError("api_key не может быть пустым")

        if not model:
            raise ValueError("model не может быть пустым")

        self.api_key = api_key
        self.model = model

        self.timeout = aiohttp.ClientTimeout(
            total=timeout
        )

        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Создать HTTP-сессию."""

        if self._session is not None:
            if not self._session.closed:
                return

        self._session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            timeout=self.timeout,
        )

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""

        if self._session is not None:
            if not self._session.closed:
                await self._session.close()

            self._session = None

    async def __aenter__(self) -> "GenAPIClient":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def generate(
        self,
        messages: list[dict[str, str]],
        json_format: Optional[dict[str, Any]] = None,
        model: Optional[str] = None
    ) -> str:
        if not messages:
            raise ValueError(
                "messages не может быть пустым"
            )

        await self.start()

        if self._session is None:
            raise GenAPIError(
                "HTTP-сессия не создана"
            )

        payload = {
            "is_sync": True,
            "messages": messages,
        }

        if json_format is not None:
            payload["json_format"] = json_format

        if model is not None:
            url = (
                f"{self.BASE_URL}/networks/{model}"
            )
        else:
            url = (
                f"{self.BASE_URL}/networks/{self.model}"
            )

        try:
            async with self._session.post(
                url,
                json=payload,
            ) as response:

                body = await response.text()

                if response.status >= 400:
                    raise GenAPIError(
                        f"GenAPI HTTP {response.status}: {body}"
                    )

                data = await response.json()

        except aiohttp.ClientError as exc:
            logger.exception(
                "Ошибка HTTP GenAPI"
            )

            raise GenAPIError(
                "Ошибка HTTP при обращении к GenAPI"
            ) from exc

        return data

    def get_response_content(self, result: dict[str, Any]) -> str:
        """Извлечь текст ответа из поддерживаемых форматов GenAPI."""
        paths = (
            ("response", 0, "choices", 0, "message", "content"),
            ("response", 0, "message", "content"),
        )

        for path in paths:
            value: Any = result

            try:
                for key in path:
                    value = value[key]
            except (KeyError, IndexError, TypeError):
                continue

            if not isinstance(value, str):
                continue

            return value

        raise GenAPIResponseFormatError(
            "Не удалось найти ответ GenAPI ни в одном из поддерживаемых форматов."
        )

    def parse_json_response(self, result: dict[str, Any]) -> Any:
        """Извлечь и разобрать JSON из поддерживаемых форматов ответа GenAPI."""
        content = self.get_response_content(result)

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise GenAPIResponseFormatError(
                "Ответ GenAPI найден, но его содержимое не является корректным JSON."
            ) from exc

    

   
