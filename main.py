import asyncio
import logging
import hmac
import hashlib
import json
import math
import random
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
import aiosqlite
from aiohttp import web as aio_web
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    MenuButtonWebApp,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

# ===================== КОНФИГ =====================
BOT_TOKEN = "8672400944:AAHNBgcNkkcOi2q-dXgqH34EDRHWxAacQ5k"
SUPERADMIN_IDS: set[int] = {8513748992}   # нельзя удалить через команды
ADMIN_IDS: set[int] = set(SUPERADMIN_IDS) # дополняется из БД при запуске
DB_PATH = "bot.db"
PROXY = ""
WEB_PORT = int(__import__('os').environ.get('PORT', 8080))
# Вставь сюда свой домен с BotHost (из раздела "Web" в панели хостинга)
WEB_URL = "https://lutobot.bothost.tech"
WEBAPP_DIR = Path(__file__).parent / "webapp"
# ==================================================

SHOP_TAX = 0.15   # 15% налог при продаже

# ─── КЕЙСЫ ────────────────────────────────────────────────────────────────────
CASE_PRICES: dict[str, int] = {
    'cars':       150_000,
    'apartments': 900_000,
    'houses':   1_700_000,
    'tech':         5_000,
    'phones':      15_000,
    'jewelry':     25_000,
    'balance':    100_000,
    'daily':            0,
}

# (reward_type, value_or_None, weight)
CASE_LOOT: dict[str, list] = {
    'cars': [
        ('nothing', None, 70),
        ('item', 'ВАЗ 2107', 200),
        ('item', 'Lada Vesta', 100),
        ('item', 'Toyota Camry', 50),
        ('item', 'BMW 5 Series', 20),
        ('item', 'Mercedes S-Class', 8),
        ('item', 'Porsche 911', 3),
        ('item', 'Lamborghini Huracán', 1),
        ('item', 'Bugatti Chiron', 1),
    ],
    'apartments': [
        ('nothing', None, 100),
        ('item', 'Комната в общежитии', 350),
        ('item', 'Студия', 150),
        ('item', '1-комнатная', 60),
        ('item', '2-комнатная', 25),
        ('item', '3-комнатная', 10),
        ('item', 'Пентхаус', 5),
    ],
    'houses': [
        ('nothing', None, 100),
        ('item', 'Дача', 350),
        ('item', 'Загородный дом', 150),
        ('item', 'Коттедж', 70),
        ('item', 'Особняк', 25),
        ('item', 'Вилла на Рублёвке', 5),
    ],
    'phones': [
        ('nothing', None, 150),
        ('item', 'Xiaomi Redmi 13C', 200),
        ('item', 'Samsung Galaxy A15', 150),
        ('item', 'Xiaomi Redmi Note 14', 130),
        ('item', 'Vivo Y28', 100),
        ('item', 'Samsung Galaxy A55', 70),
        ('item', 'Vivo V40', 60),
        ('item', 'Samsung Galaxy S24', 40),
        ('item', 'Vivo X200', 25),
        ('item', 'iPhone 15', 20),
        ('item', 'iPhone 16', 15),
        ('item', 'Xiaomi 15', 12),
        ('item', 'iPhone 15 Pro', 10),
        ('item', 'Samsung Galaxy S25', 8),
        ('item', 'Samsung Galaxy S24 Ultra', 6),
        ('item', 'iPhone 16 Pro', 5),
        ('item', 'Samsung Galaxy S25 Ultra', 4),
        ('item', 'iPhone 15 Pro Max', 3),
        ('item', 'iPhone 16 Pro Max', 2),
    ],
    'jewelry': [
        ('nothing', None, 100),
        ('item', 'Серебряная цепочка', 300),
        ('item', 'Золотое кольцо', 150),
        ('item', 'Часы Seiko Presage', 50),
        ('item', 'Золотая цепочка', 60),
        ('item', 'Серьги с бриллиантом', 20),
        ('item', 'Часы Rolex Submariner', 10),
        ('item', 'Бриллиантовое колье', 8),
        ('item', 'Часы Patek Philippe', 2),
    ],
    'balance': [
        ('nothing', None, 100),
        ('balance', 15_000, 300),
        ('balance', 50_000, 150),
        ('balance', 100_000, 80),
        ('balance', 200_000, 40),
        ('balance', 500_000, 20),
        ('balance', 1_000_000, 8),
        ('balance', 5_000_000, 2),
    ],
    'tech': [
        ('nothing', None, 400),
        ('item', 'Мышь Logitech G102', 250),
        ('item', 'Клавиатура HyperX', 150),
        ('item', 'ОЗУ 32GB DDR5', 70),
        ('item', 'SSD Samsung 2TB', 50),
        ('item', 'Монитор 27" QHD', 40),
        ('item', 'Наушники Sony XM5', 20),
        ('item', 'Игровой ПК (средний)', 10),
        ('item', 'RTX 4070 Ti', 7),
        ('item', 'Ноутбук Lenovo Legion', 2),
        ('item', 'MacBook Pro M3 Max', 1),
        ('item', 'Игровой ПК (топ)', 1),
        ('item', 'RTX 4090', 1),
    ],
    'daily': [
        ('nothing', None, 120),
        ('key', 'tech', 250),
        ('key', 'cars', 170),
        ('key', 'phones', 100),
        ('key', 'jewelry', 60),
        ('key', 'apartments', 60),
        ('key', 'houses', 30),
    ],
}

VALID_SETTINGS = {
    "short_numbers", "notify_transfers", "hide_from_top",
    "confirm_pay", "show_join_date", "quiet_mode",
}

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

session = AiohttpSession(proxy=PROXY) if PROXY else AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
router = Router()


class PromoState(StatesGroup):
    waiting = State()


class ReportState(StatesGroup):
    waiting = State()


# ===================== БАЗА ДАННЫХ =====================

