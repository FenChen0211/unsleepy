# coding: utf-8
'''
win_device.py
在 Windows 上获取窗口名称
by: @wyf9, @pwnint, @kmizmal, @gongfuture, @LeiSureLyYrsc
基础依赖: pywin32, httpx, psutil
媒体信息依赖: winrt (pywinrt)
'''

# ----- Part: Import

import sys
import io
import asyncio
import time
from datetime import datetime
import json
import os
import threading
import httpx
import win32api  # type: ignore
import win32con  # type: ignore
import win32gui  # type: ignore
from pywintypes import error as pywinerror  # type: ignore
try:
    import psutil  # type: ignore
except ImportError:
    psutil = None

# ----- Part: Config


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


cfg = load_config()

SERVER: str = cfg.get('server', 'http://localhost:9010')
SECRET: str = cfg.get('secret', 'YOUR_SECRET_HERE')
DEVICE_ID: str = cfg.get('device_id', 'device-1')
DEVICE_SHOW_NAME: str = cfg.get('device_show_name', 'MyDevice1')
CHECK_INTERVAL: int = cfg.get('check_interval', 5)
BYPASS_SAME_REQUEST: bool = cfg.get('bypass_same_request', True)
SKIPPED_NAMES: list = cfg.get('skipped_names', [
    '', '系统托盘溢出窗口。', '新通知', '任务切换', '快速设置', '通知中心',
    '操作中心', '日期和时间信息', '网络连接', '电池信息', '搜索',
    '任务视图', 'Program Manager', '贴靠助手',
    'Flow.Launcher', 'Snipper - Snipaste', 'Paster - Snipaste'
])
NOT_USING_NAMES: list = cfg.get('not_using_names', [
    '启动', '「开始」菜单',
    '我们喜欢这张图片，因此我们将它与你共享。', '就像你看到的图像一样？选择以下选项',
    '喜欢这张图片吗?', 'Windows 默认锁屏界面'
])
REVERSE_APP_NAME: bool = cfg.get('reverse_app_name', False)
MOUSE_IDLE_TIME: int = cfg.get('mouse_idle_time', 15)
MOUSE_MOVE_THRESHOLD: int = cfg.get('mouse_move_threshold', 10)
DEBUG: bool = cfg.get('debug', False)
PROXY: str = cfg.get('proxy', '')
MEDIA_INFO_ENABLED: bool = cfg.get('media_info_enabled', True)
MEDIA_INFO_MODE: str = cfg.get('media_info_mode', 'standalone')
MEDIA_DEVICE_ID: str = cfg.get('media_device_id', 'media-device')
MEDIA_DEVICE_SHOW_NAME: str = cfg.get('media_device_show_name', '正在播放')
BATTERY_INFO_ENABLED: bool = cfg.get('battery_info_enabled', True)

# ----- Part: Friendly Name Mapping

FRIENDLY_NAMES = {
    'msedge': 'Microsoft Edge',
    'chrome': 'Google Chrome',
    'firefox': 'Firefox',
    'Code': 'Visual Studio Code',
    'pycharm64': 'PyCharm',
    'explorer': '文件资源管理器',
}

# ----- Part: stdout

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_print_ = print


def print(msg: str, **kwargs):
    msg = str(msg).replace('\u200b', '')
    try:
        _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True, **kwargs)
    except Exception as e:
        _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Log Error: {e}', flush=True)


def debug(msg: str, **kwargs):
    if DEBUG:
        print(msg, **kwargs)


def reverse_app_name(name: str) -> str:
    lst = name.split(' - ')
    new = []
    for i in lst:
        new = [i] + new
    return ' - '.join(new)


# ----- Part: Media Info

_media_fail_count = 0

if MEDIA_INFO_ENABLED:
    try:
        import winrt.windows.media.control as media  # type: ignore
    except ImportError:
        try:
            import winrt.windows.media.control as media  # type: ignore
        except ImportError:
            media = None


async def get_media_info():
    global _media_fail_count
    if media is None:
        return False, '', '', ''
    try:
        manager = await media.GlobalSystemMediaTransportControlsSessionManager.request_async()  # type: ignore
        session = manager.get_current_session()
        if not session:
            return False, '', '', ''

        info = session.get_playback_info()
        is_playing = info.playback_status == media.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING  # type: ignore

        props = await session.try_get_media_properties_async()
        title = props.title or '' if props else ''  # type: ignore
        artist = props.artist or '' if props else ''  # type: ignore
        album = props.album_title or '' if props else ''  # type: ignore

        if '未知唱片集' in album or ('<' in album and '>' in album):
            album = ''

        _media_fail_count = 0
        debug(f'[get_media_info] return: {is_playing}, {title}, {artist}, {album}')
        return is_playing, title, artist, album

    except Exception as e:
        _media_fail_count += 1
        if _media_fail_count <= 3:
            print(f'媒体信息获取失败 ({_media_fail_count}/3): {e}')
        else:
            debug(f'媒体信息获取失败: {e}')
        return False, '', '', ''


# ----- Part: Battery Info

