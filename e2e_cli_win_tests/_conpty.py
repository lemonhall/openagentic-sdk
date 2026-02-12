from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Pattern

import ctypes
from ctypes import wintypes

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class COORD(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


HPCON = wintypes.HANDLE


CreatePseudoConsole = kernel32.CreatePseudoConsole
CreatePseudoConsole.argtypes = [COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(HPCON)]
CreatePseudoConsole.restype = ctypes.c_long  # HRESULT

ClosePseudoConsole = kernel32.ClosePseudoConsole
ClosePseudoConsole.argtypes = [HPCON]
ClosePseudoConsole.restype = None

ResizePseudoConsole = kernel32.ResizePseudoConsole
ResizePseudoConsole.argtypes = [HPCON, COORD]
ResizePseudoConsole.restype = ctypes.c_long  # HRESULT

CreatePipe = kernel32.CreatePipe
CreatePipe.argtypes = [ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p, wintypes.DWORD]
CreatePipe.restype = wintypes.BOOL

PeekNamedPipe = kernel32.PeekNamedPipe
PeekNamedPipe.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
PeekNamedPipe.restype = wintypes.BOOL

ReadFile = kernel32.ReadFile
ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
ReadFile.restype = wintypes.BOOL

WriteFile = kernel32.WriteFile
WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
WriteFile.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

TerminateProcess = kernel32.TerminateProcess
TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
TerminateProcess.restype = wintypes.BOOL

GetExitCodeProcess = kernel32.GetExitCodeProcess
GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
GetExitCodeProcess.restype = wintypes.BOOL

WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
WaitForSingleObject.restype = wintypes.DWORD

INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x00000102
STILL_ACTIVE = 259


InitializeProcThreadAttributeList = kernel32.InitializeProcThreadAttributeList
InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
InitializeProcThreadAttributeList.restype = wintypes.BOOL

UpdateProcThreadAttribute = kernel32.UpdateProcThreadAttribute
UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
UpdateProcThreadAttribute.restype = wintypes.BOOL

DeleteProcThreadAttributeList = kernel32.DeleteProcThreadAttributeList
DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
DeleteProcThreadAttributeList.restype = None

EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400

PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _check(ok: bool, msg: str) -> None:
    if ok:
        return
    err = ctypes.get_last_error()
    raise OSError(err, msg)


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", wintypes.LPVOID), ("bInheritHandle", wintypes.BOOL)]


CreateProcessW = kernel32.CreateProcessW
CreateProcessW.argtypes = [
    wintypes.LPCWSTR,  # lpApplicationName
    wintypes.LPWSTR,  # lpCommandLine
    ctypes.POINTER(SECURITY_ATTRIBUTES),  # lpProcessAttributes
    ctypes.POINTER(SECURITY_ATTRIBUTES),  # lpThreadAttributes
    wintypes.BOOL,  # bInheritHandles
    wintypes.DWORD,  # dwCreationFlags
    wintypes.LPVOID,  # lpEnvironment
    wintypes.LPCWSTR,  # lpCurrentDirectory
    ctypes.POINTER(STARTUPINFOEXW),  # lpStartupInfo
    ctypes.POINTER(PROCESS_INFORMATION),  # lpProcessInformation
]
CreateProcessW.restype = wintypes.BOOL


def _create_pipe() -> tuple[wintypes.HANDLE, wintypes.HANDLE]:
    r = wintypes.HANDLE()
    w = wintypes.HANDLE()
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.lpSecurityDescriptor = None
    sa.bInheritHandle = True
    _check(bool(CreatePipe(ctypes.byref(r), ctypes.byref(w), ctypes.byref(sa), 0)), "CreatePipe failed")
    return r, w


def _build_environment_block(env: dict[str, str]) -> ctypes.Array:
    # CreateProcessW expects a double-NUL terminated block of UTF-16 "k=v\0" strings.
    items = [f"{k}={v}" for k, v in env.items()]
    items.sort(key=lambda s: s.split("=", 1)[0].upper())
    block = "\0".join(items) + "\0\0"
    return ctypes.create_unicode_buffer(block)


@dataclass
class ConPtyResult:
    exit_code: int
    output: str


class ConPtyProcess:
    def __init__(self, argv: list[str], *, cwd: str, env: dict[str, str], cols: int = 120, rows: int = 30) -> None:
        if os.name != "nt":
            raise RuntimeError("ConPtyProcess is Windows-only.")

        # Pipes: input -> conpty, output <- conpty
        in_read, in_write = _create_pipe()
        out_read, out_write = _create_pipe()
        self._in_read = in_read
        self._in_write = in_write
        self._out_read = out_read
        self._out_write = out_write

        size = COORD(int(cols), int(rows))
        hpc = HPCON()
        hr = CreatePseudoConsole(size, in_read, out_write, 0, ctypes.byref(hpc))
        if hr != 0:
            raise OSError(int(hr), "CreatePseudoConsole failed")
        self._hpc = hpc

        # Attribute list.
        size_needed = ctypes.c_size_t(0)
        InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size_needed))
        attr_buf = ctypes.create_string_buffer(size_needed.value)
        _check(bool(InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(size_needed))), "InitializeProcThreadAttributeList failed")
        self._attr_list = attr_buf

        _check(
            bool(
                UpdateProcThreadAttribute(
                    attr_buf,
                    0,
                    PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                    self._hpc,
                    ctypes.sizeof(HPCON),
                    None,
                    None,
                )
            ),
            "UpdateProcThreadAttribute(PSEUDOCONSOLE) failed",
        )

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.lpAttributeList = ctypes.cast(attr_buf, ctypes.c_void_p)
        pi = PROCESS_INFORMATION()

        cmdline = " ".join([_quote_arg(a) for a in argv])
        self._env_buf = _build_environment_block(env)
        env_block = ctypes.cast(self._env_buf, ctypes.c_void_p)
        ok = CreateProcessW(
            None,
            ctypes.create_unicode_buffer(cmdline),
            None,
            None,
            True,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            env_block,
            cwd,
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        _check(bool(ok), "CreateProcessW failed")

        self._proc = pi
        self._buf = ""

        # Close the ends we handed to the pseudoconsole. The pseudoconsole takes ownership, but
        # we keep them alive until after CreateProcessW returns to avoid premature teardown.
        try:
            CloseHandle(in_read)
        except Exception:
            pass
        try:
            CloseHandle(out_write)
        except Exception:
            pass

    @property
    def pid(self) -> int:
        return int(self._proc.dwProcessId)

    def send(self, s: str) -> None:
        data = s.encode("utf-8", errors="replace")
        n = wintypes.DWORD(0)
        _check(bool(WriteFile(self._in_write, data, len(data), ctypes.byref(n), None)), "WriteFile failed")

    def _peek_available(self) -> int:
        avail = wintypes.DWORD(0)
        ok = PeekNamedPipe(self._out_read, None, 0, None, ctypes.byref(avail), None)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, "PeekNamedPipe failed")
        return int(avail.value)

    def _read_some(self, *, timeout_s: float) -> str:
        deadline = time.time() + max(0.0, float(timeout_s))
        while time.time() < deadline:
            avail = self._peek_available()
            if avail <= 0:
                time.sleep(0.01)
                continue
            to_read = min(4096, avail)
            buf = (ctypes.c_char * to_read)()
            got = wintypes.DWORD(0)
            ok = ReadFile(self._out_read, ctypes.byref(buf), to_read, ctypes.byref(got), None)
            if not ok:
                return ""
            if got.value <= 0:
                return ""
            return bytes(buf[: got.value]).decode("utf-8", errors="replace")
        return ""

    def read_until(self, pattern: str | Pattern[str], *, timeout_s: float = 30.0, strip_ansi_codes: bool = True) -> str:
        if isinstance(pattern, str):
            rx: Pattern[str] = re.compile(re.escape(pattern))
        else:
            rx = pattern

        deadline = time.time() + max(0.1, float(timeout_s))
        while True:
            hay = strip_ansi(self._buf) if strip_ansi_codes else self._buf
            if rx.search(hay):
                return hay

            if time.time() >= deadline:
                sample = hay[-4000:]
                raise TimeoutError(f"timeout waiting for pattern: {rx.pattern}\n--- tail ---\n{sample}")

            chunk = self._read_some(timeout_s=0.2)
            if chunk:
                self._buf += chunk
                hay_after = strip_ansi(self._buf) if strip_ansi_codes else self._buf
                if rx.search(hay_after):
                    return hay_after

            if self._poll_exit_code() is not None and self._peek_available() == 0:
                hay2 = strip_ansi(self._buf) if strip_ansi_codes else self._buf
                sample = hay2[-4000:]
                raise AssertionError(f"process exited before pattern matched: {rx.pattern}\n--- tail ---\n{sample}")

    def _poll_exit_code(self) -> int | None:
        code = wintypes.DWORD(0)
        if not GetExitCodeProcess(self._proc.hProcess, ctypes.byref(code)):
            return None
        if int(code.value) == STILL_ACTIVE:
            return None
        return int(code.value)

    def close(self, *, timeout_s: float = 10.0) -> ConPtyResult:
        # Drain any remaining output first.
        for _ in range(50):
            chunk = self._read_some(timeout_s=0.05)
            if not chunk:
                break
            self._buf += chunk

        ms = int(max(0.1, float(timeout_s)) * 1000)
        rc = WaitForSingleObject(self._proc.hProcess, ms)
        if rc == WAIT_TIMEOUT:
            # Best-effort: send exit and wait a bit more.
            try:
                self.send("/exit\r\n")
            except Exception:
                pass
            rc2 = WaitForSingleObject(self._proc.hProcess, 2000)
            if rc2 == WAIT_TIMEOUT:
                # Force terminate to avoid leaking a running conhost/python keeping temp dirs locked.
                try:
                    TerminateProcess(self._proc.hProcess, 1)
                except Exception:
                    pass
                WaitForSingleObject(self._proc.hProcess, 2000)

        # Drain final output.
        for _ in range(200):
            chunk = self._read_some(timeout_s=0.05)
            if not chunk:
                break
            self._buf += chunk

        code = self._poll_exit_code()
        exit_code = int(code) if code is not None else 1

        # Cleanup.
        try:
            CloseHandle(self._in_read)
        except Exception:
            pass
        try:
            CloseHandle(self._in_write)
        except Exception:
            pass
        try:
            CloseHandle(self._out_read)
        except Exception:
            pass
        try:
            CloseHandle(self._out_write)
        except Exception:
            pass
        try:
            CloseHandle(self._proc.hThread)
        except Exception:
            pass
        try:
            CloseHandle(self._proc.hProcess)
        except Exception:
            pass
        try:
            DeleteProcThreadAttributeList(self._attr_list)
        except Exception:
            pass
        try:
            ClosePseudoConsole(self._hpc)
        except Exception:
            pass

        return ConPtyResult(exit_code=exit_code, output=self._buf)


def _quote_arg(s: str) -> str:
    # Minimal CreateProcess quoting rules.
    if not s:
        return '""'
    if not any(ch in s for ch in ' \t"'):
        return s
    bs = 0
    out: list[str] = ['"']
    for ch in s:
        if ch == "\\":
            bs += 1
            continue
        if ch == '"':
            out.append("\\" * (bs * 2 + 1))
            out.append('"')
            bs = 0
            continue
        if bs:
            out.append("\\" * bs)
            bs = 0
        out.append(ch)
    if bs:
        out.append("\\" * (bs * 2))
    out.append('"')
    return "".join(out)


def conpty_available() -> bool:
    # ConPTY was introduced in Windows 10 1809; this v24 suite targets Windows 11.
    return os.name == "nt" and bool(getattr(kernel32, "CreatePseudoConsole", None))
