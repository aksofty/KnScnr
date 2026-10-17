import logging
from typing import List, Optional, Union

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

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

    async def send_video(self, video_path_or_url: str, caption: Optional[str] = None) -> bool:
        """Отправка видео (по URL или пути к локальному файлу) с подписью."""
        return await self._send(
            "видео",
            self.bot.send_video(
                chat_id=self.channel_id,
                video=self._media_source(video_path_or_url),
                caption=self._truncate_caption(caption),
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
            ),
        )

    async def send_gallery(
        self,
        photos: List[str],
        caption: Optional[str] = None,
        video: Optional[str] = None,
    ) -> bool:
        """
        Отправка галереи (альбома) из 2-10 медиафайлов.

        :param photos: Список путей к файлам или URL-ссылок на изображения.
        :param caption: Подпись к альбому (прикрепляется к первому элементу, обрезается до 1024 симв.).
        :param video: Путь или URL видео, которое заменяет второе изображение.
        """
        media_items: List[tuple[str, str]] = [("photo", item) for item in photos]
        if video:
            if len(media_items) >= 2:
                media_items[1] = ("video", video)
            else:
                media_items.append(("video", video))

        if not self.MIN_GALLERY_SIZE <= len(media_items) <= self.MAX_GALLERY_SIZE:
            logger.error(
                "Галерея должна содержать от %d до %d медиафайлов.",
                self.MIN_GALLERY_SIZE,
                self.MAX_GALLERY_SIZE,
            )
            return False

        safe_caption = self._truncate_caption(caption)
        caption_options = (
            {"caption": safe_caption, "parse_mode": ParseMode.HTML}
            if safe_caption
            else {}
        )
        media_group: List[InputMediaPhoto | InputMediaVideo] = []

        for index, (media_type, item) in enumerate(media_items):
            media = self._media_source(item)
            options = caption_options if index == 0 else {}
            if media_type == "video":
                media_group.append(
                    InputMediaVideo(media=media, supports_streaming=True, **options)
                )
            else:
                media_group.append(InputMediaPhoto(media=media, **options))

        return await self._send(
            "галереи",
            self.bot.send_media_group(chat_id=self.channel_id, media=media_group),
        )
