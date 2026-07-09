import os
import json
from typing import List, Dict, Any
import sys

# Add the src directory to the Python path to avoid import errors
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import supabase


def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    """Reads a JSON file and parses it into a Python dictionary or list."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # If the data is a single dictionary, convert it to a list for batch insertion
    return data if isinstance(data, list) else [data]

def insert_to_supabase(data: List[Dict[str, Any]], provider_name: str, batch_size: int = 500):
    """Inserts data into the Supabase raw_stations table in batches."""
    
    total_records = len(data)
    print(f"Starting ingestion for provider: {provider_name}. Total records: {total_records}")
    
    # Format the data to match the raw_stations schema (JSONB column)
    formatted_data = [{"provider": provider_name, "raw_data": item} for item in data]
    
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
    # Define the directory containing the raw JSON files
    data_dir = "turkey-gas-station-data/raw-json" 

    # List all .json files in the directory
    json_files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"No JSON files found in {data_dir}.")
        return

    for file_name in json_files:
        file_path = os.path.join(data_dir, file_name)
        
        # Extract provider name from file name (e.g., "shell.json" -> "Shell")
        provider_name = os.path.splitext(file_name)[0].capitalize() 
        
        try:
            raw_data = load_json_file(file_path)
            insert_to_supabase(raw_data, provider_name)
        except Exception as e:
             print(f"Failed to process {file_name}. Error: {e}")
             
    print("\nAll data successfully loaded into the Supabase raw_stations table.")

if __name__ == "__main__":
    main()