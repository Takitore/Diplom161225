import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class BookingStates(StatesGroup):
    choosing_film = State()
    choosing_time = State()
    choosing_seats = State()
    confirming_booking = State()

# Инициализация базы данных
async def init_db():
    async with aiosqlite.connect('cinema.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS films (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                duration INTEGER,
                genre TEXT,
                rating REAL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                film_id INTEGER,
                date_time DATETIME,
                hall INTEGER,
                price REAL,
                FOREIGN KEY (film_id) REFERENCES films (id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_id INTEGER,
                seats TEXT,
                booking_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        await db.commit()

# Генерация тестовых данных
async def generate_test_data():
    async with aiosqlite.connect('cinema.db') as db:
        # Проверяем, есть ли уже фильмы
        cursor = await db.execute("SELECT COUNT(*) FROM films")
        count = await cursor.fetchone()
        
        if count[0] == 0:
            # Добавляем фильмы
            films = [
                ('Интерстеллар', 'Фантастический эпос о путешествиях сквозь червоточины', 169, 'фантастика, драма', 8.6),
                ('Крестный отец', 'Эпическая история сицилийской мафиозной семьи', 175, 'криминал, драма', 9.2),
                ('Побег из Шоушенка', 'История невиновного банкира в тюрьме', 142, 'драма', 9.3),
                ('Форрест Гамп', 'Жизнь человека с низким IQ, который стал свидетелем ключевых событий XX века', 142, 'драма, комедия', 8.8),
                ('Начало', 'Проникновение в сны для совершения идеального преступления', 148, 'боевик, фантастика', 8.8)
            ]
            
            for film in films:
                await db.execute(
                    "INSERT INTO films (title, description, duration, genre, rating) VALUES (?, ?, ?, ?, ?)",
                    film
                )
            
            # Добавляем сеансы на ближайшие дни
            for i in range(1, 6):
                for hour in [10, 14, 18, 22]:
                    date_time = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=i)
                    await db.execute(
                        "INSERT INTO sessions (film_id, date_time, hall, price) VALUES (?, ?, ?, ?)",
                        (i, date_time.isoformat(), 1, 300 + i*50)
                    )
            
            await db.commit()

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Сегодня в кино", callback_data="today_films")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="🎟️ Бронирование", callback_data="booking")],
        [InlineKeyboardButton(text="ℹ️ О кинотеатре", callback_data="about")],
        [InlineKeyboardButton(text="📞 Контакты", callback_data="contacts")]
    ])
    
    await message.answer(
        "🎥 Добро пожаловать в наш кинотеатр!\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=keyboard
    )

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🎬 *Команды бота:*\n\n"
        "*/start* - Главное меню\n"
        "*/help* - Справка по командам\n"
        "*/films* - Все фильмы\n"
        "*/today* - Сеансы на сегодня\n"
        "*/booking* - Начать бронирование\n\n"
        "Или используйте кнопки меню!"
    )
    await message.answer(help_text, parse_mode="Markdown")

# Сеансы на сегодня
@dp.callback_query(lambda c: c.data == "today_films")
async def today_films(callback: types.CallbackQuery):
    today = datetime.now().date()
    
    async with aiosqlite.connect('cinema.db') as db:
        cursor = await db.execute('''
            SELECT f.title, s.date_time, s.hall, s.price 
            FROM sessions s
            JOIN films f ON s.film_id = f.id
            WHERE DATE(s.date_time) = ?
            ORDER BY s.date_time
        ''', (today.isoformat(),))
        
        sessions = await cursor.fetchall()
    
    if not sessions:
        await callback.message.answer("На сегодня сеансов нет 😔")
        return
    
    response = f"🎬 *Сеансы на сегодня ({today.strftime('%d.%m.%Y')}):*\n\n"
    
    for session in sessions:
        title, date_time, hall, price = session
        dt = datetime.fromisoformat(date_time)
        response += f"*{title}*\n"
        response += f"⏰ {dt.strftime('%H:%M')} | 📍 Зал {hall} | 💰 {price} руб.\n"
        response += "─" * 30 + "\n"
    
    await callback.message.answer(response, parse_mode="Markdown")

# Все фильмы
@dp.message(Command("films"))
async def all_films(message: types.Message):
    async with aiosqlite.connect('cinema.db') as db:
        cursor = await db.execute("SELECT id, title, description, duration, genre, rating FROM films")
        films = await cursor.fetchall()
    
    response = "🎥 *Все фильмы в прокате:*\n\n"
    
    for film in films:
        id, title, description, duration, genre, rating = film
        response += f"*{title}*\n"
        response += f"⭐ Рейтинг: {rating}/10\n"
        response += f"⏱️ Длительность: {duration} мин.\n"
        response += f"🎭 Жанр: {genre}\n"
        response += f"📝 {description[:100]}...\n"
        
        # Кнопка для просмотра сеансов
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📅 Сеансы", callback_data=f"film_sessions_{id}")
        ]])
        
        await message.answer(response, parse_mode="Markdown", reply_markup=keyboard)
        response = ""

        # Сеансы для конкретного фильма
@dp.callback_query(lambda c: c.data.startswith("film_sessions_"))
async def film_sessions(callback: types.CallbackQuery):
    film_id = int(callback.data.split("_")[2])
    
    async with aiosqlite.connect('cinema.db') as db:
        # Получаем информацию о фильме
        cursor = await db.execute("SELECT title FROM films WHERE id = ?", (film_id,))
        film = await cursor.fetchone()
        
        # Получаем сеансы на 3 дня вперед
        date_from = datetime.now()
        date_to = date_from + timedelta(days=3)
        
        cursor = await db.execute('''
            SELECT s.id, s.date_time, s.hall, s.price
            FROM sessions s
            WHERE s.film_id = ? AND s.date_time BETWEEN ? AND ?
            ORDER BY s.date_time
        ''', (film_id, date_from.isoformat(), date_to.isoformat()))
        
        sessions = await cursor.fetchall()
    
    if not sessions:
        await callback.message.answer(f"На ближайшие 3 дня сеансов для фильма '{film[0]}' нет.")
        return
    
    response = f"🎬 *Сеансы для фильма '{film[0]}':*\n\n"
    
    for session in sessions:
        session_id, date_time, hall, price = session
        dt = datetime.fromisoformat(date_time)
        response += f"📅 *{dt.strftime('%d.%m.%Y %H:%M')}*\n"
        response += f"📍 Зал: {hall} | 💰 {price} руб.\n"