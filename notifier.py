"""ส่งข้อความเข้า Telegram ผ่าน Bot API"""
from __future__ import annotations

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(bot_token: str, chat_id: str, text: str, timeout: int = 20) -> dict:
    """ส่งข้อความ (รองรับ HTML formatting) คืน response ของ Telegram"""
    resp = requests.post(
        API.format(token=bot_token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data.get('description', data)}")
    return data
