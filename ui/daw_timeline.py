import os
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsItem, QMenu, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QColor, QPen, QBrush, QDrag, QPainter

BASE_PPS = 100      # 기본 pixels per second
TRACK_HEIGHT = 40
RULER_HEIGHT = 30
NUM_TRACKS = 3
TOTAL_DURATION = 300  # seconds


class AudioClipItem(QGraphicsRectItem):
    def __init__(self, text, file_path, duration_sec, track_idx, time_sec, pps, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.text = text
        self.duration_sec = duration_sec
        self.track_idx = track_idx
        self.time_sec = time_sec
        self.pps = pps
        self.y_pos = 0

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._update_geometry()

    def _update_geometry(self):
        width_px = max(self.duration_sec * self.pps, 20)
        height_px = TRACK_HEIGHT - 10
        self.setRect(0, 0, width_px, height_px)

        x_pos = self.time_sec * self.pps
        self.y_pos = self.track_idx * TRACK_HEIGHT + RULER_HEIGHT + 5
        self.setPos(x_pos, self.y_pos)

        colors = ["#3498db", "#e67e22", "#9b59b6"]
        self.setBrush(QBrush(QColor(colors[self.track_idx % len(colors)])))
        self.setPen(QPen(QColor("#1a252f"), 1))

        for child in self.childItems():
            child.setParentItem(None)

        display_txt = self.text[:16] + "..." if len(self.text) > 16 else self.text
        self.label = QGraphicsTextItem(display_txt, self)
        self.label.setDefaultTextColor(Qt.GlobalColor.white)
        self.label.setPos(3, 2)

        self.time_label = QGraphicsTextItem(f"{self.time_sec:.1f}s", self)
        self.time_label.setDefaultTextColor(QColor("#ecf0f1"))
        self.time_label.setPos(3, 20)

    def rescale(self, new_pps):
        self.pps = new_pps
        self._update_geometry()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            new_pos = value
            new_pos.setY(self.y_pos)
            if new_pos.x() < 0:
                new_pos.setX(0)
            self.time_sec = new_pos.x() / self.pps
            if hasattr(self, 'time_label'):
                self.time_label.setPlainText(f"{self.time_sec:.1f}s")
            return new_pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.scene() and self.scene().views():
                self.scene().views()[0].timelineChanged.emit()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        # 개별 아이템의 메뉴 처리를 View로 위임하기 위해 무시
        event.ignore()


class DAWTimeline(QGraphicsView):
    itemDropped = pyqtSignal(str, str, float, int)
    playheadSeek = pyqtSignal(float, bool)
    
    # 컨텍스트 메뉴 시그널
    clipSplitRequested = pyqtSignal(object) # item
    clipFadeRequested = pyqtSignal(object, str) # item, "in" or "out"
    clipCopyRequested = pyqtSignal(object) # item
    clipDeleteRequested = pyqtSignal(object) # item
    pasteRequested = pyqtSignal(float, int) # time_sec, track_idx
    timelineChanged = pyqtSignal() # 타임라인 변경 시 자동 믹싱 트리거용

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.pps = BASE_PPS
        self.playhead_time = -1.0
        self._is_scrubbing = False
        self._bg_items = []
        self._playhead_line = None

        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._rebuild_background()
        self._build_playhead()

    # ── 배경 및 눈금자 ──────────────────────────────────────
    def _clear_bg(self):
        for item in self._bg_items:
            self._scene.removeItem(item)
        self._bg_items.clear()

    def _rebuild_background(self):
        self._clear_bg()
        self._scene.setBackgroundBrush(QBrush(QColor("#2c3e50")))

        total_w = TOTAL_DURATION * self.pps
        total_h = RULER_HEIGHT + NUM_TRACKS * TRACK_HEIGHT + 10
        self._scene.setSceneRect(0, 0, total_w, total_h)

        for i in range(TOTAL_DURATION + 1):
            x = i * self.pps
            if i % 5 == 0:
                line = self._scene.addLine(x, 0, x, RULER_HEIGHT,
                                           QPen(QColor("#95a5a6"), 1))
                t = self._scene.addText(f"{i}s")
                t.setDefaultTextColor(QColor("#bdc3c7"))
                t.setPos(x + 2, 0)
                font = t.font()
                font.setPointSize(max(6, min(9, int(self.pps / 12))))
                t.setFont(font)
                self._bg_items.append(t)
            else:
                line = self._scene.addLine(x, RULER_HEIGHT - 8, x, RULER_HEIGHT,
                                           QPen(QColor("#5d6d7e"), 1))
            self._bg_items.append(line)

        track_colors = ["#1a2738", "#1c2b1e", "#1e1a2e"]
        track_names = ["트랙 1", "트랙 2", "트랙 3"]
        for t in range(NUM_TRACKS):
            y = t * TRACK_HEIGHT + RULER_HEIGHT
            rect = self._scene.addRect(0, y, total_w, TRACK_HEIGHT,
                                       QPen(QColor("#34495e")),
                                       QBrush(QColor(track_colors[t])))
            rect.setZValue(-1)
            self._bg_items.append(rect)

            lbl = self._scene.addText(track_names[t])
            lbl.setDefaultTextColor(QColor("#ecf0f1"))
            lbl.setPos(4, y + 5)
            lbl.setZValue(5)
            self._bg_items.append(lbl)

    # ── 플레이헤드 ──────────────────────────────────────────
    def _build_playhead(self):
        if self._playhead_line:
            self._scene.removeItem(self._playhead_line)
        total_h = RULER_HEIGHT + NUM_TRACKS * TRACK_HEIGHT + 10
        self._playhead_line = self._scene.addLine(0, 0, 0, total_h,
                                                  QPen(QColor("#e74c3c"), 2))
        self._playhead_line.setZValue(100)
        self._playhead_line.setVisible(False)

    def set_playhead_time(self, time_sec):
        if time_sec < 0:
            self._playhead_line.setVisible(False)
        else:
            self._playhead_line.setVisible(True)
            x = time_sec * self.pps
            total_h = RULER_HEIGHT + NUM_TRACKS * TRACK_HEIGHT + 10
            self._playhead_line.setLine(x, 0, x, total_h)

    # ── 줌 (pps 방식 - 화면 자체가 아닌 시간 눈금만 조절) ──
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.25 if delta > 0 else 1.0 / 1.25
            new_pps = max(8, min(2000, self.pps * factor))
            self._apply_zoom(new_pps)
            event.accept()
        else:
            super().wheelEvent(event)

    def _apply_zoom(self, new_pps):
        self.pps = new_pps
        self._rebuild_background()
        for item in self._scene.items():
            if isinstance(item, AudioClipItem):
                item.rescale(new_pps)
        self._build_playhead()
        if self.playhead_time >= 0:
            self.set_playhead_time(self.playhead_time)

    # ── 드래그 앤 드롭 ──────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-audio-clip"):
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-audio-clip"):
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-audio-clip"):
            raw = event.mimeData().data("application/x-audio-clip").data().decode("utf-8")
            text, file_path = raw.split("|||")
            pos = self.mapToScene(event.position().toPoint())
            time_sec = max(0.0, pos.x() / self.pps)
            track_idx = int((pos.y() - RULER_HEIGHT) / TRACK_HEIGHT)
            track_idx = max(0, min(NUM_TRACKS - 1, track_idx))
            self.itemDropped.emit(text, file_path, time_sec, track_idx)
            event.accept()
        else:
            super().dropEvent(event)

    def add_clip(self, text, file_path, time_sec, track_idx, duration_sec):
        item = AudioClipItem(text, file_path, duration_sec, track_idx, time_sec, self.pps)
        self._scene.addItem(item)
        self.timelineChanged.emit()

    def get_timeline_data(self):
        data = []
        for item in self._scene.items():
            if isinstance(item, AudioClipItem):
                data.append({
                    'time': item.time_sec,
                    'file': item.file_path,
                    'vol': 0.0,
                    'track': item.track_idx,
                    'duration': item.duration_sec
                })
        return data

    def clear_track(self, track_idx):
        changed = False
        for item in list(self._scene.items()):
            if isinstance(item, AudioClipItem) and item.track_idx == track_idx:
                self._scene.removeItem(item)
                changed = True
        if changed:
            self.timelineChanged.emit()

    def clear_all(self):
        changed = False
        for item in list(self._scene.items()):
            if isinstance(item, AudioClipItem):
                self._scene.removeItem(item)
                changed = True
        if changed:
            self.timelineChanged.emit()

    # ── 마우스로 플레이헤드 이동 ────────────────────────────
    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, AudioClipItem):
            super().mousePressEvent(event)
            return
        if item and item.parentItem() and isinstance(item.parentItem(), AudioClipItem):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.pos())
            time_sec = max(0.0, pos.x() / self.pps)
            self._is_scrubbing = True
            self.playhead_time = time_sec
            self.set_playhead_time(time_sec)
            self.playheadSeek.emit(time_sec, False)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_scrubbing:
            pos = self.mapToScene(event.pos())
            time_sec = max(0.0, pos.x() / self.pps)
            self.playhead_time = time_sec
            self.set_playhead_time(time_sec)
            self.playheadSeek.emit(time_sec, False)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_scrubbing:
            pos = self.mapToScene(event.pos())
            time_sec = max(0.0, pos.x() / self.pps)
            self.playhead_time = time_sec
            self.set_playhead_time(time_sec)
            self.playheadSeek.emit(time_sec, True)
            self._is_scrubbing = False
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        pos = event.pos()
        scene_pos = self.mapToScene(pos)
        item = self.scene().itemAt(scene_pos, self.transform())
        
        # AudioClipItem의 자식(텍스트 라벨 등)을 클릭했을 수 있으므로 부모를 찾음
        if item and not isinstance(item, AudioClipItem) and isinstance(item.parentItem(), AudioClipItem):
            item = item.parentItem()
            
        menu = QMenu(self)
        
        if isinstance(item, AudioClipItem):
            # 클립 위에서 우클릭
            split_action = menu.addAction("✂️ 플레이헤드 위치에서 자르기")
            fadein_action = menu.addAction("↗️ 페이드 인 (1초) 적용")
            fadeout_action = menu.addAction("↘️ 페이드 아웃 (1초) 적용")
            menu.addSeparator()
            copy_action = menu.addAction("📋 이 클립 복사")
            delete_action = menu.addAction("🗑️ 이 클립 삭제")
            
            action = menu.exec(event.globalPos())
            
            if action == split_action:
                self.clipSplitRequested.emit(item)
            elif action == fadein_action:
                self.clipFadeRequested.emit(item, "in")
            elif action == fadeout_action:
                self.clipFadeRequested.emit(item, "out")
            elif action == copy_action:
                self.clipCopyRequested.emit(item)
            elif action == delete_action:
                self.clipDeleteRequested.emit(item)
                
        else:
            # 빈 공간에서 우클릭
            time_sec = max(0.0, scene_pos.x() / self.pps)
            track_idx = int((scene_pos.y() - RULER_HEIGHT) / TRACK_HEIGHT)
            track_idx = max(0, min(NUM_TRACKS - 1, track_idx))
            
            paste_action = menu.addAction("📋 선택한 클립 여기에 복사(붙여넣기)")
            action = menu.exec(event.globalPos())
            if action == paste_action:
                self.pasteRequested.emit(time_sec, track_idx)


class AssetListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return
        drag = QDrag(self)
        mime_data = QMimeData()
        text = item.text()
        file_path = item.data(Qt.ItemDataRole.UserRole)
        mime_data.setData("application/x-audio-clip",
                         f"{text}|||{file_path}".encode("utf-8"))
        drag.setMimeData(mime_data)
        drag.exec(supportedActions)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        del_action = menu.addAction("삭제")
        action = menu.exec(event.globalPos())
        if action == del_action:
            for item in self.selectedItems():
                self.takeItem(self.row(item))
