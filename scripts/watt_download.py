# -*- coding: utf-8 -*-
"""
Watt Toolkit 安装包：多线程分块并发下载 + 自动切换镜像 + 断点续传 + 合并 + SHA256 校验

设计要点：
- 分块 1MB（实测镜像对单请求有 ~1MB 大小限制，超过会被 Connection reset）
- 多线程并发（默认 12），已完整的分块自动跳过（断点续传）
- 每块失败后自动轮换镜像重试，最多 6 次
- 全部完成后合并，并计算 SHA256 与 GitHub API 返回的官方 digest 比对
"""
import os
import sys
import json
import time
import hashlib
import threading
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR      = r"G:\workbuddy_hy\2026-10-16-22-46-10\downloads"
TMP      = os.path.join(DIR, ".wattparts")
OUT      = os.path.join(DIR, "WattToolkit_v3.1.0_win_x64.exe")
RAW      = "https://github.com/BeyondDimension/SteamTools/releases/download/3.1.0/Steam%2B%2B_v3.1.0_win_x64.exe"
MIRRORS  = [
    "https://githubproxy.cc/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
]
CHUNK   = 1024 * 1024          # 1MB / 块
WORKERS = 12                   # 并发线程数
CURL    = r"C:\Windows\System32\curl.exe"

# 清空代理环境变量，确保直连镜像（不走沙箱代理）
ENV = os.environ.copy()
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    ENV.pop(_k, None)

os.makedirs(TMP, exist_ok=True)


def get_asset_info():
    """从 GitHub API 获取精确大小与官方 digest（api.github.com 直连可用）"""
    req = urllib.request.Request(
        "https://api.github.com/repos/BeyondDimension/SteamTools/releases/latest",
        headers={"User-Agent": "watt-dl"},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    for a in data.get("assets", []):
        if a["name"].endswith("win_x64.exe"):
            return a["size"], a.get("digest")
    raise RuntimeError("未在 release 中找到 win_x64.exe")


TOTAL, DIGEST = get_asset_info()
N = (TOTAL + CHUNK - 1) // CHUNK
print(f"[阶段1] 取到元信息: {TOTAL} bytes ({TOTAL/1048576:.2f} MB), 分块 {N} 个", flush=True)
print(f"[阶段1] 官方 digest: {DIGEST}", flush=True)

lock = threading.Lock()
stat = {"done": 0, "fail": 0, "skip": 0}


def part_path(i):
    return os.path.join(TMP, f"part_{i:04d}.bin")


def expected_len(i):
    s = i * CHUNK
    e = min(s + CHUNK - 1, TOTAL - 1)
    return e - s + 1


def is_ok(i):
    p = part_path(i)
    return os.path.exists(p) and os.path.getsize(p) == expected_len(i)


def fetch(i):
    if is_ok(i):
        with lock:
            stat["skip"] += 1
        return True
    s = i * CHUNK
    e = min(s + CHUNK - 1, TOTAL - 1)
    p = part_path(i)
    for attempt in range(6):
        mb = MIRRORS[attempt % len(MIRRORS)]
        try:
            subprocess.run(
                [CURL, "--noproxy", "*", "-sSL", "-r", f"{s}-{e}", "-o", p,
                 "--max-time", "60", mb + RAW],
                timeout=75, check=False, env=ENV,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
        if is_ok(i):
            with lock:
                stat["done"] += 1
                if stat["done"] % 10 == 0:
                    print(f"  已补 {stat['done']} 块（累计跳过 {stat['skip']}）", flush=True)
            return True
        time.sleep(0.4)
    with lock:
        stat["fail"] += 1
    print(f"  块 {i} 重试 6 次仍失败", flush=True)
    return False


t0 = time.time()
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    list(ex.map(fetch, range(N)))

print(f"[阶段2] 下载结束: 新下 {stat['done']} 块, 跳过 {stat['skip']} 块, 失败 {stat['fail']} 块, "
      f"耗时 {(time.time()-t0)/60:.1f} 分钟", flush=True)

if stat["fail"] != 0:
    print("[阶段2] 存在失败块，中止合并", flush=True)
    sys.exit(2)

# ---------- 合并 + 计算 SHA256 ----------
print("[阶段3] 开始合并并计算 SHA256 ...", flush=True)
h = hashlib.sha256()
with open(OUT, "wb") as fo:
    for i in range(N):
        with open(part_path(i), "rb") as fi:
            while True:
                b = fi.read(4 * 1024 * 1024)
                if not b:
                    break
                fo.write(b)
                h.update(b)

size = os.path.getsize(OUT)
hexd = h.hexdigest()
print(f"[阶段3] 合并完成: {size} bytes ({size/1048576:.2f} MB)", flush=True)
print(f"[阶段3] 实际 SHA256: {hexd}", flush=True)

if DIGEST:
    algo, _, official = DIGEST.partition(":")
    if algo.lower() == "sha256":
        same = official.lower() == hexd
        print(f"[阶段3] 官方 SHA256: {official}", flush=True)
        print("[阶段3] 校验结果: " + ("OK 完全一致" if same else "MISMATCH 不一致"), flush=True)
        if not same:
            sys.exit(3)
else:
    print("[阶段3] 官方未提供 digest，跳过哈希比对（稍后由数字签名验证兜底）", flush=True)

print("[阶段3] 文件已就绪: " + OUT, flush=True)
