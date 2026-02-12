"""
仪表盘页面 - 启动/停止 Bot + 状态显示
使用 QThread 进行网络请求，避免阻塞 GUI
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, Slot

from botGUI.core import ProcessManager, APIClient
from botGUI.core.process_manager import BotStatus
from botGUI.core.theme import COLORS, STATUS_COLORS

# 页面透明背景样式
PAGE_STYLE = "background: transparent;"


class DashboardStatsWorker(QThread):
    """后台获取统计数据的线程"""
    
    stats_ready = Signal(dict)
    
    def __init__(self, api_client: APIClient, parent=None):
        super().__init__(parent)
        self._api = api_client
    
    def run(self):
        resp = self._api.get_stats()
        if resp.success and resp.data:
            self.stats_ready.emit(resp.data)
        else:
            self.stats_ready.emit({})


class StatusIndicator(QFrame):
    """状态指示器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = STATUS_COLORS["stopped"]
        self._update_style()
    
    def set_status(self, status: BotStatus):
        self._color = STATUS_COLORS.get(status.value, STATUS_COLORS["stopped"])
        self._update_style()
    
    def _update_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {self._color};
                border-radius: 6px;
            }}
        """)


class StatCard(QFrame):
    """统计卡片"""
    
    def __init__(self, title: str, value: str = "-", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(160)
        self.setMinimumHeight(80)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS["surface"]};
                border-radius: 8px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        
        self._value_label = QLabel(value)
        self._value_label.setMinimumWidth(100)
        self._value_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 20px; font-weight: bold;")
        
        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
    
    def set_value(self, value: str):
        self._value_label.setText(value)


class DashboardPage(QWidget):
    """仪表盘页面"""
    
    def __init__(self, process_manager: ProcessManager, api_client: APIClient, parent=None):
        super().__init__(parent)
        self._pm = process_manager
        self._api = api_client
        self._stats_worker: DashboardStatsWorker | None = None
        
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(PAGE_STYLE)
        
        self._setup_ui()
        self._connect_signals()
        
        # 定时刷新统计
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_stats)
        self._refresh_timer.start(5000)  # 5秒刷新一次
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 标题
        title = QLabel("🌸 Yuki Bot 控制台")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {COLORS['primary']};")
        layout.addWidget(title)
        
        # 状态区域
        status_group = self._create_status_section()
        layout.addWidget(status_group)
        
        # 统计卡片
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)
        
        self._card_users = StatCard("总用户数")
        self._card_messages = StatCard("今日消息")
        self._card_tokens = StatCard("今日 Token")
        self._card_cost = StatCard("今日费用")
        
        stats_layout.addWidget(self._card_users)
        stats_layout.addWidget(self._card_messages)
        stats_layout.addWidget(self._card_tokens)
        stats_layout.addWidget(self._card_cost)
        
        layout.addLayout(stats_layout)
        
        # 快捷操作
        actions_group = self._create_actions_section()
        layout.addWidget(actions_group)
        
        layout.addStretch()
    
    def _create_status_section(self) -> QGroupBox:
        """创建状态区域"""
        group = QGroupBox("运行状态")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # 状态指示器 + 文字
        status_layout = QHBoxLayout()
        self._status_indicator = StatusIndicator()
        self._status_label = QLabel("未运行")
        self._status_label.setStyleSheet(f"font-size: 16px; font-weight: bold;")
        status_layout.addWidget(self._status_indicator)
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        
        # PID 显示
        self._pid_label = QLabel("PID: -")
        self._pid_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        
        # 按钮
        self._start_btn = QPushButton("▶ 启动 Bot")
        self._start_btn.setFixedWidth(120)
        self._start_btn.clicked.connect(self._on_start_clicked)
        
        self._stop_btn = QPushButton("■ 停止 Bot")
        self._stop_btn.setFixedWidth(120)
        self._stop_btn.setProperty("class", "danger")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setEnabled(False)
        
        self._restart_btn = QPushButton("↻ 重启")
        self._restart_btn.setFixedWidth(80)
        self._restart_btn.clicked.connect(self._on_restart_clicked)
        self._restart_btn.setEnabled(False)
        
        layout.addLayout(status_layout)
        layout.addWidget(self._pid_label)
        layout.addStretch()
        layout.addWidget(self._start_btn)
        layout.addWidget(self._stop_btn)
        layout.addWidget(self._restart_btn)
        
        return group
    
    def _create_actions_section(self) -> QGroupBox:
        """创建快捷操作区域"""
        group = QGroupBox("快捷操作")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(16, 16, 16, 16)
        
        btn_web = QPushButton("🌐 打开 Web 后台")
        btn_web.clicked.connect(self._open_web_admin)
        
        btn_logs = QPushButton("📋 查看日志目录")
        btn_logs.clicked.connect(self._open_logs_folder)
        
        btn_config = QPushButton("⚙️ 打开配置目录")
        btn_config.clicked.connect(self._open_config_folder)
        
        layout.addWidget(btn_web)
        layout.addWidget(btn_logs)
        layout.addWidget(btn_config)
        layout.addStretch()
        
        return group
    
    def _connect_signals(self):
        """连接 Qt 信号"""
        self._pm.status_changed.connect(self._on_status_changed)
    
    def _on_status_changed(self, status: BotStatus):
        """状态变化回调"""
        self._status_indicator.set_status(status)
        
        status_texts = {
            BotStatus.STOPPED: "未运行",
            BotStatus.STARTING: "启动中...",
            BotStatus.RUNNING: "运行中",
            BotStatus.STOPPING: "停止中...",
            BotStatus.ERROR: "错误",
        }
        self._status_label.setText(status_texts.get(status, "未知"))
        
        # 更新 PID
        pid = self._pm.pid
        self._pid_label.setText(f"PID: {pid}" if pid else "PID: -")
        
        # 更新按钮状态
        is_running = status == BotStatus.RUNNING
        is_busy = status in (BotStatus.STARTING, BotStatus.STOPPING)
        
        self._start_btn.setEnabled(not is_running and not is_busy)
        self._stop_btn.setEnabled(is_running and not is_busy)
        self._restart_btn.setEnabled(is_running and not is_busy)
        
        # 运行后立即刷新统计
        if status == BotStatus.RUNNING:
            QTimer.singleShot(2000, self._refresh_stats)
    
    def _on_start_clicked(self):
        self._pm.start_bot()
    
    def _on_stop_clicked(self):
        self._pm.stop_bot()
    
    def _on_restart_clicked(self):
        self._pm.restart_bot()
    
    def _refresh_stats(self):
        """刷新统计数据（非阻塞）"""
        if not self._pm.is_running:
            self._card_users.set_value("-")
            self._card_messages.set_value("-")
            self._card_tokens.set_value("-")
            self._card_cost.set_value("-")
            return
        
        # 如果已有请求在进行，跳过
        if self._stats_worker and self._stats_worker.isRunning():
            return
        
        # 在后台线程请求
        self._stats_worker = DashboardStatsWorker(self._api)
        self._stats_worker.stats_ready.connect(self._on_stats_ready)
        self._stats_worker.start()
    
    @Slot(dict)
    def _on_stats_ready(self, data: dict):
        """统计数据就绪（在主线程）"""
        self._stats_worker = None
        
        if not data:
            # API 返回空数据，可能是连接失败
            return
        
        global_stats = data.get("global", {})
        today_stats = data.get("today", {})
        
        # 总用户数
        self._card_users.set_value(str(global_stats.get("total_users", 0)))
        
        # 今日消息数（收到 + 发送）
        today_messages = today_stats.get("msg_received", 0) + today_stats.get("msg_sent", 0)
        self._card_messages.set_value(str(today_messages))
        
        # 今日 Token（R1 + V3）
        today_tokens = today_stats.get("r1_tokens", 0) + today_stats.get("v3_tokens", 0)
        self._card_tokens.set_value(f"{today_tokens:,}")
        
        # 今日费用（从全局统计中获取，或者计算）
        # 使用全局的 total_cost 作为参考
        cost = global_stats.get("total_cost", 0)
        self._card_cost.set_value(f"¥{cost:.4f}")
    
    def _open_web_admin(self):
        """打开 Web 后台"""
        import webbrowser
        from botGUI.core import ConfigIO
        port = ConfigIO().get_bot_port()
        webbrowser.open(f"http://127.0.0.1:{port}/admin")
    
    def _open_logs_folder(self):
        """打开日志目录"""
        import os
        from pathlib import Path
        logs_dir = Path(__file__).parent.parent.parent.parent / "logs"
        if logs_dir.exists():
            os.startfile(str(logs_dir))
    
    def _open_config_folder(self):
        """打开配置目录"""
        import os
        from pathlib import Path
        config_dir = Path(__file__).parent.parent.parent.parent / "configs"
        if config_dir.exists():
            os.startfile(str(config_dir))
