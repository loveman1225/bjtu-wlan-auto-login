import argparse
import base64
import ctypes
import ctypes.wintypes as wintypes
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "campus_net_guard_config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "campus_net_guard_config.example.json"
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_V = 0x56


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", GUID),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", wintypes.DWORD),
    ]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1),
    ]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", ctypes.c_ubyte * 32),
    ]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", wintypes.DWORD),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11PhyType", wintypes.DWORD),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("ulRxRate", wintypes.ULONG),
        ("ulTxRate", wintypes.ULONG),
    ]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
        ("dot11AuthAlgorithm", wintypes.DWORD),
        ("dot11CipherAlgorithm", wintypes.DWORD),
    ]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("isState", wintypes.DWORD),
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", wintypes.WCHAR * 256),
        ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
        ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES),
    ]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            "Missing campus_net_guard_config.json. Copy "
            "campus_net_guard_config.example.json to campus_net_guard_config.json "
            "and edit it for your machine."
        )
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def setup_logging(config: dict) -> None:
    log_path = Path(config.get("log_file", "campus_net_guard.log"))
    if not log_path.is_absolute():
        log_path = BASE_DIR / log_path

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def config_path_value(config: dict, key: str, default: str) -> Path:
    value = Path(config.get(key, default))
    if value.is_absolute():
        return value
    return BASE_DIR / value


def save_credentials(config: dict, username: str, password: str) -> None:
    credential_path = config_path_value(
        config,
        "credential_file",
        "campus_net_guard_credentials.json",
    )
    credentials = {
        "username": username,
        "password": password,
    }
    credential_path.write_text(
        json.dumps(credentials, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_credentials(config: dict) -> dict | None:
    credential_path = config_path_value(
        config,
        "credential_file",
        "campus_net_guard_credentials.json",
    )
    if not credential_path.exists():
        logging.warning("credential file not found: %s", credential_path)
        return None

    try:
        with credential_path.open("r", encoding="utf-8") as f:
            credentials = json.load(f)
    except Exception as exc:
        logging.warning("failed to load credentials: %s", exc)
        return None

    if not credentials.get("username") or not credentials.get("password"):
        logging.warning("credential file is missing username or password")
        return None
    return credentials


def get_clipboard_text() -> str | None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(ctypes.c_void_p(pointer))
        except (OSError, ValueError):
            return None
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    data = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())

    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        handle = None
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def press_key(vk: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def press_ctrl_v() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def paste_text(text: str) -> None:
    set_clipboard_text(text)
    time.sleep(0.1)
    press_ctrl_v()


def current_ssid_from_wlanapi() -> str | None:
    wlanapi = ctypes.WinDLL("wlanapi")
    handle = wintypes.HANDLE()
    negotiated_version = wintypes.DWORD()

    result = wlanapi.WlanOpenHandle(
        2,
        None,
        ctypes.byref(negotiated_version),
        ctypes.byref(handle),
    )
    if result != 0:
        return None

    interface_list_ptr = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
    try:
        result = wlanapi.WlanEnumInterfaces(handle, None, ctypes.byref(interface_list_ptr))
        if result != 0:
            return None

        count = interface_list_ptr.contents.dwNumberOfItems
        interface_array_type = WLAN_INTERFACE_INFO * count
        interface_array = ctypes.cast(
            interface_list_ptr.contents.InterfaceInfo,
            ctypes.POINTER(interface_array_type),
        ).contents

        for interface in interface_array:
            data_size = wintypes.DWORD()
            data_ptr = ctypes.c_void_p()
            opcode = wintypes.DWORD()
            result = wlanapi.WlanQueryInterface(
                handle,
                ctypes.byref(interface.InterfaceGuid),
                7,  # wlan_intf_opcode_current_connection
                None,
                ctypes.byref(data_size),
                ctypes.byref(data_ptr),
                ctypes.byref(opcode),
            )
            if result != 0 or not data_ptr:
                continue

            try:
                attrs = ctypes.cast(
                    data_ptr,
                    ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES),
                ).contents
                ssid_struct = attrs.wlanAssociationAttributes.dot11Ssid
                if ssid_struct.uSSIDLength:
                    raw = bytes(ssid_struct.ucSSID[: ssid_struct.uSSIDLength])
                    return raw.decode("utf-8", errors="replace")
            finally:
                wlanapi.WlanFreeMemory(data_ptr)
    finally:
        if interface_list_ptr:
            wlanapi.WlanFreeMemory(interface_list_ptr)
        wlanapi.WlanCloseHandle(handle, None)

    return None


def current_ssid_from_netsh() -> str | None:
    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        logging.info("netsh wlan query failed: %s", completed.stderr.strip())
        return None

    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("ssid") and "bssid" not in stripped.lower():
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def get_current_ssid() -> str | None:
    return current_ssid_from_wlanapi() or current_ssid_from_netsh()


def http_probe(url: str) -> tuple[bool, str]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPRedirectHandler(),
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "campus-net-guard/1.0",
            "Cache-Control": "no-cache",
        },
    )

    try:
        with opener.open(request, timeout=8) as response:
            final_url = response.geturl()
            status = getattr(response, "status", response.getcode())
            body = response.read(128).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        final_url = exc.geturl()
        status = exc.code
        body = ""
    except Exception as exc:
        return False, f"{url} failed: {exc}"

    final_url_lower = final_url.lower()
    if "login.bjtu.edu.cn" in final_url_lower:
        return False, f"{url} redirected to BJTU login page: {final_url}"

    if "msftconnecttest.com/connecttest.txt" in url.lower():
        ok = status == 200 and "Microsoft Connect Test" in body
        return ok, f"{url} status={status} final={final_url}"

    if "generate_204" in url.lower():
        ok = status == 204
        return ok, f"{url} status={status} final={final_url}"

    ok = 200 <= status < 400 and "login.bjtu.edu.cn" not in final_url_lower
    return ok, f"{url} status={status} final={final_url}"


