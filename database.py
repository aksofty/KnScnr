from __future__ import annotations
import json
import math
import logging
from datetime import date, datetime, timezone
from typing import Any, Sequence

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, select, and_, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, aliased
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# ============================================================
# Exceptions
# ============================================================

class DatabaseError(Exception):
    """Базовая ошибка БД."""


class FilmDatabaseError(DatabaseError):
    """Ошибка при работе с фильмом."""


class SnapshotDatabaseError(DatabaseError):
    """Ошибка при работе со snapshot."""


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


class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    overview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    release_date: Mapped[str | None] = mapped_column(String, nullable=True)


    rating: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    vote_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    popularity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="film",
        cascade="all, delete-orphan",
    )


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    rating: Mapped[float] = mapped_column(Float, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False)
    popularity: Mapped[float] = mapped_column(Float, nullable=False)

    film: Mapped["Film"] = relationship(
        back_populates="snapshots",
    )

    __table_args__ = (
        UniqueConstraint(
            "film_id",
            "captured_at",
            name="uq_snapshot_film_date",
        ),
    )

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    signal: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    film: Mapped["Film"] = relationship()

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

    # ========================================================
    # Films
    # ========================================================

    async def upsert_film(
        self,
        tmdb_id: int,
        title: str,
        overview: str,
        rating: float,
        vote_count: int,
        popularity: float,
        release_date: str | None = None
    ) -> Film:
        try:
            async with self.session_factory() as session:

                film = await session.scalar(
                    select(Film)
                    .where(Film.tmdb_id == tmdb_id)
                )

                if film is None:
                    film = Film(
                        tmdb_id=tmdb_id,
                        title=title,
                        overview=overview,
                        rating=rating,
                        vote_count=vote_count,
                        popularity=popularity,
                        release_date=release_date,
                    )

                    session.add(film)

                else:
                    film.title = title
                    film.release_date = release_date
                    film.rating=rating
                    film.vote_count=vote_count
                    film.popularity=popularity

                await session.commit()

                # После commit гарантированно получаем ID.
                await session.refresh(film)

                return film

        except IntegrityError as exc:
            logger.exception(
                "Ошибка целостности при сохранении фильма "
                "tmdb_id=%s",
                tmdb_id,
            )

            raise FilmDatabaseError(
                f"Не удалось сохранить фильм tmdb_id={tmdb_id}"
            ) from exc

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка БД при сохранении фильма "
                "tmdb_id=%s",
                tmdb_id,
            )

            raise FilmDatabaseError(
                f"Ошибка БД при сохранении фильма tmdb_id={tmdb_id}"
            ) from exc

    async def get_film_by_tmdb_id(
        self,
        tmdb_id: int,
    ) -> Film | None:

        try:
            async with self.session_factory() as session:
                return await session.scalar(
                    select(Film)
                    .where(Film.tmdb_id == tmdb_id)
                )

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка получения фильма tmdb_id=%s",
                tmdb_id,
            )

            raise FilmDatabaseError(
                f"Не удалось получить фильм tmdb_id={tmdb_id}"
            ) from exc

    # ========================================================
    # Snapshots
    # ========================================================

    async def add_snapshot(
        self,
        film_id: int,
        rating: float,
        vote_count: int,
        popularity: float,
        captured_at: datetime | None = None,
    ) -> Snapshot:

        if captured_at is None:
            captured_at = datetime.now(timezone.utc)


        captured_at = captured_at.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        try:
            async with self.session_factory() as session:
                snapshot = await session.scalar(
                    select(Snapshot)
                    .where(
                        Snapshot.film_id == film_id,
                        Snapshot.captured_at == captured_at,
                    )
                )

                if snapshot is None:

                    snapshot = Snapshot(
                        film_id=film_id,
                        captured_at=captured_at,
                        rating=rating,
                        vote_count=vote_count,
                        popularity=popularity,
                    )

                    session.add(snapshot)

                else:
                    snapshot.rating = rating
                    snapshot.vote_count = vote_count
                    snapshot.popularity = popularity

                await session.commit()
                await session.refresh(snapshot)

                return snapshot

        except IntegrityError as exc:
            logger.exception(
                "Ошибка целостности snapshot "
                "film_id=%s",
                film_id,
            )

            raise SnapshotDatabaseError(
                f"Не удалось сохранить snapshot film_id={film_id}"
            ) from exc

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка БД при сохранении snapshot "
                "film_id=%s",
                film_id,
            )

            raise SnapshotDatabaseError(
                f"Ошибка БД при сохранении snapshot film_id={film_id}"
            ) from exc

    async def get_previous_snapshot(
        self,
        film_id: int,
        before: datetime | None = None,
    ) -> Snapshot | None:

        if before is None:
            before = datetime.now(timezone.utc)

        try:
            async with self.session_factory() as session:

                query = (
                    select(Snapshot)
                    .where(
                        Snapshot.film_id == film_id,
                        Snapshot.captured_at < before,
                    )
                    .order_by(
                        Snapshot.captured_at.desc()
                    )
                    .limit(1)
                )

                return await session.scalar(query)

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка получения предыдущего snapshot "
                "film_id=%s",
                film_id,
            )

            raise SnapshotDatabaseError(
                f"Не удалось получить snapshot film_id={film_id}"
            ) from exc

    async def get_snapshots(
        self,
        film_id: int,
        limit: int = 30,
    ) -> Sequence[Snapshot]:

        if limit <= 0:
            raise ValueError("limit должен быть больше 0")

        try:
            async with self.session_factory() as session:

                result = await session.scalars(
                    select(Snapshot)
                    .where(Snapshot.film_id == film_id)
                    .order_by(
                        Snapshot.captured_at.desc()
                    )
                    .limit(limit)
                )

                return result.all()

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка получения snapshots "
                "film_id=%s",
                film_id,
            )

            raise SnapshotDatabaseError(
                f"Не удалось получить snapshots film_id={film_id}"
            ) from exc


    async def get_post_candidates(
        self,
        limit: int = 20,
        min_vote_growth: int = 10,
        min_rating_growth: float = 0.2,
        cooldown_days: int = 30,
    ) -> list[dict]:
        """
        Получить несколько кандидатов для последующего выбора нейросетью.

        Возвращает список словарей:

        {
            "film": Film,
            "latest": Snapshot,
            "previous": Snapshot,
            "popularity_growth": float,
            "vote_growth": int,
            "rating_growth": float,
            "score": float,
        }
        """

        if limit <= 0:
            raise ValueError("limit должен быть больше 0")

        if cooldown_days < 0:
            raise ValueError("cooldown_days не может быть отрицательным")

        now = datetime.now(timezone.utc)
        cooldown_date = now - timedelta(days=cooldown_days)

        try:
            async with self.session_factory() as session:

                # ---------------------------------------------------------
                # Последний snapshot каждого фильма
                # ---------------------------------------------------------

                latest_subquery = (
                    select(
                        Snapshot.film_id.label("film_id"),
                        func.max(
                            Snapshot.captured_at
                        ).label("captured_at"),
                    )
                    .group_by(Snapshot.film_id)
                    .subquery()
                )

                latest = aliased(Snapshot)
                previous = aliased(Snapshot)

                # ---------------------------------------------------------
                # Последний post каждого фильма
                # ---------------------------------------------------------

                last_post_subquery = (
                    select(
                        Post.film_id.label("film_id"),
                        func.max(
                            Post.published_at
                        ).label("published_at"),
                    )
                    .group_by(Post.film_id)
                    .subquery()
                )

                # ---------------------------------------------------------
                # Запрос
                # ---------------------------------------------------------

                query = (
                    select(
                        Film,
                        latest,
                        previous,
                        last_post_subquery.c.published_at.label(
                            "last_published_at"
                        ),
                    )

                    # Последний snapshot
                    .join(
                        latest_subquery,
                        latest_subquery.c.film_id == Film.id,
                    )
                    .join(
                        latest,
                        and_(
                            latest.film_id == Film.id,
                            latest.captured_at
                            == latest_subquery.c.captured_at,
                        ),
                    )

                    # Предыдущий snapshot
                    .join(
                        previous,
                        and_(
                            previous.film_id == Film.id,
                            previous.captured_at
                            < latest.captured_at,
                        ),
                    )

                    # Берём только самый свежий previous snapshot
                    .where(
                        previous.captured_at
                        == select(
                            func.max(Snapshot.captured_at)
                        )
                        .where(
                            Snapshot.film_id == Film.id,
                            Snapshot.captured_at
                            < latest.captured_at,
                        )
                        .correlate(Film)
                        .scalar_subquery()
                    )

                    # Последний post — LEFT JOIN,
                    # потому что фильм может никогда не публиковаться
                    .outerjoin(
                        last_post_subquery,
                        last_post_subquery.c.film_id == Film.id,
                    )

                    # Cooldown
                    .where(
                        or_(
                            last_post_subquery.c.published_at.is_(None),
                            last_post_subquery.c.published_at
                            <= cooldown_date,
                        )
                    )

                    .limit(limit * 5)
                )

                result = await session.execute(query)

                rows = result.all()

                candidates = []

                # ---------------------------------------------------------
                # Score рассчитываем уже в Python.
                # SQL при этом сделал только необходимую выборку.
                # ---------------------------------------------------------

                for row in rows:

                    film = row[0]
                    latest_snapshot = row[1]
                    previous_snapshot = row[2]

                    popularity_growth = (
                        latest_snapshot.popularity
                        - previous_snapshot.popularity
                    )

                    vote_growth = (
                        latest_snapshot.vote_count
                        - previous_snapshot.vote_count
                    )

                    rating_growth = (
                        latest_snapshot.rating
                        - previous_snapshot.rating
                    )

                    # Пока простая формула.
                    # Позже вынесем её в отдельный scorer.
                    score = (
                        popularity_growth
                        + vote_growth * 0.01
                        + rating_growth * 10
                    )

                    # Если никакого положительного сигнала нет —
                    # нейросети такой фильм не нужен.
                    #if score <= 0 or vote_growth <= min_vote_growth:
                    if vote_growth <= min_vote_growth or rating_growth <= min_rating_growth:
                        continue

                    candidates.append(
                        {
                            "film": film,
                            "latest": latest_snapshot,
                            "previous": previous_snapshot,
                            "popularity_growth": popularity_growth,
                            "vote_growth": vote_growth,
                            "rating_growth": rating_growth,
                            "score": score,
                        }
                    )

                # ---------------------------------------------------------
                # Сортируем по силе сигнала
                # ---------------------------------------------------------

                candidates.sort(
                    key=lambda item: item["score"],
                    reverse=True,
                )

                return candidates[:limit]

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка при получении кандидатов для публикации"
            )

            raise DatabaseError(
                "Не удалось получить кандидатов для публикации"
            ) from exc



    async def get_discovery_candidates(
        self,
        limit: int = 20,
        cooldown_days: int = 10,
        rating: float = 7.0,
        vote_count_min: int = 200,
        vote_count_max: int = 10000,
    ) -> list[Film]:
        """
        Получить случайную выборку фильмов для Discovery.

        Фильтры:
        - рейтинг >= 7.0
        - количество оценок от 200 до 10000
        - фильм не публиковался последние cooldown_days дней
        - выборка случайная

        films содержит актуальные значения rating/vote_count.
        snapshots для Discovery не используются.
        """

        if limit <= 0:
            raise ValueError("limit должен быть больше 0")

        if cooldown_days < 0:
            raise ValueError(
                "cooldown_days не может быть отрицательным"
            )

        cooldown_date = (
            datetime.now(timezone.utc)
            - timedelta(days=cooldown_days)
        )

        try:
            async with self.session_factory() as session:

                # ---------------------------------------------------------
                # Последняя публикация каждого фильма
                # ---------------------------------------------------------

                last_post_subquery = (
                    select(
                        Post.film_id.label("film_id"),
                        func.max(
                            Post.published_at
                        ).label("published_at"),
                    )
                    .group_by(Post.film_id)
                    .subquery()
                )

                # ---------------------------------------------------------
                # 1. Выбираем случайные film_id
                # ---------------------------------------------------------

                film_ids_query = (
                    select(Film.id)
                    .outerjoin(
                        last_post_subquery,
                        last_post_subquery.c.film_id == Film.id,
                    )
                    .where(
                        # Базовые параметры фильма
                        Film.rating >= rating,
                        Film.vote_count >= vote_count_min,
                        Film.vote_count <= vote_count_max,

                        # Cooldown
                        or_(
                            last_post_subquery.c.published_at.is_(None),
                            last_post_subquery.c.published_at
                            <= cooldown_date,
                        ),
                    )
                    .order_by(func.random())
                    .limit(limit)
                )

                result = await session.scalars(film_ids_query)

                film_ids = list(result.all())

                if not film_ids:
                    return []

                # ---------------------------------------------------------
                # 2. Получаем данные фильмов
                # ---------------------------------------------------------

                films_query = (
                    select(Film)
                    .where(Film.id.in_(film_ids))
                )

                result = await session.scalars(films_query)

                films = list(result.all())

                return films

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка при получении discovery-кандидатов"
            )

            raise DatabaseError(
                "Не удалось получить discovery-кандидатов"
            ) from exc

    async def add_post(
        self,
        film_id: int,
        signal: str,
        text: str,
        published_at: datetime | None = None,
    ) -> Post:
        """
        Добавить опубликованный пост.

        :param film_id: ID фильма в БД.
        :param signal: Сигнал, по которому был выбран фильм.
        :param published_at: Время публикации.
            Если не передано — используется текущее UTC-время.
        """

        if film_id <= 0:
            raise ValueError("film_id должен быть больше 0")

        if not signal.strip():
            raise ValueError("signal не может быть пустым")

        if published_at is None:
            published_at = datetime.now(timezone.utc)

        try:
            async with self.session_factory() as session:
                post = Post(
                    film_id=film_id,
                    published_at=published_at,
                    signal=signal,
                    text=text,
                )

                session.add(post)

                await session.commit()
                await session.refresh(post)

                return post

        except SQLAlchemyError as exc:
            logger.exception(
                "Ошибка при добавлении поста: film_id=%s",
                film_id,
            )

            raise DatabaseError(
                "Не удалось добавить пост"
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
        created_at: datetime | None = None,
    )-> AgentResearcherMemory:
        """
        Добавить запись в память агента.

        :param data: Данные памяти в виде словаря (сохраняются как JSON).
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
