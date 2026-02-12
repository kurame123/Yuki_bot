"""
GUI 主题配置 - 颜色、样式表
"""

# Yuki 风格配色
COLORS = {
    "primary": "#60a5fa",       # 浅蓝色
    "secondary": "#a7f3d0",     # 薄荷绿
    "accent": "#fda4af",        # 粉色
    "background": "#1e293b",    # 深蓝灰背景
    "surface": "#334155",       # 卡片背景
    "text": "#f1f5f9",          # 主文字
    "text_secondary": "#94a3b8", # 次要文字
    "success": "#4ade80",       # 成功绿
    "warning": "#fbbf24",       # 警告黄
    "error": "#f87171",         # 错误红
    "border": "#475569",        # 边框色
}

# 状态颜色
STATUS_COLORS = {
    "running": "#4ade80",
    "stopped": "#94a3b8",
    "starting": "#fbbf24",
    "stopping": "#fbbf24",
    "error": "#f87171",
}

# 全局样式表
STYLESHEET = f"""
/* 全局样式 */
QWidget {{
    background-color: {COLORS["background"]};
    color: {COLORS["text"]};
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}}

/* 主窗口 */
QMainWindow {{
    background-color: {COLORS["background"]};
}}

/* 按钮 */
QPushButton {{
    background-color: {COLORS["primary"]};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #3b82f6;
}}

QPushButton:pressed {{
    background-color: #2563eb;
}}

QPushButton:disabled {{
    background-color: {COLORS["border"]};
    color: {COLORS["text_secondary"]};
}}

/* 成功按钮 */
QPushButton[class="success"] {{
    background-color: {COLORS["success"]};
}}

QPushButton[class="success"]:hover {{
    background-color: #22c55e;
}}

/* 危险按钮 */
QPushButton[class="danger"] {{
    background-color: {COLORS["error"]};
}}

QPushButton[class="danger"]:hover {{
    background-color: #ef4444;
}}

/* 侧边栏按钮 */
QPushButton[class="nav"] {{
    background-color: transparent;
    text-align: left;
    padding: 12px 16px;
    border-radius: 8px;
}}

QPushButton[class="nav"]:hover {{
    background-color: {COLORS["surface"]};
}}

QPushButton[class="nav"]:checked {{
    background-color: {COLORS["primary"]};
}}

/* 输入框 */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px;
    color: {COLORS["text"]};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {COLORS["primary"]};
}}

/* 下拉框 */
QComboBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    color: {COLORS["text"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["primary"]};
}}

/* 标签 */
QLabel {{
    color: {COLORS["text"]};
    background: transparent;
}}

QLabel[class="title"] {{
    font-size: 18px;
    font-weight: bold;
    color: {COLORS["primary"]};
}}

QLabel[class="subtitle"] {{
    font-size: 14px;
    color: {COLORS["text_secondary"]};
}}

/* 分组框 */
QGroupBox {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: {COLORS["text"]};
}}

/* 滚动区域 */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background-color: {COLORS["background"]};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS["border"]};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS["text_secondary"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* 表格 */
QTableWidget {{
    background-color: {COLORS["surface"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    gridline-color: {COLORS["border"]};
}}

QTableWidget::item {{
    padding: 8px;
}}

QTableWidget::item:selected {{
    background-color: {COLORS["primary"]};
}}

QHeaderView::section {{
    background-color: {COLORS["background"]};
    color: {COLORS["text"]};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
}}

/* 选项卡 */
QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    background-color: {COLORS["surface"]};
}}

QTabBar::tab {{
    background-color: {COLORS["background"]};
    color: {COLORS["text_secondary"]};
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:selected {{
    background-color: {COLORS["surface"]};
    color: {COLORS["text"]};
}}

/* 进度条 */
QProgressBar {{
    background-color: {COLORS["surface"]};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS["primary"]};
    border-radius: 4px;
}}

/* 复选框 */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {COLORS["border"]};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS["primary"]};
    border-color: {COLORS["primary"]};
}}

/* 日志区域 */
QPlainTextEdit[class="log"] {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    background-color: #0f172a;
    border: 1px solid {COLORS["border"]};
}}
"""
