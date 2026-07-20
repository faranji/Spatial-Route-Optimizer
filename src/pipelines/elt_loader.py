import os
import json
from typing import List, Dict, Any
import sys

# Add the src directory to the Python path to avoid import errors
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import supabase

def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    """Reads a JSON file and parses it, handling various nested structures."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # EĞER DATA BİR SÖZLÜKSE (DICTIONARY)
    if isinstance(data, dict):
        
        # 1. (GeoJSON: data -> stationList -> features)
        if "data" in data and isinstance(data["data"], dict):
            if "stationList" in data["data"] and "features" in data["data"]["stationList"]:
                return data["data"]["stationList"]["features"]
                
        # 2. PETROL OFİSİ FORMATI
        if "Values" in data:
            return data["Values"]
            
        # 3. ZES FORMATI
        extracted_stations = []
        if "stations" in data and isinstance(data["stations"], list):
            extracted_stations.extend(data["stations"])
        
        if "stationLocations" in data and isinstance(data["stationLocations"], list):
            extracted_stations.extend(data["stationLocations"])
            
        # Eğer içinden Zes verisi çıktıysa birleşik listeyi döndür
        if extracted_stations:
            return extracted_stations
            
        return [data]
        
    # EĞER DATA BİR LİSTE İSE (LIST)
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            # Liste içinde Petrol Ofisi formatı
            if "Values" in data[0]:
                all_values = []
                for block in data:
                    if "Values" in block:
                        all_values.extend(block["Values"])
                return all_values
            # Liste içinde Zes formatı
            if "stations" in data[0]:
                all_stations = []
                for block in data:
                    if "stations" in block:
                        all_stations.extend(block["stations"])
                return all_stations
        return data
        
    return []

def insert_to_supabase(data: List[Dict[str, Any]], provider_name: str, station_type: str, batch_size: int = 500):
    """Inserts data into the Supabase raw_stations table in batches."""
    
    total_records = len(data)
    print(f"Starting ingestion for provider: {provider_name} (Type: {station_type}). Total records: {total_records}")
    
    formatted_data = []
    for item in data:
        # JSON verisinin içine 'station_type' bilgisini enjekte ediyoruz
        item["gasgraph_station_type"] = station_type
        formatted_data.append({
            "provider": provider_name, 
            "raw_data": item
        })
    
    # Send data in small batches to prevent API timeout issues
    for i in range(0, total_records, batch_size):
        batch = formatted_data[i:i+batch_size]
        try:
            # Supabase Insert operation
            supabase.table("raw_stations").insert(batch).execute()
            print(f"  Success - {provider_name}: {i + len(batch)} / {total_records} records inserted.")
        except Exception as e:
            print(f"  Error inserting batch at index {i} for {provider_name}: {e}")

def main():
    data_sources = [
        {"dir": "turkey-gas-station-data/fuel-stations", "type": "fuel"},
        {"dir": "turkey-gas-station-data/electric-stations", "type": "ev"}
    ]

    for source in data_sources:
        data_dir = source["dir"]
        station_type = source["type"]
        
        # Klasör yoksa hata vermeden diğerine geçsin
        if not os.path.exists(data_dir):
            print(f"Warning: Directory {data_dir} not found.")
            continue

        json_files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
        
        if not json_files:
            print(f"No JSON files found in {data_dir}.")
            continue

        print(f"\n--- Processing Directory: {data_dir} ---")
        for file_name in json_files:
            file_path = os.path.join(data_dir, file_name)
            
            # Extract provider name (e.g., "shell.json" -> "Shell", "zes.json" -> "Zes")
            provider_name = os.path.splitext(file_name)[0].capitalize() 
            
            try:
                raw_data = load_json_file(file_path)
                insert_to_supabase(raw_data, provider_name, station_type)
            except Exception as e:
                 print(f"Failed to process {file_name}. Error: {e}")
                 
    print("\nAll data successfully loaded into the Supabase raw_stations table.")

if __name__ == "__main__":
    main()