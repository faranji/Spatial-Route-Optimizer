import googlemaps
import streamlit as st

import os
import streamlit as st


def load_google_maps_api_key() -> str:
    # Önce işletim sistemi environment variable'ını kontrol et.
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if api_key:
        return api_key

    # Ardından Streamlit secrets'i kontrol et.
    try:
        api_key = st.secrets["GOOGLE_MAPS_API_KEY"]
        if api_key:
            return api_key
    except Exception:
        pass

    # Eski config.py yapısıyla geriye dönük uyumluluk.
    try:
        from config import GOOGLE_MAPS_API_KEY as config_api_key

        if config_api_key:
            return config_api_key
    except (ImportError, ModuleNotFoundError):
        pass

    raise RuntimeError(
        "GOOGLE_MAPS_API_KEY was not found. "
        "Add it to .streamlit/secrets.toml or Streamlit Cloud secrets."
    )

GOOGLE_MAPS_API_KEY = load_google_maps_api_key()

gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def get_coordinates(location_name: str) -> dict:
    if not gmaps:
        return {}
        
    try:
        geocode_result = gmaps.geocode(location_name, components={"country": "TR"})
        
        results = {}
        
        for place in geocode_result[:5]:
            tam_adres = place['formatted_address']
            lat = place['geometry']['location']['lat']
            lon = place['geometry']['location']['lng']
            
            results[tam_adres] = (lat, lon)
            
        return results
        
    except Exception as e:
        print(f"Google Maps Error: {e}")
        return {}