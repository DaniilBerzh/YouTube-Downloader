// Функция получения информации о видео
async function getVideoInfo() {
    const urlInput = document.getElementById('video-url');
    const url = urlInput.value.trim();
    const button = document.getElementById('get-video-btn');
    
    console.log('URL видео:', url);
    
    if (!url) {
        showError('Введите ссылку на YouTube видео');
        return;
    }
    
    if (!isValidYouTubeUrl(url)) {
        showError('Некорректная ссылка на YouTube');
        return;
    }
    
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Загрузка...';
    
    showLoading();
    hideError();
    hideVideoInfo();
    
    try {
        const response = await fetch('/get_video_info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        console.log('Ответ от сервера:', data);
        
        if (data.success) {
            displayVideoInfo(data.data);
        } else {
            showError(data.error || 'Ошибка получения информации');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError('Ошибка соединения с сервером');
    } finally {
        button.disabled = false;
        button.innerHTML = '<span>Продолжить</span><i class="fas fa-arrow-right"></i>';
        hideLoading();
    }
}

// Проверка YouTube ссылки
function isValidYouTubeUrl(url) {
    const patterns = [
        /^(https?:\/\/)?(www\.)?youtube\.com\/watch\?v=[\w-]+/,
        /^(https?:\/\/)?(www\.)?youtu\.be\/[\w-]+/,
        /^(https?:\/\/)?(www\.)?youtube\.com\/shorts\/[\w-]+/
    ];
    return patterns.some(pattern => pattern.test(url));
}

// Отображение информации о видео
function displayVideoInfo(info) {
    console.log('Отображаем информацию:', info);
    
    document.getElementById('video-title').textContent = info.title || 'Без названия';
    document.getElementById('video-author').textContent = info.author || 'Неизвестный автор';
    document.getElementById('video-views').textContent = info.views || '0';
    document.getElementById('video-duration').textContent = info.duration || '0:00';
    document.getElementById('video-thumbnail').src = info.thumbnail || '';
    
    const qualityDiv = document.getElementById('quality-buttons');
    qualityDiv.innerHTML = '';
    
    if (!info.formats || info.formats.length === 0) {
        qualityDiv.innerHTML = '<p style="color: #fff; text-align: center;">Нет доступных форматов</p>';
        showVideoInfo();
        return;
    }
    
    if (info.ffmpeg_available) {
        const status = document.createElement('p');
        status.style.color = '#44ff44';
        status.style.marginBottom = '15px';
        status.style.textAlign = 'center';
        status.style.fontWeight = 'bold';
        status.innerHTML = '✅ FFmpeg установлен - 1080p будет с аудио';
        qualityDiv.appendChild(status);
    } else {
        const status = document.createElement('p');
        status.style.color = '#ff4444';
        status.style.marginBottom = '15px';
        status.style.textAlign = 'center';
        status.style.fontWeight = 'bold';
        status.innerHTML = '❌ FFmpeg не найден - 1080p будет без звука';
        qualityDiv.appendChild(status);
    }
    
    info.formats.forEach(format => {
        const btn = document.createElement('button');
        btn.className = 'quality-btn';
        
        let sizeText = '';
        if (format.filesize && format.filesize > 0) {
            const sizeMB = format.filesize / (1024 * 1024);
            sizeText = ` (${sizeMB.toFixed(2)} MB)`;
        }
        
        const audioIcon = format.will_have_audio ? '🔊' : '🔇';
        btn.innerHTML = `${audioIcon} ${format.resolution}${sizeText}`;
        
        btn.style.background = format.will_have_audio ? 
            'linear-gradient(135deg, #44ff44, #00aa00)' : 
            'linear-gradient(135deg, #ff4444, #aa0000)';
        
        btn.onclick = () => downloadVideo(format.format_id);
        qualityDiv.appendChild(btn);
    });
    
    showVideoInfo();
}

// Скачивание видео
async function downloadVideo(formatId) {
    const url = document.getElementById('video-url').value.trim();
    
    showLoading();
    
    try {
        console.log('Отправляем запрос на скачивание...');
        
        const response = await fetch('/download_video', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                url: url,
                format_id: formatId
            })
        });
        
        if (response.ok) {
            const contentDisposition = response.headers.get('content-disposition');
            let filename = 'video.mp4';
            if (contentDisposition) {
                const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (match && match[1]) {
                    filename = match[1].replace(/['"]/g, '');
                }
            }
            
            const blob = await response.blob();
            const fileSizeMB = (blob.size / (1024 * 1024)).toFixed(1);
            
            console.log(`Размер файла: ${fileSizeMB} MB`);
            
            if (blob.size < 512 * 1024) {
                showError(`Файл слишком маленький (${fileSizeMB} MB). YouTube блокирует скачивание.`);
                hideLoading();
                return;
            }
            
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
            
            showSuccess(`✅ Видео скачано! Размер: ${fileSizeMB} MB`);
        } else {
            const error = await response.json();
            showError(error.error || 'Ошибка при скачивании');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError('Ошибка при скачивании видео');
    } finally {
        hideLoading();
    }
}

function showSuccess(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    errorDiv.style.background = 'rgba(0, 255, 0, 0.1)';
    errorDiv.style.border = '1px solid rgba(0, 255, 0, 0.3)';
    errorDiv.style.color = '#4caf50';
    errorDiv.classList.remove('hidden');
    
    setTimeout(() => {
        errorDiv.classList.add('hidden');
    }, 3000);
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
    errorDiv.style.background = 'rgba(255, 0, 0, 0.1)';
    errorDiv.style.border = '1px solid rgba(255, 0, 0, 0.3)';
    errorDiv.style.color = '#ff6b6b';
    errorDiv.classList.remove('hidden');
}

function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showVideoInfo() {
    document.getElementById('video-info').classList.remove('hidden');
}

function hideVideoInfo() {
    document.getElementById('video-info').classList.add('hidden');
}

function hideError() {
    document.getElementById('error-message').classList.add('hidden');
}

// Инициализация
document.addEventListener('DOMContentLoaded', function() {
    console.log('Страница загружена');
    
    const urlInput = document.getElementById('video-url');
    const button = document.getElementById('get-video-btn');
    
    if (urlInput) {
        urlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') getVideoInfo();
        });
        
        urlInput.addEventListener('paste', function() {
            setTimeout(getVideoInfo, 100);
        });
    }
    
    if (button) {
        button.addEventListener('click', getVideoInfo);
    }
});