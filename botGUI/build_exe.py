"""
PyInstaller 打包脚本
运行: python botGUI/build_exe.py
"""
import subprocess
import sys
from pathlib import Path


def build():
    """执行打包"""
    project_root = Path(__file__).parent.parent
    icon_path = project_root / "botGUI" / "ui" / "icons" / "yuki.ico"
    version_file = project_root / "botGUI" / "version_info.txt"
    
    # 生成版本信息文件
    sys.path.insert(0, str(project_root))
    from botGUI.version_info import create_version_file
    create_version_file()
    print("📋 已生成版本信息文件")
    
    # PyInstaller 参数
    args = [
        sys.executable, "-m", "PyInstaller",
        str(project_root / "botGUI" / "main.py"),
        "--name", "YukiBotGUI",
        "--noconsole",  # 不显示控制台
        "--onedir",     # 生成目录而非单文件
        "--clean",      # 清理临时文件
        
        # 添加数据文件（让 exe 能访问配置）
        "--add-data", f"{project_root / 'configs'};configs",
        "--add-data", f"{project_root / 'src'};src",
        
        # 隐藏导入 - GUI 相关
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtNetwork",
        # 隐藏导入 - 配置文件处理
        "--hidden-import", "tomllib",  # Python 3.11+ 内置
        "--hidden-import", "tomli",
        "--hidden-import", "tomli_w",
        # 隐藏导入 - 网络请求
        "--hidden-import", "httpx",
        "--hidden-import", "httpx._transports",
        "--hidden-import", "httpx._transports.default",
        "--hidden-import", "httpcore",
        # 隐藏导入 - 其他常用
        "--hidden-import", "json",
        "--hidden-import", "logging",
        "--hidden-import", "pathlib",
        "--hidden-import", "datetime",
        "--hidden-import", "typing",
        "--hidden-import", "dataclasses",
        "--hidden-import", "enum",
        
        # 输出目录
        "--distpath", str(project_root / "dist"),
        "--workpath", str(project_root / "build"),
        "--specpath", str(project_root),
    ]
    
    # 如果图标文件存在，添加图标参数
    if icon_path.exists():
        args.extend(["--icon", str(icon_path)])
        print(f"🎨 使用图标: {icon_path}")
    else:
        print(f"⚠️ 图标文件不存在，使用默认图标")
        print(f"   如需自定义图标，请将 .ico 文件放到: {icon_path}")
    
    # 添加版本信息
    if version_file.exists():
        args.extend(["--version-file", str(version_file)])
        print(f"📋 使用版本信息: {version_file}")
    
    print("🔨 开始打包 Yuki Bot GUI...")
    print(f"   命令: {' '.join(args)}")
    
    result = subprocess.run(args, cwd=str(project_root))
    
    if result.returncode == 0:
        print("\n✅ 打包成功！")
        print(f"   输出目录: {project_root / 'dist' / 'YukiBotGUI'}")
        print("\n📝 使用说明:")
        print("   方法1: 直接从项目根目录运行")
        print(f"         {project_root / 'dist' / 'YukiBotGUI' / 'YukiBotGUI.exe'}")
        print("   方法2: 将 dist/YukiBotGUI 文件夹内容复制到项目根目录后运行")
        print("\n   注意: GUI 会自动查找项目根目录（包含 bot.py 的目录）")
    else:
        print(f"\n❌ 打包失败，退出码: {result.returncode}")
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(build())
