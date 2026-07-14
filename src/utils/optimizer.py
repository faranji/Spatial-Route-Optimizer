import math
import pandas as pd

def calculate_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    İki koordinat arasındaki kuş uçuşu mesafeyi (KM) hesaplar.
    """
    # İPUCU: Dünyanın yarıçapı R = 6371 km'dir.
    R = 6371
    # TODO 1: Enlem ve boylamları math.radians() ile radyana çevir.
    radian_lat1 = math.radians(lat1)
    radian_lat2 = math.radians(lat2)
    radian_lon1 = math.radians(lon1)
    radian_lon2 = math.radians(lon2)

    dlat = radian_lat2 - radian_lat1
    dlon = radian_lon2 - radian_lon1

    # TODO 2: Haversine formülünü uygula: a = sin²(Δlat/2) + cos(lat1)*cos(lat2)*sin²(Δlon/2)
    a = (math.sin(dlat/2))**2 + (math.cos(radian_lat1))*(math.cos(radian_lat2))*(math.sin(dlon/2))**2

    # TODO 3: c = 2 * atan2(√a, √(1−a)) hesapla.
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                  
    # TODO 4: Sonuç = R * c döndür.
    return R*c
    pass

def calculate_station_cost(station_lat, station_lon, start_lat, start_lon, end_lat, end_lon, 
                           has_wc, has_market, wc_bonus=5.0, market_bonus=3.0) -> float:
    """
    İstasyonun algoritma için "Maliyet" puanını hesaplar. Düşük maliyet = Daha iyi istasyon.
    """
    # TODO 1: start_lat, start_lon ile station_lat, station_lon arasındaki mesafeyi hesapla.
    start_to_station = calculate_haversine(start_lat, start_lon, station_lat, station_lon)

    # TODO 2: station_lat, station_lon ile end_lat, end_lon arasındaki mesafeyi hesapla.
    station_to_end = calculate_haversine(station_lat, station_lon, end_lat, end_lon)

    # TODO 3: start ile end arasındaki direkt mesafeyi hesapla (Sapmayı bulmak için).
    di_route = calculate_haversine(start_lat, start_lon, end_lat, end_lon)

    # TODO 4: Sapma (Detour) = (Start->Station) + (Station->End) - (Start->End)
    detour = start_to_station + station_to_end - di_route

    # TODO 5: Toplam Maliyet = Detour. Eğer has_wc True ise maliyetten wc_bonus'u çıkar. Market varsa market_bonus'u çıkar.
    cost_val = detour
    
    if has_wc:
        cost_val -= wc_bonus
    if has_market:
        cost_val -= market_bonus
        
    return cost_val
    pass

"""
    while dist_to_destination > current_remaining_range:
        for station in calculate_haversine(df_stations-current_loc) < current_remaining_range:
            calculate_station_cost(station)
"""

def calculate_route(start_coords, end_coords, current_range, max_range, df_stations, wc_bonus=5.0, market_bonus=3.0):
    route_history = []
    current_loc = start_coords
    current_remaining_range = current_range
    
    dist_to_destination = calculate_haversine(current_loc[0], current_loc[1], end_coords[0], end_coords[1])
    
    while dist_to_destination > current_remaining_range:
        # Mesafeleri hesapla
        df_stations['dist_from_current'] = df_stations.apply(
            lambda row: calculate_haversine(current_loc[0], current_loc[1], row['lat'], row['lon']), axis=1
        )
        
        # Aday kümeyi filtrele
        reachable_stations = df_stations[df_stations['dist_from_current'] <= current_remaining_range].copy()
        
        if reachable_stations.empty:
            break # Menzil içinde istasyon yoksa döngüyü kır
            
        # Maliyetleri hesapla
        reachable_stations['cost'] = reachable_stations.apply(
            lambda row: calculate_station_cost(
                row['lat'], row['lon'], 
                current_loc[0], current_loc[1], 
                end_coords[0], end_coords[1], 
                row['has_wc'], row['has_market'],
                wc_bonus, market_bonus
            ), axis=1
        )
        
        # En düşük maliyetli (en iyi) istasyonu seç
        best_station = reachable_stations.loc[reachable_stations['cost'].idxmin()]
        
        # Geçmişe ekle ve durumu güncelle
        route_history.append(best_station.to_dict())
        current_loc = (best_station['lat'], best_station['lon'])
        current_remaining_range = max_range
        dist_to_destination = calculate_haversine(current_loc[0], current_loc[1], end_coords[0], end_coords[1])
        
    return route_history