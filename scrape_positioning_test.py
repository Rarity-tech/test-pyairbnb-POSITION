#!/usr/bin/env python3
"""
=============================================================================
SOLUTION INDÉPENDANTE - TRACKING POSITION AIRBNB AVEC FILTRE ADULTS
=============================================================================
Cette version N'UTILISE PAS pyairbnb pour la recherche.
Elle appelle directement l'API Airbnb avec contrôle total sur les paramètres.
=============================================================================
"""

import os
import re
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict
from curl_cffi import requests as curl_requests

# Importer UNIQUEMENT pour le calendrier (pas pour la recherche)
import pyairbnb

# ==============================================================================
# CONFIG
# ==============================================================================
NE_LAT = 25.209954590340505
NE_LNG = 55.284802388971144
SW_LAT = 25.17910678720699
SW_LNG = 55.25763445730311
ZOOM = 14

ROOM_ID = os.environ.get("ROOM_ID", "")
GUESTS = int(os.environ.get("GUESTS", "2"))
MAX_NIGHTS = int(os.environ.get("MAX_NIGHTS", "3"))
CURRENCY = os.environ.get("CURRENCY", "AED")
DATES_PER_MONTH = int(os.environ.get("DATES_PER_MONTH", "5"))
MONTHS_TO_CHECK = int(os.environ.get("MONTHS_TO_CHECK", "2"))
RESULTS_PER_PAGE = 18
DELAY = 1.5

# API Key Airbnb (clé publique valide trouvée dans les sources)
AIRBNB_API_KEY = "d306zoyjsyarp7ifhu67rjxn52tv0t20"

