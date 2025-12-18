import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import pyairbnb

# ==============================================================================
# CONFIG (phase test: uniquement logs)
# ==============================================================================
CURRENCY = os.environ.get("CURRENCY", "AED")
LANGUAGE = os.environ.get("LANGUAGE", "en")
PROXY_URL = os.environ.get("PROXY_URL", "")
RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", "18"))
MAX_DAYS = int(os.environ.get("MAX_DAYS", "0"))  # 0 = toutes les dates dispo
DELAY_BETWEEN_SEARCHES = float(os.environ.get("DELAY_BETWEEN_SEARCHES", "1.0"))

# ==============================================================================
# URL helpers
# ==============================================================================
def set_dates_in_url(url: str, checkin: str, checkout: str) -> str:
    """
    Injecte checkin/checkout dans l'URL.
    Par défaut: checkin=YYYY-MM-DD & checkout=YYYY-MM-DD
    """
    u = urlparse(url)
    q = parse_qs(u.query)

    # Airbnb utilise très souvent ces clés; si ton URL utilise d'autres noms,
    # on pourra les adapter plus tard après observation.
    q["checkin"] = [checkin]
    q["checkout"] = [checkout]

    new_query = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


# ==============================================================================
# Parsing helpers (best-effort)
# ==============================================================================
def extract_listing_id(item):
    """
    Essaie d’extraire l’ID listing depuis les objets renvoyés par search_all_from_url.
    La structure peut varier; on couvre les variantes courantes.
    """
    if item is None:
        return None
    if isinstance(item, (int, str)):
        return str(item)

    if isinstance(item, dict):
        for k in ("room_id", "listing_id", "id"):
            if k in item and item[k] is not None:
                return str(item[k])

        # variantes imbriquées fréquentes
        for path in (
            ("listing", "id"),
            ("listing", "room_id"),
            ("listing", "listing_id"),
            ("data", "id"),
        ):
            cur = item
            ok = True
            for p in path:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    ok = False
                    break
            if ok and cur is not None:
                return str(cur)

    return None


def find_rank(results_list, target_room_id: str):
    target_room_id = str(target_room_id)
    for i, it in enumerate(results_list or []):
        if extract_listing_id(it) == target_room_id:
            return True, i
    return False, None


def index_to_page_pos(index0: int, per_page: int):
    rank = index0 + 1
    page = (rank - 1) // per_page + 1
    pos = (rank - 1) % per_page + 1
    return rank, page, pos


# ==============================================================================
# Calendar helpers (adapté à ton script prix)
# ==============================================================================
def get_available_days(calendar_data):
    """
    Reprend exactement la logique de ton script prix:
    calendar_data attendu = liste de mois, chaque mois contient "days",
    chaque day contient "calendarDate", "available", "minNights", "maxNights".
    """
    available_days = {}

    if not isinstance(calendar_data, list):
        return available_days

    for month_data in calendar_data:
        if not isinstance(month_data, dict):
            continue

        days = month_data.get("days", [])
        for day in days:
            date_str = day.get("calendarDate", "")
            if date_str:
                available_days[date_str] = {
                    "available": day.get("available", False),
                    "min_nights": day.get("minNights", 1),
                    "max_nights": day.get("maxNights", 365),
                }

    return available_days


