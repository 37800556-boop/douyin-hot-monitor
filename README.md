# 抖音爆款监控 (Douyin Hot Monitor)

🔍 自动监控抖音巨量百应平台的商品视频，根据关键词筛选爆款并推送到飞书。

## 功能特点

- ✅ 多类目自动扫描（家居日用、美妆、个护等）
- ✅ 关键词智能匹配
- ✅ 24小时自动去重
- ✅ 飞书实时推送
- ✅ 支持定时自动执行

## 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/你的用户名/douyin-hot-monitor.git
cd douyin-hot-monitor

# 安装依赖
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置

```bash
# 复制示例配置
cp config.example.json config.json

# 编辑配置
nano config.json
```

需要修改的配置：
- `webhook`: 飞书机器人webhook地址
- `category_list`: 监控类目
- `target_keywords`: 监控关键词

### 3. 登录抖音

首次使用需要登录巨量百应平台：

```python
# 使用 OpenClaw 浏览器
browser start profile=openclaw
browser navigate profile=openclaw targetUrl=https://buyin.jinritemai.com/dashboard
```

扫码登录后，后续会自动保持登录状态。

### 4. 运行监控

```bash
python run.py
```

## 配置说明

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `webhook` | string | 飞书机器人webhook地址 |
| `category_list` | array | 监控类目列表 |
| `target_keywords` | array | 监控关键词列表 |
| `scroll_times` | number | 每类目滚动次数 |
| `dedup_hours` | number | 去重时间窗口(小时) |

## 自动化

设置定时任务，每天自动执行：

**Linux/Mac (crontab):**
```bash
0 9 * * * cd /path/to/douyin-hot-monitor && python run.py
```

**Windows (任务计划程序):**
- 创建基本任务
- 设置每天9:00触发
- 操作: 启动程序 `python.exe`
- 参数: `run.py`
- 起始于: 脚本所在目录

## 项目结构

```
douyin-hot-monitor/
├── SKILL.md              # Skill 说明文档
├── README.md             # 项目说明
├── run.py                # 运行脚本
├── config.example.json   # 配置示例
├── requirements.txt      # 依赖列表
└── scripts/
    └── douyin_monitor.py # 核心监控模块
```

## 注意事项

1. 需要抖音电商达人账号才能访问巨量百应平台
2. 首次登录后建议保持浏览器运行，或设置独立profile
3. 监控频率建议每天1-2次，避免过于频繁

## License

MIT License

## 致谢

基于 OpenClaw 和 Playwright 构建
