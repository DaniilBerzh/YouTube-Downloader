import os
import sys
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import logging
import re
import subprocess
import shutil
import time
import random

# ========== АБСОЛЮТНО НАДЕЖНОЕ ОПРЕДЕЛЕНИЕ ПУТЕЙ ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# ПРОВЕРКА: выводим в логи информацию о путях
print("=" * 50)
print(f"🔍 БАЗОВАЯ ПАПКА: {BASE_DIR}")
print(f"🔍 ПАПКА TEMPLATES: {TEMPLATES_DIR}")
print(f"🔍 Папка templates существует: {os.path.exists(TEMPLATES_DIR)}")
print(f"🔍 Файл index.html существует: {os.path.exists(os.path.join(TEMPLATES_DIR, 'index.html'))}")
print(f"🔍 ПАПКА STATIC: {STATIC_DIR}")
print(f"🔍 Папка static существует: {os.path.exists(STATIC_DIR)}")
print("=" * 50)

# ========== СОЗДАНИЕ ПРИЛОЖЕНИЯ ==========
app = Flask(__name__,
            template_folder=TEMPLATES_DIR,
            static_folder=STATIC_DIR)
CORS(app)

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ========== ПАПКА ДЛЯ СКАЧИВАНИЯ ==========
DOWNLOAD_FOLDER = tempfile.mkdtemp()
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

# ========== ПРОВЕРКА FFMPEG ==========
FFMPEG_PATH = shutil.which('ffmpeg')
FFPROBE_PATH = shutil.which('ffprobe')
if FFMPEG_PATH:
    logger.info(f"✅ FFmpeg найден: {FFMPEG_PATH}")
else:
    logger.warning("❌ FFmpeg не найден! 1080p будет без звука")

# ========== ПУТЬ К COOKIES ==========
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
if os.path.exists(COOKIES_FILE):
    logger.info("🍪 Файл cookies.txt найден")
else:
    logger.warning("⚠️ Файл cookies.txt не найден")

# ========== USER-AGENT ДЛЯ РОТАЦИИ ==========
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# ========== ГЛАВНАЯ СТРАНИЦА ==========
@app.route('/')
def index():
    """Главная страница"""
    try:
        logger.info("Запрос главной страницы")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"❌ ОШИБКА РЕНДЕРИНГА: {str(e)}")
        return f"""
        <h1>Ошибка загрузки страницы</h1>
        <p>Текст ошибки: {str(e)}</p>
        <p>Путь к templates: {TEMPLATES_DIR}</p>
        <p>Папка существует: {os.path.exists(TEMPLATES_DIR)}</p>
        <p>Файл index.html существует: {os.path.exists(os.path.join(TEMPLATES_DIR, 'index.html'))}</p>
        <p>Содержимое папки: {os.listdir(BASE_DIR) if os.path.exists(BASE_DIR) else 'папка не найдена'}</p>
        """, 500

# ========== ПОЛУЧЕНИЕ ИНФОРМАЦИИ О ВИДЕО ==========
@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL не указан'})
        
        clean_url = re.sub(r'[&?]t=\d+s?', '', url)
        logger.info(f"Получен запрос для URL: {clean_url}")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'headers': {
                'User-Agent': random.choice(USER_AGENTS),
            }
        }
        
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE
            logger.info("🍪 Использую cookies")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            if not info:
                return jsonify({'success': False, 'error': 'Не удалось получить информацию'})
            
            formats = []
            for f in info.get('formats', []):
                height = f.get('height')
                if height and height in [1080, 720, 480, 360]:
                    filesize = f.get('filesize') or f.get('filesize_approx', 0)
                    has_audio = f.get('acodec') != 'none'
                    will_have_audio = has_audio or (FFMPEG_PATH and height == 1080)
                    
                    formats.append({
                        'resolution': f"{height}p",
                        'format_id': f.get('format_id'),
                        'filesize': filesize,
                        'ext': f.get('ext'),
                        'has_audio': has_audio,
                        'will_have_audio': will_have_audio
                    })
            
            formats.sort(key=lambda x: int(x['resolution'].replace('p', '')), reverse=True)
            
            duration = info.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}:{seconds:02d}"
            
            video_info = {
                'success': True,
                'data': {
                    'title': info.get('title', 'Без названия'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': duration_str,
                    'author': info.get('uploader', 'Неизвестный автор'),
                    'views': format_number(info.get('view_count', 0)),
                    'formats': formats,
                    'ffmpeg_available': FFMPEG_PATH is not None
                }
            }
            
            logger.info(f"✅ Найдено форматов: {len(formats)}")
            return jsonify(video_info)
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# ========== СКАЧИВАНИЕ ВИДЕО ==========
@app.route('/download_video', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id')
        
        if not url or not format_id:
            return jsonify({'success': False, 'error': 'Не все данные получены'})
        
        logger.info(f"▶️ Начинаю скачивание. Формат ID: {format_id}")
        
        clean_url = re.sub(r'[&?]t=\d+s?', '', url)
        download_dir = os.path.join(DOWNLOAD_FOLDER, str(int(time.time())))
        os.makedirs(download_dir, exist_ok=True)
        
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl_info:
            info_full = ydl_info.extract_info(clean_url, download=False)
            
            selected = None
            for f in info_full.get('formats', []):
                if f.get('format_id') == format_id:
                    selected = f
                    break
            
            if not selected:
                return jsonify({'success': False, 'error': 'Формат не найден'})
            
            height = selected.get('height', 720)
            has_audio = selected.get('acodec') != 'none'
            logger.info(f"Скачиваю: {height}p, аудио: {has_audio}")
        
        if FFMPEG_PATH and height == 1080 and not has_audio:
            format_string = 'bestvideo[height=1080][ext=mp4]+bestaudio[ext=m4a]/best[height=1080]'
            logger.info("🎵 Использую FFmpeg для добавления звука")
        else:
            format_string = format_id
        
        ydl_opts = {
            'format': format_string,
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
            'headers': {
                'User-Agent': random.choice(USER_AGENTS),
            }
        }
        
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE
            logger.info("🍪 Использую cookies")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            title = info.get('title', 'video')
            
            time.sleep(2)
            files = os.listdir(download_dir)
            video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.webm'))]
            
            if not video_files:
                return jsonify({'success': False, 'error': 'Файл не найден'})
            
            video_path = os.path.join(download_dir, video_files[0])
            file_size = os.path.getsize(video_path)
            file_size_mb = file_size / (1024 * 1024)
            
            if file_size < 1024 * 1024:
                return jsonify({'success': False, 'error': f'Файл слишком мал ({file_size_mb:.1f} MB)'})
            
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
            logger.info(f"✅ Успешно! Размер: {file_size_mb:.2f} MB")
            
            return send_file(
                video_path,
                as_attachment=True,
                download_name=f"{safe_title}.mp4",
                mimetype='video/mp4'
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# ========== ФОРМАТИРОВАНИЕ ЧИСЕЛ ==========
def format_number(num):
    if not num:
        return "0"
    if num > 1000000:
        return f"{num/1000000:.1f}M"
    elif num > 1000:
        return f"{num/1000:.1f}K"
    return str(num)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
