# YouTube Media Downloader

Um downloader para áudio e vídeo do YouTube usando Python e yt-dlp.

## Características

- Download de áudio em múltiplos formatos (MP3, OGG, WAV, etc.)
- Download de vídeo com controle de qualidade
- Suporte a playlists
- Progress bar com estatísticas
- Validação automática de formatos
- Interface de linha de comando

## Dependências

### Sistema
- Python 3.7+
- FFmpeg
- yt-dlp

### Instalação

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-pip ffmpeg
pip3 install yt-dlp

# macOS
brew install python3 ffmpeg
pip3 install yt-dlp

# Windows
# 1. Instalar Python do python.org
# 2. Baixar FFmpeg de ffmpeg.org e adicionar ao PATH
# 3. pip install yt-dlp
```

## Como Usar

### Uso Básico

```bash
# Download de áudio (MP3 padrão)
python3 youtube_media_downloader.py --url "https://www.youtube.com/watch?v=..."

# Especificar formato e qualidade
python3 youtube_media_downloader.py --url "URL" --format ogg --quality 320

# Download de vídeo
python3 youtube_media_downloader.py --url "URL" --video --format mp4 --quality 1080p

# Playlist
python3 youtube_media_downloader.py --url "https://www.youtube.com/playlist?list=..." --outfolder "./musicas"
```

### Argumentos

| Argumento | Padrão | Descrição |
|-----------|--------|-----------|
| `--url` | - | URL do vídeo ou playlist (obrigatório) |
| `--outfolder` | `downloads` | Pasta de destino |
| `--format` | `mp3` | Formato de saída |
| `--quality` | `192` | Bitrate (áudio) ou resolução (vídeo) |
| `--video` | `False` | Baixar vídeo completo |
| `--template` | `%(title)s - %(id)s.%(ext)s` | Template do nome |

## Formatos Suportados

### Áudio
- MP3, OGG, WAV, M4A, AAC, FLAC
- Qualidade: 64-320 kbps

### Vídeo  
- MP4, WEBM, MKV, AVI, MOV, FLV
- Qualidade: 360p, 480p, 720p, 1080p, 1440p, 2160p, "best", "worst"

## Exemplos

```bash
# Áudio alta qualidade
python3 youtube_media_downloader.py --url "URL" --format mp3 --quality 320

# Vídeo 4K
python3 youtube_media_downloader.py --url "URL" --video --quality best

# Playlist em OGG
python3 youtube_media_downloader.py --url "PLAYLIST_URL" --format ogg --outfolder "./musicas"

# Vídeo para mobile
python3 youtube_media_downloader.py --url "URL" --video --quality 480p
```

## Importação em Python

```python
from youtube_media_downloader import download_media

# Função simples
info = download_media(
    url="https://www.youtube.com/watch?v=...",
    outfolder="./downloads",
    fmt="mp3",
    quality=192
)

# Usando a classe
from youtube_media_downloader import YouTubeDownloader

downloader = YouTubeDownloader()
info = downloader.download_media(
    url="URL",
    fmt="ogg", 
    quality=320,
    is_video=False
)
downloader.print_summary()
```

## Solução de Problemas

### FFmpeg não encontrado
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS  
brew install ffmpeg

# Windows: baixar de ffmpeg.org e adicionar ao PATH
```

### yt-dlp não encontrado
```bash
pip3 install --upgrade yt-dlp
```

### Permissões (Linux/macOS)
```bash
chmod +x youtube_media_downloader.py
```

### Vídeo indisponível
- Verificar se o vídeo não é privado
- Alguns vídeos têm restrições geográficas
- Tentar com VPN se necessário
