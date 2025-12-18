#!/usr/bin/env python3
"""
=============================================================================
SCRAPE POSITIONING TEST - Version v4
=============================================================================
Réplique exactement la recherche Airbnb par URL (place_id + cursor)
=============================================================================
"""

import os
import re
import json
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from collections import defaultdict

from curl_cffi import requests
import pyairbnb

# ==============================================================================
# CONFIG
# ==============================================================================
CURRENCY = os.environ.get("CURRENCY", "AED")
LANGUAGE = os.environ.get("LANGUAGE", "fr")
PROXY_URL = os.environ.get("PROXY_URL", "")
RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", "18"))
DATES_PER_MONTH = int(os.environ.get("DATES_PER_MONTH", "3"))
MONTHS_TO_CHECK = int(os.environ.get("MONTHS_TO_CHECK", "3"))
DELAY_BETWEEN_SEARCHES = float(os.environ.get("DELAY_BETWEEN_SEARCHES", "1.5"))
DEBUG = os.environ.get("DEBUG", "0") == "1"
MAX_PAGES = int(os.environ.get("MAX_PAGES", "20"))

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


# ==============================================================================
# API KEY & HASH
# ==============================================================================
def get_api_key(proxy_url=""):
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
# CALENDAR
# ==============================================================================
def get_available_days(calendar_data):
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
    today = datetime.now().date()
    current_month = today.month
    current_year = today.year
    
    dates_by_month = defaultdict(list)
    for date_str, info in availability.items():
        if not info.get("available", False):
            continue
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            continue
        if date_obj <= today:
            continue
        month_key = (date_obj.year, date_obj.month)
        dates_by_month[month_key].append((date_str, info))
    
    target_months = []
    month = current_month
    year = current_year
    for _ in range(months_to_check):
        month += 1
        if month > 12:
            month = 1
            year += 1
        target_months.append((year, month))
    
    selected_tests = []
    for month_key in target_months:
        month_dates = dates_by_month.get(month_key, [])
        month_dates.sort(key=lambda x: x[0])
        for date_str, info in month_dates[:dates_per_month]:
            min_nights = info.get("min_nights", 1)
            check_in_date = datetime.strptime(date_str, "%Y-%m-%d")
            check_out_date = check_in_date + timedelta(days=min_nights)
            selected_tests.append((date_str, check_out_date.strftime("%Y-%m-%d"), min_nights))
    
    return selected_tests


# ==============================================================================
# URL PARSING
# ==============================================================================
def extract_search_params_from_url(url):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    params = {
        "place_id": qs.get("place_id", [None])[0],
        "query": qs.get("query", [None])[0],
        "checkin": qs.get("checkin", [None])[0],
        "checkout": qs.get("checkout", [None])[0],
    }
    
    if params["query"]:
        params["query"] = unquote(params["query"])
    
    return params


