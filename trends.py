"""ดึงเทรนด์จาก trends24.in (แหล่งรวมเทรนด์ X/Twitter ฟรี)"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://trends24.in"

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


def fetch_trends(region: str, top_n: int = 10, timeout: int = 20) -> list[dict]:
    """คืนเทรนด์ล่าสุดของพื้นที่นั้น (เรียงตามอันดับ)

    แต่ละรายการเป็น dict: {"name": ชื่อเทรนด์, "url": ลิงก์ค้นหาใน X}
    trends24.in แสดงหลาย snapshot ต่อวัน — เราเอาการ์ดใบแรก (ล่าสุดที่สุด)
    """
    resp = requests.get(_region_url(region), headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # หน้าเว็บเป็น UTF-8 แต่ requests เดาผิดในบางหน้า
    soup = BeautifulSoup(resp.text, "html.parser")

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


if __name__ == "__main__":
    # ทดสอบเร็ว ๆ
    for r in ("thailand", "worldwide"):
        print(f"== {region_label(r)} ==")
        for i, t in enumerate(fetch_trends(r), 1):
            print(f"{i}. {t['name']}  ->  {t['url']}")
        print()
