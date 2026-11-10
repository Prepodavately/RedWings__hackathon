"""
Парсер расписаний прямых рейсов конкурентов (requests + BeautifulSoup) с кэшем на диске.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 1 (Data & Parsing)

Два контура работы fetch_competitor_routes(pairs, use_cache):
  use_cache=True  — читает data/raw/schedules_raw.json и фильтрует по парам
                    (сборка и дашборд работают без интернета);
  use_cache=False — ходит на страницы расписаний biletdv.ru
                    https://www.biletdv.ru/raspisanie/avia/<origin_slug>-<dest_slug>.htm,
                    разбирает карточки прямых рейсов (перевозчик, рейсов/нед, own_operator,
                    мин. тариф). Если сайт не ответил — warnings.warn и запись этой пары
                    берётся из локального кэша.

Формат записи (одинаков для кэша и парсера):
  origin_iata, dest_iata, carrier, weekly_flights (int), own_operator (bool — рейсы
  самой Red Wings), week, source (URL страницы), note, min_fare_rub (int или null).
"""

from __future__ import annotations

import json
import re
import time
import warnings
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.parsers.rosstat_loader import RAW_DIR

SCHEDULES_FILE = RAW_DIR / "schedules_raw.json"
REQUIRED_KEYS = {
    "origin_iata", "dest_iata", "carrier", "weekly_flights", "own_operator",
    "week", "source", "note", "min_fare_rub",
}

BASE_URL = "https://www.biletdv.ru/raspisanie/avia/{origin}-{dest}.htm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.8",
}
REQUEST_TIMEOUT = 10
REQUEST_PAUSE_SEC = 0.4

# IATA → slug города на biletdv.ru (12 городов ТЗ)
CITY_SLUG = {
    "KUF": "samara", "GOJ": "nizhny-novgorod", "UFA": "ufa", "KZN": "kazan",
    "MRV": "mineralnye-vody", "PEE": "perm", "SVX": "yekaterinburg", "CEK": "chelyabinsk",
    "TJM": "tyumen", "VOG": "volgograd", "GSV": "saratov", "OMS": "omsk",
}

# Названия перевозчиков на сайте → названия, принятые в schedules_raw.json
CARRIER_ALIASES = {
    "Ред Вингс": "Red Wings", "Red Wings": "Red Wings",
    "ЮВТ АЭРО": "ЮВТ Аэро", "АЗИМУТ": "Азимут", "АЭРОФЛОТ": "Аэрофлот",
    "ГАЗПРОМ АВИА": "Газпром авиа", "АО АТК ЯМАЛ": "Ямал", "Nordwind": "Северный ветер",
    "Северный ветер": "Северный ветер", "ЮТэйр": "Utair",
}
OWN_OPERATOR = "Red Wings"
NO_DIRECT = "нет прямых рейсов"

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7,
    "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


# ----------------------------------------------------------------------------- кэш

def load_schedules() -> pd.DataFrame:
    """Читает schedules_raw.json и проверяет структуру записей."""
    records = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
    if not records:
        raise ValueError(f"{SCHEDULES_FILE.name} пуст: нет данных о рейсах конкурентов")
    bad = [r for r in records if not REQUIRED_KEYS <= set(r)]
    if bad:
        raise ValueError(f"В {SCHEDULES_FILE.name} у записей нет полей: {sorted(REQUIRED_KEYS)}")
    return _to_frame(records)


def _to_frame(records: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=sorted(REQUIRED_KEYS))
    df["origin_iata"] = df["origin_iata"].astype(str)
    df["dest_iata"] = df["dest_iata"].astype(str)
    df["weekly_flights"] = df["weekly_flights"].astype(int)
    df["own_operator"] = df["own_operator"].astype(bool)
    df["min_fare_rub"] = pd.to_numeric(df["min_fare_rub"], errors="coerce")
    return df


def _filter_pairs(df: pd.DataFrame, pairs: List[Tuple[str, str]]) -> pd.DataFrame:
    wanted = set(pairs)
    mask = [(o, d) in wanted for o, d in zip(df["origin_iata"], df["dest_iata"])]
    return df[mask].reset_index(drop=True)


# -------------------------------------------------------------------------- парсинг

def schedule_url(origin: str, dest: str) -> str:
    try:
        return BASE_URL.format(origin=CITY_SLUG[origin], dest=CITY_SLUG[dest])
    except KeyError as e:
        raise ValueError(f"Нет slug для аэропорта {e.args[0]} (CITY_SLUG)") from None


