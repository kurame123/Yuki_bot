"""
日志页面 - 实时显示 Bot 运行日志
使用 Qt 信号接收日志，不阻塞主线程
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QCheckBox, QLineEdit
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCursor, QFont

from botGUI.core.process_manager import ProcessManager
from botGUI.core.theme import COLORS

PAGE_STYLE = "background: transparent;"


class LogPage(QWidget):
    """日志页面"""
    
    def __init__(self, process_manager: ProcessManager, parent=None):
        super().__init__(parent)
        self._pm = process_manager
        self._auto_scroll = True
        
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(PAGE_STYLE)
        
        self._setup_ui()
        self._connect_signals()
        
        # 加载已有日志
        self._load_existing_logs()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 标题栏
        header = QHBoxLayout()
        
        title = QLabel("📋 运行日志")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['primary']};")
        header.addWidget(title)
        
        header.addStretch()
        
        # 搜索框
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索日志...")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._on_search)
        header.addWidget(self._search_input)
        
        # 自动滚动
        self._auto_scroll_cb = QCheckBox("自动滚动")
        self._auto_scroll_cb.setChecked(True)
        self._auto_scroll_cb.toggled.connect(self._on_auto_scroll_toggled)
        header.addWidget(self._auto_scroll_cb)
        
        # 清空按钮
        clear_btn = QPushButton("🗑 清空")
        clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(clear_btn)
        
        layout.addLayout(header)
        
        # 日志显示区域
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 10))
        self._log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._log_view.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0f172a;
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 8px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 12px;
            }}
        """)
        
        layout.addWidget(self._log_view, 1)
        
        # 状态栏
        status_layout = QHBoxLayout()
        
        self._line_count_label = QLabel("0 行")
        self._line_count_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        status_layout.addWidget(self._line_count_label)
        
        status_layout.addStretch()
        
        self._status_label = QLabel("等待 Bot 启动...")
        self._status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        status_layout.addWidget(self._status_label)
        
        layout.addLayout(status_layout)
    
    def _connect_signals(self):
        """连接进程管理器的 Qt 信号"""
        self._pm.log_received.connect(self._on_log_received)
        self._pm.status_changed.connect(self._on_status_changed)
    
    def _load_existing_logs(self):
        """加载已有的日志"""
        for line in self._pm.log_buffer:
            self._append_log_line(line)
        self._update_line_count()
    
    @Slot(str)
    def _on_log_received(self, line: str):
        """收到新日志行（通过 Qt 信号，在主线程执行）"""
        self._append_log_line(line)
        self._update_line_count()
    
    @Slot()
    def _on_status_changed(self, status):
        """状态变化"""
        from botGUI.core.process_manager import BotStatus
        if status == BotStatus.RUNNING:
            self._status_label.setText("Bot 运行中")
        elif status == BotStatus.STOPPED:
            self._status_label.setText("Bot 未运行")
        elif status == BotStatus.STARTING:
            self._status_label.setText("Bot 启动中...")
        elif status == BotStatus.STOPPING:
            self._status_label.setText("Bot 停止中...")
        else:
            self._status_label.setText("状态异常")
    
    def _append_log_line(self, line: str):
        """追加一行日志"""
        self._log_view.appendPlainText(line)
        
        # 自动滚动到底部
        if self._auto_scroll:
            scrollbar = self._log_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _update_line_count(self):
        """更新行数显示"""
        count = self._log_view.document().blockCount()
        self._line_count_label.setText(f"{count} 行")
    
    def _on_auto_scroll_toggled(self, checked: bool):
        """切换自动滚动"""
        self._auto_scroll = checked
    
    def _on_search(self, text: str):
        """搜索日志"""
        if not text:
            return
        
        # 简单搜索：滚动到第一个匹配
        content = self._log_view.toPlainText()
        pos = content.lower().find(text.lower())
        if pos >= 0:
            cursor = self._log_view.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(text))
            self._log_view.setTextCursor(cursor)
            self._log_view.centerCursor()
    
    def _clear_logs(self):
        """清空日志显示"""
        self._log_view.clear()
        self._update_line_count()
