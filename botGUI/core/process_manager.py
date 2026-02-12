"""
Bot 进程管理器 - 启动/停止 bot.py 子进程
使用 Qt 信号实现线程安全的 GUI 更新
"""
import subprocess
import signal
import sys
import os
from pathlib import Path
from typing import Optional
from enum import Enum

from PySide6.QtCore import QObject, Signal, QThread


class BotStatus(Enum):
    """Bot 运行状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class LogReaderThread(QThread):
    """日志读取线程 - 在后台读取子进程输出"""
    
    log_line = Signal(str)       # 新日志行信号
    process_exited = Signal(int) # 进程退出信号，参数是退出码
    
    def __init__(self, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._process = process
        self._running = True
    
    def run(self):
        """线程主循环"""
        try:
            # 持续读取 stdout
            while self._running and self._process.poll() is None:
                line = self._process.stdout.readline()
                if line:
                    self.log_line.emit(line.rstrip())
            
            # 读取剩余输出
            for line in self._process.stdout:
                if line:
                    self.log_line.emit(line.rstrip())
            
            # 进程已结束
            exit_code = self._process.returncode if self._process.returncode is not None else -1
            self.process_exited.emit(exit_code)
            
        except Exception as e:
            self.log_line.emit(f"[GUI] 读取日志出错: {e}")
            self.process_exited.emit(-1)
    
    def stop(self):
        """停止读取"""
        self._running = False


class StopBotThread(QThread):
    """停止 Bot 的线程 - 避免 wait() 阻塞主线程"""
    
    finished_signal = Signal(bool, str)  # (成功, 消息)
    
    def __init__(self, process: subprocess.Popen, timeout: float = 5.0, parent=None):
        super().__init__(parent)
        self._process = process
        self._timeout = timeout
    
    def run(self):
        """执行停止操作"""
        try:
            # Windows 使用 CTRL_BREAK_EVENT
            if sys.platform == "win32":
                self._process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self._process.terminate()
            
            # 等待进程结束
            try:
                self._process.wait(timeout=self._timeout)
                self.finished_signal.emit(True, "Bot 已正常停止")
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
                self.finished_signal.emit(True, "Bot 已强制终止")
                
        except Exception as e:
            self.finished_signal.emit(False, f"停止失败: {e}")


class ProcessManager(QObject):
    """
    Bot 进程管理器（单例）
    
    所有状态变化和日志都通过 Qt 信号发送，确保线程安全
    """
    
    # Qt 信号 - GUI 可以连接这些信号来更新界面
    status_changed = Signal(BotStatus)
    log_received = Signal(str)
    
    _instance: Optional["ProcessManager"] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, parent=None):
        if self._initialized:
            return
        super().__init__(parent)
        self._initialized = True
        
        self._process: Optional[subprocess.Popen] = None
        self._status = BotStatus.STOPPED
        self._log_buffer: list[str] = []
        self._max_log_lines = 500
        
        self._log_thread: Optional[LogReaderThread] = None
        self._stop_thread: Optional[StopBotThread] = None
        
        # 项目根目录 - 支持打包后和开发环境
        self._project_root = self._get_project_root()
    
    def _get_project_root(self) -> Path:
        """获取项目根目录，兼容打包后和开发环境"""
        # 检查是否是 PyInstaller 打包环境
        if getattr(sys, 'frozen', False):
            # 打包后：exe 所在目录的上级就是项目根目录
            # dist/YukiBotGUI/YukiBotGUI.exe -> 项目根目录应该是 dist/YukiBotGUI 的上上级
            # 但实际上打包后应该把 GUI 放到项目根目录运行
            # 所以直接用 exe 所在目录的上级
            exe_dir = Path(sys.executable).parent
            # 如果 exe 在 dist/YukiBotGUI 下，需要回到项目根目录
            # 检查是否存在 bot.py 来确定根目录
            for candidate in [exe_dir.parent.parent, exe_dir.parent, exe_dir]:
                if (candidate / "bot.py").exists():
                    return candidate
            # 默认返回 exe 上两级目录
            return exe_dir.parent.parent
        else:
            # 开发环境：基于源码位置
            return Path(__file__).parent.parent.parent
    
    @property
    def status(self) -> BotStatus:
        return self._status
    
    @property
    def is_running(self) -> bool:
        return self._status == BotStatus.RUNNING
    
    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None
    
    @property
    def log_buffer(self) -> list[str]:
        return self._log_buffer.copy()
    
    def _set_status(self, status: BotStatus):
        """更新状态并发送信号"""
        self._status = status
        self.status_changed.emit(status)
    
    def _append_log(self, line: str):
        """添加日志行并发送信号"""
        self._log_buffer.append(line)
        if len(self._log_buffer) > self._max_log_lines:
            self._log_buffer.pop(0)
        self.log_received.emit(line)
    
    def _on_log_line(self, line: str):
        """日志线程的回调（通过信号，已在主线程）"""
        self._append_log(line)
    
    def _on_process_exited(self, exit_code: int):
        """进程退出的回调（通过信号，已在主线程）"""
        if exit_code == 0:
            self._append_log("[GUI] Bot 进程正常退出")
        else:
            self._append_log(f"[GUI] Bot 进程退出，退出码: {exit_code}")
        
        self._process = None
        self._log_thread = None
        self._set_status(BotStatus.STOPPED)
    
    def _on_stop_finished(self, success: bool, message: str):
        """停止线程完成的回调（通过信号，已在主线程）"""
        self._append_log(f"[GUI] {message}")
        self._process = None
        self._stop_thread = None
        self._set_status(BotStatus.STOPPED if success else BotStatus.ERROR)
    
    def start_bot(self) -> bool:
        """
        启动 Bot 进程（非阻塞）
        
        Returns:
            bool: 是否成功启动
        """
        if self._status in (BotStatus.RUNNING, BotStatus.STARTING):
            self._append_log("[GUI] Bot 已在运行中")
            return False
        
        self._set_status(BotStatus.STARTING)
        self._log_buffer.clear()
        
        try:
            # 打包环境下 sys.executable 是 GUI exe，需要找系统 Python
            if getattr(sys, 'frozen', False):
                # 打包环境：使用系统 Python
                import shutil
                python_exe = shutil.which("python") or shutil.which("python3") or "python"
            else:
                python_exe = sys.executable
            
            bot_script = self._project_root / "bot.py"
            
            self._append_log(f"[GUI] 启动 Bot: {python_exe} {bot_script}")
            
            # 启动子进程 - 不阻塞
            # 设置环境变量强制 UTF-8 编码，解决 Windows GBK 编码问题
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            
            self._process = subprocess.Popen(
                [python_exe, "-u", str(bot_script)],  # -u 禁用缓冲
                cwd=str(self._project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",  # 遇到无法解码的字符用 ? 替代
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self._append_log(f"[GUI] Bot 进程已启动，PID: {self._process.pid}")
            
            # 启动日志读取线程
            self._log_thread = LogReaderThread(self._process)
            self._log_thread.log_line.connect(self._on_log_line)
            self._log_thread.process_exited.connect(self._on_process_exited)
            self._log_thread.start()
            
            self._set_status(BotStatus.RUNNING)
            return True
            
        except Exception as e:
            self._append_log(f"[GUI] 启动失败: {e}")
            self._set_status(BotStatus.ERROR)
            return False
    
    def stop_bot(self, timeout: float = 5.0) -> bool:
        """
        停止 Bot 进程（非阻塞）
        
        停止操作在后台线程执行，完成后通过信号通知
        """
        if self._status == BotStatus.STOPPED:
            self._append_log("[GUI] Bot 未在运行")
            return True
        
        if not self._process:
            self._set_status(BotStatus.STOPPED)
            return True
        
        if self._status == BotStatus.STOPPING:
            self._append_log("[GUI] 正在停止中，请稍候...")
            return False
        
        self._set_status(BotStatus.STOPPING)
        self._append_log("[GUI] 正在停止 Bot...")
        
        # 停止日志读取线程
        if self._log_thread:
            self._log_thread.stop()
        
        # 在后台线程执行停止操作
        self._stop_thread = StopBotThread(self._process, timeout)
        self._stop_thread.finished_signal.connect(self._on_stop_finished)
        self._stop_thread.start()
        
        return True
    
    def restart_bot(self) -> bool:
        """重启 Bot（先停止再启动）"""
        self._append_log("[GUI] 正在重启 Bot...")
        
        if self._status == BotStatus.RUNNING:
            # 停止后自动启动
            if self._stop_thread:
                return False
            
            self._set_status(BotStatus.STOPPING)
            self._append_log("[GUI] 正在停止 Bot...")
            
            if self._log_thread:
                self._log_thread.stop()
            
            self._stop_thread = StopBotThread(self._process, 5.0)
            self._stop_thread.finished_signal.connect(self._on_restart_stop_finished)
            self._stop_thread.start()
            return True
        else:
            return self.start_bot()
    
    def _on_restart_stop_finished(self, success: bool, message: str):
        """重启时停止完成的回调"""
        self._append_log(f"[GUI] {message}")
        self._process = None
        self._stop_thread = None
        
        if success:
            # 停止成功，立即启动
            self.start_bot()
        else:
            self._set_status(BotStatus.ERROR)


# 全局单例
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """获取进程管理器单例"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
