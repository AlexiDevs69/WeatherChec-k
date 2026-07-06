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


async def get_bot_settings() -> dict:
    """
    Reads the single bot_settings row maintained by the admin dashboard's
    /settings page (id=1: welcome_message, maintenance_mode, maintenance_message).

    Returns safe defaults instead of raising if:
      - the table doesn't exist yet (dashboard hasn't been deployed/started
        at least once), or
      - the row doesn't exist yet (nobody opened /settings in the dashboard
        yet, so the dashboard never inserted the default row).
    This means the bot NEVER crashes because of the dashboard being out of
    sync — worst case it just behaves as if maintenance mode is off and
    the welcome message is unset.
    """
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT welcome_message, maintenance_mode, maintenance_message
                FROM bot_settings
                WHERE id = 1
                """
            )
    except asyncpg.exceptions.UndefinedTableError:
        row = None

    if row is None:
        return {
            "welcome_message": None,
            "maintenance_mode": False,
            "maintenance_message": None,
        }

    return dict(row)
