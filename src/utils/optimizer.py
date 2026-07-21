import numpy as np
import pandas as pd
import requests

def vectorized_haversine(lat1, lon1, lat2_array, lon2_array):
    """
    NumPy Vektörizasyonu ile 1 noktanın, 10.000 noktaya olan mesafesini 
    satır satır değil, matris hesabı ile saniyenin binde birinde hesaplar.
    """
    R = 6371.0 # Dünya yarıçapı
    
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2, lon2 = np.radians(lat2_array), np.radians(lon2_array)
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    
    return R * c

def get_real_road_route(coords_list):
    """Koordinatları OSRM API'ına gönderip gerçek virajları ortaya çıkarır."""
    waypoints = ";".join([f"{lon},{lat}" for lat, lon in coords_list])
    url = f"http://router.project-osrm.org/route/v1/driving/{waypoints}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("code") == "Ok":
            route_geometry = data["routes"][0]["geometry"]["coordinates"]
            return [(lat, lon) for lon, lat in route_geometry]
    except Exception as e:
        print(f"OSRM API Hatası: {e}")
        
    return coords_list

def calculate_route(start_coords, end_coords, current_range, max_range, df_stations, wc_bonus=5.0, market_bonus=3.0, tortuosity=1.3, force_forward=False):
    route_history = []
    current_loc = start_coords
    current_remaining_range = current_range
    df_work = df_stations.copy().reset_index(drop=True)
    dist_to_destination = vectorized_haversine(current_loc[0], current_loc[1], end_coords[0], end_coords[1])
    stops = 0
    max_stops = 20 
    
    while (dist_to_destination * tortuosity) > current_remaining_range and stops < max_stops:
        lats = df_work['lat'].values
        lons = df_work['lon'].values
        dists = vectorized_haversine(current_loc[0], current_loc[1], lats, lons)
        
        safe_range = current_remaining_range * 0.80
        reachable_mask = dists <= safe_range
        
        if not reachable_mask.any():
            raise ValueError("Menzil içinde uygun istasyon bulunamadı. Lütfen başlangıç menzilini artırın.")
            
        reachable_df = df_work[reachable_mask].copy()

        dists_to_station = dists[reachable_mask]
        dists_to_end = vectorized_haversine(reachable_df['lat'].values, reachable_df['lon'].values, end_coords[0], end_coords[1])
        
        if force_forward:
            backward_mask = dists_to_end > dist_to_destination
            reachable_df.loc[backward_mask, 'cost'] += 10000.0
            
        detour = dists_to_station + dists_to_end - dist_to_destination
        wc_discount = reachable_df['has_wc'].fillna(False).astype(int).values * wc_bonus
        market_discount = reachable_df['has_market'].fillna(False).astype(int).values * market_bonus
        
        reachable_df['detour'] = detour
        reachable_df['cost'] = detour - wc_discount - market_discount
        
        top_3_stations = reachable_df.sort_values('cost').drop_duplicates(subset=['provider']).head(3) # aynı istasyonu vermesin
        route_history.append(top_3_stations.to_dict('records'))
        
        best_station = top_3_stations.iloc[0] 
        current_loc = (best_station['lat'], best_station['lon'])
        current_remaining_range = max_range
        dist_to_destination = vectorized_haversine(current_loc[0], current_loc[1], end_coords[0], end_coords[1])
        stops += 1
        
        df_work = df_work[df_work['id'] != best_station['id']].reset_index(drop=True)
        
    return route_history

def calculate_multi_waypoint_route(waypoints_list, current_range, max_range, df_stations, **kwargs):
    """
    Kullanıcının girdiği sıralı rotayı (Örn: İstanbul -> Kalkan -> Kaş) bacaklara böler.
    Her bacak için calculate_route fonksiyonunu ardışık (recursive) olarak çalıştırır.
    """
    full_trip_stops = []
    simulated_range = current_range
    
    for i in range(len(waypoints_list) - 1):
        start_leg = waypoints_list[i]
        end_leg = waypoints_list[i+1]
    
        leg_history = calculate_route(start_leg, end_leg, simulated_range, max_range, df_stations, **kwargs)
        full_trip_stops.extend(leg_history)
        
        simulated_range = max_range 
        
    return full_trip_stops