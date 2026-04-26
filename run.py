#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音爆款监控 - 运行脚本
"""

import sys
import json
import os

# 添加脚本目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from douyin_monitor import run


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
    
    # 公共配置
    common_config = {
        "chrome_user_data_dir": config.get("chrome_user_data_dir", ""),
        "chrome_user_data_dir_independent": config.get("chrome_user_data_dir_independent", ""),
        "use_independent_profile": config.get("use_independent_profile", True),
        "use_cdp_connect": config.get("use_cdp_connect", False),
        "chrome_remote_debugging_port": config.get("chrome_remote_debugging_port", 9222),
        "wait_for_manual_login": config.get("wait_for_manual_login", False),
        "login_wait_time": config.get("login_wait_time", 60),
        "login_mode": config.get("login_mode", "manual"),
    }
    
    try:
        run(config, common_config)
    except Exception as e:
        print(f"[错误] 监控执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
