# 参与贡献

欢迎通过 Issue 描述问题或通过 Pull Request 提交改进。请提供可复现步骤、操作系统、Python 版本及预期行为，删除日志中的专属 URL、令牌、账号和额度明细。

## 本地验证

项目使用 Python 标准库，无需安装依赖。单元测试通过模拟 Codex RPC、系统音频和网络配置运行，无需 Codex 登录：

```sh
python3 -m unittest discover -s tests -v
```

建议使用 Python 3.10 或更新版本。CI 在 Ubuntu、macOS 和 Python 3.10、3.13 上运行测试。Linux 可验证逻辑与 HTTP 边界；真实闹铃、登录启动和 Bonjour 地址需要在 macOS 验证。请勿在测试中访问真实账号或触发真实闹铃。

涉及行为变化时先添加能复现问题的失败测试，再修改实现。提交前检查测试和 diff，保留独立上游目录的许可证和来源说明。修改局域网接口时验证令牌、Origin、Host、JSON 大小限制和敏感信息脱敏。

使用简洁的 conventional commit 标题，例如 `fix: prevent duplicate alarms`。PR 说明应包括触发场景、行为变化及验证结果。不要提交运行状态、preferences.json、iphone-token、日志、凭据或带令牌的截图。
