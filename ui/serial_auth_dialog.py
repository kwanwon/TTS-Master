#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial Authentication Dialog for TTS Master
- Modern PyQt6 modal dialog for entering license key
- Visual feedback during verification (Render server communication)
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QProgressBar, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from core.serial_auth import SerialAuth

class SerialCheckThread(QThread):
    finished = pyqtSignal(bool, str, str)  # is_valid, message, expiry_date
    
    def __init__(self, serial_auth: SerialAuth, serial_number: str):
        super().__init__()
        self.serial_auth = serial_auth
        self.serial_number = serial_number
        
    def run(self):
        is_valid, msg, expiry = self.serial_auth.validate(self.serial_number)
        self.finished.emit(is_valid, msg, expiry or "")

class SerialAuthDialog(QDialog):
    """Popup dialog displayed when serial key is missing or expired."""
    
    def __init__(self, parent=None, serial_auth=None):
        super().__init__(parent)
        self.serial_auth = serial_auth or SerialAuth()
        self.check_thread = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("🔐 라이선스 시리얼 번호 인증")
        self.setFixedSize(460, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(12)
        
        # Title
        title_label = QLabel("AI 마스터 라이선스 인증")
        title_font = QFont("Apple SD Gothic Neo", 16, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)
        
        # Subtitle
        desc_label = QLabel("프로그램 사용을 위해 발급받으신 시리얼 번호를 입력해주세요.")
        desc_label.setFont(QFont("Apple SD Gothic Neo", 11))
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(desc_label)
        
        # Serial input field
        self.input_serial = QLineEdit()
        self.input_serial.setPlaceholderText("예: AIMASTER-XXXX-XXXX-XXXX")
        self.input_serial.setFont(QFont("Monospace", 12))
        self.input_serial.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_serial.setStyleSheet("""
            QLineEdit {
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                padding: 8px;
                background-color: #ffffff;
                color: #2c3e50;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
        """)
        self.input_serial.returnPressed.connect(self.on_verify_clicked)
        layout.addWidget(self.input_serial)
        
        # Status / Progress indicator
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Button bar
        btn_layout = QHBoxLayout()
        self.btn_verify = QPushButton("🔑 시리얼 인증하기")
        self.btn_verify.setFont(QFont("Apple SD Gothic Neo", 12, QFont.Weight.Bold))
        self.btn_verify.setStyleSheet("""
            QPushButton {
                background-color: #2980b9;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
            }
            QPushButton:hover {
                background-color: #3498db;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.btn_verify.clicked.connect(self.on_verify_clicked)
        
        self.btn_close = QPushButton("종료")
        self.btn_close.setFont(QFont("Apple SD Gothic Neo", 12))
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #ecf0f1;
                color: #7f8c8d;
                border: 1px solid #bdc3c7;
                border-radius: 6px;
                padding: 10px 18px;
            }
            QPushButton:hover {
                background-color: #bdc3c7;
                color: #2c3e50;
            }
        """)
        self.btn_close.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_verify)
        layout.addLayout(btn_layout)
        
        # Preload cached serial if exists
        cached = self.serial_auth.load_config()
        if cached.get("serial_number"):
            self.input_serial.setText(cached["serial_number"])
            
    def on_verify_clicked(self):
        serial = self.input_serial.text().strip()
        if not serial:
            self.status_label.setText("시리얼 번호를 입력해주세요.")
            return
            
        self.input_serial.setEnabled(False)
        self.btn_verify.setEnabled(False)
        self.status_label.setStyleSheet("color: #2980b9; font-size: 11px;")
        self.status_label.setText("서버에 인증 요청 중입니다... (최대 30초 소요)")
        self.progress_bar.show()
        
        self.check_thread = SerialCheckThread(self.serial_auth, serial)
        self.check_thread.finished.connect(self._on_check_finished)
        self.check_thread.start()
        
    def _on_check_finished(self, is_valid: bool, msg: str, expiry: str):
        self.progress_bar.hide()
        self.input_serial.setEnabled(True)
        self.btn_verify.setEnabled(True)
        
        if is_valid:
            info = msg
            if expiry:
                info += f"\n만료일: {expiry}"
            QMessageBox.information(self, "인증 완료", info)
            self.accept()
        else:
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.status_label.setText(msg)
            QMessageBox.warning(self, "인증 실패", msg)