async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY,
                username         TEXT,
                balance          REAL    DEFAULT 0,
                games_played     INTEGER DEFAULT 0,
                uid              INTEGER UNIQUE,
                short_numbers    INTEGER DEFAULT 0,
                notify_transfers INTEGER DEFAULT 1,
                hide_from_top    INTEGER DEFAULT 0,
                confirm_pay      INTEGER DEFAULT 0,
                show_join_date   INTEGER DEFAULT 1,
                quiet_mode       INTEGER DEFAULT 0,
                banned           INTEGER DEFAULT 0,
                registered_at    TEXT
            )
        """)
        for col, typ, default in [
            ("short_numbers",    "INTEGER", "0"),
            ("notify_transfers", "INTEGER", "1"),
            ("hide_from_top",    "INTEGER", "0"),
            ("confirm_pay",      "INTEGER", "0"),
            ("show_join_date",   "INTEGER", "1"),
            ("quiet_mode",       "INTEGER", "0"),
            ("banned",           "INTEGER", "0"),
            ("is_admin",         "INTEGER", "0"),
            ("registered_at",    "TEXT",    "NULL"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT {default}"
                )
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code       TEXT PRIMARY KEY,
                reward     REAL    NOT NULL,
                max_uses   INTEGER NOT NULL,
                uses_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS used_promos (
                user_id INTEGER NOT NULL,
                code    TEXT    NOT NULL,
                PRIMARY KEY (user_id, code)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                reason     TEXT,
                created_at TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT    NOT NULL,
                from_id    INTEGER,
                to_id      INTEGER,
                amount     REAL    NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                username   TEXT,
                reason     TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT 'open',
                created_at TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                won        INTEGER NOT NULL,
                bet        REAL    NOT NULL,
                profit     REAL    NOT NULL,
                mult       REAL    NOT NULL,
                created_at TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                type       TEXT    NOT NULL,
                amount     REAL    NOT NULL,
                from_name  TEXT,
                created_at TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                category     TEXT    NOT NULL,
                name         TEXT    NOT NULL,
                description  TEXT,
                price        REAL    NOT NULL,
                icon         TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                item_id    INTEGER NOT NULL,
                price_paid REAL    NOT NULL,
                bought_at  TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rentals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                inv_id         INTEGER NOT NULL UNIQUE,
                item_id        INTEGER NOT NULL,
                rate           REAL    NOT NULL,
                started_at     TEXT    NOT NULL,
                last_collected TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS case_keys (
                user_id   INTEGER NOT NULL,
                case_type TEXT    NOT NULL,
                amount    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, case_type)
            )
        """)
        # Добавляем rent_rate в shop_items если ещё нет
        try:
            await db.execute("ALTER TABLE shop_items ADD COLUMN rent_rate REAL DEFAULT 0")
        except Exception:
            pass
        # Добавляем image_url в shop_items если ещё нет
        try:
            await db.execute("ALTER TABLE shop_items ADD COLUMN image_url TEXT DEFAULT NULL")
        except Exception:
            pass
        # Проставляем пути к картинкам для машин
        _car_images = {
            "ВАЗ 2107":             "/images/ВАЗ_2107.jpg",
            "Lada Vesta":           "/images/Lada Vesta.jpg",
            "Toyota Camry":         "/images/Toyota_Camry.jpg",
            "BMW 5 Series":         "/images/BMW_5_Series.jpg",
            "Mercedes S-Class":     "/images/Mersedes_S-Class.jpg",
            "Porsche 911":          "/images/Porsche_911.jpg",
            "Lamborghini Huracán":  "/images/Lamborghini_Huracan.jpg",
            "Bugatti Chiron":       "/images/Bugatti_Chiron.jpg",
        }
        for name, url in _car_images.items():
            await db.execute("UPDATE shop_items SET image_url=? WHERE name=?", (url, name))
        # Добавляем daily_case_at в users если ещё нет
        try:
            await db.execute("ALTER TABLE users ADD COLUMN daily_case_at TEXT DEFAULT NULL")
        except Exception:
            pass
        # Заполняем магазин если пуст
        async with db.execute("SELECT COUNT(*) FROM shop_items") as cur:
            if (await cur.fetchone())[0] == 0:
                shop_seed = [
                    # (category, name, description, price, icon)
                    ("cars","ВАЗ 2107","Классика отечественного автопрома",120_000,"🚗"),
                    ("cars","Lada Vesta","Современный российский седан",850_000,"🚙"),
                    ("cars","Toyota Camry","Надёжный японский бизнес-класс",2_400_000,"🚘"),
                    ("cars","BMW 5 Series","Немецкое качество и динамика",6_500_000,"🏎"),
                    ("cars","Mercedes S-Class","Флагман немецкого комфорта",14_000_000,"🚐"),
                    ("cars","Porsche 911","Легенда мирового автоспорта",22_000_000,"🏁"),
                    ("cars","Lamborghini Huracán","Итальянский суперкар",35_000_000,"⚡"),
                    ("cars","Bugatti Chiron","Быстрейший серийный автомобиль",200_000_000,"👑"),
                    ("apartments","Комната в общежитии","12 м² — минимум для жизни",800_000,"🏠"),
                    ("apartments","Студия","24 м² — уютное гнёздышко",3_500_000,"🏡"),
                    ("apartments","1-комнатная","38 м² — для одного в самый раз",6_000_000,"🏠"),
                    ("apartments","2-комнатная","58 м² — хватит на семью",10_500_000,"🏘"),
                    ("apartments","3-комнатная","85 м² — простор и комфорт",18_000_000,"🏰"),
                    ("apartments","Пентхаус","250 м² — вид на весь город",75_000_000,"🌆"),
                    ("houses","Дача","50 м² — картошка и шашлык",1_500_000,"🌿"),
                    ("houses","Загородный дом","100 м² — жизнь за городом",7_000_000,"🏡"),
                    ("houses","Коттедж","200 м² — всё своё",18_000_000,"🏘"),
                    ("houses","Особняк","450 м² — охрана и бассейн",65_000_000,"🏰"),
                    ("houses","Вилла на Рублёвке","800 м² — для настоящих богачей",250_000_000,"👑"),
                    ("tech","Мышь Logitech G102","Точность и скорость",2_500,"🖱"),
                    ("tech","Клавиатура HyperX","Механика для профи",5_500,"⌨"),
                    ("tech","Наушники Sony XM5","Шумоподавление топ-уровня",32_000,"🎧"),
                    ("tech","Монитор 27\" QHD","Чёткое изображение без компромиссов",28_000,"🖥"),
                    ("tech","ОЗУ 32GB DDR5","Максимальная скорость",18_000,"💾"),
                    ("tech","SSD Samsung 2TB","Быстро и много",18_000,"💿"),
                    ("tech","RTX 4070 Ti","Высокие настройки без проблем",85_000,"🎮"),
                    ("tech","RTX 4090","Абсолютный топ видеокарт",180_000,"🔥"),
                    ("tech","Ноутбук Lenovo Legion","Игровой зверь в тонком корпусе",95_000,"💻"),
                    ("tech","MacBook Pro M3 Max","Мощь Apple на максималках",380_000,"🍎"),
                    ("tech","Игровой ПК (средний)","Сборка для большинства игр",150_000,"🖥"),
                    ("tech","Игровой ПК (топ)","Никаких компромиссов",500_000,"💎"),
                ]
                await db.executemany(
                    "INSERT INTO shop_items (category,name,description,price,icon) VALUES (?,?,?,?,?)",
                    shop_seed
                )
        # Добавляем новые товары (phones/jewelry) если ещё не существуют
        new_items = [
            ("phones","Xiaomi Redmi 13C","Бюджетный Xiaomi для всего нужного",12_000,"📱"),
            ("phones","Samsung Galaxy A15","Надёжный Samsung для повседневных задач",20_000,"📲"),
            ("phones","Xiaomi Redmi Note 14","Большой экран AMOLED, мощная батарея",22_000,"📱"),
            ("phones","Vivo Y28","Стильный смартфон с большим аккумулятором",25_000,"📱"),
            ("phones","Samsung Galaxy A55","Металлический корпус, AMOLED 120Гц",40_000,"📲"),
            ("phones","Vivo V40","Стильный дизайн, ZEISS портреты",45_000,"📱"),
            ("phones","iPhone SE (3rd gen)","Мощный и компактный смартфон Apple",50_000,"📱"),
            ("phones","Samsung Galaxy S24","Snapdragon 8 Gen 3, AI-функции",80_000,"📲"),
            ("phones","Vivo X200","Zeiss-камера, Dimensity 9400",90_000,"📱"),
            ("phones","iPhone 15","Dynamic Island, USB-C, 48 Мп",90_000,"📱"),
            ("phones","iPhone 16","A18, камера 48 Мп, Action Button",100_000,"📱"),
            ("phones","Samsung Galaxy S25","Snapdragon 8 Elite, Galaxy AI",100_000,"📲"),
            ("phones","Xiaomi 15","Leica-камера, Snapdragon 8 Elite",110_000,"📱"),
            ("phones","iPhone 15 Pro","Титановый корпус, ProMotion 120Гц",130_000,"🍎"),
            ("phones","Samsung Galaxy S24 Ultra","S Pen, 200 Мп камера",150_000,"💫"),
            ("phones","iPhone 16 Pro","A18 Pro, камера 48 Мп, 5× зум",150_000,"🍎"),
            ("phones","iPhone 15 Pro Max","6.7\", 5× телефото, ProMotion",165_000,"👑"),
            ("phones","Samsung Galaxy S25 Ultra","S Pen, Snapdragon 8 Elite, 200 Мп",180_000,"💫"),
            ("phones","iPhone 16 Pro Max","6.9\", A18 Pro, лучший iPhone 2024",190_000,"👑"),
            ("jewelry","Серебряная цепочка","Классика на любой случай",4_500,"⛓"),
            ("jewelry","Золотое кольцо","585 проба, элегантный дизайн",28_000,"💍"),
            ("jewelry","Часы Seiko Presage","Японская точность и стиль",45_000,"⌚"),
            ("jewelry","Золотая цепочка","750 проба, солидный подарок",75_000,"📿"),
            ("jewelry","Серьги с бриллиантом","Натуральные бриллианты, 0.5 карата",180_000,"💎"),
            ("jewelry","Бриллиантовое колье","Роскошный жемчуг с бриллиантами",500_000,"👑"),
            ("jewelry","Часы Rolex Submariner","Легенда швейцарского часового дела",1_500_000,"⌚"),
            ("jewelry","Часы Patek Philippe","Абсолютный люкс — лучшие часы в мире",8_000_000,"💎"),
            ("businesses","Ларёк с шаурмой","Небольшой ларёк на углу — первый шаг в бизнесе",50_000,"🌯"),
            ("businesses","Автомойка","Автоматическая мойка на 3 поста с химчисткой",300_000,"🚿"),
            ("businesses","Частное казино","Небольшое закрытое казино для избранных",15_000_000,"🎰"),
            ("businesses","Нефтяная компания в океане","Добывающая платформа в открытом море",249_999_999,"⛽"),
        ]
        for ni in new_items:
            await db.execute(
                "INSERT INTO shop_items (category,name,description,price,icon) "
                "SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM shop_items WHERE name=?)",
                (*ni, ni[1])
            )
        # Ставки аренды для квартир и бизнесов (всегда после вставки товаров)
        for name, rate in [
            ('Комната в общежитии', 20_000), ('Студия', 35_000),
            ('1-комнатная', 50_000), ('2-комнатная', 65_000),
            ('3-комнатная', 80_000), ('Пентхаус', 100_000),
            ('Ларёк с шаурмой', 3_500), ('Автомойка', 4_000),
            ('Частное казино', 500_000), ('Нефтяная компания в океане', 3_500_000),
        ]:
            await db.execute("UPDATE shop_items SET rent_rate=? WHERE name=?", (rate, name))

        # Стартовая квартира для всех пользователей без квартир в инвентаре
        async with db.execute(
            "SELECT id FROM shop_items WHERE name='Комната в общежитии' LIMIT 1"
        ) as cur:
            starter = await cur.fetchone()
        if starter:
            async with db.execute("""
                SELECT u.id, u.registered_at FROM users u
                WHERE NOT EXISTS (
                    SELECT 1 FROM inventory inv
                    JOIN shop_items s ON inv.item_id = s.id
                    WHERE inv.user_id = u.id AND s.category = 'apartments'
                )
            """) as cur:
                users_no_apt = await cur.fetchall()
            today = datetime.now().strftime("%Y-%m-%d")
            for u in users_no_apt:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, price_paid, bought_at) VALUES (?, ?, 0, ?)",
                    (u['id'], starter['id'], today)
                )

        await db.execute(
            "INSERT OR IGNORE INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)",
            ("TEST100", 100.0, 10)
        )
        await db.commit()


async def get_or_create_user(user_id: int, username: str) -> tuple[dict, bool]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            async with db.execute("SELECT COALESCE(MAX(uid), 0) + 1 FROM users") as cur:
                uid = (await cur.fetchone())[0]
            now = datetime.now().strftime("%Y-%m-%d")
            await db.execute(
                "INSERT INTO users (id, username, balance, games_played, uid, registered_at)"
                " VALUES (?, ?, 0, 0, ?, ?)",
                (user_id, username, uid, now)
            )
            # Стартовая квартира — Комната в общежитии (бесплатно)
            async with db.execute(
                "SELECT id FROM shop_items WHERE name='Комната в общежитии' LIMIT 1"
            ) as cur:
                starter = await cur.fetchone()
            if starter:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, price_paid, bought_at) VALUES (?, ?, 0, ?)",
                    (user_id, starter['id'], now)
                )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
            return dict(row), True
        return dict(row), False


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username.lstrip("@"),)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_rank(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE balance > (SELECT balance FROM users WHERE id = ?)",
            (user_id,)
        ) as cur:
            return (await cur.fetchone())[0] + 1


async def get_top(limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, balance FROM users WHERE hide_from_top = 0"
            " ORDER BY balance DESC LIMIT ?",
            (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def toggle_setting(user_id: int, setting: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT {setting} FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        new_val = 0 if row[0] else 1
        await db.execute(f"UPDATE users SET {setting} = ? WHERE id = ?", (new_val, user_id))
        await db.commit()


# user_id -> asyncio.Event для long polling
_event_watchers: dict[int, asyncio.Event] = {}


async def create_event(user_id: int, etype: str, amount: float, from_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pending_events (user_id, type, amount, from_name) VALUES (?, ?, ?, ?)",
            (user_id, etype, amount, from_name)
        )
        await db.commit()
    # Мгновенно будим ждущий long-poll клиент
    if user_id in _event_watchers:
        _event_watchers[user_id].set()


async def transfer(from_id: int, to_id: int, amount: float) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE id = ?", (from_id,)) as cur:
            sender = await cur.fetchone()
        if not sender or sender[0] < amount:
            return "not_enough"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, from_id))
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, to_id))
        await db.execute(
            "INSERT INTO transactions (type, from_id, to_id, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            ("pay", from_id, to_id, amount, now)
        )
        await db.commit()
        return "ok"


async def use_promo(code: str, user_id: int) -> tuple[str, float]:
    code = code.upper()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM used_promos WHERE user_id = ? AND code = ?", (user_id, code)
        ) as cur:
            if await cur.fetchone():
                return "already_used", 0.0
        async with db.execute(
            "SELECT reward, max_uses, uses_count FROM promo_codes WHERE code = ?", (code,)
        ) as cur:
            promo = await cur.fetchone()
        if not promo:
            return "invalid", 0.0
        reward, max_uses, uses_count = promo
        if uses_count >= max_uses:
            return "exhausted", 0.0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = ?", (code,)
        )
        await db.execute(
            "INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code)
        )
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (reward, user_id))
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?, ?, ?, ?)",
            ("promo", user_id, reward, now)
        )
        await db.commit()
        return "ok", reward


