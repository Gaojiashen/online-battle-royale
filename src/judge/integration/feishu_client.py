"""
飞书 BitTable API 客户端 — 读写多维表格

用于法官App向玩家Base写入状态/记录/日志
"""
import os
import httpx
from typing import Dict, List, Any, Optional


class FeishuClient:
    """飞书OpenAPI客户端（BitTable操作）"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self.app_id = os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        self._tenant_token: Optional[str] = None
        self._http: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def _get_tenant_token(self) -> str:
        """获取 tenant_access_token"""
        if self._tenant_token:
            return self._tenant_token

        client = await self._get_client()
        resp = await client.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取tenant_token失败: {data}")

        self._tenant_token = data["tenant_access_token"]
        return self._tenant_token

    async def _headers(self) -> Dict[str, str]:
        token = await self._get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def list_records(self, app_token: str, table_id: str,
                           page_size: int = 100) -> List[Dict]:
        """读取Base表的所有记录"""
        client = await self._get_client()
        headers = await self._headers()

        all_records = []
        page_token = None

        while True:
            params = {
                "page_size": min(page_size, 500),
            }
            if page_token:
                params["page_token"] = page_token

            resp = await client.get(
                f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                headers=headers,
                params=params,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"读取记录失败: {data}")

            items = data.get("data", {}).get("items", [])
            all_records.extend(items)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        return all_records

    async def update_record(self, app_token: str, table_id: str,
                            record_id: str, fields: Dict[str, Any]) -> Dict:
        """更新一条记录"""
        client = await self._get_client()
        headers = await self._headers()

        resp = await client.put(
            f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers=headers,
            json={"fields": fields},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"更新记录失败: {data}")
        return data

    async def add_record(self, app_token: str, table_id: str,
                         fields: Dict[str, Any]) -> Dict:
        """新增一条记录"""
        client = await self._get_client()
        headers = await self._headers()

        resp = await client.post(
            f"{self.BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=headers,
            json={"fields": fields},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"新增记录失败: {data}")
        return data


# 全局单例
feishu_client = FeishuClient()
