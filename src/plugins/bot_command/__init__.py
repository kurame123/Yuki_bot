"""
Bot 命令插件
提供管理和公共命令功能
"""
from .public_cmd import help_matcher, open_group, open_friend
from .admin_cmd import (
    test_matcher,
    ban_matcher,
    unban_matcher,
    baninfo_matcher,
    banlist_matcher,
    banstat_matcher,
    banclean_matcher
)

__all__ = [
    "help_matcher",
    "open_group",
    "open_friend",
    "test_matcher",
    "ban_matcher",
    "unban_matcher",
    "baninfo_matcher",
    "banlist_matcher",
    "banstat_matcher",
    "banclean_matcher"
]
