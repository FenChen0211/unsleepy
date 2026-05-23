# Sleepy Board

> 基于 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy) 二次开发。
> 感谢原项目作者与贡献者。当前仓库保留原项目的 MIT License。

unsleepy 是一个用于 ~~视奸~~ 查看个人在线状态，并**分析你的时间都去哪儿了**的 Flask 应用。既然原项目 sleepy 负责睡着，unsleepy 就负责醒来后的时间追踪。基于 sleepy 二次开发，增加使用统计、应用分类、热力图、年度报告与可选 LLM 分析。


适合用来搭一个私人状态页，或者当作一个轻量的个人时间流记录工具。

## 功能

- **在线状态页**：展示当前手动状态、设备状态、电量、媒体信息等。
- **后台管理面板**：切换状态、管理设备、控制前台卡片、配置个人信息。
- **自定义状态文案**：在后台把状态改成更像 QQ 状态的自定义名称和描述。
- **使用统计**：按今日、本周、本月、本年查看应用使用时长。
- **应用分类**：通过关键词规则把应用自动归到开发、娱乐、工作等分类。
- **热力图与年度报告**：用日历热力图和年度汇总查看长期使用习惯。
- **专注模式**：内置简易番茄钟，记录专注会话。
- **LLM 分析**：可选接入 OpenAI 兼容接口，对使用数据生成简短分析。
- **PWA 支持**：可安装到桌面或手机主屏，支持离线缓存基础资源。
- **多客户端上报**：包含 Windows、Linux、油猴、AutoX.js、Magisk 等示例客户端。

## 快速开始

### 环境要求

- Python 3.10+
- 推荐使用 [uv](https://github.com/astral-sh/uv) 管理依赖

### 本地运行

```bash
git clone https://github.com/FenChen0211/unsleepy
cd sleepy-board

uv sync
uv run python main.py
```

默认监听 `http://localhost:9010`。

如果不用 uv，也可以使用 pip：

```bash
pip install -r requirements.txt
python main.py
```

### Docker 运行

```bash
docker compose up -d --build
```

默认映射端口为 `9010:9010`，数据目录挂载到 `./data`。

## 配置

服务端配置默认从 `data/` 目录读取，支持：

- `data/.env`
- `data/config.yaml`
- `data/config.toml`
- `data/config.json`
- `sleepy_` 前缀的环境变量

最重要的是先设置 `main.secret`，它相当于后台密码和客户端上报密钥。

使用环境变量示例：

```bash
sleepy_main_secret=change_me
sleepy_page_name=YourName
```

Docker Compose 中也可以直接改 `docker-compose.yml` 里的环境变量。

## 客户端

客户端负责把当前设备状态上报到服务端。Windows 客户端示例：

```bash
cd client
copy config.example.json config.json
```

编辑 `client/config.json`：

```json
{
  "server": "http://localhost:9010",
  "secret": "YOUR_SECRET_HERE",
  "device_id": "device-1",
  "device_show_name": "我的电脑",
  "check_interval": 5,
  "mouse_idle_time": 15,
  "media_info_enabled": true
}
```

运行：

```bash
python client/win_device.py
```

> 这些客户端来自原项目 [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy)，本仓库未做修改。

各平台客户端速查：

| 平台 | 脚本 | 说明 |
|------|------|------|
| **Windows** | `win_device.py` | 基础版，需 Python，支持媒体/电池/空闲检测 |
| | `win_device_ds.py` | 增强版，系统托盘 + 异步 HTTP |
| | `Win_Simple/script.py` | 轻量版，可用 PyInstaller 打包 exe，无需 Python |
| | `Sleepy.Powershell.ps1` | 纯 PowerShell，无需 Python |
| **Android** | `autoxjs_device.js` | AutoX.js 常驻循环版，无需 Root |
| | `autoxjs_device_gemini.js` | AutoX.js 亮屏触发版，带去重保护 |
| | `autoxjs_device_once_gemini.js` | AutoX.js 定时任务版，变化时上报 |
| | `magisk/service.sh` | Magisk 模块，需 Root |
| **Linux** | `linux_device_kde.py` | KDE Plasma，需 kdotool |
| | `linux_device_hyprland.sh` | Hyprland，纯 Bash |
| **浏览器** | `browser-script.user.js` | Tampermonkey / Violentmonkey 用户脚本 |
| **其他** | `mc_script.py` | Minecraft 游戏内状态（需 Minescript） |
| | `zhixue.py` | 智学网成绩抓取上报 |

## 常用页面

- `/`：前台状态页
- `/panel`：后台管理面板
- `/stats`：使用统计
- `/stats/annual`：年度报告
- `/api/status/query`：当前状态 API
- `/api/device/set`：客户端设备状态上报 API

## 项目结构

```text
.
├── main.py                 # Flask 服务入口
├── start.py                # 简易守护启动脚本
├── config.py               # 配置加载
├── data.py                 # 数据模型与统计逻辑
├── models.py               # 配置模型
├── plugin.py               # 插件系统
├── admin.py                # Flask-Admin 数据视图
├── public/                 # favicon、manifest、service worker
├── theme/                  # 前台和后台主题模板
├── plugins/                # 内置插件
├── client/                 # 各平台客户端示例
└── data/                   # 本地配置、数据库、缓存，默认不提交
```

## 数据与隐私

默认使用 SQLite，数据保存在 `data/` 目录。这个目录可能包含使用记录、配置和密钥，已经在 `.gitignore` 中排除。

发布公开仓库前，请不要提交：

- `data/`
- `client/config.json`
- 自己打包出来的 `.exe`、`.dmg`、`.zip`
- 任何真实域名密钥、API Key 或个人数据

## 开发检查

```bash
uv run python -m compileall -q .
node --check theme/default/static/panel.js
node --check theme/default/static/modal.js
```

## License

本项目基于 sleepy-project/sleepy 修改，当前仓库使用 [MIT License](./LICENSE)。

如果你继续发布修改版，请保留原项目来源和许可证说明。

## 致谢

- [sleepy-project/sleepy](https://github.com/sleepy-project/sleepy)：原项目
- 原项目作者与贡献者：提供了在线状态页、插件系统和多客户端基础
