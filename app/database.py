# app/database.py

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


# ============================================================
# CHECKOUT — User + Subscription helpers
# ============================================================

async def save_user_and_subscription(
    name: str,
    email: str,
    phone: str,
    plan: str,
    sprint: str,
    payment_id: str,
    order_id: str,
    amount: int,
) -> int:
    """
    Create or find a user by email, then create a subscription row.
    Returns the user_id (int).
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        async with conn.transaction():
            # 1. Find or create user
            user_row = await conn.fetchrow(
                "SELECT id FROM users WHERE email = $1",
                email,
            )

            if user_row:
                user_id = user_row["id"]
                # Update name/phone if they were empty
                await conn.execute(
                    """
                    UPDATE users
                    SET name = COALESCE(NULLIF(name, ''), $1),
                        phone = COALESCE(NULLIF(phone, ''), $2)
                    WHERE id = $3
                    """,
                    name, phone, user_id,
                )
            else:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (name, email, phone, created_at)
                    VALUES ($1, $2, $3, NOW())
                    RETURNING id
                    """,
                    name, email, phone,
                )

            # 2. Compute end date based on plan
            if plan == "sprint":
                duration_days = 28
            else:  # "pass"
                duration_days = 365

            # 3. Insert subscription
            await conn.execute(
                """
                INSERT INTO subscriptions (
                    user_id, plan, sprint, payment_id, order_id,
                    amount, status, start_date, end_date
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, 'active', NOW(), NOW() + ($7 || ' days')::interval
                )
                """,
                user_id, plan, sprint, payment_id, order_id,
                amount, str(duration_days),
            )

            return user_id

    finally:
        await conn.close()


async def get_user_by_id(user_id: int):
    """
    Fetch a user + their latest subscription. Used by the product page
    to verify a session token and load the right dashboard.
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        user = await conn.fetchrow(
            "SELECT id, name, email, phone, created_at FROM users WHERE id = $1",
            user_id,
        )
        if not user:
            return None

        subscription = await conn.fetchrow(
            """
            SELECT id, plan, sprint, status, start_date, end_date
            FROM subscriptions
            WHERE user_id = $1 AND status = 'active'
            ORDER BY start_date DESC
            LIMIT 1
            """,
            user_id,
        )

        return {
            "user": dict(user),
            "subscription": dict(subscription) if subscription else None,
        }
    finally:
        await conn.close()
