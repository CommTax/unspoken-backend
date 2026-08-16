import asyncpg
from app.config import Config

async def get_db():
    """
    Get a single database connection.
    Use this for simple queries where you don't need a connection pool.
    """
    return await asyncpg.connect(Config.DATABASE_URL)

async def get_db_pool():
    """
    Get a database connection pool.
    Use this for production to manage multiple concurrent connections.
    """
    return await asyncpg.create_pool(
        Config.DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=60
    )

async def close_db_pool(pool):
    """
    Close the database connection pool.
    """
    if pool:
        await pool.close()
