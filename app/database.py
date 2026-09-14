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

            # ============================================================
# CHECKOUT HELPERS
# ============================================================
import uuid
from datetime import datetime, timedelta


async def create_paid_user_and_session(
    name: str,
    email: str,
    phone: str,
    plan: str,
    sprint: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    amount: int,
    duration_days: int,
):
    """
    Creates or updates a user, then creates:
      - user_sessions row (plan + sprint + dates)
      - payments row
      - transactions row
      - session_tokens row (drill_id = NULL → marks it as a paid session)
    Returns { user_id, session_token }
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        async with conn.transaction():
            # ─── 1. Find or create user ───
            user_row = await conn.fetchrow(
                "SELECT user_id FROM users WHERE email = $1",
                email,
            )

            if user_row:
                user_id = user_row["user_id"]
                # Update name/phone if they were empty
                await conn.execute(
                    """
                    UPDATE users
                    SET full_name = COALESCE(NULLIF(full_name, ''), $1),
                        phone = COALESCE(NULLIF(phone, ''), $2),
                        updated_at = NOW()
                    WHERE user_id = $3
                    """,
                    name, phone, user_id,
                )
            else:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (user_id, full_name, email, phone, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, NOW(), NOW())
                    RETURNING user_id
                    """,
                    uuid.uuid4(), name, email, phone,
                )

            # ─── 2. Compute sprint dates ───
            sprint_start = datetime.utcnow().date()
            sprint_end = sprint_start + timedelta(days=duration_days)

            # ─── 3. Create user_sessions row ───
            await conn.execute(
                """
                INSERT INTO user_sessions (
                    session_id, email, phone, name, plan,
                    track_id, current_day, total_days,
                    questions_per_day, trials_per_question,
                    sprint_start_date, sprint_end_date,
                    current_streak, total_reps,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, 1, $7,
                    2, 2,
                    $8, $9,
                    0, 0,
                    NOW(), NOW()
                )
                """,
                uuid.uuid4(), email, phone, name, plan,
                sprint, duration_days,
                sprint_start, sprint_end,
            )

            # ─── 4. Create payments row ───
            await conn.execute(
                """
                INSERT INTO payments (
                    payment_id, email, gateway, product_type,
                    track_id, amount_inr, currency, status,
                    gateway_order_id, gateway_signature,
                    metadata, created_at, paid_at
                )
                VALUES (
                    $1, $2, 'razorpay', $3,
                    $4, $5, 'INR', 'captured',
                    $6, $7,
                    $8, NOW(), NOW()
                )
                """,
                razorpay_payment_id, email, plan,
                sprint, amount / 100,  # convert paise → INR
                razorpay_order_id, razorpay_signature,
                json.dumps({"plan": plan, "sprint": sprint, "phone": phone}),
            )

            # ─── 5. Create transactions row ───
            await conn.execute(
                """
                INSERT INTO transactions (
                    transaction_id, user_id, razorpay_payment_id,
                    razorpay_order_id, razorpay_signature,
                    amount, currency, status, type, product_name,
                    metadata, created_at, completed_at, updated_at
                )
                VALUES (
                    $1, $2, $3,
                    $4, $5,
                    $6, 'INR', 'success', 'payment', $7,
                    $8, NOW(), NOW(), NOW()
                )
                """,
                uuid.uuid4(), user_id, razorpay_payment_id,
                razorpay_order_id, razorpay_signature,
                amount, plan,
                json.dumps({"sprint": sprint, "plan": plan, "email": email}),
            )

            # ─── 6. Create session token ───
            session_token = str(uuid.uuid4())
            token_expiry = datetime.utcnow() + timedelta(days=30)

            await conn.execute(
                """
                INSERT INTO session_tokens (
                    jti, email, drill_id, used_at, expires_at, created_at
                )
                VALUES ($1, $2, NULL, NULL, $3, NOW())
                """,
                session_token, email, token_expiry,
            )

            return {
                "user_id": str(user_id),
                "session_token": session_token,
            }

    finally:
        await conn.close()


async def get_user_by_session_token(token: str):
    """
    Returns user + plan info if the token is a valid paid session.
    Returns None if token is invalid or expired.
    Returns { is_paid: False } if it's a drill session.
    """
    conn = await asyncpg.connect(Config.DATABASE_URL)
    try:
        # 1. Look up session token
        token_row = await conn.fetchrow(
            """
            SELECT jti, email, drill_id, expires_at, used_at
            FROM session_tokens
            WHERE jti = $1
            """,
            token,
        )

        if not token_row:
            return None

        if token_row["expires_at"] < datetime.utcnow():
            return None

        # 2. Drill session → not paid
        if token_row["drill_id"] is not None:
            return {"is_paid": False}

        # 3. Paid session → fetch user + user_session
        email = token_row["email"]

        user_row = await conn.fetchrow(
            """
            SELECT user_id, full_name, email, phone
            FROM users
            WHERE email = $1
            """,
            email,
        )

        if not user_row:
            return None

        session_row = await conn.fetchrow(
            """
            SELECT plan, track_id, current_day, total_days,
                   sprint_start_date, sprint_end_date
            FROM user_sessions
            WHERE email = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            email,
        )

        if not session_row:
            return None

        return {
            "is_paid": True,
            "user_id": str(user_row["user_id"]),
            "name": user_row["full_name"],
            "email": user_row["email"],
            "phone": user_row["phone"],
            "plan": session_row["plan"],
            "sprint": session_row["track_id"],
            "sprint_start_date": session_row["sprint_start_date"],
            "sprint_end_date": session_row["sprint_end_date"],
            "current_day": session_row["current_day"],
            "total_days": session_row["total_days"],
        }

    finally:
        await conn.close()
            "subscription": dict(subscription) if subscription else None,
        }
    finally:
        await conn.close()
