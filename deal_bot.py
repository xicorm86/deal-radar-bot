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
            sale_el = item.select_one("[class*='sale'], [class*='price'], [class*='current']")
            link_el = item.select_one("a[href]")
            if not name_el or not link_el:
                continue
            orig = parse_price(orig_el.get_text()) if orig_el else 0
            sale = parse_price(sale_el.get_text()) if sale_el else 0
            if not orig or not sale:
                continue
            pct = calc_discount(orig, sale)
            if pct < MIN_DISCOUNT:
                continue
            href = link_el["href"]
            if not href.startswith("http"):
                href = prefix + href
            deals.append(Deal(store, name_el.get_text(strip=True)[:60], href, orig, sale, pct))
        except:
            continue
    log.info(f"{store}: {len(deals)} ofertas")
    return deals

TIENDAS = [
    ("Zalando Mujer Ropa",    "https://www.zalando.es/ropa-de-mujer/?sale=true",         "https://www.zalando.es"),
    ("Zalando Hombre Ropa",   "https://www.zalando.es/ropa-de-hombre/?sale=true",        "https://www.zalando.es"),
    ("Zalando Mujer Zapatos", "https://www.zalando.es/zapatos-de-mujer/?sale=true",      "https://www.zalando.es"),
    ("Zalando Hombre Zapatos","https://www.zalando.es/zapatos-de-hombre/?sale=true",     "https://www.zalando.es"),
    ("Mango Outlet",          "https://www.mangooutlet.com/es/es/sale",                  "https://www.mangooutlet.com"),
    ("Fifty Outlet",          "https://fiftyoutlet.com/es/es/mujer/sale",                "https://fiftyoutlet.com"),
    ("El Corte Inglés",       "https://www.elcorteingles.es/moda/rebajas/",              "https://www.elcorteingles.es"),
    ("Nike",                  "https://www.nike.com/es/w/sale-3yaep",                    "https://www.nike.com"),
    ("Adidas",                "https://www.adidas.es/sale-calzado",                      "https://www.adidas.es"),
    ("Puma",                  "https://es.puma.com/es/outlet",                           "https://es.puma.com"),
    ("New Balance",           "https://www.newbalance.es/sale/",                         "https://www.newbalance.es"),
    ("Converse",              "https://www.converse.com/es/sale/",                       "https://www.converse.com"),
    ("Levis",                "https://www.levi.com/ES/es_ES/sale",                      "https://www.levi.com"),
    ("Tommy Hilfiger",        "https://www.tommy.com/es/es/outlet",                      "https://www.tommy.com"),
    ("Calvin Klein",          "https://www.calvinklein.es/sale",                         "https://www.calvinklein.es"),
    ("Under Armour",          "https://www.underarmour.com/es-es/c/sale/",               "https://www.underarmour.com"),
    ("Primeriti",             "https://www.primeriti.es/",                               "https://www.primeriti.es"),
    ("Private Sport Shop",    "https://www.privatesportshop.es/",                        "https://www.privatesportshop.es"),
    ("Outletinn",             "https://www.tradeinn.com/outletinn/es",                   "https://www.tradeinn.com"),
    ("ASOS",                  "https://www.asos.com/es/sale/",                           "https://www.asos.com"),
]

sent_deals = set()

def check_and_alert():
    log.info(f"Rastreando — {datetime.now().strftime('%H:%M %d/%m/%Y')}")
    all_deals = []
    for store, url, prefix in TIENDAS:
        try:
            all_deals.extend(scrape(store, url, prefix))
            time.sleep(2)
        except Exception as e:
            log.error(f"Error en {store}: {e}")

    new_deals = [d for d in all_deals if d.key() not in sent_deals]
    for d in new_deals:
        sent_deals.add(d.key())

    if not new_deals:
        send_telegram(f"🔍 Rastreo completado {datetime.now().strftime('%H:%M %d/%m/%Y')}\nSin ofertas nuevas ≥{MIN_DISCOUNT}%.")
        return

    by_store = {}
    for d in new_deals:
        by_store.setdefault(d.store, []).append(d)

    resumen = f"🚨 <b>DEAL RADAR — {datetime.now().strftime('%H:%M %d/%m/%Y')}</b>\n📦 <b>{len(new_deals)} ofertas ≥{MIN_DISCOUNT}%</b> en {len(by_store)} tiendas\n\n"
    resumen += "\n".join(f"• <b>{s}</b>: {len(d)} oferta(s)" for s, d in sorted(by_store.items(), key=lambda x: -len(x[1])))
    send_telegram(resumen)
    time.sleep(1)

    for store, deals in by_store.items():
        top = sorted(deals, key=lambda d: -d.discount_pct)[:5]
        lines = [f"🛍️ <b>{store}</b>\n"]
        for d in top:
            lines.append(f"• <a href='{d.url}'>{d.name}</a> — <b>-{d.discount_pct}%</b> ({d.sale_price:.0f}€ antes {d.original_price:.0f}€)")
        send_telegram("\n".join(lines))
        time.sleep(1)

def main():
    send_telegram(f"🤖 <b>Deal Radar Bot activado</b>\nRastreando <b>{len(TIENDAS)} tiendas</b>\nDescuento mínimo: <b>{MIN_DISCOUNT}%</b>")
    for hour in CHECK_HOURS:
        schedule.every().day.at(f"{hour:02d}:00").do(check_and_alert)
    check_and_alert()
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
