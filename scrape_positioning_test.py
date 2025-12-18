#!/usr/bin/env python3
"""
=============================================================================
SCRAPE POSITIONING TEST - Version corrigée
=============================================================================
- Utilise le placeId extrait de l'URL (au lieu de coordonnées)
- Prend 3 dates disponibles par mois pour les 3 prochains mois
=============================================================================
"""

import os
import re
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from collections import defaultdict

from curl_cffi import requests

# ==============================================================================
# CONFIG
# ==============================================================================
CURRENCY = os.environ.get("CURRENCY", "AED")
LANGUAGE = os.environ.get("LANGUAGE", "en")
PROXY_URL = os.environ.get("PROXY_URL", "")
RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", "18"))
MAX_DAYS = int(os.environ.get("MAX_DAYS", "0"))  # 0 = utiliser la logique 3 dates x 3 mois
DATES_PER_MONTH = int(os.environ.get("DATES_PER_MONTH", "3"))
MONTHS_TO_CHECK = int(os.environ.get("MONTHS_TO_CHECK", "3"))
DELAY_BETWEEN_SEARCHES = float(os.environ.get("DELAY_BETWEEN_SEARCHES", "1.5"))

# Headers Chrome
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TREATMENT_FLAGS = [
    "feed_map_decouple_m11_treatment",
    "stays_search_rehydration_treatment_desktop",
    "stays_search_rehydration_treatment_moweb",
]


# ==============================================================================
# API KEY
# ==============================================================================
def get_api_key(proxy_url=""):
    """Récupère la clé API depuis la page Airbnb"""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    response = requests.get(
        "https://www.airbnb.com/",
        headers=HEADERS,
        proxies=proxies,
        impersonate="chrome124",
        timeout=30
    )
    response.raise_for_status()
    
    match = re.search(r'"key":"([^"]+)"', response.text)
    if match:
        return match.group(1)
    
    raise Exception("API Key non trouvée")


# ==============================================================================
# CALENDAR (réutilise pyairbnb)
# ==============================================================================
def get_calendar(api_key, room_id, proxy_url=""):
    """Récupère le calendrier d'un listing"""
    import pyairbnb
    return pyairbnb.get_calendar(api_key=api_key, room_id=str(room_id), proxy_url=proxy_url)


def get_available_days(calendar_data):
    """Extrait les jours disponibles du calendrier"""
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


def select_dates_per_month(availability, dates_per_month=3, months_to_check=3):
    """
    Sélectionne X dates disponibles pour chacun des Y prochains mois.
    
    Args:
        availability: dict {date_str: {available, min_nights, max_nights}}
        dates_per_month: nombre de dates à prendre par mois
        months_to_check: nombre de mois à vérifier
    
    Returns:
        list of (check_in, check_out, min_nights)
    """
    today = datetime.now().date()
    current_month = today.month
    current_year = today.year
    
    # Organiser les dates disponibles par mois
    dates_by_month = defaultdict(list)
    
    for date_str, info in availability.items():
        if not info.get("available", False):
            continue
        
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            continue
        
        # Ignorer les dates passées
        if date_obj <= today:
            continue
        
        month_key = (date_obj.year, date_obj.month)
        dates_by_month[month_key].append((date_str, info))
    
    # Déterminer les 3 prochains mois
    target_months = []
    month = current_month
    year = current_year
    
    for _ in range(months_to_check):
        month += 1
        if month > 12:
            month = 1
            year += 1
        target_months.append((year, month))
    
    # Sélectionner X dates par mois
    selected_tests = []
    
    for month_key in target_months:
        month_dates = dates_by_month.get(month_key, [])
        
        # Trier par date
        month_dates.sort(key=lambda x: x[0])
        
        # Prendre les X premières dates disponibles
        for date_str, info in month_dates[:dates_per_month]:
            min_nights = info.get("min_nights", 1)
            check_in_date = datetime.strptime(date_str, "%Y-%m-%d")
            check_out_date = check_in_date + timedelta(days=min_nights)
            check_out = check_out_date.strftime("%Y-%m-%d")
            
            selected_tests.append((date_str, check_out, min_nights))
    
    return selected_tests


