#!/usr/bin/env python3
"""
=============================================================================
TEST POSITIONNEMENT COMPLET
=============================================================================
Paramètres:
- ROOM_ID : ID du listing à tracker
- GUESTS : Nombre de voyageurs
- MAX_NIGHTS : Nombre max de nuits (flexible selon dispo)
- DATES_PER_MONTH : Nombre de dates à tester par mois
- MONTHS_TO_CHECK : Nombre de mois à vérifier
=============================================================================
"""

import os
import time
from datetime import datetime, timedelta
from collections import defaultdict

import pyairbnb

# ==============================================================================
# CONFIG
# ==============================================================================
# Coordonnées exactes Downtown Dubai
NE_LAT = 25.209954590340505
NE_LNG = 55.284802388971144
SW_LAT = 25.17910678720699
SW_LNG = 55.25763445730311
ZOOM = 14

# Paramètres depuis environnement
ROOM_ID = os.environ.get("ROOM_ID", "")
GUESTS = int(os.environ.get("GUESTS", "2"))
MAX_NIGHTS = int(os.environ.get("MAX_NIGHTS", "3"))
CURRENCY = os.environ.get("CURRENCY", "AED")
DATES_PER_MONTH = int(os.environ.get("DATES_PER_MONTH", "5"))
MONTHS_TO_CHECK = int(os.environ.get("MONTHS_TO_CHECK", "2"))
RESULTS_PER_PAGE = 18
DELAY = 1.5


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


def calculate_booking_nights(availability, check_in_str, max_nights):
    """
    Calcule le nombre de nuits optimal pour une réservation.
    - Essaie max_nights d'abord
    - Si pas possible, réduit jusqu'à trouver une période valide
    - Respecte min_nights du calendrier
    """
    check_in = datetime.strptime(check_in_str, "%Y-%m-%d").date()
    min_required = availability.get(check_in_str, {}).get("min_nights", 1)
    
    # Commencer par le max demandé, descendre si nécessaire
    for nights in range(max_nights, min_required - 1, -1):
        if nights < min_required:
            break
        
        # Vérifier que toutes les nuits sont disponibles
        all_available = True
        for i in range(nights):
            check_date = (check_in + timedelta(days=i)).strftime("%Y-%m-%d")
            day_info = availability.get(check_date, {})
            if not day_info.get("available", False):
                all_available = False
                break
        
        if all_available:
            return nights
    
    # Fallback: utiliser min_nights
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
    
    # Prochains mois
    target_months = []
    month = current_month
    year = current_year
    for _ in range(months_to_check):
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
            
            # Calculer le nombre de nuits optimal
            nights = calculate_booking_nights(availability, date_str, max_nights)
            
            check_in = datetime.strptime(date_str, "%Y-%m-%d")
            check_out = check_in + timedelta(days=nights)
            
            selected.append((date_str, check_out.strftime("%Y-%m-%d"), nights))
            count += 1
    
    return selected


# ==============================================================================
# PRICE EXTRACTION
# ==============================================================================
def extract_price(price_data):
    if not price_data:
        return None
    if isinstance(price_data, dict):
        unit = price_data.get("unit", {})
        if unit:
            return unit.get("amount")
        return price_data.get("amount")
    return None


def calculate_page_ranges(results):
    pages = []
    for i in range(0, len(results), RESULTS_PER_PAGE):
        page_listings = results[i:i + RESULTS_PER_PAGE]
        prices = []
        for item in page_listings:
            price = extract_price(item.get("price"))
            if price and price > 0:
                prices.append(price)
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
    # Vérifier ROOM_ID
    if not ROOM_ID:
        print("❌ ERREUR: ROOM_ID est requis!")
        print("   Définissez la variable d'environnement ROOM_ID")
        return
    
    print("=" * 80)
    print("🚀 TEST POSITIONNEMENT COMPLET")
    print("=" * 80)
    print(f"📍 Room ID : {ROOM_ID}")
    print(f"👥 Voyageurs : {GUESTS}")
    print(f"🌙 Max nuits : {MAX_NIGHTS}")
    print(f"💰 Devise : {CURRENCY}")
    print(f"📊 Config : {DATES_PER_MONTH} dates/mois × {MONTHS_TO_CHECK} mois")
    print(f"📍 Zone : Downtown Dubai")
    print("=" * 80)
    
    # API Key
    print("\n📦 Récupération API Key...", end=" ", flush=True)
    api_key = pyairbnb.get_api_key("")
    print("OK")
    
    # Calendrier
    print("📅 Récupération calendrier...", end=" ", flush=True)
    calendar_data = pyairbnb.get_calendar(api_key=api_key, room_id=ROOM_ID, proxy_url="")
    print("OK")
    
    availability = get_available_days(calendar_data)
    available_count = sum(1 for info in availability.values() if info["available"])
    print(f"📊 Jours disponibles : {available_count}")
    
    # Sélection dates avec nuits flexibles
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
            # Recherche
            # Note: pyairbnb ne supporte pas le filtre par nombre de voyageurs
            results = pyairbnb.search_all(
                check_in=check_in,
                check_out=check_out,
                ne_lat=NE_LAT,
                ne_long=NE_LNG,
                sw_lat=SW_LAT,
                sw_long=SW_LNG,
                zoom_value=ZOOM,
                price_min=0,
                price_max=0,
                currency=CURRENCY,
                proxy_url="",
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
                    my_price = extract_price(item.get("price"))
                    my_page = (my_position - 1) // RESULTS_PER_PAGE + 1
                    my_pos_on_page = (my_position - 1) % RESULTS_PER_PAGE + 1
                    found = True
                    break
            
            # Afficher résultat
            if found:
                print(f"\n✅ TROUVÉ !")
                print(f"   📍 Position : #{my_position} (Page {my_page}, rang {my_pos_on_page}/18)")
                if my_price:
                    print(f"   💰 Prix : {my_price:,.0f} {CURRENCY} ({nights} nuits)")
            else:
                print(f"\n❌ NON TROUVÉ dans {len(results)} résultats")
            
            # Fourchettes de prix par page
            page_ranges = calculate_page_ranges(results)
            
            print(f"\n📊 Fourchettes de prix par page :")
            for pr in page_ranges:
                marker = " ← MON LISTING" if found and pr["page"] == my_page else ""
                print(f"   Page {pr['page']:2d} : {pr['min']:,.0f} - {pr['max']:,.0f} {CURRENCY} ({pr['count']} prix){marker}")
            
            # Stocker résultat
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
    
    # Résumé final
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
