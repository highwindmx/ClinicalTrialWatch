"""
clinWatch 系统托盘启动器（轻量 launcher）
----------------------------------------
用 pystray 在 Windows 托盘区托管 Flask 服务，避免启动一个常驻 cmd 窗口。
- 本进程（托盘壳）由 PyInstaller 打包为 clinWatch.exe（windowed，无控制台窗口）；
  它自身仅含托盘 UI，不含 Flask，体积远小于"单文件自包含"方案。
- Flask 服务由**项目自带 .venv 的 pythonw.exe** 运行 app.py（外部子进程），
  整条进程链均为无控制台子系统，不冒命令行窗口。
- 任务管理器中：托盘进程 = clinWatch.exe；Flask 子进程 = pythonw.exe
  （若把 .venv/Scripts/pythonw.exe 复制为 clinWatch_srv.exe，则子进程也显示 clinWatch_srv.exe）。
- 托盘右键菜单: 打开看板 / 重启服务 / 退出 / 开机自启
- 日志重定向到 data/clinwatch.log
- pythonw 下 stderr/stdout 为 None，任何 print 都会静默崩溃，故早期即重定向到日志

启动方式:
    开发态:  pythonw tray.py            # 由 startWatch.vbs 无窗口调用
    部署态:  双击 clinWatch.exe          # PyInstaller 打包的托盘壳，自动定位项目根并拉起 .venv 的 Flask
"""

import ctypes
import io
import os
import struct
import sys
import traceback
import winreg
from datetime import datetime

