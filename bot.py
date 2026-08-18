"""รับคำสั่งจาก Telegram แล้วตอบกลับ (แบบเช็คเป็นรอบ ไม่ต้องมีเซิร์ฟเวอร์ตลอด)

กลไก: ใช้ getUpdates ดึงข้อความที่ยังไม่ยืนยัน -> ตอบ -> ยืนยัน (acknowledge)
Telegram จะลบข้อความที่ยืนยันแล้วออกเอง จึงไม่ต้องเก็บ offset ลงไฟล์/commit

รันเช็ก 1 รอบ (ใช้ใน GitHub Actions):
    python bot.py

รันฟังต่อเนื่องบนเครื่องตัวเอง (ตอบทันที):
    python bot.py --serve
"""
from __future__ import annotations

import argparse
import html
import sys
import time
from datetime import datetime

import requests

from main import TZ, load_settings, _parse_list
from notifier import send_message
from trends import REGION_LABELS, fetch_trends, region_label

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

GET_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"

HELP_TEXT = (
    "<b>🤖 คำสั่งที่ใช้ได้</b>\n"
    "/now — ดึงเทรนด์ทุกพื้นที่ที่ตั้งไว้เดี๋ยวนี้\n"
    "/thailand — เฉพาะเทรนด์ไทย\n"
    "/worldwide — เฉพาะเทรนด์ทั่วโลก\n"
    "/&lt;พื้นที่&gt; — เช่น /japan /united-states\n"
    "/help — แสดงคำสั่งทั้งหมด"
)


def get_updates(token: str, offset: int | None = None, timeout: int = 0) -> list[dict]:
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(
        GET_UPDATES.format(token=token), params=params, timeout=timeout + 15
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates error: {data.get('description', data)}")
    return data.get("result", [])


def format_region(region: str, top_n: int) -> str:
    """ดึงเทรนด์พื้นที่เดียวแล้วจัดเป็นข้อความ (ตามคำสั่ง ไม่มี 🆕/🔻)"""
    try:
        trends = fetch_trends(region, top_n=top_n)
    except Exception as exc:  # noqa: BLE001
        return f"{region_label(region)}\n⚠️ ดึงไม่สำเร็จ: {exc}"
    if not trends:
        return f"{region_label(region)}\n(ไม่มีข้อมูล)"
    lines = [region_label(region)]
    for i, t in enumerate(trends, 1):
        name = html.escape(t["name"])
        url = html.escape(t["url"], quote=True)
        link = f'<a href="{url}">{name}</a>' if url else name
        lines.append(f"{i}. {link}")
    return "\n".join(lines)


def handle_command(text: str, settings: dict) -> str | None:
    """แปลข้อความคำสั่ง -> ข้อความตอบกลับ (None = ไม่ต้องตอบ)"""
    text = text.strip()
    if not text.startswith("/"):
        return None
    # ตัด @ชื่อบอท (กรณีใช้ในกลุ่ม เช่น /now@MyBot) และ argument
    cmd = text[1:].split()[0].split("@")[0].lower()

    top_n = settings["top_n"]
    regions = _parse_list(settings["regions"])

    if cmd in ("help", "start"):
        return HELP_TEXT
    if cmd in ("now", "all", "trends"):
        now = datetime.now(TZ).strftime("%d/%m/%Y %H:%M") + " น."
        parts = [f"<b>🔥 เทรนด์ X</b>  <i>{now}</i>"]
        parts += [format_region(r, top_n) for r in regions]
        return "\n\n".join(parts)
    # ชื่อพื้นที่: รับทั้งที่รู้จัก (REGION_LABELS) และที่ตั้งไว้ใน regions
    if cmd in REGION_LABELS or cmd in regions:
        return format_region(cmd, top_n)
    return "❓ ไม่รู้จักคำสั่งนี้\n\n" + HELP_TEXT


def poll_once(settings: dict) -> int:
    """เช็คข้อความใหม่ 1 รอบ ตอบกลับ แล้วยืนยัน คืนจำนวนคำสั่งที่ตอบ"""
    token = settings["bot_token"]
    owner = settings["chat_id"]  # ตอบเฉพาะเจ้าของ (chat_id ที่ตั้งไว้)

    updates = get_updates(token)
    if not updates:
        return 0

    last_id = None
    replied = 0
    for u in updates:
        last_id = u["update_id"]
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        chat_id = str(msg.get("chat", {}).get("id"))
        text = msg.get("text") or ""
        if chat_id != str(owner):
            continue  # ไม่ตอบคนอื่นที่มาทักบอท (กันสแปม/ใช้โควต้ามั่ว)
        reply = handle_command(text, settings)
        if reply:
            send_message(token, chat_id, reply)
            replied += 1

    # ยืนยันว่าอ่านถึง last_id แล้ว -> Telegram จะไม่ส่งซ้ำรอบหน้า
    if last_id is not None:
        get_updates(token, offset=last_id + 1)
    return replied


def main() -> None:
    parser = argparse.ArgumentParser(description="รับคำสั่งเทรนด์จาก Telegram")
    parser.add_argument(
        "--serve", action="store_true", help="ฟังต่อเนื่องบนเครื่องตัวเอง (ตอบทันที)"
    )
    args = parser.parse_args()
    settings = load_settings()

    if not args.serve:
        n = poll_once(settings)
        print(f"[{datetime.now(TZ):%H:%M:%S}] ตอบไป {n} คำสั่ง")
        return

    print("🤖 โหมด serve: กำลังฟังคำสั่ง (กด Ctrl+C เพื่อหยุด)")
    while True:
        try:
            poll_once(settings)
        except Exception as exc:  # noqa: BLE001
            print(f"[{datetime.now(TZ):%H:%M:%S}] ⚠️ ผิดพลาด: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    main()
