import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://v3.football.api-sports.io"
API_KEY = os.environ["API_FOOTBALL_KEY"]

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / "data" / ".request_budget.json"

# Darmowy plan API-Football pozwala na 100 zapytan/dzien (reset o 00:00 UTC).
# Zostawiamy bezpieczny zapas, zeby nigdy przypadkiem nie przekroczyc limitu.
DAILY_SAFETY_LIMIT = 90

# Darmowy plan ma tez limit 10 zapytan/minute. Poprzedni odstep (0.5s) pozwalal
# na 120 zapytan/minute - ponad 12x za duzo - i doprowadzil do automatycznego
# zawieszenia konta przez firewall API-Football ("abnormal traffic spikes").
# 6.5s daje maksymalnie ~9 zapytan/minute, z zapasem ponizej limitu.
REQUEST_INTERVAL_SECONDS = 6.5


def _today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_budget():
    if BUDGET_FILE.exists():
        data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        if data.get("date") == _today_utc():
            return data
    return {"date": _today_utc(), "count": 0}


def _save_budget(data):
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(data), encoding="utf-8")


def get(endpoint, params=None):
    budget = _load_budget()
    if budget["count"] >= DAILY_SAFETY_LIMIT:
        raise RuntimeError(
            f"Osiagnieto bezpieczny limit {DAILY_SAFETY_LIMIT} zapytan na dzisiaj "
            f"(prawdziwy limit planu to 100/dzien, reset o 00:00 UTC). "
            f"Przerywam, uruchom skrypt ponownie jutro - juz pobrane dane zostana w cache."
        )

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={"x-apisports-key": API_KEY},
        params=params or {},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    budget["count"] += 1
    _save_budget(budget)

    remaining = response.headers.get("x-ratelimit-requests-remaining", "?")
    print(f"    [API] {endpoint} {params or ''} -> nasz licznik {budget['count']}/{DAILY_SAFETY_LIMIT}, limit API-Football pokazuje pozostalo: {remaining}")

    if data.get("errors"):
        print(f"    [UWAGA] API zwrocilo blad: {data['errors']}")

    time.sleep(REQUEST_INTERVAL_SECONDS)
    return data
