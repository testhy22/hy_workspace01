# -*- coding: utf-8 -*-
"""
通过 COM 接口 (IShellLinkW + IPersistFile) 直接创建 .lnk 快捷方式。
不依赖 PowerShell / cscript / pywin32，全部使用标准库 ctypes。
"""
import ctypes
import os
import sys
import uuid

ole32 = ctypes.WinDLL("ole32")

CLSCTX_INPROC_SERVER = 1
S_OK = 0


class GUID(ctypes.Structure):
    _fields_ = [
        ("d1", ctypes.c_uint32),
        ("d2", ctypes.c_uint16),
        ("d3", ctypes.c_uint16),
        ("d4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, s):
        super().__init__()
        u = uuid.UUID(s)
        self.d1 = u.time_low
        self.d2 = u.time_mid
        self.d3 = u.time_hi_version
        for i, b in enumerate(u.bytes[8:]):
            self.d4[i] = b


CLSID_ShellLink = GUID("{00021401-0000-0000-C000-000000000046}")
IID_IShellLinkW = GUID("{000214F9-0000-0000-C000-000000000046}")
IID_IPersistFile = GUID("{0000010B-0000-0000-C000-000000000046}")


def vtbl_call(ptr, index, restype, argtypes, *args):
    """按 vtable 下标调用 COM 方法。ptr 为接口指针。"""
    vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    fn = proto(vt[index])
    return fn(ptr, *args)


def shell_link(target, workdir, desc, icon, lnk_path):
    hr = ole32.CoInitialize(None)
    p_unk = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(CLSID_ShellLink),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(IID_IShellLinkW),
        ctypes.byref(p_unk),
    )
    if hr != S_OK:
        raise OSError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08X}")

    # IShellLinkW vtable: 3 GetPath, 4 GetIDList, 5 SetIDList, 6 GetDescription,
    # 7 SetDescription, 8 GetWorkingDirectory, 9 SetWorkingDirectory,
    # 10 GetArguments, 11 SetArguments, ..., 16 GetIconLocation,
    # 17 SetIconLocation, 18 SetRelativePath, 19 Resolve, 20 SetPath
    vtbl_call(p_unk, 20, ctypes.c_int, [ctypes.c_wchar_p, ctypes.c_uint32], target, 0)
    vtbl_call(p_unk, 9, ctypes.c_int, [ctypes.c_wchar_p], workdir)
    vtbl_call(p_unk, 7, ctypes.c_int, [ctypes.c_wchar_p], desc)
    vtbl_call(p_unk, 17, ctypes.c_int, [ctypes.c_wchar_p, ctypes.c_int], icon, 0)

    # QueryInterface -> IPersistFile
    p_pf = ctypes.c_void_p()
    hr = vtbl_call(
        p_unk,
        0,
        ctypes.c_int,
        [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
        ctypes.byref(IID_IPersistFile),
        ctypes.byref(p_pf),
    )
    if hr != S_OK:
        raise OSError(f"QueryInterface(IPersistFile) failed: 0x{hr & 0xFFFFFFFF:08X}")

    # IPersistFile::Save(index=6)
    hr = vtbl_call(p_pf, 6, ctypes.c_int, [ctypes.c_wchar_p, ctypes.c_int], lnk_path, 1)
    if hr != S_OK:
        raise OSError(f"IPersistFile::Save failed: 0x{hr & 0xFFFFFFFF:08X}")

    # Release
    vtbl_call(p_pf, 2, ctypes.c_ulong, [])
    vtbl_call(p_unk, 2, ctypes.c_ulong, [])
    return True


def main():
    target = r"E:\Program Files\WattToolkit\Steam++.exe"
    workdir = r"E:\Program Files\WattToolkit"
    desc = "Watt Toolkit"

    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    programs = os.path.join(home, "AppData", "Roaming", "Microsoft",
                            "Windows", "Start Menu", "Programs")

    made = []
    for d in (desktop, programs):
        if not os.path.isdir(d):
            print(f"[skip] 目录不存在: {d}")
            continue
        lnk = os.path.join(d, "Watt Toolkit.lnk")
        shell_link(target, workdir, desc, target, lnk)
        size = os.path.getsize(lnk)
        print(f"[ok] {lnk}  ({size} bytes)")
        made.append(lnk)

    print(f"共创建 {len(made)} 个快捷方式")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