async def resolve_target(target_str: str) -> dict | None:
    if target_str.startswith("@"):
        return await get_user_by_username(target_str[1:])
    try:
        return await get_user(int(target_str))
    except ValueError:
        return None


async def create_promo(code: str, reward: float, max_uses: int) -> bool:
    """Возвращает False если промокод уже существует."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)",
                (code.upper(), reward, max_uses)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_promo(code: str) -> bool:
    """Возвращает False если промокод не найден."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM promo_codes WHERE code = ?", (code.upper(),)
        ) as cur:
            if not await cur.fetchone():
                return False
        await db.execute("DELETE FROM promo_codes WHERE code = ?", (code.upper(),))
        await db.execute("DELETE FROM used_promos WHERE code = ?", (code.upper(),))
        await db.commit()
        return True


async def get_all_promos() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT code, reward, max_uses, uses_count FROM promo_codes ORDER BY code"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?, ?, ?, ?)",
            ("addbalance", user_id, amount, now)
        )
        await db.commit()


async def subtract_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?, ?, ?, ?)",
            ("removebalance", user_id, amount, now)
        )
        await db.commit()


async def set_balance_exact(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance = ? WHERE id = ?", (amount, user_id))
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?, ?, ?, ?)",
            ("setbalance", user_id, amount, now)
        )
        await db.commit()


async def reset_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = 0, games_played = 0 WHERE id = ?", (user_id,)
        )
        await db.commit()


async def reset_all():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = 0, games_played = 0")
        await db.commit()


async def add_warning(user_id: int, reason: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT INTO warnings (user_id, reason, created_at) VALUES (?, ?, ?)",
            (user_id, reason, now)
        )
        await db.commit()
        async with db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,)
        ) as cur:
            return (await cur.fetchone())[0]


async def get_warnings(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT reason, created_at FROM warnings WHERE user_id = ? ORDER BY id",
            (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def clear_warnings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        await db.commit()


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET banned = 1 WHERE id = ?", (user_id,))
        await db.commit()


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users") as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_stats_data() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, username FROM users ORDER BY uid") as cur:
            users = [dict(r) for r in await cur.fetchall()]
        async with db.execute("SELECT COUNT(*) FROM transactions") as cur:
            tx_count = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(balance), 0) FROM users") as cur:
            total_balance = (await cur.fetchone())[0]
    return {"users": users, "tx_count": tx_count, "total_balance": total_balance}


