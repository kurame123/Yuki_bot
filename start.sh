#!/bin/bash

# ============================================================
# Yuki Bot 启动脚本 (Linux/macOS)
# ============================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 清屏
clear

# 显示标题和声明
echo -e "${CYAN}"
echo "============================================================"
echo "                Yuki Bot - 月代雪互动机器人"
echo "============================================================"
echo -e "${NC}"
echo ""
echo -e "${RED}                     ⚠️  重要声明  ⚠️${NC}"
echo ""
echo "------------------------------------------------------------"
echo " 本项目完全免费开源，仅供学习交流使用"
echo "------------------------------------------------------------"
echo ""
echo -e "${RED} ❌ 严禁用于任何商业用途${NC}"
echo -e "${RED} ❌ 严禁二次开发后商业化${NC}"
echo -e "${RED} ❌ 严禁用于违法违规活动${NC}"
echo ""
echo -e "${YELLOW} ⚠️  警惕诈骗：${NC}"
echo "    - 任何声称本项目需要付费的行为均为诈骗"
echo "    - 任何以本项目名义提供付费服务的行为均为诈骗"
echo "    - 如遇诈骗请立即举报"
echo ""
echo -e "${BLUE} 📄 版权声明：${NC}"
echo "    - 角色\"月代雪\"版权归《魔法少女的魔女审判》原作者所有"
echo "    - 本项目为粉丝自制，与游戏官方无关"
echo ""
echo -e "${YELLOW} ⚖️  免责声明：${NC}"
echo "    - 使用本项目产生的一切后果由使用者自行承担"
echo "    - 作者不对任何直接或间接损失负责"
echo "    - 请遵守相关法律法规和平台服务条款"
echo ""
echo "------------------------------------------------------------"
echo ""
read -p "  输入 yes 表示你已阅读并同意以上声明: " agree

if [ "$agree" != "yes" ]; then
    echo ""
    echo -e "${RED} ❌ 你未同意声明，程序将退出${NC}"
    echo ""
    exit 1
fi

clear
echo ""
echo -e "${CYAN}"
echo "============================================================"
echo "                   正在启动 Yuki Bot..."
echo "============================================================"
echo -e "${NC}"
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误：未检测到 Python3${NC}"
    echo ""
    echo "请先安装 Python 3.9 或更高版本"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Python 环境检测通过${NC}"
echo ""

# 检查 .env 文件是否存在
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  警告：未找到 .env 配置文件${NC}"
    echo ""
    if [ -f ".env.example" ]; then
        echo "正在从 .env.example 创建 .env 文件..."
        cp .env.example .env
        echo -e "${GREEN}✅ 已创建 .env 文件${NC}"
        echo ""
        echo -e "${YELLOW}⚠️  请先编辑 .env 文件，填入你的配置后再启动${NC}"
        echo ""
        exit 1
    else
        echo -e "${RED}❌ 错误：未找到 .env.example 文件${NC}"
        echo ""
        exit 1
    fi
fi

echo -e "${GREEN}配置文件检测通过${NC}"
echo ""

# 检查依赖是否安装
echo "正在检查依赖..."
if ! python3 -c "import nonebot" &> /dev/null; then
    echo -e "${YELLOW} 警告：依赖未安装或不完整${NC}"
    echo ""
    read -p "是否现在安装依赖？(yes/no): " install
    if [ "$install" = "yes" ]; then
        echo ""
        echo "正在安装依赖，请稍候..."
        pip3 install -r requirements.txt
        if [ $? -ne 0 ]; then
            echo ""
            echo -e "${RED}依赖安装失败${NC}"
            echo ""
            exit 1
        fi
        echo ""
        echo -e "${GREEN}✅ 依赖安装完成${NC}"
    else
        echo ""
        echo -e "${RED}依赖未安装，无法启动${NC}"
        echo ""
        echo "请手动运行：pip3 install -r requirements.txt"
        echo ""
        exit 1
    fi
fi

echo -e "${GREEN}依赖检测通过${NC}"
echo ""
echo "------------------------------------------------------------"
echo ""
echo -e "${GREEN}启动中...${NC}"
echo ""
echo "提示："
echo "  - 按 Ctrl+C 可以停止机器人"
echo "  - 日志文件保存在 logs/ 目录"
echo "  - Web 管理后台：http://localhost:8080/admin"
echo ""
echo "------------------------------------------------------------"
echo ""

# 启动机器人
python3 bot.py

# 如果程序异常退出
if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}"
    echo "============================================================"
    echo "                   ❌ 程序异常退出"
    echo "============================================================"
    echo -e "${NC}"
    echo ""
    echo "可能的原因："
    echo "  1. 配置文件错误（检查 .env 和 configs/ 目录）"
    echo "  2. 端口被占用（修改 .env 中的 PORT）"
    echo "  3. API 密钥无效（检查 configs/ai_model_config.toml）"
    echo "  4. 依赖版本冲突（尝试重新安装依赖）"
    echo ""
    echo "详细错误信息请查看上方日志或 logs/ 目录"
    echo ""
fi
