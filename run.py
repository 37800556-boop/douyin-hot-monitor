#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音爆款监控 - 运行脚本
"""

import sys
import json
import os

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.douyin_monitor import DouyinMonitor
from playwright.sync_api import sync_playwright


def load_config():
    """加载配置文件"""
    config_paths = [
        "config.json",
        "config/config.json",
        os.path.expanduser("~/.douyin-monitor/config.json")
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    raise FileNotFoundError("找不到配置文件 config.json")


def main():
    print("=" * 60)
    print("抖音爆款监控启动")
    print("=" * 60)
    
    # 加载配置
    config = load_config()
    monitor_config = config.get('skills', {}).get('douyin_monitor', {})
    
    if not monitor_config:
        print("[错误] 配置中找不到 douyin_monitor 配置项")
        return
    
    # 启动监控
    with sync_playwright() as p:
        monitor = DouyinMonitor(monitor_config)
        results = monitor.monitor(p)
        
        print(f"\n{'=' * 60}")
        print(f"监控完成！找到 {len(results)} 个匹配商品")
        print(f"{'=' * 60}")
        
        for item in results:
            print(f"- {item.get('title', '未知标题')}")


if __name__ == "__main__":
    main()
