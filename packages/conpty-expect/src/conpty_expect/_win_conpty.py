from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

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
STARTF_USESTDHANDLES = 0x00000100

WAIT_TIMEOUT = 0x00000102
STILL_ACTIVE = 259


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


def _check(ok: bool, msg: str) -> None:
    if ok:
        return
    err = ctypes.get_last_error()
    raise OSError(err, msg)


def conpty_available() -> bool:
    return os.name == "nt" and bool(getattr(kernel32, "CreatePseudoConsole", None))


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
    items = [f"{k}={v}" for k, v in env.items()]
    items.sort(key=lambda s: s.split("=", 1)[0].upper())
    block = "\0".join(items) + "\0\0"
    return ctypes.create_unicode_buffer(block)


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


class WinConPty:
    def __init__(self, argv: list[str], *, cwd: str, env: dict[str, str], cols: int, rows: int) -> None:
        if os.name != "nt":
            raise RuntimeError("WinConPty is Windows-only.")

        in_read, in_write = _create_pipe()
        out_read, out_write = _create_pipe()
        self._in_write = in_write
        self._out_read = out_read
        self._term_tail = b""

        size = COORD(int(cols), int(rows))
        hpc = HPCON()
        hr = CreatePseudoConsole(size, in_read, out_write, 0, ctypes.byref(hpc))
        if hr != 0:
            raise OSError(int(hr), "CreatePseudoConsole failed")
        self._hpc = hpc

        size_needed = ctypes.c_size_t(0)
        InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size_needed))
        attr_buf = ctypes.create_string_buffer(size_needed.value)
        _check(
            bool(InitializeProcThreadAttributeList(attr_buf, 1, 0, ctypes.byref(size_needed))),
            "InitializeProcThreadAttributeList failed",
        )
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
        si.StartupInfo.dwFlags |= STARTF_USESTDHANDLES
        si.lpAttributeList = ctypes.cast(attr_buf, ctypes.c_void_p)
        pi = PROCESS_INFORMATION()

        cmdline = " ".join([_quote_arg(a) for a in argv])
        env_buf = _build_environment_block(env)
        env_block = ctypes.cast(env_buf, ctypes.c_void_p)
        ok = CreateProcessW(
            None,
            ctypes.create_unicode_buffer(cmdline),
            None,
            None,
            False,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            env_block,
            cwd,
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        _check(bool(ok), "CreateProcessW failed")

        self._proc = pi
        self._env_buf = env_buf  # keep alive

        # Close ends handed to ConPTY.
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

    def send_bytes(self, b: bytes) -> None:
        n = wintypes.DWORD(0)
        _check(bool(WriteFile(self._in_write, b, len(b), ctypes.byref(n), None)), "WriteFile failed")

    def _maybe_respond_to_terminal_queries(self, raw: bytes) -> None:
        # Minimal: answer CPR + device attributes, to avoid some CLIs stalling.
        view = self._term_tail + raw
        try:
            if b"\x1b[6n" in view or b"\x1b[?6n" in view:
                self.send_bytes(b"\x1b[1;1R")
            if b"\x1b[c" in view or b"\x1b[>c" in view:
                self.send_bytes(b"\x1b[?1;0c")
        except Exception:
            pass
        self._term_tail = view[-16:]

    def read_available_bytes(self, *, max_bytes: int = 4096) -> bytes:
        avail = wintypes.DWORD(0)
        ok = PeekNamedPipe(self._out_read, None, 0, None, ctypes.byref(avail), None)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, "PeekNamedPipe failed")
        n_avail = int(avail.value)
        if n_avail <= 0:
            return b""
        to_read = min(int(max_bytes), n_avail)
        buf = (ctypes.c_char * to_read)()
        got = wintypes.DWORD(0)
        ok2 = ReadFile(self._out_read, ctypes.byref(buf), to_read, ctypes.byref(got), None)
        if not ok2 or got.value <= 0:
            return b""
        raw = bytes(buf[: got.value])
        self._maybe_respond_to_terminal_queries(raw)
        return raw

    def poll_exit_code(self) -> int | None:
        code = wintypes.DWORD(0)
        if not GetExitCodeProcess(self._proc.hProcess, ctypes.byref(code)):
            return None
        v = int(code.value)
        if v == STILL_ACTIVE:
            return None
        return v

    def wait(self, timeout_s: float) -> bool:
        ms = int(max(0.0, float(timeout_s)) * 1000)
        rc = WaitForSingleObject(self._proc.hProcess, ms)
        return rc != WAIT_TIMEOUT

    def terminate(self) -> None:
        try:
            TerminateProcess(self._proc.hProcess, 1)
        except Exception:
            pass

    def close(self) -> None:
        for h in (self._in_write, self._out_read, self._proc.hThread, self._proc.hProcess):
            try:
                CloseHandle(h)
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

