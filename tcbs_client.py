"""
tcbs_client.py - Gọi trực tiếp cổng dữ liệu TCBS (tcinvest MCP) từ app Streamlit.

Cấu hình trong .streamlit/secrets.toml (hoặc Secrets trên Streamlit Cloud):

    TCBS_API_TOKEN  = "..."                                   # token cấp bởi TCBS
    TCBS_MCP_URL    = "https://mcp.tcbs.com.vn/mcp/tcinvest"  # (tuỳ chọn) mặc định như trên
    TCBS_AUTH_HEADER = "Authorization"                        # (tuỳ chọn)
    TCBS_AUTH_PREFIX = "Bearer "                              # (tuỳ chọn)

Yêu cầu: pip install mcp
"""
import asyncio
import concurrent.futures
import json

import streamlit as st

DEFAULT_MCP_URL = "https://mcp.tcbs.com.vn/mcp/tcinvest"


class TcbsError(Exception):
    pass


def _config():
    def _get(key, default=""):
        try:
            return st.secrets.get(key, default)
        except Exception:
            return default

    url = _get("TCBS_MCP_URL", DEFAULT_MCP_URL)
    token = _get("TCBS_API_TOKEN", "")
    headers = {}
    if token:
        headers[_get("TCBS_AUTH_HEADER", "Authorization")] = f"{_get('TCBS_AUTH_PREFIX', 'Bearer ')}{token}"
    return url, headers


async def _call_many(calls, url, headers):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    results = []
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, args in calls:
                try:
                    res = await session.call_tool(name, args)
                    text = "".join(c.text for c in res.content if getattr(c, "type", "") == "text")
                    if getattr(res, "isError", False):
                        results.append({"_error": text or "Tool trả về lỗi"})
                    else:
                        results.append(json.loads(text))
                except Exception as e:  # 1 tool lỗi không làm hỏng các tool còn lại
                    results.append({"_error": f"{type(e).__name__}: {e}"})
    return results


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Đang trong event loop (hiếm với Streamlit) -> chạy ở thread riêng
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def call_tools(calls):
    """calls = [(tool_name, {args}), ...] -> list kết quả (dict) theo đúng thứ tự.
    Mỗi phần tử lỗi có dạng {"_error": "..."}. Lỗi kết nối/xác thực -> raise TcbsError."""
    url, headers = _config()
    try:
        return _run(_call_many(calls, url, headers))
    except Exception as e:
        raise TcbsError(
            f"Không kết nối được TCBS ({url}): {type(e).__name__}: {e}. "
            "Kiểm tra TCBS_API_TOKEN / TCBS_MCP_URL trong Secrets."
        ) from e
