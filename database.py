from __future__ import annotations
import json
import math
import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, select, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ============================================================
# Exceptions
# ============================================================

class DatabaseError(Exception):
    """Базовая ошибка БД."""


class ActorDatabaseError(DatabaseError):
    """Ошибка при работе с актером."""


# ============================================================
# Models
# ============================================================

class Base(AsyncAttrs, DeclarativeBase):
    pass


class Actors(Base):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_name: Mapped[str] = mapped_column(String, nullable=False)
    main_roles_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        index=True,
    )


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.now, 
        nullable=False,
        index=True,
    )


class AgentResearcherMemory(Base):
    __tablename__ = "agent_researcher_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    reasoning: Mapped[str] = mapped_column(String)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.now, 
        nullable=False,
        index=True,
    )

class TelegramPost(Base):
    __tablename__ = "telegram_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    post_text: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.now, 
        nullable=False,
        index=True,
    )


# ============================================================
# Database
# ============================================================

class Database:
    def __init__(
        self,
        url: str = "sqlite+aiosqlite:///tenkino.db",
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
            echo=False,
        )

        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    # ========================================================
    # Init / close
    # ========================================================

    async def init(self) -> None:
        try:
            async with self.engine.begin() as connection:
                await connection.run_sync(
                    Base.metadata.create_all
                )
                await self._migrate_sqlite(connection)

        except SQLAlchemyError as exc:
            logger.exception("Не удалось инициализировать БД")
            raise DatabaseError(
                "Не удалось инициализировать базу данных"
            ) from exc

    async def close(self) -> None:
        try:
            await self.engine.dispose()
        except SQLAlchemyError:
            logger.exception("Ошибка при закрытии БД")

    async def _migrate_sqlite(self, connection: AsyncConnection) -> None:
        """Добавить новые колонки в существующую SQLite-базу."""
        if self.engine.dialect.name != "sqlite":
            return

        result = await connection.exec_driver_sql(
            "PRAGMA table_info(agent_researcher_memory)"
        )
        columns = {row[1] for row in result.fetchall()}
        if "message_id" not in columns:
            await connection.exec_driver_sql(
                "ALTER TABLE agent_researcher_memory ADD COLUMN message_id INTEGER"
            )

    # ========================================================
    # Actors
    # ========================================================

    async def add_actor(
        self,
        rank: int,
        actor_name: str,
        main_roles_count: int,
        tmdb_id: int,
        posted_at: datetime | None = None,
    ) -> Actors:
        actor = Actors(
            rank=rank,
            actor_name=actor_name,
            main_roles_count=main_roles_count,
            tmdb_id=tmdb_id,
            posted_at=posted_at,
        )

        try:
            async with self.session_factory() as session:
                session.add(actor)
                await session.commit()
                await session.refresh(actor)
                return actor
        except IntegrityError as exc:
            logger.exception("Ошибка целостности при добавлении актера tmdb_id=%s", tmdb_id)
            raise ActorDatabaseError(
                f"Не удалось добавить актера tmdb_id={tmdb_id}"
            ) from exc
        except SQLAlchemyError as exc:
            logger.exception("Ошибка БД при добавлении актера tmdb_id=%s", tmdb_id)
            raise ActorDatabaseError(
                f"Ошибка БД при добавлении актера tmdb_id={tmdb_id}"
            ) from exc

    async def update_actor(self, tmdb_id: int, **values: Any) -> Actors | None:
        allowed_fields = {"rank", "actor_name", "main_roles_count", "posted_at"}
        invalid_fields = values.keys() - allowed_fields
        if invalid_fields:
            raise ValueError(f"Недопустимые поля актера: {', '.join(sorted(invalid_fields))}")
        if not values:
            raise ValueError("Не указаны поля для обновления")

        try:
            async with self.session_factory() as session:
                actor = await session.scalar(
                    select(Actors).where(Actors.tmdb_id == tmdb_id)
                )
                if actor is None:
                    return None

                for field, value in values.items():
                    setattr(actor, field, value)

                await session.commit()
                await session.refresh(actor)
                return actor
        except SQLAlchemyError as exc:
            logger.exception("Ошибка БД при обновлении актера tmdb_id=%s", tmdb_id)
            raise ActorDatabaseError(
                f"Не удалось обновить актера tmdb_id={tmdb_id}"
            ) from exc

    async def get_actors(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str = "rank",
        descending: bool = False,
        limit: int | None = None,
    ) -> list[Actors]:
        actor_fields = {"id", "rank", "actor_name", "main_roles_count", "tmdb_id", "posted_at"}
        filters = filters or {}
        invalid_fields = filters.keys() - actor_fields
        if invalid_fields:
            raise ValueError(f"Недопустимые поля фильтра: {', '.join(sorted(invalid_fields))}")
        if order_by not in actor_fields:
            raise ValueError(f"Недопустимое поле сортировки: {order_by}")
        if limit is not None and limit <= 0:
            raise ValueError("limit должен быть больше 0")

        query = select(Actors)
        for field, value in filters.items():
            query = query.where(getattr(Actors, field) == value)

        sort_column = getattr(Actors, order_by)
        query = query.order_by(sort_column.desc() if descending else sort_column.asc())
        if limit is not None:
            query = query.limit(limit)

        try:
            async with self.session_factory() as session:
                result = await session.scalars(query)
                return list(result.all())
        except SQLAlchemyError as exc:
            logger.exception("Ошибка БД при получении актеров")
            raise ActorDatabaseError("Не удалось получить актеров") from exc

    async def get_random_actor_due_for_post(
        self,
        cooldown_days: int,
    ) -> Actors | None:
        if cooldown_days < 0:
            raise ValueError("cooldown_days не может быть отрицательным")

        cutoff = datetime.now() - timedelta(days=cooldown_days)
        query = (
            select(Actors)
            .where(or_(Actors.posted_at.is_(None), Actors.posted_at < cutoff))
            .order_by(func.random())
            .limit(1)
        )

        try:
            async with self.session_factory() as session:
                return await session.scalar(query)
        except SQLAlchemyError as exc:
            logger.exception("Ошибка БД при выборе случайного актера для публикации")
            raise ActorDatabaseError(
                "Не удалось выбрать случайного актера для публикации"
            ) from exc

    async def add_agent_memory(
        self,
        data: dict[str, Any],
        created_at: datetime | None = None,
    ) -> AgentMemory:
        """
        Добавить запись в память агента.

        :param data: Данные памяти в виде словаря (сохраняются как JSON).
        :param created_at: Время создания записи (нативное время без часового пояса).
            Если не передано — используется текущее локальное/naive время.
        """

        if not data:
            raise ValueError("data не может быть пустым")

        # Передаем "нативную" (naive) дату без timezone, как требовалось для SQLite
        if created_at is None:
            created_at = datetime.now()
        elif created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)

        try:
            async with self.session_factory() as session:
                memory = AgentMemory(
                    data=data,
                    created_at=created_at,
                )

                session.add(memory)

                await session.commit()
                await session.refresh(memory)

                return memory

        except SQLAlchemyError as exc:
            logger.exception("Ошибка при добавлении памяти агента")

            raise DatabaseError("Не удалось добавить запись в память агента") from exc

    from sqlalchemy import select

    async def get_agent_memory(
        self,
        limit: int = 10,
    ) -> list[AgentMemory]:
        """
        Получить список записей из памяти агента, отсортированных от новых к старым.

        :param limit: Максимальное количество возвращаемых записей (по умолчанию 10).
        :return: Список объектов AgentMemory.
        """
        if limit <= 0:
            raise ValueError("limit должен быть больше 0")

        try:
            async with self.session_factory() as session:
                stmt = (
                    select(AgentMemory)
                    .order_by(AgentMemory.created_at.desc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                return list(result.scalars().all())

        except SQLAlchemyError as exc:
            logger.exception("Ошибка при получении памяти агента")

            raise DatabaseError("Не удалось получить записи из памяти агента") from exc


    async def add_agent_researcher_memory(
        self,
        tmdb_id: int,
        title: str,
        reasoning: str,
        message_id: int | None = None,
        created_at: datetime | None = None,
    )-> AgentResearcherMemory:
        """
        Добавить запись в память агента.

        :param tmdb_id: Идентификатор фильма в TMDB.
        :param title: Название фильма.
        :param reasoning: Обоснование выбора фильма.
        :param message_id: ID опубликованного поста в Telegram.
        :param created_at: Время создания записи (нативное время без часового пояса).
            Если не передано — используется текущее локальное/naive время.
        """
        if not tmdb_id:
            raise ValueError("tmdb_id не может быть пустым")

        # Передаем "нативную" (naive) дату без timezone, как требовалось для SQLite
        if created_at is None:
            created_at = datetime.now()
        elif created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)

        try:
            async with self.session_factory() as session:
                memory = AgentResearcherMemory(
                    tmdb_id=tmdb_id,
                    title=title,
                    reasoning=reasoning,
                    message_id=message_id,
                    created_at=created_at,
                )

                session.add(memory)

                await session.commit()
                await session.refresh(memory)

                return memory

        except SQLAlchemyError as exc:
            logger.exception("Ошибка при добавлении памяти агента 2")

            raise DatabaseError("Не удалось добавить запись в память агента 2") from exc


    async def get_agent_researcher_memory(
        self,
        limit: int = 10,
    ) -> list[AgentResearcherMemory]:
        """
        Получить список записей из памяти агента 2, отсортированных от новых к старым.

        :param limit: Максимальное количество возвращаемых записей (по умолчанию 10).
        :return: Список объектов AgentResearcherMemory.
        """
        if limit <= 0:
            raise ValueError("limit должен быть больше 0")

        try:
            async with self.session_factory() as session:
                stmt = (
                    select(AgentResearcherMemory)
                    .order_by(AgentResearcherMemory.created_at.desc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                return list(result.scalars().all())

        except SQLAlchemyError as exc:
            logger.exception("Ошибка при получении памяти агента")

            raise DatabaseError("Не удалось получить записи из памяти агента") from exc


    async def add_telegram_post(
        self,
        tmdb_id: int,
        title: str,
        post_text: str,
        created_at: datetime | None = None,
    )-> TelegramPost:
        """
        Добавить пост телеграм.
        """
        if not tmdb_id:
            raise ValueError("tmdb_id не может быть пустым")

        # Передаем "нативную" (naive) дату без timezone, как требовалось для SQLite
        if created_at is None:
            created_at = datetime.now()
        elif created_at.tzinfo is not None:
            created_at = created_at.replace(tzinfo=None)

        try:
            async with self.session_factory() as session:
                memory = TelegramPost(
                    tmdb_id=tmdb_id,
                    title=title,
                    post_text=post_text,
                    created_at=created_at,
                )

                session.add(memory)

                await session.commit()
                await session.refresh(memory)

                return memory

        except SQLAlchemyError as exc:
            logger.exception("Ошибка при добавлении поста телеграм")

            raise DatabaseError("Не удалось добавить запиь в таблицу пост телеграм") from exc
