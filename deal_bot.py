"""
DEAL RADAR BOT — Ropa & Calzado +70% descuento
Alertas automáticas por Telegram
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import schedule
import logging
import re
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
CHAT_ID        = os.environ.get("CHAT_ID", "TU_CHAT_ID_AQUI")
MIN_DISCOUNT   = 70
CHECK_HOURS    = [8, 12, 16, 20]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
}

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

    def emoji(self):
        cat = self.category.lower()
        if "calzado" in cat or "zapato" in cat:
            return "👟"
        if "abrigo" in cat or "chaqueta" in cat:
            return "🧥"
        return "🛍️"

def send_telegram(text: str):
    base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    try:
        r = requests.post(f"{base}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        if not r.ok:
            log.warning(f"Telegram error: {r.text}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")

def send_summary(deals, store_name=""):
    if not deals:
        return
    lines = [
        f"⚡ <b>{store_name.upper()} — {datetime.now().strftime('%H:%M %d/%m/%Y')}</b>\n"
        f"<b>{len(deals)}</b> ofertas con ≥{MIN_DISCOUNT}% dto.\n"
    ]
    for d in deals[:10]:
        lines.append(
            f"{d.emoji()} <a href=\"{d.url}\">{d.name[:45]}</a> "
            f"— <b>-{d.discount_pct}%</b> ({d.sale_price:.0f}€)"
        )
    send_telegram("\n".join(lines))

def get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"get_soup failed [{url}]: {e}")
        return None

def parse_price(text: str) -> Optional[float]:
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

def calc_discount(original: float, sale: float) -> int:
    if not original or not sale or original <= 0:
        return 0
    return int(round((1 - sale / original) * 100))

def scrape_zalando() -> list:
    deals = []
    urls = [
        "https://www.zalando.es/ropa-de-mujer/?sale=true",
        "https://www.zalando.es/ropa-de-hombre/?sale=true",
        "https://www.zalando.es/zapatos-de-mujer/?sale=true",
        "https://www.zalando.es/zapatos-de-hombre/?sale=true",
    ]
    for url in urls:
        soup = get_soup(url)
        if not soup:
            continue
        for article in soup.select("article")[:30]:
            try:
                name_el = article.select_one("h3")
                orig_el = article.select_one("[class*='originalPrice']")
                sale_el = article.select_one("[class*='price']")
                link_el = article.select_one("a[href]")
                if not all([name_el, orig_el, sale_el, link_el]):
                    continue
                orig = parse_price(orig_el.get_text())
                sale = parse_price(sale_el.get_text())
                if not orig or not sale:
                    continue
                pct = calc_discount(orig, sale)
                if pct < MIN_DISCOUNT:
                    continue
                href = link_el["href"]
                if not href.startswith("http"):
                    href = "https://www.zalando.es" + href
                deals.append(Deal("Zalando", name_el.get_text(strip=True), href, orig, sale, pct,
                    "Calzado" if "zapatos" in url else "Ropa"))
            except:
                continue
    log.info(f"Zalando: {len(deals)} ofertas")
    return deals

def scrape_asos() -> list:
    deals = []
    soup = get_soup("https://www.asos.com/es/sale/")
    if not soup:
        return deals
    for article in soup.select("article")[:30]:
        try:
            name_el = article.select_one("a")
            sale_el = article.select_one("[class*='reducedPrice']")
            orig_el = article.select_one("[class*='previousPrice']")
            link_el = article.select_one("a[href]")
            if not (name_el and sale_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text())
            if not sale:
                continue
            pct = calc_discount(orig, sale) if orig else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.asos.com" + href
            deals.append(Deal("ASOS", name_el.get_text(strip=True), href, orig, sale, pct, "Moda"))
        except:
            continue
    log.info(f"ASOS: {len(deals)} ofertas")
    return deals

def scrape_mango_outlet() -> list:
    deals = []
    soup = get_soup("https://www.mangooutlet.com/es/es/sale")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:30]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("[class*='original'], [class*='crossed']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.mangooutlet.com" + href
            deals.append(Deal("Mango Outlet", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa"))
        except:
            continue
    log.info(f"Mango Outlet: {len(deals)} ofertas")
    return deals

def scrape_nike() -> list:
    deals = []
    soup = get_soup("https://www.nike.com/es/w/sale-3yaep")
    if not soup:
        return deals
    for item in soup.select("[class*='product-card']")[:25]:
        try:
            name_el = item.select_one("[class*='title']")
            orig_el = item.select_one("[class*='strikethrough']")
            sale_el = item.select_one("[class*='sale-price'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.nike.com" + href
            deals.append(Deal("Nike", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa/Calzado"))
        except:
            continue
    log.info(f"Nike: {len(deals)} ofertas")
    return deals

def scrape_adidas() -> list:
    deals = []
    soup = get_soup("https://www.adidas.es/sale-calzado")
    if not soup:
        return deals
    for item in soup.select("[class*='product-card']")[:25]:
        try:
            name_el = item.select_one("[class*='title'], h3")
            orig_el = item.select_one("[class*='strikethrough']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.adidas.es" + href
            deals.append(Deal("Adidas", name_el.get_text(strip=True), href, orig, sale, pct, "Calzado"))
        except:
            continue
    log.info(f"Adidas: {len(deals)} ofertas")
    return deals

def scrape_puma() -> list:
    deals = []
    soup = get_soup("https://es.puma.com/es/outlet")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:25]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, s")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://es.puma.com" + href
            deals.append(Deal("Puma", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa/Calzado"))
        except:
            continue
    log.info(f"Puma: {len(deals)} ofertas")
    return deals

def scrape_levis() -> list:
    deals = []
    soup = get_soup("https://www.levi.com/ES/es_ES/sale")
    if not soup:
        return deals
    for item in soup.select("[class*='product'], [class*='tile']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, s, [class*='strike']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.levi.com" + href
            deals.append(Deal("Levi's", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa"))
        except:
            continue
    log.info(f"Levi's: {len(deals)} ofertas")
    return deals

def scrape_new_balance() -> list:
    deals = []
    soup = get_soup("https://www.newbalance.es/sale/")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, s, [class*='was']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.newbalance.es" + href
            deals.append(Deal("New Balance", name_el.get_text(strip=True), href, orig, sale, pct, "Calzado"))
        except:
            continue
    log.info(f"New Balance: {len(deals)} ofertas")
    return deals

def scrape_converse() -> list:
    deals = []
    soup = get_soup("https://www.converse.com/es/sale/")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, s")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.converse.com" + href
            deals.append(Deal("Converse", name_el.get_text(strip=True), href, orig, sale, pct, "Calzado"))
        except:
            continue
    log.info(f"Converse: {len(deals)} ofertas")
    return deals

def scrape_eci() -> list:
    deals = []
    soup = get_soup("https://www.elcorteingles.es/moda/rebajas/")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("[class*='original'], del")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.elcorteingles.es" + href
            deals.append(Deal("El Corte Inglés", name_el.get_text(strip=True), href, orig, sale, pct, "Moda"))
        except:
            continue
    log.info(f"El Corte Inglés: {len(deals)} ofertas")
    return deals

def scrape_fifty_outlet() -> list:
    deals = []
    soup = get_soup("https://fiftyoutlet.com/es/es/mujer/sale")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:25]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, s")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://fiftyoutlet.com" + href
            deals.append(Deal("Fifty Outlet", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa"))
        except:
            continue
    log.info(f"Fifty Outlet: {len(deals)} ofertas")
    return deals

def scrape_privalia() -> list:
    deals = []
    soup = get_soup("https://es.privalia.com/")
    if not soup:
        return deals
    for item in soup.select("[class*='campaign'], [class*='sale']")[:20]:
        try:
            name_el = item.select_one("h2, h3, [class*='title']")
            disc_el = item.select_one("[class*='discount'], [class*='percent']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            pct_text = disc_el.get_text(strip=True) if disc_el else ""
            m = re.search(r"(\d+)", pct_text)
            pct = int(m.group(1)) if m else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://es.privalia.com" + href
            deals.append(Deal("Privalia", name_el.get_text(strip=True), href, 0, 0, pct, "Moda"))
        except:
            continue
    log.info(f"Privalia: {len(deals)} ofertas")
    return deals

def scrape_veepee() -> list:
    deals = []
    soup = get_soup("https://www.veepee.es/")
    if not soup:
        return deals
    for item in soup.select("[class*='brand'], [class*='event']")[:20]:
        try:
            name_el = item.select_one("h2, h3, [class*='title']")
            disc_el = item.select_one("[class*='discount'], [class*='reduction']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            pct_text = disc_el.get_text(strip=True) if disc_el else ""
            m = re.search(r"(\d+)", pct_text)
            pct = int(m.group(1)) if m else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.veepee.es" + href
            deals.append(Deal("Veepee", name_el.get_text(strip=True), href, 0, 0, pct, "Moda"))
        except:
            continue
    log.info(f"Veepee: {len(deals)} ofertas")
    return deals

def scrape_tommy() -> list:
    deals = []
    soup = get_soup("https://www.tommy.com/es/es/outlet")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, [class*='original']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = "https://www.tommy.com" + href
            deals.append(Deal("Tommy Hilfiger", name_el.get_text(strip=True), href, orig, sale, pct, "Ropa"))
        except:
            continue
    log.info(f"Tommy Hilfiger: {len(deals)} ofertas")
    return deals

def scrape_calvin_klein() -> list:
    deals = []
    soup = get_soup("https://www.calvinklein.es/sale")
    if not soup:
        return deals
    for item in soup.select("[class*='product']")[:20]:
        try:
            name_el = item.select_one("[class*='name'], h3")
            orig_el = item.select_one("del, [class*='original']")
            sale_el = item.select_one("[class*='sale'], [class*='price']")
            link_el = item.select_one("a[href]")
            if not (name_el and link_el):
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            pct = calc_discount(orig, sale) if (orig and sale) else 0
            if pct < MIN_DISCOUNT:
        