async def load_admins():
    """Загружает is_admin=1 из БД в ADMIN_IDS при старте."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE is_admin = 1") as cur:
            rows = await cur.fetchall()
    for row in rows:
        ADMIN_IDS.add(row[0])


async def db_add_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        await db.commit()
    ADMIN_IDS.add(user_id)


async def db_remove_admin(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
        await db.commit()
    ADMIN_IDS.discard(user_id)


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET banned = 0 WHERE id = ?", (user_id,))
        await db.commit()


async def add_report(user_id: int, username: str, reason: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = await db.execute(
            "INSERT INTO reports (user_id, username, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, reason, now)
        )
        await db.commit()
        return cur.lastrowid


async def get_open_reports() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reports WHERE status = 'open' ORDER BY id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_report(report_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def close_report(report_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE reports SET status = 'closed' WHERE id = ?", (report_id,))
        await db.commit()


async def delete_report(report_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        await db.commit()


# ===================== WEB SERVER =====================

def validate_init_data(init_data: str) -> int | None:
    if not init_data:
        return None
    try:
        parsed: dict[str, str] = {}
        for item in init_data.split('&'):
            if '=' in item:
                k, v = item.split('=', 1)
                parsed[k] = unquote(v)
        received_hash = parsed.pop('hash', '')
        if not received_hash:
            return None
        data_check = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None
        user = json.loads(parsed.get('user', '{}'))
        return user.get('id')
    except Exception:
        return None


async def web_index(request: aio_web.Request) -> aio_web.Response:
    return aio_web.FileResponse(WEBAPP_DIR / "index.html")


async def web_api_ping(request: aio_web.Request) -> aio_web.Response:
    return aio_web.json_response({'ok': True})


async def web_api_user(request: aio_web.Request) -> aio_web.Response:
    try:
        user_id = validate_init_data(request.query.get('init_data', ''))
        if not user_id:
            logging.warning("web_api_user: invalid init_data")
            return aio_web.json_response({'error': 'Unauthorized'}, status=401)
        user = await get_user(user_id)
        if not user:
            logging.warning("web_api_user: user %s not found", user_id)
            return aio_web.json_response({'error': 'Пользователь не найден'}, status=404)
        return aio_web.json_response({
            'user_id': user_id,
            'balance': user['balance'],
            'username': user.get('username', ''),
        })
    except Exception:
        logging.exception("web_api_user crashed")
        return aio_web.json_response({'error': 'Внутренняя ошибка сервера'}, status=500)


async def web_api_upgrade(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    try:
        bet = round(float(data['bet']), 2)
        multiplier = round(float(data['multiplier']), 2)
    except (KeyError, TypeError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})

    if bet < 500:
        return aio_web.json_response({'error': 'Минимальная ставка 500₽'})
    if multiplier < 1.1 or multiplier > 100:
        return aio_web.json_response({'error': 'Неверный множитель'})

    user = await get_user(user_id)
    if not user:
        return aio_web.json_response({'error': 'Пользователь не найден'})
    if user.get('banned', 0):
        return aio_web.json_response({'error': 'Вы заблокированы'})

    balance = round(float(user['balance']), 2)
    if balance < bet:
        return aio_web.json_response({'error': 'Недостаточно средств'})

    won = random.random() < (1.0 / multiplier)
    profit = round(bet * (multiplier - 1), 2) if won else 0.0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        if won:
            new_balance = round(balance + profit, 2)
            await db.execute(
                "UPDATE users SET balance = ?, games_played = games_played + 1 WHERE id = ?",
                (new_balance, user_id),
            )
            await db.execute(
                "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?,?,?,?)",
                ("upgrade_win", user_id, profit, now_str),
            )
        else:
            new_balance = round(balance - bet, 2)
            await db.execute(
                "UPDATE users SET balance = ?, games_played = games_played + 1 WHERE id = ?",
                (new_balance, user_id),
            )
            await db.execute(
                "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?,?,?,?)",
                ("upgrade_lose", user_id, bet, now_str),
            )
        await db.execute(
            "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, 1 if won else 0, bet, profit, multiplier, now_str)
        )
        await db.commit()

    updated = await get_user(user_id)
    return aio_web.json_response({
        'won': won,
        'profit': profit,
        'new_balance': round(float(updated['balance']), 2),
    })


async def web_api_history(request: aio_web.Request) -> aio_web.Response:
    user_id = validate_init_data(request.query.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT won, bet, profit, mult, created_at FROM game_history"
            " WHERE user_id = ? ORDER BY id DESC LIMIT 50",
            (user_id,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return aio_web.json_response({'history': rows})


# ── САПЁР: сессии в памяти ────────────────────────────
ms_sessions: dict[str, dict] = {}

MS_HOUSE = 0.97

ROULETTE_SEGMENTS = [
    'blue', 'green', 'red', 'blue', 'blue',
    'green', 'blue', 'red', 'blue', 'green',
    'blue', 'red', 'blue', 'green', 'yellow'
]
ROULETTE_MULTIPLIERS = {'blue': 1.5, 'green': 2.0, 'red': 3.0, 'yellow': 5.0}

def ms_calc_mult(opened: int, mines: int) -> float:
    m = 1.0
    for i in range(opened):
        m *= (25 - i) / (25 - mines - i)
    return round(m * MS_HOUSE, 4)


async def web_api_ms_start(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    try:
        bet = round(float(data['bet']), 2)
        mines = int(data['mines'])
    except (KeyError, TypeError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})

    if bet < 500:
        return aio_web.json_response({'error': 'Минимальная ставка 500₽'})
    if mines < 1 or mines > 24:
        return aio_web.json_response({'error': 'Неверное количество мин'})

    user = await get_user(user_id)
    if not user:
        return aio_web.json_response({'error': 'Пользователь не найден'})
    if user.get('banned', 0):
        return aio_web.json_response({'error': 'Вы заблокированы'})

    balance = round(float(user['balance']), 2)
    if balance < bet:
        return aio_web.json_response({'error': 'Недостаточно средств'})

    new_balance = round(balance - bet, 2)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = ?, games_played = games_played + 1 WHERE id = ?",
            (new_balance, user_id)
        )
        await db.commit()

    mine_positions = set(random.sample(range(25), mines))
    session_id = secrets.token_hex(16)
    ms_sessions[session_id] = {
        'user_id': user_id,
        'bet': bet,
        'mines': mines,
        'mine_positions': mine_positions,
        'opened': [],
        'active': True,
    }

    return aio_web.json_response({'session_id': session_id, 'new_balance': new_balance})


async def web_api_ms_open(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    session_id = data.get('session_id', '')
    cell = data.get('cell')
    session = ms_sessions.get(session_id)

    if not session or session['user_id'] != user_id or not session['active']:
        return aio_web.json_response({'error': 'Сессия не найдена'})
    if not isinstance(cell, int) or cell < 0 or cell > 24:
        return aio_web.json_response({'error': 'Неверная клетка'})
    if cell in session['opened']:
        return aio_web.json_response({'error': 'Клетка уже открыта'})

    if cell in session['mine_positions']:
        session['active'] = False
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, 0, session['bet'], 0.0, 0.0, now_str)
            )
            await db.commit()
        mine_list = list(session['mine_positions'])
        del ms_sessions[session_id]
        user = await get_user(user_id)
        return aio_web.json_response({
            'is_mine': True,
            'mine_positions': mine_list,
            'new_balance': round(float(user['balance']), 2) if user else 0,
        })
    else:
        session['opened'].append(cell)
        multiplier = ms_calc_mult(len(session['opened']), session['mines'])
        return aio_web.json_response({'is_mine': False, 'multiplier': multiplier})


async def web_api_ms_cashout(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    session_id = data.get('session_id', '')
    session = ms_sessions.get(session_id)

    if not session or session['user_id'] != user_id or not session['active']:
        return aio_web.json_response({'error': 'Сессия не найдена'})
    if not session['opened']:
        return aio_web.json_response({'error': 'Откройте хотя бы одну клетку'})

    multiplier = ms_calc_mult(len(session['opened']), session['mines'])
    total_win = round(session['bet'] * multiplier, 2)
    profit = round(total_win - session['bet'], 2)

    session['active'] = False
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (total_win, user_id)
        )
        await db.execute(
            "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, 1, session['bet'], profit, multiplier, now_str)
        )
        await db.commit()

    del ms_sessions[session_id]
    user = await get_user(user_id)
    return aio_web.json_response({
        'profit': profit,
        'new_balance': round(float(user['balance']), 2) if user else 0,
    })


# ── КРАШ ─────────────────────────────────────────────
crash_sessions: dict[str, dict] = {}
crash_history:  list[float]     = []
CRASH_GROWTH = 0.035  # mult(t) = e^(t * CRASH_GROWTH), ~x2 за ~20 сек

def _crash_mult(elapsed: float) -> float:
    return math.e ** (elapsed * CRASH_GROWTH)

def _gen_crash_point() -> float:
    r = random.random()
    if r < 0.004:          # 0.4% мгновенный краш
        return 1.0
    cp = 0.97 / (1.0 - r)
    return round(max(1.01, cp), 2)

async def web_api_crash_start(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    try:
        bet = round(float(data['bet']), 2)
    except (KeyError, TypeError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})

    if bet < 500:
        return aio_web.json_response({'error': 'Минимальная ставка 500₽'})

    user = await get_user(user_id)
    if not user:
        return aio_web.json_response({'error': 'Пользователь не найден'})
    if user.get('banned', 0):
        return aio_web.json_response({'error': 'Вы заблокированы'})

    balance = round(float(user['balance']), 2)
    if balance < bet:
        return aio_web.json_response({'error': 'Недостаточно средств'})

    new_balance = round(balance - bet, 2)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = ?, games_played = games_played + 1 WHERE id = ?",
            (new_balance, user_id)
        )
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?,?,?,?)",
            ("crash_bet", user_id, bet, now_str)
        )
        await db.commit()

    crash_point = _gen_crash_point()
    session_id  = secrets.token_hex(16)
    start_ts    = datetime.now().timestamp()

    crash_sessions[session_id] = {
        'user_id': user_id, 'bet': bet,
        'crash_point': crash_point, 'start_time': start_ts,
        'active': True, 'cashed_out': False, 'history_recorded': False,
    }

    return aio_web.json_response({
        'session_id': session_id,
        'start_ms':   int(start_ts * 1000),
        'new_balance': new_balance,
        'history':    list(crash_history[-10:]),
    })


async def web_api_crash_cashout(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    session_id = data.get('session_id', '')
    session = crash_sessions.get(session_id)

    if not session or session['user_id'] != user_id:
        return aio_web.json_response({'error': 'Сессия не найдена'})
    if session['cashed_out']:
        return aio_web.json_response({'error': 'Уже выведено'})
    if not session['active']:
        return aio_web.json_response({'crashed': True, 'crash_point': session['crash_point']})

    elapsed      = datetime.now().timestamp() - session['start_time']
    current_mult = _crash_mult(elapsed)

    if current_mult >= session['crash_point']:
        session['active'] = False
        cp = session['crash_point']
        if not session['history_recorded']:
            session['history_recorded'] = True
            crash_history.append(cp)
            if len(crash_history) > 20:
                crash_history.pop(0)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, 0, session['bet'], 0.0, cp, now_str)
                )
                await db.commit()
        crash_sessions.pop(session_id, None)
        return aio_web.json_response({'crashed': True, 'crash_point': cp})

    cashout_mult = round(current_mult, 2)
    total        = round(session['bet'] * cashout_mult, 2)
    profit       = round(total - session['bet'], 2)

    session['active']    = False
    session['cashed_out'] = True

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (total, user_id)
        )
        await db.execute(
            "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, 1, session['bet'], profit, cashout_mult, now_str)
        )
        await db.commit()

    crash_sessions.pop(session_id, None)
    user = await get_user(user_id)
    return aio_web.json_response({
        'crashed': False, 'mult': cashout_mult,
        'profit': profit,
        'new_balance': round(float(user['balance']), 2),
    })


async def web_api_crash_status(request: aio_web.Request) -> aio_web.Response:
    session_id = request.query.get('session_id', '')
    init_data  = request.query.get('init_data', '')

    user_id = validate_init_data(init_data)
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    session = crash_sessions.get(session_id)
    if not session or session['user_id'] != user_id:
        return aio_web.json_response({'error': 'Сессия не найдена'})

    if not session['active']:
        return aio_web.json_response({'active': False, 'cashed_out': session['cashed_out']})

    elapsed      = datetime.now().timestamp() - session['start_time']
    current_mult = _crash_mult(elapsed)

    if current_mult >= session['crash_point']:
        session['active'] = False
        cp = session['crash_point']
        if not session['history_recorded']:
            session['history_recorded'] = True
            crash_history.append(cp)
            if len(crash_history) > 20:
                crash_history.pop(0)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, 0, session['bet'], 0.0, cp, now_str)
                )
                await db.commit()
        crash_sessions.pop(session_id, None)
        return aio_web.json_response({
            'active': False, 'crashed': True,
            'crash_point': cp,
            'history': list(crash_history[-10:]),
        })

    return aio_web.json_response({
        'active': True,
        'mult':    round(current_mult, 2),
        'elapsed': round(elapsed, 3),
    })


async def web_api_roulette(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)

    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)

    try:
        bet = round(float(data['bet']), 2)
        color = str(data['color']).lower()
    except (KeyError, TypeError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})

    if bet < 500:
        return aio_web.json_response({'error': 'Минимальная ставка 500₽'})
    if color not in ROULETTE_MULTIPLIERS:
        return aio_web.json_response({'error': 'Неверный цвет'})

    user = await get_user(user_id)
    if not user:
        return aio_web.json_response({'error': 'Пользователь не найден'})
    if user.get('banned', 0):
        return aio_web.json_response({'error': 'Вы заблокированы'})

    balance = round(float(user['balance']), 2)
    if balance < bet:
        return aio_web.json_response({'error': 'Недостаточно средств'})

    segment_idx = random.randint(0, len(ROULETTE_SEGMENTS) - 1)
    result_color = ROULETTE_SEGMENTS[segment_idx]
    won = result_color == color
    multiplier = ROULETTE_MULTIPLIERS[color]
    profit = round(bet * (multiplier - 1), 2) if won else 0.0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        if won:
            new_balance = round(balance + profit, 2)
        else:
            new_balance = round(balance - bet, 2)
        await db.execute(
            "UPDATE users SET balance = ?, games_played = games_played + 1 WHERE id = ?",
            (new_balance, user_id)
        )
        await db.execute(
            "INSERT INTO transactions (type, to_id, amount, created_at) VALUES (?,?,?,?)",
            ("roulette_win" if won else "roulette_lose", user_id, profit if won else bet, now_str)
        )
        await db.execute(
            "INSERT INTO game_history (user_id, won, bet, profit, mult, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, 1 if won else 0, bet, profit, multiplier, now_str)
        )
        await db.commit()

    return aio_web.json_response({
        'won': won,
        'profit': profit,
        'result_color': result_color,
        'segment_idx': segment_idx,
        'new_balance': new_balance,
    })


@aio_web.middleware
async def cors_middleware(request: aio_web.Request, handler):
    if request.method == 'OPTIONS':
        return aio_web.Response(headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        })
    resp = await handler(request)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


async def _fetch_and_clear_events(user_id: int) -> tuple[float, list]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None, []
        bal = round(float(row['balance']), 2)
        async with db.execute(
            "SELECT id, type, amount, from_name FROM pending_events WHERE user_id = ? ORDER BY id ASC",
            (user_id,)
        ) as cur:
            events = [dict(r) for r in await cur.fetchall()]
        if events:
            ids = [e['id'] for e in events]
            await db.execute(
                f"DELETE FROM pending_events WHERE id IN ({','.join('?'*len(ids))})", tuple(ids)
            )
            await db.commit()
    return bal, events


async def web_api_events(request: aio_web.Request) -> aio_web.Response:
    try:
        user_id = validate_init_data(request.query.get('init_data', ''))
        if not user_id:
            return aio_web.json_response({'error': 'Unauthorized'}, status=401)
        bal, events = await _fetch_and_clear_events(user_id)
        if bal is None:
            return aio_web.json_response({'error': 'Not found'}, status=404)
        return aio_web.json_response({
            'balance': bal,
            'events': [{'type': e['type'], 'amount': e['amount'], 'from_name': e['from_name']} for e in events],
        })
    except Exception:
        logging.exception("web_api_events crashed")
        return aio_web.json_response({'error': 'Internal error'}, status=500)


def calc_rental_income(last_collected: str, rate: float) -> float:
    last = datetime.strptime(last_collected, "%Y-%m-%d %H:%M:%S")
    return (datetime.now() - last).total_seconds() / 3600 * rate


async def web_api_shop(request: aio_web.Request) -> aio_web.Response:
    user_id = validate_init_data(request.query.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id,category,name,description,price,icon,image_url FROM shop_items ORDER BY category,price"
        ) as cur:
            items = [dict(r) for r in await cur.fetchall()]
    return aio_web.json_response({'items': items})


async def web_api_shop_buy(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        item_id = int(data['item_id'])
    except (KeyError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)) as cur:
            item = await cur.fetchone()
        if not item:
            return aio_web.json_response({'error': 'Товар не найден'})
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row['balance'] < item['price']:
            return aio_web.json_response({'error': 'Недостаточно средств'})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (item['price'], user_id))
        await db.execute(
            "INSERT INTO inventory (user_id,item_id,price_paid,bought_at) VALUES (?,?,?,?)",
            (user_id, item_id, item['price'], now)
        )
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            new_bal = round(float((await cur.fetchone())['balance']), 2)
    return aio_web.json_response({'ok': True, 'new_balance': new_bal,
                                   'item': {'name': item['name'], 'icon': item['icon']}})


async def web_api_inventory(request: aio_web.Request) -> aio_web.Response:
    user_id = validate_init_data(request.query.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT i.id, i.price_paid, i.bought_at,
                      s.name, s.description, s.icon, s.category,
                      CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END as is_rented
               FROM inventory i JOIN shop_items s ON i.item_id = s.id
               LEFT JOIN rentals r ON r.inv_id = i.id
               WHERE i.user_id = ? ORDER BY i.bought_at DESC""",
            (user_id,)
        ) as cur:
            items = [dict(r) for r in await cur.fetchall()]
    return aio_web.json_response({'items': items})


async def web_api_inventory_sell(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        inv_id = int(data['inv_id'])
    except (KeyError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT i.*,s.name FROM inventory i JOIN shop_items s ON i.item_id=s.id WHERE i.id=? AND i.user_id=?",
            (inv_id, user_id)
        ) as cur:
            inv = await cur.fetchone()
        if not inv:
            return aio_web.json_response({'error': 'Предмет не найден'})
        async with db.execute("SELECT 1 FROM rentals WHERE inv_id=?", (inv_id,)) as cur:
            if await cur.fetchone():
                return aio_web.json_response({'error': 'Сначала остановите аренду'})
        if inv['name'] == 'Комната в общежитии' and inv['price_paid'] == 0:
            return aio_web.json_response({'error': 'Стартовую квартиру нельзя продать'})
        sell_price = round(inv['price_paid'] * (1 - SHOP_TAX), 2)
        await db.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (sell_price, user_id))
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            new_bal = round(float((await cur.fetchone())['balance']), 2)
    return aio_web.json_response({'ok': True, 'sell_price': sell_price, 'new_balance': new_bal})


