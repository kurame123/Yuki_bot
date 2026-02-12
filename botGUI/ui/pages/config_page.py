"""
配置管理页面 - 可视化编辑 TOML 配置
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QScrollArea,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTextEdit, QMessageBox, QGroupBox, QFrame
)
from PySide6.QtCore import Qt

from botGUI.core import ConfigIO
from botGUI.core.theme import COLORS

PAGE_STYLE = "background: transparent;"


class ConfigPage(QWidget):
    """配置管理页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_io = ConfigIO()
        self._current_file = None
        self._current_data = None
        self._editors = {}  # 存储编辑器控件
        
        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(PAGE_STYLE)
        
        self._setup_ui()
        self._load_file_list()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 左侧：文件列表
        left_panel = QVBoxLayout()
        left_panel.setSpacing(8)
        
        list_label = QLabel("配置文件")
        list_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['text']};")
        left_panel.addWidget(list_label)
        
        self._file_list = QListWidget()
        self._file_list.setFixedWidth(200)
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        left_panel.addWidget(self._file_list)
        
        layout.addLayout(left_panel)
        
        # 右侧：编辑区域
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)
        
        # 文件信息
        self._file_info = QLabel("选择一个配置文件")
        self._file_info.setStyleSheet(f"font-size: 16px; font-weight: bold;")
        right_panel.addWidget(self._file_info)
        
        self._file_desc = QLabel("")
        self._file_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        right_panel.addWidget(self._file_desc)
        
        # 编辑区域（滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self._edit_container = QWidget()
        self._edit_layout = QVBoxLayout(self._edit_container)
        self._edit_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._edit_container)
        
        right_panel.addWidget(scroll, 1)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._reload_btn = QPushButton("↻ 重新加载")
        self._reload_btn.clicked.connect(self._reload_config)
        self._reload_btn.setEnabled(False)
        
        self._save_btn = QPushButton("💾 保存配置")
        self._save_btn.setProperty("class", "success")
        self._save_btn.clicked.connect(self._save_config)
        self._save_btn.setEnabled(False)
        
        btn_layout.addWidget(self._reload_btn)
        btn_layout.addWidget(self._save_btn)
        
        right_panel.addLayout(btn_layout)
        
        layout.addLayout(right_panel, 1)
    
    def _load_file_list(self):
        """加载配置文件列表"""
        self._file_list.clear()
        
        for config in self._config_io.list_config_files():
            item = QListWidgetItem(config.name)
            item.setData(Qt.UserRole, config)
            self._file_list.addItem(item)
    
    def _on_file_selected(self, current: QListWidgetItem, previous):
        """选择文件时加载内容"""
        if not current:
            return
        
        config = current.data(Qt.UserRole)
        self._current_file = config
        self._file_info.setText(config.name)
        self._file_desc.setText(config.description)
        
        self._reload_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        
        self._load_config_content()
    
    def _clear_layout(self, layout):
        """递归清空布局中的所有控件"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())
    
    def _load_config_content(self):
        """加载配置内容到编辑器"""
        # 清空现有编辑器
        self._editors.clear()
        self._clear_layout(self._edit_layout)
        
        if not self._current_file:
            return
        
        try:
            if self._current_file.file_type == "toml":
                self._current_data = self._config_io.read_toml(self._current_file.name)
                self._build_toml_editors(self._current_data)
            else:
                self._current_data = self._config_io.read_env()
                self._build_env_editors(self._current_data)
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"无法加载配置文件：{e}")
    
    def _build_toml_editors(self, data: dict, prefix: str = "", parent_layout=None):
        """递归构建 TOML 编辑器"""
        layout = parent_layout or self._edit_layout
        
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # 嵌套字典 -> 分组
                group = QGroupBox(key)
                group_layout = QVBoxLayout(group)
                self._build_toml_editors(value, full_key, group_layout)
                layout.addWidget(group)
            else:
                # 基本类型 -> 编辑控件
                row = QHBoxLayout()
                label = QLabel(key)
                label.setFixedWidth(180)
                label.setStyleSheet(f"color: {COLORS['text']};")
                
                editor = self._create_editor(value)
                self._editors[full_key] = (editor, type(value))
                
                row.addWidget(label)
                row.addWidget(editor, 1)
                layout.addLayout(row)
    
    def _build_env_editors(self, data: dict):
        """构建 .env 编辑器"""
        for key, value in data.items():
            row = QHBoxLayout()
            label = QLabel(key)
            label.setFixedWidth(220)
            label.setStyleSheet(f"color: {COLORS['text']}; font-family: monospace;")
            
            editor = QLineEdit(value)
            self._editors[key] = (editor, str)
            
            row.addWidget(label)
            row.addWidget(editor, 1)
            self._edit_layout.addLayout(row)
    
    def _create_editor(self, value):
        """根据值类型创建编辑控件"""
        if isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
        elif isinstance(value, int):
            editor = QSpinBox()
            editor.setRange(-999999, 999999)
            editor.setValue(value)
        elif isinstance(value, float):
            editor = QDoubleSpinBox()
            editor.setRange(-999999, 999999)
            editor.setDecimals(4)
            editor.setValue(value)
        elif isinstance(value, list):
            editor = QLineEdit(str(value))
            editor.setPlaceholderText("列表格式: [item1, item2]")
        else:
            editor = QLineEdit(str(value))
        
        return editor
    
    def _get_editor_value(self, editor, value_type):
        """从编辑控件获取值"""
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        elif isinstance(editor, QSpinBox):
            return editor.value()
        elif isinstance(editor, QDoubleSpinBox):
            return editor.value()
        elif isinstance(editor, QLineEdit):
            text = editor.text()
            if value_type == list:
                # 尝试解析列表
                try:
                    import ast
                    return ast.literal_eval(text)
                except:
                    return text
            return text
        return None
    
    def _reload_config(self):
        """重新加载配置"""
        self._load_config_content()
    
    def _save_config(self):
        """保存配置"""
        if not self._current_file or not self._current_data:
            return
        
        try:
            if self._current_file.file_type == "toml":
                # 更新数据
                for full_key, (editor, value_type) in self._editors.items():
                    keys = full_key.split(".")
                    target = self._current_data
                    for k in keys[:-1]:
                        target = target[k]
                    target[keys[-1]] = self._get_editor_value(editor, value_type)
                
                self._config_io.write_toml(self._current_file.name, self._current_data)
            else:
                # .env 文件
                updates = {}
                for key, (editor, _) in self._editors.items():
                    updates[key] = editor.text()
                self._config_io.write_env(updates)
            
            QMessageBox.information(self, "保存成功", "配置已保存！\n如果 Bot 正在运行，可能需要重启才能生效。")
        
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存配置：{e}")
