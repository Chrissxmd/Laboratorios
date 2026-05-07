from __future__ import annotations

import csv
import logging
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QProgressBar, QSizePolicy,
    QSpinBox, QComboBox, QCheckBox, QStatusBar, QVBoxLayout, QWidget,
    QRadioButton, QButtonGroup, QScrollArea,
)

from core.ai import AIConfig, MODELS
from core.pdf_utils import OCRConfig
from core.processor import safe_max_threads
from ui.worker import ProcessWorker, ConnectionTestWorker, ReprocessErrorsWorker

log = logging.getLogger("lab_extractor.main")

DARK_BG="#0b0f18"; PANEL_BG="#111827"; CARD_BG="#172033"; CARD_BG_2="#1b2538"
BORDER="#283552"; BORDER_SOFT="#22304a"; ACCENT="#3b82f6"; ACCENT_HOVER="#2563eb"
SUCCESS="#10b981"; ERROR_COLOR="#ef4444"; WARNING="#f59e0b"; TEXT_PRIMARY="#eef4ff"; TEXT_MUTED="#7e8da8"; TEXT_LABEL="#b7c3d9"

STYLESHEET=f"""
QMainWindow, QWidget {{background-color:{DARK_BG};color:{TEXT_PRIMARY};font-family:'Segoe UI','SF Pro Display','Helvetica Neue',Arial,sans-serif;font-size:13px;}}
QLabel {{color:{TEXT_LABEL};font-size:12px;background:transparent;}}
QLabel#title_label {{color:{TEXT_PRIMARY};font-size:24px;font-weight:800;letter-spacing:-0.5px;}}
QLabel#subtitle_label {{color:{TEXT_MUTED};font-size:12px;}}
QLabel#section_title {{color:{TEXT_PRIMARY};font-size:16px;font-weight:700;}}
QLabel#section_title_blue {{color:{ACCENT};font-size:16px;font-weight:800;}}
QLabel#small_help {{color:{TEXT_MUTED};font-size:11px;}}
QLabel#green_help {{color:{SUCCESS};font-size:11px;font-weight:600;}}
QLabel#status_pill {{color:{SUCCESS};font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;background-color:rgba(16,185,129,0.14);border:1px solid rgba(16,185,129,0.32);}}
QLabel#security_badge {{color:{SUCCESS};font-size:12px;font-weight:800;}}
QLabel#security_sub {{color:{TEXT_LABEL};font-size:11px;}}
QLabel#file_label {{color:{TEXT_PRIMARY};font-size:12px;}}
QLabel#summary_label {{color:{TEXT_MUTED};font-size:11px;}}
QLabel#link_label {{color:#60a5fa;font-size:11px;text-decoration:underline;}}
QFrame#card, QFrame#card_active, QFrame#metric_card, QFrame#security_card {{background-color:{CARD_BG};border:1px solid {BORDER};border-radius:12px;}}
QFrame#card_active {{border:1px solid {ACCENT};background-color:#0f2444;}}
QFrame#security_card {{border:1px solid rgba(16,185,129,0.45);background-color:rgba(16,185,129,0.06);}}
QFrame#footer_bar {{background-color:{PANEL_BG};border-top:1px solid {BORDER_SOFT};}}
QLineEdit,QComboBox,QSpinBox {{background-color:{PANEL_BG};border:1px solid {BORDER};border-radius:7px;padding:7px 10px;color:{TEXT_PRIMARY};font-size:13px;selection-background-color:{ACCENT};min-height:20px;}}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus {{border:1px solid {ACCENT};}}
QLineEdit:hover,QComboBox:hover,QSpinBox:hover {{border:1px solid #3a4b71;}}
QComboBox::drop-down {{border:none;width:28px;}}
QComboBox::down-arrow {{image:none;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid {TEXT_MUTED};margin-right:8px;}}
QComboBox QAbstractItemView {{background-color:{PANEL_BG};border:1px solid {BORDER};selection-background-color:{ACCENT};color:{TEXT_PRIMARY};padding:4px;}}
QSpinBox::up-button,QSpinBox::down-button {{background:{BORDER};border:none;border-radius:3px;width:16px;}}
QCheckBox,QRadioButton {{color:{TEXT_LABEL};spacing:8px;font-size:12px;}}
QRadioButton::indicator {{width:14px;height:14px;}}
QCheckBox::indicator {{width:16px;height:16px;}}
QPushButton {{background-color:{CARD_BG_2};color:{TEXT_PRIMARY};border:1px solid {BORDER};border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;}}
QPushButton:hover {{background-color:#25314a;border-color:{ACCENT};}}
QPushButton:pressed {{background-color:{ACCENT};color:white;}}
QPushButton#primary_btn {{background-color:{ACCENT};color:white;border:1px solid {ACCENT};font-weight:800;font-size:15px;padding:10px 24px;}}
QPushButton#primary_btn:hover {{background-color:{ACCENT_HOVER};}}
QPushButton#primary_btn:disabled {{background-color:#29344d;color:{TEXT_MUTED};border-color:#29344d;}}
QPushButton#danger_btn {{background-color:transparent;color:{ERROR_COLOR};border:1px solid {ERROR_COLOR};font-weight:800;}}
QPushButton#danger_btn:hover {{background-color:{ERROR_COLOR};color:white;}}
QPushButton#pause_btn {{background-color:transparent;color:#93c5fd;border:1px solid {ACCENT};font-weight:800;}}
QPushButton#pause_btn:hover {{background-color:{ACCENT};color:white;}}
QPushButton#success_btn {{background-color:rgba(16,185,129,0.08);color:{SUCCESS};border:1px solid {SUCCESS};font-weight:700;}}
QPushButton#success_btn:hover {{background-color:{SUCCESS};color:white;}}
QProgressBar {{background-color:{PANEL_BG};border:1px solid {BORDER};border-radius:7px;height:12px;color:{TEXT_PRIMARY};text-align:right;padding-right:4px;}}
QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {SUCCESS},stop:1 {ACCENT});border-radius:6px;}}
QPlainTextEdit {{background-color:{PANEL_BG};color:#b7c3d9;border:1px solid {BORDER};border-radius:10px;font-family:'Cascadia Code','Consolas','Courier New',monospace;font-size:11px;padding:10px;selection-background-color:{ACCENT};}}
QScrollBar:vertical {{background:{PANEL_BG};width:8px;border-radius:4px;}}
QScrollBar::handle:vertical {{background:{BORDER};border-radius:4px;min-height:20px;}}
QScrollBar::handle:vertical:hover {{background:{ACCENT};}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
QStatusBar {{background-color:{PANEL_BG};color:{TEXT_MUTED};font-size:11px;border-top:1px solid {BORDER};}}
"""

