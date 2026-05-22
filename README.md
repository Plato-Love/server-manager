# 服务器管家 (Server Manager)

Windows 桌面应用，用于集中管理多台服务器：面板登录、DNS 解析、脚本执行与常用运维操作。

## 功能

- **服务器管理**：分组、备注、一键打开宝塔面板并自动登录
- **DNS 解析**：阿里云、DNSPod、腾讯云解析记录的增删改查
- **DNS 辅助**：服务商识别、剪贴板内容解析、快速解析配置
- **脚本中心**：保存与执行 Python 脚本，按服务器运行并查看实时日志
- **系统集成**：系统托盘、开机自启、无边框窗口、明暗主题

## 环境要求

- Windows 10 / 11
- Python 3.10+（从源码运行时需要）
- Chromium 内核浏览器（用于宝塔自动登录，可在应用设置中指定路径）

## 从源码运行

```powershell
git clone https://github.com/Plato-Love/server-manager.git
cd server-manager
python -m pip install -r requirements.txt
python main.py
```

首次启动会在程序目录下创建 `data/`，用于保存服务器列表、脚本与本地配置。

## 打包

```powershell
.\build_release.ps1
```

输出：`dist\ServerManager\ServerManager.exe`。运行后数据保存在同目录下的 `data/` 文件夹。

## 目录结构

```
server-manager/
├── main.py              # 入口
├── backend/             # 后端逻辑
├── frontend/            # 界面
├── data/                # 本地数据（运行时生成）
├── server-manager.spec  # 打包配置
└── requirements.txt     # 依赖
```

## 技术栈

- [pywebview](https://github.com/r0x0r/pywebview)
- [DrissionPage](https://github.com/g1879/DrissionPage)
- [pystray](https://github.com/moses-palmer/pystray)
- PyInstaller

## 隐私与安全

所有服务器信息、API 密钥与面板凭据均保存在本机 `data/` 目录，不会上传至任何第三方服务。请妥善备份该目录，勿与他人共享。
