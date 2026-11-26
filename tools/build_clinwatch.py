"""将 clinWatch 打包为轻量托盘 launcher（onedir，无控制台窗口，进程名 clinWatch.exe）。

与"单文件自包含"方案的区别：
- 本 launcher 仅含托盘 UI（pystray + PIL），**不含 Flask**；
- Flask 服务在运行时由项目根 .venv 的 pythonw 启动 app.py（外部子进程）；
- 因此 exe 体积远小于 23MB 的 onefile 版本，且启动无需解压全部依赖。

用法（项目根目录下）：
    uv run python tools/build_clinwatch.py
产物：dist/clinWatch/（含 clinWatch.exe + _internal/）
分发：把整个 dist/clinWatch/ 放到项目内任意位置（如项目根下的 launcher 目录），
      clinWatch.exe 会自动向上查找含 app.py 与 .venv 的项目根。
依赖：pyinstaller（已加为 dev 依赖）
"""
import os
import sys

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ico = os.path.join(ROOT, "data", "clinwatch.ico")

args = [
    os.path.join(ROOT, "tray.py"),
    "--name", "clinWatch",
    "--windowed",          # 无控制台窗口
    "--onedir",            # 目录模式：启动零解压、最快；配合外部 .venv 提供 Flask
    "--icon", ico,
    # pystray 的 win32 后端是条件 import，PyInstaller 静态分析抓不到，需显式声明
    "--hidden-import", "pystray._win32",
    "--hidden-import", "pystray._util.win32",
    "--hidden-import", "pystray._util",
    "--hidden-import", "PIL._imagingtk",
    "--hidden-import", "PIL._tkinter_finder",
    # 明确排除 Web 框架（launcher 不含 Flask，避免被任何间接引用误打包）
    "--exclude-module", "flask",
    "--exclude-module", "werkzeug",
    "--exclude-module", "jinja2",
    "--exclude-module", "itsdangerous",
    "--exclude-module", "click",
    "--exclude-module", "markupsafe",
    "--noconfirm",
    "--clean",
]

if __name__ == "__main__":
    sys.exit(PyInstaller.__main__.run(args))