# ==============================================================================
# URL PARSING
# ==============================================================================
def extract_search_params_from_url(url):
    """
    Extrait les paramètres de recherche depuis une URL Airbnb.
    Retourne: dict avec placeId, query, etc.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    params = {
        "place_id": qs.get("place_id", [None])[0],
        "query": qs.get("query", [None])[0],
        "checkin": qs.get("checkin", [None])[0],
        "checkout": qs.get("checkout", [None])[0],
        "ne_lat": qs.get("ne_lat", [None])[0],
        "ne_lng": qs.get("ne_lng", [None])[0],
        "sw_lat": qs.get("sw_lat", [None])[0],
        "sw_lng": qs.get("sw_lng", [None])[0],
    }
    
    # Décoder le query si présent
    if params["query"]:
        params["query"] = unquote(params["query"])
    
    return params


# ==============================================================================
# RECHERCHE AIRBNB (avec placeId)
# ==============================================================================
def search_airbnb(api_key, place_id, query, check_in, check_out, cursor="", proxy_url=""):
    """
    Effectue une recherche Airbnb en utilisant le placeId.
    Retourne tous les résultats (pagination automatique).
    """
    
    operation_id = '9f945886dcc032b9ef4ba770d9132eb0aa78053296b5405483944c229617b00b'
    base_url = f"https://www.airbnb.com/api/v3/StaysSearch/{operation_id}"
    url = f"{base_url}?operationName=StaysSearch&locale={LANGUAGE}&currency={CURRENCY}"
    
    try:
        nights = (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days
    except:
        nights = 1
    
    all_listings = []
    page_cursor = cursor
    page_count = 0
    max_pages = 20  # Sécurité
    
    while page_count < max_pages:
        page_count += 1
        
        raw_params = [
            {"filterName": "cdnCacheSafe", "filterValues": ["false"]},
            {"filterName": "channel", "filterValues": ["EXPLORE"]},
            {"filterName": "checkin", "filterValues": [check_in]},
            {"filterName": "checkout", "filterValues": [check_out]},
            {"filterName": "datePickerType", "filterValues": ["calendar"]},
            {"filterName": "flexibleTripLengths", "filterValues": ["one_week"]},
            {"filterName": "itemsPerGrid", "filterValues": ["50"]},
            {"filterName": "placeId", "filterValues": [place_id]},
            {"filterName": "query", "filterValues": [query or ""]},
            {"filterName": "priceFilterInputType", "filterValues": ["0"]},
            {"filterName": "priceFilterNumNights", "filterValues": [str(nights)]},
            {"filterName": "refinementPaths", "filterValues": ["/homes"]},
            {"filterName": "screenSize", "filterValues": ["large"]},
            {"filterName": "searchByMap", "filterValues": ["false"]},
            {"filterName": "tabId", "filterValues": ["home_tab"]},
            {"filterName": "version", "filterValues": ["1.8.3"]},
        ]
        
        input_data = {
            "operationName": "StaysSearch",
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": operation_id,
                },
            },
            "variables": {
                "staysSearchRequest": {
                    "cursor": page_cursor,
                    "maxMapItems": 9999,
                    "requestedPageType": "STAYS_SEARCH",
                    "metadataOnly": False,
                    "source": "structured_search_input_header",
                    "searchType": "filter_change",
                    "treatmentFlags": TREATMENT_FLAGS,
                    "rawParams": raw_params,
                },
                "staysMapSearchRequestV2": {
                    "cursor": page_cursor,
                    "requestedPageType": "STAYS_SEARCH",
                    "metadataOnly": False,
                    "source": "structured_search_input_header",
                    "searchType": "filter_change",
                    "treatmentFlags": TREATMENT_FLAGS,
                    "rawParams": raw_params,
                },
                "includeMapResults": True,
                "isLeanTreatment": False,
            },
        }
        
        headers = HEADERS.copy()
        headers["X-Airbnb-Api-Key"] = api_key
        
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        
        response = requests.post(
            url,
            json=input_data,
            headers=headers,
            proxies=proxies,
            impersonate="chrome124",
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"      ⚠️ Erreur API: {response.status_code}")
            break
        
        data = response.json()
        
        # Extraire les listings de cette page
        search_results = (data.get("data", {})
                         .get("presentation", {})
                         .get("staysSearch", {})
                         .get("results", {})
                         .get("searchResults", []))
        
        for item in search_results:
            listing = item.get("listing", {})
            listing_id = listing.get("id", "")
            
            if isinstance(listing_id, str) and "StayListing:" in listing_id:
                listing_id = listing_id.replace("StayListing:", "")
            
            if listing_id:
                all_listings.append({
                    "id": str(listing_id),
                    "name": listing.get("name", "")[:50],
                })
        
        # Vérifier pagination
        pagination = (data.get("data", {})
                     .get("presentation", {})
                     .get("staysSearch", {})
                     .get("results", {})
                     .get("paginationInfo", {}))
        
        next_cursor = pagination.get("nextPageCursor")
        
        if not next_cursor or not search_results:
            break
        
        page_cursor = next_cursor
        time.sleep(0.5)  # Petit délai entre les pages
    
    return all_listings


# ==============================================================================
# POSITION FINDING
# ==============================================================================
def find_position(listings, room_id):
    """Trouve la position d'un listing dans les résultats"""
    room_id = str(room_id)
    
    for i, listing in enumerate(listings):
        if str(listing.get("id", "")) == room_id:
            rank = i + 1
            page = (rank - 1) // RESULTS_PER_PAGE + 1
            pos_on_page = (rank - 1) % RESULTS_PER_PAGE + 1
            return True, rank, page, pos_on_page
    
    return False, None, None, None


