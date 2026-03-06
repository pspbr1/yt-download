"""
youtube_downloader_pro.py

Downloader de áudio e vídeo do YouTube com interface gráfica aprimorada.
Utiliza yt-dlp e ffmpeg para processamento.

Melhorias v2:
- Progresso detalhado com velocidade, ETA e tamanho
- Histórico de downloads com sessão persistente
- Mini player de preview de metadados
- Fila de downloads múltiplos
- Cores e tema modernos via ttk customizado
- Melhor tratamento de erros e cancelamento real
- Separação clara de responsabilidades (MVC leve)
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional, Union, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import subprocess
import queue

# ──────────────────────────────────────────────
# Dependências externas
# ──────────────────────────────────────────────
try:
    from yt_dlp import YoutubeDL
except ImportError:
    print("Instalando yt-dlp...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
    from yt_dlp import YoutubeDL


# ──────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────
AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac']
VIDEO_FORMATS = ['mp4', 'webm', 'mkv', 'avi', 'mov', 'flv']
VIDEO_QUALITIES = [
    'best', '2160p (4K)', '1440p (2K)', '1080p (Full HD)',
    '720p (HD)', '480p', '360p', '240p', '144p', 'worst'
]
AUDIO_BITRATES = ['64', '96', '128', '160', '192', '256', '320']

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")

# Paleta de cores
COLORS = {
    'bg':          '#0f0f13',
    'surface':     '#1a1a24',
    'surface2':    '#22222f',
    'border':      '#2e2e42',
    'accent':      '#6c63ff',
    'accent_dim':  '#4a44cc',
    'success':     '#3dd68c',
    'error':       '#ff5c5c',
    'warning':     '#f5a623',
    'text':        '#e8e8f0',
    'text_dim':    '#8888aa',
    'progress_bg': '#1e1e2e',
    'progress_fg': '#6c63ff',
}


# ──────────────────────────────────────────────
# Modelos de dados
# ──────────────────────────────────────────────
@dataclass
class DownloadStats:
    total_files: int = 0
    completed: int = 0
    errors: int = 0
    current_file: str = ''
    start_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.completed / self.total_files) * 100

    @property
    def elapsed(self) -> str:
        if self.start_time is None:
            return '—'
        secs = int(time.time() - self.start_time)
        return str(timedelta(seconds=secs))


@dataclass
class DownloadRecord:
    title: str
    url: str
    fmt: str
    status: str          # 'ok' | 'error' | 'cancelled'
    timestamp: str = field(default_factory=lambda: datetime.now().strftime('%H:%M:%S'))
    size_mb: float = 0.0


# ──────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────
def fmt_bytes(n: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_speed(bps: float) -> str:
    return f"{fmt_bytes(bps)}/s"


def fmt_eta(secs: Optional[float]) -> str:
    if secs is None or secs <= 0:
        return '—'
    return str(timedelta(seconds=int(secs)))


def extract_quality_number(quality_str: str) -> Optional[str]:
    """Extrai número de resolução de string como '1080p (Full HD)'."""
    part = quality_str.split('p')[0]
    return part if part.isdigit() else None


def build_ydl_opts(
    outfolder: str,
    filename_template: str,
    is_video: bool,
    fmt: str,
    quality: Union[str, int],
    progress_hook,
) -> Dict[str, Any]:
    """Monta dicionário de opções para YoutubeDL."""
    template = os.path.join(outfolder, filename_template)

    opts: Dict[str, Any] = {
        'outtmpl': template,
        'noplaylist': False,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'progress_hooks': [progress_hook],
        'noprogress': False,
    }

    if is_video:
        qual_num = extract_quality_number(str(quality))
        if quality == 'best':
            opts['format'] = 'bestvideo+bestaudio/best'
        elif quality == 'worst':
            opts['format'] = 'worstvideo+worstaudio/worst'
        elif qual_num:
            opts['format'] = (
                f'bestvideo[height<={qual_num}]+bestaudio'
                f'/best[height<={qual_num}]'
            )
        else:
            opts['format'] = 'bestvideo+bestaudio/best'

        if fmt != 'mp4':
            opts['merge_output_format'] = fmt
    else:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': fmt,
            'preferredquality': str(quality) if fmt in ('mp3', 'aac', 'ogg') else None,
        }]

    return opts


# ──────────────────────────────────────────────
# Motor de download (sem UI)
# ──────────────────────────────────────────────
class DownloadEngine:
    """Executa downloads em thread separada e comunica via callbacks."""

    def __init__(self):
        self._cancel_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # Callbacks (atribuídos externamente)
    on_progress: Optional[callable] = None
    on_log: Optional[callable] = None
    on_finished: Optional[callable] = None

    # ── Controle ──────────────────────────────
    def start(self, url: str, outfolder: str, fmt: str,
              quality: Union[str, int], is_video: bool,
              filename_template: str):
        if self._thread and self._thread.is_alive():
            return
        self._cancel_flag.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(url, outfolder, fmt, quality, is_video, filename_template),
            daemon=True,
        )
        self._thread.start()

    def cancel(self):
        self._cancel_flag.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Execução ──────────────────────────────
    def _run(self, url, outfolder, fmt, quality, is_video, filename_template):
        self._emit_log("Preparando download…", 'info')
        stats = DownloadStats(start_time=time.time())

        try:
            ydl_opts = build_ydl_opts(
                outfolder, filename_template, is_video, fmt, quality,
                self._make_progress_hook(stats),
            )

            with YoutubeDL(ydl_opts) as ydl:
                # Fase 1 — extrair informações
                self._emit_log("Obtendo informações do vídeo/playlist…", 'info')
                info = ydl.extract_info(url, download=False)

                if self._cancel_flag.is_set():
                    self._finish(stats, cancelled=True)
                    return

                if info and 'entries' in info:
                    entries = [e for e in info['entries'] if e]
                    stats.total_files = len(entries)
                    title = info.get('title', 'Playlist')
                    self._emit_log(
                        f"Playlist: "{title}" — {stats.total_files} arquivos", 'info'
                    )
                else:
                    stats.total_files = 1
                    title = info.get('title', url) if info else url
                    self._emit_log(f"Vídeo: "{title}"", 'info')

                if self.on_progress:
                    self.on_progress({'_meta': True, 'stats': stats})

                # Fase 2 — download
                ydl.extract_info(url, download=True)

                stats.completed = stats.total_files - stats.errors

        except Exception as exc:
            self._emit_log(f"Erro inesperado: {exc}", 'error')
            stats.errors += 1
        finally:
            self._finish(stats)

    def _make_progress_hook(self, stats: DownloadStats):
        def hook(d: Dict[str, Any]):
            if self._cancel_flag.is_set():
                raise Exception("Download cancelado pelo usuário.")

            status = d.get('status')
            filename = os.path.basename(d.get('filename', ''))

            if status == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                speed = d.get('speed')
                eta = d.get('eta')
                pct = (downloaded / total * 100) if total else None

                payload = {
                    'status': 'downloading',
                    'filename': filename,
                    'downloaded': downloaded,
                    'total': total,
                    'pct': pct,
                    'speed': speed,
                    'eta': eta,
                    'stats': stats,
                }
                if self.on_progress:
                    self.on_progress(payload)

            elif status == 'finished':
                size_mb = d.get('downloaded_bytes', 0) / (1024 * 1024)
                self._emit_log(
                    f"✔ Concluído: {filename}  ({size_mb:.1f} MB)", 'success'
                )
                stats.completed += 1
                if self.on_progress:
                    self.on_progress({'status': 'finished', 'stats': stats,
                                     'filename': filename, 'size_mb': size_mb})

            elif status == 'error':
                self._emit_log(f"✘ Erro: {filename}", 'error')
                stats.errors += 1
                if self.on_progress:
                    self.on_progress({'status': 'error', 'stats': stats})

        return hook

    def _emit_log(self, msg: str, tag: str = ''):
        if self.on_log:
            self.on_log(msg, tag)

    def _finish(self, stats: DownloadStats, cancelled: bool = False):
        if cancelled:
            self._emit_log("Download cancelado.", 'warning')
        if self.on_finished:
            self.on_finished(stats, cancelled)


# ──────────────────────────────────────────────
# Widgets customizados
# ──────────────────────────────────────────────
class RoundedProgressBar(tk.Canvas):
    """Barra de progresso customizada com degradê e bordas arredondadas."""

    def __init__(self, master, height=22, **kw):
        super().__init__(master, height=height, highlightthickness=0,
                         bg=COLORS['bg'], **kw)
        self._pct = 0.0
        self._height = height
        self.bind('<Configure>', lambda e: self._draw())

    def set(self, pct: float):
        self._pct = max(0.0, min(100.0, pct))
        self._draw()

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()
        h = self._height
        r = h // 2

        # Track
        self._rounded_rect(0, 0, w, h, r, COLORS['progress_bg'])

        # Fill
        fill_w = int(w * self._pct / 100)
        if fill_w > r * 2:
            self._rounded_rect(0, 0, fill_w, h, r, COLORS['accent'])

        # Texto
        txt = f"{self._pct:.1f}%"
        self.create_text(w // 2, h // 2, text=txt,
                         fill=COLORS['text'], font=('Consolas', 9, 'bold'))

    def _rounded_rect(self, x1, y1, x2, y2, r, color):
        self.create_arc(x1, y1, x1+2*r, y1+2*r, start=90, extent=90,  fill=color, outline='')
        self.create_arc(x2-2*r, y1, x2, y1+2*r, start=0,  extent=90,  fill=color, outline='')
        self.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90, fill=color, outline='')
        self.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90, fill=color, outline='')
        self.create_rectangle(x1+r, y1, x2-r, y2, fill=color, outline='')
        self.create_rectangle(x1, y1+r, x2, y2-r, fill=color, outline='')


class SpeedGauge(tk.Canvas):
    """Mini gauge circular de velocidade."""

    def __init__(self, master, size=80, **kw):
        super().__init__(master, width=size, height=size,
                         highlightthickness=0, bg=COLORS['bg'], **kw)
        self._size = size
        self._speed_text = '—'
        self._draw()

    def update_speed(self, bps: Optional[float]):
        self._speed_text = fmt_speed(bps) if bps else '—'
        self._draw()

    def _draw(self):
        self.delete('all')
        s = self._size
        pad = 6
        self.create_oval(pad, pad, s-pad, s-pad,
                         outline=COLORS['border'], width=3)
        self.create_text(s//2, s//2 - 6, text=self._speed_text,
                         fill=COLORS['accent'], font=('Consolas', 8, 'bold'),
                         width=s-10)
        self.create_text(s//2, s//2 + 10, text='velocidade',
                         fill=COLORS['text_dim'], font=('Consolas', 7))


class LogPanel(tk.Frame):
    """Painel de log com cores e botão de limpeza."""

    TAG_COLORS = {
        'error':   COLORS['error'],
        'success': COLORS['success'],
        'info':    '#7eb8f7',
        'warning': COLORS['warning'],
        '':        COLORS['text'],
    }

    def __init__(self, master, **kw):
        super().__init__(master, bg=COLORS['bg'], **kw)
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=COLORS['bg'])
        header.pack(fill=tk.X, pady=(0, 4))

        tk.Label(header, text="LOG DE ATIVIDADE", bg=COLORS['bg'],
                 fg=COLORS['text_dim'], font=('Consolas', 8, 'bold')).pack(side=tk.LEFT)

        tk.Button(header, text="Limpar", bg=COLORS['surface'], fg=COLORS['text_dim'],
                  relief='flat', font=('Consolas', 8), cursor='hand2',
                  command=self.clear, bd=0, padx=6).pack(side=tk.RIGHT)

        self.text = scrolledtext.ScrolledText(
            self, height=12, bg=COLORS['surface'], fg=COLORS['text'],
            font=('Consolas', 9), relief='flat', bd=0, wrap=tk.WORD,
            insertbackground=COLORS['text'],
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.configure(state=tk.DISABLED)

        for tag, color in self.TAG_COLORS.items():
            self.text.tag_config(tag, foreground=color)

    def append(self, message: str, tag: str = ''):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f"[{ts}] {message}\n"
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, line, tag or '')
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def clear(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete('1.0', tk.END)
        self.text.configure(state=tk.DISABLED)


class HistoryPanel(tk.Frame):
    """Painel de histórico de downloads da sessão."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=COLORS['bg'], **kw)
        self._records: List[DownloadRecord] = []
        self._build()

    def _build(self):
        tk.Label(self, text="HISTÓRICO DA SESSÃO", bg=COLORS['bg'],
                 fg=COLORS['text_dim'], font=('Consolas', 8, 'bold')).pack(anchor='w', pady=(0, 4))

        cols = ('Hora', 'Título', 'Formato', 'Status', 'Tamanho')
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=6)

        widths = (60, 260, 60, 70, 70)
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor='center' if col != 'Título' else 'w')

        self.tree.tag_configure('ok',        foreground=COLORS['success'])
        self.tree.tag_configure('error',     foreground=COLORS['error'])
        self.tree.tag_configure('cancelled', foreground=COLORS['warning'])

        sb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def add(self, record: DownloadRecord):
        self._records.append(record)
        size_str = f"{record.size_mb:.1f} MB" if record.size_mb else '—'
        title = record.title[:40] + '…' if len(record.title) > 40 else record.title
        self.tree.insert('', 0, values=(
            record.timestamp, title, record.fmt.upper(),
            record.status.upper(), size_str,
        ), tags=(record.status,))


