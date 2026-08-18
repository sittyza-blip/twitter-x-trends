"""ตัวหลัก: ดึงเทรนด์จาก X (ผ่าน trends24.in) -> ส่งเข้า Telegram

รันครั้งเดียว (เหมาะกับ Task Scheduler):
    python main.py

รันวนทุก 1 ชั่วโมงในตัวเอง:
    python main.py --loop
"""
from __future__ import annotations

import argparse
import configparser
import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from notifier import send_message
from trends import fetch_trends, region_label

# กัน console บน Windows (cp1252) crash เวลา print emoji
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.ini"
STATE_PATH = HERE / "state.json"  # เก็บเทรนด์รอบก่อน ไว้ทำเครื่องหมาย "ใหม่"


def load_settings() -> dict:
    """อ่านค่าตั้งต้น — ใช้ environment variable ก่อน (สำหรับ GitHub Actions/คลาวด์)
    ถ้าไม่มีค่อยตกไปอ่าน config.ini (สำหรับรันบนเครื่องตัวเอง)
    """
    env_token = os.environ.get("BOT_TOKEN")
    env_chat = os.environ.get("CHAT_ID")
    if env_token and env_chat:
        return {
            "bot_token": env_token.strip(),
            "chat_id": env_chat.strip(),
            "regions": os.environ.get("REGIONS", "thailand, worldwide"),
            "top_n": int(os.environ.get("TOP_N", "10")),
        }

    if not CONFIG_PATH.exists():
        sys.exit(
            "❌ ไม่พบ config.ini และไม่มี environment variable BOT_TOKEN/CHAT_ID\n"
            "   บนเครื่องตัวเอง: คัดลอก config.example.ini เป็น config.ini แล้วใส่ค่า\n"
            "   บนคลาวด์: ตั้ง secret BOT_TOKEN กับ CHAT_ID"
        )
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return {
        "bot_token": cfg["telegram"]["bot_token"].strip(),
        "chat_id": cfg["telegram"]["chat_id"].strip(),
        "regions": cfg["settings"].get("regions", "thailand, worldwide"),
        "top_n": cfg["settings"].getint("top_n", fallback=10),
    }


def load_state() -> dict[str, list[str]]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict[str, list[str]]) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _rank_marker(name: str, cur_rank: int, prev_names: list[str]) -> str:
    """คืนเครื่องหมายบอกสถานะอันดับเทียบรอบก่อน: 🆕 / ▲n / ▼n / เท่าเดิม"""
    if name not in prev_names:
        return " 🆕"
    prev_rank = prev_names.index(name) + 1  # อันดับเดิม (1-based)
    diff = prev_rank - cur_rank
    if diff > 0:
        return f" 🔺{diff}"
    if diff < 0:
        return f" 🔻{-diff}"
    return ""


def build_message(
    regions: list[str], top_n: int, prev: dict[str, list[str]]
) -> tuple[str, dict[str, list[str]]]:
    """สร้างข้อความ + คืน state ใหม่ (เก็บเป็นรายชื่อเรียงตามอันดับ) ไว้บันทึก"""
    now = datetime.now().strftime("%d/%m/%Y %H:%M") + " น."
    lines = [f"<b>🔥 เทรนด์ X ล่าสุด</b>  <i>{now}</i>"]
    new_state: dict[str, list[str]] = {}

    for region in regions:
        try:
            trends = fetch_trends(region, top_n=top_n)
        except Exception as exc:  # noqa: BLE001 - อยากให้รอบอื่นทำงานต่อ
            lines.append(f"\n{region_label(region)}\n⚠️ ดึงไม่สำเร็จ: {exc}")
            new_state[region] = prev.get(region, [])
            continue

        new_state[region] = [t["name"] for t in trends]
        prev_names = prev.get(region, [])
        lines.append(f"\n{region_label(region)}")
        if not trends:
            lines.append("(ไม่มีข้อมูล)")
            continue
        for i, t in enumerate(trends, 1):
            marker = _rank_marker(t["name"], i, prev_names)
            name = html.escape(t["name"])
            url = html.escape(t["url"], quote=True)
            # ชื่อเทรนด์เป็นลิงก์กดเปิด X ได้เลย
            link = f'<a href="{url}">{name}</a>' if url else name
            lines.append(f"{i}. {link}{marker}")

    lines.append("\n<i>🔺/🔻 = อันดับขึ้น/ลงจากรอบก่อน · 🆕 = เพิ่งติดเทรนด์</i>")
    return "\n".join(lines), new_state


def run_once(settings: dict) -> None:
    regions = [r.strip() for r in settings["regions"].split(",") if r.strip()]
    top_n = settings["top_n"]

    prev = load_state()
    message, new_state = build_message(regions, top_n, prev)
    send_message(settings["bot_token"], settings["chat_id"], message)
    save_state(new_state)
    print(f"[{datetime.now():%H:%M:%S}] ✅ ส่งแจ้งเตือนแล้ว ({', '.join(regions)})")


def main() -> None:
    parser = argparse.ArgumentParser(description="แจ้งเตือนเทรนด์ X เข้า Telegram")
    parser.add_argument(
        "--loop", action="store_true", help="วนทำงานเองทุก N นาที (ดู --interval)"
    )
    parser.add_argument(
        "--interval", type=int, default=60, help="ระยะห่างเป็นนาที เมื่อใช้ --loop (ค่าเริ่มต้น 60)"
    )
    args = parser.parse_args()

    settings = load_settings()

    if not args.loop:
        run_once(settings)
        return

    print(f"🔁 โหมด loop: ส่งทุก {args.interval} นาที (กด Ctrl+C เพื่อหยุด)")
    while True:
        try:
            run_once(settings)
        except Exception as exc:  # noqa: BLE001 - ไม่ให้ loop ตาย
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ ผิดพลาด: {exc}")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
