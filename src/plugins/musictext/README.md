# MusicText 歌词总结插件

## 概述

MusicText 是一个轻量级的歌词总结插件，复用 Music_plug 的搜索结果缓存，通过 AI 模型生成简洁的歌词总结（≤180字）。

## 设计原则

- **不参与对话流程**：独立运行，不写入短期对话记忆
- **复用现有基础设施**：使用 Music_plug 的搜索缓存、ConfigManager、AIManager
- **最小改动**：不修改 Music_plug 代码，只读取其缓存
- **可维护性**：清晰的目录结构，独立的配置文件

## 目录结构

```
src/plugins/musictext/
├── __init__.py              # 插件入口
├── commands.py              # /总结 命令处理
├── README.md                # 本文档
└── services/
    ├── __init__.py
    ├── lyrics_client.py     # 歌词获取与清洗
    └── summarizer.py        # AI 总结生成
```

## 工作流程

```
用户: /song 晴天
  ↓
Music_plug 搜索并缓存结果
  ↓
用户: /总结 1
  ↓
MusicText 从缓存获取歌曲信息
  ↓
调用歌词接口获取原始歌词
  ↓
清洗歌词（去时间戳、metadata）
  ↓
调用 AI 模型生成总结
  ↓
返回总结结果
```

## 核心功能

### 1. 歌词获取 (lyrics_client.py)

- 支持 QQ 音乐和网易云音乐
- 统一接口：`fetch_lyrics(platform, song_id)`
- 自动重试和超时处理（12秒）
- 错误信息友好提示

### 2. 歌词清洗 (_clean_lyrics)

清洗步骤：
1. 去除时间戳：`[00:12.34]` → 空
2. 替换换行符：`\\n` → `\n`
3. 去除 metadata：作词、作曲、编曲等
4. 去除空行
5. 限制长度：最多 5000 字符

### 3. AI 总结 (summarizer.py)

- 使用 `ai_model_config.toml` 的 generator 模型
- 温度：0.4（客观总结）
- 最大 tokens：250
- 硬性截断：确保 ≤180 字

### 4. 命令处理 (commands.py)

- 命令：`/总结 序号`
- 冷却时间：10 秒（可配置）
- 权限控制：使用 whitelist_rule
- 错误处理：友好的错误提示

## 配置文件

位置：`configs/musictext_config.toml`

```toml
[general]
enable = true
max_chars = 180
cooldown_seconds = 10

[prompt]
template = """..."""

[qq]
enable = true
base_url = "http://127.0.0.1:3101"
lyrics_path = "/lyric"
songmid_param = "songmid"

[netease]
enable = true
base_url = "http://127.0.0.1:3000"
lyrics_path = "/lyric"
id_param = "id"
```

## 依赖关系

### 复用的模块

- `Music_plug.state`：搜索结果缓存
- `Music_plug.models.SongItem`：歌曲数据模型
- `ConfigManager`：配置管理
- `AIManager`：AI 模型调用
- `whitelist_rule`：权限控制
- `logger`：日志记录

### 新增的依赖

- `httpx`：HTTP 请求（已在项目中）
- `re`：正则表达式（标准库）

## 使用示例

```
用户: /song 晴天
Bot: 🎵 QQ音乐 搜索结果：
     1. 晴天 - 周杰伦
     2. 晴天 - 孙燕姿
     ...

用户: /总结 1
Bot: 正在获取歌词并总结，请稍候...
     🎵 晴天 - 周杰伦
     
     这首歌描述了一段青春时期的校园恋情，通过雨天、晴天等天气变化来隐喻感情的起伏。
     歌词充满怀旧情绪，表达了对过去美好时光的追忆和对逝去爱情的不舍。
     整体情感温暖而略带忧伤，展现了青春期特有的纯真与遗憾。
```

## 错误处理

| 错误情况 | 提示信息 |
|---------|---------|
| 未搜索歌曲 | 当前没有可用的点歌结果，请先使用 /song 搜索歌曲 |
| 序号超出范围 | 序号超出范围（1-6），请重新输入 |
| 冷却中 | 请稍等 X 秒后再试 |
| 无歌词 | 该歌曲暂无歌词或为纯音乐，无法总结 |
| 接口超时 | 获取歌词超时，请稍后再试 |
| 生成失败 | 生成总结失败，请稍后再试 |

## 性能优化

1. **冷却机制**：防止频繁调用 LLM
2. **超时控制**：12 秒超时避免长时间等待
3. **长度限制**：歌词最多 5000 字符，避免 token 爆炸
4. **异步处理**：使用 async/await 提高并发性能

## 测试

### 配置加载测试

```bash
python test_musictext_config.py
```

### 歌词清洗测试

```bash
python test_lyrics_clean.py
```

## 未来扩展

可能的扩展方向：

1. **多平台支持**：酷狗、酷我、Spotify
2. **歌词翻译**：支持中英文互译
3. **情感分析**：分析歌词情感倾向
4. **关键词提取**：提取歌词关键词
5. **记忆写入**：可选地将总结写入向量记忆
6. **批量总结**：一次总结多首歌曲
7. **总结风格**：支持不同风格的总结（客观/主观/诗意）

## 注意事项

1. **接口依赖**：需要 QQ 音乐或网易云音乐 API 服务运行
2. **成本控制**：每次总结会调用 LLM，注意 API 成本
3. **缓存生命周期**：搜索结果缓存在内存中，重启后失效
4. **歌词版权**：仅用于个人学习和研究，不得用于商业用途

## 维护指南

### 添加新平台

1. 在 `musictext_config.toml` 添加平台配置
2. 在 `config_schema.py` 添加配置模型
3. 在 `lyrics_client.py` 添加 `_fetch_xxx_lyrics` 方法
4. 更新 `fetch_lyrics` 的平台判断

### 调整总结风格

修改 `musictext_config.toml` 的 `[prompt].template`

### 调整清洗规则

修改 `lyrics_client.py` 的 `_clean_lyrics` 方法

## 贡献者

- 初始实现：Kiro AI Assistant
- 设计参考：用户需求文档

## 许可证

与主项目保持一致