# ==============================================================================
# INPUT
# ==============================================================================
def read_input(env_key, prompt, required=True):
    """Lit une entrée depuis env ou stdin"""
    v = os.environ.get(env_key, "").strip()
    if v:
        return v
    
    v = input(prompt).strip()
    if required and not v:
        raise SystemExit(f"Entrée requise: {env_key}")
    return v


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 80)
    print("🚀 TEST POSITIONNEMENT — Version corrigée (placeId)")
    print("=" * 80)
    print(f"📅 Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Devise: {CURRENCY} | 🌐 Langue: {LANGUAGE}")
    print(f"📊 Config: {DATES_PER_MONTH} dates/mois × {MONTHS_TO_CHECK} mois")
    print("=" * 80)
    
    # Inputs
    room_id = read_input("ROOM_ID", "RoomID (listing id) : ")
    search_url = read_input("SEARCH_URL", "URL de recherche Airbnb : ")
    date_input = read_input("DATE_INPUT", "Date (YYYY-MM-DD) ou 0 pour auto-calendrier : ")
    
    # Extraire placeId et query de l'URL
    print("\n" + "-" * 80)
    print("📍 Extraction paramètres URL...")
    url_params = extract_search_params_from_url(search_url)
    
    place_id = url_params.get("place_id")
    query = url_params.get("query", "")
    
    if not place_id:
        print("❌ ERREUR: place_id non trouvé dans l'URL!")
        print(f"   URL analysée: {search_url[:100]}...")
        print("   Paramètres trouvés:", url_params)
        return
    
    print(f"   ✅ place_id: {place_id}")
    print(f"   ✅ query: {query}")
    
    # API Key
    print("\n📦 Récupération API Key...", end=" ", flush=True)
    api_key = get_api_key(PROXY_URL)
    print("OK")
    
    # Construire la liste de tests
    tests = []
    
    if date_input == "0":
        print("\n📅 Mode auto-calendrier")
        print("📅 Récupération calendrier...", end=" ", flush=True)
        calendar_data = get_calendar(api_key, room_id, PROXY_URL)
        print("OK")
        
        availability = get_available_days(calendar_data)
        available_count = sum(1 for d, info in availability.items() if info["available"])
        print(f"📊 Jours disponibles total: {available_count}")
        
        if available_count == 0:
            print("⚠️ Aucun jour disponible!")
            return
        
        # Sélection: 3 dates par mois pour 3 mois
        if MAX_DAYS > 0:
            # Mode legacy: prendre les X premières dates
            available_dates = [d for d, info in sorted(availability.items()) if info["available"]]
            available_dates = available_dates[:MAX_DAYS]
            for check_in in available_dates:
                min_nights = availability[check_in].get("min_nights", 1)
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
                check_out_date = check_in_date + timedelta(days=min_nights)
                tests.append((check_in, check_out_date.strftime("%Y-%m-%d"), min_nights))
            print(f"📊 Mode MAX_DAYS: {len(tests)} dates sélectionnées")
        else:
            # Nouvelle logique: X dates par mois pour Y mois
            tests = select_dates_per_month(availability, DATES_PER_MONTH, MONTHS_TO_CHECK)
            print(f"📊 Sélection: {len(tests)} dates ({DATES_PER_MONTH}/mois × {MONTHS_TO_CHECK} mois)")
        
        if tests:
            print("\n📋 Dates sélectionnées:")
            for i, (ci, co, n) in enumerate(tests, 1):
                print(f"   {i}. {ci} → {co} ({n} nuit(s))")
    
    else:
        # Mode manuel
        check_in = date_input
        check_out = read_input("CHECKOUT", "Checkout (YYYY-MM-DD) : ")
        try:
            nights = (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days
        except:
            nights = 1
        tests = [(check_in, check_out, nights)]
    
    if not tests:
        print("❌ Aucune date à tester!")
        return
    
    # Exécution des tests
    print("\n" + "=" * 80)
    print(f"🔎 Tests à exécuter: {len(tests)}")
    print("=" * 80)
    
    results = []
    
    for i, (checkin, checkout, nights) in enumerate(tests, 1):
        print(f"\n" + "-" * 80)
        print(f"🧪 [{i}/{len(tests)}] {checkin} → {checkout} ({nights} nuit(s))")
        
        try:
            listings = search_airbnb(
                api_key=api_key,
                place_id=place_id,
                query=query,
                check_in=checkin,
                check_out=checkout,
                proxy_url=PROXY_URL,
            )
            
            print(f"📦 Résultats: {len(listings)} listings")
            
            found, rank, page, pos = find_position(listings, room_id)
            
            if found:
                print(f"✅ TROUVÉ ! Position #{rank} (Page {page}, rang {pos}/{RESULTS_PER_PAGE})")
                results.append({
                    "date": checkin,
                    "found": True,
                    "rank": rank,
                    "page": page,
                    "position": pos,
                    "total": len(listings),
                })
            else:
                print(f"❌ NON TROUVÉ dans {len(listings)} résultats")
                results.append({
                    "date": checkin,
                    "found": False,
                    "rank": None,
                    "page": None,
                    "position": None,
                    "total": len(listings),
                })
        
        except Exception as e:
            print(f"❌ Erreur: {str(e)[:100]}")
            results.append({
                "date": checkin,
                "found": False,
                "error": str(e)[:100],
            })
        
        time.sleep(DELAY_BETWEEN_SEARCHES)
    
    # Résumé
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ")
    print("=" * 80)
    
    found_count = sum(1 for r in results if r.get("found"))
    print(f"✅ Trouvé: {found_count}/{len(results)} dates")
    
    if found_count > 0:
        ranks = [r["rank"] for r in results if r.get("found")]
        avg_rank = sum(ranks) / len(ranks)
        min_rank = min(ranks)
        max_rank = max(ranks)
        print(f"📈 Position moyenne: #{avg_rank:.1f}")
        print(f"📈 Meilleure position: #{min_rank}")
        print(f"📈 Pire position: #{max_rank}")
    
    print("\n" + "=" * 80)
    print("🎉 FIN")
    print("=" * 80)


if __name__ == "__main__":
    main()