# ==============================================================================
# RECHERCHE COMPLÈTEMENT INDÉPENDANTE
# ==============================================================================
def independent_search(check_in, check_out, ne_lat, ne_lng, sw_lat, sw_lng, adults, currency="AED"):
    """
    Recherche Airbnb COMPLÈTEMENT indépendante de pyairbnb.
    Appelle directement l'API Airbnb v2/explore_tabs avec PAGINATION complète.
    """
    
    # Endpoint historique qui fonctionne sans GraphQL complexe
    url = "https://www.airbnb.com/api/v2/explore_tabs"
    
    # Calculer nombre de nuits
    check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
    check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
    nights = (check_out_date - check_in_date).days
    
    # Paramètres de base
    base_params = {
        # PARAMÈTRES CRITIQUES
        "adults": str(adults),
        "children": "0",
        "infants": "0",
        
        # Dates
        "checkin": check_in,
        "checkout": check_out,
        
        # Coordonnées
        "ne_lat": str(ne_lat),
        "ne_lng": str(ne_lng),
        "sw_lat": str(sw_lat),
        "sw_lng": str(sw_lng),
        "search_by_map": "true",
        "zoom": str(ZOOM),
        
        # Paramètres de recherche
        "version": "1.8.3",
        "satori_version": "1.2.0",
        "_format": "for_explore_search_web",
        "items_per_grid": "50",
        "screen_size": "large",
        "query": "Downtown Dubai, Dubai, United Arab Emirates",
        
        # Autres
        "currency": currency,
        "locale": "en",
        "key": AIRBNB_API_KEY,
        "timezone_offset": "240",
        
        # Flags
        "is_guided_search": "true",
        "is_standard_search": "true",
        "refinement_paths[]": "/homes",
        "tab_id": "home_tab",
        "channel": "EXPLORE",
        "date_picker_type": "calendar",
        "source": "structured_search_input_header",
        "search_type": "user_map_move",
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Airbnb-API-Key": AIRBNB_API_KEY,
    }
    
    all_listings = []
    items_offset = 0
    section_offset = 0
    page_count = 0
    max_pages = 16  # ~280 listings = 15-16 pages
    
    try:
        # Boucle de pagination
        while page_count < max_pages:
            page_count += 1
            
            # Préparer les paramètres avec offset
            params = base_params.copy()
            if page_count > 1:
                params["items_offset"] = str(items_offset)
                params["section_offset"] = str(section_offset)
            
            # Requête API
            response = curl_requests.get(
                url,
                params=params,
                headers=headers,
                impersonate="chrome120",
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"      ⚠️  HTTP {response.status_code}: {response.text[:500]}")
                break
            
            data = response.json()
            
            # Extraction des listings depuis explore_tabs
            page_listings = []
            pagination_metadata = None
            
            # Structure explore_tabs
            explore_tabs = data.get("explore_tabs", [])
            
            for tab in explore_tabs:
                # Récupérer metadata de pagination
                if not pagination_metadata:
                    pagination_metadata = tab.get("pagination_metadata", {})
                
                sections = tab.get("sections", [])
                for section in sections:
                    listings = section.get("listings", [])
                    
                    for listing in listings:
                        listing_data = listing.get("listing", {})
                        pricing = listing.get("pricing_quote", {})
                        
                        room_id = listing_data.get("id")
                        if not room_id:
                            continue
                        
                        # Éviter les doublons
                        if any(l["room_id"] == str(room_id) for l in all_listings):
                            continue
                        
                        # Extraire prix
                        price = None
                        if pricing:
                            rate = pricing.get("rate", {})
                            amount = rate.get("amount")
                            if amount:
                                try:
                                    price = float(amount)
                                except:
                                    pass
                        
                        page_listings.append({
                            "room_id": str(room_id),
                            "name": listing_data.get("name", ""),
                            "price": price,
                        })
            
            # Ajouter les résultats de cette page
            all_listings.extend(page_listings)
            
            if page_count == 1:
                print(f"      📄 Page {page_count}: {len(page_listings)} listings")
            else:
                print(f"      📄 Page {page_count}: +{len(page_listings)} listings (total: {len(all_listings)})")
            
            # Vérifier s'il y a une page suivante
            if not page_listings:
                # Aucun résultat sur cette page = fin
                break
            
            # Vérifier s'il y a une page suivante
            has_next_page = pagination_metadata.get("has_next_page", False) if pagination_metadata else False
            
            if not has_next_page:
                # Pas de page suivante
                break
            
            # Mettre à jour les offsets pour la page suivante
            items_offset = pagination_metadata.get("items_offset", 0) if pagination_metadata else 0
            section_offset = pagination_metadata.get("section_offset", 0) if pagination_metadata else 0
            
            # Petit délai entre les pages pour éviter rate limiting
            if page_count < max_pages:
                time.sleep(0.5)
        
        print(f"      ✅ Total: {len(all_listings)} listings ({page_count} page{'s' if page_count > 1 else ''})")
        return all_listings
        
    except Exception as e:
        print(f"      ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return all_listings  # Retourner ce qu'on a récupéré jusqu'ici


# ==============================================================================
# CALENDAR (on garde pyairbnb pour ça car ça marche)
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


def calculate_booking_nights(availability, check_in_str, max_nights):
    check_in = datetime.strptime(check_in_str, "%Y-%m-%d").date()
    min_required = availability.get(check_in_str, {}).get("min_nights", 1)

    for nights in range(max_nights, min_required - 1, -1):
        if nights < min_required:
            break

        all_available = True
        for i in range(nights):
            check_date = (check_in + timedelta(days=i)).strftime("%Y-%m-%d")
            day_info = availability.get(check_date, {})
            if not day_info.get("available", False):
                all_available = False
                break

        if all_available:
            return nights

    return min_required


def select_dates(availability, dates_per_month, months_to_check, max_nights):
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

    target_months = [(current_year, current_month)]
    month = current_month
    year = current_year
    for _ in range(months_to_check - 1):
        month += 1
        if month > 12:
            month = 1
            year += 1
        target_months.append((year, month))

    selected = []
    for month_key in target_months:
        month_dates = dates_by_month.get(month_key, [])
        month_dates.sort(key=lambda x: x[0])

        count = 0
        for date_str, info in month_dates:
            if count >= dates_per_month:
                break

            nights = calculate_booking_nights(availability, date_str, max_nights)
            check_in = datetime.strptime(date_str, "%Y-%m-%d")
            check_out = check_in + timedelta(days=nights)

            selected.append((date_str, check_out.strftime("%Y-%m-%d"), nights))
            count += 1

    return selected


# ==============================================================================
# PRICE EXTRACTION
# ==============================================================================
def calculate_page_ranges(results):
    pages = []
    for i in range(0, len(results), RESULTS_PER_PAGE):
        page_listings = results[i : i + RESULTS_PER_PAGE]
        prices = [r["price"] for r in page_listings if r.get("price") and r["price"] > 0]
        
        if prices:
            page_num = (i // RESULTS_PER_PAGE) + 1
            pages.append({
                "page": page_num,
                "min": min(prices),
                "max": max(prices),
                "count": len(prices),
            })
    return pages


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    if not ROOM_ID:
        print("❌ ERREUR: ROOM_ID est requis!")
        return

    print("=" * 80)
    print("🚀 TRACKING POSITION AIRBNB")
    print("=" * 80)
    print(f"📍 Room ID : {ROOM_ID}")
    print(f"👥 Voyageurs : {GUESTS}")
    print(f"🌙 Max nuits : {MAX_NIGHTS}")
    print(f"💰 Devise : {CURRENCY}")
    print(f"📊 Config : {DATES_PER_MONTH} dates/mois × {MONTHS_TO_CHECK} mois")
    print(f"📍 Zone : Downtown Dubai")
    print("=" * 80)

    # Calendrier (on utilise pyairbnb pour ça)
    print("\n📅 Récupération calendrier...", end=" ", flush=True)
    api_key = pyairbnb.get_api_key("")
    calendar_data = pyairbnb.get_calendar(api_key=api_key, room_id=ROOM_ID, proxy_url="")
    print("OK")

    availability = get_available_days(calendar_data)
    available_count = sum(1 for info in availability.values() if info["available"])
    print(f"📊 Jours disponibles : {available_count}")

    tests = select_dates(availability, DATES_PER_MONTH, MONTHS_TO_CHECK, MAX_NIGHTS)
    print(f"📋 Dates sélectionnées : {len(tests)}")

    if not tests:
        print("❌ Aucune date disponible!")
        return

    for i, (ci, co, n) in enumerate(tests, 1):
        print(f"   {i}. {ci} → {co} ({n} nuit(s))")

    # Exécution
    print("\n" + "=" * 80)
    print("🔎 RECHERCHES")
    print("=" * 80)

    all_results = []

    for i, (check_in, check_out, nights) in enumerate(tests, 1):
        print(f"\n{'─' * 80}")
        print(f"🧪 [{i}/{len(tests)}] {check_in} → {check_out} ({nights} nuit(s)) | {GUESTS} voyageur(s)")
        print("─" * 80)

        try:
            # RECHERCHE INDÉPENDANTE
            results = independent_search(
                check_in=check_in,
                check_out=check_out,
                ne_lat=NE_LAT,
                ne_lng=NE_LNG,
                sw_lat=SW_LAT,
                sw_lng=SW_LNG,
                adults=GUESTS,
                currency=CURRENCY,
            )

            print(f"📦 Résultats : {len(results)} listings")

            # Chercher notre listing
            found = False
            my_price = None
            my_position = None
            my_page = None

            for idx, item in enumerate(results):
                if str(item.get("room_id", "")) == str(ROOM_ID):
                    my_position = idx + 1
                    my_price = item.get("price")
                    my_page = (my_position - 1) // RESULTS_PER_PAGE + 1
                    my_pos_on_page = (my_position - 1) % RESULTS_PER_PAGE + 1
                    found = True
                    break

            if found:
                print(f"\n✅ TROUVÉ !")
                print(f"   📍 Position : #{my_position} (Page {my_page}, rang {my_pos_on_page}/18)")
                if my_price:
                    print(f"   💰 Prix : {my_price:,.0f} {CURRENCY} ({nights} nuits)")
            else:
                print(f"\n❌ NON TROUVÉ dans {len(results)} résultats")

            page_ranges = calculate_page_ranges(results)

            print(f"\n📊 Fourchettes de prix par page :")
            for pr in page_ranges:
                marker = " ← MON LISTING" if found and pr["page"] == my_page else ""
                print(f"   Page {pr['page']:2d} : {pr['min']:,.0f} - {pr['max']:,.0f} {CURRENCY} ({pr['count']} prix){marker}")

            all_results.append({
                "date": check_in,
                "nights": nights,
                "found": found,
                "position": my_position,
                "page": my_page if found else None,
                "price": my_price,
                "total": len(results),
                "page_ranges": page_ranges,
            })

        except Exception as e:
            print(f"❌ Erreur : {e}")
            import traceback
            traceback.print_exc()
            all_results.append({
                "date": check_in,
                "nights": nights,
                "found": False,
                "error": str(e),
            })

        time.sleep(DELAY)

    # Résumé
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 80)

    found_results = [r for r in all_results if r.get("found")]
    print(f"\n✅ Trouvé : {len(found_results)}/{len(all_results)} dates")

    if found_results:
        positions = [r["position"] for r in found_results]
        prices = [r["price"] for r in found_results if r.get("price")]

        print(f"\n📍 Positions :")
        print(f"   Moyenne : #{sum(positions)/len(positions):.1f}")
        print(f"   Meilleure : #{min(positions)}")
        print(f"   Pire : #{max(positions)}")

        if prices:
            print(f"\n💰 Prix de mon listing :")
            print(f"   Min : {min(prices):,.0f} {CURRENCY}")
            print(f"   Max : {max(prices):,.0f} {CURRENCY}")
            print(f"   Moyenne : {sum(prices)/len(prices):,.0f} {CURRENCY}")

    print("\n📋 Détails par date :")
    print(f"{'Date':<12} {'Nuits':>6} {'Pos':>6} {'Page':>6} {'Mon Prix':>12} {'Page Min':>12} {'Page Max':>12}")
    print("─" * 80)

    for r in all_results:
        nights = r.get("nights", "?")
        if r.get("found"):
            page = r["page"]
            page_range = next((p for p in r.get("page_ranges", []) if p["page"] == page), None)
            page_min = f"{page_range['min']:,.0f}" if page_range else "N/A"
            page_max = f"{page_range['max']:,.0f}" if page_range else "N/A"
            my_price = f"{r['price']:,.0f}" if r.get("price") else "N/A"
            print(f"{r['date']:<12} {nights:>6} {r['position']:>6} {page:>6} {my_price:>12} {page_min:>12} {page_max:>12}")
        else:
            print(f"{r['date']:<12} {nights:>6} {'N/A':>6} {'N/A':>6} {'N/A':>12} {'N/A':>12} {'N/A':>12}")

    print("\n" + "=" * 80)
    print("🎉 FIN")
    print("=" * 80)


if __name__ == "__main__":
    main()
