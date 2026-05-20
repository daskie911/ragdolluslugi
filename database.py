"""
Работа с SQLite через aiosqlite.
Хранит: пользователей (с балансом), активные услуги, историю покупок.
"""
import os
import time
import aiosqlite

DB_PATH = os.getenv("DATABASE_PATH", "bot.db")


async def init_db() -> None:
    """Создать таблицы, если ещё не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        # ── Пользователи ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                balance    INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)
        # ── Маппинг username → user_id (кэш) ────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS username_cache (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                user_id  INTEGER NOT NULL
            )
        """)
        # ── Активные услуги ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_services (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                service    TEXT    NOT NULL,
                chat_id    INTEGER NOT NULL,
                target_id  INTEGER,
                buyer_id   INTEGER NOT NULL,
                payload    TEXT,
                expires_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        # ── История покупок ──────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchase_history (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id            INTEGER NOT NULL,
                service             TEXT    NOT NULL,
                duration_key        TEXT,
                price_stars         INTEGER NOT NULL,
                target_id           INTEGER,
                payload             TEXT,
                telegram_charge     TEXT,
                created_at          INTEGER NOT NULL
            )
        """)
        await db.commit()


# ═══════════════════════════════════════════════════════════════
# Пользователи
# ═══════════════════════════════════════════════════════════════

async def ensure_user(user_id: int, username: str | None = None,
                      first_name: str | None = None) -> None:
    """Создать пользователя если нет. Обновить username/first_name. Обновить кэш."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (user_id, username, first_name, balance, created_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   username   = COALESCE(excluded.username, users.username),
                   first_name = COALESCE(excluded.first_name, users.first_name)
            """,
            (user_id, username, first_name, now),
        )
        if username:
            await db.execute(
                """INSERT INTO username_cache (username, user_id)
                   VALUES (?, ?)
                   ON CONFLICT(username) DO UPDATE SET user_id = excluded.user_id
                """,
                (username.lower(), user_id),
            )
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY balance DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_user_balance(user_id: int) -> int:
    user = await get_user(user_id)
    return user["balance"] if user else 0


async def add_balance(user_id: int, amount: int) -> int:
    """Добавить (или вычесть) звёзды. Возвращает новый баланс."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()
    return await get_user_balance(user_id)


async def set_balance(user_id: int, amount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()


async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_total_stars() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COALESCE(SUM(balance), 0) FROM users")
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_total_revenue() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(price_stars), 0) FROM purchase_history"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# ═══════════════════════════════════════════════════════════════
# Кэш username → user_id
# ═══════════════════════════════════════════════════════════════

async def get_user_id_by_username(username: str) -> int | None:
    """Найти user_id по username из кэша."""
    clean = username.strip().lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM username_cache WHERE username = ?", (clean,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


# ═══════════════════════════════════════════════════════════════
# Активные услуги
# ═══════════════════════════════════════════════════════════════

async def add_active_service(
    service: str, chat_id: int, target_id: int | None,
    buyer_id: int, payload: str | None, expires_at: int,
) -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO active_services
               (service, chat_id, target_id, buyer_id, payload, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (service, chat_id, target_id, buyer_id, payload, expires_at, now),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]


async def get_expired_services() -> list[dict]:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM active_services
               WHERE active = 1 AND expires_at > 0 AND expires_at <= ?""",
            (now,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def deactivate_service(service_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE active_services SET active = 0 WHERE id = ?", (service_id,)
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════
# История покупок
# ═══════════════════════════════════════════════════════════════

async def add_purchase(
    buyer_id: int, service: str, duration_key: str | None,
    price_stars: int, target_id: int | None,
    payload: str | None, telegram_charge: str | None,
) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO purchase_history
               (buyer_id, service, duration_key, price_stars, target_id,
                payload, telegram_charge, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (buyer_id, service, duration_key, price_stars,
             target_id, payload, telegram_charge, now),
        )
        await db.commit()


async def get_user_purchases(buyer_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM purchase_history
               WHERE buyer_id = ? ORDER BY created_at DESC LIMIT ?""",
            (buyer_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_purchases_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM purchase_history")
        row = await cursor.fetchone()
        return row[0] if row else 0
