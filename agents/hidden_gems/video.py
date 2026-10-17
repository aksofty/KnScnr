import logging
import os

import yt_dlp

logger = logging.getLogger(__name__)

MAX_VIDEO_HEIGHT = 720
PLAYER_CLIENTS = (None, "android", "android_vr")


class _YtDlpLogger:
    """Направляет вывод yt-dlp в стандартный логгер, не засоряя консоль."""

    def debug(self, message: str) -> None:
        logger.debug(message)

    def info(self, message: str) -> None:
        logger.debug(message)

    def warning(self, message: str) -> None:
        logger.debug(message)

    def error(self, message: str) -> None:
        logger.debug(message)


BASE_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 20,
    "retries": 3,
    "logger": _YtDlpLogger(),
}
FORMAT_WITH_AUDIO = (
    f"best[height<={MAX_VIDEO_HEIGHT}][ext=mp4][vcodec!=none][acodec!=none]"
    f"/best[height<={MAX_VIDEO_HEIGHT}][vcodec!=none][acodec!=none]"
)
FORMAT_VIDEO_ONLY = (
    f"best[height<={MAX_VIDEO_HEIGHT}][ext=mp4][vcodec!=none]"
    f"/best[height<={MAX_VIDEO_HEIGHT}][vcodec!=none]"
)


def _options(format_selector: str, player_client: str | None, **extra) -> dict:
    options = {**BASE_OPTIONS, "format": format_selector, **extra}
    if player_client:
        options["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    return options


def _download_info(trailer_url: str, format_selector: str, **extra) -> dict | None:
    """Скачать видео, перебирая клиенты YouTube при ошибке формата."""
    for player_client in PLAYER_CLIENTS:
        options = _options(format_selector, player_client, **extra)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(trailer_url, download=True)
        except Exception as exc:
            logger.debug(
                "yt-dlp (%s) не смог обработать %s: %s",
                player_client or "default",
                trailer_url,
                exc,
            )
            continue
        if info:
            return info
    return None


def download_video(trailer_url: str, directory: str) -> str | None:
    """Скачать видео с качеством не выше 720p в указанную директорию."""
    outtmpl = os.path.join(directory, "%(id)s.%(ext)s")
    info = _download_info(
        trailer_url, FORMAT_WITH_AUDIO, outtmpl=outtmpl
    )
    if not info:
        info = _download_info(
            trailer_url, FORMAT_VIDEO_ONLY, outtmpl=outtmpl
        )
    if not info:
        logger.warning("Не удалось скачать видео %s.", trailer_url)
        return None

    for download in info.get("requested_downloads") or []:
        path = download.get("filepath")
        if path and os.path.exists(path):
            return path

    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None
