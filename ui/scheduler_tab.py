import os
import json
import pygame
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QTabBar, QGroupBox, QLabel, QSlider, QTableWidget, QTableWidgetItem, QCheckBox,
    QComboBox, QHeaderView, QMenu, QInputDialog, QMessageBox, QFileDialog, QTimeEdit,
    QSplitter, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime, QUrl, QMimeData
from PyQt6.QtGui import QAction, QKeySequence, QColor, QDropEvent, QDragEnterEvent, QDragMoveEvent, QBrush, QDrag, QFont

class PlaybackThread(QThread):
    item_playing = pyqtSignal(int)
    playback_finished = pyqtSignal()
    
    def __init__(self, items, start_index=0, repeat=False, channel_id=0, parent=None):
        super().__init__(parent)
        self.items = items # List of dicts: {'path': path, 'delay': delay}
        self.start_index = start_index
        self.repeat = repeat
        self.channel_id = channel_id
        self._is_paused = False
        self._is_stopped = False
        
    def run(self):
        try:
            pygame.mixer.set_num_channels(8) # Ensure enough channels
            channel = pygame.mixer.Channel(self.channel_id)
            
            while not self._is_stopped:
                for i in range(self.start_index, len(self.items)):
                    if self._is_stopped:
                        break
                        
                    item = self.items[i]
                    path = item['path']
                    delay = item['delay']
                    
                    if not os.path.exists(path):
                        continue
                        
                    self.item_playing.emit(i)
                    
                    # Play audio via specific channel
                    sound = pygame.mixer.Sound(path)
                    channel.play(sound)
                    
                    # Wait for audio to finish, handling pause and stop
                    while channel.get_busy() or self._is_paused:
                        if self._is_stopped:
                            channel.stop()
                            break
                        if self._is_paused:
                            channel.pause()
                            # Loop until unpaused or stopped
                            while self._is_paused and not self._is_stopped:
                                self.msleep(100)
                            if not self._is_stopped:
                                channel.unpause()
                        self.msleep(100)
                        
                    if self._is_stopped:
                        break
                        
                    # Handle delay
                    delay_ms = int(delay * 1000)
                    waited = 0
                    while waited < delay_ms:
                        if self._is_stopped:
                            break
                        if self._is_paused:
                            while self._is_paused and not self._is_stopped:
                                self.msleep(100)
                        self.msleep(100)
                        waited += 100
                        
                if not self.repeat or self._is_stopped:
                    break
                self.start_index = 0 # If repeating, start from beginning
                
        finally:
            self.playback_finished.emit()
            
    def pause(self):
        self._is_paused = not self._is_paused
        
    def stop(self):
        self._is_stopped = True
        self._is_paused = False

