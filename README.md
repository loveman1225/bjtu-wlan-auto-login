# Campus Net Guard

Campus Net Guard 是一个面向 Windows 的轻量校园网守护脚本。它适合这类场景：电脑连着校园网，人在宿舍、实验室或远程办公时需要它保持在线，但校园网认证会偶尔失效；一旦掉线，远程桌面、SSH、下载任务、同步任务或长时间运行的程序就会中断。这个脚本通过 Windows 任务计划程序定时检查网络状态，在需要认证时自动完成登录。

一个典型的小故事是：你把电脑留在宿舍或实验室跑任务，自己在外面用远程桌面连回来。刚开始一切正常，但校园网半夜把认证注销了，远程连接断开，任务虽然还在本机跑，你却再也连不回去。Campus Net Guard 做的事很朴素：每隔几分钟看一眼网络是否还通，如果发现连着目标校园 Wi-Fi 但已经掉进认证状态，就自动尝试重新登录，让这台机器尽量保持可访问。

目前项目只针对北京交通大学 `web.wlan.bjtu` / BJTU Dr.COM 门户做过实际测试。核心思路可以迁移到其他学校，但登录接口、页面字段、认证流程大概率需要自行适配。

## 功能

- 每 5 分钟由任务计划程序唤起一次，执行后立即退出，不常驻后台
- 只在连接目标 SSID 时工作，避免误操作其他网络
- 通过 Windows 联网检测地址判断是否掉入校园网认证状态
- 优先尝试 Dr.COM 登录接口，失败后启动独立 Edge 窗口并在网页 DOM 中填写账号密码
- 账号密码从本地独立文件读取，不写死在代码里
- 可选管理 Clash Verge，避免代理/VPN 干扰校园网登录

## 为什么有 Clash Verge 选项

有些人平时会开 Clash Verge、VPN 或类似代理工具。校园网认证页面通常在内网或劫持门户里完成，代理规则、TUN 模式、系统代理或残留的代理进程可能会干扰认证请求，导致浏览器打不开登录页、接口请求走错路径，或者登录成功后系统仍判断不可联网。

因此项目提供了 `manage_clash` 开关：

- 开启时，脚本在需要登录前尝试关闭 Clash Verge 主程序，并在登录结束后确保 Clash Verge 主程序重新运行
- 关闭时，脚本完全不检查、不关闭、不启动任何 Clash 相关进程

默认公开模板里是关闭的。只有确实遇到代理干扰校园网登录时，才建议开启。

## 文件

- `campus_net_guard.py`: 主程序
- `campus_net_guard_config.example.json`: 配置模板，适合提交到 GitHub
- `campus_net_guard_config.json`: 本地真实配置，已被 `.gitignore` 排除
- `campus_net_guard_credentials.example.json`: 账号密码模板，适合提交到 GitHub
- `campus_net_guard_credentials.json`: 本地账号密码，已被 `.gitignore` 排除
- `install_task.ps1`: 安装 5 分钟定时任务
- `uninstall_task.ps1`: 删除定时任务

## 初始化

复制配置模板：

```powershell
Copy-Item .\campus_net_guard_config.example.json .\campus_net_guard_config.json
```

复制账号密码模板：

```powershell
Copy-Item .\campus_net_guard_credentials.example.json .\campus_net_guard_credentials.json
```

编辑 `campus_net_guard_credentials.json`：

```json
{
  "username": "你的账号",
  "password": "你的密码"
}
```

也可以用命令写入账号密码：

```powershell
python .\campus_net_guard.py --set-credentials 你的账号 你的密码
```

## 登录 URL

公开模板里的 `login_url` 使用：

```json
"login_url": "http://login.bjtu.edu.cn/"
```

如果你的校园网弹出的登录页能稳定自动跳转，这通常就够用。如果无法打开或自动填表失败，先断开认证状态，连接 `web.wlan.bjtu`，然后访问：

```text
http://neverssl.com
```

浏览器跳到 BJTU 登录页后，把地址栏完整 URL 填入 `campus_net_guard_config.json` 的 `login_url`。这个真实 URL 可能包含 `userip`、`usermac` 等本机参数，所以不要提交到 GitHub。

## Clash Verge 开关

命令行切换：

```powershell
python .\campus_net_guard.py --enable-clash
python .\campus_net_guard.py --disable-clash
```

也可以直接编辑 `campus_net_guard_config.json`：

```json
"manage_clash": true
```

不需要 Clash Verge 管理时改成：

```json
"manage_clash": false
```

如果你的 Clash Verge 不在默认路径，修改：

```json
"clash_executable": "C:\\Program Files\\Clash Verge\\clash-verge.exe"
```

## 测试

手动运行一次：

```powershell
python .\campus_net_guard.py
```

如果已经联网，脚本会很快退出。如果需要认证，正常情况下会看到类似：

```text
BJTU login appears needed
direct portal login did not restore connectivity; trying browser DOM login
browser DOM login appears successful
```

## 安装定时任务

在项目目录中运行：

```powershell
.\install_task.ps1
```

如果 PowerShell 执行策略拦截：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```

任务名是 `CampusNetGuard`，默认每 5 分钟运行一次。

## 查看日志

```powershell
Get-Content .\campus_net_guard.log -Tail 80
```

## 卸载定时任务

```powershell
.\uninstall_task.ps1
```

## 注意

- 这个项目不会绕过校园网认证，只是自动提交你自己的账号密码
- 真实配置、账号密码、日志和浏览器临时配置都不要提交到 GitHub
- Edge DOM 自动登录依赖当前用户桌面会话，建议任务计划程序按默认方式在用户登录后运行
- 任务计划程序绑定脚本路径，移动项目目录后需要重新运行 `install_task.ps1`
