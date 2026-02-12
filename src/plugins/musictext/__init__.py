"""
歌词总结插件
复用 /song 的搜索结果，拉取歌词并生成总结
"""
from . import commands

__plugin_name__ = "musictext"
__plugin_usage__ = """
歌词总结插件

命令：
/总结 序号 - 总结指定歌曲的歌词（需先使用 /song 搜索）

示例：
/song 晴天
/总结 1
"""
