import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QTextEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt

from core.ai_generator import (
    load_gemini_env,
    save_gemini_api_key,
    load_common_settings,
    save_common_settings,
    extract_text_from_file,
    fetch_text_from_url,
    AIGenerator,
)


class GlobalAISettingsDialog(QDialog):
    """
    프로그램 전체에서 공통으로 사용하는 초간편 통합 설정창:
    1) Google Gemini API Key (AI 대본 및 현장 영어 구령 자동생성용)
    2) 구글 드라이브(Docs/Sheets/Drive) 링크 또는 내 컴퓨터 수련계획표 파일 불러오기
    3) 공통 수련계획표 / 수련 기본 정보 편집 및 저장
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI API 키 및 공통 수련자료 통합 설정")
        self.resize(720, 620)
        self._init_ui()
        self._load_current_values()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top_guide = QLabel(
            "💡 이곳에 API 키와 수련계획표(구글 드라이브 링크·파일·메모)를 한 번만 등록해 두면,\n"
            "   [메인 대본 생성창]과 [서킷 인터벌 생성창] 어디서나 복잡하게 다시 넣을 필요 없이 바로 사용됩니다."
        )
        top_guide.setStyleSheet(
            "background-color: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; "
            "border-radius: 6px; padding: 8px 10px; font-weight: bold; font-size: 12px;"
        )
        layout.addWidget(top_guide)

        # ------------------------------------------------------------------
        # 1. Google Gemini API 키 설정
        # ------------------------------------------------------------------
        g_key = QGroupBox("🔑 1. Google Gemini API Key 설정 (AI 대본 및 현장 영어 자동완성)")
        g_key.setStyleSheet("QGroupBox { font-weight: bold; }")
        l_key = QVBoxLayout(g_key)

        h_key = QHBoxLayout()
        h_key.addWidget(QLabel("API Key:"))
        self.txt_api_key = QLineEdit()
        self.txt_api_key.setPlaceholderText("Google AI Studio에서 발급받은 API 키 입력 (예: AIzaSy...)")
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_api_key.setStyleSheet("padding: 6px; font-size: 13px;")
        h_key.addWidget(self.txt_api_key, stretch=1)

        self.cb_show_key = QCheckBox("키 보기")
        self.cb_show_key.toggled.connect(self._on_toggle_show_key)
        h_key.addWidget(self.cb_show_key)

        self.btn_test_key = QPushButton("🔍 연결 확인")
        self.btn_test_key.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px;"
        )
        self.btn_test_key.clicked.connect(self._on_test_api_key)
        h_key.addWidget(self.btn_test_key)
        l_key.addLayout(h_key)

        self.lbl_key_status = QLabel("상태: 저장된 API 키를 확인합니다.")
        self.lbl_key_status.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
        l_key.addWidget(self.lbl_key_status)

        h_api_helpers = QHBoxLayout()
        self.btn_open_aistudio = QPushButton("🌐 무료 Gemini API Key 발급받기 (Google AI Studio)")
        self.btn_open_aistudio.setToolTip("구글 공식 사이트(aistudio.google.com)로 이동하여 무료 API 키를 30초 만에 발급받습니다.")
        self.btn_open_aistudio.setStyleSheet(
            "background-color: #059669; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_open_aistudio.clicked.connect(self._on_open_aistudio)
        h_api_helpers.addWidget(self.btn_open_aistudio)

        self.btn_open_api_manual = QPushButton("📖 API 발급 & 프로그램 설명서 보기")
        self.btn_open_api_manual.setToolTip("온라인 설명서의 Gemini API 발급 가이드 페이지를 웹 브라우저로 엽니다.")
        self.btn_open_api_manual.setStyleSheet(
            "background-color: #f59e0b; color: #0b0f19; font-weight: bold; padding: 6px 12px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_open_api_manual.clicked.connect(self._on_open_api_manual)
        h_api_helpers.addWidget(self.btn_open_api_manual)
        l_key.addLayout(h_api_helpers)

        layout.addWidget(g_key)

        # ------------------------------------------------------------------
        # 2. 구글 드라이브 링크 & 수련계획표 파일 불러오기
        # ------------------------------------------------------------------
        g_source = QGroupBox("🌐 2. 공통 수련계획표 불러오기 (구글 드라이브 링크 또는 파일)")
        g_source.setStyleSheet("QGroupBox { font-weight: bold; }")
        l_source = QVBoxLayout(g_source)

        # (A) 구글 드라이브 링크
        h_link = QHBoxLayout()
        h_link.addWidget(QLabel("🔗 구글 드라이브 링크:"))
        self.txt_gdrive_url = QLineEdit()
        self.txt_gdrive_url.setPlaceholderText(
            "구글 문서(Docs)·시트(Sheets)·드라이브 공유 링크 붙여넣기 (https://docs.google.com/...)"
        )
        self.txt_gdrive_url.setStyleSheet("padding: 6px; font-size: 13px;")
        h_link.addWidget(self.txt_gdrive_url, stretch=1)

        self.btn_fetch_link = QPushButton("📥 링크 내용 가져오기")
        self.btn_fetch_link.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px;"
        )
        self.btn_fetch_link.clicked.connect(self._on_fetch_gdrive_link)
        h_link.addWidget(self.btn_fetch_link)
        l_source.addLayout(h_link)

        # (B) 내 컴퓨터 파일
        h_file = QHBoxLayout()
        h_file.addWidget(QLabel("📂 내 컴퓨터 파일:"))
        self.txt_file_path = QLineEdit()
        self.txt_file_path.setReadOnly(True)
        self.txt_file_path.setPlaceholderText("선택된 파일 없음 (.txt, .docx, .md, .csv 지원)")
        self.txt_file_path.setStyleSheet("padding: 6px; font-size: 12px; background-color: #f8fafc; color: #334155;")
        h_file.addWidget(self.txt_file_path, stretch=1)

        self.btn_browse_file = QPushButton("📂 파일 찾아보기")
        self.btn_browse_file.setStyleSheet(
            "background-color: #0d9488; color: white; font-weight: bold; padding: 6px 12px; border-radius: 5px;"
        )
        self.btn_browse_file.clicked.connect(self._on_browse_file)
        h_file.addWidget(self.btn_browse_file)
        l_source.addLayout(h_file)

        layout.addWidget(g_source)

        # ------------------------------------------------------------------
        # 3. 공통 수련 정보 / 불러온 계획표 내용 (넓은 편집창)
        # ------------------------------------------------------------------
        g_info = QGroupBox("📝 3. 공통 수련계획표 / 수업 기본 정보 (직접 입력 및 자유 수정 가능)")
        g_info.setStyleSheet("QGroupBox { font-weight: bold; }")
        l_info = QVBoxLayout(g_info)

        h_info_top = QHBoxLayout()
        lbl_info_desc = QLabel(
            "아래 내용은 위 링크·파일에서 불러오거나 직접 적어둘 수 있습니다. (AI 대본 생성 시 공통 참고 자료로 활용)"
        )
        lbl_info_desc.setStyleSheet("color: #475569; font-size: 12px; font-weight: normal;")
        h_info_top.addWidget(lbl_info_desc)
        h_info_top.addStretch()

        btn_clear_info = QPushButton("🗑️ 내용 비우기")
        btn_clear_info.setStyleSheet("padding: 3px 8px; font-size: 11px;")
        btn_clear_info.clicked.connect(self._on_clear_info)
        h_info_top.addWidget(btn_clear_info)
        l_info.addLayout(h_info_top)

        self.txt_common_info = QTextEdit()
        self.txt_common_info.setMinimumHeight(190)
        self.txt_common_info.setPlaceholderText(
            "여기에 주간/일일 수련계획표 내용이나 주요 운동 구성을 자유롭게 적어두세요.\n"
            "예시:\n"
            "- 이번 주 집중 훈련: 팔굽혀펴기 2회 + 빠른 발차기 5회 + 버피 2회 서킷\n"
            "- 중점 지도 사항: 낙법 후 빠르게 일어나서 다음 동작 연결, 영어 구령은 쉽고 활기차게 진행"
        )
        self.txt_common_info.setStyleSheet("font-size: 13px; padding: 6px;")
        l_info.addWidget(self.txt_common_info, stretch=1)
        layout.addWidget(g_info, stretch=1)

        # ------------------------------------------------------------------
        # 하단 저장 / 닫기 버튼
        # ------------------------------------------------------------------
        h_bottom = QHBoxLayout()
        h_bottom.addStretch()

        self.btn_save = QPushButton("💾 설정 저장 및 적용")
        self.btn_save.setStyleSheet(
            "background-color: #16a34a; color: white; font-weight: bold; "
            "font-size: 14px; padding: 8px 22px; border-radius: 6px;"
        )
        self.btn_save.clicked.connect(self._on_save_and_close)
        h_bottom.addWidget(self.btn_save)

        btn_cancel = QPushButton("닫기")
        btn_cancel.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        btn_cancel.clicked.connect(self.reject)
        h_bottom.addWidget(btn_cancel)

        layout.addLayout(h_bottom)

    def _on_toggle_show_key(self, checked: bool):
        self.txt_api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _load_current_values(self):
        env_cfg = load_gemini_env()
        key = env_cfg.get("GEMINI_API_KEY", "")
        self.txt_api_key.setText(key)
        if key:
            self.lbl_key_status.setText(
                f"✅ API 키가 설정되어 있습니다. (모델: {env_cfg.get('GEMINI_MODEL', 'gemini-3.1-flash-lite')})"
            )
            self.lbl_key_status.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
        else:
            self.lbl_key_status.setText("⚠️ 아직 API 키가 입력되지 않았습니다. 위 칸에 키를 입력해 주세요.")
            self.lbl_key_status.setStyleSheet("color: #dc2626; font-size: 12px; font-weight: bold;")

        common_cfg = load_common_settings()
        self.txt_gdrive_url.setText(common_cfg.get("gdrive_url", ""))
        self.txt_file_path.setText(common_cfg.get("plan_file_path", ""))
        self.txt_common_info.setPlainText(common_cfg.get("common_info", ""))

    def _on_open_aistudio(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://aistudio.google.com/app/apikey"))

    def _on_open_api_manual(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://kwanwon.github.io/TTS-Master/#api-guide"))

    def _on_test_api_key(self):
        key = self.txt_api_key.text().strip()
        if not key:
            QMessageBox.warning(self, "API 키 확인", "먼저 Google Gemini API Key를 입력해 주세요.")
            return

        self.btn_test_key.setEnabled(False)
        self.btn_test_key.setText("확인 중...")
        try:
            gen = AIGenerator(api_key=key)
            ok, msg = gen.test_connection()
            if ok:
                save_gemini_api_key(key)
                self.lbl_key_status.setText(f"✅ {msg}")
                self.lbl_key_status.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: bold;")
                QMessageBox.information(self, "연결 성공", f"Google Gemini AI 엔진이 정상 연결되었습니다!\n\n{msg}")
            else:
                self.lbl_key_status.setText(f"❌ {msg}")
                self.lbl_key_status.setStyleSheet("color: #dc2626; font-size: 12px; font-weight: bold;")
                QMessageBox.warning(self, "연결 실패", msg)
        finally:
            self.btn_test_key.setEnabled(True)
            self.btn_test_key.setText("🔍 연결 확인")

    def _on_fetch_gdrive_link(self):
        url = self.txt_gdrive_url.text().strip()
        if not url:
            QMessageBox.information(
                self,
                "링크 입력 안내",
                "구글 드라이브나 구글 문서(Docs/Sheets) 공유 링크를 먼저 입력해 주세요."
            )
            return

        self.btn_fetch_link.setEnabled(False)
        self.btn_fetch_link.setText("불러오는 중...")
        try:
            fetched = fetch_text_from_url(url)
            if not fetched or fetched.startswith("[링크 불러오기 오류"):
                QMessageBox.warning(self, "링크 불러오기 실패", fetched or "내용을 가져올 수 없습니다.")
                return
            self.txt_common_info.setPlainText(fetched)
            QMessageBox.information(
                self,
                "불러오기 완료",
                "구글 드라이브/문서 링크에서 내용을 성공적으로 가져왔습니다!\n아래 내용 창에서 확인 및 수정하실 수 있습니다."
            )
        finally:
            self.btn_fetch_link.setEnabled(True)
            self.btn_fetch_link.setText("📥 링크 내용 가져오기")

    def _on_browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "수련계획표 / 운동 메모 파일 선택",
            "",
            "문서 파일 (*.txt *.md *.docx *.csv *.json);;모든 파일 (*)"
        )
        if not file_path:
            return

        text = extract_text_from_file(file_path)
        if not text or text.startswith("[파일 읽기 오류"):
            QMessageBox.warning(self, "파일 읽기 오류", text or "파일 내용을 읽을 수 없습니다.")
            return

        self.txt_file_path.setText(file_path)
        self.txt_common_info.setPlainText(text)
        QMessageBox.information(
            self,
            "파일 불러오기 완료",
            f"'{os.path.basename(file_path)}' 파일 내용을 아래 공통 수련 정보 창에 불러왔습니다."
        )

    def _on_clear_info(self):
        self.txt_gdrive_url.clear()
        self.txt_file_path.clear()
        self.txt_common_info.clear()

    def _on_save_and_close(self):
        key = self.txt_api_key.text().strip()
        if key:
            save_gemini_api_key(key)

        save_common_settings({
            "gdrive_url": self.txt_gdrive_url.text().strip(),
            "plan_file_path": self.txt_file_path.text().strip(),
            "common_info": self.txt_common_info.toPlainText().strip(),
        })
        self.accept()
