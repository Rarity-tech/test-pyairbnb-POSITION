#!/usr/bin/env python3
"""
=============================================================================
TEST SIMPLE - Coordonnées exactes Downtown Dubai
=============================================================================
"""

import pyairbnb

# Coordonnées exactes extraites de l'URL Airbnb
NE_LAT = 25.209954590340505
NE_LNG = 55.284802388971144
SW_LAT = 25.17910678720699
SW_LNG = 55.25763445730311
ZOOM = 14

# Test
ROOM_ID = "1414331280662142957"
CHECK_IN = "2026-01-20"
CHECK_OUT = "2026-01-23"

def main():
    print("=" * 70)
    print("TEST SIMPLE - pyairbnb.search_all()")
    print("=" * 70)
    print(f"Room ID cible : {ROOM_ID}")
    print(f"Dates : {CHECK_IN} → {CHECK_OUT}")
    print(f"Coordonnées :")
    print(f"  NE: ({NE_LAT}, {NE_LNG})")
    print(f"  SW: ({SW_LAT}, {SW_LNG})")
    print(f"  Zoom: {ZOOM}")
    print("=" * 70)
    
    print("\n📡 Lancement recherche pyairbnb.search_all()...")
    
    results = pyairbnb.search_all(
        check_in=CHECK_IN,
        check_out=CHECK_OUT,
        ne_lat=NE_LAT,
        ne_long=NE_LNG,
        sw_lat=SW_LAT,
        sw_long=SW_LNG,
        zoom_value=ZOOM,
        price_min=0,
        price_max=0,
        currency="AED",
        proxy_url="",
    )
    
    print(f"✅ Résultats : {len(results)} listings")
    
    # Chercher notre room_id
    found = False
    for i, item in enumerate(results):
        rid = str(item.get("room_id", ""))
        if rid == ROOM_ID:
            position = i + 1
            print(f"\n🎯 TROUVÉ ! Position #{position} sur {len(results)}")
            print(f"   Nom : {item.get('name', 'N/A')}")
            print(f"   Prix : {item.get('price', 'N/A')}")
            found = True
            break
    
    if not found:
        print(f"\n❌ Room ID {ROOM_ID} NON TROUVÉ dans les {len(results)} résultats")
        print("\n📋 Premiers 10 IDs trouvés :")
        for i, item in enumerate(results[:10]):
            print(f"   {i+1}. {item.get('room_id')}")
    
    print("\n" + "=" * 70)
    print("FIN")
    print("=" * 70)


if __name__ == "__main__":
    main()