def _parse_week(soup: BeautifulSoup) -> str:
    """«…на неделю с 9 ноября по 15 ноября 2026 года» → «09.11-15.11.2026»."""
    h1 = soup.find("h1")
    text = h1.get_text(" ", strip=True) if h1 else ""
    m = re.search(r"с (\d{1,2}) (\w+) по (\d{1,2}) (\w+) (\d{4})", text)
    if not m:
        return ""
    d1, m1, d2, m2, year = m.groups()
    return f"{int(d1):02d}.{MONTHS_RU.get(m1, 0):02d}-{int(d2):02d}.{MONTHS_RU.get(m2, 0):02d}.{year}"


def _parse_fare(text: str) -> Optional[int]:
    """«Купить от 6 140 ₽» → 6140; «Купить» → None."""
    m = re.search(r"от\s*([\d\s ]+)\s*₽", text)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def _parse_weekly(cell) -> Tuple[int, str]:
    """Число рейсов в неделю и описание дней из блока schedule-info."""
    days = cell.select(".schedule-info .scheduled-day")
    if any(d.get("data-day") == "all" for d in days):
        return 7, "ежедневно"
    names = [d.get_text(strip=True) for d in days]
    return len(names), ", ".join(names)


def parse_schedule_page(html: str, origin: str, dest: str, url: str) -> List[Dict]:
    """Карточки прямых рейсов страницы → записи формата schedules_raw.json."""
    soup = BeautifulSoup(html, "lxml")
    week = _parse_week(soup)
    records: List[Dict] = []
    for cell in soup.select("div.flights-cell"):
        carrier_el = cell.select_one(".flight-logo .op-line")
        flight_el = cell.select_one(".flight-duration .op-line")
        if carrier_el is None or flight_el is None:
            continue
        flight_text = flight_el.get_text(" ", strip=True)
        if "посадк" in flight_text.lower():     # «1 посадка» — рейс не прямой
            continue
        raw_carrier = carrier_el.get_text(strip=True)
        carrier = CARRIER_ALIASES.get(raw_carrier, raw_carrier)
        weekly, days = _parse_weekly(cell)
        if weekly == 0:
            continue
        buy = cell.select_one(".buy-link")
        records.append({
            "origin_iata": origin, "dest_iata": dest, "carrier": carrier,
            "weekly_flights": weekly, "own_operator": carrier == OWN_OPERATOR,
            "week": week, "source": url,
            "note": f"{flight_text}; {days}",
            "min_fare_rub": _parse_fare(buy.get_text(" ", strip=True)) if buy else None,
        })
    if not records:
        records.append({
            "origin_iata": origin, "dest_iata": dest, "carrier": NO_DIRECT,
            "weekly_flights": 0, "own_operator": False, "week": week, "source": url,
            "note": "на странице нет прямых рейсов на неделю", "min_fare_rub": None,
        })
    return records


def scrape_pair(origin: str, dest: str, session: Optional[requests.Session] = None) -> List[Dict]:
    """Один HTTP-запрос к странице пары. Бросает requests.RequestException при сбое сети."""
    url = schedule_url(origin, dest)
    http = session or requests
    resp = http.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return parse_schedule_page(resp.text, origin, dest, url)


# -------------------------------------------------------------------- точка входа

def fetch_competitor_routes(
    pairs: List[Tuple[str, str]], use_cache: bool = True
) -> pd.DataFrame:
    """
    Прямые рейсы конкурентов по парам (origin, dest).

    use_cache=True  — из data/raw/schedules_raw.json (если файла нет — парсинг).
    use_cache=False — живой парсинг biletdv.ru с паузой REQUEST_PAUSE_SEC между запросами;
                      при ошибке сети пара берётся из кэша (с предупреждением).
    """
    cached = load_schedules() if SCHEDULES_FILE.exists() else None
    if use_cache and cached is not None:
        return _filter_pairs(cached, pairs)

    records: List[Dict] = []
    with requests.Session() as session:
        for i, (origin, dest) in enumerate(pairs):
            try:
                records.extend(scrape_pair(origin, dest, session))
            except requests.RequestException as e:
                warnings.warn(f"{origin}-{dest}: сайт не ответил ({e}); беру пару из кэша", stacklevel=2)
                if cached is None:
                    raise
                records.extend(_filter_pairs(cached, [(origin, dest)]).to_dict("records"))
            if i < len(pairs) - 1:
                time.sleep(REQUEST_PAUSE_SEC)
    return _to_frame(records)


def refresh_cache(pairs: List[Tuple[str, str]]) -> pd.DataFrame:
    """Перепарсить пары и перезаписать data/raw/schedules_raw.json. Вызывать вручную."""
    df = fetch_competitor_routes(pairs, use_cache=False)
    out = df.copy()
    out["min_fare_rub"] = out["min_fare_rub"].astype(object).where(out["min_fare_rub"].notna(), None)
    SCHEDULES_FILE.write_text(
        json.dumps(out.to_dict("records"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return df