def post_form(url: str, fields: dict[str, str], timeout: int = 12) -> tuple[bool, str]:
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(512).decode("gb18030", errors="ignore")
            return True, f"status={response.status} final={response.geturl()} body={body[:120]!r}"
    except Exception as exc:
        return False, str(exc)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("websocket connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class DevToolsWebSocket:
    def __init__(self, ws_url: str):
        parsed = urllib.parse.urlparse(ws_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.sock: socket.socket | None = None
        self.next_id = 1

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            self.sock.close()

    def connect(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((self.host, self.port), timeout=10)
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(response.decode("latin1", errors="replace"))
        self.sock = sock

    def send_text(self, text: str) -> None:
        if not self.sock:
            raise ConnectionError("websocket is not connected")
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str:
        if not self.sock:
            raise ConnectionError("websocket is not connected")
        while True:
            first, second = recv_exact(self.sock, 2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(recv_exact(self.sock, 2), "big")
            elif length == 127:
                length = int.from_bytes(recv_exact(self.sock, 8), "big")
            mask = recv_exact(self.sock, 4) if masked else b""
            payload = recv_exact(self.sock, length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 1:
                return payload.decode("utf-8", errors="replace")
            if opcode == 8:
                raise ConnectionError("websocket closed")
            if opcode == 9:
                self.send_pong(payload)

    def send_pong(self, payload: bytes) -> None:
        if not self.sock:
            return
        header = bytearray([0x8A])
        length = len(payload)
        header.append(0x80 | length)
        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def call(self, method: str, params: dict | None = None, timeout: int = 20) -> dict:
        message_id = self.next_id
        self.next_id += 1
        self.send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = json.loads(self.recv_text())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
        raise TimeoutError(method)


def read_json_url(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_devtools_page(
    port: int,
    timeout_seconds: int,
    url_contains: str | None = None,
) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    list_url = f"http://127.0.0.1:{port}/json/list"
    while time.monotonic() < deadline:
        try:
            targets = read_json_url(list_url, timeout=3)
            pages = [target for target in targets if target.get("type") == "page"]
            if url_contains:
                matching_pages = [
                    target for target in pages if url_contains in target.get("url", "")
                ]
                if matching_pages:
                    return matching_pages[0]
            if pages:
                return pages[0]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def evaluate_with_retries(
    ws: DevToolsWebSocket,
    expression: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return ws.call(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "timeout": 5000,
                },
                timeout=8,
            )
        except Exception as exc:
            last_error = exc
            text = str(exc)
            if (
                "Cannot find default execution context" not in text
                and "Execution context was destroyed" not in text
            ):
                raise
            time.sleep(0.5)
    raise TimeoutError(f"Runtime.evaluate did not become ready: {last_error}")


def connectivity_status(config: dict) -> str:
    saw_bjtu_portal = False

    for url in config["connectivity_checks"]:
        ok, detail = http_probe(url)
        logging.info("connectivity check: ok=%s %s", ok, detail)
        if ok:
            return "online"
        if "login.bjtu.edu.cn" in detail.lower():
            saw_bjtu_portal = True

    if saw_bjtu_portal:
        return "bjtu_portal"
    return "offline_or_blocked"


def wait_until_online(config: dict, timeout_seconds: int = 20) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if connectivity_status(config) == "online":
            return True
        time.sleep(2)
    return False


def direct_portal_login(config: dict) -> bool:
    if not config.get("direct_login", False):
        return False

    credentials = load_credentials(config)
    if not credentials:
        return False

    login_url = config.get("portal_login_url")
    if not login_url:
        logging.warning("portal_login_url is not configured")
        return False

    fields = dict(config.get("portal_login_fields", {}))
    fields["DDDDD"] = credentials["username"]
    fields["upass"] = credentials["password"]

    ok, detail = post_form(login_url, fields)
    logging.info("direct portal login submitted: ok=%s %s", ok, detail)
    if not ok:
        return False

    return wait_until_online(config, timeout_seconds=20)


def running_process_names() -> set[str]:
    try:
        completed = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()

    names: set[str] = set()
    for line in completed.stdout.splitlines():
        if not line:
            continue
        first = line.split(",", 1)[0].strip().strip('"')
        if first.lower().endswith(".exe"):
            first = first[:-4]
        names.add(first.lower())
    return names


def clash_restart_marker_path(config: dict) -> Path:
    return config_path_value(
        config,
        "clash_restart_marker_file",
        "clash_was_stopped.marker",
    )


def should_manage_clash(config: dict) -> bool:
    return bool(config.get("manage_clash", False))


def mark_clash_stopped(config: dict) -> None:
    if not should_manage_clash(config):
        return
    try:
        clash_restart_marker_path(config).write_text(str(time.time()), encoding="utf-8")
    except Exception as exc:
        logging.info("failed to write Clash restart marker: %s", exc)


def clear_clash_stopped_marker(config: dict) -> None:
    if not should_manage_clash(config):
        return
    try:
        clash_restart_marker_path(config).unlink(missing_ok=True)
    except Exception as exc:
        logging.info("failed to clear Clash restart marker: %s", exc)


def should_restart_clash(config: dict, clash_was_stopped: bool) -> bool:
    if not should_manage_clash(config):
        return False
    if clash_was_stopped:
        return True
    if clash_restart_marker_path(config).exists():
        return True
    return bool(config.get("ensure_clash_after_login", False))


def is_clash_gui_running() -> bool:
    return "clash-verge" in running_process_names()


def stop_clash(config: dict) -> bool:
    if not should_manage_clash(config):
        logging.info("Clash management is disabled")
        return False

    running = running_process_names()
    stopped_any = False

    for name in config.get("clash_process_names", []):
        normalized = name.lower().removesuffix(".exe")
        if normalized not in running:
            continue

        exe_name = f"{normalized}.exe"
        completed = subprocess.run(
            ["taskkill", "/IM", exe_name, "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
        )
        logging.info(
            "taskkill %s returncode=%s stdout=%s stderr=%s",
            exe_name,
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )
        if completed.returncode == 0:
            stopped_any = True
            mark_clash_stopped(config)

    if stopped_any:
        time.sleep(3)

    return stopped_any


def start_clash(config: dict) -> None:
    if not should_manage_clash(config):
        logging.info("Clash management is disabled")
        return

    if is_clash_gui_running():
        logging.info("Clash Verge is already running")
        clear_clash_stopped_marker(config)
        return

    executable = config.get("clash_executable")
    if not executable or not Path(executable).exists():
        logging.warning("Clash executable not found: %s", executable)
        return

    subprocess.Popen(
        [executable],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    logging.info("started Clash Verge: %s", executable)
    clear_clash_stopped_marker(config)


def browser_dom_login(config: dict) -> bool:
    if not config.get("browser_dom_login", False):
        return False

    credentials = load_credentials(config)
    if not credentials:
        return False

    browser_executable = Path(config.get("browser_executable", ""))
    if not browser_executable.exists():
        logging.warning("browser executable not found: %s", browser_executable)
        return False

    port = int(config.get("browser_debug_port", 9223))
    timeout_seconds = int(config.get("browser_dom_login_timeout_seconds", 35))
    profile_dir = config_path_value(
        config,
        "browser_user_data_dir",
        "edge-campus-net-guard-profile",
    )
    profile_dir.mkdir(parents=True, exist_ok=True)

    login_url = config["login_url"]
    command = [
        str(browser_executable),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--new-window",
        "about:blank",
    ]
    logging.info("starting browser DOM login with %s", browser_executable)
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    try:
        target = wait_for_devtools_page(port, timeout_seconds=timeout_seconds)
        if not target or not target.get("webSocketDebuggerUrl"):
            logging.warning("browser devtools page was not available")
            return False

        script = f"""
(async () => {{
  const username = {json.dumps(credentials["username"])};
  const password = {json.dumps(credentials["password"])};
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  const visible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }};
  const setNativeValue = (el, value) => {{
    el.focus();
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value') ||
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (desc && desc.set) {{
      desc.set.call(el, value);
    }} else {{
      el.value = value;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const describeInputs = () => Array.from(document.querySelectorAll('input')).map((el) => ({{
    type: el.type || '',
    name: el.name || '',
    id: el.id || '',
    placeholder: el.placeholder || '',
    visible: visible(el)
  }}));
  const findFields = () => {{
    const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
    let user = document.querySelector('input[name="DDDDD"], input#DDDDD, input[name="username"], input[name="user"], input[type="text"], input:not([type])');
    let pass = document.querySelector('input[name="upass"], input#upass, input[type="password"]');
    if (!visible(user)) {{
      user = inputs.find((el) => !['password','hidden','submit','button','checkbox','radio'].includes((el.type || 'text').toLowerCase()));
    }}
    if (!visible(pass)) {{
      pass = inputs.find((el) => (el.type || '').toLowerCase() === 'password') || inputs[1];
    }}
    return {{ user, pass, inputs }};
  }};
  for (let i = 0; i < 80; i++) {{
    const {{ user, pass, inputs }} = findFields();
    if (user && pass) {{
      user.scrollIntoView({{ block: 'center', inline: 'center' }});
      user.click();
      setNativeValue(user, username);
      await sleep(150);
      pass.scrollIntoView({{ block: 'center', inline: 'center' }});
      pass.click();
      setNativeValue(pass, password);
      await sleep(150);

      const buttons = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],a,div,span')).filter(visible);
      const submit = buttons.find((el) => /登录|登\\s*录|login|connect|上网|认证/.test(((el.innerText || el.value || el.textContent || '') + '').toLowerCase()));
      if (submit) {{
        submit.click();
      }} else if (pass.form && pass.form.requestSubmit) {{
        pass.form.requestSubmit();
      }} else if (pass.form) {{
        pass.form.submit();
      }} else {{
        pass.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
        pass.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
      }}
      return {{ ok: true, inputs: describeInputs(), url: location.href }};
    }}
    await sleep(500);
  }}
  return {{ ok: false, inputs: describeInputs(), url: location.href, title: document.title }};
}})()
"""
        with DevToolsWebSocket(target["webSocketDebuggerUrl"]) as ws:
            try:
                ws.call("Page.enable")
            except Exception as exc:
                logging.info("Page.enable failed: %s", exc)
            try:
                ws.call("Runtime.enable")
            except Exception as exc:
                logging.info("Runtime.enable failed: %s", exc)
            ws.call("Page.navigate", {"url": login_url})
            time.sleep(float(config.get("auto_login_page_load_seconds", 4)))
            result = evaluate_with_retries(ws, script, timeout_seconds=timeout_seconds)
        value = result.get("result", {}).get("value")
        logging.info("browser DOM login result: %s", value)
        if not isinstance(value, dict) or not value.get("ok"):
            return False

        return wait_until_online(config, timeout_seconds=25)
    except Exception as exc:
        logging.warning("browser DOM login failed: %s", exc)
        return False
    finally:
        if process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass


def open_login_page(config: dict) -> None:
    login_url = config["login_url"]
    logging.info("opening login page: %s", login_url)
    webbrowser.open(login_url, new=2, autoraise=True)


def auto_login(config: dict) -> bool:
    if not config.get("auto_login", False):
        return False

    credentials = load_credentials(config)
    if not credentials:
        return False

    page_load_seconds = float(config.get("auto_login_page_load_seconds", 4))
    logging.info("waiting %.1f seconds before auto login", page_load_seconds)
    time.sleep(page_load_seconds)

    try:
        original_clipboard = get_clipboard_text()
    except Exception as exc:
        logging.info("clipboard backup skipped: %s", exc)
        original_clipboard = None
    try:
        paste_text(credentials["username"])
        time.sleep(0.2)
        press_key(VK_TAB)
        time.sleep(0.2)
        paste_text(credentials["password"])
        time.sleep(0.2)
        press_key(VK_RETURN)
        logging.info("auto login keystrokes sent")
        return True
    except Exception as exc:
        logging.warning("auto login failed: %s", exc)
        return False
    finally:
        if original_clipboard is not None:
            try:
                set_clipboard_text(original_clipboard)
            except Exception as exc:
                logging.info("failed to restore clipboard: %s", exc)


def main() -> int:
    config = load_config()
    setup_logging(config)

    target_ssid = config["target_ssid"]
    current_ssid = get_current_ssid()
    logging.info("current ssid: %s", current_ssid)

    if current_ssid and current_ssid != target_ssid:
        logging.info("not on target Wi-Fi %s; exiting", target_ssid)
        return 0

    status = connectivity_status(config)
    if status == "online":
        logging.info("internet is available; exiting")
        return 0

    if current_ssid is None and status != "bjtu_portal":
        logging.info("SSID unknown and BJTU portal not detected; exiting")
        return 0

    logging.info("BJTU login appears needed; status=%s", status)
    clash_was_stopped = stop_clash(config)

    if direct_portal_login(config):
        logging.info("direct portal login appears successful")
        if should_restart_clash(config, clash_was_stopped):
            start_clash(config)
        return 0

    logging.info("direct portal login did not restore connectivity; trying browser DOM login")
    if browser_dom_login(config):
        logging.info("browser DOM login appears successful")
        if should_restart_clash(config, clash_was_stopped):
            start_clash(config)
        return 0

    logging.info("browser DOM login did not restore connectivity; falling back to keystrokes")
    open_login_page(config)
    attempted_auto_login = auto_login(config)
    wait_seconds = int(config.get("browser_open_wait_seconds", 90))
    if attempted_auto_login:
        wait_seconds = min(wait_seconds, 20)
    logging.info("waiting %s seconds for browser login", wait_seconds)
    time.sleep(wait_seconds)

    if connectivity_status(config) == "online":
        logging.info("login appears successful")
        if should_restart_clash(config, clash_was_stopped):
            start_clash(config)
        return 0

    logging.warning("internet still unavailable after login window")
    if should_restart_clash(config, clash_was_stopped):
        start_clash(config)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BJTU campus network guard")
    clash_group = parser.add_mutually_exclusive_group()
    clash_group.add_argument(
        "--enable-clash",
        action="store_true",
        help="Enable Clash Verge management in campus_net_guard_config.json.",
    )
    clash_group.add_argument(
        "--disable-clash",
        action="store_true",
        help="Disable Clash Verge management in campus_net_guard_config.json.",
    )
    parser.add_argument(
        "--set-credentials",
        nargs=2,
        metavar=("USERNAME", "PASSWORD"),
        help="Write BJTU login credentials to the configured credentials JSON file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.enable_clash or args.disable_clash:
        cfg = load_config()
        cfg["manage_clash"] = bool(args.enable_clash)
        save_config(cfg)
        state = "enabled" if args.enable_clash else "disabled"
        print(f"Clash Verge management {state}.")
        raise SystemExit(0)
    if args.set_credentials:
        cfg = load_config()
        save_credentials(cfg, args.set_credentials[0], args.set_credentials[1])
        print("Credentials saved to the configured credentials file.")
        raise SystemExit(0)
    raise SystemExit(main())