if BATTERY_INFO_ENABLED and psutil:
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            print("无法获取电池信息")
            BATTERY_INFO_ENABLED = False
    except Exception as e:
        print(f"获取电池信息失败: {e}")
        BATTERY_INFO_ENABLED = False
elif not psutil:
    BATTERY_INFO_ENABLED = False


def get_battery_info():
    try:
        battery = psutil.sensors_battery()  # type: ignore
        if battery is None:
            return 0, "未知"
        percent = battery.percent
        power_plugged = battery.power_plugged
        status = "⚡" if power_plugged else ""
        debug(f'--- 电量: `{percent}%`, 状态: {status}')
        return percent, status
    except Exception as e:
        debug(f"获取电池信息失败: {e}")
        return 0, "未知"


# ----- Part: App Info


def get_app_info(hwnd):
    raw_title = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32gui.GetWindowThreadProcessId(hwnd)
        if pid and psutil:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            if proc_name.lower().endswith('.exe'):
                proc_name = proc_name[:-4]
            app_name = FRIENDLY_NAMES.get(proc_name, proc_name)
            return app_name, raw_title
    except Exception:
        pass
    return raw_title, raw_title


# ----- Part: Send status


Url = f'{SERVER}/api/device/set'


async def send_status(client: httpx.AsyncClient,
                      using: bool = True, status: str = '',
                      id: str = DEVICE_ID, show_name: str = DEVICE_SHOW_NAME,
                      app_name: str = '', **kwargs):
    json_data = {
        'secret': SECRET,
        'id': id,
        'show_name': show_name,
        'using': using,
        'status': status,
        'app_name': app_name
    }
    resp = await client.post(
        url=Url,
        json=json_data,
        headers={'Content-Type': 'application/json'},
        **kwargs
    )
    return resp


# ----- Part: Shutdown handler


