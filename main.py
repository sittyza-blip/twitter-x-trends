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
from zoneinfo import ZoneInfo

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
TZ = ZoneInfo("Asia/Bangkok")  # แสดงเวลาไทยเสมอ (คลาวด์รันด้วย UTC)


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
            "keywords": os.environ.get("KEYWORDS", ""),
            "quiet_hours": os.environ.get("QUIET_HOURS", ""),
            "only_on_change": os.environ.get("ONLY_ON_CHANGE", "true"),
        }

    if not CONFIG_PATH.exists():
        sys.exit(
            "❌ ไม่พบ config.ini และไม่มี environment variable BOT_TOKEN/CHAT_ID\n"
            "   บนเครื่องตัวเอง: คัดลอก config.example.ini เป็น config.ini แล้วใส่ค่า\n"
            "   บนคลาวด์: ตั้ง secret BOT_TOKEN กับ CHAT_ID"
        )
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    s = cfg["settings"]
    return {
        "bot_token": cfg["telegram"]["bot_token"].strip(),
        "chat_id": cfg["telegram"]["chat_id"].strip(),
        "regions": s.get("regions", "thailand, worldwide"),
        "top_n": s.getint("top_n", fallback=10),
        "keywords": s.get("keywords", ""),
        "quiet_hours": s.get("quiet_hours", ""),
        "only_on_change": s.get("only_on_change", "true"),
    }


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_list(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def in_quiet_hours(quiet_hours: str, now: datetime) -> bool:
    """quiet_hours รูปแบบ "start-end" เช่น "0-7" (งดส่ง 00:00–06:59 เวลาไทย)
    รองรับข้ามเที่ยงคืน เช่น "22-6". ค่าว่าง = ไม่งดเลย
    """
    quiet_hours = quiet_hours.strip()
    if not quiet_hours or "-" not in quiet_hours:
        return False
    try:
        start, end = (int(x) for x in quiet_hours.split("-", 1))
    except ValueError:
        return False
    h = now.hour
    if start <= end:
        return start <= h < end
    return h >= start or h < end  # ช่วงข้ามเที่ยงคืน


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
    """คืนเครื่องหมายบอกสถานะอันดับเทียบรอบก่อน: 🆕 / 🔺n / 🔻n / เท่าเดิม"""
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
    regions: list[str],
    top_n: int,
    prev: dict[str, list[str]],
    keywords: list[str],
) -> tuple[str, dict[str, list[str]]]:
    """สร้างข้อความ + คืน state ใหม่ (เก็บเป็นรายชื่อเรียงตามอันดับ) ไว้บันทึก"""
    now = datetime.now(TZ).strftime("%d/%m/%Y %H:%M") + " น."
    body: list[str] = []
    new_state: dict[str, list[str]] = {}
    hits: list[str] = []  # เทรนด์ที่ตรง keyword ที่ติดตาม
    kw_lower = [k.lower() for k in keywords]

    for region in regions:
        try:
            trends = fetch_trends(region, top_n=top_n)
        except Exception as exc:  # noqa: BLE001 - อยากให้รอบอื่นทำงานต่อ
            body.append(f"\n{region_label(region)}\n⚠️ ดึงไม่สำเร็จ: {exc}")
            new_state[region] = prev.get(region, [])
            continue

        new_state[region] = [t["name"] for t in trends]
        prev_names = prev.get(region, [])
        body.append(f"\n{region_label(region)}")
        if not trends:
            body.append("(ไม่มีข้อมูล)")
            continue
        for i, t in enumerate(trends, 1):
            marker = _rank_marker(t["name"], i, prev_names)
            name = html.escape(t["name"])
            url = html.escape(t["url"], quote=True)
            is_hit = any(k in t["name"].lower() for k in kw_lower)
            star = " 📢" if is_hit else ""
            link = f'<a href="{url}">{name}</a>' if url else name
            body.append(f"{i}. {link}{marker}{star}")
            if is_hit:
                hits.append(f"📢 <b>{name}</b> — {region_label(region)} (อันดับ {i})")

    header = [f"<b>🔥 เทรนด์ X ล่าสุด</b>  <i>{now}</i>"]
    if hits:
        header.append("\n<b>คำที่คุณติดตามกำลังติดเทรนด์!</b>")
        header.extend(hits)
    footer = ["\n<i>🔺/🔻 = อันดับขึ้น/ลงจากรอบก่อน · 🆕 = เพิ่งติดเทรนด์"
              + (" · 📢 = คำที่ติดตาม" if keywords else "") + "</i>"]
    return "\n".join(header + body + footer), new_state


def run_once(settings: dict) -> None:
    regions = _parse_list(settings["regions"])
    keywords = _parse_list(settings.get("keywords", ""))
    top_n = settings["top_n"]

    now = datetime.now(TZ)
    if in_quiet_hours(settings.get("quiet_hours", ""), now):
        print(f"[{now:%H:%M}] 😴 อยู่ในช่วงเงียบ ({settings['quiet_hours']}) — ไม่ส่ง")
        return

    prev = load_state()
    message, new_state = build_message(regions, top_n, prev, keywords)

    if _as_bool(settings.get("only_on_change", "true")) and new_state == prev:
        print(f"[{now:%H:%M}] ⏸️ เทรนด์ไม่เปลี่ยนจากรอบก่อน — ไม่ส่งซ้ำ")
        return

    send_message(settings["bot_token"], settings["chat_id"], message)
    save_state(new_state)
    print(f"[{now:%H:%M}] ✅ ส่งแจ้งเตือนแล้ว ({', '.join(regions)})")


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
            print(f"[{datetime.now(TZ):%H:%M:%S}] ⚠️ ผิดพลาด: {exc}")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