# ==============================================================================
# Input logic: GitHub Actions (env) OR local prompts
# ==============================================================================
def read_input_env_or_prompt(env_key: str, prompt: str, required: bool = True) -> str:
    v = os.environ.get(env_key, "").strip()
    if v:
        return v

    v = input(prompt).strip()
    if required and not v:
        raise SystemExit(f"Entrée requise manquante: {env_key}")
    return v


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 80)
    print("🚀 TEST POSITIONNEMENT — pyairbnb 2.1.1 (LOGS ONLY)")
    print("=" * 80)
    print(f"📅 Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Devise: {CURRENCY} | 🌐 Langue: {LANGUAGE} | 📄 results/page: {RESULTS_PER_PAGE}")
    print("=" * 80)

    room_id = read_input_env_or_prompt("ROOM_ID", "RoomID (listing id) : ")
    search_url = read_input_env_or_prompt("SEARCH_URL", "URL de recherche Airbnb : ")

    date_input = read_input_env_or_prompt(
        "DATE_INPUT",
        "Date (YYYY-MM-DD) ou 0 pour auto-calendrier : ",
        required=True,
    )

    # 1) API KEY
    print("\n" + "-" * 80)
    print("📦 Récupération API Key...", end=" ", flush=True)
    api_key = pyairbnb.get_api_key(PROXY_URL)
    print("OK")

    # 2) Construire la liste de tests (checkin, checkout)
    tests = []

    if date_input == "0":
        print("\n📅 Mode auto-calendrier")
        print("📅 Récupération calendrier...", end=" ", flush=True)
        calendar_data = pyairbnb.get_calendar(
            api_key=api_key,
            room_id=str(room_id),
            proxy_url=PROXY_URL,
        )
        print("OK")

        availability = get_available_days(calendar_data)
        available_dates = [d for d, info in availability.items() if info["available"]]

        print(f"📊 Jours disponibles trouvés: {len(available_dates)}")

        if not available_dates:
            print("⚠️ Aucun jour disponible dans le calendrier.")
            return

        if MAX_DAYS > 0:
            available_dates = available_dates[:MAX_DAYS]
            print(f"📊 Limité à MAX_DAYS={MAX_DAYS} → {len(available_dates)} dates testées")

        # Générer (checkin, checkout) en respectant min_nights (comme ton script prix)
        for check_in in available_dates:
            min_nights = availability.get(check_in, {}).get("min_nights", 1)
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
            check_out_date = check_in_date + timedelta(days=min_nights)
            check_out = check_out_date.strftime("%Y-%m-%d")
            tests.append((check_in, check_out, min_nights))

    else:
        # mode manuel: on demande aussi checkout
        check_in = date_input
        check_out = read_input_env_or_prompt("CHECKOUT", "Checkout (YYYY-MM-DD) : ")
        # nights approximatif (log)
        try:
            ci = datetime.strptime(check_in, "%Y-%m-%d").date()
            co = datetime.strptime(check_out, "%Y-%m-%d").date()
            nights = (co - ci).days
        except Exception:
            nights = ""
        tests = [(check_in, check_out, nights)]

    # 3) Run tests
    print("\n" + "=" * 80)
    print(f"🔎 Tests à exécuter: {len(tests)}")
    print("=" * 80)

    for i, (checkin, checkout, nights) in enumerate(tests, 1):
        url_used = set_dates_in_url(search_url, checkin, checkout)

        print("\n" + "-" * 80)
        print(f"🧪 [{i}/{len(tests)}] checkin={checkin} checkout={checkout} nights={nights}")
        print(f"🌐 URL (dates injectées): {url_used}")

        try:
            results = pyairbnb.search_all_from_url(
                url_used,
                currency=CURRENCY,
                language=LANGUAGE,
                proxy_url=PROXY_URL,
                hash="",  # si nécessaire plus tard: fetch_stays_search_hash()
            )

            count = len(results) if results else 0
            found, idx0 = find_rank(results, room_id)

            print(f"📦 Résultats récupérés: {count}")
            if found:
                rank, page, pos = index_to_page_pos(idx0, RESULTS_PER_PAGE)
                print(f"✅ FOUND: room_id={room_id}")
                print(f"🏁 Rank global: {rank} | Page: {page} | Position page: {pos}")
            else:
                print(f"❌ NOT FOUND: room_id={room_id} (dans les résultats récupérés)")

        except Exception as e:
            print(f"❌ Erreur search: {str(e)[:300]}")

        time.sleep(DELAY_BETWEEN_SEARCHES)

    print("\n" + "=" * 80)
    print("🎉 FIN TEST POSITIONNEMENT (aucun CSV généré)")
    print("=" * 80)


if __name__ == "__main__":
    main()
