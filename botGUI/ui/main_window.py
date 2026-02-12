"""
主窗口 - 侧边栏导航 + 多页面布局
"""
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QCloseEvent, QPalette, QBrush, QPixmap

from botGUI.core import ProcessManager, ConfigIO, APIClient
from botGUI.core.process_manager import get_process_manager, BotStatus
from botGUI.core.api_client import get_api_client
from botGUI.core.theme import STYLESHEET, COLORS

from .pages import DashboardPage, ConfigPage, StatsPage, LogPage, AboutPage

# 背景图路径
BG_IMAGE_PATH = Path(__file__).parent / "yuki_bg.png"


class NavButton(QPushButton):
    """导航按钮"""
    
    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(f"{icon}  {text}", parent)
        self.setCheckable(True)
        self.setProperty("class", "nav")
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化核心组件
        self._pm = get_process_manager()
        self._config_io = ConfigIO()
        self._api = get_api_client(
            port=self._config_io.get_bot_port()
        )
        
        self._setup_window()
        self._setup_ui()
        self._connect_signals()
    
    def _setup_window(self):
        """设置窗口属性"""
        bot_name = self._config_io.get_bot_nickname()
        self.setWindowTitle(f"{bot_name} Bot 控制台")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        
        # 应用样式表
        self.setStyleSheet(STYLESHEET)
    
    def _setup_ui(self):
        """设置 UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        # 设置背景图
        self._setup_background(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 侧边栏
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)
        
        # 内容区域 - 更深的遮罩，确保可读性
        self._content_stack = QStackedWidget()
        self._content_stack.setStyleSheet(f"""
            QStackedWidget {{
                background-color: rgba(30, 41, 59, 0.92);
            }}
        """)
        
        # 创建页面
        self._dashboard_page = DashboardPage(self._pm, self._api)
        self._config_page = ConfigPage()
        self._stats_page = StatsPage(self._api)
        self._log_page = LogPage(self._pm)
        self._about_page = AboutPage()
        
        self._content_stack.addWidget(self._dashboard_page)
        self._content_stack.addWidget(self._stats_page)
        self._content_stack.addWidget(self._config_page)
        self._content_stack.addWidget(self._log_page)
        self._content_stack.addWidget(self._about_page)
        
        main_layout.addWidget(self._content_stack, 1)
    
    def _setup_background(self, widget: QWidget):
        """设置背景图 - 带暗色遮罩，保证可读性"""
        if BG_IMAGE_PATH.exists():
            # 背景图 + 深色半透明遮罩，让文字清晰可读
            widget.setStyleSheet(f"""
                QWidget#centralWidget {{
                    background-image: url("{BG_IMAGE_PATH.as_posix()}");
                    background-repeat: no-repeat;
                    background-position: center;
                }}
            """)
            widget.setObjectName("centralWidget")
        else:
            widget.setStyleSheet(f"background-color: {COLORS['background']};")
    
    def _create_sidebar(self) -> QFrame:
        """创建侧边栏"""
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        # 不透明侧边栏，确保导航清晰可读
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 41, 59, 0.95);
                border-right: 1px solid {COLORS['border']};
            }}
        """)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(8)
        
        # Logo / 标题
        logo_layout = QHBoxLayout()
        logo_label = QLabel("🌸")
        logo_label.setStyleSheet("font-size: 24px; background: transparent;")
        
        title_label = QLabel("Yuki Bot")
        title_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {COLORS['primary']};
            background: transparent;
        """)
        
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(title_label)
        logo_layout.addStretch()
        layout.addLayout(logo_layout)
        
        layout.addSpacing(20)
        
        # 导航按钮
        self._nav_buttons = []
        
        nav_items = [
            ("🏠", "仪表盘", 0),
            ("📊", "统计数据", 1),
            ("⚙️", "配置管理", 2),
            ("📋", "运行日志", 3),
            ("💜", "关于", 4),
        ]
        
        for icon, text, index in nav_items:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked, i=index: self._switch_page(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)
        
        # 默认选中第一个
        self._nav_buttons[0].setChecked(True)
        
        layout.addStretch()
        
        # 底部状态
        self._status_indicator = QLabel("● 未运行")
        self._status_indicator.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 12px;
            background: transparent;
            padding: 8px;
        """)
        layout.addWidget(self._status_indicator)
        
        return sidebar
    
    def _connect_signals(self):
        """连接 Qt 信号"""
        self._pm.status_changed.connect(self._on_bot_status_changed)
    
    def _switch_page(self, index: int):
        """切换页面"""
        self._content_stack.setCurrentIndex(index)
        
        # 更新按钮状态
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
    
    def _on_bot_status_changed(self, status: BotStatus):
        """Bot 状态变化"""
        status_map = {
            BotStatus.STOPPED: ("● 未运行", COLORS["text_secondary"]),
            BotStatus.STARTING: ("● 启动中...", COLORS["warning"]),
            BotStatus.RUNNING: ("● 运行中", COLORS["success"]),
            BotStatus.STOPPING: ("● 停止中...", COLORS["warning"]),
            BotStatus.ERROR: ("● 错误", COLORS["error"]),
        }
        
        text, color = status_map.get(status, ("● 未知", COLORS["text_secondary"]))
        self._status_indicator.setText(text)
        self._status_indicator.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            background: transparent;
            padding: 8px;
        """)
    
    def closeEvent(self, event: QCloseEvent):
        """关闭窗口时停止 Bot"""
        if self._pm.is_running:
            # 可以弹窗询问是否停止 Bot
            self._pm.stop_bot()
        event.accept()
