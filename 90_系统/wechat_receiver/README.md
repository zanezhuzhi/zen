# 公众号测试号回调接收服务

## 启动本地服务

```powershell
cd "D:\==我的学习库==\90_系统\wechat_receiver"
.\run_server.ps1
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
```

## 启动公网隧道

另开一个 PowerShell：

```powershell
cd "D:\==我的学习库==\90_系统\wechat_receiver"
.\run_tunnel.ps1
```

复制输出里的 `https://xxxx.trycloudflare.com`，在微信测试号页面填写。

填写：

```text
URL: https://xxxx.trycloudflare.com/wechat/callback
Token: 与 90_系统/config/wechat.yaml 中的 token 保持一致
```

`JS接口安全域名` 首版留空。

## 入库位置

公众号消息会写入：

```text
D:\==我的学习库==\00_入口收件箱\公众号同步\YYYY-MM-DD.md
```

日志会写入：

```text
D:\==我的学习库==\90_系统\logs\wechat_receiver.log
```
