import os
import json
import pygame
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QGroupBox, QLabel, QSlider, QTableWidget, QTableWidgetItem, QCheckBox,
    QComboBox, QHeaderView, QMenu, QInputDialog, QMessageBox, QFileDialog, QTimeEdit,
    QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime
from PyQt6.QtGui import QAction, QKeySequence, QColor, QDropEvent, QBrush

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

class AudioPlaylistWidget(QListWidget):
    total_time_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        
        self.undo_stack = []
        self.clipboard = []
        
        self.itemDoubleClicked.connect(self.edit_delay)
        
    def dragEnterEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        # Handle file drops from OS
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                    self.add_audio_file(path, 0.0)
            event.acceptProposedAction()
        else:
            # Internal move
            super().dropEvent(event)
            self.total_time_changed.emit()

    def add_audio_file(self, path, delay=0.0):
        name = os.path.basename(path)
        item = QListWidgetItem(f"{name} (딜레이: {delay}초)")
        item.setData(Qt.ItemDataRole.UserRole, {'path': path, 'delay': float(delay)})
        self.addItem(item)
        self.total_time_changed.emit()
        
    def edit_delay(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
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
            self.clipboard.append(item.data(Qt.ItemDataRole.UserRole))
            
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
            row += 1 # Insert below the currently selected item
            
        added_items = []
        for i, data in enumerate(self.clipboard):
            name = os.path.basename(data['path'])
            item = QListWidgetItem(f"{name} (딜레이: {data['delay']}초)")
            item.setData(Qt.ItemDataRole.UserRole, dict(data)) # copy dict
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
            for row, data in items: # Need to re-insert
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
        
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        edit_action = menu.addAction("딜레이 시간 수정")
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
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Toolbar
        toolbar = QHBoxLayout()
        btn_add = QPushButton("🎵 파일 추가")
        btn_play = QPushButton("▶️ 재생")
        btn_pause = QPushButton("⏸")
        btn_stop = QPushButton("⏹ 정지")
        btn_clear = QPushButton("🗑 전체 삭제")
        
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_play)
        toolbar.addWidget(btn_pause)
        toolbar.addWidget(btn_stop)
        toolbar.addWidget(btn_clear)
        layout.addLayout(toolbar)
        
        # Playlist
        playlist = AudioPlaylistWidget()
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
        files, _ = QFileDialog.getOpenFileNames(self, "음원 파일 다중 선택", "", "Audio Files (*.mp3 *.wav *.ogg *.m4a)", options=QFileDialog.Option.DontUseNativeDialog)
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
                item.setBackground(QColor("#3498db"))
                item.setForeground(QColor("white"))
                playlist.scrollToItem(item)
            else:
                # Reset to default. Alternating row colors handles the rest
                item.setBackground(QBrush()) # transparent
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
        file_path, _ = QFileDialog.getSaveFileName(self, "스케줄 파일 저장", "", "JSON Files (*.json)", options=QFileDialog.Option.DontUseNativeDialog)
        if file_path:
            state = self._get_state_dict()
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "성공", "스케줄이 성공적으로 저장되었습니다.")
            
    def load_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "스케줄 파일 불러오기", "", "JSON Files (*.json)", options=QFileDialog.Option.DontUseNativeDialog)
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._apply_state_dict(state)
            QMessageBox.information(self, "성공", "스케줄을 성공적으로 불러왔습니다.")