def card_frame(active: bool=False)->QFrame:
    f=QFrame(); f.setObjectName("card_active" if active else "card"); return f

class StepWidget(QFrame):
    def __init__(self,n:int,title:str,detail:str,icon:str,active:bool=False):
        super().__init__()
        lay=QHBoxLayout(self); lay.setContentsMargins(14,12,14,12); lay.setSpacing(12)
        self._n=n
        self._icon=icon
        self.num=QLabel(str(n)); self.num.setAlignment(Qt.AlignmentFlag.AlignCenter); self.num.setFixedSize(42,42)
        self.ic=QLabel(icon); self.ic.setFixedWidth(28)
        texts=QVBoxLayout(); texts.setSpacing(4)
        self.ttl=QLabel(title); self.ttl.setWordWrap(True)
        self.det=QLabel(detail); self.det.setWordWrap(True); self.det.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        texts.addWidget(self.ttl); texts.addWidget(self.det); lay.addWidget(self.num); lay.addWidget(self.ic); lay.addLayout(texts,1)
        self.set_state("active" if active else "pending")

    def set_active(self,active:bool):
        self.set_state("active" if active else "pending")

    def set_state(self,state:str):
        state = state if state in {"pending","active","completed"} else "pending"
        active = state == "active"
        completed = state == "completed"
        self.setObjectName("card_active" if active else "card")
        self.style().unpolish(self); self.style().polish(self)
        color = SUCCESS if completed else (ACCENT if active else TEXT_MUTED)
        fill = "rgba(16,185,129,0.12)" if completed else ("rgba(59,130,246,0.10)" if active else "transparent")
        self.num.setText("✓" if completed else str(self._n))
        self.ic.setText("✓" if completed else self._icon)
        self.num.setStyleSheet(
            f"background-color:{fill};border:1px solid {color};border-radius:21px;"
            f"color:{color};font-size:18px;font-weight:900;"
        )
        self.ic.setStyleSheet(f"font-size:22px;color:{color};")
        self.ttl.setStyleSheet(f"color:{color if active or completed else TEXT_LABEL};font-size:14px;font-weight:800;")
        self.det.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")

class MetricCard(QFrame):
    def __init__(self,title:str,color:str,icon:str):
        super().__init__(); self.setObjectName("metric_card"); self.setStyleSheet(f"QFrame#metric_card{{background-color:{CARD_BG};border:1px solid {color};border-radius:10px;}}")
        lay=QVBoxLayout(self); lay.setContentsMargins(10,9,10,9); lay.setSpacing(3)
        ic=QLabel(icon); ic.setAlignment(Qt.AlignmentFlag.AlignCenter); ic.setStyleSheet(f"font-size:22px;color:{color};")
        self.value=QLabel("0"); self.value.setAlignment(Qt.AlignmentFlag.AlignCenter); self.value.setStyleSheet(f"color:{color};font-size:26px;font-weight:900;")
        ttl=QLabel(title.upper()); ttl.setAlignment(Qt.AlignmentFlag.AlignCenter); ttl.setWordWrap(True); ttl.setStyleSheet(f"color:{color};font-size:9px;font-weight:800;")
        lay.addWidget(ic); lay.addWidget(self.value); lay.addWidget(ttl)
    def set_value(self,v:int|str): self.value.setText(str(v))

