"""
youtube_media_downloader.py

Script unificado para download de audio e video do YouTube usando yt-dlp.

Exemplos de uso:
    # Para audio
    python youtube_media_downloader.py --url "https://www.youtube.com/watch?v=..." --outfolder "./musicas" --format mp3 --quality 192
    python youtube_media_downloader.py --url "https://www.youtube.com/playlist?list=..." --format ogg --quality 320
    
    # Para video
    python youtube_media_downloader.py --url "https://www.youtube.com/watch?v=..." --outfolder "./videos" --video --format mp4 --quality 1080p
    python youtube_media_downloader.py --url "https://www.youtube.com/playlist?list=..." --video --quality best

Tambem pode ser importado em outros scripts:
    from youtube_media_downloader import download_media
    download_media(url, outfolder, fmt, quality, is_video)
"""

import os
import sys
import argparse
from typing import Optional, Union, Dict, Any
from yt_dlp import YoutubeDL

class YouTubeDownloader:
    """Classe para gerenciar downloads do YouTube com yt-dlp."""
    
    # Formatos suportados
    AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac']
    VIDEO_FORMATS = ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv']
    
    def __init__(self):
        self.download_stats = {
            'total_files': 0,
            'completed': 0,
            'errors': 0
        }

    def validate_format(self, fmt: str, is_video: bool) -> str:
        """Valida e corrige o formato solicitado."""
        fmt = fmt.lower()
        
        if is_video:
            if fmt not in self.VIDEO_FORMATS:
                print(f"Formato de video '{fmt}' não suportado. Usando mp4 como padrão.")
                return 'mp4'
        else:
            if fmt not in self.AUDIO_FORMATS:
                print(f"Formato de audio '{fmt}' não suportado. Usando mp3 como padrão.")
                return 'mp3'
        
        return fmt

    def validate_quality(self, quality: Union[str, int], is_video: bool) -> Union[str, int]:
        """Valida e padroniza a qualidade."""
        if is_video:
            if isinstance(quality, str):
                # Remove 'p' se presente e valida resoluçoes comuns
                quality_clean = quality.replace('p', '').lower()
                if quality_clean == 'best' or quality_clean == 'worst':
                    return quality_clean
                elif quality_clean.isdigit():
                    return f"{quality_clean}p"
                else:
                    print(f"Qualidade de video '{quality}' invalida. Usando 'best' como padrão.")
                    return 'best'
            return str(quality)
        else:
            # Para audio, converter para inteiro se possivel
            if isinstance(quality, str) and quality.isdigit():
                quality = int(quality)
            if isinstance(quality, int):
                # Limitar bitrate a valores razoaveis
                if quality < 64:
                    quality = 64
                elif quality > 320:
                    quality = 320
                return quality
            else:
                print(f"Qualidade de audio '{quality}' invalida. Usando 192 kbps como padrão.")
                return 192

    def get_ydl_options(self, outfolder: str, fmt: str, quality: Union[str, int], 
                       is_video: bool, filename_template: str) -> Dict[str, Any]:
        """Constrói as opçoes para o yt-dlp baseado nos parâmetros."""
        
        ydl_opts = {
            'outtmpl': os.path.join(outfolder, filename_template),
            'noplaylist': False,
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
            'progress_hooks': [self.progress_hook],
            'restrictfilenames': False,
            'writeinfojson': False,  # Não salvar metadados JSON
            'writedescription': False,
            'writesubtitles': False,
        }

        if is_video:
            # Configuraçoes para video
            if quality == 'best':
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
            elif quality == 'worst':
                ydl_opts['format'] = 'worstvideo+worstaudio/worst'
            else:
                # Extrair numero da qualidade (ex: '1080p' -> 1080)
                quality_num = quality.replace('p', '') if 'p' in quality else quality
                ydl_opts['format'] = f'bestvideo[height<={quality_num}]+bestaudio/best[height<={quality_num}]'
            
            # Forçar merge para o formato desejado se necessario
            if fmt != 'mp4':  # mp4 e o formato padrao do merge
                ydl_opts['merge_output_format'] = fmt
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': fmt
                }]
        else:
            # Configuraçoes para audio apenas
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': fmt,
                'preferredquality': str(quality) if fmt in ['mp3', 'aac', 'ogg'] else None
            }]

        return ydl_opts

    def progress_hook(self, d: Dict[str, Any]) -> None:
        """Hook para mostrar progresso do download."""
        status = d.get('status')
        filename = os.path.basename(d.get('filename', 'Arquivo desconhecido'))
        
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            
            if total:
                pct = (downloaded / total) * 100
                total_mb = total / (1024 * 1024)
                downloaded_mb = downloaded / (1024 * 1024)
                print(f" {filename[:50]}... — {pct:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='\r')
            else:
                downloaded_mb = downloaded / (1024 * 1024)
                print(f" {filename[:50]}... — {downloaded_mb:.1f} MB baixados", end='\r')
                
        elif status == 'finished':
            print(f"\nDownload concluido: {filename}")
            if 'postprocessor' not in d:  # Evita contar duas vezes
                print("Convertendo arquivo...")
            self.download_stats['completed'] += 1
            
        elif status == 'error':
            print(f"\n Erro no download: {filename}")
            print(f"   Detalhes: {d}")
            self.download_stats['errors'] += 1

    def download_media(self, url: str, outfolder: str = 'downloads', fmt: str = 'mp3', 
                      quality: Union[str, int] = 192, is_video: bool = False,
                      filename_template: str = '%(title)s - %(id)s.%(ext)s') -> Optional[Dict[str, Any]]:
        """
        Baixa audio ou video de um video ou playlist do YouTube.
        
        Args:
            url: URL do video ou playlist do YouTube
            outfolder: Pasta de destino
            fmt: Formato de saida (audio: mp3,ogg,wav,m4a,aac,flac; video: mp4,webm,mkv,avi,mov,flv)
            quality: Para audio: bitrate em kbps; Para video: resolução (360p,720p,1080p) ou 'best'/'worst'
            is_video: Se True, baixa video; se False, baixa apenas audio
            filename_template: Template de nome do arquivo
            
        Returns:
            Informaçoes extraidas pelo yt-dlp ou None em caso de erro
        """
        
        # Validaçoes
        fmt = self.validate_format(fmt, is_video)
        quality = self.validate_quality(quality, is_video)
        
        # Criar diretório de saida
        os.makedirs(outfolder, exist_ok=True)
        
        # Configurar opçoes do yt-dlp
        ydl_opts = self.get_ydl_options(outfolder, fmt, quality, is_video, filename_template)
        
        print(f"Iniciando download {'de video' if is_video else 'de audio'}...")
        print(f"Pasta de destino: {outfolder}")
        print(f"Formato: {fmt}")
        print(f"Qualidade: {quality}{'p' if is_video and isinstance(quality, int) else (' kbps' if not is_video else '')}")
        print(f"URL: {url}\n")
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                # Extrair informaçoes primeiro para contar arquivos
                info = ydl.extract_info(url, download=False)
                
                if 'entries' in info:  # e uma playlist
                    self.download_stats['total_files'] = len([e for e in info['entries'] if e])
                    print(f" Playlist detectada: {self.download_stats['total_files']} arquivos\n")
                else:  # e um video único
                    self.download_stats['total_files'] = 1
                    print(f" Video único detectado\n")
                
                # Realizar o download
                info = ydl.extract_info(url, download=True)
                
                return info
                
        except Exception as e:
            print(f"\n Erro durante o download: {str(e)}")
            self.download_stats['errors'] += 1
            return None

    def print_summary(self) -> None:
        """Imprime resumo dos downloads."""
        print(f"\n{'='*50}")
        print(" RESUMO DOS DOWNLOADS")
        print(f"{'='*50}")
        print(f" Total de arquivos: {self.download_stats['total_files']}")
        print(f" Concluidos: {self.download_stats['completed']}")
        print(f" Erros: {self.download_stats['errors']}")
        
        if self.download_stats['total_files'] > 0:
            success_rate = (self.download_stats['completed'] / self.download_stats['total_files']) * 100
            print(f" Taxa de sucesso: {success_rate:.1f}%")
        
        print(f"{'='*50}\n")


def download_media(url: str, outfolder: str = 'downloads', fmt: str = 'mp3', 
                  quality: Union[str, int] = 192, is_video: bool = False,
                  filename_template: str = '%(title)s - %(id)s.%(ext)s') -> Optional[Dict[str, Any]]:
    """
    Função standalone para download (compatibilidade com importação).
    """
    downloader = YouTubeDownloader()
    return downloader.download_media(url, outfolder, fmt, quality, is_video, filename_template)


def main():
    """Função principal para uso via linha de comando."""
    parser = argparse.ArgumentParser(
        description=" Baixador de audio e video do YouTube usando yt-dlp + ffmpeg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  # Baixar audio MP3 de um video
  python youtube_media_downloader.py --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --format mp3 --quality 192
  
  # Baixar playlist completa em OGG
  python youtube_media_downloader.py --url "https://www.youtube.com/playlist?list=..." --format ogg --quality 320
  
  # Baixar video em MP4 1080p
  python youtube_media_downloader.py --url "https://www.youtube.com/watch?v=..." --video --format mp4 --quality 1080p
  
  # Baixar video na melhor qualidade disponivel
  python youtube_media_downloader.py --url "https://www.youtube.com/watch?v=..." --video --quality best

Formatos suportados:
  audio: mp3, ogg, wav, m4a, aac, flac
  Video: mp4, webm, mkv, avi, mov, flv
        """
    )
    
    parser.add_argument('--url', required=True, 
                       help='URL do video ou playlist do YouTube')
    parser.add_argument('--outfolder', default='downloads', 
                       help='Pasta de destino (padrão: downloads)')
    parser.add_argument('--format', default='mp3', 
                       help='Formato de saida (padrão: mp3)')
    parser.add_argument('--quality', default='192', 
                       help='Para audio: bitrate em kbps (64-320). Para video: resolução (360p,720p,1080p) ou "best"/"worst" (padrão: 192)')
    parser.add_argument('--video', action='store_true', 
                       help='Baixar video completo em vez de apenas audio')
    parser.add_argument('--template', default='%(title)s - %(id)s.%(ext)s', 
                       help='Template de nome do arquivo (padrão: "%(title)s - %(id)s.%(ext)s")')
    
    args = parser.parse_args()
    
    # Converter quality para inteiro se for audio e numerico
    quality_param = args.quality
    if not args.video and args.quality.isdigit():
        quality_param = int(args.quality)
    
    # Criar instância do downloader
    downloader = YouTubeDownloader()
    
    # Realizar download
    info = downloader.download_media(
        url=args.url,
        outfolder=args.outfolder,
        fmt=args.format,
        quality=quality_param,
        is_video=args.video,
        filename_template=args.template
    )
    
    # Mostrar resumo
    downloader.print_summary()
    
    if info:
        print(" Download finalizado com sucesso!")
        return 0
    else:
        print(" Download falhou!")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Download interrompido pelo usuario.")
        sys.exit(130)
    except Exception as e:
        print(f"\n Erro inesperado: {str(e)}")
        sys.exit(1)