def on_shutdown(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_QUERYENDSESSION:
        print("Received logout event, sending not using...")
        try:
            async def _send():
                async with httpx.AsyncClient(proxy=PROXY or None, timeout=7.5) as client:
                    return await send_status(
                        client=client, using=False, status="要关机了喵",
                        id=DEVICE_ID, show_name=DEVICE_SHOW_NAME
                    )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resp = loop.run_until_complete(_send())
            loop.close()
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Exception: {e}')
        return True
    return 0


wc = win32gui.WNDCLASS()
wc.lpfnWndProc = on_shutdown  # type: ignore
wc.lpszClassName = "ShutdownListener"  # type: ignore
wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore

class_atom = win32gui.RegisterClass(wc)
hwnd = win32gui.CreateWindow(
    class_atom, "Sleepy Shutdown Listener",
    0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
)


def message_loop():
    win32gui.PumpMessages()


message_thread = threading.Thread(target=message_loop, daemon=True)
message_thread.start()

# ----- Part: Mouse idle

last_mouse_pos = win32api.GetCursorPos()
last_mouse_move_time = time.time()


def check_mouse_idle() -> bool:
    """返回 True 表示鼠标静止超时，纯计算函数，不修改全局状态"""
    global last_mouse_pos, last_mouse_move_time
    try:
        current_pos = win32api.GetCursorPos()
    except pywinerror as e:
        print(f'Check mouse pos error: {e}')
        return time.time() - last_mouse_move_time > MOUSE_IDLE_TIME * 60

    current_time = time.time()
    dx = abs(current_pos[0] - last_mouse_pos[0])
    dy = abs(current_pos[1] - last_mouse_pos[1])
    distance_squared = dx * dx + dy * dy
    threshold_squared = MOUSE_MOVE_THRESHOLD * MOUSE_MOVE_THRESHOLD

    if distance_squared > threshold_squared:
        last_mouse_pos = current_pos
        last_mouse_move_time = current_time
        debug(f'Mouse moved > {MOUSE_MOVE_THRESHOLD}px')
        return False

    idle_time = current_time - last_mouse_move_time
    debug(f'Idle time: {idle_time:.1f}s / {MOUSE_IDLE_TIME * 60:.1f}s')
    return idle_time > MOUSE_IDLE_TIME * 60


# ----- Part: Main interval check

is_mouse_idle = False
cached_window_title = ''
last_window = ''
last_app_name = ''
last_media_hash = ''


async def do_update(client: httpx.AsyncClient):
    global last_window, last_app_name, cached_window_title, is_mouse_idle, last_media_hash

    # --- 应用名和窗口标题
    hwnd = win32gui.GetForegroundWindow()
    app_name, raw_title = get_app_info(hwnd)

    if REVERSE_APP_NAME and ' - ' in raw_title:
        current_window = reverse_app_name(raw_title)
    else:
        current_window = raw_title

    mouse_idle_result = check_mouse_idle()
    debug(f'--- App: `{app_name}`, Window: `{current_window}`, idle: {mouse_idle_result}')

    window = current_window
    using = True

    # --- 电池信息
    if BATTERY_INFO_ENABLED:
        battery_percent, battery_status = get_battery_info()
        if battery_percent > 0:
            window = f"[🔋{battery_percent}%{battery_status}] {window}"

    # --- 媒体信息
    prefix_media_info = None
    standalone_media_info = None
    media_hash = ''

    if MEDIA_INFO_ENABLED:
        is_playing, title, artist, album = await get_media_info()
        media_hash = f"{is_playing}{title}{artist}"

        if is_playing and (title or artist):
            if title:
                prefix_media_info = f"[♪{title}]"
            else:
                prefix_media_info = "[♪]"

            parts = []
            if title:
                parts.append(f"♪{title}")
            if artist and artist != title:
                parts.append(artist)
            if album and album != title and album != artist:
                parts.append(album)
            standalone_media_info = " - ".join(parts) if parts else "♪播放中"
            print(f"独立媒体信息: {standalone_media_info}")

    # prefix 模式
    if MEDIA_INFO_ENABLED and prefix_media_info and MEDIA_INFO_MODE == 'prefix':
        window = f"{prefix_media_info} {window}"

    # --- 鼠标空闲状态管理
    prev_idle = is_mouse_idle

    if mouse_idle_result and not prev_idle:
        cached_window_title = current_window
        print(f'Mouse idle: caching window "{cached_window_title[:40]}"')
        using = False
        window = ''
    elif not mouse_idle_result and prev_idle:
        window = cached_window_title
        using = True
        is_mouse_idle = False
        print(f'Mouse active: restoring window "{window[:40]}"')
    elif mouse_idle_result:
        using = False
        window = ''

    is_mouse_idle = mouse_idle_result

    # --- 是否需要发送设备更新
    should_update = (
        mouse_idle_result != prev_idle or
        window != last_window or
        app_name != last_app_name or
        not BYPASS_SAME_REQUEST
    )

    if should_update:
        if current_window in NOT_USING_NAMES:
            using = False
            debug(f'* not using: `{current_window}`')

        if current_window in SKIPPED_NAMES:
            if not (mouse_idle_result != prev_idle):
                debug(f'* in skip list: `{current_window}`, skipped')
                should_update = False
            else:
                debug(f'* in skip list: `{current_window}`, set app name to last window')
                window = last_window

    if should_update:
        print(f'Sending update: app="{app_name}", using={using}, status="{window[:50]}{"..." if len(window)>50 else ""}", idle={mouse_idle_result}')
        try:
            resp = await send_status(
                client=client, using=using, status=window,
                id=DEVICE_ID, show_name=DEVICE_SHOW_NAME,
                app_name=app_name
            )
            debug(f'Response: {resp.status_code}')
            if resp.status_code != 200 and not DEBUG:
                try:
                    print(f'Error! Response: {resp.status_code} - {resp.json()}')
                except Exception:
                    print(f'Error! Response: {resp.status_code}')
            last_window = window
            last_app_name = app_name
        except Exception as e:
            print(f'Error sending update: {e}')
    else:
        debug('No state change, skipping update')

    # --- 媒体信息独立设备上报
    if MEDIA_INFO_ENABLED and MEDIA_INFO_MODE == 'standalone' and media_hash != last_media_hash:
        last_media_hash = media_hash
        try:
            if standalone_media_info:
                print(f'Media update: {standalone_media_info[:50]}')
                media_resp = await send_status(
                    client=client, using=True, status=standalone_media_info,
                    id=MEDIA_DEVICE_ID, show_name=MEDIA_DEVICE_SHOW_NAME
                )
            else:
                media_resp = await send_status(
                    client=client, using=False, status='没有媒体播放',
                    id=MEDIA_DEVICE_ID, show_name=MEDIA_DEVICE_SHOW_NAME
                )
            debug(f'Media Response: {media_resp.status_code}')
        except Exception as e:
            debug(f'Media Info Error: {e}')


# ----- Part: Main


async def main():
    global last_window, last_app_name, is_mouse_idle, cached_window_title, last_media_hash

    client = httpx.AsyncClient(proxy=PROXY or None, timeout=7.5)
    try:
        while True:
            await do_update(client)
            await asyncio.sleep(CHECK_INTERVAL)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError) as e:
        debug(f'Interrupted / Cancelled: {e}')
        try:
            resp = await send_status(
                client=client, using=False, status='未在使用',
                id=DEVICE_ID, show_name=DEVICE_SHOW_NAME
            )
            debug(f'Response: {resp.status_code}')

            if MEDIA_INFO_ENABLED and MEDIA_INFO_MODE == 'standalone':
                media_resp = await send_status(
                    client=client, using=False, status='未在使用',
                    id=MEDIA_DEVICE_ID, show_name=MEDIA_DEVICE_SHOW_NAME
                )
                debug(f'Media Response: {media_resp.status_code}')

            if resp.status_code != 200:
                try:
                    print(f'Error! Response: {resp.status_code} - {resp.json()}')
                except Exception:
                    print(f'Error! Response: {resp.status_code}')
        except Exception as e:
            print(f'Error sending not using: {e}')
        finally:
            print(f'Bye.')
    finally:
        await client.aclose()


if __name__ == '__main__':
    asyncio.run(main())
