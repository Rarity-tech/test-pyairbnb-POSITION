#!/usr/bin/env python3
"""
=============================================================================
SCRAPE POSITIONING TEST - Version v3
=============================================================================
Utilise pyairbnb.search_all() directement (qui fonctionne)
=============================================================================
"""

import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from collections import defaultdict

import pyairbnb

# ==============================================================================
# CONFIG
# ==============================================================================
CURRENCY = os.environ.get("CURRENCY", "AED")
LANGUAGE = os.environ.get("LANGUAGE", "en")
PROXY_URL = os.environ.get("PROXY_URL", "")
RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", "18"))
MAX_DAYS = int(os.environ.get("MAX_DAYS", "0"))
DATES_PER_MONTH = int(os.environ.get("DATES_PER_MONTH", "3"))
MONTHS_TO_CHECK = int(os.environ.get("MONTHS_TO_CHECK", "3"))
DELAY_BETWEEN_SEARCHES = float(os.environ.get("DELAY_BETWEEN_SEARCHES", "1.5"))
DEBUG = os.environ.get("DEBUG", "0") == "1"


# ==============================================================================
# COORDONNÉES PRÉDÉFINIES POUR LES ZONES CONNUES
# ==============================================================================
KNOWN_ZONES = {
    # Downtown Dubai (centre-ville)
    "ChIJg_kMcC9oXz4RBLnAdrBYzLU": {
        "name": "Downtown Dubai",
        "ne_lat": 25.2100,
        "ne_lng": 55.2850,
        "sw_lat": 25.1850,
        "sw_lng": 55.2600,
        "zoom": 14,
    },
    # Dubai Marina
    "ChIJHeMYJBZDXz4RsM0yP2BjzKU": {
        "name": "Dubai Marina",
        "ne_lat": 25.0950,
        "ne_lng": 55.1550,
        "sw_lat": 25.0700,
        "sw_lng": 55.1250,
        "zoom": 14,
    },
    # Palm Jumeirah
    "ChIJDR_hQi5FXz4RCoge8pIJ5xE": {
        "name": "Palm Jumeirah",
        "ne_lat": 25.1400,
        "ne_lng": 55.1500,
        "sw_lat": 25.1000,
        "sw_lng": 55.1050,
        "zoom": 13,
    },
    # Business Bay
    "ChIJx3bKhCNoXz4R51CQHxyDJDE": {
        "name": "Business Bay",
        "ne_lat": 25.1950,
        "ne_lng": 55.2750,
        "sw_lat": 25.1750,
        "sw_lng": 55.2550,
        "zoom": 14,
    },
}


# ==============================================================================
# CALENDAR
# ==============================================================================
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
    """Sélectionne X dates disponibles pour chacun des Y prochains mois."""
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
            check_out = check_out_date.strftime("%Y-%m-%d")
            
            selected_tests.append((date_str, check_out, min_nights))
    
    return selected_tests


