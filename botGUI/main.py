"""
Yuki Bot GUI 启动入口
"""
import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "gui.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GUI")


def exception_hook(exc_type, exc_value, exc_tb):
    """全局异常处理"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.error(f"未捕获的异常:\n{error_msg}")
    
    # 写入崩溃日志
    crash_file = log_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    crash_file.write_text(error_msg, encoding="utf-8")
    logger.error(f"崩溃日志已保存: {crash_file}")


def main():
    """GUI 主入口"""
    # 安装全局异常处理
    sys.excepthook = exception_hook
    
    logger.info("=" * 50)
    logger.info("Yuki Bot GUI 启动")
    logger.info("=" * 50)
    
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        
        # 启用高 DPI 支持
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        app = QApplication(sys.argv)
        app.setApplicationName("Yuki Bot GUI")
        app.setApplicationVersion("1.0.0")
        
        # 设置默认字体
        font = QFont("Microsoft YaHei", 10)
        app.setFont(font)
        
        # 创建主窗口
        from botGUI.ui import MainWindow
        window = MainWindow()
        window.show()
        
        logger.info("GUI 窗口已显示")
        
        exit_code = app.exec()
        logger.info(f"GUI 正常退出，退出码: {exit_code}")
        sys.exit(exit_code)
        
    except Exception as e:
        logger.exception(f"GUI 启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
