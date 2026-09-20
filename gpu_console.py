#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU Console — 桌面 GPU 监控 HUD(多 GPU,3x RTX 3090)。

- 窗口固定大小 1024x768(不可缩放),自绘标题条拖动移动
- overrideredirect 去除原生标题栏/边框
- 位置记忆(position.json);默认主屏左上角
- F11 全屏(等比例缩放:所有坐标与字体按同一比例 s 放大,letterbox 居中,不拉伸)
- Esc / Q / 右键 退出
- nvidia-smi 无黑窗轮询(隐藏 stdout/stderr),附带驱动版本
- 每卡标题行标注品牌(NVIDIA/AMD/Intel 按品牌色)+ 型号 + PCIe 槽位
- 底栏:刷新率/时间/品牌/驱动版本
- 布局:每行(标题/Util/VRAM/数值/历史图)用游标逐行排版,历史图吸收剩余高度,任何比例下都不重叠
- 每卡历史图取自身索引(修复所有卡片同画 GPU0 的问题)
"""
import json
import os
import subprocess
import sys
import time

IS_WIN = sys.platform == "win32"

# ── 路径:开发环境用脚本目录;打包(frozen)时位置文件存 %APPDATA% / ~/Library/Application Support,
#    随机的 _MEIPASS 临时目录不用于持久化 ─────────────
if getattr(sys, "frozen", False):
    BASE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "GPU Console")
    os.makedirs(BASE, exist_ok=True)
    BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
    BUNDLE = BASE
POS_FILE = os.path.join(BASE, "position.json")

try:
    import tkinter as tk
    from tkinter import font as tkfont
except Exception as e:  # 无显示环境
    print("需要图形环境(tkinter):", e)
    sys.exit(1)

# ── 调色板(暗色终端风格)────────────────────────────
BG = "#0a0e14"
PANEL = "#0d1420"
PANEL2 = "#101a2a"
BORDER = "#1c2739"
TXT = "#d7e3f4"
DIM = "#6b7d94"
DIM2 = "#46586e"
CYAN = "#38cfe6"
GREEN = "#3fd07f"
AMBER = "#f2b13d"
RED = "#ef5b5b"
BAR_BG = "#141d2c"
HIST_BG = "#0c1420"

# ── 布局(1024x768 坐标系,行高为基准值,渲染时 × s)──
WIN_W, WIN_H = 1024, 768
M = 16      # 画布外边距
PAD = 14    # 卡片内边距
HDR = 34    # 顶栏(基准)
FTR = 26    # 底栏(基准)
CARD = {    # 单卡各行基准高度(历史图 = 剩余)
    "inset": 8, "title": 22, "util": 16, "vram": 22, "kv": 24, "gap": 6,
}


def col_for(v):
    if v >= 85:
        return RED
    if v >= 50:
        return AMBER
    return GREEN


def brand_of(name):
    """从显卡名解析(品牌, 品牌色)。未知返回 (None, TXT)。"""
    n = (name or "").upper()
    if "NVIDIA" in n or "QUADRO" in n or "GTX" in n or "RTX" in n:
        return "NVIDIA", "#76b900"
    if "AMD" in n or "RADEON" in n:
        return "AMD", "#ed1c24"
    if "INTEL" in n or "IRIS" in n or "ARCGPU" in n or "ARC " in n:
        return "INTEL", "#00b4eb"
    return None, TXT


def _find_nvidia_smi():
    """优先用目标机 NVIDIA 驱动的 nvidia-smi(版本与驱动匹配,最可靠);
    目标机 PATH 没有(未装驱动)时退回随包捆绑的一份。"""
    import shutil
    syspath = shutil.which("nvidia-smi")
    if syspath:
        return syspath
    for cand in ("nvidia-smi.exe", "nvidia-smi"):
        b = os.path.join(BUNDLE, cand)
        if os.path.exists(b):
            return b
    return "nvidia-smi"


def _run_tool(p, *args, timeout=5):
    """无窗口/无黑框地运行外部工具,返回 stdout(失败抛异常)。"""
    cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([p, *args], capture_output=True, text=True,
                       timeout=timeout, creationflags=cflags)
    return r.stdout


# ── nvidia-smi ─────────────────────────────────────
def driver_version():
    """驱动/版本信息(仅取一次,用于底栏;失败返回 None)。"""
    try:
        out = _run_tool(_find_nvidia_smi(),
                        "--query-gpu=driver_version",
                        "--format=csv,noheader,nounits",
                        timeout=4).strip()
        v = out.splitlines()[0].strip() if out else None
        return v if v and v.lower() != "n/a" else None
    except Exception:
        return None


def sample():
    try:
        out = _run_tool(
            _find_nvidia_smi(),
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,fan.speed,clocks.max.graphics,pci.bus_id",
            "--format=csv,noheader,nounits",
        )
        gpus = []
        for line in out.splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) < 9:
                continue
            def f(x, d=0):
                try:
                    return float(x)
                except Exception:
                    return float(d)
            gpus.append({
                "idx": int(f(p[0])),
                "name": p[1],
                "util": int(f(p[2])),
                "vram": int(f(p[3])),
                "vram_tot": int(f(p[4])),
                "temp": int(f(p[5])),
                "pwr": f(p[6]),
                "fan": int(f(p[7])),
                "clk": int(f(p[8])),
                "slot": (p[9] if len(p) > 9 and p[9] else None),
                "source": "nvidia-smi",
            })
        return gpus
    except Exception:
        return None


class App:
    POLL_MS = 1000

    def __init__(self, root):
        self.root = root
        self.root.title("GPU Console")
        self.root.overrideredirect(True)   # 自绘无边框
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x, y = self._load_pos(sw)
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
        self.root.update_idletasks()

        self.f_title = tkfont.Font(family="Consolas", size=12, weight="bold")
        self.f_hdr = tkfont.Font(family="Consolas", size=9)
        self.f_small = tkfont.Font(family="Consolas", size=8)
        self._fcache = {}

        self.c = tk.Canvas(root, width=WIN_W, height=WIN_H,
                           bg=BG, highlightthickness=0)
        self.c.pack(fill="both", expand=True)

        self.tbar = tk.Canvas(root, width=WIN_W, height=24,
                              bg=PANEL2, highlightthickness=0)
        self.tbar.place(x=0, y=0, width=WIN_W, height=24)
        self._draw_titlebar()
        self.tbar.bind("<ButtonPress-1>", self._start_drag)
        self.tbar.bind("<B1-Motion>", self._on_drag)

        self.root.bind("<Button-3>", lambda e: self.close())
        self.root.bind("<Escape>", lambda e: self.close())
        self.root.bind("q", lambda e: self.close())
        self.root.bind("Q", lambda e: self.close())
        self.root.bind("<F11>", lambda e: self.toggle_full())
        self._drag = None
        self._fullscreen = False
        self._prev_geom = None

        self.gpus = []
        self.hist = []
        self.HIST_N = 30
        self._last_data = None
        self._drv = driver_version()
        self._poll()
        self.root.after(self.POLL_MS, self._poll)

    # ── 字体(按 s 缩放,缓存)──
    def F(self, size, bold=False):
        pt = max(6, int(round(size * self._s)))
        w = "bold" if bold else "normal"
        key = (pt, w)
        if key not in self._fcache:
            self._fcache[key] = tkfont.Font(family="Consolas", size=pt, weight=w)
        return self._fcache[key]

    def _load_pos(self, sw):
        try:
            with open(POS_FILE, "r", encoding="utf-8") as f:
                p = json.load(f)
            x = int(p.get("x", 0)); y = int(p.get("y", 0))
            if 0 <= x < sw and 0 <= y < self.root.winfo_screenheight():
                return x, y
        except Exception:
            pass
        return 0, 0

    def _save_pos(self):
        try:
            x = self.root.winfo_x(); y = self.root.winfo_y()
            with open(POS_FILE, "w", encoding="utf-8") as f:
                json.dump({"x": x, "y": y}, f)
        except Exception:
            pass

    def _draw_titlebar(self):
        self.tbar.delete("all")
        w = self.tbar.winfo_width() or WIN_W
        self.tbar.create_text(10, 12, text="GPU CONSOLE", anchor="w",
                              font=self.f_title, fill=CYAN)
        self.tbar.create_text(w - 10, 12, text="F11 全屏   Esc 退出",
                              anchor="e", font=self.f_hdr, fill=DIM)

    def _start_drag(self, e):
        self._drag = (e.x, e.y)

    def _on_drag(self, e):
        if not self._drag:
            return
        dx, dy = self._drag
        nx = self.root.winfo_x() + (e.x - dx)
        ny = self.root.winfo_y() + (e.y - dy)
        self.root.geometry(f"+{nx}+{ny}")

    # ── 全屏 ──
    def toggle_full(self):
        if not self._fullscreen:
            self._prev_geom = self.root.geometry()
            self._fullscreen = True
            self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        else:
            self._fullscreen = False
            if self._prev_geom:
                self.root.geometry(self._prev_geom)
                self._save_pos()

    # ── 轮询 ──
    def _poll(self):
        if not self.root.winfo_exists():
            return
        data = sample()
        if data:
            self._last_data = data
            self.gpus = data
            self.hist.append([g.get("util", 0) for g in data])
            if len(self.hist) > self.HIST_N:
                self.hist.pop(0)
        self._draw()
        self.root.after(self.POLL_MS, self._poll)

    # ── 渲染 ──
    def _draw(self):
        c = self.c
        c.delete("all")
        w = c.winfo_width() or WIN_W
        h = c.winfo_height() or WIN_H
        # 等比缩放:所有坐标/字体按同一 s,letterbox 居中,不拉伸
        s = max(0.6, min(w / WIN_W, h / WIN_H))
        self._s = s
        cw = int(WIN_W * s)
        ch = int(WIN_H * s)
        ox = (w - cw) // 2
        oy = (h - ch) // 2

        d = self._last_data or []
        n = max(1, len(d))
        hdr = int(HDR * s)
        ftr = int(FTR * s)
        self._header(c, cw, ox, oy, hdr, s)
        # 卡片区:均分剩余高度,历史图吸收余量 → 永不溢出/重叠
        avail = ch - hdr - ftr
        per = max(60, int(avail / n))
        y = hdr
        for g in d:
            self._gpu_block(c, cw, ox, oy, y, per, g, s)
            y += per
        self._footer(c, cw, ch, ox, oy, ftr, s)

    # ── 顶栏 ──
    def _header(self, c, w, ox, oy, hdr, s):
        c.create_rectangle(ox, oy, ox + w, oy + hdr, fill=PANEL, outline="")
        c.create_line(ox, oy + hdr, ox + w, oy + hdr, fill=BORDER)
        title = "GPU CONSOLE"
        sub = ""
        if self.gpus:
            sub = f"{len(self.gpus)}x " + self.gpus[0]['name'].replace('NVIDIA ', '').replace('GeForce ', '')
        c.create_text(ox + int(M * s), oy + hdr // 2, text=title, anchor="w",
                      font=self.F(13, True), fill=CYAN)
        if sub:
            c.create_text(ox + int(M * s) + int(120 * s), oy + hdr // 2,
                          text=sub, anchor="w", font=self.F(8), fill=DIM)
        c.create_text(ox + w - int(M * s), oy + hdr // 2,
                      text="F11 全屏    Esc 退出", anchor="e",
                      font=self.F(8), fill=DIM2)

    # ── 单块 GPU 卡片(游标逐行,历史图吸收剩余)──
    def _gpu_block(self, c, w, ox, oy, y, per, g, s):
        x = ox + int(M * s)
        cw = w - int(M * s * 2)
        bx = x + int(PAD * s)
        bw = cw - int(PAD * s * 2)
        c.create_rectangle(x, y, x + cw, y + per, fill=PANEL, outline=BORDER, width=1)

        i = int(CARD["inset"] * s)
        title_h = int(CARD["title"] * s)
        util_h = int(CARD["util"] * s)
        vram_h = int(CARD["vram"] * s)
        kv_h = int(CARD["kv"] * s)
        fixed = title_h + util_h + vram_h + kv_h + 2 * i
        hist_h = max(18, per - fixed - int(4 * s))   # 历史图吸收剩余

        util = g.get("util", 0) or 0
        uc = col_for(util)
        vt = g.get("vram_tot") or 24576
        vram = g.get("vram", 0)
        vp = min(100, int(vram / vt * 100)) if vt else 0

        yy = y + i
        # 行1:GPU N + 型号 + 利用率(右)
        c.create_rectangle(bx, yy + 2, bx + int(5 * s), yy + int(13 * s), fill=CYAN)
        c.create_text(bx + int(12 * s), yy + int(7 * s), text=f"GPU {g.get('idx', 0)}",
                      anchor="w", font=self.F(8, True), fill=CYAN)
        brand, bcol = brand_of(g.get("name", ""))
        name_txt = g.get("name", "GPU")
        slot = g.get("slot")
        if slot:
            if ":" in slot and len(slot) > 11:  # 去掉前缀域 00000000:
                slot = slot.split(":", 1)[1]
            name_txt += f"   [PCIe {slot}]"
        if brand:
            # 品牌色块 + 品牌名(标注显卡品牌),后跟完整型号(用字体实测宽度定位,不重叠)
            c.create_rectangle(bx + int(58 * s), yy + 2,
                               bx + int(66 * s), yy + int(13 * s), fill=bcol)
            c.create_text(bx + int(70 * s), yy + int(7 * s), text=brand,
                          anchor="w", font=self.F(9, True), fill=bcol)
            brand_w = self.F(9, True).measure(brand)
            nx = bx + int(70 * s) + brand_w + int(8 * s)
            c.create_text(nx, yy + int(7 * s), text=name_txt,
                          anchor="w", font=self.F(11, True), fill=TXT)
        else:
            c.create_text(bx + int(58 * s), yy + int(7 * s), text=name_txt,
                          anchor="w", font=self.F(11, True), fill=TXT)
        c.create_text(bx + bw, yy + int(7 * s), text=f"{util}%", anchor="e",
                      font=self.F(12, True), fill=uc)
        yy += title_h

        # 行2:Util 条(标签左,条中,百分比右)
        c.create_text(bx, yy + int(5 * s), text="UTIL", anchor="w", font=self.F(8), fill=DIM)
        bar_x = bx + int(42 * s)
        bar_w = bw - int(42 * s)
        c.create_rectangle(bar_x, yy, bar_x + bar_w, yy + int(10 * s), fill=BAR_BG, outline="")
        if bar_w > 0:
            c.create_rectangle(bar_x, yy, bar_x + int(bar_w * util / 100), yy + int(10 * s), fill=uc, outline="")
        c.create_text(bar_x + bar_w, yy + int(5 * s), text=f"{util}%", anchor="e",
                      font=self.F(8, True), fill=uc)
        yy += util_h

        # 行3:VRAM 条与数值同行(数值右端预留,条画在文字之下 → 不再遮挡)
        c.create_text(bx, yy + int(5 * s), text="VRAM", anchor="w", font=self.F(8), fill=DIM)
        vbar_x = bx + int(42 * s)
        vbar_w = bw - int(42 * s) - int(120 * s)
        if vbar_w > 0:
            c.create_rectangle(vbar_x, yy, vbar_x + vbar_w, yy + int(10 * s),
                               fill=BAR_BG, outline="")
            c.create_rectangle(vbar_x, yy, vbar_x + int(vbar_w * vp / 100),
                               yy + int(10 * s), fill=CYAN, outline="")
        vcol = CYAN
        if vp >= 85:
            vcol = RED
        elif vp >= 50:
            vcol = AMBER
        c.create_text(bx + bw, yy + int(5 * s),
                      text=f"{vram} / {vt} MiB   {vp}%", anchor="e",
                      font=self.F(10, True), fill=vcol)
        yy += vram_h

        # 行4:TEMP / PWR / FAN / CLK
        temp = g.get("temp", 0) or 0
        cols = [
            ("TEMP", f"{temp}C", AMBER if temp >= 83 else TXT),
            ("PWR", f"{g.get('pwr', 0):.0f}W", TXT),
            ("FAN", f"{g.get('fan', 0)}%", TXT),
            ("CLK", f"{g.get('clk', 0)}MHz", CYAN),
        ]
        colw = bw / 4
        for ci, (lab, val, vc) in enumerate(cols):
            cx = bx + int(colw * ci)
            c.create_text(cx, yy + int(4 * s), text=lab, anchor="w", font=self.F(8), fill=DIM)
            c.create_text(cx, yy + int(14 * s), text=val, anchor="w",
                          font=self.F(10, True), fill=vc)
        yy += kv_h

        # 行5:30s 利用率历史(吸收剩余高度)
        hy = yy + int(3 * s)
        c.create_rectangle(bx, hy, bx + bw, hy + hist_h, fill=HIST_BG, outline=BORDER, width=1)
        ci = g.get("idx", 0)
        rows = self.hist
        if rows:
            nlen = len(rows)
            step = bw / max(1, nlen)
            for i2, r in enumerate(rows):
                v = r[ci] if ci < len(r) else 0
                bh = max(2, int(hist_h * v / 100))
                bx0 = bx + int(step * i2)
                c.create_rectangle(bx0, hy + hist_h - bh,
                                   bx0 + max(1, int(step) - 1), hy + hist_h,
                                   fill=col_for(v), outline="")
        else:
            c.create_text(bx + bw // 2, hy + hist_h // 2, text="采样中…",
                          font=self.F(8), fill=DIM2)

    # ── 底栏 ──
    def _footer(self, c, w, ch, ox, oy, ftr, s):
        y = oy + ch - ftr
        c.create_rectangle(ox, y, ox + w, oy + ch, fill=PANEL2, outline="")
        c.create_line(ox, y, ox + w, y, fill=BORDER)
        drv = self._drv
        mid = f"   driver {drv}" if drv else ""
        left = f"poll {1000 // self.POLL_MS}Hz   {time.strftime('%H:%M:%S')}{mid}"
        c.create_text(ox + int(M * s), y + ftr // 2, text=left, anchor="w",
                      font=self.F(8), fill=DIM)
        c.create_text(ox + w - int(M * s), y + ftr // 2, text="nvidia-smi",
                      anchor="e", font=self.F(8), fill=DIM2)

    def close(self):
        self._save_pos()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    if "--test" in sys.argv:
        d = sample()
        print(json.dumps(d, ensure_ascii=False, indent=2) if d else "no data")
    elif "--selftest-gui" in sys.argv:
        root = tk.Tk()
        app = App(root)
        root.update()
        print("geom:", root.geometry())
        app.toggle_full(); root.update(); print("full:", root.geometry())
        app.toggle_full(); root.update(); print("restored:", root.geometry())
        root.destroy()
    else:
        main()