# ==============================================================================
# URL PARSING
# ==============================================================================
def extract_search_params_from_url(url):
    """Extrait les paramètres de recherche depuis une URL Airbnb."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    params = {
        "place_id": qs.get("place_id", [None])[0],
        "query": qs.get("query", [None])[0],
        "ne_lat": qs.get("ne_lat", [None])[0],
        "ne_lng": qs.get("ne_lng", [None])[0],
        "sw_lat": qs.get("sw_lat", [None])[0],
        "sw_lng": qs.get("sw_lng", [None])[0],
        "zoom": qs.get("zoom", qs.get("zoom_level", [None]))[0],
    }
    
    if params["query"]:
        params["query"] = unquote(params["query"])
    
    return params


def get_coordinates_for_place(place_id, url_params):
    """Retourne les coordonnées pour un placeId."""
    # 1. Si l'URL contient déjà des coordonnées, les utiliser
    if all([url_params.get("ne_lat"), url_params.get("ne_lng"), 
            url_params.get("sw_lat"), url_params.get("sw_lng")]):
        return {
            "ne_lat": float(url_params["ne_lat"]),
            "ne_lng": float(url_params["ne_lng"]),
            "sw_lat": float(url_params["sw_lat"]),
            "sw_lng": float(url_params["sw_lng"]),
            "zoom": int(url_params.get("zoom") or 14),
        }
    
    # 2. Chercher dans les zones connues
    if place_id and place_id in KNOWN_ZONES:
        return KNOWN_ZONES[place_id]
    
    return None


# ==============================================================================
# RECHERCHE - Utilise pyairbnb.search_all directement
# ==============================================================================
def search_airbnb(coords, check_in, check_out):
    """
    Effectue une recherche Airbnb en utilisant pyairbnb.search_all.
    Retourne liste de {"id": ..., "name": ...}
    """
    print(f"   📡 Recherche pyairbnb...", end=" ", flush=True)
    
    try:
        results = pyairbnb.search_all(
            check_in=check_in,
            check_out=check_out,
            ne_lat=coords["ne_lat"],
            ne_long=coords["ne_lng"],
            sw_lat=coords["sw_lat"],
            sw_long=coords["sw_lng"],
            zoom_value=coords.get("zoom", 14),
            price_min=0,
            price_max=0,
            currency=CURRENCY,
            proxy_url=PROXY_URL,
        )
        
        print(f"OK ({len(results or [])} résultats bruts)")
        
        # Convertir au format attendu
        listings = []
        for item in (results or []):
            room_id = item.get("room_id")
            if room_id:
                listings.append({
                    "id": str(room_id),
                    "name": item.get("name", "")[:50],
                })
        
        if DEBUG and results and len(results) > 0:
            print(f"   🔍 Premier résultat: room_id={results[0].get('room_id')}")
            print(f"   🔍 Clés disponibles: {list(results[0].keys())}")
        
        return listings
    
    except Exception as e:
        print(f"Erreur: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
        return []


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
    print("🚀 TEST POSITIONNEMENT — Version v3 (pyairbnb.search_all)")
    print("=" * 80)
    print(f"📅 Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 Devise: {CURRENCY} | 🌐 Langue: {LANGUAGE}")
    print(f"📊 Config: {DATES_PER_MONTH} dates/mois × {MONTHS_TO_CHECK} mois")
    if DEBUG:
        print("🐛 MODE DEBUG ACTIVÉ")
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
    
    print(f"   place_id: {place_id or '(non trouvé)'}")
    print(f"   query: {query or '(non trouvé)'}")
    
    # Obtenir les coordonnées
    coords = get_coordinates_for_place(place_id, url_params)
    
    if not coords:
        print("❌ ERREUR: Impossible de déterminer les coordonnées!")
        print("   → Ajoutez ne_lat, ne_lng, sw_lat, sw_lng dans l'URL")
        print("   → Ou utilisez un place_id connu:")
        for pid, info in KNOWN_ZONES.items():
            print(f"      • {info['name']}: {pid}")
        return
    
    print(f"   ✅ Zone: {KNOWN_ZONES.get(place_id, {}).get('name', 'Custom')}")
    print(f"   ✅ Coordonnées: NE({coords['ne_lat']}, {coords['ne_lng']}) SW({coords['sw_lat']}, {coords['sw_lng']})")
    
    # Récupérer API Key pour le calendrier
    print("\n📦 Récupération API Key...", end=" ", flush=True)
    api_key = pyairbnb.get_api_key(PROXY_URL)
    print(f"OK")
    
    # Construire la liste de tests
    tests = []
    
    if date_input == "0":
        print("\n📅 Mode auto-calendrier")
        print("📅 Récupération calendrier...", end=" ", flush=True)
        calendar_data = pyairbnb.get_calendar(api_key=api_key, room_id=str(room_id), proxy_url=PROXY_URL)
        print("OK")
        
        availability = get_available_days(calendar_data)
        available_count = sum(1 for d, info in availability.items() if info["available"])
        print(f"📊 Jours disponibles total: {available_count}")
        
        if available_count == 0:
            print("⚠️ Aucun jour disponible!")
            return
        
        if MAX_DAYS > 0:
            available_dates = [d for d, info in sorted(availability.items()) if info["available"]]
            available_dates = available_dates[:MAX_DAYS]
            for check_in in available_dates:
                min_nights = availability[check_in].get("min_nights", 1)
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
                check_out_date = check_in_date + timedelta(days=min_nights)
                tests.append((check_in, check_out_date.strftime("%Y-%m-%d"), min_nights))
            print(f"📊 Mode MAX_DAYS: {len(tests)} dates sélectionnées")
        else:
            tests = select_dates_per_month(availability, DATES_PER_MONTH, MONTHS_TO_CHECK)
            print(f"📊 Sélection: {len(tests)} dates ({DATES_PER_MONTH}/mois × {MONTHS_TO_CHECK} mois)")
        
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
                coords=coords,
                check_in=checkin,
                check_out=checkout,
            )
            
            print(f"   📦 Listings uniques: {len(listings)}")
            
            if not listings:
                print(f"   ⚠️ Aucun listing retourné")
                results.append({
                    "date": checkin,
                    "found": False,
                    "total": 0,
                })
                continue
            
            # Afficher quelques IDs pour debug
            if DEBUG and listings:
                print(f"   🔍 Premiers IDs: {[l['id'] for l in listings[:5]]}")
            
            found, rank, page, pos = find_position(listings, room_id)
            
            if found:
                print(f"   ✅ TROUVÉ ! Position #{rank} (Page {page}, rang {pos}/{RESULTS_PER_PAGE})")
                results.append({
                    "date": checkin,
                    "found": True,
                    "rank": rank,
                    "page": page,
                    "position": pos,
                    "total": len(listings),
                })
            else:
                print(f"   ❌ NON TROUVÉ dans {len(listings)} résultats")
                results.append({
                    "date": checkin,
                    "found": False,
                    "rank": None,
                    "page": None,
                    "position": None,
                    "total": len(listings),
                })
        
        except Exception as e:
            print(f"   ❌ Erreur: {str(e)}")
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
