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
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict

import pyairbnb
from pyairbnb.search import headers_global, treament
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests

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
# CUSTOM SEARCH WITH GUESTS
# ==============================================================================
def search_with_guests(check_in, check_out, ne_lat, ne_lng, sw_lat, sw_lng, zoom, adults, currency="AED"):
    """
    Recherche personnalisée avec filtre par nombre de voyageurs.
    Basée sur pyairbnb.search mais avec le paramètre adults ajouté.
    """
    
    # API Key
    api_key = pyairbnb.get_api_key("")
    
    # Hash dynamique
    try:
        operation_id = pyairbnb.fetch_stays_search_hash("")
    except:
        operation_id = '9f945886dcc032b9ef4ba770d9132eb0aa78053296b5405483944c229617b00b'
    
    base_url = f"https://www.airbnb.com/api/v3/StaysSearch/{operation_id}"
    query_params = {
        "operationName": "StaysSearch",
        "locale": "en",
        "currency": currency,
    }
    url = f"{base_url}?{urlencode(query_params)}"
    
    # Calculer nombre de nuits
    check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
    check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
    nights = (check_out_date - check_in_date).days
    
    # Paramètres de recherche
    raw_params = [
        {"filterName": "cdnCacheSafe", "filterValues": ["false"]},
        {"filterName": "channel", "filterValues": ["EXPLORE"]},
        {"filterName": "checkin", "filterValues": [check_in]},
        {"filterName": "checkout", "filterValues": [check_out]},
        {"filterName": "datePickerType", "filterValues": ["calendar"]},
        {"filterName": "flexibleTripLengths", "filterValues": ["one_week"]},
        {"filterName": "itemsPerGrid", "filterValues": ["50"]},
        {"filterName": "monthlyLength", "filterValues": ["3"]},
        {"filterName": "neLat", "filterValues": [str(ne_lat)]},
        {"filterName": "neLng", "filterValues": [str(ne_lng)]},
        {"filterName": "priceFilterInputType", "filterValues": ["0"]},
        {"filterName": "priceFilterNumNights", "filterValues": [str(nights)]},
        {"filterName": "refinementPaths", "filterValues": ["/homes"]},
        {"filterName": "screenSize", "filterValues": ["large"]},
        {"filterName": "searchByMap", "filterValues": ["true"]},
        {"filterName": "swLat", "filterValues": [str(sw_lat)]},
        {"filterName": "swLng", "filterValues": [str(sw_lng)]},
        {"filterName": "tabId", "filterValues": ["home_tab"]},
        {"filterName": "version", "filterValues": ["1.8.3"]},
        {"filterName": "zoomLevel", "filterValues": [str(zoom)]},
    ]
    
    # Bloc voyageurs complet (Airbnb attend souvent l'ensemble)
    raw_params.append({"filterName": "adults", "filterValues": [str(adults)]})
    raw_params.append({"filterName": "children", "filterValues": ["0"]})
    raw_params.append({"filterName": "infants", "filterValues": ["0"]})
    raw_params.append({"filterName": "pets", "filterValues": ["0"]})
    
    input_data = {
        "operationName": "StaysSearch",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": operation_id,
            },
        },
        "variables": {
            "skipExtendedSearchParams": False,
            "includeMapResults": True,
            "isLeanTreatment": False,
            "aiSearchEnabled": False,
            "staysMapSearchRequestV2": {
                "cursor": "",
                "requestedPageType": "STAYS_SEARCH",
                "metadataOnly": False,
                "source": "structured_search_input_header",
                "searchType": "user_map_move",
                "treatmentFlags": treament,
                "rawParams": raw_params,
            },
            "staysSearchRequest": {
                "cursor": "",
                "maxMapItems": 9999,
                "requestedPageType": "STAYS_SEARCH",
                "metadataOnly": False,
                "source": "structured_search_input_header",
                "searchType": "user_map_move",
                "treatmentFlags": treament,
                "rawParams": raw_params,
            },
        },
    }
    
    headers = headers_global.copy()
    headers["X-Airbnb-Api-Key"] = api_key
    
    response = curl_requests.post(url, json=input_data, headers=headers, impersonate="chrome124")
    
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
    
    data = response.json()
    
    all_listings = []
    
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
            
            price_info = item.get("pricingQuote", {}).get("structuredStayDisplayPrice", {})
            primary_line = price_info.get("primaryLine", {})
            price_amount = primary_line.get("price", "")
            
            price_match = re.search(r'[\d,]+', str(price_amount))
            price = float(price_match.group().replace(",", "")) if price_match else None
            
            if listing_id:
                all_listings.append({
                    "room_id": str(listing_id),
                    "name": listing.get("name", ""),
                    "price": {"unit": {"amount": price}} if price else None,
                })
    except Exception as e:
        print(f"      ⚠️ Erreur extraction searchResults: {e}")
    
    try:
        map_results = (data
                      .get("data", {})
                      .get("presentation", {})
                      .get("staysSearch", {})
                      .get("results", {})
                      .get("mapSearchResults", []))
        
        existing_ids = {l["room_id"] for l in all_listings}
        
        for item in map_results:
            listing = item.get("listing", {})
            listing_id = listing.get("id", "")
            if isinstance(listing_id, str) and "StayListing:" in listing_id:
                listing_id = listing_id.replace("StayListing:", "")
            
            if listing_id and str(listing_id) not in existing_ids:
                all_listings.append({
                    "room_id": str(listing_id),
                    "name": listing.get("name", ""),
                    "price": None,
                })
    except:
        pass
    
    return all_listings
