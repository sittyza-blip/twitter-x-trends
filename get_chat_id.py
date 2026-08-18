"""ตัวช่วยหา chat_id ของคุณ

วิธีใช้:
1. ใส่ bot_token ใน config.ini ให้เรียบร้อยก่อน
2. เปิด Telegram ไปทักบอทของคุณ พิมพ์อะไรก็ได้ส่งไป 1 ข้อความ
3. รัน:  python get_chat_id.py
4. ก็อป chat_id ที่ได้ไปใส่ใน config.ini
"""
from __future__ import annotations

import configparser
import sys
from pathlib import Path

import requests

cfg = configparser.ConfigParser()
cfg_path = Path(__file__).parent / "config.ini"
if not cfg_path.exists():
    sys.exit("❌ ยังไม่มี config.ini — คัดลอกจาก config.example.ini ก่อน")
cfg.read(cfg_path, encoding="utf-8")
token = cfg["telegram"]["bot_token"].strip()

resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
data = resp.json()

if not data.get("ok"):
    sys.exit(f"❌ token ผิดหรือมีปัญหา: {data.get('description', data)}")

updates = data.get("result", [])
if not updates:
    sys.exit(
        "⚠️ ยังไม่เห็นข้อความ — ไปทักบอทใน Telegram (พิมพ์อะไรก็ได้) แล้วรันสคริปต์นี้ใหม่"
    )

seen = {}
for u in updates:
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat", {})
    if chat:
        seen[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name", "")

print("พบ chat ดังนี้ (เอา id ไปใส่ใน config.ini):")
for cid, name in seen.items():
    print(f"  chat_id = {cid}   ({name})")
