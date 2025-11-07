import logging
import os
import asyncio
import random
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp
import requests
import sqlite3

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY', 'YOUR_LASTFM_API_KEY')
LASTFM_API_URL = 'http://ws.audioscrobbler.com/2.0/'

# Реклама
ADS = [
    "🎵 Реклама: Попробуй наш партнёрский бот @CoolMusicBot!",
    "🎧 Реклама: Открой для себя новую музыку с @MusicDiscoveryBot!",
    "🎸 Реклама: Лучшие плейлисты только в @TopPlaylistsBot!",
    "🎹 Реклама: Скачивай музыку быстрее с @FastMusicBot!",
]


class Database:
    def __init__(self, db_file='users.db'):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                mode TEXT DEFAULT 'basic',
                interaction_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                track_name TEXT,
                artist TEXT,
                downloaded_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS preferences (
                user_id INTEGER PRIMARY KEY,
                favorite_genres TEXT,
                favorite_artists TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        conn.commit()
        conn.close()

    def get_user(self, user_id: int):
        """Получить пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    def create_user(self, user_id: int, username: str):
        """Создать пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, username, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def update_mode(self, user_id: int, mode: str):
        """Обновить режим пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET mode = ? WHERE user_id = ?', (mode, user_id))
        conn.commit()
        conn.close()

    def increment_interaction(self, user_id: int) -> int:
        """Увеличить счетчик взаимодействий"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET interaction_count = interaction_count + 1
            WHERE user_id = ?
        ''', (user_id,))
        cursor.execute('SELECT interaction_count FROM users WHERE user_id = ?', (user_id,))
        count = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return count

    def add_download(self, user_id: int, track_name: str, artist: str):
        """Добавить скачанный трек"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO downloads (user_id, track_name, artist, downloaded_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, track_name, artist, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_user_downloads(self, user_id: int, limit: int = 10):
        """Получить историю скачиваний пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT track_name, artist, downloaded_at
            FROM downloads
            WHERE user_id = ?
            ORDER BY downloaded_at DESC
            LIMIT ?
        ''', (user_id, limit))
        downloads = cursor.fetchall()
        conn.close()
        return downloads


