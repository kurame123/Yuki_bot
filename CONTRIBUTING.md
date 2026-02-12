# 贡献指南

感谢你对 Yuki Bot 项目的关注！我们欢迎所有形式的贡献。

## 🤝 如何贡献

### 报告 Bug

如果你发现了 Bug，请通过 QQ：3413299642提交，并包含以下信息：

- **Bug 描述**：清晰简洁地描述问题
- **复现步骤**：详细的复现步骤
- **预期行为**：你期望发生什么
- **实际行为**：实际发生了什么
- **环境信息**：
  - 操作系统和版本
  - Python 版本
  - 相关依赖版本
- **日志信息**：相关的错误日志（请移除敏感信息）
- **截图**：如果适用，添加截图帮助说明问题

### 提出新功能

如果你有新功能的想法，请先通过 讨论：

- 描述你想要的功能
- 说明为什么需要这个功能
- 提供可能的实现思路

### 提交代码

1. **Fork 项目**
   ```bash
   # 点击 GitHub 页面右上角的 Fork 按钮
   ```

2. **克隆你的 Fork**
   ```bash
   git clone https://github.com/your-username/yuki-bot.git
   cd yuki-bot
   ```

3. **创建功能分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

4. **进行修改**
   - 遵循项目的代码风格
   - 添加必要的注释
   - 更新相关文档

5. **测试你的修改**
   ```bash
   # 确保代码能正常运行
   python bot.py
   ```

6. **提交修改**
   ```bash
   git add .
   git commit -m "feat: 添加新功能描述"
   # 或
   git commit -m "fix: 修复某个问题"
   ```

7. **推送到你的 Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **创建 Pull Request**
   - 访问你的 Fork 页面
   - 点击 "New Pull Request"
   - 填写 PR 描述，说明你的修改

## 📝 代码规范

### Python 代码风格

- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 代码风格
- 使用 4 个空格缩进（不使用 Tab）
- 每行代码不超过 120 个字符
- 使用有意义的变量名和函数名

### 注释规范

```python
def example_function(param1: str, param2: int) -> bool:
    """
    函数功能的简短描述
    
    Args:
        param1: 参数1的描述
        param2: 参数2的描述
        
    Returns:
        返回值的描述
        
    Raises:
        可能抛出的异常
    """
    pass
```

### Commit 信息规范

使用语义化的 commit 信息：

- `feat: 添加新功能`
- `fix: 修复 Bug`
- `docs: 更新文档`
- `style: 代码格式调整（不影响功能）`
- `refactor: 代码重构`
- `perf: 性能优化`
- `test: 添加测试`
- `chore: 构建过程或辅助工具的变动`

示例：
```
feat: 添加好感度查询命令

- 实现 /affection 命令
- 显示当前好感度等级和分数
- 添加好感度历史记录
```

## 🔍 Pull Request 检查清单

提交 PR 前，请确保：

- [ ] 代码遵循项目的代码风格
- [ ] 添加了必要的注释和文档
- [ ] 更新了 README.md（如果需要）
- [ ] 测试了所有修改的功能
- [ ] 没有引入新的警告或错误
- [ ] Commit 信息清晰明确
- [ ] 没有包含敏感信息（API 密钥、个人信息等）

## 🚫 不接受的贡献

以下类型的贡献将不会被接受：

- 违反法律法规的功能
- 侵犯他人版权的内容
- 恶意代码或后门
- 商业化相关的功能
- 未经讨论的大规模重构

## 📧 联系方式

如有任何问题，可以通过以下方式联系：

- 提交 [Issue](https://github.com/your-username/yuki-bot/issues)
- 在 [Discussions](https://github.com/your-username/yuki-bot/discussions) 中讨论
- 发送邮件至：your-email@example.com

## 📄 许可证

通过贡献代码，你同意你的贡献将在 MIT 许可证下发布。

---

再次感谢你的贡献！❤️
