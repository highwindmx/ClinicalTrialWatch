"""
clinWatch 系统托盘启动器
--------------------------------
用 pystray 在 Windows 托盘区托管 Flask 服务，避免启动一个常驻 cmd 窗口。
- 子进程用项目自带的 uv venv (Python 3.14) 运行 app.py
- 托盘右键菜单: 打开看板 / 重启服务 / 退出
- 日志重定向到 data/clinwatch.log
- pythonw 下 stderr/stdout 为 None，任何 print 都会静默崩溃，故早期即重定向到日志

启动方式(供 startWatch.bat 调用):
    pythonw tray.py        # 无控制台窗口
如需排错，用 run_tray_debug.bat（带控制台，可直接看 traceback）。
"""

import os
import sys
import traceback
from datetime import datetime

# ==================== 路径配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "data", "clinwatch.log")
PROJECT_VENV_PY = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
APP_SCRIPT = os.path.join(BASE_DIR, "app.py")
URL = "http://localhost:5000"

# ==================== 早期日志 / 重定向 ====================
def log(msg: str):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass

# pythonw 下 sys.stdout/stderr 为 None，必须在 import 任何可能 print 的库之前重定向
try:
    _logf = open(LOG_FILE, "a", encoding="utf-8")
    sys.stdout = _logf
    sys.stderr = _logf
except Exception:
    pass

def show_error(title: str, text: str):
    """原生错误弹窗（pythonw 下也可用）。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(text), str(title), 0x10)  # MB_ICONERROR
    except Exception:
        log("show_error 失败: " + str(text))

log("=== tray.py 启动 (pythonw 模式) ===")

# ==================== 依赖导入（带诊断） ====================
try:
    import subprocess
    import threading
    import webbrowser
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    log("依赖导入成功 (pystray / PIL)")
except Exception as e:
    tb = traceback.format_exc()
    log("依赖导入失败:\n" + tb)
    show_error("clinWatch 启动失败",
               "无法加载依赖 (pystray/PIL)。\n错误: %s\n\n详见 data/clinwatch.log" % str(e))
    sys.exit(1)

# ==================== 生成托盘图标 ====================
def _load_cjk_font(size: int):
    """加载支持中文的字体；Windows 优先微软雅黑，退化到默认字体（不崩）。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc", # 微软雅黑 Bold
        "C:/Windows/Fonts/simhei.ttf", # 黑体
        "C:/Windows/Fonts/simsun.ttc", # 宋体
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def make_icon() -> Image.Image:
    """程序生成图标：蓝底白字「临研看板」2x2 布局，无需外部素材。"""
    size = 64
    bg = (37, 99, 235, 255)  # 蓝 #2563EB
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角蓝底瓦片（四周留 2px 透明边，更精致）
    margin = 2
    d.rounded_rectangle([margin, margin, size - 1 - margin, size - 1 - margin],
                        radius=12, fill=bg)
    # 2x2 文字：临(左上) 研(右上) 看(左下) 板(右下)
    # 字号缩小 + 网格内移，四字离瓦片边缘留出充足 margin
    font = _load_cjk_font(20)
    cx, cy = size // 2, size // 2          # 32, 32 画布中心
    off = 12                                # 2x2 各自相对中心的偏移
    chars = ["临", "研", "看", "板"]
    positions = [(cx - off, cy - off), (cx + off, cy - off),
                 (cx - off, cy + off), (cx + off, cy + off)]
    for ch, (x, y) in zip(chars, positions):
        d.text((x, y), ch, fill=(255, 255, 255, 255), font=font, anchor="mm")
    return img

# 图标缓存：只在不存在时生成一次，之后托盘稳定引用，避免每次启动重画
ICON_CACHE = os.path.join(BASE_DIR, "data", "clinwatch.ico")

def get_icon() -> Image.Image:
    try:
        if not os.path.exists(ICON_CACHE):
            os.makedirs(os.path.dirname(ICON_CACHE), exist_ok=True)
            make_icon().save(ICON_CACHE)
            log("生成图标缓存: %s" % ICON_CACHE)
        return Image.open(ICON_CACHE)
    except Exception as e:
        log("图标缓存失败，回退实时生成: %s" % e)
        return make_icon()

# ==================== 子进程管理 ====================
proc = None
proc_lock = threading.Lock()

