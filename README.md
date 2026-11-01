# Codex 额度闹钟

macOS 本地小工具：从已登录的 Codex 读取 **5 小时额度窗口的实际重置时间**，到时播放系统提示音并弹出提醒对话框。重置时间由 Codex 提供，不是从启动工具时机械倒数 5 小时。

## 使用

需要 macOS、Python 3（建议 3.10 或以上）和已登录 ChatGPT 账号的 Codex。没有第三方 Python 依赖。

1. 双击 `查看额度.command`，确认能读取下一次重置时间。
2. 双击 `启动闹钟.command`，保持打开的终端窗口运行。
3. 到重置时间，电脑播放提示音并弹窗。按 `Control+C` 停止监测。

首次运行若 macOS 拦截 `.command`，可以在终端进入本文件夹执行下方命令。音量、静音状态与系统对终端的自动化权限可能影响提示；可先运行测试提醒检查。

```sh
python3 alarm.py status
python3 alarm.py run
python3 alarm.py test-alarm
```

默认优先使用 PATH 中的 `codex`，其次使用存在的 `~/.local/bin/codex`，最后尝试 Codex 桌面应用内置路径。可指定其他路径：

```sh
python3 alarm.py status --codex '/Applications/Codex.app/Contents/Resources/codex'
python3 alarm.py run --interval 30
```

## 行为和边界

- 默认每 60 秒读取额度；已记录的重置时间临近时会缩短等待。
- 通过 `codex app-server` 的标准输入输出 RPC 读取 `account/rateLimits/read`；不读取或保存登录凭据，不上传数据。
- 读取失败会重试，已保存的闹钟仍可到时触发。
- 同一重置时间只提醒一次；本机同一状态路径只允许一个监测进程。
- 状态保存在 `~/Library/Application Support/CodexResetAlarm/state.json`。`--state` 可指定其他文件。
- 电脑休眠时不能播放声音；唤醒并恢复运行后会补报已记录且未提醒的重置时间。首次观察到的过期时间不会误报。
- 必须保持程序运行。关闭终端、退出程序或关机后不会在后台自行运行；本项目没有安装开机启动项。
- 优先读取 `codex` 额度桶，避免其他产品的旧重置时间影响提醒；其次读取默认额度桶，均缺失时才选择其他桶中最近的 5 小时重置时间。API key 账号或未提供 5 小时窗口的账号可能无法使用。
- 提醒表示窗口已到重置时间；实际可用额度以 Codex 页面为准。Codex app-server 接口若变更，工具可能需要同步更新。

## 验证

```sh
python3 -m unittest discover -s tests -v
python3 -m trace --count --summary --missing --coverdir /tmp/codex-alarm-coverage --module unittest discover -s tests
```

自动测试覆盖窗口解析、过期首次启动、休眠补报、去重、失败重试、状态保存、模拟 RPC、CLI 和提醒调用。真实声音与系统弹窗需通过 `test-alarm` 在本机验证。

## 持续闹铃与后台状态

闹铃会循环播放，点击“停止闹铃”停止，最多播放 5 分钟。`status` 显示最近心跳、检查、提醒和错误；心跳超过 120 秒显示过期。系统音量仍需开启。

程序会保存接口提供的赠送额度重置次数，后续 `availableCount` 增加时响铃，首次读取不提醒。状态输出包含接口返回的赠送次数及到期字段；接口未提供的未来赠送日期无法预测。

已提供 `安装登录启动.command` 和 `卸载登录启动.command`，仅在用户双击安装后才修改登录项。`python3 launchd_setup.py` 只生成 plist，不安装。安装后通过 `查看额度.command` 查看心跳；日志在 `/tmp/codex-reset-alarm.log` 和 `/tmp/codex-reset-alarm.error.log`。安装前关闭已有终端监测，避免单实例锁冲突。

双击 `试听闹铃.command` 可检查持续响铃和停止按钮。上游独立 CLI 入口为 `node upstream/codex-quota-watcher/src/cli.mjs --help`（需要 Node.js 20+），来源和许可证见 `UPSTREAM.md` 及上游目录。
