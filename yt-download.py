"""
youtube_media_downloader_gui.py

Downloader de áudio e vídeo do YouTube com interface gráfica.
Utiliza yt-dlp e ffmpeg para processamento.

Autor: Versão melhorada com GUI
Data: 2024
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Union, Dict, Any
from datetime import datetime
import subprocess

# Verificar dependências
try:
    from yt_dlp import YoutubeDL
except ImportError:
    print("Instalando yt-dlp...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
    from yt_dlp import YoutubeDL


class RedirectText:
    """Classe para redirecionar stdout para o widget de texto."""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""

    def write(self, string):
        self.buffer += string
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update()

    def flush(self):
        pass


class YouTubeDownloaderGUI:
    """Classe principal da interface gráfica."""
    
    # Formatos suportados
    AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac']
    VIDEO_FORMATS = ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv']
    
    # Qualidades de vídeo comuns
    VIDEO_QUALITIES = ['best', '2160p (4K)', '1440p (2K)', '1080p (Full HD)', 
                       '720p (HD)', '480p', '360p', '240p', '144p', 'worst']
    
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader Pro")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        # Variáveis de controle
        self.download_type = tk.StringVar(value="audio")
        self.audio_format = tk.StringVar(value="mp3")
        self.video_format = tk.StringVar(value="mp4")
        self.audio_quality = tk.StringVar(value="192")
        self.video_quality = tk.StringVar(value="best")
        self.output_folder = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "YouTube"))
        self.filename_template = tk.StringVar(value="%(title)s - %(id)s")
        self.is_downloading = False
        self.download_thread = None
        
        # Estatísticas
        self.download_stats = {
            'total_files': 0,
            'completed': 0,
            'errors': 0,
            'current_file': ''
        }
        
        # Configurar estilo
        self.setup_styles()
        
        # Criar interface
        self.create_widgets()
        
        # Configurar atalhos
        self.setup_shortcuts()
        
        # Verificar ffmpeg
        self.check_ffmpeg()
    
    def setup_styles(self):
        """Configura estilos personalizados."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Cores
        self.bg_color = '#2b2b2b'
        self.fg_color = '#ffffff'
        self.accent_color = '#0078d4'
        self.success_color = '#28a745'
        self.error_color = '#dc3545'
        
        # Configurar cores da janela principal
        self.root.configure(bg=self.bg_color)
        
        # Estilos personalizados
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'), 
                       background=self.bg_color, foreground=self.fg_color)
        style.configure('Header.TLabel', font=('Segoe UI', 10, 'bold'),
                       background=self.bg_color, foreground=self.fg_color)
        style.configure('Status.TLabel', font=('Segoe UI', 9),
                       background=self.bg_color, foreground=self.fg_color)
        style.configure('Accent.TButton', font=('Segoe UI', 10, 'bold'))
    
    def create_widgets(self):
        """Cria todos os widgets da interface."""
        
        # Frame principal com scroll
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas para scroll
        canvas = tk.Canvas(main_container, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Título
        title_label = ttk.Label(scrollable_frame, text="🎥 YouTube Downloader Pro", 
                                style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Frame para URL
        url_frame = ttk.LabelFrame(scrollable_frame, text="URL do Vídeo/Playlist", 
                                   padding=10)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.url_entry = ttk.Entry(url_frame, font=('Segoe UI', 10))
        self.url_entry.pack(fill=tk.X, pady=(0, 5))
        self.url_entry.bind('<Return>', lambda e: self.start_download())
        
        # Botões de ação rápida
        action_frame = ttk.Frame(url_frame)
        action_frame.pack(fill=tk.X)
        
        ttk.Button(action_frame, text="Colar URL", 
                  command=self.paste_url).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(action_frame, text="Limpar", 
                  command=lambda: self.url_entry.delete(0, tk.END)).pack(side=tk.LEFT)
        
        # Frame para tipo de download
        type_frame = ttk.LabelFrame(scrollable_frame, text="Tipo de Download", 
                                    padding=10)
        type_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Radiobutton(type_frame, text="🎵 Áudio", variable=self.download_type, 
                       value="audio", command=self.update_format_options).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(type_frame, text="🎬 Vídeo", variable=self.download_type, 
                       value="video", command=self.update_format_options).pack(side=tk.LEFT, padx=10)
        
        # Frame para formato e qualidade
        format_frame = ttk.LabelFrame(scrollable_frame, text="Formato e Qualidade", 
                                      padding=10)
        format_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Formato
        format_inner = ttk.Frame(format_frame)
        format_inner.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(format_inner, text="Formato:", style='Header.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        self.format_combo = ttk.Combobox(format_inner, textvariable=self.audio_format, 
                                         values=self.AUDIO_FORMATS, state='readonly', width=10)
        self.format_combo.pack(side=tk.LEFT)
        
        # Qualidade
        quality_inner = ttk.Frame(format_frame)
        quality_inner.pack(fill=tk.X)
        
        ttk.Label(quality_inner, text="Qualidade:", style='Header.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        self.quality_combo = ttk.Combobox(quality_inner, textvariable=self.audio_quality, 
                                          width=15)
        self.quality_combo.pack(side=tk.LEFT)
        
        # Frame para destino
        dest_frame = ttk.LabelFrame(scrollable_frame, text="Pasta de Destino", 
                                    padding=10)
        dest_frame.pack(fill=tk.X, pady=(0, 10))
        
        dest_inner = ttk.Frame(dest_frame)
        dest_inner.pack(fill=tk.X)
        
        self.dest_entry = ttk.Entry(dest_inner, textvariable=self.output_folder)
        self.dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(dest_inner, text="📁 Procurar", 
                  command=self.browse_folder).pack(side=tk.RIGHT)
        
        # Template de nome
        template_frame = ttk.LabelFrame(scrollable_frame, text="Template do Nome do Arquivo", 
                                        padding=10)
        template_frame.pack(fill=tk.X, pady=(0, 10))
        
        template_inner = ttk.Frame(template_frame)
        template_inner.pack(fill=tk.X)
        
        template_entry = ttk.Entry(template_inner, textvariable=self.filename_template)
        template_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(template_inner, text="Ajuda", 
                  command=self.show_template_help).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Frame de progresso
        progress_frame = ttk.LabelFrame(scrollable_frame, text="Progresso", 
                                        padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Barra de progresso
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        # Labels de status
        self.status_label = ttk.Label(progress_frame, text="Pronto para download", 
                                      style='Status.TLabel')
        self.status_label.pack()
        
        self.file_status_label = ttk.Label(progress_frame, text="", 
                                           style='Status.TLabel', wraplength=800)
        self.file_status_label.pack()
        
        # Frame de botões de controle
        control_frame = ttk.Frame(scrollable_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.download_btn = ttk.Button(control_frame, text="🚀 Iniciar Download", 
                                       command=self.start_download, style='Accent.TButton')
        self.download_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.cancel_btn = ttk.Button(control_frame, text="⏹️ Cancelar", 
                                     command=self.cancel_download, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT)
        
        # Frame de log
        log_frame = ttk.LabelFrame(scrollable_frame, text="Log de Download", 
                                   padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Widget de texto para log com scroll
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_text_frame, 
            height=15,
            bg='#1e1e1e',
            fg='#d4d4d4',
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configurar tags de cores para o log
        self.log_text.tag_config('error', foreground='#f48771')
        self.log_text.tag_config('success', foreground='#6a9955')
        self.log_text.tag_config('info', foreground='#9cdcfe')
        self.log_text.tag_config('warning', foreground='#ce9178')
        
        # Frame de estatísticas
        stats_frame = ttk.LabelFrame(scrollable_frame, text="Estatísticas", 
                                     padding=10)
        stats_frame.pack(fill=tk.X, pady=(10, 0))
        
        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack()
        
        self.stats_labels = {}
        stats_items = [
            ('total', 'Total:', '0'),
            ('completed', 'Concluídos:', '0'),
            ('errors', 'Erros:', '0'),
            ('success', 'Sucesso:', '0%')
        ]
        
        for i, (key, label, value) in enumerate(stats_items):
            ttk.Label(stats_inner, text=label).grid(row=i//2, column=(i%2)*2, 
                                                    padx=(0, 5), pady=2, sticky='w')
            self.stats_labels[key] = ttk.Label(stats_inner, text=value)
            self.stats_labels[key].grid(row=i//2, column=(i%2)*2 + 1, 
                                        padx=(0, 20), pady=2, sticky='w')
        
        # Redirecionar stdout para o log
        self.redirect = RedirectText(self.log_text)
        sys.stdout = self.redirect
        
        # Atualizar opções iniciais
        self.update_format_options()
    
    def setup_shortcuts(self):
        """Configura atalhos de teclado."""
        self.root.bind('<Control-v>', lambda e: self.paste_url())
        self.root.bind('<Control-o>', lambda e: self.browse_folder())
        self.root.bind('<F1>', lambda e: self.show_help())
    
    def update_format_options(self):
        """Atualiza as opções de formato baseado no tipo de download."""
        if self.download_type.get() == 'audio':
            self.format_combo['values'] = self.AUDIO_FORMATS
            self.format_combo.set(self.audio_format.get())
            self.quality_combo['values'] = ['64', '96', '128', '160', '192', '256', '320']
            self.quality_combo.set(self.audio_quality.get())
        else:
            self.format_combo['values'] = self.VIDEO_FORMATS
            self.format_combo.set(self.video_format.get())
            self.quality_combo['values'] = self.VIDEO_QUALITIES
            self.quality_combo.set(self.video_quality.get())
    
    def paste_url(self):
        """Cola a URL da área de transferência."""
        try:
            url = self.root.clipboard_get()
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, url)
        except:
            pass
    
    def browse_folder(self):
        """Abre diálogo para selecionar pasta de destino."""
        folder = filedialog.askdirectory(
            title="Selecione a pasta de destino",
            initialdir=self.output_folder.get()
        )
        if folder:
            self.output_folder.set(folder)
    
    def show_template_help(self):
        """Mostra ajuda sobre o template de nomes."""
        help_text = """
        📝 Template do Nome do Arquivo
        
        Variáveis disponíveis:
        %(title)s - Título do vídeo
        %(id)s - ID do vídeo
        %(uploader)s - Nome do canal
        %(upload_date)s - Data de upload (YYYYMMDD)
        %(duration)s - Duração em segundos
        %(view_count)s - Número de visualizações
        %(ext)s - Extensão do arquivo
        
        Exemplos:
        %(title)s - %(id)s.%(ext)s
        %(uploader)s - %(title)s.%(ext)s
        %(upload_date)s - %(title)s.%(ext)s
        
        Observação: A extensão será adicionada automaticamente.
        """
        messagebox.showinfo("Ajuda - Template", help_text)
    
    def show_help(self):
        """Mostra ajuda geral do programa."""
        help_text = """
        🆘 Ajuda do YouTube Downloader Pro
        
        Como usar:
        1. Cole a URL do vídeo ou playlist
        2. Escolha o tipo (Áudio ou Vídeo)
        3. Selecione formato e qualidade
        4. Escolha a pasta de destino
        5. Clique em "Iniciar Download"
        
        Formatos suportados:
        • Áudio: MP3, WAV, OGG, M4A, AAC, FLAC
        • Vídeo: MP4, WEBM, MKV, AVI, MOV, FLV
        
        Qualidades de vídeo:
        • best: Melhor qualidade disponível
        • worst: Pior qualidade disponível
        • Resoluções: 2160p até 144p
        
        Atalhos:
        • Ctrl+V: Colar URL
        • Ctrl+O: Abrir pasta
        • F1: Esta ajuda
        """
        messagebox.showinfo("Ajuda", help_text)
    
    def check_ffmpeg(self):
        """Verifica se o ffmpeg está instalado."""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            self.log_message("✅ ffmpeg encontrado", 'success')
        except:
            self.log_message("⚠️ ffmpeg não encontrado. Algumas conversões podem falhar.", 'warning')
            self.log_message("   Instale o ffmpeg: https://ffmpeg.org/download.html", 'info')
    
    def log_message(self, message, tag=None):
        """Adiciona mensagem ao log com formatação."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}\n"
        
        if tag:
            self.log_text.insert(tk.END, formatted_msg, tag)
        else:
            self.log_text.insert(tk.END, formatted_msg)
        
        self.log_text.see(tk.END)
        self.root.update()
    
    def update_stats(self):
        """Atualiza as estatísticas na interface."""
        self.stats_labels['total'].config(text=str(self.download_stats['total_files']))
        self.stats_labels['completed'].config(text=str(self.download_stats['completed']))
        self.stats_labels['errors'].config(text=str(self.download_stats['errors']))
        
        if self.download_stats['total_files'] > 0:
            success_rate = (self.download_stats['completed'] / self.download_stats['total_files']) * 100
            self.stats_labels['success'].config(text=f"{success_rate:.1f}%")
    
    def progress_hook(self, d: Dict[str, Any]) -> None:
        """Hook para mostrar progresso do download na GUI."""
        if not self.is_downloading:
            return
        
        status = d.get('status')
        filename = os.path.basename(d.get('filename', 'Arquivo desconhecido'))
        
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            
            self.download_stats['current_file'] = filename
            
            if total:
                pct = (downloaded / total) * 100
                total_mb = total / (1024 * 1024)
                downloaded_mb = downloaded / (1024 * 1024)
                
                # Atualizar barra de progresso
                self.progress_bar['value'] = pct
                
                # Atualizar status
                status_text = f"📥 Baixando: {downloaded_mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%)"
                self.status_label.config(text=status_text)
                self.file_status_label.config(text=f"Arquivo: {filename[:80]}...")
            else:
                downloaded_mb = downloaded / (1024 * 1024)
                self.progress_bar['value'] = 0
                self.status_label.config(text=f"📥 Baixando: {downloaded_mb:.1f} MB")
                self.file_status_label.config(text=f"Arquivo: {filename[:80]}...")
                
        elif status == 'finished':
            self.log_message(f"✅ Download concluído: {filename}", 'success')
            self.progress_bar['value'] = 100
            self.status_label.config(text="⚙️ Convertendo arquivo...")
            
        elif status == 'error':
            self.log_message(f"❌ Erro no download: {filename}", 'error')
            self.download_stats['errors'] += 1
            self.update_stats()
    
    def start_download(self):
        """Inicia o download em uma thread separada."""
        url = self.url_entry.get().strip()
        
        if not url:
            messagebox.showwarning("Aviso", "Por favor, insira uma URL do YouTube.")
            return
        
        if self.is_downloading:
            messagebox.showwarning("Aviso", "Download já em andamento.")
            return
        
        # Criar pasta de destino
        try:
            os.makedirs(self.output_folder.get(), exist_ok=True)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível criar a pasta:\n{str(e)}")
            return
        
        # Preparar parâmetros
        is_video = self.download_type.get() == 'video'
        fmt = self.video_format.get() if is_video else self.audio_format.get()
        quality = self.video_quality.get() if is_video else self.audio_quality.get()
        
        # Converter qualidade para inteiro se for áudio
        if not is_video and quality.isdigit():
            quality = int(quality)
        
        # Atualizar interface
        self.is_downloading = True
        self.download_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        
        # Limpar estatísticas anteriores
        self.download_stats = {
            'total_files': 0,
            'completed': 0,
            'errors': 0,
            'current_file': ''
        }
        self.update_stats()
        
        self.log_message("="*50, 'info')
        self.log_message(f"🎯 Iniciando download de {'vídeo' if is_video else 'áudio'}", 'info')
        self.log_message(f"📁 Pasta: {self.output_folder.get()}", 'info')
        self.log_message(f"🎵 Formato: {fmt}", 'info')
        self.log_message(f"⚙️ Qualidade: {quality}", 'info')
        self.log_message("="*50, 'info')
        
        # Iniciar thread de download
        self.download_thread = threading.Thread(
            target=self.download_media,
            args=(url, self.output_folder.get(), fmt, quality, is_video,
                  f"{self.filename_template.get()}.%(ext)s")
        )
        self.download_thread.daemon = True
        self.download_thread.start()
        
        # Verificar conclusão
        self.check_download_thread()
    
    def download_media(self, url: str, outfolder: str, fmt: str, quality: Union[str, int],
                      is_video: bool, filename_template: str):
        """Executa o download (executado em thread separada)."""
        try:
            # Configurar opções do yt-dlp
            ydl_opts = {
                'outtmpl': os.path.join(outfolder, filename_template),
                'noplaylist': False,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'progress_hooks': [self.progress_hook],
            }
            
            if is_video:
                # Configurações para vídeo
                if quality == 'best':
                    ydl_opts['format'] = 'bestvideo+bestaudio/best'
                elif quality == 'worst':
                    ydl_opts['format'] = 'worstvideo+worstaudio/worst'
                else:
                    # Extrair resolução (ex: '1080p (Full HD)' -> 1080)
                    quality_num = quality.split('p')[0]
                    if quality_num.isdigit():
                        ydl_opts['format'] = f'bestvideo[height<={quality_num}]+bestaudio/best[height<={quality_num}]'
                    else:
                        ydl_opts['format'] = 'bestvideo+bestaudio/best'
                
                if fmt != 'mp4':
                    ydl_opts['merge_output_format'] = fmt
            else:
                # Configurações para áudio
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': fmt,
                    'preferredquality': str(quality) if fmt in ['mp3', 'aac', 'ogg'] else None
                }]
            
            # Realizar download
            with YoutubeDL(ydl_opts) as ydl:
                # Primeiro, extrair informações para contar arquivos
                info = ydl.extract_info(url, download=False)
                
                if info and 'entries' in info:
                    self.download_stats['total_files'] = len([e for e in info['entries'] if e])
                    self.log_message(f"📋 Playlist detectada: {self.download_stats['total_files']} arquivos", 'info')
                else:
                    self.download_stats['total_files'] = 1
                    self.log_message("📋 Vídeo único detectado", 'info')
                
                self.root.after(0, self.update_stats)
                
                # Realizar download
                ydl.extract_info(url, download=True)
                
                self.download_stats['completed'] = self.download_stats['total_files'] - self.download_stats['errors']
                
        except Exception as e:
            self.log_message(f"❌ Erro durante o download: {str(e)}", 'error')
            self.download_stats['errors'] += 1
        
        finally:
            self.is_downloading = False
            self.root.after(0, self.download_finished)
    
    def check_download_thread(self):
        """Verifica se a thread de download terminou."""
        if self.download_thread and self.download_thread.is_alive():
            self.root.after(100, self.check_download_thread)
        else:
            self.download_finished()
    
    def download_finished(self):
        """Callback quando o download termina."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_bar['value'] = 100
        
        self.update_stats()
        
        self.log_message("="*50, 'info')
        self.log_message("✅ Download finalizado!", 'success')
        self.log_message(f"📊 Resumo: {self.download_stats['completed']} concluídos, "
                        f"{self.download_stats['errors']} erros", 'info')
        self.log_message("="*50, 'info')
        
        self.status_label.config(text="Download concluído!")
        self.file_status_label.config(text="")
        
        # Perguntar se quer abrir a pasta
        if messagebox.askyesno("Concluído", "Download finalizado!\nDeseja abrir a pasta de destino?"):
            self.open_output_folder()
    
    def cancel_download(self):
        """Cancela o download em andamento."""
        if self.is_downloading:
            self.is_downloading = False
            self.log_message("⏸️ Download cancelado pelo usuário", 'warning')
            self.status_label.config(text="Download cancelado")
            self.download_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
    
    def open_output_folder(self):
        """Abre a pasta de destino no explorador de arquivos."""
        folder = self.output_folder.get()
        if os.path.exists(folder):
            if sys.platform == 'win32':
                os.startfile(folder)
            elif sys.platform == 'darwin':
                subprocess.run(['open', folder])
            else:
                subprocess.run(['xdg-open', folder])
    
    def on_closing(self):
        """Callback quando a janela é fechada."""
        if self.is_downloading:
            if messagebox.askyesno("Confirmar", "Download em andamento. Deseja realmente sair?"):
                self.is_downloading = False
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """Função principal."""
    root = tk.Tk()
    app = YouTubeDownloaderGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()