def start_flask():
    global proc
    with proc_lock:
        if proc is not None and proc.poll() is None:
            return
        # 优先用启动本托盘的解释器（即 .venv 的 pythonw），保证与托盘同环境；
        # 退化到 PROJECT_VENV_PY，再退化到 sys.executable
        if os.path.exists(PROJECT_VENV_PY):
            py = PROJECT_VENV_PY
        else:
            py = sys.executable
        log("启动 Flask 子进程: %s %s" % (py, APP_SCRIPT))
        proc = subprocess.Popen(
            [py, APP_SCRIPT],
            cwd=BASE_DIR,
            stdout=open(LOG_FILE, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

def stop_flask():
    global proc
    with proc_lock:
        if proc is not None and proc.poll() is None:
            log("停止 Flask 子进程 (pid=%s)" % proc.pid)
            try:
                if sys.platform == "win32":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate()
            except Exception as e:
                log("停止异常: %s" % e)
        proc = None

def restart_flask():
    stop_flask()
    start_flask()
    log("Flask 已重启")

# ==================== 开机自启 ====================
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
SHORTCUT_PATH = os.path.join(STARTUP_DIR, "clinWatch.lnk")

def autostart_enabled() -> bool:
    return os.path.exists(SHORTCUT_PATH)

def set_autostart(enable: bool):
    try:
        if enable:
            if not os.path.isdir(STARTUP_DIR):
                os.makedirs(STARTUP_DIR, exist_ok=True)
            # 确保图标缓存文件存在（开机自启 .lnk 要引用它）
            ico = get_icon() and ICON_CACHE
            # 用系统自带 PowerShell 创建 .lnk（不依赖任何第三方包）
            # 目标指向 startWatch.vbs（无窗口启动器，vbs 内部用 ScriptFullName 定位 base）
            # IconLocation 指向我们的蓝底白字图标，使快捷方式显示项目 icon 而非默认图标
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                "$sc = $ws.CreateShortcut('%s'); "
                "$sc.TargetPath = '%s'; "
                "$sc.WorkingDirectory = '%s'; "
                "$sc.WindowStyle = 7; "
                "$sc.IconLocation = '%s,0'; "
                "$sc.Description = 'clinWatch 临床研究数据看板'; "
                "$sc.Save()"
            ) % (SHORTCUT_PATH,
                  os.path.join(BASE_DIR, "startWatch.vbs"),
                  BASE_DIR,
                  ICON_CACHE)
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            log("已开启开机自启: %s" % SHORTCUT_PATH)
        else:
            if os.path.exists(SHORTCUT_PATH):
                os.remove(SHORTCUT_PATH)
            log("已关闭开机自启")
    except Exception as e:
        log("设置开机自启失败: %s" % e)
        show_error("clinWatch", "设置开机自启失败:\n%s" % e)

def toggle_autostart(icon, item):
    set_autostart(not autostart_enabled())

# ==================== 启动后自动打开浏览器 ====================
def _wait_and_open_browser():
    """后台线程：轮询端口，就绪后打开看板。"""
    import socket
    import time
    for _ in range(60):  # 最多等 30 秒
        try:
            with socket.create_connection(("127.0.0.1", 5000), timeout=1):
                time.sleep(0.5)
                webbrowser.open(URL)
                log("已自动打开看板: %s" % URL)
                return
        except OSError:
            time.sleep(0.5)
    log("等待看板端口超时，未自动打开浏览器")

def auto_open_browser():
    t = threading.Thread(target=_wait_and_open_browser, daemon=True)
    t.start()

# ==================== 托盘菜单动作 ====================
def open_dashboard(icon, item):
    webbrowser.open(URL)

def restart_action(icon, item):
    restart_flask()

def quit_action(icon, item):
    log("托盘退出，清理 Flask 子进程")
    stop_flask()
    icon.stop()

# ==================== 主入口 ====================
def main():
    start_flask()
    auto_open_browser()  # 端口就绪后自动开浏览器
    icon = pystray.Icon(
        "clinWatch",
        icon=get_icon(),
        title="clinWatch 临床研究数据看板",
        menu=pystray.Menu(
            pystray.MenuItem("打开看板", open_dashboard, default=True),
            pystray.MenuItem("重启服务", restart_action),
            pystray.MenuItem("开机自启", toggle_autostart, checked=lambda item: autostart_enabled()),
            pystray.MenuItem("退出", quit_action),
        ),
    )
    log("托盘图标创建完成，进入消息循环")
    icon.run()
    log("托盘消息循环结束")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        log("主流程异常:\n" + tb)
        show_error("clinWatch 运行出错", "运行异常:\n%s\n\n详见 data/clinwatch.log" % str(e))
        sys.exit(1)
