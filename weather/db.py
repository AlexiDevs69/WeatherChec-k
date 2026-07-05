import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Lazily creates a single shared connection pool."""
    global _pool
    if _pool is None:
        # asyncpg wants "postgresql://", Render gives "postgres://" — normalize it.
        dsn = DATABASE_URL
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    return _pool


async def upsert_user(user_id: int, username: str | None) -> None:
    """Insert a new user, or update their username if they already exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, username, created_at)
            VALUES ($1, $2, now())
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
            """,
            user_id, username,
        )


async def log_action(user_id: int, username: str | None, action: str) -> None:
    """Insert one row into the logs table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO logs (user_id, username, action, timestamp)
            VALUES ($1, $2, $3, now())
            """,
            user_id, username, action,
        )
