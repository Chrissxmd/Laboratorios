from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, pyqtSignal

from core.ai import AIConfig, test_connection
from core.pdf_utils import OCRConfig
from core.processor import process_folder, safe_max_threads, reprocess_temporary_errors


class ProcessWorker(QObject):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, folder_path: str, ai_config: AIConfig,
                 ocr_config: OCRConfig, threads: int = 1, output_dir: str | None = None):
        super().__init__()
        self.folder_path = folder_path
        self.ai_config   = ai_config
        self.ocr_config  = ocr_config
        self.threads     = threads
        self.output_dir  = output_dir
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()

    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    def cancel(self):
        self.cancel_event.set()
        self.pause_event.clear()

    def run(self):
        try:
            summary = process_folder(
                self.folder_path,
                self.ai_config,
                self.ocr_config,
                progress_cb=lambda payload: self.progress.emit(payload),
                threads=self.threads,
                output_dir=self.output_dir or None,
                pause_event=self.pause_event,
                cancel_event=self.cancel_event,
            )
            self.finished.emit(summary.__dict__)
        except (OSError, RuntimeError, ValueError) as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Error inesperado: {e}")



class ReprocessErrorsWorker(QObject):
    progress = pyqtSignal(dict)
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, output_dir: str, folder_path: str, ai_config: AIConfig,
                 ocr_config: OCRConfig, threads: int = 1):
        super().__init__()
        self.output_dir = output_dir
        self.folder_path = folder_path
        self.ai_config = ai_config
        self.ocr_config = ocr_config
        self.threads = threads

    def run(self):
        try:
            summary = reprocess_temporary_errors(
                self.output_dir,
                self.folder_path,
                self.ai_config,
                self.ocr_config,
                progress_cb=lambda payload: self.progress.emit(payload),
                threads=self.threads,
            )
            self.finished.emit(summary.__dict__)
        except (OSError, RuntimeError, ValueError) as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Error inesperado: {e}")


class ConnectionTestWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)

    def __init__(self, ai_config: AIConfig):
        super().__init__()
        self.ai_config = ai_config

    def run(self):
        self.progress.emit("Probando conexión con la API...")
        ok, msg = test_connection(self.ai_config)
        self.finished.emit(ok, msg)
