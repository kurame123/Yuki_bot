"""
关于页面 - 显示 Bot 信息
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont

from botGUI.core.theme import COLORS

PAGE_STYLE = "background: transparent;"


class AboutPage(QWidget):
    """关于页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(PAGE_STYLE)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setAlignment(Qt.AlignCenter)
        
        # Logo / 头像区域
        avatar_frame = QFrame()
        avatar_frame.setFixedSize(120, 120)
        avatar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['primary']};
                border-radius: 60px;
            }}
        """)
        
        avatar_layout = QVBoxLayout(avatar_frame)
        avatar_label = QLabel("🌸")
        avatar_label.setStyleSheet("font-size: 48px; background: transparent;")
        avatar_label.setAlignment(Qt.AlignCenter)
        avatar_layout.addWidget(avatar_label)
        
        layout.addWidget(avatar_frame, alignment=Qt.AlignCenter)
        
        # 名称
        name_label = QLabel("Yuki Bot")
        name_label.setStyleSheet(f"""
            font-size: 32px;
            font-weight: bold;
            color: {COLORS['primary']};
        """)
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        
        # 版本
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        
        # 描述
        desc_label = QLabel("一个可爱的 QQ 聊天机器人 💕\n基于 NoneBot2 + OneBot v11")
        desc_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLORS['border']};")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
        # 技术栈
        tech_label = QLabel(
            "技术栈：\n"
            "• NoneBot2 - 异步机器人框架\n"
            "• FastAPI - Web 后台\n"
            "• ChromaDB - 向量记忆存储\n"
            "• PySide6 - GUI 界面"
        )
        tech_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        tech_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tech_label)
        
        # 链接按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        
        github_btn = QPushButton("📦 GitHub")
        github_btn.clicked.connect(lambda: self._open_url("https://github.com"))
        
        docs_btn = QPushButton("📖 文档")
        docs_btn.clicked.connect(lambda: self._open_url("https://nonebot.dev"))
        
        btn_layout.addStretch()
        btn_layout.addWidget(github_btn)
        btn_layout.addWidget(docs_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        
        # 底部版权
        copyright_label = QLabel("Made with ❤️ by Yuki")
        copyright_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)
    
    def _open_url(self, url: str):
        """打开 URL"""
        import webbrowser
        webbrowser.open(url)
