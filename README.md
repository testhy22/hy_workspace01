# hy-workspace

个人工作仓库。

## 环境

- Git 2.56.0.windows.2 (Windows)
- 提交身份: yhuang <2568494086@qq.com>

## 说明

此仓库由 WorkBuddy 初始化。

## 脚本

| 文件 | 用途 |
|---|---|
| `scripts/watt_download.py` | 大文件多线程分块下载器：多镜像轮换 + 断点续传 + SHA256 校验（用于绕过 GitHub 直连限速）|
| `scripts/make_shortcut.py` | 用 ctypes 直调 `IShellLinkW`/`IPersistFile` 创建 `.lnk` 快捷方式，不依赖 pywin32 |

两个脚本均只需 Python 标准库。运行前请按需修改脚本顶部的路径与镜像常量。
