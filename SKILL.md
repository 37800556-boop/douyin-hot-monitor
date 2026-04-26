---
name: douyin-hot-monitor
description: 抖音爆款商品监控系统，自动扫描巨量百应平台的商品视频，根据四层关键词词包（primary/expand/explore/exclude）筛选爆款并推送到飞书。当用户提到"抖音监控"、"爆款监控"、"商品监控"、"巨量百应"时触发此skill。
---

# 抖音爆款监控

自动监控抖音巨量百应平台（https://buyin.jinritemai.com）的商品视频，根据四层关键词词包筛选潜在爆款，并将结果推送到飞书。

## 前置条件

1. **浏览器登录**：必须先通过 `browser start profile=openclaw` 启动浏览器，然后 `browser navigate profile=openclaw targetUrl=https://buyin.jinritemai.com/dashboard` 打开巨量百应。首次需手动扫码登录，后续Cookie自动保持。
2. **配置文件**：复制 `config.example.json` 为 `config.json`，填入自己的飞书webhook和关键词。
3. **依赖**：`pip install playwright requests && playwright install chromium`

## 启动监控

```bash
cd <skill目录>
python run.py
```

或直接在代码中调用：

```python
from scripts.douyin_monitor import run
import json

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

common_config = {
    "use_cdp_connect": config.get("use_cdp_connect", True),
    "chrome_remote_debugging_port": config.get("chrome_remote_debugging_port", 18800),
    "chrome_user_data_dir_independent": config.get("chrome_user_data_dir_independent", ""),
    "wait_for_manual_login": config.get("wait_for_manual_login", False),
}

run(config, common_config)
```

## 关键词四层词包

配置在 `config.json` 的 `skills.douyin_monitor.keywords`：

| 层级 | 字段名 | 作用 | 匹配优先级 |
|------|--------|------|-----------|
| 主推词 | `primary` | 直接出现在商品/视频标题中 | 高置信度 🔥 |
| 扩展词 | `expand` | 用户需求/痛点相关词 | 低置信度 |
| 探索词 | `explore` | 新奇/好奇/情绪价值词 | 中置信度 ⭐ |
| 排除词 | `exclude` | 明确不相关的品类词 | 直接排除 |

> 向后兼容：旧版 `target_keywords` 字段仍可工作，会被映射为 `primary` 词。

## 核心配置项

```json
{
  "use_cdp_connect": true,
  "chrome_remote_debugging_port": 18800,
  "wait_for_manual_login": false,
  "skills": {
    "douyin_monitor": {
      "webhook": "飞书机器人webhook",
      "category_list": ["家居日用", "个人护理", "美妆", "运动户外", "3C数码家电"],
      "scroll_times": 20,
      "dedup_hours": 0,
      "keywords": { "primary": [], "expand": [], "explore": [], "exclude": [] }
    }
  }
}
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `webhook` | 飞书机器人webhook URL | 必填 |
| `category_list` | 监控类目列表 | 5个类目 |
| `scroll_times` | 每类目滚动次数 | 20 |
| `dedup_hours` | 去重时间窗口(小时)，0=不去重 | 0 |
| `use_cdp_connect` | 是否通过CDP连接已有浏览器 | true |
| `wait_for_manual_login` | 是否等待手动登录 | false |

## 通知格式

匹配到商品后，同时通过两种方式推送：
- **Webhook**：发送到配置的飞书群机器人
- **飞书API**（可选）：如果配置了 `feishu_global.app_id/app_secret` 和 `chat_id`，同时发送到指定群

推送内容包含：商品名称、视频标题、作者、播放量、点赞量、类目、销售额、成交单量、视频链接。

## 文件结构

```
douyin-hot-monitor/
├── SKILL.md                  # 本文件
├── run.py                    # 入口脚本
├── config.example.json       # 配置模板
├── requirements.txt          # 依赖
└── scripts/
    ├── douyin_monitor.py     # 核心监控逻辑
    └── feishu_base.py        # 飞书API基础模块
```

## 常见问题

**Q: 监控结果为0？**
A: 检查浏览器是否已登录巨量百应。导航到 `https://buyin.jinritemai.com/dashboard` 验证登录状态。

**Q: 类目点击失败？**
A: 巨量百应平台会不定期调整类目名称，更新 `category_list` 中的名称为当前平台实际显示的名称。

**Q: 如何添加定时自动运行？**
A: 使用系统定时任务（crontab/Windows任务计划程序）每天执行 `python run.py`。
