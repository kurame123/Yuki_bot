# Yuki Bot - 月代雪互动机器人

<div align="center">

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![NoneBot](https://img.shields.io/badge/NoneBot-2.1.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Version](https://img.shields.io/badge/Version-1.0.0-red.svg)

基于游戏《魔法少女的魔女审判》角色**月代雪**打造的智能互动 QQ 机器人

具备先进的 RAG 记忆系统、好感度系统和角色扮演能力

[关于月代雪](#关于月代雪) • [功能特性](#功能特性) • [快速开始](#快速开始) • [配置说明](#配置说明) • [使用指南](#使用指南)

</div>

---

## ⚠️ 重要声明

> **本项目仅供学习交流使用，严禁用于商业用途！**
> 
> - ❌ **禁止任何形式的商业化使用**（包括但不限于：付费服务、广告推广、商业运营等）
> - ❌ **禁止以本项目为基础进行二次开发后商业化**
> - ❌ **禁止将本项目用于任何违法违规活动**
> - ⚠️ **警惕任何以本项目名义进行的收费、诈骗等行为**
> - ⚠️ **如遇到有人声称本项目需要付费或提供付费服务，请立即举报**
> 
> **使用本项目即表示您同意：**
> - ✅ 仅用于个人学习、研究和非商业用途
> - ✅ 遵守相关法律法规和平台服务条款
> - ✅ 自行承担使用本项目产生的一切后果
> - ✅ 不得侵犯他人合法权益
> 
> **作者不对以下情况承担任何责任：**
> - 使用本项目造成的任何直接或间接损失
> - 违反法律法规或平台规则导致的封号等后果
> - 第三方利用本项目进行的任何违法违规行为
> 
> **如发现任何商业化使用或诈骗行为，请通过 Issues 举报！**

---

## 🎮 关于月代雪

本项目是基于游戏《魔法少女的魔女审判》中的角色**月代雪**打造的互动机器人。

### 角色背景
- **身份**：大魔女，魔女种族最后的幸存者
- **性格**：冷静琉璃，很少安慰他人
- **背景故事**：背负着族人被人类灭绝的仇恨，打算散播魔女因子消灭人类
- **特殊关系**：作为初中生，对艾玛和希罗有特殊感情

> **注意**：本项目为粉丝自制，与游戏官方无关。角色设定和对话内容均基于游戏原作进行二次创作。

---

## 功能特性

### 对话系统
- **角色扮演**：深度还原月代雪的人设、说话风格和性格特征
- **知识库系统**：内置角色背景知识，确保对话符合角色设定
- **注入攻击防护**：智能检测并防御 Prompt 注入攻击，保护角色人设

### 记忆系统
- **FAISS 向量记忆**：基于语义相似度的长期记忆检索
- **RAG 知识图谱**：实体-关系图谱，结构化存储对话信息
- **双数据库架构**：私聊/群聊分离存储，支持跨场景记忆检索
- **智能记忆管理**：自动垃圾回收、AI 驱动的图谱清理

### 好感度系统
- **14 级好感度等级**：从"讨厌"(-2级) 到"永恒"(13级) 的细致情感建模
- **动态温度调节**：根据好感度自动调整 AI 回复的情感温度
- **智能评分算法**：基于对话内容、长度、情感词汇的综合评分
- **情感发展**：随着互动逐渐提升好感度，解锁不同的对话风格
- **Web 管理界面**：可视化好感度统计和用户管理

### 表情包学习
- **自动学习**：智能学习用户发送的表情包
- **语义匹配**：基于对话内容自动发送相关表情包
- **相似度控制**：可调节表情包发送的匹配精度

### 娱乐功能
- **音乐点歌**：支持 QQ 音乐、网易云音乐搜索和分享
- **歌词总结**：AI 智能总结歌词内容和情感
- **色图功能**：支持多平台图片搜索（可配置 R18）
- **复读机**：智能复读群聊消息

### 安全与管理
- **白名单系统**：精确控制用户和群组访问权限
- **临时黑名单**：自动封禁恶意用户
- **Web 管理后台**：实时监控机器人状态和数据
- **定时任务**：自动清理过期数据和优化性能

## 快速开始

### 环境要求

- Python 3.9+
- 支持的操作系统：Windows、Linux、macOS
- 内存：建议 2GB 以上
- 存储：建议 5GB 以上可用空间

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/your-username/yuki-bot.git
cd yuki-bot
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置
```

4. **配置机器人**
```bash
# 编辑配置文件
configs/bot_config.toml          # 机器人基础配置
configs/ai_model_config.toml     # AI 模型配置
configs/role_play_config.toml    # 角色配置
```

5. **构建知识库**（可选）
```bash
# 将知识文档放入 knowledge_docs/ 目录
# 运行知识库构建工具
python tools/rebuild_knowledge_base.py
```

6. **启动机器人**

**Windows:**
```bash
# 双击运行
启动.bat

# 或在命令行运行
python bot.exe
```

**Linux/macOS:**
```bash
# 添加执行权限（首次运行）
chmod +x start.sh

# 启动
./start.sh
```

启动时会显示重要声明，输入 `yes` 表示同意后才能继续。

### Docker 部署

```bash
# 构建镜像
docker build -t yuki-bot .

# 运行容器
docker run -d \
  --name yuki-bot \
  -p 8080:8080 \
  -v ./data:/app/data \
  -v ./configs:/app/configs \
  yuki-bot
```

## ⚙️ 配置说明

### 核心配置文件

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置（端口、超级用户等） |
| `configs/bot_config.toml` | 机器人基础配置（白名单、回复策略等） |
| `configs/ai_model_config.toml` | AI 模型配置（API 密钥、模型参数等） |
| `configs/role_play_config.toml` | 角色扮演配置（人设、说话风格等） |

### 重要配置项

#### AI 模型配置
```toml
# AI 服务商配置
[providers.openai]
api_base = "https://api.openai.com/v1"
api_key = "your-api-key"

# 上下文整理模型选择
[organizer]
model_name = "gpt-4o-mini"
temperature = 0.3

# 内容回复模型选择
[generator]
model_name = "gpt-4o"
temperature = 0.7
```

#### 白名单配置
```toml
[bot.whitelist]
enable = true
allowed_users = [123456789]  # 允许的用户 QQ 号
allowed_groups = [987654321] # 允许的群号
```

#### 记忆系统配置
```toml
[storage]
vector_db_path = "./data/memory_v2"
similarity_threshold = 0.3
max_memory_per_user = 500
enable_knowledge_graph = true
```

## 📚 使用指南

### 基础命令

- `/chat <消息>` - 强制触发对话
- `/reload` - 重载配置文件（管理员）
- `/stats` - 查看机器人统计信息
- `/affection` - 查看好感度信息

### 知识库管理

知识库用于存储角色背景、设定、剧情等信息，确保机器人的回复符合角色人设。

1. 将角色设定文档放入 `knowledge_docs/` 目录
   - 例如：《月代雪设定集.txt》、《角色背景.md》等
2. 支持 `.txt` 和 `.md` 格式
3. 运行构建工具：
   ```bash
   python tools/rebuild_knowledge_base.py
   ```
   或直接运行：`知识库构建工具.bat`（Windows）

**建议的知识库内容**：
- 角色基本信息（姓名、年龄、身份等）
- 性格特征和说话风格
- 背景故事和经历
- 与其他角色的关系
- 重要剧情事件

### Web 管理后台

访问 `http://localhost:8080/admin` 查看：
- 机器人运行状态
- 好感度统计
- 记忆数据管理
- 用户活跃度分析

## 🏗️ 项目架构

```
yuki-bot/
├── bot.py                 # 主启动文件
├── src/
│   ├── core/             # 核心模块
│   │   ├── config_manager.py    # 配置管理
│   │   ├── Affection/           # 好感度系统
│   │   └── RAGM/               # RAG 知识图谱
│   ├── services/         # 服务层
│   │   ├── ai_manager.py       # AI 调度中心
│   │   ├── vector_service.py   # 向量服务
│   │   └── emoji_service.py    # 表情包服务
│   ├── plugins/          # 功能插件
│   │   ├── yuki_chat/          # 主聊天插件
│   │   ├── Music_plug/         # 音乐插件
│   │   └── affection_query/    # 好感度查询
│   └── web/              # Web 管理界面
├── configs/              # 配置文件
├── data/                 # 数据存储
├── tools/                # 工具脚本
└── knowledge_docs/       # 知识库文档
```

### 核心组件

#### AI 管理器 (AIManager)
- 双阶段推理流程
- 多模型调度
- 记忆整合
- 好感度集成

#### 向量服务 (VectorService)
- FAISS 向量检索
- 双数据库架构
- 跨场景记忆
- 智能相似度匹配

#### 好感度系统 (AffectionService)
- 14 级情感建模
- 动态温度调节
- 智能评分算法
- 数据持久化

## 🔧 开发指南

### 添加新插件

1. 在 `src/plugins/` 创建插件目录
2. 实现插件逻辑
3. 在 `__init__.py` 中注册

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent

my_plugin = on_command("myplugin")

@my_plugin.handle()
async def handle_my_plugin(event: MessageEvent):
    await my_plugin.send("Hello from my plugin!")
```

### 扩展 AI 功能

1. 继承 `AIManager` 类
2. 重写相关方法
3. 在配置中注册新模型

### 自定义记忆策略

1. 实现 `MemoryStrategy` 接口
2. 在 `vector_service.py` 中注册
3. 通过配置文件启用

## 📊 性能优化

### 内存优化
- 定期清理过期记忆
- 限制单用户记忆数量
- 使用 FAISS 压缩索引

### 响应速度优化
- 异步处理长时间任务
- 缓存常用数据
- 预加载活跃用户记忆

### 存储优化
- 分库分表存储
- 定期数据压缩
- 智能垃圾回收

## 🐛 故障排除

### 常见问题

**Q: 机器人无法启动**
A: 检查 Python 版本、依赖安装和配置文件格式

**Q: AI 回复异常**
A: 验证 API 密钥、网络连接和模型配置

**Q: 记忆检索失败**
A: 检查向量数据库文件权限和磁盘空间

**Q: 好感度不更新**
A: 确认数据库文件可写和用户在白名单中

### 日志分析

日志文件位置：`logs/` 目录
- `bot.log` - 主程序日志
- `model.log` - AI 模型调用日志
- `error.log` - 错误日志

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 贡献方式
1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 开发规范
- 遵循 PEP 8 代码风格
- 添加必要的注释和文档
- 编写单元测试
- 更新相关文档

## 📄 许可证与声明

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

**重要提醒：**
- 本项目仅供学习交流使用
- 严禁用于任何商业用途
- 使用者需自行承担使用本项目的一切风险和责任
- 作者不对使用本项目造成的任何后果负责

**版权声明：**
- 角色"月代雪"及相关设定版权归《魔法少女的魔女审判》原作者所有
- 本项目为粉丝自制的二次创作，与游戏官方无关
- 请尊重原作版权，不得用于商业用途
- 如有侵权，请联系删除

## 🙏 致谢

### 技术框架
- [NoneBot2](https://github.com/nonebot/nonebot2) - 优秀的 Python 异步机器人框架
- [FAISS](https://github.com/facebookresearch/faiss) - 高效的向量检索库
- [OneBot](https://github.com/botuniverse/onebot) - 统一的聊天机器人应用接口标准

### 角色来源
- **游戏**：《魔法少女的魔女审判》
- **角色**：月代雪
- 本项目为粉丝自制，与游戏官方无关
- 角色设定版权归原作者所有

## 联系我们

- QQ：3413299642

---

<div align="center">

### ⚠️ 再次提醒

**本项目完全免费开源，任何收费行为均为诈骗！**

**如遇到以下情况请立即举报：**
- 有人声称本项目需要付费才能使用
- 有人以本项目名义提供付费服务或技术支持
- 有人利用本项目进行任何形式的商业活动

---

**1**
</div>