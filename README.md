# แจ้งเตือนเทรนด์ X (Twitter) เข้า Telegram

ดึงเทรนด์ที่กำลังฮิตจาก X ผ่านเว็บรวมเทรนด์ฟรี [trends24.in](https://trends24.in)
(ไทย + ทั่วโลก) แล้วส่งเข้า Telegram ทุก 1 ชั่วโมง

**ในข้อความจะมี:**
- ชื่อเทรนด์แต่ละอันเป็น **ลิงก์กดเปิด X ได้เลย**
- 🆕 = เทรนด์ที่เพิ่งขึ้นใหม่ · 🔺/🔻 = อันดับขึ้น/ลงจากรอบก่อน

มี 2 วิธีใช้งาน — เลือกอย่างใดอย่างหนึ่ง:
- **[แบบคลาวด์](#วิธีที่-2-รันบนคลาวด์ฟรี-ไม่ต้องเปิดคอม-แนะนำ)** (GitHub Actions) — ปิดคอมได้ รันเองทุกชั่วโมง **แนะนำ**
- **[แบบรันบนเครื่องตัวเอง](#วิธีที่-1-รันบนเครื่องตัวเอง)** — ต้องเปิดคอมไว้ / ตั้ง Task Scheduler

---

## เตรียม Telegram (ทำครั้งเดียว ใช้ได้ทั้ง 2 วิธี)

1. เปิด Telegram ทักหา **@BotFather** → พิมพ์ `/newbot` → ตั้งชื่อ → จะได้ **bot token**
2. ไปทักบอทที่เพิ่งสร้าง (พิมพ์อะไรก็ได้ส่งไป 1 ข้อความ)
3. หา **chat id** — วิธีเร็วสุดคือเปิดลิงก์นี้ในเบราว์เซอร์ (แทน `<TOKEN>` ด้วย token ของคุณ):

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

   มองหาเลขในช่อง `"chat":{"id": ... }` — นั่นคือ chat id ของคุณ
   (หรือถ้าตั้ง config.ini แล้ว รัน `python get_chat_id.py` ก็ได้)

---

## วิธีที่ 1: รันบนเครื่องตัวเอง

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> **PowerShell** ต้องมี `.\` นำหน้า path เสมอ · ถ้าใช้ **cmd** ตัด `.\` ออกได้

คัดลอก `config.example.ini` เป็น `config.ini` แล้วใส่ `bot_token` + `chat_id` จากนั้น:

```powershell
# ทดสอบส่ง 1 รอบ
.\.venv\Scripts\python.exe main.py

# รันวนเองทุกชั่วโมง (ต้องเปิดหน้าต่างค้างไว้)
.\.venv\Scripts\python.exe main.py --loop --interval 60
```

**ให้รันอัตโนมัติแม้ปิดหน้าต่าง** — ใช้ Task Scheduler เรียก `run_hourly.bat`:
Create Task → Trigger: Daily + *Repeat every 1 hour* / Indefinitely → Action: เลือก `run_hourly.bat`

---

## วิธีที่ 2: รันบนคลาวด์ฟรี (ไม่ต้องเปิดคอม) — แนะนำ

ใช้ **GitHub Actions** รันให้ทุกชั่วโมงบนเซิร์ฟเวอร์ของ GitHub ฟรี ไม่ต้องมีเซิร์ฟเวอร์เอง

1. สร้าง repo บน GitHub แล้ว push โค้ดนี้ขึ้นไป (ไฟล์ `config.ini` ไม่ถูก push อยู่แล้วเพราะ git-ignore)
2. ไปที่ repo → **Settings → Secrets and variables → Actions**
3. แท็บ **Secrets** → *New repository secret* เพิ่ม 2 อัน:
   - `BOT_TOKEN` = token จาก BotFather
   - `CHAT_ID` = chat id ของคุณ
4. (ไม่บังคับ) แท็บ **Variables** ปรับพื้นที่/จำนวนได้:
   - `REGIONS` เช่น `thailand, worldwide, japan` · `TOP_N` เช่น `10`
5. ไปแท็บ **Actions** → เลือก workflow *"แจ้งเตือนเทรนด์ X เข้า Telegram"* → **Run workflow** เพื่อทดสอบ

เสร็จแล้วมันจะส่งเข้า Telegram ให้เองทุกชั่วโมง (ไฟล์ตั้งเวลาอยู่ที่
[.github/workflows/trends.yml](.github/workflows/trends.yml)) แม้ปิดคอม

> หมายเหตุ: เวลา cron เป็น **UTC** และรอบตามเวลาจริงอาจคลาดจากนาทีที่ตั้งได้เล็กน้อยตามคิวของ GitHub
> · ถ้า repo ไม่มีกิจกรรมเกิน 60 วัน GitHub จะพัก schedule ไว้ (กด Run เองครั้งเดียวก็กลับมาทำงาน)

---

## ปรับแต่ง

- **บนเครื่องตัวเอง:** แก้ในไฟล์ `config.ini` ส่วน `[settings]`
- **บนคลาวด์:** แก้ที่ repository **Variables** (Settings → Secrets and variables → Actions → Variables)

| ตั้งค่า | config.ini | คลาวด์ (Variable) | ความหมาย |
|--------|-----------|------------------|----------|
| พื้นที่ | `regions` | `REGIONS` | slug ของ trends24.in เช่น `thailand, worldwide, japan, united-states` |
| จำนวน | `top_n` | `TOP_N` | เทรนด์สูงสุดต่อพื้นที่ |
| ส่งเฉพาะมีของใหม่ | `only_on_change` | `ONLY_ON_CHANGE` | `true` = ไม่ส่งซ้ำถ้าเทรนด์ไม่เปลี่ยน |
| คำที่ติดตาม | `keywords` | `KEYWORDS` | เช่น `redkiss, blackpink` — ติดเทรนด์เมื่อไรมี 📢 เด้งเน้น |
| ช่วงเงียบ | `quiet_hours` | `QUIET_HOURS` | เวลาไทย เช่น `0-7` = งด 00:00–06:59 (ข้ามเที่ยงคืนได้ เช่น `23-7`) |

(เพิ่มพื้นที่+ธงใหม่ได้ที่ `REGION_LABELS` ใน `trends.py`)

## หมายเหตุ

- ใช้แหล่งฟรี ไม่ต้องมี X API key — ถ้า trends24.in เปลี่ยนโครงสร้าง HTML อาจต้องปรับ selector ใน `trends.py`
- **ไม่มียอดทวีต** — X ซ่อนตัวเลข volume ไว้หลัง tier เสียเงิน และเว็บ aggregator ฟรีก็เลิกโชว์แล้ว
  จึงใช้ **อันดับ + ลูกศรขึ้น/ลง (🔺🔻)** เป็นตัวบอกความแรงแทน