# ==============================================================================
# RECHERCHE AIRBNB - Exactement comme l'URL (place_id, pas de coordonnées)
# ==============================================================================
def search_by_place_id(api_key, place_id, query, check_in, check_out, items_offset=0):
    """
    Recherche Airbnb exactement comme l'URL:
    - Utilise place_id
    - Pas de coordonnées
    - searchByMap: false
    - Pagination par cursor (items_offset)
    """
    
    # Récupérer le hash dynamique
    try:
        operation_id = pyairbnb.fetch_stays_search_hash(PROXY_URL)
    except:
        operation_id = '9f945886dcc032b9ef4ba770d9132eb0aa78053296b5405483944c229617b00b'
    
    base_url = f"https://www.airbnb.com/api/v3/StaysSearch/{operation_id}"
    url = f"{base_url}?operationName=StaysSearch&locale={LANGUAGE}&currency={CURRENCY}"
    
    # Calculer le nombre de nuits
    try:
        nights = (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days
    except:
        nights = 2
    
    # Créer le cursor encodé en base64
    cursor_data = {
        "section_offset": 0,
        "items_offset": items_offset,
        "version": 1
    }
    cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    # Paramètres EXACTEMENT comme l'URL Airbnb
    raw_params = [
        {"filterName": "cdnCacheSafe", "filterValues": ["false"]},
        {"filterName": "channel", "filterValues": ["EXPLORE"]},
        {"filterName": "checkin", "filterValues": [check_in]},
        {"filterName": "checkout", "filterValues": [check_out]},
        {"filterName": "datePickerType", "filterValues": ["calendar"]},
        {"filterName": "flexibleTripLengths", "filterValues": ["one_week"]},
        {"filterName": "itemsPerGrid", "filterValues": ["18"]},  # 18 par page comme Airbnb
        {"filterName": "monthlyLength", "filterValues": ["3"]},
        {"filterName": "placeId", "filterValues": [place_id]},
        {"filterName": "priceFilterInputType", "filterValues": ["2"]},
        {"filterName": "priceFilterNumNights", "filterValues": [str(nights)]},
        {"filterName": "query", "filterValues": [query]},
        {"filterName": "refinementPaths", "filterValues": ["/homes"]},
        {"filterName": "screenSize", "filterValues": ["large"]},
        {"filterName": "searchByMap", "filterValues": ["false"]},  # IMPORTANT: false!
        {"filterName": "tabId", "filterValues": ["home_tab"]},
        {"filterName": "version", "filterValues": ["1.8.3"]},
    ]
    
    treatment_flags = [
        "feed_map_decouple_m11_treatment",
        "stays_search_rehydration_treatment_desktop",
        "stays_search_rehydration_treatment_moweb",
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
                "cursor": cursor,
                "maxMapItems": 9999,
                "requestedPageType": "STAYS_SEARCH",
                "metadataOnly": False,
                "source": "structured_search_input_header",
                "searchType": "pagination",
                "treatmentFlags": treatment_flags,
                "rawParams": raw_params,
            },
            "staysMapSearchRequestV2": {
                "cursor": cursor,
                "requestedPageType": "STAYS_SEARCH",
                "metadataOnly": False,
                "source": "structured_search_input_header",
                "searchType": "pagination",
                "treatmentFlags": treatment_flags,
                "rawParams": raw_params,
            },
            "includeMapResults": True,
            "isLeanTreatment": False,
        },
    }
    
    headers = HEADERS.copy()
    headers["X-Airbnb-Api-Key"] = api_key
    
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
    
    response = requests.post(
        url,
        json=input_data,
        headers=headers,
        proxies=proxies,
        impersonate="chrome124",
        timeout=60
    )
    
    if response.status_code != 200:
        if DEBUG:
            print(f"      ❌ HTTP {response.status_code}: {response.text[:200]}")
        return [], False
    
    data = response.json()
    
    # Vérifier les erreurs
    if "errors" in data and data.get("data") is None:
        if DEBUG:
            print(f"      ❌ API Error: {data['errors']}")
        return [], False
    
    # Extraire les listings
    listings = []
    try:
        search_results = (data
                        .get("data", {})
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
                listings.append({
                    "id": str(listing_id),
                    "name": listing.get("name", "")[:50],
                })
        
        # Vérifier s'il y a plus de pages
        pagination = (data
                     .get("data", {})
                     .get("presentation", {})
                     .get("staysSearch", {})
                     .get("results", {})
                     .get("paginationInfo", {}))
        
        has_next = pagination.get("hasNextPage", False) or len(listings) == 18
        
    except Exception as e:
        if DEBUG:
            print(f"      ❌ Parse error: {e}")
        return [], False
    
    return listings, has_next


def search_all_pages(api_key, place_id, query, check_in, check_out, target_room_id):
    """
    Parcourt toutes les pages jusqu'à trouver le listing ou la fin des résultats.
    Retourne (found, position, total_listings)
    """
    all_listings = []
    items_offset = 0
    page = 1
    
    print(f"   📡 Recherche page par page...", flush=True)
    
    while page <= MAX_PAGES:
        listings, has_next = search_by_place_id(
            api_key, place_id, query, check_in, check_out, items_offset
        )
        
        if not listings:
            break
        
        # Ajouter les listings
        start_pos = len(all_listings) + 1
        for i, listing in enumerate(listings):
            listing["position"] = start_pos + i
            all_listings.append(listing)
            
            # Vérifier si c'est notre cible
            if str(listing["id"]) == str(target_room_id):
                position = listing["position"]
                page_num = (position - 1) // RESULTS_PER_PAGE + 1
                pos_on_page = (position - 1) % RESULTS_PER_PAGE + 1
                print(f"      ✅ Trouvé page {page} (offset {items_offset})")
                return True, position, page_num, pos_on_page, len(all_listings)
        
        if DEBUG:
            print(f"      Page {page}: {len(listings)} listings (total: {len(all_listings)})")
        
        if not has_next:
            break
        
        items_offset += 18
        page += 1
        time.sleep(0.3)  # Petit délai entre les pages
    
    return False, None, None, None, len(all_listings)


# ==============================================================================
# INPUT
# ==============================================================================
def read_input(env_key, prompt, required=True):
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
    print("🚀 TEST POSITIONNEMENT — Version v4 (place_id + cursor)")
    print("=" * 80)
    print(f"📅 Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Devise: {CURRENCY} | 🌐 Langue: {LANGUAGE}")
    print(f"📊 Config: {DATES_PER_MONTH} dates/mois × {MONTHS_TO_CHECK} mois")
    print(f"📄 Max pages: {MAX_PAGES}")
    if DEBUG:
        print("🐛 MODE DEBUG ACTIVÉ")
    print("=" * 80)
    
    # Inputs
    room_id = read_input("ROOM_ID", "RoomID (listing id) : ")
    search_url = read_input("SEARCH_URL", "URL de recherche Airbnb : ")
    date_input = read_input("DATE_INPUT", "Date (YYYY-MM-DD) ou 0 pour auto-calendrier : ")
    
    # Extraire paramètres de l'URL
    print("\n" + "-" * 80)
    print("📍 Extraction paramètres URL...")
    url_params = extract_search_params_from_url(search_url)
    
    place_id = url_params.get("place_id")
    query = url_params.get("query", "")
    
    if not place_id:
        print("❌ ERREUR: place_id non trouvé dans l'URL!")
        return
    
    if not query:
        print("❌ ERREUR: query non trouvé dans l'URL!")
        return
    
    print(f"   ✅ place_id: {place_id}")
    print(f"   ✅ query: {query}")
    
    # API Key
    print("\n📦 Récupération API Key...", end=" ", flush=True)
    api_key = get_api_key(PROXY_URL)
    print("OK")
    
    # Tests à exécuter
    tests = []
    
    if date_input == "0":
        print("\n📅 Mode auto-calendrier")
        print("📅 Récupération calendrier...", end=" ", flush=True)
        calendar_data = pyairbnb.get_calendar(api_key=api_key, room_id=str(room_id), proxy_url=PROXY_URL)
        print("OK")
        
        availability = get_available_days(calendar_data)
        available_count = sum(1 for d, info in availability.items() if info["available"])
        print(f"📊 Jours disponibles: {available_count}")
        
        if available_count == 0:
            print("⚠️ Aucun jour disponible!")
            return
        
        tests = select_dates_per_month(availability, DATES_PER_MONTH, MONTHS_TO_CHECK)
        print(f"📊 Sélection: {len(tests)} dates")
        
        if tests:
            print("\n📋 Dates sélectionnées:")
            for i, (ci, co, n) in enumerate(tests, 1):
                print(f"   {i}. {ci} → {co} ({n} nuit(s))")
    else:
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
    
    # Exécution
    print("\n" + "=" * 80)
    print(f"🔎 Tests à exécuter: {len(tests)}")
    print("=" * 80)
    
    results = []
    
    for i, (checkin, checkout, nights) in enumerate(tests, 1):
        print(f"\n" + "-" * 80)
        print(f"🧪 [{i}/{len(tests)}] {checkin} → {checkout} ({nights} nuit(s))")
        
        try:
            found, position, page, pos_on_page, total = search_all_pages(
                api_key, place_id, query, checkin, checkout, room_id
            )
            
            if found:
                print(f"   ✅ TROUVÉ ! Position #{position} (Page {page}, rang {pos_on_page})")
                results.append({
                    "date": checkin,
                    "found": True,
                    "rank": position,
                    "page": page,
                    "position": pos_on_page,
                    "total": total,
                })
            else:
                print(f"   ❌ NON TROUVÉ dans {total} résultats ({total // 18 + 1} pages)")
                results.append({
                    "date": checkin,
                    "found": False,
                    "total": total,
                })
        
        except Exception as e:
            print(f"   ❌ Erreur: {e}")
            if DEBUG:
                import traceback
                traceback.print_exc()
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
