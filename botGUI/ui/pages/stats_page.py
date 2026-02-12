"""
统计页面 - 显示 Bot 运行统计和好感度概览
使用 QThread 进行网络请求，避免阻塞 GUI
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QProgressBar,
    QHeaderView, QFrame
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot, QObject

from botGUI.core import APIClient
from botGUI.core.theme import COLORS

PAGE_STYLE = "background: transparent;"


class StatsWorker(QThread):
    """后台获取统计数据的线程"""
    
    stats_ready = Signal(dict)
    affection_ready = Signal(dict)
    error = Signal(str)
    
    def __init__(self, api_client: APIClient, parent=None):
        super().__init__(parent)
        self._api = api_client
    
    def run(self):
        """在后台线程执行 API 请求"""
        try:
            # 获取统计
            resp = self._api.get_stats()
            if resp.success and resp.data:
                self.stats_ready.emit(resp.data)
            
            # 获取好感度
            resp = self._api.get_affection_overview()
            if resp.success and resp.data:
                self.affection_ready.emit(resp.data)
        except Exception as e:
            self.error.emit(str(e))


class StatsPage(QWidget):
    """统计页面"""
    
    def __init__(self, api_client: APIClient, parent=None):
        super().__init__(parent)
        self._api = api_client
        self._worker: StatsWorker | None = None
        
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(PAGE_STYLE)
        
        self._setup_ui()
        
        # 定时刷新（10秒）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(10000)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 标题 + 刷新按钮
        header = QHBoxLayout()
        title = QLabel("📊 统计数据")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['primary']};")
        header.addWidget(title)
        header.addStretch()
        
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        header.addWidget(self._status_label)
        
        self._refresh_btn = QPushButton("↻ 刷新")
        self._refresh_btn.clicked.connect(self._refresh_all)
        header.addWidget(self._refresh_btn)
        
        layout.addLayout(header)
        
        # 全局统计
        global_group = QGroupBox("全局统计")
        global_layout = QHBoxLayout(global_group)
        
        self._stat_labels = {}
        for key, label in [
            ("total_users", "总用户数"),
            ("total_messages", "总消息数"),
            ("total_tokens", "总 Token"),
            ("total_cost", "总费用"),
        ]:
            stat_widget = self._create_stat_widget(label)
            self._stat_labels[key] = stat_widget
            global_layout.addWidget(stat_widget)
        
        layout.addWidget(global_group)
        
        # 好感度分布
        affection_group = QGroupBox("好感度分布")
        affection_layout = QVBoxLayout(affection_group)
        
        self._affection_bars = {}
        levels = [
            ("陌生", "#94a3b8"),
            ("一般", "#60a5fa"),
            ("稍熟", "#4ade80"),
            ("熟悉", "#a3e635"),
            ("热情", "#facc15"),
            ("亲密", "#fb923c"),
            ("喜欢", "#f472b6"),
            ("喜欢+", "#f87171"),
        ]
        
        for i, (name, color) in enumerate(levels):
            row = QHBoxLayout()
            row.setSpacing(12)
            
            label = QLabel(f"Lv.{i+1} {name}")
            label.setFixedWidth(90)
            label.setStyleSheet(f"color: {COLORS['text']};")
            
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            bar.setFormat("%v 人")
            bar.setFixedHeight(24)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {COLORS['surface']};
                    border-radius: 4px;
                    text-align: center;
                    color: {COLORS['text']};
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
            
            # 人数标签（单独显示，避免被进度条遮挡）
            count_label = QLabel("0 人")
            count_label.setFixedWidth(60)
            count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            count_label.setStyleSheet(f"color: {COLORS['text']};")
            count_label.setObjectName(f"count_{i+1}")
            
            self._affection_bars[i+1] = (bar, count_label)
            
            row.addWidget(label)
            row.addWidget(bar, 1)
            row.addWidget(count_label)
            affection_layout.addLayout(row)
        
        layout.addWidget(affection_group)
        
        # 每日统计表格
        daily_group = QGroupBox("近 7 日统计")
        daily_layout = QVBoxLayout(daily_group)
        
        self._daily_table = QTableWidget()
        self._daily_table.setColumnCount(5)
        self._daily_table.setHorizontalHeaderLabels(["日期", "消息数", "Token", "费用", "活跃用户"])
        self._daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._daily_table.setAlternatingRowColors(True)
        
        daily_layout.addWidget(self._daily_table)
        layout.addWidget(daily_group)
    
    def _create_stat_widget(self, label: str) -> QFrame:
        """创建统计小部件"""
        frame = QFrame()
        frame.setMinimumWidth(180)  # 设置最小宽度
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border-radius: 8px;
            }}
        """)
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        
        title = QLabel(label)
        title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        
        value = QLabel("-")
        value.setObjectName("value")
        value.setMinimumWidth(120)  # 确保数字有足够空间
        value.setStyleSheet(f"color: {COLORS['text']}; font-size: 18px; font-weight: bold;")
        
        layout.addWidget(title)
        layout.addWidget(value)
        
        return frame
    
    def _refresh_all(self):
        """刷新所有数据（非阻塞）"""
        # 如果已有请求在进行，跳过
        if self._worker is not None and self._worker.isRunning():
            return
        
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("刷新中...")
        self._status_label.setText("正在获取数据...")
        
        # 创建后台线程
        self._worker = StatsWorker(self._api, self)
        self._worker.stats_ready.connect(self._on_stats_ready)
        self._worker.affection_ready.connect(self._on_affection_ready)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()
    
    @Slot(dict)
    def _on_stats_ready(self, data: dict):
        """统计数据就绪（在主线程）"""
        global_stats = data.get("global", {})
        daily_stats = data.get("daily", [])
        
        # 计算总消息数（收到 + 发送）
        total_messages = global_stats.get("total_msg_received", 0) + global_stats.get("total_msg_sent", 0)
        
        # 计算总 Token（R1 + V3 的输入输出）
        total_tokens = (
            global_stats.get("r1_input_tokens", 0) + 
            global_stats.get("r1_output_tokens", 0) +
            global_stats.get("v3_input_tokens", 0) + 
            global_stats.get("v3_output_tokens", 0)
        )
        
        # 更新全局统计
        self._update_stat("total_users", str(global_stats.get("total_users", 0)))
        self._update_stat("total_messages", str(total_messages))
        self._update_stat("total_tokens", f"{total_tokens:,}")
        self._update_stat("total_cost", f"¥{global_stats.get('total_cost', 0):.4f}")
        
        # 更新每日表格
        self._daily_table.setRowCount(len(daily_stats))
        for i, day in enumerate(daily_stats):
            self._daily_table.setItem(i, 0, QTableWidgetItem(day.get("date", "")))
            self._daily_table.setItem(i, 1, QTableWidgetItem(str(day.get("message_count", 0))))
            self._daily_table.setItem(i, 2, QTableWidgetItem(f"{day.get('total_tokens', 0):,}"))
            self._daily_table.setItem(i, 3, QTableWidgetItem(f"¥{day.get('total_cost', 0):.4f}"))
            self._daily_table.setItem(i, 4, QTableWidgetItem(str(day.get("active_users", 0))))
        
        self._status_label.setText("统计数据已更新")
    
    @Slot(dict)
    def _on_affection_ready(self, data: dict):
        """好感度数据就绪（在主线程）"""
        # API 返回的是 level_counts，key 是整数
        distribution = data.get("level_counts", {})
        
        # 计算最大值用于缩放
        values = [distribution.get(i, 0) for i in range(1, 9)]
        max_count = max(values) if values and max(values) > 0 else 1
        
        for level, (bar, count_label) in self._affection_bars.items():
            # key 可能是整数或字符串
            count = distribution.get(level, distribution.get(str(level), 0))
            bar.setMaximum(max(max_count, 1))
            bar.setValue(count)
            bar.setFormat("")  # 不在进度条上显示文字
            count_label.setText(f"{count} 人")
    
    @Slot(str)
    def _on_error(self, error: str):
        """错误处理"""
        self._status_label.setText(f"错误: {error}")
    
    @Slot()
    def _on_worker_finished(self):
        """后台线程完成"""
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("↻ 刷新")
        self._worker = None
    
    def _update_stat(self, key: str, value: str):
        """更新统计值"""
        if key in self._stat_labels:
            label = self._stat_labels[key].findChild(QLabel, "value")
            if label:
                label.setText(value)
    
    def showEvent(self, event):
        """页面显示时刷新"""
        super().showEvent(event)
        # 延迟刷新，确保页面已完全显示
        QTimer.singleShot(200, self._refresh_all)
