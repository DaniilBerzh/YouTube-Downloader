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

# ========== ПУТИ ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

print("=" * 50)
print(f"🔍 БАЗОВАЯ ПАПКА: {BASE_DIR}")
print(f"🔍 ПАПКА TEMPLATES: {TEMPLATES_DIR}")
print(f"🔍 Папка templates существует: {os.path.exists(TEMPLATES_DIR)}")
print(f"🔍 Файл index.html существует: {os.path.exists(os.path.join(TEMPLATES_DIR, 'index.html'))}")
print("=" * 50)

# ========== СОЗДАНИЕ ПРИЛОЖЕНИЯ ==========
app = Flask(__name__,
            template_folder=TEMPLATES_DIR,
            static_folder=STATIC_DIR)
CORS(app)

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ========== ПАПКА ДЛЯ СКАЧИВАНИЯ ==========
DOWNLOAD_FOLDER = tempfile.mkdtemp()
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# ========== ПРОВЕРКА FFMPEG ==========
FFMPEG_PATH = shutil.which('ffmpeg')
if FFMPEG_PATH:
    logger.info(f"✅ FFmpeg найден: {FFMPEG_PATH}")
else:
    logger.warning("❌ FFmpeg не найден!")

# ========== COOKIES ==========
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')
if os.path.exists(COOKIES_FILE):
    logger.info("🍪 Cookies найдены")
else:
    logger.warning("⚠️ Cookies не найдены")

# ========== USER-AGENT ==========
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
]

# ========== ГЛАВНАЯ ==========
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Ошибка: {e}", 500

# ========== ИНФО О ВИДЕО ==========
@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({'success': False, 'error': 'URL не указан'})

        clean_url = re.sub(r'[&?]t=\d+s?', '', url)
        
        ydl_opts = {'quiet': True, 'no_warnings': True}
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                height = f.get('height')
                if height and height in [1080, 720, 480, 360]:
                    formats.append({
                        'resolution': f"{height}p",
                        'format_id': f.get('format_id'),
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'has_audio': f.get('acodec') != 'none'
                    })

            formats.sort(key=lambda x: int(x['resolution'].replace('p', '')), reverse=True)
            
            duration = info.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60

            return jsonify({
                'success': True,
                'data': {
                    'title': info.get('title', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': f"{minutes}:{seconds:02d}",
                    'author': info.get('uploader', ''),
                    'views': str(info.get('view_count', 0)),
                    'formats': formats
                }
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== СКАЧИВАНИЕ ==========
@app.route('/download_video', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id')

        if not url:
            return jsonify({'success': False, 'error': 'URL не указан'})

        clean_url = re.sub(r'[&?]t=\d+s?', '', url)
        download_dir = os.path.join(DOWNLOAD_FOLDER, str(int(time.time())))
        os.makedirs(download_dir, exist_ok=True)

        # Получаем инфону о форматах
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_full = ydl.extract_info(clean_url, download=False)
            
            # Если формат не указан или не найден - берем лучший
            selected = None
            if format_id:
                for f in info_full.get('formats', []):
                    if f.get('format_id') == format_id:
                        selected = f
                        break
            
            if not selected:
                # Сортируем по качеству и берем лучший с аудио
                formats = sorted(info_full.get('formats', []), 
                               key=lambda x: x.get('height', 0) or 0, 
                               reverse=True)
                for f in formats:
                    if f.get('height') and f.get('acodec') != 'none':
                        selected = f
                        break
                if not selected and formats:
                    selected = formats[0]

            if not selected:
                return jsonify({'success': False, 'error': 'Нет форматов'})

            height = selected.get('height', 720)
            has_audio = selected.get('acodec') != 'none'
            format_id = selected.get('format_id')

        # Настройки скачивания
        if FFMPEG_PATH and not has_audio and height >= 720:
            format_string = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
        else:
            format_string = format_id

        ydl_opts = {
            'format': format_string,
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': False
        }

        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            title = info.get('title', 'video')
            
            time.sleep(2)
            files = os.listdir(download_dir)
            video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.webm'))]
            
            if not video_files:
                return jsonify({'success': False, 'error': 'Файл не найден'})

            video_path = os.path.join(download_dir, video_files[0])
            file_size = os.path.getsize(video_path) / (1024 * 1024)

            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
            
            return send_file(
                video_path,
                as_attachment=True,
                download_name=f"{safe_title}.mp4",
                mimetype='video/mp4'
            )

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
