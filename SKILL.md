---
name: douyin-hot-monitor
description: 抖音爆款商品监控系统，自动扫描巨量百应平台的商品视频，根据关键词筛选爆款并推送到飞书。当用户提到"抖音监控"、"爆款监控"、"商品监控"、"巨量百应"时触发此skill。
---

# 抖音爆款监控 Skill

自动监控抖音巨量百应平台的商品视频，根据关键词筛选潜在爆款，并将结果推送到飞书。

## 功能特点

- 🔍 **多类目监控**：支持家居日用、美妆、个护等多个类目
- 🎯 **关键词匹配**：自定义关键词筛选目标商品
- 🔄 **智能去重**：24小时内重复商品自动过滤
- 📱 **飞书推送**：匹配结果实时推送到飞书群/个人
- 🤖 **自动执行**：支持定时自动运行

## 使用方法

### 1. 安装依赖

```bash
pip install playwright
playwright install chromium
```

### 2. 配置文件

创建 `config.json`：

```json
{
  "use_cdp_connect": true,
  "chrome_remote_debugging_port": 18800,
  "chrome_user_data_dir_independent": "C:\\Users\\你的用户名\\.openclaw\\browser\\openclaw\\user-data",
  "wait_for_manual_login": false,
  "skills": {
    "douyin_monitor": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook地址",
      "target_url": "https://buyin.jinritemai.com/dashboard",
      "category_list": ["家居日用", "个人护理", "美妆", "运动户外", "3C数码家电"],
      "target_keywords": ["塑形", "贴", "矫正"],
      "scroll_times": 12,
      "dedup_hours": 24
    }
  }
}
```

### 3. 启动浏览器（保持登录状态）

```python
# 使用OpenClaw浏览器
browser start profile=openclaw
browser navigate profile=openclaw targetUrl=https://buyin.jinritemai.com/dashboard
```

首次需要手动登录巨量百应平台，之后会自动保持登录状态。

### 4. 运行监控

```python
from scripts.douyin_monitor import run
import json

# 加载配置
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# 运行监控
results = run(config['skills']['douyin_monitor'])
print(f"找到 {len(results)} 个匹配商品")
```

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `webhook` | 飞书机器人webhook地址 | 必填 |
| `category_list` | 监控类目列表 | ["家居日用", "美妆"] |
| `target_keywords` | 监控关键词 | ["塑形", "贴"] |
| `scroll_times` | 每类目滚动次数 | 12 |
| `dedup_hours` | 去重时间窗口(小时) | 24 |

## 平台说明

- **目标平台**：巨量百应达人平台 (https://buyin.jinritemai.com)
- **账号要求**：需要抖音电商达人账号
- **登录方式**：支持二维码扫码登录，一次登录长期有效

## 自动化设置

添加定时任务，每天自动执行：

```bash
# 添加到 crontab (Linux/Mac)
0 9 * * * cd /path/to/skill && python run_monitor.py

# Windows 任务计划程序
# 创建每天9点执行的任务
```

## 依赖项

- Python 3.8+
- playwright
- requests

## License

MIT
