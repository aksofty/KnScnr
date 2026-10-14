import logging
from typing import List, Optional, Union

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, InputMediaPhoto

logger = logging.getLogger(__name__)


class TgPoster:
    """Класс для асинхронной публикации постов в Telegram канал или группу."""

    MAX_CAPTION_LENGTH = 1024
    MIN_GALLERY_SIZE = 2
    MAX_GALLERY_SIZE = 10
    TRUNCATION_SUFFIX = "..."

    def __init__(self, bot_token: str, channel_id: str):
        self.bot = Bot(token=bot_token)
        self.channel_id = channel_id

    async def __aenter__(self) -> "TgPoster":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def close(self) -> None:
        await self.bot.session.close()

    @classmethod
    def _truncate_caption(cls, caption: Optional[str]) -> Optional[str]:
        """Обрезка caption до максимально допустимой длины."""
        if not caption or len(caption) <= cls.MAX_CAPTION_LENGTH:
            return caption
        return caption[: cls.MAX_CAPTION_LENGTH - len(cls.TRUNCATION_SUFFIX)] + cls.TRUNCATION_SUFFIX

    @staticmethod
    def _media_source(path_or_url: str) -> Union[str, FSInputFile]:
        """Вернуть URL как есть либо обернуть локальный путь в FSInputFile."""
        return path_or_url if path_or_url.startswith("http") else FSInputFile(path_or_url)

    async def _send(self, action: str, coro) -> bool:
        """Выполнить отправку и вернуть результат без проброса исключения."""
        try:
            await coro
            return True
        except Exception as exc:
            logger.error("Ошибка при отправке %s: %s", action, exc)
            return False

    async def send_text(self, text: str, disable_preview: bool = False) -> bool:
        """Отправка текстового сообщения."""
        return await self._send(
            "текста",
            self.bot.send_message(
                chat_id=self.channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=disable_preview,
            ),
        )

    async def send_photo(self, photo_path_or_url: str, caption: Optional[str] = None) -> bool:
        """Отправка фото (по URL или пути к локальному файлу) с подписью."""
        return await self._send(
            "фото",
            self.bot.send_photo(
                chat_id=self.channel_id,
                photo=self._media_source(photo_path_or_url),
                caption=self._truncate_caption(caption),
                parse_mode=ParseMode.HTML,
            ),
        )

    async def send_gallery(self, photos: List[str], caption: Optional[str] = None) -> bool:
        """
        Отправка галереи (альбома) из 2-10 фотографий.

        :param photos: Список путей к файлам или URL-ссылок на изображения.
        :param caption: Подпись к альбому (прикрепляется к первому фото, обрезается до 1024 симв.).
        """
        if not self.MIN_GALLERY_SIZE <= len(photos) <= self.MAX_GALLERY_SIZE:
            logger.error(
                "Галерея должна содержать от %d до %d фотографий.",
                self.MIN_GALLERY_SIZE,
                self.MAX_GALLERY_SIZE,
            )
            return False

        safe_caption = self._truncate_caption(caption)
        media_group: List[InputMediaPhoto] = []

        for index, item in enumerate(photos):
            media = self._media_source(item)
            if index == 0 and safe_caption:
                media_group.append(
                    InputMediaPhoto(media=media, caption=safe_caption, parse_mode=ParseMode.HTML)
                )
            else:
                media_group.append(InputMediaPhoto(media=media))

        return await self._send(
            "галереи",
            self.bot.send_media_group(chat_id=self.channel_id, media=media_group),
        )