class HoverTabBar(QTabBar):
    """드래그 중에 탭 바 위에 마우스를 350ms 올리면 해당 탭으로 자동 스위칭"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(350)
        self._hover_index = -1
        self._hover_timer.timeout.connect(self._on_hover_timeout)

    def _on_hover_timeout(self):
        if self._hover_index >= 0:
            parent_tab = self.parent()
            if isinstance(parent_tab, QTabWidget):
                parent_tab.setCurrentIndex(self._hover_index)

    def dragEnterEvent(self, event: QDragEnterEvent):
        event.acceptProposedAction()
        event.accept()

    def dragMoveEvent(self, event: QDragMoveEvent):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        idx = self.tabAt(pos)
        if idx >= 0 and idx != self.currentIndex():
            if idx != self._hover_index:
                self._hover_index = idx
                self._hover_timer.start()
        else:
            self._hover_timer.stop()
            self._hover_index = -1
        event.acceptProposedAction()
        event.accept()

    def dragLeaveEvent(self, event):
        self._hover_timer.stop()
        self._hover_index = -1


class AudioPlaylistWidget(QListWidget):
    total_time_changed = pyqtSignal()
    
    def __init__(self, session_name="수련1", scheduler_tab=None, parent=None):
        super().__init__(parent)
        self.session_name = session_name
        self.scheduler_tab = scheduler_tab
        
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(False)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        
        # 글씨 크기 대폭 확대(14px) 및 항목 행 높이/패딩 여백 넉넉하게 확장 (손떨림 방지 카드형 UI)
        self.setStyleSheet("""
            QListWidget {
                background-color: #1a1e24;
                border: 2px solid #30363d;
                border-radius: 8px;
                padding: 6px;
                font-size: 14px;
                color: #f0f6fc;
            }
            QListWidget::item {
                min-height: 40px;
                height: 40px;
                padding: 6px 14px;
                margin: 4px 2px;
                border-radius: 6px;
                background-color: #242933;
                border: 1px solid #323b47;
                color: #f0f6fc;
                font-size: 14px;
                font-weight: 500;
            }
            QListWidget::item:hover {
                background-color: #2f3846;
                border: 1px solid #58a6ff;
                color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: #1f6feb;
                border: 1px solid #79c0ff;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        
        self.undo_stack = []
        self.clipboard = []
        
        self.itemDoubleClicked.connect(self.edit_delay)
        
    def startDrag(self, supportedActions):
        selected = self.selectedItems()
        if not selected:
            return
            
        items_payload = []
        for item in selected:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                items_payload.append(dict(data))
                
        mime = QMimeData()
        mime.setData("application/x-aimaster-playlist-items", json.dumps(items_payload).encode("utf-8"))
        
        # OS 호환용 URLs 첨부
        urls = [QUrl.fromLocalFile(d['path']) for d in items_payload if os.path.exists(d.get('path', ''))]
        if urls:
            mime.setUrls(urls)
            
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-aimaster-playlist-items") or isinstance(event.source(), AudioPlaylistWidget):
            event.acceptProposedAction()
            event.accept()
        else:
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            event.accept()
        elif event.mimeData().hasFormat("application/x-aimaster-playlist-items") or isinstance(event.source(), AudioPlaylistWidget):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.acceptProposedAction()
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        target_item = self.itemAt(pos)
        drop_row = self.row(target_item) if target_item else self.count()
        if drop_row < 0:
            drop_row = self.count()

        # 1. 수련 리스트 간 및 동일 리스트 내부 드래그 앤 드롭 이동
        if event.mimeData().hasFormat("application/x-aimaster-playlist-items") or isinstance(event.source(), AudioPlaylistWidget):
            items_payload = []
            if event.mimeData().hasFormat("application/x-aimaster-playlist-items"):
                try:
                    raw = event.mimeData().data("application/x-aimaster-playlist-items").data()
                    items_payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    pass
                    
            source_widget = event.source()
            if not items_payload and isinstance(source_widget, AudioPlaylistWidget):
                items_payload = [item.data(Qt.ItemDataRole.UserRole) for item in source_widget.selectedItems() if item.data(Qt.ItemDataRole.UserRole)]

            if items_payload:
                if source_widget == self:
                    # 동일 위젯 내부 순서 재배치
                    selected_rows = sorted([self.row(item) for item in self.selectedItems()], reverse=True)
                    for r in selected_rows:
                        self.takeItem(r)
                        if r < drop_row:
                            drop_row -= 1
                    drop_row = max(0, min(drop_row, self.count()))
                    for i, data in enumerate(items_payload):
                        self.insert_audio_file(drop_row + i, data['path'], data.get('delay', 0.0))
                else:
                    # 다른 수련 위젯에서 드롭 (수련1,2 -> 수련3,4 등 교차 이동)
                    if isinstance(source_widget, AudioPlaylistWidget):
                        selected_rows = sorted([source_widget.row(item) for item in source_widget.selectedItems()], reverse=True)
                        for r in selected_rows:
                            source_widget.takeItem(r)
                        source_widget.total_time_changed.emit()

                    drop_row = max(0, min(drop_row, self.count()))
                    for i, data in enumerate(items_payload):
                        self.insert_audio_file(drop_row + i, data['path'], data.get('delay', 0.0))

                self.total_time_changed.emit()
                event.acceptProposedAction()
                event.accept()
                return

        # 2. OS 파일 탐색기(Finder)에서 음원 파일 및 폴더 드래그 앤 드롭
        if event.mimeData().hasUrls():
            audio_exts = ('.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma')
            dropped_paths = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if not p:
                    continue
                if os.path.isdir(p):
                    # 폴더 드롭 시 내부 음원 재귀 탐색
                    for root, _, files in os.walk(p):
                        for f in sorted(files):
                            if f.lower().endswith(audio_exts):
                                dropped_paths.append(os.path.join(root, f))
                elif p.lower().endswith(audio_exts):
                    dropped_paths.append(p)

            if dropped_paths:
                drop_row = max(0, min(drop_row, self.count()))
                for i, p in enumerate(dropped_paths):
                    self.insert_audio_file(drop_row + i, p, 0.0)
                self.total_time_changed.emit()

            event.acceptProposedAction()
            event.accept()
            return

        super().dropEvent(event)
        self.total_time_changed.emit()

    def add_audio_file(self, path, delay=0.0):
        self.insert_audio_file(self.count(), path, delay)

    def insert_audio_file(self, row, path, delay=0.0):
        name = os.path.basename(path)
        item = QListWidgetItem(f"{name} (딜레이: {delay}초)")
        item.setData(Qt.ItemDataRole.UserRole, {'path': path, 'delay': float(delay)})
        self.insertItem(row, item)
        self.total_time_changed.emit()
        
    def edit_delay(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        current_delay = data['delay']
        delay, ok = QInputDialog.getDouble(self, "딜레이 시간 수정", "대기할 딜레이 시간(초)을 입력하세요:", current_delay, 0.0, 3600.0, 1)
        if ok:
            data['delay'] = delay
            item.setData(Qt.ItemDataRole.UserRole, data)
            name = os.path.basename(data['path'])
            item.setText(f"{name} (딜레이: {delay}초)")
            self.total_time_changed.emit()
            
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                self.copy_items()
            elif event.key() == Qt.Key.Key_X:
                self.cut_items()
            elif event.key() == Qt.Key.Key_V:
                self.paste_items()
            elif event.key() == Qt.Key.Key_Z:
                self.undo()
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.remove_items()
        else:
            super().keyPressEvent(event)
            
    def copy_items(self):
        self.clipboard = []
        for item in self.selectedItems():
            self.clipboard.append(dict(item.data(Qt.ItemDataRole.UserRole)))
            
    def cut_items(self):
        self.copy_items()
        self.remove_items()
        
    def paste_items(self):
        if not self.clipboard:
            return
            
        row = self.currentRow()
        if row < 0:
            row = self.count()
        else:
            row += 1
            
        added_items = []
        for i, data in enumerate(self.clipboard):
            name = os.path.basename(data['path'])
            item = QListWidgetItem(f"{name} (딜레이: {data['delay']}초)")
            item.setData(Qt.ItemDataRole.UserRole, dict(data))
            self.insertItem(row + i, item)
            added_items.append(item)
            
        self.undo_stack.append(('paste', added_items))
        self.total_time_changed.emit()
        
    def remove_items(self):
        removed = []
        for item in self.selectedItems():
            row = self.row(item)
            data = item.data(Qt.ItemDataRole.UserRole)
            removed.append((row, data))
            self.takeItem(row)
        if removed:
            self.undo_stack.append(('remove', removed))
            self.total_time_changed.emit()
            
    def undo(self):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        type_ = action[0]
        
        if type_ == 'remove':
            items = action[1]
            for row, data in items:
                name = os.path.basename(data['path'])
                item = QListWidgetItem(f"{name} (딜레이: {data['delay']}초)")
                item.setData(Qt.ItemDataRole.UserRole, data)
                self.insertItem(row, item)
        elif type_ == 'paste':
            items = action[1]
            for item in items:
                row = self.row(item)
                if row >= 0:
                    self.takeItem(row)
        self.total_time_changed.emit()

    def transfer_to_session(self, target_session, is_move=True):
        """다른 수련 칸으로 선택 항목을 일괄 이동 또는 복사"""
        if not self.scheduler_tab or target_session not in self.scheduler_tab.playlists:
            return
            
        target_playlist = self.scheduler_tab.playlists[target_session]
        selected_items = self.selectedItems()
        if not selected_items:
            return
            
        items_data = [dict(item.data(Qt.ItemDataRole.UserRole)) for item in selected_items if item.data(Qt.ItemDataRole.UserRole)]
        
        if is_move:
            self.remove_items()
            
        for d in items_data:
            target_playlist.add_audio_file(d['path'], d.get('delay', 0.0))
            
        target_playlist.total_time_changed.emit()
        self.total_time_changed.emit()
        
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        edit_action = menu.addAction("✏️ 딜레이 시간 수정")
        menu.addSeparator()
        
        # 다른 수련 칸으로 간편 이동 / 복사 서브메뉴
        if self.scheduler_tab:
            all_sessions = getattr(self.scheduler_tab, 'sessions', ["수련1", "수련2", "수련3", "수련4", "수련5", "수련6"])
            other_sessions = [s for s in all_sessions if s != self.session_name]
            
            move_menu = menu.addMenu("🚀 다른 수련으로 이동 ➡️")
            for s in other_sessions:
                act = move_menu.addAction(f"[{s}]로 이동")
                act.triggered.connect(lambda _, ts=s: self.transfer_to_session(ts, is_move=True))
                
            copy_menu = menu.addMenu("📋 다른 수련으로 복사 ➡️")
            for s in other_sessions:
                act = copy_menu.addAction(f"[{s}]로 복사")
                act.triggered.connect(lambda _, ts=s: self.transfer_to_session(ts, is_move=False))
            menu.addSeparator()

        copy_action = menu.addAction("복사 (Ctrl+C)")
        cut_action = menu.addAction("잘라내기 (Ctrl+X)")
        paste_action = menu.addAction("붙여넣기 (Ctrl+V)")
        remove_action = menu.addAction("삭제 (Del)")
        menu.addSeparator()
        undo_action = menu.addAction("되돌리기 (Ctrl+Z)")
        menu.addSeparator()
        sel_all_action = menu.addAction("전체 선택")
        
        action = menu.exec(self.mapToGlobal(event.pos()))
        
        if action == edit_action:
            item = self.itemAt(event.pos())
            if item: self.edit_delay(item)
        elif action == copy_action: self.copy_items()
        elif action == cut_action: self.cut_items()
        elif action == paste_action: self.paste_items()
        elif action == remove_action: self.remove_items()
        elif action == undo_action: self.undo()
        elif action == sel_all_action: self.selectAll()


class SchedulerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.play_threads = {}
        self.sessions = ["수련1", "수련2", "수련3", "수련4", "수련5", "수련6"]
        self.playlists = {} # Maps session name to AudioPlaylistWidget
        self.repeat_vars = {} # Maps session name to QCheckBox
        self.time_labels = {} # Maps session name to QLabel
        
        # Scheduling timer
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.check_schedule)
        self.schedule_timer.start(1000)
        
        self.init_ui()
        self.load_state()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Top Panel: Save / Load state
        top_layout = QHBoxLayout()
        btn_save_state = QPushButton("💾 현재 스케줄 파일로 저장 (.json)")
        btn_load_state = QPushButton("📂 스케줄 파일 불러오기 (.json)")
        btn_save_state.clicked.connect(self.save_to_file)
        btn_load_state.clicked.connect(self.load_from_file)
        top_layout.addWidget(btn_save_state)
        top_layout.addWidget(btn_load_state)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        # Splitter for Tabs (Left) and Schedule Table (Right)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Panel: TabWidget for Sessions (3 Tabs, 2 Sessions per Tab)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.tabs.setTabBar(HoverTabBar(self.tabs))
        tab_pairs = [("수련1", "수련2"), ("수련3", "수련4"), ("수련5", "수련6")]
        
        for idx, (s1, s2) in enumerate(tab_pairs):
            tab = QWidget()
            tab_layout = QHBoxLayout(tab)
            
            # Splitter inside tab for two sessions
            tab_splitter = QSplitter(Qt.Orientation.Horizontal)
            
            p1 = self.create_session_panel(s1, idx * 2)
            p2 = self.create_session_panel(s2, idx * 2 + 1)
            
            tab_splitter.addWidget(p1)
            tab_splitter.addWidget(p2)
            
            tab_layout.addWidget(tab_splitter)
            self.tabs.addTab(tab, f"[{s1} & {s2}]")
            
        left_layout.addWidget(self.tabs)
        content_splitter.addWidget(left_panel)
        
        # Right Panel: Schedule Table
        right_panel = QGroupBox("자동 예약 스케줄러 (시간표)")
        right_layout = QVBoxLayout(right_panel)
        
        self.schedule_table = QTableWidget(20, 4)
        self.schedule_table.setHorizontalHeaderLabels(["사용", "시작 시간", "종료 시간", "대상 수련"])
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        for row in range(20):
            # Checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.schedule_table.setItem(row, 0, chk)
            
            # Start Time
            start_te = QTimeEdit()
            start_te.setDisplayFormat("HH:mm")
            start_te.setTime(QTime(14 + (row//2), 0 if row%2==0 else 30))
            self.schedule_table.setCellWidget(row, 1, start_te)
            
            # End Time
            end_te = QTimeEdit()
            end_te.setDisplayFormat("HH:mm")
            end_te.setTime(QTime(14 + (row//2), 50 if row%2==0 else 20)) 
            if row%2 != 0: end_te.setTime(QTime(14 + (row//2) + 1, 20))
            self.schedule_table.setCellWidget(row, 2, end_te)
            
            # Session Combo
            combo = QComboBox()
            combo.addItems(self.sessions)
            self.schedule_table.setCellWidget(row, 3, combo)
            
        right_layout.addWidget(self.schedule_table)
        content_splitter.addWidget(right_panel)
        
        content_splitter.setSizes([800, 300])
        main_layout.addWidget(content_splitter)
        
    def create_session_panel(self, session, channel_id):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        title = QLabel(f"=== {session} ===")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #58a6ff; padding: 4px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Toolbar (큼직하고 넉넉한 버튼 패딩 적용)
        toolbar = QHBoxLayout()
        btn_add = QPushButton("🎵 파일 추가")
        btn_play = QPushButton("▶️ 재생")
        btn_pause = QPushButton("⏸")
        btn_stop = QPushButton("⏹ 정지")
        btn_clear = QPushButton("🗑 전체 삭제")
        
        for btn in (btn_add, btn_play, btn_pause, btn_stop, btn_clear):
            btn.setStyleSheet("""
                QPushButton {
                    min-height: 32px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 4px 8px;
                    border-radius: 6px;
                }
            """)
        
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_play)
        toolbar.addWidget(btn_pause)
        toolbar.addWidget(btn_stop)
        toolbar.addWidget(btn_clear)
        layout.addLayout(toolbar)
        
        # Playlist (수련 명칭 및 상위 탭 참조 전달)
        playlist = AudioPlaylistWidget(session, scheduler_tab=self)
        self.playlists[session] = playlist
        layout.addWidget(playlist)
        
        # Status & Volume
        status_layout = QHBoxLayout()
        time_lbl = QLabel("예상 소요: 00분 00초")
        time_lbl.setStyleSheet("font-weight: bold; color: blue;")
        self.time_labels[session] = time_lbl
        
        repeat_cb = QCheckBox("반복")
        self.repeat_vars[session] = repeat_cb
        
        vol_lbl = QLabel("볼륨:")
        vol_slider = QSlider(Qt.Orientation.Horizontal)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(100)
        vol_slider.setFixedWidth(80)
        
        status_layout.addWidget(time_lbl)
        status_layout.addStretch()
        status_layout.addWidget(repeat_cb)
        status_layout.addWidget(vol_lbl)
        status_layout.addWidget(vol_slider)
        layout.addLayout(status_layout)
        
        # Connections
        btn_add.clicked.connect(lambda _, s=session: self.on_add_files(s))
        btn_play.clicked.connect(lambda _, s=session: self.on_play(s, channel_id))
        btn_pause.clicked.connect(lambda _, s=session: self.on_pause(s))
        btn_stop.clicked.connect(lambda _, s=session: self.on_stop(s))
        btn_clear.clicked.connect(lambda _, s=session: self.playlists[s].clear())
        playlist.total_time_changed.connect(lambda s=session: self.update_total_time(s))
        vol_slider.valueChanged.connect(lambda val, c=channel_id: self.update_volume(c, val))
        
        return panel
            
    def on_add_files(self, session):
        files, _ = QFileDialog.getOpenFileNames(self, "음원 파일 다중 선택", "", "Audio Files (*.mp3 *.wav *.ogg *.m4a)")
        for file in files:
            self.playlists[session].add_audio_file(file, 0.0)
            
    def update_volume(self, channel_id, val):
        channel = pygame.mixer.Channel(channel_id)
        channel.set_volume(val / 100.0)
        
    def update_total_time(self, session):
        playlist = self.playlists[session]
        total_seconds = 0.0
        
        for i in range(playlist.count()):
            item = playlist.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            path = data['path']
            delay = data['delay']
            name = os.path.basename(path)
            
            try:
                if os.path.exists(path):
                    sound = pygame.mixer.Sound(path)
                    total_seconds += sound.get_length()
            except:
                pass
            total_seconds += delay
            
            # 아이템 텍스트에 타임라인(누적 완료 시간) 업데이트
            m, s = divmod(int(total_seconds), 60)
            item.setText(f"[{m:02d}분 {s:02d}초] {name} (딜레이: {delay}초)")
            
        m, s = divmod(int(total_seconds), 60)
        self.time_labels[session].setText(f"예상 소요: {m:02d}분 {s:02d}초")
        
    def on_play(self, session, channel_id):
        if session in self.play_threads and self.play_threads[session].isRunning():
            return
            
        playlist = self.playlists[session]
        if playlist.count() == 0:
            return
            
        items = []
        # If there's a selection, play from first selected index
        start_index = 0
        selected = playlist.selectedIndexes()
        if selected:
            start_index = selected[0].row()
            
        for i in range(playlist.count()):
            items.append(playlist.item(i).data(Qt.ItemDataRole.UserRole))
            
        repeat = self.repeat_vars[session].isChecked()
        
        thread = PlaybackThread(items, start_index=start_index, repeat=repeat, channel_id=channel_id, parent=self)
        thread.item_playing.connect(lambda idx, s=session: self.highlight_item(s, idx))
        thread.playback_finished.connect(lambda s=session: self.clear_highlight(s))
        
        self.play_threads[session] = thread
        thread.start()
        
    def on_pause(self, session):
        if session in self.play_threads:
            self.play_threads[session].pause()
            
    def on_stop(self, session):
        if session in self.play_threads:
            self.play_threads[session].stop()
            
    def highlight_item(self, session, idx):
        playlist = self.playlists[session]
        for i in range(playlist.count()):
            item = playlist.item(i)
            if i == idx:
                item.setBackground(QColor("#238636"))
                item.setForeground(QColor("white"))
                playlist.scrollToItem(item)
            else:
                item.setBackground(QBrush())
                item.setForeground(QBrush())
                
    def clear_highlight(self, session):
        playlist = self.playlists[session]
        for i in range(playlist.count()):
            item = playlist.item(i)
            item.setBackground(QBrush())
            item.setForeground(QBrush())

    def check_schedule(self):
        now = QTime.currentTime()
        
        for row in range(20):
            chk = self.schedule_table.item(row, 0)
            if chk.checkState() == Qt.CheckState.Checked:
                start_time = self.schedule_table.cellWidget(row, 1).time()
                end_time = self.schedule_table.cellWidget(row, 2).time()
                session = self.schedule_table.cellWidget(row, 3).currentText()
                
                # Check if we should start
                if start_time.hour() == now.hour() and start_time.minute() == now.minute() and start_time.second() == now.second():
                    if session not in self.play_threads or not self.play_threads[session].isRunning():
                        # Determine channel_id from session
                        channel_id = int(session.replace("수련", "")) - 1
                        self.on_play(session, channel_id)
                
                # Check if we should stop
                if end_time.hour() == now.hour() and end_time.minute() == now.minute() and end_time.second() == now.second():
                    if session in self.play_threads and self.play_threads[session].isRunning():
                        self.on_stop(session)
                        chk.setCheckState(Qt.CheckState.Unchecked) # Auto uncheck after finish

    def _get_state_dict(self):
        state = {
            "sessions": {},
            "schedules": []
        }
        # Save Sessions
        for session in self.sessions:
            playlist = self.playlists[session]
            items = []
            for i in range(playlist.count()):
                items.append(playlist.item(i).data(Qt.ItemDataRole.UserRole))
            state["sessions"][session] = {
                "repeat": self.repeat_vars[session].isChecked(),
                "items": items
            }
        # Save Schedules
        for row in range(20):
            chk = self.schedule_table.item(row, 0).checkState() == Qt.CheckState.Checked
            start = self.schedule_table.cellWidget(row, 1).time().toString("HH:mm")
            end = self.schedule_table.cellWidget(row, 2).time().toString("HH:mm")
            session = self.schedule_table.cellWidget(row, 3).currentText()
            state["schedules"].append({
                "checked": chk,
                "start": start,
                "end": end,
                "session": session
            })
        return state
        
    def _apply_state_dict(self, state):
        if "sessions" in state:
            for session, data in state["sessions"].items():
                if session in self.sessions:
                    self.playlists[session].clear()
                    self.repeat_vars[session].setChecked(data.get("repeat", False))
                    for item in data.get("items", []):
                        self.playlists[session].add_audio_file(item["path"], item["delay"])
                        
        if "schedules" in state:
            for row, data in enumerate(state["schedules"]):
                if row >= 20: break
                self.schedule_table.item(row, 0).setCheckState(Qt.CheckState.Checked if data["checked"] else Qt.CheckState.Unchecked)
                self.schedule_table.cellWidget(row, 1).setTime(QTime.fromString(data["start"], "HH:mm"))
                self.schedule_table.cellWidget(row, 2).setTime(QTime.fromString(data["end"], "HH:mm"))
                self.schedule_table.cellWidget(row, 3).setCurrentText(data["session"])

    def save_state(self):
        # Auto-save
        state = self._get_state_dict()
        try:
            os.makedirs("projects", exist_ok=True)
            with open("projects/scheduler_state.json", "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
        except: pass
            
    def load_state(self):
        # Auto-load
        try:
            if not os.path.exists("projects/scheduler_state.json"): return
            with open("projects/scheduler_state.json", "r", encoding="utf-8") as f:
                state = json.load(f)
            self._apply_state_dict(state)
        except: pass
        
    def save_to_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "스케줄 파일 저장", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            if not os.path.splitext(file_path)[1]:
                file_path += ".json"
            try:
                state = self._get_state_dict()
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "성공", f"스케줄이 성공적으로 저장되었습니다:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"스케줄 파일 저장 중 오류가 발생했습니다:\n{e}")
            
    def load_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "스케줄 파일 불러오기", "",
            "All Files (*);;JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self._apply_state_dict(state)
                QMessageBox.information(self, "성공", f"스케줄을 성공적으로 불러왔습니다:\n{os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "불러오기 오류", f"스케줄 파일 형식이 올바르지 않거나 읽을 수 없습니다:\n{e}")
