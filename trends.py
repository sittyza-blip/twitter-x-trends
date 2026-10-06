"""ดึงเทรนด์จาก trends24.in (แหล่งรวมเทรนด์ X/Twitter ฟรี)"""
from __future__ import annotations

import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://trends24.in"
FALLBACK_URL = "https://getdaytrends.com"  # สำรองเมื่อ trends24 ใช้ไม่ได้

# slug ของแต่ละพื้นที่ -> ชื่อที่อ่านง่ายสำหรับแสดงผล
REGION_LABELS = {
    "worldwide": "🌍 ทั่วโลก",
    "thailand": "🇹🇭 ไทย",
    "united-states": "🇺🇸 สหรัฐฯ",
    "japan": "🇯🇵 ญี่ปุ่น",
    "united-kingdom": "🇬🇧 อังกฤษ",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def region_label(region: str) -> str:
    return REGION_LABELS.get(region, region.replace("-", " ").title())


def _region_url(region: str) -> str:
    if region == "worldwide":
        return BASE_URL + "/"
    return f"{BASE_URL}/{region}/"


def _get_html(url: str, timeout: int, retries: int = 2) -> str:
    """GET พร้อมลองซ้ำ; ถ้าไม่สำเร็จ raise RuntimeError ที่บอก HTTP code จริง"""
    last = "unknown"
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            last = f"{type(exc).__name__}"
        else:
            if resp.status_code == 200:
                resp.encoding = "utf-8"  # requests เดาผิดในบางหน้า
                return resp.text
            last = f"HTTP {resp.status_code}"
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{last} @ {url}")


def _x_search_url(name: str) -> str:
    return "https://x.com/search?q=" + quote(name)


def _parse_trends24(html_text: str, top_n: int) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    # หน้าเว็บมีหลาย snapshot ต่อวัน แต่ละอันคือ <ol class=trend-card__list>
    # ใบแรกคือ snapshot ล่าสุดที่สุด
    card = soup.select_one("ol.trend-card__list")
    if card is None:
        return []
    trends: list[dict] = []
    seen: set[str] = set()
    for a in card.select("a.trend-link"):
        name = a.get_text(strip=True)
        if not name or name in seen:
            continue
        seen.add(name)
        # เว็บลิงก์ไป twitter.com/search — เปลี่ยนเป็น x.com ให้เปิดในแอป X ได้
        url = (a.get("href") or "").replace("twitter.com", "x.com")
        trends.append({"name": name, "url": url})
        if len(trends) >= top_n:
            break
    return trends


def _parse_getdaytrends(html_text: str, top_n: int) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    trends: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("table tbody tr td.main a"):
        name = a.get_text(strip=True)
        if not name or name in seen:
            continue
        seen.add(name)
        trends.append({"name": name, "url": _x_search_url(name)})
        if len(trends) >= top_n:
            break
    return trends


def fetch_trends(region: str, top_n: int = 10, timeout: int = 20) -> list[dict]:
    """คืนเทรนด์ล่าสุดของพื้นที่นั้น (เรียงตามอันดับ)

    แต่ละรายการเป็น dict: {"name": ชื่อเทรนด์, "url": ลิงก์ค้นหาใน X}
    ลอง trends24.in ก่อน ถ้าล้ม (โดนบล็อก IP / เว็บเปลี่ยนโครงสร้าง) ตกไป getdaytrends.com
    ถ้าล้มทั้งคู่ raise RuntimeError ที่รวมสาเหตุของทั้งสองแหล่ง
    """
    sources = (
        ("trends24", _region_url(region), _parse_trends24),
        ("getdaytrends", f"{FALLBACK_URL}/" + ("" if region == "worldwide" else f"{region}/"),
         _parse_getdaytrends),
    )
    errors: list[str] = []
    for label, url, parse in sources:
        try:
            trends = parse(_get_html(url, timeout), top_n)
        except Exception as exc:  # noqa: BLE001 - ลองแหล่งถัดไป
            errors.append(f"{label}: {exc}")
            continue
        if trends:
            return trends
        errors.append(f"{label}: 200 แต่หาเทรนด์ไม่เจอ (โครงสร้างหน้าเปลี่ยน/โดนหน้าบล็อก)")
    raise RuntimeError(" | ".join(errors))


if __name__ == "__main__":
    # ทดสอบเร็ว ๆ
    for r in ("thailand", "worldwide"):
        print(f"== {region_label(r)} ==")
        for i, t in enumerate(fetch_trends(r), 1):
            print(f"{i}. {t['name']}  ->  {t['url']}")
        print()