class StatsWidget(QWidget):
    def __init__(self):
        super().__init__(); lay=QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(10)
        self.cargables=MetricCard("Cargables",SUCCESS,"▣"); self.revision=MetricCard("Revisión",ACCENT,"◉")
        self.no_cargables=MetricCard("No cargables",WARNING,"⚠"); self.errores=MetricCard("Errores",ERROR_COLOR,"!"); self.total=MetricCard("Total",TEXT_MUTED,"▤")
        for w in [self.cargables,self.revision,self.no_cargables,self.errores,self.total]: lay.addWidget(w,1)
    def update(self,total=None,ok=None,err=None,native=None,threads=None,cargables=None,revision=None,no_cargables=None):
        if total is not None: self.total.set_value(total)
        if err is not None: self.errores.set_value(err)
        if cargables is not None: self.cargables.set_value(cargables)
        elif ok is not None: self.cargables.set_value(ok)
        if revision is not None: self.revision.set_value(revision)
        if no_cargables is not None: self.no_cargables.set_value(no_cargables)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Lab PDF Extractor v8.9 — Producción estable")
        self.resize(1280,860); self.setMinimumSize(1120,760)
        self._thread=self._worker=self._test_thread=self._test_worker=None; self._is_paused=False; self._last_output_dir=None; self._applying_profile=False; self._active_step=1; self._highest_step_reached=1
        self._build_ui()

    def _build_ui(self):
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        central=QWidget(); scroll.setWidget(central)
        central.setMinimumWidth(1180); root=QVBoxLayout(central); root.setContentsMargins(16,14,16,10); root.setSpacing(12)
        hdr=QHBoxLayout(); ico=QLabel("⚗"); ico.setStyleSheet(f"font-size:36px;color:{SUCCESS};background:transparent;")
        blk=QVBoxLayout(); t1=QLabel("Laboratory PDF Extractor"); t1.setObjectName("title_label")
        t2=QLabel("Extracción automática de resultados médicos con IA • Producción segura + identidad + métricas + reproceso automático"); t2.setObjectName("subtitle_label")
        blk.addWidget(t1); blk.addWidget(t2); hdr.addWidget(ico); hdr.addSpacing(10); hdr.addLayout(blk); hdr.addStretch()
        badge=card_frame(); badge.setObjectName("security_card"); bl=QHBoxLayout(badge); bl.setContentsMargins(14,8,14,8)
        shield=QLabel("🛡"); shield.setStyleSheet(f"font-size:26px;color:{SUCCESS};"); btxt=QVBoxLayout()
        b1=QLabel("PRODUCCIÓN SEGURA"); b1.setObjectName("security_badge"); b2=QLabel("Configuración optimizada para minimizar errores"); b2.setObjectName("security_sub")
        btxt.addWidget(b1); btxt.addWidget(b2); bl.addWidget(shield); bl.addLayout(btxt); hdr.addWidget(badge); root.addLayout(hdr)
        body=QHBoxLayout(); body.setSpacing(14); root.addLayout(body,1)

        side=QVBoxLayout(); side.setSpacing(10); side_widget=QWidget(); side_widget.setLayout(side); side_widget.setMinimumWidth(250); side_widget.setMaximumWidth(290)
        self.steps=[
            StepWidget(1,"1. Seleccionar carpetas","Define entrada y salida de los PDFs.","📁",True),
            StepWidget(2,"2. Configurar IA","Selecciona proveedor, modelo e ingresa tu API Key.","🧠"),
            StepWidget(3,"3. Modo de velocidad","Ajusta el paralelismo y los límites de velocidad.","⏱"),
            StepWidget(4,"4. Procesar","Inicia la extracción de información con IA.","▶"),
            StepWidget(5,"5. Revisar resultados","Revisa los archivos y valida los resultados.","✓"),
        ]
        for step in self.steps: side.addWidget(step)
        info=card_frame(); il=QVBoxLayout(info); il.setContentsMargins(14,12,14,12)
        it=QLabel("🛡  Seguro y Recomendado"); it.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:13px;font-weight:700;")
        idet=QLabel("Usa configuraciones validadas para producción."); idet.setWordWrap(True); idet.setObjectName("small_help")
        self.info_btn=QPushButton("Más información"); self.info_btn.setFlat(True); self.info_btn.setCursor(Qt.CursorShape.PointingHandCursor); self.info_btn.setStyleSheet(f"QPushButton{{color:#60a5fa;text-align:left;border:none;padding:0;font-size:11px;text-decoration:underline;background:transparent;}} QPushButton:hover{{color:#93c5fd;}}")
        self.info_btn.clicked.connect(self.show_more_info)
        il.addWidget(it); il.addWidget(idet); il.addWidget(self.info_btn); side.addWidget(info); side.addStretch(); body.addWidget(side_widget,0)

        center=QVBoxLayout(); center.setSpacing(12); center_widget=QWidget(); center_widget.setLayout(center); center_widget.setMinimumWidth(460); body.addWidget(center_widget,2)
        card_folders=card_frame(); fl=QVBoxLayout(card_folders); fl.setContentsMargins(16,14,16,14); fl.setSpacing(10)
        title=QLabel("📁  1. Seleccionar carpetas"); title.setObjectName("section_title_blue"); desc=QLabel("Indica las carpetas desde donde se leerán los PDFs y dónde se guardarán los resultados."); desc.setObjectName("small_help")
        fl.addWidget(title); fl.addWidget(desc); g=QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(8)
        self.input_edit=QLineEdit(); self.input_edit.setPlaceholderText("Selecciona la carpeta con archivos PDF...")
        btn_browse=QPushButton("Explorar..."); btn_browse.setFixedWidth(100); btn_browse.clicked.connect(self.select_input_folder)
        self.input_edit.textChanged.connect(lambda _t: self._set_active_step(1))
        self.output_edit=QLineEdit(); self.output_edit.setPlaceholderText("Carpeta donde se guardarán los resultados...")
        self.output_edit.textChanged.connect(lambda _t: self._set_active_step(1))
        btn_output=QPushButton("Explorar..."); btn_output.setFixedWidth(100); btn_output.clicked.connect(self.select_output_folder)
        g.addWidget(QLabel("Entrada (carpeta con PDFs)"),0,0,1,2); g.addWidget(self.input_edit,1,0); g.addWidget(btn_browse,1,1)
        g.addWidget(QLabel("Salida (carpeta de resultados)"),2,0,1,2); g.addWidget(self.output_edit,3,0); g.addWidget(btn_output,3,1); fl.addLayout(g); center.addWidget(card_folders)

        card_ai=card_frame(); al=QVBoxLayout(card_ai); al.setContentsMargins(16,14,16,14); al.setSpacing(10)
        at=QLabel("🧠  2. Configurar IA"); at.setObjectName("section_title_blue"); ad=QLabel("Configura el proveedor, modelo y credenciales de acceso a la API."); ad.setObjectName("small_help")
        al.addWidget(at); al.addWidget(ad); g2=QGridLayout(); g2.setHorizontalSpacing(12); g2.setVerticalSpacing(8)
        self.provider_combo=QComboBox(); self.provider_combo.addItems(["gemini","openai","claude","deepseek"]); self.provider_combo.currentTextChanged.connect(self._on_provider_changed); self.provider_combo.currentTextChanged.connect(lambda _t: self._set_active_step(2))
        self.model_combo=QComboBox(); self.model_combo.setEditable(True); self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.model_combo.currentTextChanged.connect(lambda _t: self._set_active_step(2))
        self.api_edit=QLineEdit(); self.api_edit.setEchoMode(QLineEdit.EchoMode.Password); self.api_edit.setPlaceholderText("AIza... / sk-... / ...")
        self.api_edit.textChanged.connect(lambda _t: self._set_active_step(2))
        self.count_tokens_check=QCheckBox("Medir tokens antes de llamar a IA"); self.count_tokens_check.setChecked(False); self.count_tokens_check.setToolTip("Desactivado reduce latencia porque evita la llamada previa countTokens.")
        g2.addWidget(QLabel("Proveedor"),0,0); g2.addWidget(QLabel("Modelo"),0,1); g2.addWidget(self.provider_combo,1,0); g2.addWidget(self.model_combo,1,1)
        g2.addWidget(QLabel("API Key"),2,0,1,2); g2.addWidget(self.api_edit,3,0,1,2); al.addLayout(g2)
        row_ai=QHBoxLayout(); self.connection_label=QLabel("● Conexión pendiente"); self.connection_label.setObjectName("small_help")
        key_note=QLabel("🔒 La clave se almacena solo en memoria"); key_note.setObjectName("small_help")
        test_btn=QPushButton("Probar conexión"); test_btn.setObjectName("success_btn"); test_btn.clicked.connect(self.test_connection)
        row_ai.addWidget(self.connection_label); row_ai.addStretch(); row_ai.addWidget(key_note); row_ai.addWidget(test_btn); al.addLayout(row_ai); center.addWidget(card_ai)

        card_speed=card_frame(); vl=QVBoxLayout(card_speed); vl.setContentsMargins(16,14,16,14); vl.setSpacing(8)
        vt=QLabel("⏱  3. Modo de velocidad"); vt.setObjectName("section_title_blue"); vd=QLabel("Elige el perfil de procesamiento según precisión y velocidad deseadas."); vd.setObjectName("small_help")
        vl.addWidget(vt); vl.addWidget(vd); self.profile_group=QButtonGroup(self)
        self.radio_safe=QRadioButton("Seguro (máxima precisión, mínimo riesgo de errores)"); self.radio_reco=QRadioButton("Recomendado (balance óptimo entre velocidad y precisión)")
        self.radio_fast=QRadioButton("Rápido (mayor velocidad)"); self.radio_adv=QRadioButton("Avanzado (configuración personalizada)")
        for i,rb in enumerate([self.radio_safe,self.radio_reco,self.radio_fast,self.radio_adv]):
            self.profile_group.addButton(rb,i); vl.addWidget(rb)
            rb.toggled.connect(lambda checked, step=3: checked and self._set_active_step(step))
        self.radio_reco.setChecked(True)
        self.profile_group.idToggled.connect(lambda pid, checked: checked and self._apply_speed_profile(pid))
        adv_grid=QGridLayout(); adv_grid.setHorizontalSpacing(12); adv_grid.setVerticalSpacing(8)
        self.threads_spin=QSpinBox(); self.threads_spin.setRange(1,10); self.threads_spin.setValue(4); self.threads_spin.setMinimumWidth(100); self.threads_spin.valueChanged.connect(self._on_threads_changed); self.threads_spin.valueChanged.connect(self._mark_manual_advanced)
        self.rpm_spin=QSpinBox(); self.rpm_spin.setRange(1,2000); self.rpm_spin.setValue(300); self.rpm_spin.setSuffix(" rpm"); self.rpm_spin.setMinimumWidth(120); self.rpm_spin.valueChanged.connect(self._mark_manual_advanced)
        self.timeout_spin=QSpinBox(); self.timeout_spin.setRange(10,600); self.timeout_spin.setValue(180); self.timeout_spin.setSuffix(" s"); self.timeout_spin.setMinimumWidth(110); self.timeout_spin.valueChanged.connect(self._mark_manual_advanced)
        self.retries_spin=QSpinBox(); self.retries_spin.setRange(1,10); self.retries_spin.setValue(3); self.retries_spin.setMinimumWidth(90); self.retries_spin.valueChanged.connect(self._mark_manual_advanced)
        adv_grid.addWidget(QLabel("Hilos"),0,0); adv_grid.addWidget(QLabel("RPM (límite por minuto)"),0,1)
        adv_grid.addWidget(self.threads_spin,1,0); adv_grid.addWidget(self.rpm_spin,1,1)
        adv_grid.addWidget(QLabel("Timeout"),2,0); adv_grid.addWidget(QLabel("Reintentos"),2,1)
        adv_grid.addWidget(self.timeout_spin,3,0); adv_grid.addWidget(self.retries_spin,3,1)
        adv_grid.setColumnStretch(0,1); adv_grid.setColumnStretch(1,1)
        vl.addLayout(adv_grid); self.threads_info=QLabel(); self.threads_info.setWordWrap(True); self.threads_info.setObjectName("small_help"); self.threads_max_label=QLabel(); self.threads_max_label.setObjectName("small_help")
        hl_info=QHBoxLayout(); hl_info.addWidget(QLabel("ℹ")); hl_info.addWidget(self.threads_info,1); hl_info.addWidget(self.threads_max_label); vl.addLayout(hl_info)
        preset_help=QLabel("Los perfiles cargan valores sugeridos, pero puedes ajustarlos manualmente en cualquier momento.")
        preset_help.setObjectName("small_help")
        vl.addWidget(preset_help)
        self.count_tokens_check.stateChanged.connect(lambda _s: self._set_active_step(3))
        vl.addWidget(self.count_tokens_check); center.addWidget(card_speed); center.addStretch()
        right=QVBoxLayout(); right.setSpacing(12); right_widget=QWidget(); right_widget.setLayout(right); right_widget.setMinimumWidth(390); body.addWidget(right_widget,2)
        card_status=card_frame(); stl=QVBoxLayout(card_status); stl.setContentsMargins(16,14,16,14); stl.setSpacing(12)
        stt=QLabel("Estado del proceso"); stt.setObjectName("section_title"); stl.addWidget(stt); self.stats=StatsWidget(); stl.addWidget(self.stats); right.addWidget(card_status)
        card_prog=card_frame(); pl=QVBoxLayout(card_prog); pl.setContentsMargins(16,14,16,14); pl.setSpacing(8)
        prow=QHBoxLayout(); pt=QLabel("Progreso"); pt.setObjectName("section_title"); self.status_pill=QLabel("EN ESPERA"); self.status_pill.setObjectName("status_pill"); prow.addWidget(pt); prow.addStretch(); prow.addWidget(self.status_pill); pl.addLayout(prow)
        row_state=QHBoxLayout(); row_state.addWidget(QLabel("Estado actual")); row_state.addStretch(); self.stage_label=QLabel("En espera..."); self.stage_label.setObjectName("file_label"); row_state.addWidget(self.stage_label); pl.addLayout(row_state)
        self.progress_bar=QProgressBar(); self.progress_bar.setRange(0,100); self.progress_bar.setValue(0); self.progress_bar.setFormat('%p%'); self.progress_bar.setTextVisible(True); self.progress_bar.setFixedHeight(18); pl.addWidget(self.progress_bar)
        row_time=QHBoxLayout(); row_time.addWidget(QLabel("Tiempo transcurrido")); self.elapsed_label=QLabel("—"); self.elapsed_label.setObjectName("file_label"); row_time.addWidget(self.elapsed_label); row_time.addStretch(); pl.addLayout(row_time)
        self.file_label=QLabel("Archivo actual: —"); self.file_label.setObjectName("file_label"); self.file_label.setWordWrap(True); pl.addWidget(self.file_label)
        self.speed_label=QLabel("Velocidad promedio: —"); self.speed_label.setObjectName("small_help"); pl.addWidget(self.speed_label); right.addWidget(card_prog)
        card_log=card_frame(); ll=QVBoxLayout(card_log); ll.setContentsMargins(16,14,16,14); ll.setSpacing(8)
        log_row=QHBoxLayout(); lt=QLabel("Log"); lt.setObjectName("section_title"); btn_clear=QPushButton("Limpiar"); btn_clear.setFixedWidth(90); btn_clear.clicked.connect(self.log_view_clear_safe); log_row.addWidget(lt); log_row.addStretch(); log_row.addWidget(btn_clear); ll.addLayout(log_row)
        self.log_view=QPlainTextEdit(); self.log_view.setReadOnly(True); self.log_view.setMinimumHeight(210); self.log_view.setPlaceholderText("El log aparecerá aquí durante el procesamiento."); ll.addWidget(self.log_view); right.addWidget(card_log,1)
        footer=QFrame(); footer.setObjectName("footer_bar"); fbar=QHBoxLayout(footer); fbar.setContentsMargins(16,10,16,10); fbar.setSpacing(12)
        self.summary_label=QLabel("Sin procesar."); self.summary_label.setObjectName("summary_label")
        self.open_results_btn=QPushButton("📁  Abrir resultados"); self.open_results_btn.setMinimumWidth(160); self.open_results_btn.setFixedHeight(46); self.open_results_btn.clicked.connect(self.open_results_folder)
        self.reprocess_errors_btn=QPushButton("↻  Reprocesar errores"); self.reprocess_errors_btn.setMinimumWidth(175); self.reprocess_errors_btn.setFixedHeight(46); self.reprocess_errors_btn.setToolTip("Reprocesa solo errores temporales: 503, timeout, red o alta demanda."); self.reprocess_errors_btn.clicked.connect(self.reprocess_errors)
        self.pause_btn=QPushButton("Ⅱ  Pausar"); self.pause_btn.setObjectName("pause_btn"); self.pause_btn.setFixedHeight(46); self.pause_btn.setMinimumWidth(155); self.pause_btn.setEnabled(False); self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn=QPushButton("■  Detener"); self.stop_btn.setObjectName("danger_btn"); self.stop_btn.setFixedHeight(46); self.stop_btn.setMinimumWidth(170); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.stop_processing)
        self.start_btn=QPushButton("▶  Procesar PDFs"); self.start_btn.setObjectName("primary_btn"); self.start_btn.setFixedHeight(46); self.start_btn.setMinimumWidth(230); self.start_btn.clicked.connect(self.start_processing)
        fbar.addWidget(self.open_results_btn); fbar.addWidget(self.reprocess_errors_btn); fbar.addWidget(self.summary_label,1); fbar.addWidget(self.pause_btn); fbar.addWidget(self.stop_btn); fbar.addWidget(self.start_btn); root.addWidget(footer)
        self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Listo — selecciona carpeta, configura la API y procesa PDFs.")
        self._on_provider_changed(self.provider_combo.currentText()); self._apply_speed_profile(self.profile_group.checkedId()); self._set_status_pill('EN ESPERA','ready')

    def _set_active_step(self, step_number:int):
        step_number=max(1,min(5,step_number))
        self._active_step = step_number
        self._highest_step_reached = max(getattr(self, "_highest_step_reached", 1), step_number)
        for idx, step in enumerate(self.steps, start=1):
            if idx == step_number:
                step.set_state("active")
            elif idx < self._highest_step_reached:
                step.set_state("completed")
            else:
                step.set_state("pending")

    def _set_status_pill(self, text:str, kind:str="info"):
        self.status_pill.setText(text)
        palette = {
            "running": (SUCCESS, "rgba(16,185,129,0.14)", "rgba(16,185,129,0.32)"),
            "ready": (ACCENT, "rgba(59,130,246,0.12)", "rgba(59,130,246,0.30)"),
            "paused": (WARNING, "rgba(245,158,11,0.13)", "rgba(245,158,11,0.32)"),
            "stopped": (TEXT_MUTED, "rgba(126,141,168,0.10)", "rgba(126,141,168,0.28)"),
            "done": (SUCCESS, "rgba(16,185,129,0.16)", "rgba(16,185,129,0.42)"),
            "error": (ERROR_COLOR, "rgba(239,68,68,0.13)", "rgba(239,68,68,0.35)"),
            "info": (ACCENT, "rgba(59,130,246,0.12)", "rgba(59,130,246,0.30)"),
        }
        color,bg,border = palette.get(kind, palette["info"])
        self.status_pill.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:800;padding:4px 10px;"
            f"border-radius:12px;background-color:{bg};border:1px solid {border};"
        )

    def show_more_info(self):
        QMessageBox.information(
            self,
            "Configuración segura y recomendada",
            "Perfiles disponibles:\n\n"
            "• Seguro: prioriza estabilidad y menor riesgo de errores.\n"
            "• Recomendado: equilibrio entre velocidad y precisión.\n"
            "• Rápido: mayor velocidad, ideal para API de pago y lotes grandes.\n"
            "• Avanzado: permite ajustar manualmente hilos, RPM, timeout y reintentos.\n\n"
            "Sugerencia:\n"
            "Para producción usa Seguro o Recomendado, y pasa a Avanzado solo si necesitas ajustar el rendimiento de forma manual."
        )

    def _mark_manual_advanced(self, *_args):
        if getattr(self, "_applying_profile", False):
            return
        if not self.radio_adv.isChecked():
            self.radio_adv.setChecked(True)
        self._refresh_thread_ui(self.provider_combo.currentText())

    def _on_provider_changed(self,provider:str):
        current=self.model_combo.currentText().strip(); self.model_combo.clear()
        for m in MODELS.get(provider,[]): self.model_combo.addItem(m)
        if current: self.model_combo.setEditText(current)
        elif self.model_combo.count(): self.model_combo.setCurrentIndex(0)
        max_t=safe_max_threads(provider); self.threads_spin.setMaximum(max_t)
        if self.threads_spin.value()>max_t: self.threads_spin.setValue(max_t)
        self._refresh_thread_ui(provider)
    def _apply_speed_profile(self,profile_id:int):
        provider=self.provider_combo.currentText(); max_t=safe_max_threads(provider)
        self._applying_profile=True
        try:
            if profile_id==0:
                values=(min(2,max_t),60,180,3)
            elif profile_id==1:
                values=(min(4,max_t),180,180,3)
            elif profile_id==2:
                values=(min(6,max_t),300,180,2)
            else:
                self._refresh_thread_ui(provider)
                return
            self.threads_spin.setValue(values[0]); self.rpm_spin.setValue(values[1]); self.timeout_spin.setValue(values[2]); self.retries_spin.setValue(values[3])
        finally:
            self._applying_profile=False
        profile_names={0:"Seguro",1:"Recomendado",2:"Rápido",3:"Avanzado"}
        self.statusBar().showMessage(f"Perfil de velocidad: {profile_names.get(profile_id,'Avanzado')} · Hilos {self.threads_spin.value()} · RPM {self.rpm_spin.value()}")
        self._refresh_thread_ui(provider)
    def _set_advanced_enabled(self,enabled:bool):
        # Conservado por compatibilidad; los controles quedan siempre editables.
        for w in [self.threads_spin,self.rpm_spin,self.timeout_spin,self.retries_spin]:
            w.setEnabled(True)
    def _on_threads_changed(self,value:int):
        self._refresh_thread_ui(self.provider_combo.currentText())
    def _refresh_thread_ui(self,provider:str):
        max_t=safe_max_threads(provider); cur=self.threads_spin.value(); self.threads_max_label.setText(f"Máx. seguro para {provider}: {max_t}")
        if cur==1: info="Un hilo: procesamiento secuencial, máxima estabilidad."
        elif cur<=3: info=f"{cur} hilos: velocidad moderada y bajo riesgo de saturación."
        elif cur<=5: info=f"{cur} hilos: recomendado para pruebas grandes con API de pago."
        else: info=f"{cur} hilos: modo rápido; vigila errores 429/503 y memoria."
        self.threads_info.setText(info)

    def select_input_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Seleccionar carpeta con PDFs")
        if folder:
            self.input_edit.setText(folder); self._set_active_step(1)
            self.append_log(f"📁 Entrada: {folder}"); self.statusBar().showMessage(f"Entrada: {folder}")
    def select_output_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"Seleccionar carpeta de salida")
        if folder:
            self.output_edit.setText(folder); self._last_output_dir=folder; self._set_active_step(1)
            self.append_log(f"📁 Salida: {folder}"); self.statusBar().showMessage(f"Salida: {folder}")
    def open_results_folder(self):
        folder=self._last_output_dir or self.output_edit.text().strip()
        if not folder: QMessageBox.information(self,"Sin carpeta","Todavía no hay carpeta de resultados seleccionada o generada."); return
        path=Path(folder)
        if not path.exists(): QMessageBox.warning(self,"No existe",f"La carpeta no existe:\n{path}"); return
        try:
            if sys.platform.startswith("win"): os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            else: subprocess.Popen(["xdg-open",str(path)])
        except Exception as exc: QMessageBox.warning(self,"No se pudo abrir",f"No se pudo abrir la carpeta:\n{exc}")
    def build_ai_config(self)->AIConfig:
        return AIConfig(provider=self.provider_combo.currentText(),model=self.model_combo.currentText().strip(),api_key=self.api_edit.text().strip(),timeout_seconds=self.timeout_spin.value(),max_retries=self.retries_spin.value(),requests_per_minute=self.rpm_spin.value(),enable_token_count=self.count_tokens_check.isChecked(),temperature=0.0)
    def build_ocr_config(self)->OCRConfig: return OCRConfig()
    def log_view_clear_safe(self): self.log_view.clear()
    def append_log(self,text:str): self.log_view.appendPlainText(text); self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
    def validate_inputs(self)->bool:
        if not self.input_edit.text().strip(): QMessageBox.warning(self,"Falta carpeta","Selecciona la carpeta de PDFs."); return False
        if not Path(self.input_edit.text().strip()).exists(): QMessageBox.warning(self,"Carpeta inválida","La carpeta de entrada no existe."); return False
        out_txt=self.output_edit.text().strip()
        if out_txt:
            try: Path(out_txt).mkdir(parents=True,exist_ok=True)
            except Exception as exc: QMessageBox.warning(self,"Carpeta de salida inválida",f"No se pudo crear/acceder a la salida:\n{exc}"); return False
        if not self.model_combo.currentText().strip(): QMessageBox.warning(self,"Falta modelo","Ingresa o selecciona un modelo."); return False
        if not self.api_edit.text().strip(): QMessageBox.warning(self,"Falta API key","Ingresa la API key."); return False
        return True
    @staticmethod
    def _count_csv_rows(path:Path)->int:
        try:
            if not path.exists(): return 0
            with path.open("r",encoding="utf-8-sig",newline="") as f: return max(0,sum(1 for _ in csv.reader(f))-1)
        except Exception: return 0
    def test_connection(self):
        if not self.model_combo.currentText().strip() or not self.api_edit.text().strip(): QMessageBox.warning(self,"Faltan datos","Ingresa modelo y API key."); return
        self._set_active_step(2)
        self.append_log("🔗 Probando conexión con la API..."); self.stage_label.setText("Verificando API..."); self._set_status_pill("VALIDANDO","info"); self.start_btn.setEnabled(False)
        self._test_thread=QThread(); self._test_worker=ConnectionTestWorker(self.build_ai_config()); self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run); self._test_worker.progress.connect(self.append_log); self._test_worker.finished.connect(self.on_test_finished)
        self._test_worker.finished.connect(self._test_thread.quit); self._test_thread.finished.connect(self._test_thread.deleteLater); self._test_thread.start()
    def on_test_finished(self,ok:bool,msg:str):
        self.start_btn.setEnabled(True); self._set_active_step(3 if ok else 2)
        self.append_log(("✅ " if ok else "❌ ")+msg); self.stage_label.setText("API validada OK" if ok else "Error de conexión"); self._set_status_pill("LISTO","ready" if ok else "error")
        self.connection_label.setText("● Conexión verificada correctamente" if ok else "● Error de conexión"); self.connection_label.setObjectName("green_help" if ok else "small_help"); self.connection_label.style().unpolish(self.connection_label); self.connection_label.style().polish(self.connection_label)
        self.statusBar().showMessage("Conexión OK" if ok else "Error de conexión"); (QMessageBox.information if ok else QMessageBox.warning)(self,"Resultado",msg)
    def reprocess_errors(self):
        if not self.validate_inputs():
            return
        output = self.output_edit.text().strip() or self._last_output_dir
        if not output:
            QMessageBox.warning(self, "Falta carpeta de resultados", "Selecciona la carpeta de salida donde está retry_queue.json o errores_reprocesables.csv.")
            return
        out_path = Path(output)
        if not out_path.exists():
            QMessageBox.warning(self, "Carpeta inválida", f"No existe la carpeta de resultados:\n{out_path}")
            return
        retry_file = out_path / "retry_queue.json"
        errors_csv = out_path / "errores_reprocesables.csv"
        if not retry_file.exists() and not errors_csv.exists():
            QMessageBox.information(self, "Sin cola de reproceso", "No encontré retry_queue.json ni errores_reprocesables.csv en la carpeta de resultados.")
            return
        threads = min(2, self.threads_spin.value())
        self._set_active_step(4)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.reprocess_errors_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self._set_status_pill("REPROCESANDO", "running")
        self.stage_label.setText("Reprocesando errores temporales...")
        self.append_log("↻ Reproceso manual de errores temporales iniciado.")
        self._test_thread = QThread()
        self._test_worker = ReprocessErrorsWorker(
            output,
            self.input_edit.text().strip(),
            self.build_ai_config(),
            self.build_ocr_config(),
            threads=threads,
        )
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.progress.connect(self.on_progress)
        self._test_worker.finished.connect(self.on_reprocess_finished)
        self._test_worker.error.connect(self.on_error)
        self._test_worker.finished.connect(self._test_thread.quit)
        self._test_worker.error.connect(self._test_thread.quit)
        self._test_thread.finished.connect(self._test_thread.deleteLater)
        self._test_thread.start()

    def on_reprocess_finished(self, summary:dict):
        self.start_btn.setEnabled(True)
        self.reprocess_errors_btn.setEnabled(True)
        self._set_active_step(5)
        self._set_status_pill("COMPLETADO", "done")
        self.stage_label.setText("Reproceso completado")
        self.progress_bar.setValue(100)
        out = summary.get("output_dir", self.output_edit.text().strip())
        self._last_output_dir = out
        self.append_log(f"✅ Reproceso de errores finalizado. Salida: {out}")
        QMessageBox.information(self, "Reproceso completado", f"Reproceso de errores finalizado.\n\nSalida:\n{out}")

    def start_processing(self):
        if not self.validate_inputs(): return
        self._set_active_step(4)
        threads=self.threads_spin.value(); provider=self.provider_combo.currentText(); max_t=safe_max_threads(provider)
        self.progress_bar.setValue(0); self.log_view.clear(); self.start_btn.setEnabled(False); self.pause_btn.setEnabled(True); self.pause_btn.setText("Ⅱ  Pausar"); self.stop_btn.setEnabled(True); self._is_paused=False
        self.stats.update(total=0,ok=0,err=0,cargables=0,revision=0,no_cargables=0)
        self.summary_label.setText(f"{provider.upper()} · {self.model_combo.currentText().strip()} · {threads} hilo{'s' if threads>1 else ''} · {self.rpm_spin.value()} rpm · tokens={'sí' if self.count_tokens_check.isChecked() else 'no'}")
        self.stage_label.setText("Iniciando..."); self._set_status_pill("EN PROCESO","running"); self.file_label.setText("Archivo actual: preparando..."); self.elapsed_label.setText("—"); self.speed_label.setText("Velocidad promedio: —")
        self.statusBar().showMessage(f"Procesando con {threads} hilo{'s' if threads>1 else ''}...")
        self.append_log("🚀 Proceso iniciado por el usuario"); self.append_log(f"⚙ Hilos solicitados: {threads} · Máx. seguro {provider}: {max_t}"); self.append_log(f"📁 Entrada: {self.input_edit.text().strip()}")
        if self.output_edit.text().strip(): self.append_log(f"📁 Salida: {self.output_edit.text().strip()}")
        self.append_log(f"⚙ RPM: {self.rpm_spin.value()} · Medir tokens: {self.count_tokens_check.isChecked()}")
        self._thread=QThread(); self._worker=ProcessWorker(self.input_edit.text().strip(),self.build_ai_config(),self.build_ocr_config(),threads=threads,output_dir=self.output_edit.text().strip() or None)
        self._worker.moveToThread(self._thread); self._thread.started.connect(self._worker.run); self._worker.progress.connect(self.on_progress); self._worker.finished.connect(self.on_finished); self._worker.error.connect(self.on_error)
        self._worker.finished.connect(self._thread.quit); self._worker.error.connect(self._thread.quit); self._thread.finished.connect(self._thread.deleteLater); self._thread.start()
    def toggle_pause(self):
        if not self._worker: return
        if not self._is_paused:
            self._worker.pause(); self._is_paused=True; self.pause_btn.setText("▶  Retomar"); self.stage_label.setText("Pausando..."); self._set_status_pill("PAUSA","paused")
            self.statusBar().showMessage("Pausa solicitada. Terminará el PDF en curso y no iniciará nuevos hasta retomar."); self.append_log("⏸ Pausa solicitada: el PDF en curso puede terminar; luego queda en espera.")
        else:
            self._worker.resume(); self._is_paused=False; self.pause_btn.setText("Ⅱ  Pausar"); self.stage_label.setText("Reanudando..."); self._set_status_pill("EN PROCESO","running"); self.statusBar().showMessage("Proceso reanudado."); self.append_log("▶ Proceso reanudado.")
    def stop_processing(self):
        if not self._worker: return
        self._worker.cancel(); self.stop_btn.setEnabled(False); self.pause_btn.setEnabled(False); self.stage_label.setText("Deteniendo..."); self._set_status_pill("DETENIENDO","stopped")
        self.statusBar().showMessage("Detención solicitada. El PDF en curso puede terminar; el avance queda en cache."); self.append_log("⏹ Detención solicitada: se conserva cache/índice para retomar luego.")
    def on_progress(self,payload:dict):
        stage=payload.get("stage",""); message=payload.get("message",""); percent=int(payload.get("percent",self.progress_bar.value())); filename=payload.get("filename",""); current=payload.get("current"); total=payload.get("total")
        if stage == "finished":
            self._set_active_step(5)
        else:
            self._set_active_step(4)
        self.progress_bar.setValue(max(0,min(100,percent)))
        if stage: self.stage_label.setText(stage.replace("_"," ").capitalize())
        if filename and current and total:
            self.file_label.setText(f"Archivo actual: {filename}  ({current}/{total})")
            self.elapsed_label.setText(f"Avance: {current}/{total}")
        elif filename:
            self.file_label.setText(f"Archivo actual: {filename}")
        if message: self.append_log(message)
        if stage=="paused": self.stage_label.setText("Pausado"); self._set_status_pill("PAUSA","paused"); self.statusBar().showMessage("Pausado. Usa Retomar para continuar.")
        elif stage=="resumed": self.stage_label.setText("Reanudado"); self._set_status_pill("EN PROCESO","running"); self.statusBar().showMessage("Proceso reanudado.")
        elif stage=="cancelled_file": self.stage_label.setText("Detenido"); self._set_status_pill("DETENIDO","stopped")
        elif stage=="done_file":
            try: current_ok=int(self.stats.cargables.value.text())
            except Exception: current_ok=0
            self.stats.update(cargables=current_ok+1)
        elif stage=="error_file":
            try: current_err=int(self.stats.errores.value.text())
            except Exception: current_err=0
            self.stats.update(err=current_err+1)
        elif stage=="scan" and total: self.stats.update(total=total)
    def on_finished(self,summary:dict):
        self._set_active_step(5)
        self.start_btn.setEnabled(True); self.reprocess_errors_btn.setEnabled(True); self.pause_btn.setEnabled(False); self.stop_btn.setEnabled(False); self._is_paused=False; self.progress_bar.setValue(100); self.stage_label.setText("Completado OK"); self._set_status_pill("COMPLETADO","done"); self.file_label.setText("Archivo actual: —")
        th=summary.get("threads_used",1); out=summary.get("output_dir",""); self._last_output_dir=out or self.output_edit.text().strip() or None; out_path=Path(out) if out else None
        cargables=self._count_csv_rows(out_path/"sairc_cargable.csv") if out_path else summary.get("ok",0); revision=self._count_csv_rows(out_path/"sairc_revision.csv") if out_path else summary.get("revisar",0); no_cargables=self._count_csv_rows(out_path/"sairc_no_cargable.csv") if out_path else 0
        total=summary.get("total",0); errores=summary.get("errors",0); self.stats.update(total=total,cargables=cargables,revision=revision,no_cargables=no_cargables,err=errores)
        avg=summary.get("avg_seconds_per_pdf") or 0
        if avg: self.speed_label.setText(f"Tiempo promedio por PDF: {avg} s")
        self.statusBar().showMessage(f"Completado · {th} hilo{'s' if th>1 else ''} · Salida: {out}")
        msg=(f"Proceso finalizado.\n\n  Hilos usados       : {th}\n  Total archivos     : {total}\n  Procesados OK      : {summary.get('success')}\n  Cargables SAIRC    : {cargables}\n  En revisión        : {revision}\n  No cargables       : {no_cargables}\n  Errores técnicos   : {errores}\n  Reutilizados cache : {summary.get('skipped_success',0)}\n\nSalida:\n{out}")
        self.append_log("\n✅ "+msg.replace("\n","\n  ")); QMessageBox.information(self,"Proceso completado",msg)
    def on_error(self,error_text:str):
        self._set_active_step(4)
        self.start_btn.setEnabled(True); self.reprocess_errors_btn.setEnabled(True); self.pause_btn.setEnabled(False); self.stop_btn.setEnabled(False); self._is_paused=False; self.stage_label.setText("Error"); self._set_status_pill("ERROR","error")
        self.statusBar().showMessage(f"Error: {error_text[:80]}"); self.append_log(f"❌ ERROR GENERAL: {error_text}"); QMessageBox.critical(self,"Error",error_text)

def main():
    logging.basicConfig(level=logging.DEBUG,format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    app=QApplication(sys.argv); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    palette=QPalette(); palette.setColor(QPalette.ColorRole.Window,QColor(DARK_BG)); palette.setColor(QPalette.ColorRole.WindowText,QColor(TEXT_PRIMARY)); palette.setColor(QPalette.ColorRole.Base,QColor(PANEL_BG)); palette.setColor(QPalette.ColorRole.AlternateBase,QColor(CARD_BG)); palette.setColor(QPalette.ColorRole.Text,QColor(TEXT_PRIMARY)); palette.setColor(QPalette.ColorRole.Button,QColor(CARD_BG)); palette.setColor(QPalette.ColorRole.ButtonText,QColor(TEXT_PRIMARY)); palette.setColor(QPalette.ColorRole.Highlight,QColor(ACCENT)); palette.setColor(QPalette.ColorRole.HighlightedText,QColor("#ffffff")); app.setPalette(palette)
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__": main()
