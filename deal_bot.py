import requests
from bs4 import BeautifulSoup
import time
import schedule
import logging
import re
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
MIN_DISCOUNT = 70
CHECK_HOURS = [8, 12, 16, 20]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36", "Accept-Language": "es-ES,es;q=0.9"}

@dataclass
class Deal:
    store: str
    name: str
    url: str
    original_price: float
    sale_price: float
    discount_pct: int
    category: str = ""

    def key(self):
        return f"{self.store}::{self.url}"

    def saving(self):
        return self.original_price - self.sale_price

def send_telegram(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")

def get_soup(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"Error cargando {url}: {e}")
        return None

def parse_price(text):
    if not text:
        return None
    text = text.replace("\xa0", " ").strip()
    m = re.search(r"(\d[\d.,]*)\s*€?", text.replace(",", "."))
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except:
            return None
    return None

def calc_discount(original, sale):
    if not original or not sale or original <= 0:
        return 0
    return int(round((1 - sale / original) * 100))

def scrape(store, url, prefix):
    deals = []
    soup = get_soup(url)
    if not soup:
        return deals
    for item in soup.select("[class*='product'], article, [class*='item']")[:30]:
        try:
            name_el = item.select_one("h3, h2, [class*='name'], [class*='title']")
            orig_el = item.select_one("del, s, [class*='original'], [class*='was'], [class*='strike']")
            sale_el = item.select_one("[class*='sale'], [class*='pri