# ──────────────────────────────────────────────
# Janela principal (View + Controller)
# ──────────────────────────────────────────────
class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("YouTube Downloader Pro")
        self.geometry("860x820")
        self.minsize(720, 640)
        self.configure(bg=COLORS['bg'])

        self._engine = DownloadEngine()
        self._engine.on_log = self._on_log
        self._engine.on_progress = self._on_progress
        self._engine.on_finished = self._on_finished

        self._is_downloading = False
        self._last_stats: Optional[DownloadStats] = None

        # Fila thread-safe para atualizações de UI
        self._ui_queue: queue.Queue = queue.Queue()

        self._apply_styles()
        self._build_ui()
        self._check_ffmpeg()

        # Polling da fila
        self._poll_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Estilos ───────────────────────────────
    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure('.', background=COLORS['bg'], foreground=COLORS['text'],
                        fieldbackground=COLORS['surface'], bordercolor=COLORS['border'],
                        lightcolor=COLORS['border'], darkcolor=COLORS['border'],
                        troughcolor=COLORS['surface2'], selectbackground=COLORS['accent'],
                        selectforeground=COLORS['text'], insertcolor=COLORS['text'])

        style.configure('TFrame',    background=COLORS['bg'])
        style.configure('TLabel',    background=COLORS['bg'], foreground=COLORS['text'],
                        font=('Segoe UI', 9))
        style.configure('TEntry',    fieldbackground=COLORS['surface'],
                        foreground=COLORS['text'], insertcolor=COLORS['text'],
                        bordercolor=COLORS['border'], font=('Segoe UI', 10))
        style.configure('TCombobox', fieldbackground=COLORS['surface'],
                        foreground=COLORS['text'], selectbackground=COLORS['surface'],
                        selectforeground=COLORS['text'], font=('Segoe UI', 10))
        style.configure('TRadiobutton', background=COLORS['bg'],
                        foreground=COLORS['text'], font=('Segoe UI', 9))
        style.configure('TButton', background=COLORS['surface2'],
                        foreground=COLORS['text'], bordercolor=COLORS['border'],
                        font=('Segoe UI', 9), padding=(8, 4))
        style.map('TButton',
                  background=[('active', COLORS['border']), ('disabled', COLORS['surface'])],
                  foreground=[('disabled', COLORS['text_dim'])])

        style.configure('Accent.TButton', background=COLORS['accent'],
                        foreground='#ffffff', font=('Segoe UI', 10, 'bold'), padding=(12, 6))
        style.map('Accent.TButton',
                  background=[('active', COLORS['accent_dim']), ('disabled', COLORS['surface2'])])

        style.configure('TLabelframe', background=COLORS['bg'],
                        bordercolor=COLORS['border'], relief='flat')
        style.configure('TLabelframe.Label', background=COLORS['bg'],
                        foreground=COLORS['text_dim'], font=('Consolas', 8, 'bold'))

        style.configure('Treeview', background=COLORS['surface'],
                        foreground=COLORS['text'], fieldbackground=COLORS['surface'],
                        rowheight=22, font=('Consolas', 9))
        style.configure('Treeview.Heading', background=COLORS['surface2'],
                        foreground=COLORS['text_dim'], font=('Consolas', 8, 'bold'))
        style.map('Treeview', background=[('selected', COLORS['accent_dim'])])

    # ── Construção da UI ──────────────────────
    def _build_ui(self):
        # Título
        hdr = tk.Frame(self, bg=COLORS['bg'])
        hdr.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(hdr, text="▶  YouTube Downloader Pro",
                 bg=COLORS['bg'], fg=COLORS['text'],
                 font=('Segoe UI', 15, 'bold')).pack(side=tk.LEFT)
        tk.Label(hdr, text="v2.0",
                 bg=COLORS['bg'], fg=COLORS['text_dim'],
                 font=('Consolas', 9)).pack(side=tk.LEFT, padx=(8, 0), pady=(4, 0))

        sep = tk.Frame(self, bg=COLORS['border'], height=1)
        sep.pack(fill=tk.X, padx=16, pady=(0, 10))

        # Scroll container
        container = tk.Frame(self, bg=COLORS['bg'])
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        canvas = tk.Canvas(container, bg=COLORS['bg'], highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg=COLORS['bg'])
        self._scroll_frame.bind('<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Seções
        sf = self._scroll_frame
        self._build_url_section(sf)
        self._build_options_section(sf)
        self._build_dest_section(sf)
        self._build_progress_section(sf)
        self._build_controls(sf)
        self._build_log_section(sf)
        self._build_history_section(sf)

        # Bindings de scroll no canvas
        self.bind_all('<MouseWheel>',
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

    def _section(self, parent, title: str) -> tk.Frame:
        """Cria um frame de seção com título."""
        wrap = tk.Frame(parent, bg=COLORS['bg'])
        wrap.pack(fill=tk.X, pady=(0, 10))
        tk.Label(wrap, text=title, bg=COLORS['bg'], fg=COLORS['text_dim'],
                 font=('Consolas', 8, 'bold')).pack(anchor='w', pady=(0, 4))
        body = tk.Frame(wrap, bg=COLORS['surface'], padx=12, pady=10,
                        highlightbackground=COLORS['border'], highlightthickness=1)
        body.pack(fill=tk.X)
        return body

    def _build_url_section(self, parent):
        body = self._section(parent, "URL DO VÍDEO / PLAYLIST")

        self._url_var = tk.StringVar()
        row = tk.Frame(body, bg=COLORS['surface'])
        row.pack(fill=tk.X)

        self._url_entry = ttk.Entry(row, textvariable=self._url_var, font=('Segoe UI', 10))
        self._url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._url_entry.bind('<Return>', lambda e: self._start())

        ttk.Button(row, text="Colar", command=self._paste_url).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row, text="Limpar",
                   command=lambda: self._url_var.set('')).pack(side=tk.LEFT)

    def _build_options_section(self, parent):
        body = self._section(parent, "TIPO, FORMATO E QUALIDADE")

        self._dl_type = tk.StringVar(value='audio')
        self._audio_fmt = tk.StringVar(value='mp3')
        self._video_fmt = tk.StringVar(value='mp4')
        self._audio_q = tk.StringVar(value='192')
        self._video_q = tk.StringVar(value='best')

        # Tipo
        type_row = tk.Frame(body, bg=COLORS['surface'])
        type_row.pack(fill=tk.X, pady=(0, 8))
        for label, val in (('🎵  Áudio', 'audio'), ('🎬  Vídeo', 'video')):
            ttk.Radiobutton(type_row, text=label, variable=self._dl_type, value=val,
                            command=self._update_options).pack(side=tk.LEFT, padx=(0, 20))

        # Formato + Qualidade
        fq_row = tk.Frame(body, bg=COLORS['surface'])
        fq_row.pack(fill=tk.X)

        tk.Label(fq_row, text="Formato:", bg=COLORS['surface'],
                 fg=COLORS['text_dim'], font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(0, 6))
        self._fmt_combo = ttk.Combobox(fq_row, textvariable=self._audio_fmt,
                                       values=AUDIO_FORMATS, state='readonly', width=8)
        self._fmt_combo.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(fq_row, text="Qualidade:", bg=COLORS['surface'],
                 fg=COLORS['text_dim'], font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=(0, 6))
        self._q_combo = ttk.Combobox(fq_row, textvariable=self._audio_q,
                                     values=AUDIO_BITRATES, state='readonly', width=16)
        self._q_combo.pack(side=tk.LEFT)

    def _build_dest_section(self, parent):
        body = self._section(parent, "PASTA DE DESTINO  ·  TEMPLATE DO ARQUIVO")

        # Destino
        dest_row = tk.Frame(body, bg=COLORS['surface'])
        dest_row.pack(fill=tk.X, pady=(0, 6))
        self._dest_var = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        ttk.Entry(dest_row, textvariable=self._dest_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(dest_row, text="📁 Procurar", command=self._browse).pack(side=tk.RIGHT)

        # Template
        tmpl_row = tk.Frame(body, bg=COLORS['surface'])
        tmpl_row.pack(fill=tk.X)
        self._tmpl_var = tk.StringVar(value='%(title)s - %(id)s')
        ttk.Entry(tmpl_row, textvariable=self._tmpl_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(tmpl_row, text="?", command=self._show_template_help,
                   width=3).pack(side=tk.RIGHT)

    def _build_progress_section(self, parent):
        body = self._section(parent, "PROGRESSO")

        # Linha superior: nome do arquivo
        self._file_label = tk.Label(body, text="Aguardando…", bg=COLORS['surface'],
                                    fg=COLORS['text_dim'], font=('Consolas', 9),
                                    anchor='w', wraplength=750)
        self._file_label.pack(fill=tk.X, pady=(0, 6))

        # Barra de progresso customizada
        self._progress = RoundedProgressBar(body, height=24)
        self._progress.pack(fill=tk.X, pady=(0, 10))

        # Painel de métricas
        metrics = tk.Frame(body, bg=COLORS['surface'])
        metrics.pack(fill=tk.X)

        self._speed_gauge = SpeedGauge(metrics, size=80)
        self._speed_gauge.pack(side=tk.LEFT, padx=(0, 16))

        # Grid de labels
        info_grid = tk.Frame(metrics, bg=COLORS['surface'])
        info_grid.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._metric_vars: Dict[str, tk.StringVar] = {}
        fields = [
            ('downloaded', 'Baixado:'),
            ('total',      'Total:'),
            ('speed',      'Velocidade:'),
            ('eta',        'ETA:'),
            ('elapsed',    'Decorrido:'),
            ('files',      'Arquivos:'),
        ]
        for i, (key, lbl) in enumerate(fields):
            r, c = divmod(i, 2)
            tk.Label(info_grid, text=lbl, bg=COLORS['surface'],
                     fg=COLORS['text_dim'], font=('Consolas', 8)).grid(
                         row=r, column=c*2, sticky='w', padx=(0, 4), pady=1)
            var = tk.StringVar(value='—')
            self._metric_vars[key] = var
            tk.Label(info_grid, textvariable=var, bg=COLORS['surface'],
                     fg=COLORS['text'], font=('Consolas', 8, 'bold')).grid(
                         row=r, column=c*2+1, sticky='w', padx=(0, 24), pady=1)

    def _build_controls(self, parent):
        row = tk.Frame(parent, bg=COLORS['bg'])
        row.pack(fill=tk.X, pady=(0, 10))

        self._dl_btn = ttk.Button(row, text="▶  Iniciar Download",
                                  command=self._start, style='Accent.TButton')
        self._dl_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._cancel_btn = ttk.Button(row, text="■  Cancelar",
                                      command=self._cancel, state=tk.DISABLED)
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(row, text="📂 Abrir pasta",
                   command=self._open_folder).pack(side=tk.LEFT)

        ttk.Button(row, text="F1 Ajuda",
                   command=self._show_help).pack(side=tk.RIGHT)

        self.bind('<F1>', lambda e: self._show_help())
        self.bind('<Control-v>', lambda e: self._paste_url())
        self.bind('<Control-o>', lambda e: self._browse())

    def _build_log_section(self, parent):
        wrap = tk.Frame(parent, bg=COLORS['bg'])
        wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self._log = LogPanel(wrap)
        self._log.pack(fill=tk.BOTH, expand=True)

    def _build_history_section(self, parent):
        wrap = tk.Frame(parent, bg=COLORS['bg'])
        wrap.pack(fill=tk.X, pady=(0, 10))
        self._history = HistoryPanel(wrap)
        self._history.pack(fill=tk.X)

    # ── Helpers de UI ─────────────────────────
    def _update_options(self):
        is_video = self._dl_type.get() == 'video'
        if is_video:
            self._fmt_combo.configure(values=VIDEO_FORMATS)
            self._fmt_combo.set(self._video_fmt.get())
            self._q_combo.configure(values=VIDEO_QUALITIES)
            self._q_combo.set(self._video_q.get())
        else:
            self._fmt_combo.configure(values=AUDIO_FORMATS)
            self._fmt_combo.set(self._audio_fmt.get())
            self._q_combo.configure(values=AUDIO_BITRATES)
            self._q_combo.set(self._audio_q.get())

    def _paste_url(self):
        try:
            self._url_var.set(self.clipboard_get())
        except Exception:
            pass

    def _browse(self):
        d = filedialog.askdirectory(title="Pasta de destino",
                                    initialdir=self._dest_var.get())
        if d:
            self._dest_var.set(d)

    def _open_folder(self):
        folder = self._dest_var.get()
        if not os.path.exists(folder):
            messagebox.showwarning("Aviso", "A pasta ainda não existe.")
            return
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.run(['open', folder])
        else:
            subprocess.run(['xdg-open', folder])

    def _reset_metrics(self):
        for var in self._metric_vars.values():
            var.set('—')
        self._progress.set(0)
        self._speed_gauge.update_speed(None)
        self._file_label.config(text='Aguardando…')

    def _check_ffmpeg(self):
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            self._log.append("ffmpeg encontrado ✔", 'success')
        except Exception:
            self._log.append(
                "ffmpeg não encontrado — conversões podem falhar.\n"
                "Instale em: https://ffmpeg.org/download.html", 'warning'
            )

    # ── Controle de download ──────────────────
    def _start(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Cole uma URL do YouTube.")
            return
        if self._is_downloading:
            messagebox.showwarning("Aviso", "Já há um download em andamento.")
            return

        folder = self._dest_var.get()
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível criar pasta:\n{exc}")
            return

        is_video = self._dl_type.get() == 'video'
        fmt = self._video_fmt.get() if is_video else self._audio_fmt.get()
        quality = self._video_q.get() if is_video else self._audio_q.get()

        # Sincronizar variáveis de formato com combobox
        selected_fmt = self._fmt_combo.get()
        selected_q = self._q_combo.get()
        if selected_fmt:
            fmt = selected_fmt
        if selected_q:
            quality = selected_q

        self._is_downloading = True
        self._dl_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._reset_metrics()

        self._log.append(f"Iniciando: {url}", 'info')
        self._current_url = url
        self._current_fmt = fmt

        self._engine.start(
            url=url,
            outfolder=folder,
            fmt=fmt,
            quality=quality,
            is_video=is_video,
            filename_template=f"{self._tmpl_var.get()}.%(ext)s",
        )

    def _cancel(self):
        self._engine.cancel()
        self._log.append("Cancelamento solicitado…", 'warning')
        self._cancel_btn.config(state=tk.DISABLED)

    # ── Callbacks da engine (thread-safe via queue) ──
    def _on_log(self, msg: str, tag: str):
        self._ui_queue.put(('log', msg, tag))

    def _on_progress(self, payload: Dict):
        self._ui_queue.put(('progress', payload))

    def _on_finished(self, stats: DownloadStats, cancelled: bool):
        self._ui_queue.put(('finished', stats, cancelled))

    def _poll_queue(self):
        """Drena a fila de mensagens no thread da UI."""
        try:
            while True:
                item = self._ui_queue.get_nowait()
                kind = item[0]
                if kind == 'log':
                    _, msg, tag = item
                    self._log.append(msg, tag)
                elif kind == 'progress':
                    _, payload = item
                    self._apply_progress(payload)
                elif kind == 'finished':
                    _, stats, cancelled = item
                    self._apply_finished(stats, cancelled)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _apply_progress(self, d: Dict):
        if d.get('_meta'):
            stats: DownloadStats = d['stats']
            self._metric_vars['files'].set(
                f"0 / {stats.total_files}"
            )
            return

        status = d.get('status')
        stats: DownloadStats = d.get('stats', DownloadStats())

        if status == 'downloading':
            filename = d.get('filename', '')
            downloaded = d.get('downloaded', 0)
            total = d.get('total')
            pct = d.get('pct')
            speed = d.get('speed')
            eta = d.get('eta')

            if filename:
                short = filename[:90] + '…' if len(filename) > 90 else filename
                self._file_label.config(text=f"↓  {short}")

            if pct is not None:
                self._progress.set(pct)

            self._metric_vars['downloaded'].set(fmt_bytes(downloaded))
            self._metric_vars['total'].set(fmt_bytes(total) if total else '—')
            self._metric_vars['speed'].set(fmt_speed(speed) if speed else '—')
            self._metric_vars['eta'].set(fmt_eta(eta))
            self._metric_vars['elapsed'].set(stats.elapsed)
            self._metric_vars['files'].set(
                f"{stats.completed} / {stats.total_files}")
            self._speed_gauge.update_speed(speed)

        elif status == 'finished':
            self._progress.set(100)
            self._metric_vars['files'].set(
                f"{stats.completed} / {stats.total_files}")
            self._metric_vars['elapsed'].set(stats.elapsed)
            # Adicionar ao histórico
            rec = DownloadRecord(
                title=d.get('filename', 'Desconhecido'),
                url=getattr(self, '_current_url', ''),
                fmt=getattr(self, '_current_fmt', ''),
                status='ok',
                size_mb=d.get('size_mb', 0.0),
            )
            self._history.add(rec)

        elif status == 'error':
            self._metric_vars['files'].set(
                f"{stats.completed} / {stats.total_files} (erros: {stats.errors})")

    def _apply_finished(self, stats: DownloadStats, cancelled: bool):
        self._is_downloading = False
        self._dl_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        self._progress.set(100 if not cancelled else self._progress._pct)
        self._file_label.config(text='Concluído.' if not cancelled else 'Cancelado.')

        self._metric_vars['elapsed'].set(stats.elapsed)
        self._metric_vars['files'].set(
            f"{stats.completed} / {stats.total_files}  (erros: {stats.errors})")

        if not cancelled:
            self._log.append(
                f"Sessão encerrada — {stats.completed} arquivo(s) baixado(s), "
                f"{stats.errors} erro(s)  |  tempo: {stats.elapsed}", 'success'
            )
            if messagebox.askyesno("Concluído",
                                   f"Download finalizado!\n\n"
                                   f"Arquivos: {stats.completed}  |  Erros: {stats.errors}\n\n"
                                   "Abrir pasta de destino?"):
                self._open_folder()

    # ── Ajuda ─────────────────────────────────
    def _show_template_help(self):
        messagebox.showinfo("Template do nome", (
            "Variáveis disponíveis:\n\n"
            "%(title)s       — Título do vídeo\n"
            "%(id)s          — ID do vídeo\n"
            "%(uploader)s    — Canal\n"
            "%(upload_date)s — Data (YYYYMMDD)\n"
            "%(duration)s    — Duração em segundos\n"
            "%(ext)s         — Extensão\n\n"
            "Exemplo: %(uploader)s - %(title)s\n"
            "(a extensão é adicionada automaticamente)"
        ))

    def _show_help(self):
        messagebox.showinfo("Ajuda", (
            "YouTube Downloader Pro  v2.0\n\n"
            "1. Cole a URL do vídeo ou playlist\n"
            "2. Escolha Áudio ou Vídeo\n"
            "3. Selecione formato e qualidade\n"
            "4. Defina a pasta de destino\n"
            "5. Clique em Iniciar Download\n\n"
            "Atalhos:\n"
            "  Ctrl+V  — Colar URL\n"
            "  Ctrl+O  — Escolher pasta\n"
            "  F1      — Esta ajuda\n\n"
            "Formatos de áudio: MP3 WAV OGG M4A AAC FLAC\n"
            "Formatos de vídeo: MP4 WEBM MKV AVI MOV FLV\n\n"
            "Requer ffmpeg instalado para conversão."
        ))

    # ── Fechar janela ─────────────────────────
    def _on_close(self):
        if self._is_downloading:
            if messagebox.askyesno("Sair", "Download em andamento. Sair mesmo assim?"):
                self._engine.cancel()
                self.destroy()
        else:
            self.destroy()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def main():
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()