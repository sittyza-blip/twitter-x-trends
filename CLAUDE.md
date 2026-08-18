# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

บอทดึงเทรนด์ X (Twitter) จากเว็บรวมเทรนด์ฟรี **trends24.in** แล้วส่งแจ้งเตือนเข้า **Telegram**
รายชั่วโมง ไม่ใช้ X API อย่างเป็นทางการ (เลี่ยงค่าใช้จ่าย tier เสียเงิน) — ดึงด้วยการ scrape HTML

## Commands

รันจาก venv เสมอ (`.venv\Scripts\python.exe`) เพราะ deps อยู่ในนั้น:

```bash
# ติดตั้ง deps
.venv\Scripts\python.exe -m pip install -r requirements.txt

# ทดสอบ scraper อย่างเดียว (ไม่ส่ง Telegram) — พิมพ์เทรนด์ออก console
.venv\Scripts\python.exe trends.py

# รันจริง 1 รอบ (ดึง + ส่ง Telegram)
.venv\Scripts\python.exe main.py

# รันวนเองทุก N นาที
.venv\Scripts\python.exe main.py --loop --interval 60

# หา chat_id ของ Telegram
.venv\Scripts\python.exe get_chat_id.py
```

การรันอัตโนมัติมี 2 ทาง: (1) บนเครื่อง — Windows Task Scheduler เรียก `run_hourly.bat`;
(2) บนคลาวด์ — GitHub Actions 2 workflow: [trends.yml](.github/workflows/trends.yml) (cron ราย
ชั่วโมง = ส่งออก) และ [bot.yml](.github/workflows/bot.yml) (cron ทุก 5 นาที = รับคำสั่ง `bot.py`).
bot.yml ต้องให้ repo เป็น **Public** ไม่งั้นเกินโควต้านาทีฟรี (ทุก 5 นาที = ~8,640 รอบ/เดือน)

**PowerShell** ต้องมี `.\` นำหน้า path ของ .exe เสมอ (`.\.venv\Scripts\python.exe`) ไม่งั้นมันตีความ
`.venv` เป็นชื่อ module; cmd ไม่ต้องมี

## Architecture

ไปป์ไลน์ตรงไปตรงมา 3 โมดูล แยกหน้าที่ชัดเจน:

- **[trends.py](trends.py)** — scrape trends24.in. `fetch_trends()` คืน `list[dict]` แต่ละอันมี
  `{"name", "url"}` (url แปลง `twitter.com`→`x.com` แล้ว). จุดเปราะบางที่สุดของโปรเจกต์: HTML ของเว็บ
  ใช้ attribute **ไม่มี quote** (`class=trend-card__list`) และไม่มี wrapper `.trend-card` — ถ้าเว็บ
  เปลี่ยนโครงสร้าง ต้องแก้ selector ที่นี่. หน้าเว็บมีหลาย snapshot ต่อวัน โค้ดจงใจเลือก
  `ol.trend-card__list` **ใบแรก** (ล่าสุดที่สุด). ต้อง force `resp.encoding = "utf-8"` ไม่งั้น
  เทรนด์ภาษาญี่ปุ่น/ไทยในหน้า worldwide จะเป็น mojibake. **ไม่มียอดทวีต** — trends24 ปล่อย
  `data-count` ว่างในทุก snapshot
- **[notifier.py](notifier.py)** — ส่งเข้า Telegram Bot API (`sendMessage`, `parse_mode=HTML`)
- **[bot.py](bot.py)** — รับคำสั่งขาเข้า (`/now`, `/thailand`, `/help`). `poll_once()` ดึง
  `getUpdates` → ตอบ → **acknowledge ด้วย `getUpdates(offset=last+1)`** จึงไม่ต้องเก็บ offset/commit
  (ต่างจาก state.json). ตอบเฉพาะ `chat_id` เจ้าของเท่านั้น. `--serve` = long-poll บนเครื่อง
- **[main.py](main.py)** — orchestrator: อ่าน settings → ดึงทุก region → สร้างข้อความ → ส่ง → บันทึก state

**Config 2 ทาง:** `load_settings()` อ่าน **env var ก่อน** (ใช้บน GitHub Actions) ถ้าไม่มีค่อยตกไป
อ่าน `config.ini` (รันบนเครื่อง) — คืน dict คีย์: `bot_token`, `chat_id`, `regions`, `top_n`,
`keywords`, `quiet_hours`, `only_on_change` (env ชื่อตัวใหญ่ทั้งหมด). อย่าเรียก `load_config` เดิม

**ฟีเจอร์ใน run_once/build_message:**
- `only_on_change` — ถ้า `new_state == prev` (เทรนด์ไม่ขยับ) จะไม่ส่งและไม่ save
- `keywords` — เทียบ substring แบบ case-insensitive; ที่แมตช์ได้ 📢 + ขึ้นหัวข้อเด่นบนสุด
- `quiet_hours` — `in_quiet_hours("start-end")` เทียบ**เวลาไทย** (`TZ = Asia/Bangkok`); รองรับข้าม
  เที่ยงคืน (`23-7`). ต้องมี `tzdata` ใน requirements ไม่งั้น zoneinfo พังบน Windows
- เวลาในข้อความใช้ `datetime.now(TZ)` เสมอ (คลาวด์รัน UTC)

**State / เครื่องหมายอันดับ:** `state.json` เก็บ **รายชื่อเรียงตามอันดับ** ต่อ region.
`_rank_marker()` เทียบชื่อ+ตำแหน่งกับรอบก่อน → 🆕 (ใหม่) / 🔺n (ขึ้น) / 🔻n (ลง). ลบ `state.json`
= รอบถัดไปทุกอันเป็น 🆕. บนคลาวด์ workflow `git add -f state.json` (ไฟล์นี้ถูก git-ignore) แล้ว
commit กลับ เพื่อให้จำอันดับข้ามรอบได้

**การกันพัง:** ถ้า region ใด fetch ไม่สำเร็จ `build_message` จับ exception เฉพาะ region นั้นและทำ
ต่อ region อื่น ส่วน `--loop` จับ exception ทั้งรอบไม่ให้ loop ตาย

## Config & secrets

`config.ini` (git-ignored) ถือ `bot_token` + `chat_id` + `regions` + `top_n` — คัดลอกจาก
`config.example.ini`. `regions` ใช้ slug ตาม URL ของ trends24.in (`thailand`, `worldwide`,
`japan`, ...); ป้ายชื่อ+ธงที่แสดงผลกำหนดใน `REGION_LABELS` ใน [trends.py](trends.py) — เพิ่ม region
ใหม่ควรเพิ่ม label คู่กันด้วย

## Windows notes

- Console เป็น cp1252 → print emoji จะ crash. `main.py` เรียก `sys.stdout.reconfigure(utf-8)`
  ตอนเริ่ม; สคริปต์ทดสอบ ad-hoc ต้องตั้ง `PYTHONUTF8=1` เอง
- ไม่ใช่ git repo