class MusicService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_track(self, query: str, limit: int = 5):
        """Поиск треков через Last.fm API"""
        try:
            params = {
                'method': 'track.search',
                'track': query,
                'api_key': self.api_key,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            data = response.json()

            if 'results' in data and 'trackmatches' in data['results']:
                tracks = data['results']['trackmatches'].get('track', [])
                return tracks if isinstance(tracks, list) else [tracks]
            return []
        except Exception as e:
            logger.error(f"Error searching track: {e}")
            return []

    def get_similar_tracks(self, artist: str, track: str, limit: int = 10):
        """Получить похожие треки"""
        try:
            params = {
                'method': 'track.getsimilar',
                'artist': artist,
                'track': track,
                'api_key': self.api_key,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            data = response.json()

            if 'similartracks' in data and 'track' in data['similartracks']:
                return data['similartracks']['track']
            return []
        except Exception as e:
            logger.error(f"Error getting similar tracks: {e}")
            return []

    def get_top_tracks(self, limit: int = 10):
        """Получить топовые треки"""
        try:
            params = {
                'method': 'chart.gettoptracks',
                'api_key': self.api_key,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            data = response.json()

            if 'tracks' in data and 'track' in data['tracks']:
                return data['tracks']['track']
            return []
        except Exception as e:
            logger.error(f"Error getting top tracks: {e}")
            return []

    def get_artist_top_tracks(self, artist: str, limit: int = 10):
        """Получить топ треков артиста"""
        try:
            params = {
                'method': 'artist.gettoptracks',
                'artist': artist,
                'api_key': self.api_key,
                'format': 'json',
                'limit': limit
            }
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            data = response.json()

            if 'toptracks' in data and 'track' in data['toptracks']:
                return data['toptracks']['track']
            return []
        except Exception as e:
            logger.error(f"Error getting artist top tracks: {e}")
            return []


class MusicDownloader:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '/tmp/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }

    async def download_track(self, query: str) -> Optional[dict]:
        """Скачать трек с YouTube"""
        try:
            search_query = f"ytsearch1:{query}"

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=True)

                if 'entries' in info:
                    video = info['entries'][0]
                else:
                    video = info

                file_path = ydl.prepare_filename(video)
                file_path = file_path.rsplit('.', 1)[0] + '.mp3'

                return {
                    'file_path': file_path,
                    'title': video.get('title', 'Unknown'),
                    'duration': video.get('duration', 0),
                }
        except Exception as e:
            logger.error(f"Error downloading track: {e}")
            return None


# Инициализация
db = Database()
music_service = MusicService(LASTFM_API_KEY)
downloader = MusicDownloader()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    db.create_user(user.id, user.username or user.first_name)

    keyboard = [
        [InlineKeyboardButton("🎵 Базовый режим", callback_data='mode_basic')],
        [InlineKeyboardButton("🎧 Расширенный режим", callback_data='mode_advanced')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🎵 Добро пожаловать в MelodyForge — твой персональный музыкальный бот!\n\n"
        "📱 Выбери режим работы:\n"
        "• Базовый режим — быстрый поиск и скачивание музыки\n"
        "• Расширенный режим — рекомендации, плейлисты и миксы\n\n"
        "🎧 Просто отправь мне название трека или артиста!"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data.startswith('mode_'):
        mode = data.split('_')[1]
        db.update_mode(user_id, mode)

        if mode == 'basic':
            text = "✅ Активирован базовый режим!\n\n🔍 Отправь название трека для поиска."
        else:
            text = (
                "✅ Активирован расширенный режим!\n\n"
                "🎵 Доступные команды:\n"
                "• Отправь название трека — получишь рекомендации\n"
                "• /top — топ треков\n"
                "• /history — твоя история\n"
                "• /mix — создать микс на основе твоих предпочтений"
            )

        await query.edit_message_text(text)

    elif data.startswith('download_'):
        track_data = data.replace('download_', '')
        artist, track = track_data.split('|||')

        await query.edit_message_text(f"⏳ Скачиваю: {artist} - {track}...")

        result = await downloader.download_track(f"{artist} {track}")

        if result:
            try:
                with open(result['file_path'], 'rb') as audio:
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=audio,
                        title=track,
                        performer=artist,
                        duration=result['duration']
                    )

                db.add_download(user_id, track, artist)

                # Удаляем временный файл
                os.remove(result['file_path'])

                # Проверка рекламы
                count = db.increment_interaction(user_id)
                if count % 10 == 0:
                    ad = random.choice(ADS)
                    await context.bot.send_message(chat_id=query.message.chat_id, text=ad)

                await query.edit_message_text(f"✅ Готово: {artist} - {track}")
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                await query.edit_message_text("❌ Ошибка при отправке файла. Попробуй другой трек.")
        else:
            await query.edit_message_text("❌ Не удалось скачать трек. Попробуй другой запрос.")

    elif data.startswith('similar_'):
        track_data = data.replace('similar_', '')
        artist, track = track_data.split('|||')

        await query.edit_message_text(f"🔍 Ищу похожие треки на: {artist} - {track}...")

        similar = music_service.get_similar_tracks(artist, track, limit=5)

        if similar:
            text = f"🎵 Похожие треки на {artist} - {track}:\n\n"
            keyboard = []

            for i, t in enumerate(similar[:5], 1):
                track_name = t.get('name', 'Unknown')
                track_artist = t.get('artist', {}).get('name', 'Unknown')
                text += f"{i}. {track_artist} - {track_name}\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"⬇️ {track_artist} - {track_name}",
                        callback_data=f"download_{track_artist}|||{track_name}"
                    )
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await query.edit_message_text("❌ Не удалось найти похожие треки.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    query = update.message.text

    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, update.effective_user.username or update.effective_user.first_name)
        user = db.get_user(user_id)

    mode = user[2] if user else 'basic'

    await update.message.reply_text(f"🔍 Ищу: {query}...")

    tracks = music_service.search_track(query, limit=5)

    if not tracks:
        await update.message.reply_text("❌ Ничего не найдено. Попробуй другой запрос.")
        return

    if mode == 'basic':
        # Базовый режим: список для скачивания
        text = f"🎵 Найдено по запросу '{query}':\n\n"
        keyboard = []

        for i, track in enumerate(tracks[:5], 1):
            artist = track.get('artist', 'Unknown')
            name = track.get('name', 'Unknown')
            text += f"{i}. {artist} - {name}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {artist} - {name}",
                    callback_data=f"download_{artist}|||{name}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)

    else:
        # Расширенный режим: рекомендации
        text = f"🎧 Результаты по запросу '{query}':\n\n"
        keyboard = []

        for i, track in enumerate(tracks[:3], 1):
            artist = track.get('artist', 'Unknown')
            name = track.get('name', 'Unknown')
            text += f"{i}. {artist} - {name}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ Скачать",
                    callback_data=f"download_{artist}|||{name}"
                ),
                InlineKeyboardButton(
                    f"🎵 Похожие",
                    callback_data=f"similar_{artist}|||{name}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /top"""
    await update.message.reply_text("🔝 Загружаю топ треков...")

    tracks = music_service.get_top_tracks(limit=10)

    if tracks:
        text = "🔥 Топ-10 треков сейчас:\n\n"
        keyboard = []

        for i, track in enumerate(tracks, 1):
            artist = track.get('artist', {}).get('name', 'Unknown')
            name = track.get('name', 'Unknown')
            text += f"{i}. {artist} - {name}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {artist} - {name}",
                    callback_data=f"download_{artist}|||{name}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Не удалось загрузить топ треков.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /history"""
    user_id = update.effective_user.id
    downloads = db.get_user_downloads(user_id, limit=10)

    if downloads:
        text = "📜 Твоя история скачиваний:\n\n"
        for i, (track, artist, date) in enumerate(downloads, 1):
            text += f"{i}. {artist} - {track}\n"
        await update.message.reply_text(text)
    else:
        await update.message.reply_text("📭 История пуста. Скачай первый трек!")


async def mix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mix"""
    user_id = update.effective_user.id
    downloads = db.get_user_downloads(user_id, limit=5)

    if not downloads:
        await update.message.reply_text("🎵 Скачай несколько треков, чтобы я создал для тебя микс!")
        return

    await update.message.reply_text("🎧 Создаю микс на основе твоих предпочтений...")

    # Берем случайный трек из истории
    random_track = random.choice(downloads)
    track_name, artist_name, _ = random_track

    # Получаем похожие треки
    similar = music_service.get_similar_tracks(artist_name, track_name, limit=10)

    if similar:
        text = f"🎵 Твой персональный микс (на основе {artist_name} - {track_name}):\n\n"
        keyboard = []

        for i, track in enumerate(similar[:10], 1):
            artist = track.get('artist', {}).get('name', 'Unknown')
            name = track.get('name', 'Unknown')
            text += f"{i}. {artist} - {name}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⬇️ {artist} - {name}",
                    callback_data=f"download_{artist}|||{name}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Не удалось создать микс. Попробуй позже.")


def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("mix", mix_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск
    logger.info("🎵 MelodyForge запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
