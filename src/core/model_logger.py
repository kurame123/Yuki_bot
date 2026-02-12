"""
模型调用日志记录器
记录所有 AI 模型的输入、输出和元数据

日志格式：
1. JSON 格式（机器可读）：logs/organizer/*.json, logs/generator/*.json
2. TOML 格式（人类可读）：logs/llm_trace.log - 每次调用追加一条，结构清晰
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


# ============ TOML 格式调试日志 ============

# 调试日志路径
_TRACE_LOG_PATH: Optional[Path] = None


def _get_trace_log_path() -> Path:
    """获取调试日志路径（懒加载）"""
    global _TRACE_LOG_PATH
    if _TRACE_LOG_PATH is None:
        project_root = Path(__file__).parent.parent.parent
        _TRACE_LOG_PATH = project_root / "logs" / "llm_trace.log"
        _TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _TRACE_LOG_PATH


def _trim_text(text: str, max_len: int = 3000) -> str:
    """截断过长文本，避免日志爆炸"""
    if len(text) > max_len:
        return text[:max_len] + "\n...[TRUNCATED]..."
    return text


def _escape_toml_multiline(text: str) -> str:
    """转义 TOML 多行字符串中的特殊字符"""
    # 替换三引号，避免破坏 TOML 格式
    return text.replace("'''", "' ' '")


def log_llm_trace(
    stage: str,
    model: str,
    user_message: str,
    system_prompt: str,
    output: str,
    elapsed_time: float,
    user_id: str = "",
    temperature: float = 0.0,
    max_tokens: int = 0,
    context_summary: str = "",
    reasoning_content: str = "",
    is_blocked: bool = False,
    block_reason: str = ""
) -> None:
    """
    记录一次 LLM 调用到 llm_trace.log（TOML 风格，人类可读）
    
    Args:
        stage: 阶段名称 (organizer / generator / guard)
        model: 模型名称
        user_message: 用户消息
        system_prompt: 系统提示词
        output: 模型输出
        elapsed_time: 耗时（秒）
        user_id: 用户 ID（可选）
        temperature: 温度参数
        max_tokens: 最大 token 数
        context_summary: 场景摘要（仅 generator 阶段）
        reasoning_content: 推理模型的思考过程（如 DeepSeek-R1）
        is_blocked: 是否被拦截（仅 guard 阶段）
        block_reason: 拦截原因（仅 guard 阶段）
    """
    try:
        log_path = _get_trace_log_path()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 截断和转义
        user_message = _escape_toml_multiline(user_message)
        system_prompt = _escape_toml_multiline(_trim_text(system_prompt))
        output = _escape_toml_multiline(_trim_text(output))
        context_summary = _escape_toml_multiline(_trim_text(context_summary)) if context_summary else ""
        reasoning_content = _escape_toml_multiline(_trim_text(reasoning_content, max_len=5000)) if reasoning_content else ""
        block_reason = _escape_toml_multiline(block_reason) if block_reason else ""
        
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[[{stage}_call]]\n")
            f.write(f'time = "{now}"\n')
            f.write(f'model = "{model}"\n')
            f.write(f'elapsed_seconds = {elapsed_time:.2f}\n')
            if user_id:
                f.write(f'user_id = "{user_id}"\n')
            f.write(f'temperature = {temperature}\n')
            f.write(f'max_tokens = {max_tokens}\n')
            
            # Guard 特有字段
            if stage == "guard":
                f.write(f'is_blocked = {str(is_blocked).lower()}\n')
                if block_reason:
                    f.write(f'block_reason = "{block_reason}"\n')
            
            f.write('\n')
            
            # 用户消息
            f.write("user_message = '''\n")
            f.write(user_message)
            f.write("\n'''\n\n")
            
            # 场景摘要（仅 generator）
            if context_summary:
                f.write("context_summary = '''\n")
                f.write(context_summary)
                f.write("\n'''\n\n")
            
            # 系统提示词
            f.write("system_prompt = '''\n")
            f.write(system_prompt)
            f.write("\n'''\n\n")
            
            # 推理过程（如果有）
            if reasoning_content:
                f.write("reasoning = '''\n")
                f.write(reasoning_content)
                f.write("\n'''\n\n")
            
            # 模型输出
            f.write("output = '''\n")
            f.write(output)
            f.write("\n'''\n\n")
            
            # 分隔线
            f.write("# " + "=" * 60 + "\n\n")
            
    except Exception as e:
        # 调试日志失败不应影响主流程
        print(f"[llm_trace] 写入失败: {e}")


# ============ JSON 格式日志（原有功能） ============

class ModelLogger:
    """模型调用日志记录器（单例）"""
    
    _instance: Optional['ModelLogger'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 日志目录路径
        project_root = Path(__file__).parent.parent.parent
        self.logs_dir = project_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # 为不同模型创建子目录
        self.organizer_dir = self.logs_dir / "organizer"
        self.generator_dir = self.logs_dir / "generator"
        self.organizer_dir.mkdir(exist_ok=True)
        self.generator_dir.mkdir(exist_ok=True)
        
        # 当前日期和文件路径（用于缓存）
        self._current_date = None
        self._organizer_file = None
        self._generator_file = None
        self._organizer_logs = []
        self._generator_logs = []
    
    def _get_today_files(self):
        """获取今天的日志文件路径和日期"""
        today = datetime.now().date()
        
        # 如果日期改变，需要保存前一天的数据并清空缓存
        if self._current_date != today:
            # 保存前一天的日志（如果有的话）
            if self._current_date is not None:
                if self._organizer_logs:
                    self._write_logs_to_file(self._organizer_file, self._organizer_logs)
                if self._generator_logs:
                    self._write_logs_to_file(self._generator_file, self._generator_logs)
            
            # 重置为新的一天
            self._current_date = today
            date_str = today.strftime("%Y%m%d")
            self._organizer_file = self.organizer_dir / f"organizer_{date_str}.json"
            self._generator_file = self.generator_dir / f"generator_{date_str}.json"
            
            # 如果文件存在，读取已有的日志
            self._organizer_logs = self._read_existing_logs(self._organizer_file)
            self._generator_logs = self._read_existing_logs(self._generator_file)
    
    def _read_existing_logs(self, filepath: Path) -> List[Dict[str, Any]]:
        """读取已存在的日志文件"""
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 如果是列表则直接返回，否则当成单条记录
                    return data if isinstance(data, list) else [data]
            except Exception as e:
                print(f"Failed to read existing log file {filepath}: {e}")
        return []
    
    def log_organizer_call(
        self,
        user_message: str,
        context_summary: str,
        system_prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        elapsed_time: float
    ) -> None:
        """记录 Organizer 模型调用"""
        self._get_today_files()
        
        timestamp = datetime.now().isoformat()
        
        record = {
            "timestamp": timestamp,
            "model": model_name,
            "stage": "organizer",
            "input": {
                "user_message": user_message,
                "system_prompt": system_prompt
            },
            "output": {
                "context_summary": context_summary
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            "metadata": {
                "elapsed_time_seconds": elapsed_time
            }
        }
        
        self._organizer_logs.append(record)
        # 实时保存到文件
        self._write_logs_to_file(self._organizer_file, self._organizer_logs)
        
        # 同时写入人类可读的 TOML 格式日志
        log_llm_trace(
            stage="organizer",
            model=model_name,
            user_message=user_message,
            system_prompt=system_prompt,
            output=context_summary,
            elapsed_time=elapsed_time,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def log_generator_call(
        self,
        user_message: str,
        context_summary: str,
        system_prompt: str,
        reply: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        elapsed_time: float,
        reasoning_content: str = ""
    ) -> None:
        """记录 Generator 模型调用"""
        self._get_today_files()
        
        timestamp = datetime.now().isoformat()
        
        record = {
            "timestamp": timestamp,
            "model": model_name,
            "stage": "generator",
            "input": {
                "user_message": user_message,
                "context_summary": context_summary,
                "system_prompt": system_prompt
            },
            "output": {
                "reply": reply,
                "reasoning_content": reasoning_content  # 新增：思考过程
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            "metadata": {
                "elapsed_time_seconds": elapsed_time
            }
        }
        
        self._generator_logs.append(record)
        # 实时保存到文件
        self._write_logs_to_file(self._generator_file, self._generator_logs)
        
        # 同时写入人类可读的 TOML 格式日志
        log_llm_trace(
            stage="generator",
            model=model_name,
            user_message=user_message,
            system_prompt=system_prompt,
            output=reply,
            elapsed_time=elapsed_time,
            temperature=temperature,
            max_tokens=max_tokens,
            context_summary=context_summary,
            reasoning_content=reasoning_content  # 新增：思考过程
        )
    
    def log_guard_call(
        self,
        user_message: str,
        system_prompt: str,
        output: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        elapsed_time: float,
        is_blocked: bool,
        block_reason: str = "",
        user_id: str = ""
    ) -> None:
        """记录 Guard 模型调用"""
        self._get_today_files()
        
        timestamp = datetime.now().isoformat()
        
        record = {
            "timestamp": timestamp,
            "model": model_name,
            "stage": "guard",
            "input": {
                "user_message": user_message,
                "system_prompt": system_prompt
            },
            "output": {
                "result": output,
                "is_blocked": is_blocked,
                "block_reason": block_reason
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens
            },
            "metadata": {
                "elapsed_time_seconds": elapsed_time,
                "user_id": user_id
            }
        }
        
        # 创建 guard 目录（如果不存在）
        guard_dir = self.logs_dir / "guard"
        guard_dir.mkdir(exist_ok=True)
        
        # 获取今天的 guard 日志文件
        date_str = datetime.now().date().strftime("%Y%m%d")
        guard_file = guard_dir / f"guard_{date_str}.json"
        
        # 读取现有日志
        guard_logs = self._read_existing_logs(guard_file)
        guard_logs.append(record)
        
        # 保存到文件
        self._write_logs_to_file(guard_file, guard_logs)
        
        # 同时写入人类可读的 TOML 格式日志
        log_llm_trace(
            stage="guard",
            model=model_name,
            user_message=user_message,
            system_prompt=system_prompt,
            output=output,
            elapsed_time=elapsed_time,
            user_id=user_id,
            temperature=temperature,
            max_tokens=max_tokens,
            is_blocked=is_blocked,
            block_reason=block_reason
        )
    
    def _write_logs_to_file(self, filepath: Path, logs: List[Dict[str, Any]]) -> None:
        """将日志列表写入文件"""
        try:
            os.makedirs(filepath.parent, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"Failed to write model logs to {filepath}: {e}")
    
    def get_latest_logs(self, stage: str = "all", limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的日志记录"""
        self._get_today_files()
        
        logs = []
        
        if stage in ["organizer", "all"]:
            logs.extend(self._organizer_logs[-limit:])
        
        if stage in ["generator", "all"]:
            logs.extend(self._generator_logs[-limit:])
        
        # 按时间戳排序
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs[:limit]


def get_model_logger() -> ModelLogger:
    """获取全局模型日志记录器单例"""
    return ModelLogger()
