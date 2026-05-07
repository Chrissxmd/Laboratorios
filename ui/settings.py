from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from core.ai import AIConfig, MODELS
from core.pdf_utils import OCRConfig  # mantenido por compatibilidad de firma


class AISettingsDialog(QDialog):
    """Dialogo de configuracion de IA.

    En v8.8 el OCR se ha eliminado: los PDFs se envian directamente a la API.
    El objeto OCRConfig se mantiene por compatibilidad de firma pero sus
    campos no tienen efecto en el procesamiento.
    """

    def __init__(self, parent, config: AIConfig, ocr_config: OCRConfig):
        super().__init__(parent)
        self._config = config
        self._ocr_config = ocr_config
        self.setWindowTitle("Configuracion IA")
        self.setFixedWidth(520)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Proveedor"))
        self.provider = QComboBox()
        self.provider.addItems(["claude", "openai", "gemini", "deepseek"])
        self.provider.setCurrentText(self._config.provider)
        self.provider.currentTextChanged.connect(self._refresh_models)
        lay.addWidget(self.provider)

        lay.addWidget(QLabel("Modelo sugerido"))
        self.model = QComboBox()
        self.model.setEditable(True)
        lay.addWidget(self.model)

        hint_model = QLabel("Puedes escribir manualmente cualquier modelo valido.")
        hint_model.setWordWrap(True)
        hint_model.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(hint_model)

        lay.addWidget(QLabel("API Key"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("sk-... / AIza... / claude... / deepseek...")
        self.key.setText(self._config.api_key)
        lay.addWidget(self.key)

        lay.addWidget(QLabel("Timeout (segundos)"))
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 300)
        self.timeout.setValue(self._config.timeout_seconds)
        lay.addWidget(self.timeout)

        lay.addWidget(QLabel("Maximo reintentos"))
        self.retries = QSpinBox()
        self.retries.setRange(1, 10)
        self.retries.setValue(self._config.max_retries)
        lay.addWidget(self.retries)

        lay.addWidget(QLabel("Temperatura"))
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(self._config.temperature)
        lay.addWidget(self.temperature)

        # ── Nota informativa sobre el nuevo modo ───────────────────────────
        info = QLabel(
            "\u2139\ufe0f  v8.8: Los PDFs se envian directamente a la API (PDF nativo). "
            "No se requiere Tesseract ni OCR local. El modelo reconoce el documento completo, "
            "incluyendo PDFs escaneados y formatos complejos."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #3b82f6; font-size: 11px; padding: 6px; border: 1px solid #2a3050; border-radius: 6px;")
        lay.addWidget(info)

        save_btn = QPushButton("Guardar")
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

        self._refresh_models(self._config.provider)
        self.model.setEditText(self._config.model)

    def _refresh_models(self, provider: str):
        current_text = self.model.currentText().strip()
        self.model.clear()
        self.model.addItems(MODELS.get(provider, []))
        if current_text:
            self.model.setEditText(current_text)

    def _save(self):
        self._config.provider = self.provider.currentText()
        self._config.model = self.model.currentText().strip()
        self._config.api_key = self.key.text().strip()
        self._config.timeout_seconds = self.timeout.value()
        self._config.max_retries = self.retries.value()
        self._config.temperature = float(self.temperature.value())
        # OCRConfig se deja sin cambios — no tiene efecto en v8
        self.accept()