# ==================== 路径配置 ====================
def _find_project_root(start_dir):
    """从 start_dir 向上查找含 app.py 且含 .venv 的目录，作为项目根。

    打包为 onedir 后 exe 位于 dist/clinWatch/clinWatch.exe，需向上定位到真正的
    项目根（与 .venv / app.py / frontend / data 同级），才能用外部 .venv 的 pythonw
    启动 Flask、并读写持久化数据库。
    """
    cur = os.path.abspath(start_dir)
    while True:
        if os.path.isfile(os.path.join(cur, "app.py")) and os.path.isdir(os.path.join(cur, ".venv")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent

if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", EXE_DIR)
    # 托盘壳不含 Flask，运行时依赖项目根下的 .venv 提供 Web 服务；
    # 向上查找项目根，找不到则回退到 exe 所在目录（仍可由 CLINWATCH_PYTHON 指定解释器）
    BASE_DIR = _find_project_root(EXE_DIR) or EXE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR
    RES_DIR = BASE_DIR

LOG_FILE = os.path.join(EXE_DIR, "data", "clinwatch.log")
APP_LOG_FILE = os.path.join(EXE_DIR, "data", "app.log")
# Flask 子进程始终用项目自带 .venv 的 pythonw 运行 app.py（托盘壳自身不含 Flask 依赖）
PROJECT_VENV_PY = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
APP_SCRIPT = os.path.join(BASE_DIR, "app.py")
# 被 baseMan 托管时端口由环境变量下发；独立双击仍是 5003
PORT = int(os.environ.get("BASEMAN_PORT") or 5003)
URL = "http://localhost:%d" % PORT

# ==================== 早期日志 / 重定向 ====================
_LOG_FD = None  # 常驻追加句柄：os.write + O_APPEND 保证每条日志一次原子写，不会与子进程互相覆盖

def _log_tag() -> str:
    """日志前缀带上 pid 与线程名，便于区分多实例、定位卡在哪条线程。"""
    try:
        import threading
        return "pid=%s %s" % (os.getpid(), threading.current_thread().name)
    except Exception:
        return "pid=%s" % os.getpid()

def log(msg: str):
    global _LOG_FD
    line = "[%s] (%s) %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               _log_tag(), msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if _LOG_FD is None:
            _LOG_FD = os.open(LOG_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        os.write(_LOG_FD, line.encode("utf-8"))
    except Exception as e:
        # 绝不静默：主日志写不进去时复用启动时已打开的句柄，再退到备用文件，
        # 避免"日志没有这行"被误判成"代码没执行到"（本机会出现间歇性 Errno 13）
        _LOG_FD = None
        try:
            _logf.write("%s# 追加句柄写入失败: %r\n" % (line, e))
            _logf.flush()
            return
        except Exception:
            pass
        try:
            with open(LOG_FILE + ".err", "a", encoding="utf-8") as f:
                f.write("%s# 日志写入失败: %r\n" % (line, e))
        except Exception:
            pass

# pythonw 下 sys.stdout/stderr 为 None，必须在 import 任何可能 print 的库之前重定向
# buffering=1 = 行缓冲：解释器异常栈、Flask 输出都能及时落盘，不会因进程被杀而丢行
try:
    _logf = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
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

# ==================== 单实例保护 ====================
_MUTEX_HANDLE = None

def acquire_single_instance() -> bool:
    """用 Windows 命名互斥体保证托盘单实例。

    重复启动（双击 exe / 双击 vbs / 开机自启与手动启动撞车）时，
    第二个实例弹窗提示后直接退出，避免出现多个托盘 + 多个 Flask 子进程。
    互斥体按会话（Local\\）隔离：不同 Windows 账户会话互不影响。
    """
    global _MUTEX_HANDLE
    if sys.platform != "win32":
        return True
    try:
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\clinWatch_tray")
        if _MUTEX_HANDLE and ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            log("检测到已有 clinWatch 托盘实例在运行，本实例退出")
            show_error("clinWatch",
                       "clinWatch 托盘已在运行中（请查看系统托盘区图标），\n无需重复启动。")
            return False
        log("单实例互斥体获取成功")
        return True
    except Exception as e:
        # 检查本身失败不应阻止启动，仅记录
        log("单实例检查异常（忽略继续）: %s" % e)
        return True

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

# ==================== UIPI 兼容处理 ====================
def _is_elevated() -> bool:
    """当前进程是否运行在提权（管理员）上下文。"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def patch_pystray_uipi():
    """非提权进程跳过 pystray 的 UIPI 消息过滤器调用。

    pystray 创建托盘窗口时会无条件调用 ChangeWindowMessageFilterEx，其唯一用途是
    让"已提权"的进程也能收到 Explorer 广播的 WM_TASKBARCREATED（见 pystray 源码注释）。
    部分 Windows 11 环境（如 26H2 启用管理员保护后）会拒绝非提权进程调用该 API，返回
    ERROR_ACCESS_DENIED，pystray 的工作线程因此抛出 PermissionError [WinError 5]，托盘图标
    创建失败（且因异常发生在子线程而不会触发主流程的错误弹窗）。
    非提权进程与 Explorer 处于同一完整性级别，本就不需要这层 UIPI 豁免；这里只对非提权
    上下文跳过该调用，提权上下文保持原样，真实失败仍会抛出、不被掩盖。
    """
    if sys.platform != "win32":
        return
    if _is_elevated():
        log("提权上下文：保留 pystray 的 UIPI 消息过滤器调用")
        return
    try:
        from pystray._util import win32 as _pystray_win32
        _pystray_win32.ChangeWindowMessageFilterEx = lambda *args, **kwargs: True
        log("非提权上下文：跳过 pystray 的 UIPI 消息过滤器调用（该调用仅提权进程需要）")
    except Exception as e:
        log("UIPI 兼容处理失败，按 pystray 原逻辑运行: %s" % e)

# ==================== 子线程异常可见性 ====================
def _thread_exception_hook(args):
    """把未捕获的子线程异常写进日志。

    pystray 的 setup 线程与消息循环都在子线程里跑，pythonw 下这类异常既不打印、
    也不会触发主流程的错误弹窗，历史上直接表现为“托盘就是起不来”却毫无线索。
    """
    log("子线程未捕获异常 (%s):\n%s" % (
        args.thread.name if args.thread else "<unknown thread>",
        "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))))

# ==================== pystray 图标来源兼容处理 ====================
def patch_pystray_icon_source(icon_path):
    """让 pystray 直接从本地 .ico 加载 HICON，不再写临时目录。

    pystray 的图片图标会先经 tempfile.mkstemp 序列化成临时 .ico，再调用 LoadImage。
    本机 D:\\Share 下的 python 被安全策略以低完整性级别（Low IL）运行，写不了
    C:\\Users\\...\\AppData\\Local\\Temp，setup 线程因此抛 PermissionError [WinError 13]，
    图标永远不会注册（且异常静默）。这里改用已有的 data\\clinwatch.ico 作为
    LoadImage 来源，去掉对临时目录的依赖；LoadImage 失败会显式抛错，不被掩盖。
    """
    try:
        from pystray._util import win32 as _w
        from pystray._win32 import Icon as _WinIcon

        def _assert_icon_handle(self):
            if self._icon_handle:
                return
            self._icon_handle = _w.LoadImage(
                None, icon_path, _w.IMAGE_ICON, 0, 0,
                _w.LR_DEFAULTSIZE | _w.LR_LOADFROMFILE)
            if not self._icon_handle:
                raise ctypes.WinError()

        _WinIcon._assert_icon_handle = _assert_icon_handle
        log("pystray 图标改为直接从本地加载: %s" % icon_path)
    except Exception as e:
        log("pystray 图标来源兼容处理失败，按原逻辑（临时文件）运行: %s" % e)

# ==================== 完整性级别自检 ====================
# 低完整性（Low, S-1-16-4096）进程调用 Shell_NotifyIcon 时，通知会因 UIPI 被
# Medium 级别的 explorer 丢弃：NIM_ADD 仍返回 TRUE、pystray 的 visible 也是 True，
# 但通知区域里根本没有图标。必须把这条写进日志，否则又变成"静默失败"。
def check_integrity_level() -> str:
    if sys.platform != "win32":
        return "非 Windows，跳过"
    try:
        adv = ctypes.windll.advapi32
        k32 = ctypes.windll.kernel32
        # 显式声明签名/返回类型，避免 64 位下指针被当成 int 截断（曾导致 0xC0000005）
        adv.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                         ctypes.POINTER(ctypes.c_void_p)]
        adv.OpenProcessToken.restype = ctypes.c_int
        adv.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                            ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.POINTER(ctypes.c_ulong)]
        adv.GetTokenInformation.restype = ctypes.c_int
        adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        adv.GetSidSubAuthority.restype = ctypes.POINTER(ctypes.c_ulong)
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        k32.GetCurrentProcess.restype = ctypes.c_void_p

        hproc = k32.GetCurrentProcess()
        htok = ctypes.c_void_p()
        if not adv.OpenProcessToken(hproc, 0x0008, ctypes.byref(htok)):  # TOKEN_QUERY
            return "读取 token 失败: %s" % ctypes.WinError()
        buf = ctypes.create_string_buffer(64)
        need = ctypes.c_ulong(0)
        # TokenIntegrityLevel = 25
        ok = adv.GetTokenInformation(htok, 25, buf, 64, ctypes.byref(need))
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        k32.CloseHandle(htok)
        if not ok:
            return "GetTokenInformation 失败: %s" % ctypes.WinError()
        # SID 的最后一级子权威即完整性 RID：4096=Low 8192=Medium 12288=High
        sub_count = adv.GetSidSubAuthorityCount(sid)[0]
        rid = adv.GetSidSubAuthority(sid, sub_count - 1)[0] if sub_count else 0
        names = {4096: "Low", 8192: "Medium", 12288: "High", 16384: "System"}
        name = names.get(rid, str(rid))
        if rid < 8192:
            return ("%s(RID=%d) —— 低于 Medium，托盘图标通知会被 explorer 的 UIPI 丢弃，"
                    "图标不会出现；请从\n  非受限制目录（如 C:\\ 下）启动，或解除该目录的降权策略"
                    % (name, rid))
        return "%s(RID=%d)" % (name, rid)
    except Exception as e:
        return "自检异常: %s" % e

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

ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

def make_icon(size: int = 64) -> Image.Image:
    """程序生成图标：蓝底白字「临研看板」2x2 布局，几何量按 size 等比缩放。"""
    s = size
    bg = (37, 99, 235, 255)  # 蓝 #2563EB
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角蓝底瓦片（四周留白约 3%）
    margin = max(1, round(s * 0.031))
    radius = max(1, round(s * 0.19))
    d.rounded_rectangle([margin, margin, s - 1 - margin, s - 1 - margin],
                        radius=radius, fill=bg)
    # 2x2 文字：临(左上) 研(右上) 看(左下) 板(右下)
    font = _load_cjk_font(max(5, round(s * 0.31)))
    off = s * 0.19
    chars = ["临", "研", "看", "板"]
    positions = [(s / 2 - off, s / 2 - off), (s / 2 + off, s / 2 - off),
                 (s / 2 - off, s / 2 + off), (s / 2 + off, s / 2 + off)]
    for ch, (x, y) in zip(chars, positions):
        d.text((x, y), ch, fill=(255, 255, 255, 255), font=font, anchor="mm")
    return img

def _ico_dib(img) -> bytes:
    """32 位 BMP 条目（BITMAPINFOHEADER biHeight=2h + BGRA 自下而上 + AND 掩码）。

    <=128 的档位必须用 DIB：PNG 条目只有 256x256 才被资源管理器稳定支持，
    小尺寸用 PNG 会让快捷方式/资源管理器退回默认图标。
    """
    w, h = img.size
    px = img.convert("RGBA").load()
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
    xor = b"".join(bytes((px[x, y][2], px[x, y][1], px[x, y][0], px[x, y][3]))
                   for y in range(h - 1, -1, -1) for x in range(w))
    and_mask = b"\x00" * (((w + 31) // 32) * 4) * h
    return header + xor + and_mask

def write_ico(path: str, sizes=ICON_SIZES) -> int:
    """每档独立渲染并写出规范 ico（<=128 用 DIB，256 用 PNG），返回文件字节数。"""
    entries, blobs = [], []
    offset = 6 + 16 * len(sizes)
    for s in sizes:
        img = make_icon(s)
        if s >= 256:
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()
        else:
            data = _ico_dib(img)
        dim = 0 if s >= 256 else s
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries) + b"".join(blobs))
    return offset

# 图标缓存：只在不存在时生成一次，之后托盘稳定引用，避免每次启动重画
ICON_CACHE = os.path.join(BASE_DIR, "data", "clinwatch.ico")

def get_icon() -> Image.Image:
    try:
        if not os.path.exists(ICON_CACHE):
            os.makedirs(os.path.dirname(ICON_CACHE), exist_ok=True)
            write_ico(ICON_CACHE)
            log("生成图标缓存（%d 档）: %s" % (len(ICON_SIZES), ICON_CACHE))
        return Image.open(ICON_CACHE)
    except Exception as e:
        log("图标缓存失败，回退实时生成: %s" % e)
        return make_icon()

# ==================== 子进程管理 ====================
proc = None
proc_lock = threading.Lock()

def _find_pythonw():
    """定位启动 Flask 的外部解释器（无窗口 pythonw），优先级：
       1. .venv/Scripts/clinWatch_srv.exe（用户可选：把 pythonw.exe 复制改名，使子进程名可控）
       2. .venv/Scripts/pythonw.exe（项目自带 venv）
       3. 环境变量 CLINWATCH_PYTHON 指定的解释器
       4. 系统 PATH 中的 pythonw
    """
    srv = os.path.join(BASE_DIR, ".venv", "Scripts", "clinWatch_srv.exe")
    if os.path.exists(srv):
        return srv
    if os.path.exists(PROJECT_VENV_PY):
        return PROJECT_VENV_PY
    envp = os.environ.get("CLINWATCH_PYTHON")
    if envp and os.path.exists(envp):
        return envp
    return "pythonw"

def _server_argv():
    """启动 Flask 服务的命令行：始终用外部 pythonw 运行 app.py（托盘壳不含 Flask）。"""
    return [_find_pythonw(), APP_SCRIPT]

def start_flask():
    global proc
    with proc_lock:
        if proc is not None and proc.poll() is None:
            return
        args = _server_argv()
        log("启动 Flask 子进程: " + " ".join(args))
        # Flask 自己的 stdout 单独写 data\app.log：两个进程同时追加同一个文件时，
        # 子进程的块缓冲写入会覆盖父进程刚写的行（表现为"日志缺行/行首被吃掉"）。
        logf = open(APP_LOG_FILE, "a", encoding="utf-8", buffering=1)
        try:
            proc = subprocess.Popen(
                args,
                cwd=BASE_DIR,
                stdout=logf,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        finally:
            logf.close()

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
SHORTCUT_PATH = os.path.join(STARTUP_DIR, "临研看板.lnk")

def _clean_stray_vbs():
    """清理早期手动遗留的 startWatch.vbs 直接启动项（非 .lnk）：
       - 当前用户 / 所有用户 启动文件夹里的直接 vbs 文件
       - 注册表 Run 键中值数据含 startWatch.vbs 的条目（仅当前用户，免管理员权限）"""
    targets = [STARTUP_DIR]
    common = os.path.join(os.environ.get("PROGRAMDATA", ""),
                          "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    if common:
        targets.append(common)
    for d in targets:
        stray = os.path.join(d, "startWatch.vbs")
        if os.path.isfile(stray):
            try:
                os.remove(stray)
                log("清理启动文件夹直接 vbs: %s" % stray)
            except Exception as e:
                log("清理启动文件夹 vbs 失败: %s" % e)
    # 注册表当前用户 Run 键（HKLM 需管理员，跳过）
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ | winreg.KEY_WRITE)
        to_del = []
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                i += 1
            except OSError:
                break
            if "startWatch.vbs" in value:
                to_del.append(name)
        for n in to_del:
            try:
                winreg.DeleteValue(key, n)
                log("清理注册表启动项: %s" % n)
            except Exception as e:
                log("清理注册表启动项失败: %s" % e)
        winreg.CloseKey(key)
    except Exception as e:
        log("读取注册表 Run 键失败(可忽略): %s" % e)

def autostart_enabled() -> bool:
    return os.path.exists(SHORTCUT_PATH)

def set_autostart(enable: bool):
    # 历史遗留的旧启动项文件名（早期版本指向 vbs 或 pythonw），统一清理避免重复/显示异常
    OLD_LNK_NAMES = ("clinWatch.lnk", "startWatch.lnk", "startWatch.vbs.lnk")
    try:
        if not os.path.isdir(STARTUP_DIR):
            os.makedirs(STARTUP_DIR, exist_ok=True)
        if enable:
            _clean_stray_vbs()
            # 先清掉旧版 .lnk，只保留当前“临研看板.lnk”
            for name in OLD_LNK_NAMES:
                old = os.path.join(STARTUP_DIR, name)
                if os.path.exists(old):
                    try: os.remove(old)
                    except Exception: pass
            # 确保图标缓存文件存在（开机自启 .lnk 要引用它）
            get_icon()
            # 用系统自带 PowerShell 创建 .lnk（不依赖任何第三方包）
            # 冻结态（打包 exe）目标指向 clinWatch.exe（托盘模式）；开发态指向 startWatch.vbs
            # 文件名即“临研看板.lnk”，任务管理器启动项会显示“临研看板”
            # IconLocation 指向我们的蓝底白字图标，使快捷方式显示项目 icon
            target_path = sys.executable if getattr(sys, "frozen", False) else os.path.join(BASE_DIR, "startWatch.vbs")
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                "$sc = $ws.CreateShortcut('%s'); "
                "$sc.TargetPath = '%s'; "
                "$sc.WorkingDirectory = '%s'; "
                "$sc.WindowStyle = 7; "
                "$sc.IconLocation = '%s,0'; "
                "$sc.Description = '临研看板 临床研究数据看板'; "
                "$sc.Save()"
            ) % (SHORTCUT_PATH,
                  target_path,
                  BASE_DIR,
                  ICON_CACHE)
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            log("已开启开机自启: %s" % SHORTCUT_PATH)
        else:
            _clean_stray_vbs()
            # 关闭时删当前 + 所有可能残留的旧版
            for name in (os.path.basename(SHORTCUT_PATH),) + OLD_LNK_NAMES:
                p = os.path.join(STARTUP_DIR, name)
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass
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
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
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

def _describe_tray_icon(icon):
    """用 Shell_NotifyIconGetRect 确认系统是否真的持有这个托盘图标，并给出位置。

    注意必须传完整的 NOTIFYICONIDENTIFIER（第一个字段是 cbSize），
    漏掉 cbSize 会被系统当成参数非法（E_INVALIDARG），看起来像"图标没注册"。
    """
    if sys.platform != "win32":
        return "非 Windows，跳过"
    try:
        import ctypes
        from ctypes import wintypes as wt

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                        ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

        class NOTIFYICONIDENTIFIER(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32),
                        ("hWnd", wt.HWND),
                        ("uID", ctypes.c_uint32),
                        ("guidItem", GUID)]

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = icon._hwnd
        ident.uID = id(icon)
        rect = RECT()
        hr = ctypes.windll.shell32.Shell_NotifyIconGetRect(
            ctypes.byref(ident), ctypes.byref(rect))
        if hr == 0:
            return "GetRect S_OK rect=(%d,%d,%d,%d) 图标在通知区域" % (
                rect.left, rect.top, rect.right, rect.bottom)
        return "GetRect hr=0x%08X rect=(%d,%d,%d,%d)" % (
            hr & 0xFFFFFFFF, rect.left, rect.top, rect.right, rect.bottom)
    except Exception as e:
        return "GetRect 查询失败: %s" % e

def _report_tray_state(icon):
    """后台确认托盘是否真的注册成功：pystray 的 visible 只有 Shell_NotifyIcon 成功后才为 True。"""
    import time
    for _ in range(30):
        if icon.visible:
            log("托盘图标已注册（visible=True）；%s" % _describe_tray_icon(icon))
            return
        time.sleep(0.2)
    log("托盘在 6 秒内未变为可见，请查看上面的子线程异常")

# ==================== 主入口 ====================
def main():
    threading.excepthook = _thread_exception_hook
    log("步骤0/6 单实例检查")
    if not acquire_single_instance():
        sys.exit(0)
    log("步骤1/6 完整性级别自检: %s" % check_integrity_level())
    log("步骤2/6 补丁 pystray UIPI 调用")
    patch_pystray_uipi()
    log("步骤3/6 启动 Flask 子进程")
    start_flask()
    # 默认不自动打开浏览器：需要时点托盘菜单「打开看板」手动打开。
    # 如需恢复自动打开，取消下一行注释即可。
    # auto_open_browser()
    log("步骤4/6 构造 pystray.Icon（含菜单）")
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
    log("步骤5/6 pystray.Icon 构造完成，替换图标加载方式")
    patch_pystray_icon_source(ICON_CACHE)
    threading.Thread(target=_report_tray_state, args=(icon,), daemon=True).start()
    log("步骤6/6 托盘图标创建完成，进入消息循环")
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
