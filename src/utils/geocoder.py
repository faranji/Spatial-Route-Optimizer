import googlemaps
import streamlit as st

# Streamlit secrets üzerinden API anahtarını güvenli bir şekilde alıyoruz
try:
    API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
    gmaps = googlemaps.Client(key=API_KEY)
except Exception as e:
    print(f"API Key yüklenemedi: {e}")
    gmaps = None

def get_coordinates(location_name: str) -> dict:
    """
    Girilen metni Google Maps Geocoding API kullanarak koordinatlara çevirir.
    Hatalı yazımları düzeltir ve sadece Türkiye'deki sonuçları getirir.
    """
    if not gmaps:
        return {}
        
    try:
        # components={"country": "TR"} ile aramayı sadece Türkiye'ye kilitliyoruz
        geocode_result = gmaps.geocode(location_name, components={"country": "TR"})
        
        results = {}
        
        # Gelen en iyi 5 sonucu al ve SRO'nun anlayacağı sözlük formatına çevir
        for place in geocode_result[:5]:
            tam_adres = place['formatted_address']
            lat = place['geometry']['location']['lat']
            lon = place['geometry']['location']['lng']
            
            results[tam_adres] = (lat, lon)
            
        return results
        
    except Exception as e:
        print(f"Google Maps Hatası: {e}")
        return {}