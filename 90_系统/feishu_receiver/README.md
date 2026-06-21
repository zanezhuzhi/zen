# 飞书长连接收件箱

这个服务通过飞书开放平台长连接接收 `im.message.receive_v1` 事件，把发给机器人“学习库收件箱”的文本和链接写入 Obsidian。

## 1. 填写密钥

编辑本目录下的 `.env`：

```text
FEISHU_APP_ID=cli_aaa315c0cbb8dbd7
FEISHU_APP_SECRET=从飞书开放平台复制 App Secret
```

不要把 `.env` 发到公开聊天或提交到 Git。

## 2. 飞书后台配置

在飞书开放平台应用里：

1. `添加应用能力 -> 机器人` 已开启。
2. `事件与回调` 选择 `使用 长连接 接收事件` 并保存。
3. 添加事件：`im.message.receive_v1`，中文通常是“接收消息”。
4. 权限管理里至少开通接收消息相关权限；如需机器人回复“已收录”，还要开通发送消息权限。
5. 将自己加入 `测试企业和人员`。

## 3. 启动

```powershell
cd "D:\==我的学习库==\90_系统\feishu_receiver"
.\run_feishu_receiver.ps1
```

收到消息后写入：

```text
D:\==我的学习库==\00_入口收件箱\飞书同步\YYYY-MM-DD.md
```

日志写入：

```text
D:\==我的学习库==\90_系统\logs\feishu_receiver.log
```