async def web_api_rentals(request: aio_web.Request) -> aio_web.Response:
    user_id = validate_init_data(request.query.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    cat = request.query.get('cat', 'apartments')
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT r.id, r.inv_id, r.rate, r.last_collected,
                      s.name, s.icon, s.category
               FROM rentals r JOIN shop_items s ON r.item_id = s.id
               WHERE r.user_id = ? AND s.category=?""", (user_id, cat)
        ) as cur:
            rentals = [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            """SELECT i.id, s.name, s.icon, s.rent_rate, s.category
               FROM inventory i JOIN shop_items s ON i.item_id = s.id
               WHERE i.user_id = ? AND s.category=? AND s.rent_rate > 0
                 AND i.id NOT IN (SELECT inv_id FROM rentals WHERE user_id = ?)""",
            (user_id, cat, user_id)
        ) as cur:
            available = [dict(r) for r in await cur.fetchall()]
    for r in rentals:
        r['accumulated'] = math.floor(calc_rental_income(r['last_collected'], r['rate']))
    return aio_web.json_response({'rentals': rentals, 'available': available})


async def web_api_rental_start(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        inv_id = int(data['inv_id'])
    except (KeyError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT i.*,s.rent_rate,s.name FROM inventory i JOIN shop_items s ON i.item_id=s.id WHERE i.id=? AND i.user_id=?",
            (inv_id, user_id)
        ) as cur:
            item = await cur.fetchone()
        if not item:
            return aio_web.json_response({'error': 'Предмет не найден'})
        if not item['rent_rate']:
            return aio_web.json_response({'error': 'Этот предмет нельзя сдавать в аренду'})
        async with db.execute("SELECT 1 FROM rentals WHERE inv_id=?", (inv_id,)) as cur:
            if await cur.fetchone():
                return aio_web.json_response({'error': 'Уже сдаётся'})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT INTO rentals (user_id,inv_id,item_id,rate,started_at,last_collected) VALUES (?,?,?,?,?,?)",
            (user_id, inv_id, item['item_id'], item['rent_rate'], now, now)
        )
        await db.commit()
    return aio_web.json_response({'ok': True})


async def web_api_rental_collect(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        rental_id = int(data['rental_id'])
    except (KeyError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT r.*, s.category FROM rentals r JOIN shop_items s ON r.item_id=s.id WHERE r.id=? AND r.user_id=?",
            (rental_id, user_id)
        ) as cur:
            rental = await cur.fetchone()
        if not rental:
            return aio_web.json_response({'error': 'Аренда не найдена'})
        income = math.floor(calc_rental_income(rental['last_collected'], rental['rate']))
        if income < math.floor(rental['rate']):
            return aio_web.json_response({'error': 'Нельзя собирать раньше чем за 1 час аренды'})
        utility = math.floor(income * 0.10)
        net = income if rental['category'] == 'businesses' else income - utility
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (net, user_id))
        await db.execute("UPDATE rentals SET last_collected=? WHERE id=?", (now, rental_id))
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id=?", (user_id,)) as cur:
            new_bal = round(float((await cur.fetchone())['balance']), 2)
    return aio_web.json_response({'ok': True, 'income': income, 'utility': utility, 'net': net, 'new_balance': new_bal})


async def web_api_rental_stop(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    try:
        rental_id = int(data['rental_id'])
    except (KeyError, ValueError):
        return aio_web.json_response({'error': 'Неверные данные'})
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT r.*, s.category FROM rentals r JOIN shop_items s ON r.item_id=s.id WHERE r.id=? AND r.user_id=?",
            (rental_id, user_id)
        ) as cur:
            rental = await cur.fetchone()
        if not rental:
            return aio_web.json_response({'error': 'Аренда не найдена'})
        income = math.floor(calc_rental_income(rental['last_collected'], rental['rate']))
        if income > 0:
            utility = math.floor(income * 0.10)
            net = income if rental['category'] == 'businesses' else income - utility
            await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (net, user_id))
        else:
            utility = 0
            net = 0
        await db.execute("DELETE FROM rentals WHERE id=?", (rental_id,))
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id=?", (user_id,)) as cur:
            new_bal = round(float((await cur.fetchone())['balance']), 2)
    return aio_web.json_response({'ok': True, 'income': income, 'utility': utility, 'net': net, 'new_balance': new_bal})


async def web_api_case_status(request: aio_web.Request) -> aio_web.Response:
    user_id = validate_init_data(request.query.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT daily_case_at FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        daily_at = row['daily_case_at'] if row else None
        daily_available = True
        daily_next_at = None
        if daily_at:
            try:
                last = datetime.strptime(daily_at, "%Y-%m-%d %H:%M:%S")
                if (datetime.utcnow() - last).total_seconds() < 86400:
                    daily_available = False
                    daily_next_at = (last + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        keys = {'cars': 0, 'apartments': 0, 'houses': 0, 'tech': 0, 'phones': 0, 'jewelry': 0}
        async with db.execute("SELECT case_type, amount FROM case_keys WHERE user_id=?", (user_id,)) as cur:
            async for r in cur:
                if r['case_type'] in keys:
                    keys[r['case_type']] = r['amount']
    return aio_web.json_response({'ok': True, 'daily_available': daily_available, 'daily_next_at': daily_next_at, 'keys': keys})


async def web_api_case_open(request: aio_web.Request) -> aio_web.Response:
    try:
        data = await request.json()
    except Exception:
        return aio_web.json_response({'error': 'Неверный запрос'}, status=400)
    user_id = validate_init_data(data.get('init_data', ''))
    if not user_id:
        return aio_web.json_response({'error': 'Unauthorized'}, status=401)
    case_type = data.get('case_type', '')
    use_key = bool(data.get('use_key', False))
    if case_type not in CASE_LOOT:
        return aio_web.json_response({'error': 'Неверный кейс'}, status=400)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT balance, daily_case_at FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return aio_web.json_response({'error': 'Пользователь не найден'}, status=404)
        balance = row['balance']
        daily_at = row['daily_case_at']
        price = CASE_PRICES[case_type]
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if case_type == 'daily':
            if daily_at:
                try:
                    last = datetime.strptime(daily_at, "%Y-%m-%d %H:%M:%S")
                    if (datetime.utcnow() - last).total_seconds() < 86400:
                        return aio_web.json_response({'error': 'Подождите 24 часа'}, status=400)
                except Exception:
                    pass
            await db.execute("UPDATE users SET daily_case_at=? WHERE id=?", (now_str, user_id))
        elif use_key:
            async with db.execute("SELECT amount FROM case_keys WHERE user_id=? AND case_type=?", (user_id, case_type)) as cur:
                key_row = await cur.fetchone()
            if not key_row or key_row['amount'] < 1:
                return aio_web.json_response({'error': 'Нет ключа для этого кейса'}, status=400)
            await db.execute("UPDATE case_keys SET amount=amount-1 WHERE user_id=? AND case_type=?", (user_id, case_type))
        else:
            if balance < price:
                return aio_web.json_response({'error': 'Недостаточно средств'}, status=400)
            await db.execute("UPDATE users SET balance=balance-? WHERE id=?", (price, user_id))
        # Бросаем кубик
        loot_table = CASE_LOOT[case_type]
        total_weight = sum(w for _, _, w in loot_table)
        roll = random.randint(1, total_weight)
        cumulative = 0
        reward_type, reward_value = 'nothing', None
        for rtype, rval, weight in loot_table:
            cumulative += weight
            if roll <= cumulative:
                reward_type, reward_value = rtype, rval
                break
        result: dict = {'ok': True, 'reward': reward_type}
        if reward_type == 'item':
            async with db.execute("SELECT id, icon, price FROM shop_items WHERE name=?", (reward_value,)) as cur:
                item_row = await cur.fetchone()
            if item_row:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, price_paid, bought_at) VALUES (?,?,?,?)",
                    (user_id, item_row['id'], item_row['price'], now_str)
                )
                result['item'] = {'name': reward_value, 'icon': item_row['icon']}
            else:
                result['reward'] = 'nothing'
        elif reward_type == 'key':
            await db.execute(
                "INSERT INTO case_keys (user_id, case_type, amount) VALUES (?,?,1) "
                "ON CONFLICT(user_id, case_type) DO UPDATE SET amount=amount+1",
                (user_id, reward_value)
            )
            result['key_type'] = reward_value
        elif reward_type == 'balance':
            await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (reward_value, user_id))
            result['amount'] = reward_value
        await db.commit()
        async with db.execute("SELECT balance FROM users WHERE id=?", (user_id,)) as cur:
            new_bal = round(float((await cur.fetchone())['balance']), 2)
        result['new_balance'] = new_bal
    return aio_web.json_response(result)


def make_web_app() -> aio_web.Application:
    app = aio_web.Application(middlewares=[cors_middleware])
    app.router.add_get('/', web_index)
    app.router.add_get('/api/ping', web_api_ping)
    app.router.add_static('/images', Path(__file__).parent / 'images')
    app.router.add_route('OPTIONS', '/api/user', lambda r: aio_web.Response())
    app.router.add_route('OPTIONS', '/api/upgrade', lambda r: aio_web.Response())
    app.router.add_get('/api/user', web_api_user)
    app.router.add_route('OPTIONS', '/api/events', lambda r: aio_web.Response())
    app.router.add_get('/api/events', web_api_events)
    app.router.add_post('/api/upgrade', web_api_upgrade)
    app.router.add_route('OPTIONS', '/api/history', lambda r: aio_web.Response())
    app.router.add_get('/api/history', web_api_history)
    app.router.add_route('OPTIONS', '/api/shop', lambda r: aio_web.Response())
    app.router.add_get('/api/shop', web_api_shop)
    app.router.add_route('OPTIONS', '/api/shop/buy', lambda r: aio_web.Response())
    app.router.add_post('/api/shop/buy', web_api_shop_buy)
    app.router.add_route('OPTIONS', '/api/inventory', lambda r: aio_web.Response())
    app.router.add_get('/api/inventory', web_api_inventory)
    app.router.add_route('OPTIONS', '/api/inventory/sell', lambda r: aio_web.Response())
    app.router.add_post('/api/inventory/sell', web_api_inventory_sell)
    for path in ('/api/rentals', '/api/rental/start', '/api/rental/collect', '/api/rental/stop'):
        app.router.add_route('OPTIONS', path, lambda r: aio_web.Response())
    app.router.add_get ('/api/rentals',        web_api_rentals)
    app.router.add_post('/api/rental/start',   web_api_rental_start)
    app.router.add_post('/api/rental/collect', web_api_rental_collect)
    app.router.add_post('/api/rental/stop',    web_api_rental_stop)
    for path in ('/api/case/status', '/api/case/open'):
        app.router.add_route('OPTIONS', path, lambda r: aio_web.Response())
    app.router.add_get ('/api/case/status', web_api_case_status)
    app.router.add_post('/api/case/open',   web_api_case_open)
    for path in ('/api/minesweeper/start', '/api/minesweeper/open', '/api/minesweeper/cashout'):
        app.router.add_route('OPTIONS', path, lambda r: aio_web.Response())
    app.router.add_post('/api/minesweeper/start',   web_api_ms_start)
    app.router.add_post('/api/minesweeper/open',    web_api_ms_open)
    app.router.add_post('/api/minesweeper/cashout', web_api_ms_cashout)
    app.router.add_route('OPTIONS', '/api/roulette', lambda r: aio_web.Response())
    app.router.add_post('/api/roulette', web_api_roulette)
    for path in ('/api/crash/start', '/api/crash/cashout', '/api/crash/status'):
        app.router.add_route('OPTIONS', path, lambda r: aio_web.Response())
    app.router.add_post('/api/crash/start',   web_api_crash_start)
    app.router.add_post('/api/crash/cashout', web_api_crash_cashout)
    app.router.add_get ('/api/crash/status',  web_api_crash_status)
    return app


# ===================== УТИЛИТЫ =====================

def fmt_num(n: float, short: bool = False) -> str:
    if not short:
        return f"{n:,.2f}₽".replace(",", " ")
    if abs(n) >= 1_000_000:
        s = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{s}м₽"
    if abs(n) >= 1_000:
        s = f"{n / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{s}к₽"
    return f"{n:.0f}₽"


def fmt_date(date_str: str | None) -> str:
    if not date_str:
        return "—"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.day} {MONTHS_RU[dt.month - 1]} {dt.year}"
    except Exception:
        return "—"


async def notify_transfer(target: dict, amount: float, sender_name: str):
    if target.get("quiet_mode", 0) or not target.get("notify_transfers", 1):
        return
    updated = await get_user(target["id"])
    text = (
        f"💸 Входящий перевод\n\n"
        f"💰 Сумма: <b>{fmt_num(amount)}</b>\n"
        f"👤 От: @{sender_name}"
    )
    if updated:
        text += f"\n\n📊 Ваш баланс: <b>{fmt_num(updated['balance'])}</b>"
    try:
        await bot.send_message(target["id"], text, parse_mode="HTML")
    except Exception:
        pass


async def notify_give(target: dict, amount: float):
    if target.get("quiet_mode", 0) or not target.get("notify_transfers", 1):
        return
    updated = await get_user(target["id"])
    text = f"🎁 Администратор начислил вам <b>{fmt_num(amount)}</b>"
    if updated:
        text += f"\n\n📊 Ваш баланс: <b>{fmt_num(updated['balance'])}</b>"
    try:
        await bot.send_message(target["id"], text, parse_mode="HTML")
    except Exception:
        pass


async def notify_remove(target: dict, amount: float):
    if target.get("quiet_mode", 0) or not target.get("notify_transfers", 1):
        return
    updated = await get_user(target["id"])
    text = f"📉 Администратор снял <b>{fmt_num(amount)}</b> с вашего баланса"
    if updated:
        text += f"\n\n📊 Ваш баланс: <b>{fmt_num(updated['balance'])}</b>"
    try:
        await bot.send_message(target["id"], text, parse_mode="HTML")
    except Exception:
        pass


async def notify_set(target: dict, amount: float):
    if target.get("quiet_mode", 0) or not target.get("notify_transfers", 1):
        return
    text = f"⚙️ Администратор установил ваш баланс: <b>{fmt_num(amount)}</b>"
    try:
        await bot.send_message(target["id"], text, parse_mode="HTML")
    except Exception:
        pass


# ===================== КЛАВИАТУРЫ =====================

def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"),        KeyboardButton(text="🏆 Топ")],
            [KeyboardButton(text="🎟 Ввод промокода"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def _toggle_btn(label: str, val: int, cb: str) -> InlineKeyboardButton:
    state = "✅" if val else "☑️"
    return InlineKeyboardButton(text=f"{state} {label}", callback_data=cb)


def _section_btn(title: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=title, callback_data="noop")


def kb_settings(user: dict) -> InlineKeyboardMarkup:
    s = user
    return InlineKeyboardMarkup(inline_keyboard=[
        [_toggle_btn("Подтверждение перевода", s.get("confirm_pay",   0), "toggle_confirm_pay")],
        [_toggle_btn("Сокращение чисел",       s.get("short_numbers", 0), "toggle_short_numbers")],
        [_toggle_btn("Тихий режим",            s.get("quiet_mode",    0), "toggle_quiet_mode")],
    ])


def kb_pay_confirm(to_id: int, amount: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"pay_confirm:{to_id}:{amount:.2f}"),
        InlineKeyboardButton(text="❌ Отмена",      callback_data="pay_cancel"),
    ]])


def kb_promo_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="promo_cancel"),
    ]])


def kb_promo_retry() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="promo_cancel"),
        InlineKeyboardButton(text="🔄 Заново", callback_data="promo_retry"),
    ]])


def kb_reset_all_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, сбросить всё", callback_data="admin_reset_all_confirm"),
        InlineKeyboardButton(text="❌ Отмена",            callback_data="admin_reset_all_cancel"),
    ]])


def kb_report_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="report_cancel"),
    ]])


def kb_reports_list(reports: list) -> InlineKeyboardMarkup:
    rows = []
    for r in reports:
        short = r["reason"][:28] + "…" if len(r["reason"]) > 28 else r["reason"]
        uname = f"@{r['username']}" if r["username"] else f"ID {r['user_id']}"
        rows.append([InlineKeyboardButton(
            text=f"#{r['id']} {uname} — {short}",
            callback_data=f"report_view:{r['id']}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_report_detail(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↩️ Назад",    callback_data="reports_list"),
        InlineKeyboardButton(text="✅ Закрыть",  callback_data=f"report_close:{report_id}"),
        InlineKeyboardButton(text="🗑 Удалить",  callback_data=f"report_del:{report_id}"),
    ]])


# ===================== MIDDLEWARE =====================

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id not in ADMIN_IDS:
            db_user = await get_user(user.id)
            if db_user and db_user.get("banned", 0):
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 Вы заблокированы в боте.")
                    except Exception:
                        pass
                elif isinstance(event, CallbackQuery):
                    try:
                        await event.answer("🚫 Вы заблокированы.", show_alert=True)
                    except Exception:
                        pass
                return
        return await handler(event, data)


# ===================== ХЭНДЛЕРЫ =====================

@router.message(CommandStart())
async def h_start(msg: Message):
    username = msg.from_user.username or msg.from_user.first_name
    user, is_new = await get_or_create_user(msg.from_user.id, username)
    name = f"<b>{msg.from_user.first_name}</b>"

    if is_new:
        text = (
            f"👋 Привет, {name}! Добро пожаловать в <b>Лутобот</b>.\n\n"
            f"Твой номер в системе: <b>#{user['uid']}</b>\n\n"
            f"Что здесь есть:\n"
            f"• 💰 Баланс и переводы между игроками\n"
            f"• 🏆 Таблица лидеров\n"
            f"• 🎟 Промокоды с наградами\n"
            f"• ⚙️ Гибкие настройки профиля"
        )
    else:
        short = bool(user.get("short_numbers", 0))
        rank = await get_user_rank(msg.from_user.id)
        rank_str = "скрыт 👻" if user.get("hide_from_top") else f"#{rank}"
        lines = [f"👋 С возвращением, {name}!", ""]
        lines.append(f"💰 Баланс: <b>{fmt_num(user['balance'], short)}</b>")
        lines.append(f"🏆 Место в топе: {rank_str}   🎮 Игр: {user['games_played']}")
        if user.get("show_join_date", 1) and user.get("registered_at"):
            lines.append(f"📅 С нами с {fmt_date(user['registered_at'])}")
        text = "\n".join(lines)

    await msg.answer(text, parse_mode="HTML", reply_markup=kb_main())


@router.message(Command("help"))
async def h_help(msg: Message):
    is_admin = msg.from_user.id in ADMIN_IDS
    text = (
        "📋 <b>Справка по боту</b>\n\n"
        "👤 <b>Основные команды</b>\n"
        "/start — перезапустить бота\n"
        "/help — эта справка\n\n"
        "💸 <b>Переводы</b>\n"
        "/pay <code>@юзернейм сумма</code> — перевести деньги\n"
        "/pay <code>ID сумма</code> — перевести по Telegram ID\n"
        "<i>Пример: /pay @username 100</i>\n\n"
        "📋 <b>Репорты</b>\n"
        "/report <code>причина</code> — отправить жалобу\n"
        "/report — то же самое, но с запросом причины\n"
    )
    if is_admin:
        text += (
            "\n👑 <b>Администратор</b>\n"
            "/addbalance <code>ID сумма</code> — начислить валюту\n"
            "/removebalance <code>ID сумма</code> — снять валюту\n"
            "/setbalance <code>ID сумма</code> — установить точный баланс\n"
            "/reset <code>ID</code> — сбросить прогресс пользователя\n"
            "/reset_all — сбросить всю базу (с подтверждением)\n"
            "/broadcast <code>сообщение</code> — рассылка всем\n"
            "/warn <code>ID причина</code> — предупреждение (3 варна = бан)\n"
            "/warnings <code>ID</code> — список варнов пользователя\n"
            "/clearwarns <code>ID</code> — снять все варны\n"
            "/ban <code>ID</code> — заблокировать пользователя\n"
            "/unban <code>ID</code> — разблокировать пользователя\n"
            "/reports — список открытых репортов\n"
            "/addpromo <code>КОД СУММА КОЛ-ВО</code> — создать промокод\n"
            "/delpromo <code>КОД</code> — удалить промокод\n"
            "/listpromo — список всех промокодов\n"
            "/stats — статистика бота\n"
        )
        if msg.from_user.id in SUPERADMIN_IDS:
            text += (
                "\n🔱 <b>Суперадмин</b>\n"
                "/addadmin <code>ID</code> — выдать права администратора\n"
                "/deladmin <code>ID</code> — забрать права администратора\n"
            )
    await msg.answer(text, parse_mode="HTML")


@router.message(Command("pay"))
async def h_pay(msg: Message):
    args = msg.text.split()[1:]
    if len(args) < 2:
        await msg.answer(
            "❌ Использование: <code>/pay @юзернейм сумма</code>",
            parse_mode="HTML",
        )
        return

    target_str, amount_str = args[0], args[1]

    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Укажи корректную сумму.")
        return

    target = await resolve_target(target_str)
    if target is None and not target_str.startswith("@"):
        await msg.answer("❌ Неверный формат ID.")
        return

    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    if target["id"] == msg.from_user.id:
        await msg.answer("❌ Нельзя переводить деньги самому себе.")
        return

    sender = await get_user(msg.from_user.id)
    short = bool(sender.get("short_numbers", 0)) if sender else False

    if sender and sender.get("confirm_pay", 0):
        text = (
            f"💸 <b>Подтверди перевод</b>\n\n"
            f"👤 Получатель: @{target['username']}\n"
            f"💰 Сумма: <b>{fmt_num(amount, short)}</b>\n"
            f"📊 Твой баланс: {fmt_num(sender['balance'], short)}"
        )
        await msg.answer(text, parse_mode="HTML", reply_markup=kb_pay_confirm(target["id"], amount))
    else:
        result = await transfer(msg.from_user.id, target["id"], amount)
        if result == "not_enough":
            await msg.answer("❌ Недостаточно средств.")
        else:
            await msg.answer(
                f"✅ Переведено <b>{fmt_num(amount, short)}</b> → @{target['username']}",
                parse_mode="HTML",
            )
            sender_name = msg.from_user.username or msg.from_user.first_name
            await notify_transfer(target, amount, sender_name)
            await create_event(target["id"], "transfer", amount, sender_name)


# --- Кнопки главного меню ---

@router.message(F.text == "👤 Профиль")
async def h_profile(msg: Message):
    user, _ = await get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or msg.from_user.first_name,
    )
    rank = await get_user_rank(msg.from_user.id)
    short = bool(user.get("short_numbers", 0))
    nick = f"@{user['username']}" if user["username"] else msg.from_user.first_name

    rank_str = "скрыт 👻" if user.get("hide_from_top") else f"#{rank}"
    is_admin = user.get("is_admin", 0) or user["id"] in SUPERADMIN_IDS
    admin_badge = "  👑 Администратор" if is_admin else ""

    lines = [
        f"👤 <b>Профиль</b> — {nick}{admin_badge}",
        "",
        f"🆔 ID: <code>{user['id']}</code>   📌 UID: <b>#{user['uid']}</b>",
        "",
        f"💰 Баланс: <b>{fmt_num(user['balance'], short)}</b>",
        f"🏆 Место в топе: {rank_str}   🎮 Игр: {user['games_played']}",
    ]

    if user.get("show_join_date", 1) and user.get("registered_at"):
        lines += ["", f"📅 С нами с {fmt_date(user['registered_at'])}"]

    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "🏆 Топ")
async def h_top(msg: Message):
    user = await get_user(msg.from_user.id)
    short = bool(user.get("short_numbers", 0)) if user else False
    users = await get_top(10)
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    lines = ["🏆 <b>Топ 10 игроков</b>\n"]
    for i, u in enumerate(users, 1):
        prefix = medals.get(i, f"<b>{i}.</b>")
        bal = fmt_num(u["balance"], short)
        lines.append(f"{prefix} @{u['username']} — {bal}")

    if user:
        rank = await get_user_rank(msg.from_user.id)
        hidden_note = "  👻 скрыт" if user.get("hide_from_top", 0) else ""
        lines.append(f"\n📍 Ваша позиция: <b>#{rank}</b>{hidden_note}")

    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "🎟 Ввод промокода")
async def h_promo_btn(msg: Message, state: FSMContext):
    await state.set_state(PromoState.waiting)
    sent = await msg.answer(
        "🎟 Введите промокод:",
        reply_markup=kb_promo_cancel(),
    )
    await state.update_data(msg_id=sent.message_id, chat_id=sent.chat.id)


@router.message(F.text == "⚙️ Настройки")
async def h_settings(msg: Message):
    user, _ = await get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or msg.from_user.first_name,
    )
    await msg.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "✅ — включено   ☑️ — выключено\n"
        "Нажми на кнопку, чтобы переключить:",
        parse_mode="HTML",
        reply_markup=kb_settings(user),
    )


# --- Подтверждение перевода ---

@router.callback_query(F.data.startswith("pay_confirm:"))
async def cb_pay_confirm(cb: CallbackQuery):
    parts = cb.data.split(":", 2)
    to_id = int(parts[1])
    amount = float(parts[2])

    target = await get_user(to_id)
    if not target:
        await cb.answer("Пользователь не найден", show_alert=True)
        await cb.message.delete()
        return

    sender = await get_user(cb.from_user.id)
    short = bool(sender.get("short_numbers", 0)) if sender else False

    result = await transfer(cb.from_user.id, to_id, amount)
    if result == "not_enough":
        await cb.message.edit_text("❌ Недостаточно средств для перевода.")
    else:
        await cb.message.edit_text(
            f"✅ Переведено <b>{fmt_num(amount, short)}</b> → @{target['username']}",
            parse_mode="HTML",
        )
        sender_name = cb.from_user.username or cb.from_user.first_name
        await notify_transfer(target, amount, sender_name)
        await create_event(target["id"], "transfer", amount, sender_name)
    await cb.answer()


@router.callback_query(F.data == "pay_cancel")
async def cb_pay_cancel(cb: CallbackQuery):
    await cb.message.edit_text("❌ Перевод отменён.")
    await cb.answer()


# --- Переключение настроек ---

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("toggle_"))
async def cb_toggle(cb: CallbackQuery):
    setting = cb.data[len("toggle_"):]
    if setting not in VALID_SETTINGS:
        await cb.answer()
        return

    await toggle_setting(cb.from_user.id, setting)
    user = await get_user(cb.from_user.id)

    await cb.message.edit_text(
        "⚙️ <b>Настройки</b>\n\n"
        "✅ — включено   ☑️ — выключено\n"
        "Нажми на кнопку, чтобы переключить:",
        parse_mode="HTML",
        reply_markup=kb_settings(user),
    )
    await cb.answer("Настройка изменена")


# --- Промокоды ---

@router.callback_query(F.data == "promo_cancel")
async def cb_promo_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Ввод промокода отменён.")
    await cb.answer()


@router.callback_query(F.data == "promo_retry")
async def cb_promo_retry(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting)
    await state.update_data(msg_id=cb.message.message_id, chat_id=cb.message.chat.id)
    await cb.message.edit_text("🎟 Введите промокод:", reply_markup=kb_promo_cancel())
    await cb.answer()


@router.message(PromoState.waiting)
async def h_promo_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    code = msg.text.strip()

    try:
        await msg.delete()
    except Exception:
        pass

    result, reward = await use_promo(code, msg.from_user.id)

    if result == "ok":
        await create_event(msg.from_user.id, "promo", reward)
        await state.clear()
        user = await get_user(msg.from_user.id)
        short = bool(user.get("short_numbers", 0)) if user else False
        bal_line = f"\n📊 Баланс: <b>{fmt_num(user['balance'], short)}</b>" if user else ""
        await bot.edit_message_text(
            f"✅ Промокод активирован!\n"
            f"💰 Начислено <b>{fmt_num(reward, short)}</b>{bal_line}",
            chat_id=data["chat_id"],
            message_id=data["msg_id"],
            parse_mode="HTML",
        )
        uname = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.first_name
        for admin_id in ADMIN_IDS:
            if admin_id != msg.from_user.id:
                try:
                    await bot.send_message(
                        admin_id,
                        f"🎟 Промокод <code>{code.upper()}</code> активирован\n"
                        f"👤 {uname}\n"
                        f"💰 Начислено: <b>{fmt_num(reward)}</b>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
    elif result == "already_used":
        await bot.edit_message_text(
            "❌ Вы уже использовали этот промокод.",
            chat_id=data["chat_id"],
            message_id=data["msg_id"],
            reply_markup=kb_promo_retry(),
        )
    else:
        await bot.edit_message_text(
            "❌ Неверный или недействительный промокод.",
            chat_id=data["chat_id"],
            message_id=data["msg_id"],
            reply_markup=kb_promo_retry(),
        )


# ===================== АДМИНСКИЕ КОМАНДЫ =====================

@router.message(Command("addbalance"))
async def h_addbalance(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if len(args) < 2:
        await msg.answer("❌ Использование: <code>/addbalance ID сумма</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    try:
        amount = float(args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Укажи корректную сумму (больше 0).")
        return
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await add_balance(target["id"], amount)
    updated = await get_user(target["id"])
    await msg.answer(
        f"✅ Начислено <b>{fmt_num(amount)}</b> → @{target['username']}\n"
        f"📊 Новый баланс: <b>{fmt_num(updated['balance'])}</b>",
        parse_mode="HTML",
    )
    await notify_give(target, amount)
    await create_event(target["id"], "give", amount)


@router.message(Command("removebalance"))
async def h_removebalance(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if len(args) < 2:
        await msg.answer("❌ Использование: <code>/removebalance ID сумма</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    try:
        amount = float(args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Укажи корректную сумму (больше 0).")
        return
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await subtract_balance(target["id"], amount)
    updated = await get_user(target["id"])
    await msg.answer(
        f"✅ Снято <b>{fmt_num(amount)}</b> ← @{target['username']}\n"
        f"📊 Новый баланс: <b>{fmt_num(updated['balance'])}</b>",
        parse_mode="HTML",
    )
    await notify_remove(target, amount)


@router.message(Command("setbalance"))
async def h_setbalance(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if len(args) < 2:
        await msg.answer("❌ Использование: <code>/setbalance ID сумма</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    try:
        amount = float(args[1])
        if amount < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Укажи корректную сумму (≥ 0).")
        return
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await set_balance_exact(target["id"], amount)
    await msg.answer(
        f"✅ Баланс @{target['username']} установлен: <b>{fmt_num(amount)}</b>",
        parse_mode="HTML",
    )
    await notify_set(target, amount)


@router.message(Command("reset"))
async def h_reset(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/reset ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await reset_user(target["id"])
    await msg.answer(
        f"✅ Прогресс @{target['username']} сброшен (баланс: 0₽, игры: 0).",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(target["id"], "🔄 Ваш прогресс был сброшен администратором.")
    except Exception:
        pass


@router.message(Command("reset_all"))
async def h_reset_all(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    await msg.answer(
        "⚠️ <b>Сброс всей базы</b>\n\n"
        "Это обнулит баланс и статистику <b>всех пользователей</b>.\n"
        "Действие необратимо. Продолжить?",
        parse_mode="HTML",
        reply_markup=kb_reset_all_confirm(),
    )


@router.callback_query(F.data == "admin_reset_all_confirm")
async def cb_reset_all_confirm(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    await reset_all()
    await cb.message.edit_text("✅ Готово. Все балансы и статистика обнулены.")
    await cb.answer()


@router.callback_query(F.data == "admin_reset_all_cancel")
async def cb_reset_all_cancel(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    await cb.message.edit_text("❌ Сброс отменён.")
    await cb.answer()


@router.message(Command("broadcast"))
async def h_broadcast(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    parts = msg.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await msg.answer("❌ Использование: <code>/broadcast сообщение</code>", parse_mode="HTML")
        return
    text = parts[1].strip()
    user_ids = await get_all_user_ids()
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(
                uid,
                f"📢 <b>Сообщение от администратора</b>\n\n{text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1
    await msg.answer(f"📢 Рассылка завершена\n✅ Отправлено: {sent}\n❌ Не доставлено: {failed}")


@router.message(Command("warn"))
async def h_warn(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    parts = msg.text.split(None, 2)
    if len(parts) < 3:
        await msg.answer("❌ Использование: <code>/warn ID причина</code>", parse_mode="HTML")
        return
    target = await resolve_target(parts[1])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    reason = parts[2]
    count = await add_warning(target["id"], reason)

    result_text = (
        f"⚠️ Предупреждение выдано @{target['username']}\n"
        f"📋 Причина: {reason}\n"
        f"🔢 Варнов: {count}/3"
    )
    if count >= 3:
        await ban_user(target["id"])
        result_text += "\n\n🚫 Пользователь заблокирован (3 варна)"

    await msg.answer(result_text)

    try:
        user_text = f"⚠️ Вы получили предупреждение\n📋 Причина: {reason}\n🔢 Варнов: {count}/3"
        if count >= 3:
            user_text += "\n\n🚫 Вы заблокированы в боте"
        await bot.send_message(target["id"], user_text)
    except Exception:
        pass


@router.message(Command("warnings"))
async def h_warnings(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/warnings ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    warns = await get_warnings(target["id"])
    if not warns:
        await msg.answer(f"✅ У @{target['username']} нет предупреждений.")
        return
    lines = [f"⚠️ Предупреждения @{target['username']} ({len(warns)}/3):\n"]
    for i, w in enumerate(warns, 1):
        date = w["created_at"][:10]
        lines.append(f"{i}. {w['reason']}  <i>({date})</i>")
    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("clearwarns"))
async def h_clearwarns(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/clearwarns ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await clear_warnings(target["id"])
    await msg.answer(f"✅ Варны @{target['username']} сняты.")


# --- Репорты (пользователь) ---

@router.message(Command("report"))
async def h_report(msg: Message, state: FSMContext):
    parts = msg.text.split(None, 1)
    if len(parts) > 1 and parts[1].strip():
        reason = parts[1].strip()
        uname = msg.from_user.username or msg.from_user.first_name
        report_id = await add_report(msg.from_user.id, uname, reason)
        await msg.answer(f"✅ Репорт <b>#{report_id}</b> отправлен. Мы рассмотрим его в ближайшее время.", parse_mode="HTML")
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📋 Новый репорт <b>#{report_id}</b>\n"
                    f"👤 От: @{uname} (<code>{msg.from_user.id}</code>)\n"
                    f"📝 {reason}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return

    await state.set_state(ReportState.waiting)
    sent = await msg.answer(
        "📋 Опишите причину обращения:",
        reply_markup=kb_report_cancel(),
    )
    await state.update_data(msg_id=sent.message_id, chat_id=sent.chat.id)


@router.callback_query(F.data == "report_cancel")
async def cb_report_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Репорт отменён.")
    await cb.answer()


@router.message(ReportState.waiting)
async def h_report_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    reason = msg.text.strip()

    try:
        await msg.delete()
    except Exception:
        pass

    uname = msg.from_user.username or msg.from_user.first_name
    report_id = await add_report(msg.from_user.id, uname, reason)
    await state.clear()

    await bot.edit_message_text(
        f"✅ Репорт <b>#{report_id}</b> отправлен. Мы рассмотрим его в ближайшее время.",
        chat_id=data["chat_id"],
        message_id=data["msg_id"],
        parse_mode="HTML",
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📋 Новый репорт <b>#{report_id}</b>\n"
                f"👤 От: @{uname} (<code>{msg.from_user.id}</code>)\n"
                f"📝 {reason}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# --- Репорты (админ) ---

async def _reports_text_and_kb():
    reports = await get_open_reports()
    if not reports:
        return "📋 <b>Открытых репортов нет.</b>", None
    text = f"📋 <b>Открытые репорты ({len(reports)})</b>\n\nНажми на репорт, чтобы открыть:"
    return text, kb_reports_list(reports)


@router.message(Command("reports"))
async def h_reports(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    text, kb = await _reports_text_and_kb()
    await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "reports_list")
async def cb_reports_list(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    text, kb = await _reports_text_and_kb()
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("report_view:"))
async def cb_report_view(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    report_id = int(cb.data.split(":")[1])
    r = await get_report(report_id)
    if not r:
        await cb.answer("Репорт не найден.", show_alert=True)
        return
    uname = f"@{r['username']}" if r["username"] else f"ID {r['user_id']}"
    date = r["created_at"][:10]
    status_str = "✅ Закрыт" if r["status"] == "closed" else "🔴 Открыт"
    text = (
        f"📋 <b>Репорт #{r['id']}</b>  {status_str}\n\n"
        f"👤 От: {uname} (<code>{r['user_id']}</code>)\n"
        f"📅 Дата: {fmt_date(date)}\n\n"
        f"📝 <b>Причина:</b>\n{r['reason']}"
    )
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb_report_detail(report_id))
    await cb.answer()


@router.callback_query(F.data.startswith("report_close:"))
async def cb_report_close(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    report_id = int(cb.data.split(":")[1])
    await close_report(report_id)
    text, kb = await _reports_text_and_kb()
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Репорт закрыт.")


@router.callback_query(F.data.startswith("report_del:"))
async def cb_report_del(cb: CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нет прав", show_alert=True)
        return
    report_id = int(cb.data.split(":")[1])
    await delete_report(report_id)
    text, kb = await _reports_text_and_kb()
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer("Репорт удалён.")


@router.message(Command("ban"))
async def h_ban(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/ban ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    if target["id"] in ADMIN_IDS:
        await msg.answer("❌ Нельзя заблокировать администратора.")
        return
    await ban_user(target["id"])
    uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
    await msg.answer(f"🚫 Пользователь {uname} заблокирован.")
    try:
        await bot.send_message(target["id"], "🚫 Вы были заблокированы в боте.")
    except Exception:
        pass


@router.message(Command("unban"))
async def h_unban(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/unban ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    await unban_user(target["id"])
    uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
    await msg.answer(f"✅ Пользователь {uname} разблокирован.")
    try:
        await bot.send_message(target["id"], "✅ Вы были разблокированы в боте.")
    except Exception:
        pass


@router.message(Command("addadmin"))
async def h_addadmin(msg: Message):
    if msg.from_user.id not in SUPERADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/addadmin ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    if target["id"] in ADMIN_IDS:
        uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
        await msg.answer(f"ℹ️ {uname} уже является администратором.")
        return
    await db_add_admin(target["id"])
    uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
    await msg.answer(f"✅ {uname} теперь администратор.")
    try:
        await bot.send_message(target["id"], "👑 Вам выданы права администратора.")
    except Exception:
        pass


@router.message(Command("deladmin"))
async def h_deladmin(msg: Message):
    if msg.from_user.id not in SUPERADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/deladmin ID</code>", parse_mode="HTML")
        return
    target = await resolve_target(args[0])
    if not target:
        await msg.answer("❌ Пользователь не найден.")
        return
    if target["id"] in SUPERADMIN_IDS:
        await msg.answer("❌ Нельзя убрать права суперадмина.")
        return
    if target["id"] not in ADMIN_IDS:
        uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
        await msg.answer(f"ℹ️ {uname} не является администратором.")
        return
    await db_remove_admin(target["id"])
    uname = f"@{target['username']}" if target["username"] else f"ID {target['id']}"
    await msg.answer(f"✅ Права администратора у {uname} сняты.")
    try:
        await bot.send_message(target["id"], "ℹ️ Ваши права администратора были сняты.")
    except Exception:
        pass


@router.message(Command("addpromo"))
async def h_addpromo(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if len(args) < 3:
        await msg.answer(
            "❌ Использование: <code>/addpromo КОД СУММА МАКС_ИСПОЛЬЗОВАНИЙ</code>\n"
            "<i>Пример: /addpromo SALE50 50 100</i>",
            parse_mode="HTML",
        )
        return
    code = args[0].upper()
    try:
        reward = float(args[1])
        max_uses = int(args[2])
        if reward <= 0 or max_uses <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Сумма и кол-во использований должны быть больше 0.")
        return
    ok = await create_promo(code, reward, max_uses)
    if not ok:
        await msg.answer(f"❌ Промокод <code>{code}</code> уже существует.", parse_mode="HTML")
        return
    await msg.answer(
        f"✅ Промокод создан\n\n"
        f"🎟 Код: <code>{code}</code>\n"
        f"💰 Награда: <b>{fmt_num(reward)}</b>\n"
        f"🔢 Использований: <b>{max_uses}</b>",
        parse_mode="HTML",
    )


@router.message(Command("delpromo"))
async def h_delpromo(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    args = msg.text.split()[1:]
    if not args:
        await msg.answer("❌ Использование: <code>/delpromo КОД</code>", parse_mode="HTML")
        return
    code = args[0].upper()
    ok = await remove_promo(code)
    if not ok:
        await msg.answer(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")
        return
    await msg.answer(f"✅ Промокод <code>{code}</code> удалён.", parse_mode="HTML")


@router.message(Command("promos", "listpromo"))
async def h_promos(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    promos = await get_all_promos()
    if not promos:
        await msg.answer("🎟 Промокодов нет.")
        return
    lines = ["🎟 <b>Промокоды</b>\n"]
    for p in promos:
        lines.append(
            f"<code>{p['code']}</code> — {fmt_num(p['reward'])} "
            f"[{p['uses_count']}/{p['max_uses']}]"
        )
    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("stats"))
async def h_stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("❌ У вас нет прав для этой команды.")
        return
    stats = await get_stats_data()
    users = stats["users"]
    lines = [
        "📊 <b>Статистика бота</b>\n",
        f"👥 Пользователей: <b>{len(users)}</b>",
        f"💸 Транзакций: <b>{stats['tx_count']}</b>",
        f"💰 Суммарный баланс: <b>{fmt_num(stats['total_balance'])}</b>\n",
        "<b>Пользователи:</b>",
    ]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "—"
        lines.append(f"<code>{u['id']}</code> — {uname}")

    text = "\n".join(lines)
    while len(text) > 4000:
        split_pos = text.rfind("\n", 0, 4000)
        await msg.answer(text[:split_pos], parse_mode="HTML")
        text = text[split_pos + 1:]
    await msg.answer(text, parse_mode="HTML")


# ===================== ЗАПУСК =====================

async def main():
    logging.basicConfig(level=logging.INFO)
    await db_init()
    await load_admins()
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.include_router(router)

    runner = aio_web.AppRunner(make_web_app())
    await runner.setup()
    await aio_web.TCPSite(runner, '0.0.0.0', WEB_PORT).start()
    logging.info("Web app: http://0.0.0.0:%d", WEB_PORT)

    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
        text="🎮 Играть",
        web_app=WebAppInfo(url=WEB_URL),
    ))
    logging.info("Menu button set to %s", WEB_URL)

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
