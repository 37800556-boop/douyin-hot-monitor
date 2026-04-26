# -*- coding: utf-8 -*-
"""
飞书多维表格 API 操作模块（共享）
"""

import time
import json
import requests
from typing import Dict, List, Optional


class FeishuDebugger:
    """飞书 Token 调试器"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None

    def get_token(self) -> Optional[str]:
        """获取 tenant_access_token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)

            if resp.status_code != 200:
                print("[飞书API] HTTP状态码非200")
                return None

            data = resp.json()
            if data.get("code") != 0:
                print(f"[飞书API] 认证失败: {data.get('msg')}")
                return None

            self.token = data.get("tenant_access_token")
            return self.token

        except Exception as e:
            print(f"[飞书API] 请求异常: {e}")
            return None


class FeishuBaseClient:
    """飞书多维表格客户端"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        api_base: str = "https://open.feishu.cn"
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.api_base = api_base
        self.tenant_access_token: Optional[str] = None
        self.token_expire_time: float = 0

    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self.tenant_access_token and time.time() < self.token_expire_time - 300:
            return self.tenant_access_token

        url = f"{self.api_base}/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()

        if result.get("code") == 0:
            self.tenant_access_token = result.get("tenant_access_token")
            self.token_expire_time = time.time() + result.get("expire", 7200)
            return self.tenant_access_token
        else:
            raise Exception(f"获取 Token 失败: {result.get('msg')}")

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        token = self.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

    def create_records_batch(
        self,
        fields_map: Dict[str, str],
        data_list: List[Dict],
        batch_size: int = 500
    ) -> Dict[str, int]:
        """批量创建记录"""
        url = f"{self.api_base}/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create"

        success_count = 0
        failed_count = 0

        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]

            records = []
            for data in batch:
                fields = {}
                for column_name, field_key in fields_map.items():
                    value = data.get(field_key, "")
                    if value:
                        if field_key == "likes":
                            try:
                                fields[column_name] = int(value)
                            except (ValueError, TypeError):
                                fields[column_name] = 0
                        else:
                            fields[column_name] = str(value)
                records.append({"fields": fields})

            payload = {"records": records}

            try:
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )

                result = response.json()

                if result.get("code") == 0:
                    created = result.get("data", {}).get("created", len(records))
                    success_count += created
                    failed_count += len(records) - created
                    print(f"[飞书API] 批量写入成功: {created}/{len(records)}")
                else:
                    error_msg = result.get("msg", "未知错误")
                    print(f"[飞书API] 写入失败: {error_msg}")
                    failed_count += len(batch)

                time.sleep(0.5)

            except requests.RequestException as e:
                print(f"[飞书API] 网络失败: {e}")
                failed_count += len(batch)

        return {"success": success_count, "failed": failed_count}


def convert_likes_to_number(likes_str: str) -> int:
    """将点赞数字符串转换为整数"""
    if not likes_str:
        return 0

    likes_str = str(likes_str).strip().replace(",", "")

    if "万" in likes_str:
        try:
            num = float(likes_str.replace("万", "").replace("+", ""))
            return int(num * 10000)
        except ValueError:
            return 0

    if "k" in likes_str.lower():
        try:
            num = float(likes_str.lower().replace("k", "").replace("+", ""))
            return int(num * 1000)
        except ValueError:
            return 0

    try:
        return int(likes_str.replace("+", ""))
    except ValueError:
        return 0
