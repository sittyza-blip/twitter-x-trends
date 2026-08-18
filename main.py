"""ตัวหลัก: ดึงเทรนด์จาก X (ผ่าน trends24.in) -> ส่งเข้า Telegram

รันครั้งเดียว (เหมาะกับ Task Scheduler):
    python main.py

รันวนทุก 1 ชั่วโมงในตัวเอง:
    python main.py --loop

ส่งสรุปประจำวัน (เรียกจาก workflow แยกวันละครั้ง):
    python main.py --daily
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
STATE_PATH = HERE / "state.json"      # เทรนด์รอบก่อน (ต่อ region) ไว้ทำ 🆕/🔺🔻
HISTORY_PATH = HERE / "history.json"  # นับจำนวนชั่วโมงที่แต่ละเทรนด์ติดในวันนี้
TZ = ZoneInfo("Asia/Bangkok")         # แสดง/คิดเวลาไทยเสมอ (คลาวด์รันด้วย UTC)


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
            "channel_id": os.environ.get("CHANNEL_ID", ""),
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
        "channel_id": s.get("channel_id", ""),
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


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def load_state() -> dict[str, list[str]]:
    return _read_json(STATE_PATH)


def save_state(state: dict[str, list[str]]) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_history(results: dict, now: datetime) -> dict[str, dict[str, int]]:
    """นับ +1 ให้ทุกเทรนด์ที่ติดในรอบนี้ (เฉพาะ region ที่ดึงสำเร็จ)
    รีเซ็ตเมื่อขึ้นวันใหม่. คืน counts ของวันนี้ = {region: {ชื่อ: จำนวนชั่วโมง}}
    """
    today = now.strftime("%Y-%m-%d")
    hist = _read_json(HISTORY_PATH)
    if hist.get("date") != today:
        hist = {"date": today, "counts": {}}
    counts: dict = hist["counts"]
    for region, res in results.items():
        if res["error"]:
            continue
        rc = counts.setdefault(region, {})
        for t in res["trends"]:
            rc[t["name"]] = rc.get(t["name"], 0) + 1
    HISTORY_PATH.write_text(
        json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return counts


def fetch_all(regions: list[str], top_n: int) -> dict:
    """ดึงทุก region คืน {region: {"trends": [...], "error": str|None}}
    ถือว่า "พัง" ถ้า raise exception หรือได้ลิสต์ว่าง (เว็บอาจเปลี่ยนโครงสร้าง)
    """
    results: dict = {}
    for region in regions:
        try:
            trends = fetch_trends(region, top_n=top_n)
            results[region] = {"trends": trends, "error": None if trends else "empty"}
        except Exception as exc:  # noqa: BLE001 - เก็บ error ไว้รายงาน ไม่ให้ทั้งรอบตาย
            results[region] = {"trends": [], "error": str(exc)}
    return results


def _rank_marker(name: str, cur_rank: int, prev_names: list[str]) -> str:
    """เครื่องหมายอันดับเทียบรอบก่อน: 🆕 / 🔺n / 🔻n / เท่าเดิม"""
    if name not in prev_names:
        return " 🆕"
    prev_rank = prev_names.index(name) + 1
    diff = prev_rank - cur_rank
    if diff > 0:
        return f" 🔺{diff}"
    if diff < 0:
        return f" 🔻{-diff}"
    return ""


def build_message(
    results: dict,
    prev: dict[str, list[str]],
    keywords: list[str],
    counts: dict[str, dict[str, int]],
    now: datetime,
) -> tuple[str, dict[str, list[str]], list[str]]:
    """สร้างข้อความจากผลที่ดึงมาแล้ว
    คืน (ข้อความ, state ใหม่, รายชื่อ region ที่ดึงไม่สำเร็จ)
    """
    when = now.strftime("%d/%m/%Y %H:%M") + " น."
    body: list[str] = []
    new_state: dict[str, list[str]] = {}
    hits: list[str] = []
    failed: list[str] = []
    kw_lower = [k.lower() for k in keywords]

    for region, res in results.items():
        if res["error"]:
            failed.append(region)
            new_state[region] = prev.get(region, [])  # คงค่าเดิมไว้
            note = "ดึงไม่ได้ (เว็บอาจเปลี่ยนโครงสร้าง)" if res["error"] == "empty" \
                else f"ดึงไม่สำเร็จ: {res['error']}"
            body.append(f"\n{region_label(region)}\n⚠️ {note}")
            continue

        trends = res["trends"]
        new_state[region] = [t["name"] for t in trends]
        prev_names = prev.get(region, [])
        rc = counts.get(region, {})
        body.append(f"\n{region_label(region)}")
        for i, t in enumerate(trends, 1):
            marker = _rank_marker(t["name"], i, prev_names)
            hours = rc.get(t["name"], 0)
            dur = f" ⏱️{hours}h" if hours >= 2 else ""  # ติดมากี่ชั่วโมงในวันนี้
            name = html.escape(t["name"])
            url = html.escape(t["url"], quote=True)
            is_hit = any(k in t["name"].lower() for k in kw_lower)
            star = " 📢" if is_hit else ""
            link = f'<a href="{url}">{name}</a>' if url else name
            body.append(f"{i}. {link}{marker}{dur}{star}")
            if is_hit:
                hits.append(f"📢 <b>{name}</b> — {region_label(region)} (อันดับ {i})")

    header = [f"<b>🔥 เทรนด์ X ล่าสุด</b>  <i>{when}</i>"]
    if failed and len(failed) == len(results):
        header.append("🚨 <b>ดึงเทรนด์ไม่ได้เลย!</b> — trends24.in อาจเปลี่ยนโครงสร้าง "
                      "หรือเน็ตมีปัญหา ลองเช็ก trends.py")
    elif failed:
        header.append(f"⚠️ บางพื้นที่ดึงไม่ได้: {', '.join(failed)}")
    if hits:
        header.append("\n<b>คำที่คุณติดตามกำลังติดเทรนด์!</b>")
        header.extend(hits)

    legend = "🔺/🔻 = อันดับขึ้น/ลง · 🆕 = เพิ่งติด · ⏱️ = ติดมากี่ชม.วันนี้"
    if keywords:
        legend += " · 📢 = คำที่ติดตาม"
    footer = [f"\n<i>{legend}</i>"]
    return "\n".join(header + body + footer), new_state, failed


def build_daily_summary(now: datetime) -> str | None:
    """สรุปเทรนด์ที่ 'อยู่ยาวสุด' ของวันนี้ จาก history.json (ไม่มีข้อมูล = None)"""
    hist = _read_json(HISTORY_PATH)
    counts = hist.get("counts", {})
    if not counts:
        return None
    date = hist.get("date", now.strftime("%Y-%m-%d"))
    lines = [f"<b>📊 สรุปเทรนด์วันนี้</b>  <i>{date}</i>",
             "<i>เทรนด์ที่ติดยาวนานสุด (นับเป็นชั่วโมง)</i>"]
    for region, rc in counts.items():
        top = sorted(rc.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if not top:
            continue
        lines.append(f"\n{region_label(region)}")
        for i, (name, hours) in enumerate(top, 1):
            lines.append(f"{i}. {html.escape(name)} — ⏱️ {hours} ชม.")
    return "\n".join(lines)


def _broadcast(settings: dict, message: str) -> None:
    """ส่งเข้าแชทเจ้าของ + channel (ถ้าตั้ง CHANNEL_ID ไว้)"""
    send_message(settings["bot_token"], settings["chat_id"], message)
    channel = settings.get("channel_id", "").strip()
    if channel:
        try:
            send_message(settings["bot_token"], channel, message)
        except Exception as exc:  # noqa: BLE001 - channel พังไม่ควรทำให้แชทหลักพัง
            print(f"⚠️ ส่งเข้า channel ไม่ได้: {exc}")


def run_once(settings: dict) -> None:
    regions = _parse_list(settings["regions"])
    keywords = _parse_list(settings.get("keywords", ""))
    top_n = settings["top_n"]
    now = datetime.now(TZ)

    if in_quiet_hours(settings.get("quiet_hours", ""), now):
        print(f"[{now:%H:%M}] 😴 อยู่ในช่วงเงียบ ({settings['quiet_hours']}) — ไม่ส่ง")
        return

    results = fetch_all(regions, top_n)
    counts = update_history(results, now)  # นับรวมชั่วโมงนี้ด้วย
    prev = load_state()
    message, new_state, failed = build_message(results, prev, keywords, counts, now)

    # ปกติไม่ส่งซ้ำถ้าเทรนด์ไม่เปลี่ยน — ยกเว้นมี error (ต้องเตือนเสมอ)
    if (_as_bool(settings.get("only_on_change", "true"))
            and not failed and new_state == prev):
        print(f"[{now:%H:%M}] ⏸️ เทรนด์ไม่เปลี่ยนจากรอบก่อน — ไม่ส่งซ้ำ")
        save_state(new_state)
        return

    _broadcast(settings, message)
    save_state(new_state)
    status = "🚨 แจ้งเตือน scraper" if failed else "✅ ส่งแจ้งเตือน"
    print(f"[{now:%H:%M}] {status} ({', '.join(regions)})")


def run_daily(settings: dict) -> None:
    now = datetime.now(TZ)
    summary = build_daily_summary(now)
    if summary is None:
        print(f"[{now:%H:%M}] ยังไม่มีประวัติวันนี้ — ข้ามสรุป")
        return
    _broadcast(settings, summary)
    print(f"[{now:%H:%M}] 📊 ส่งสรุปประจำวันแล้ว")


def main() -> None:
    parser = argparse.ArgumentParser(description="แจ้งเตือนเทรนด์ X เข้า Telegram")
    parser.add_argument("--loop", action="store_true", help="วนทำงานเองทุก N นาที")
    parser.add_argument("--interval", type=int, default=60, help="นาทีต่อรอบเมื่อใช้ --loop")
    parser.add_argument("--daily", action="store_true", help="ส่งสรุปประจำวันแล้วจบ")
    args = parser.parse_args()

    settings = load_settings()

    if args.daily:
        run_daily(settings)
        return

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
