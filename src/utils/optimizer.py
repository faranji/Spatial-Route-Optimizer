import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

Coordinate = Tuple[float, float]
OSRM_BASE_URL = "https://router.project-osrm.org"
OSRM_HEADERS = {
    "User-Agent": "SRO-Spatial-Route-Optimizer/1.0"
}


def _normalize_coordinate(coords: Sequence[float]) -> Coordinate:
    """convert coordinates to (lat, lon) tuple."""
    if coords is None or len(coords) != 2:
        raise ValueError("wrong coord type.")

    lat = float(coords[0])
    lon = float(coords[1])

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"invalid coord: ({lat}, {lon})")

    return lat, lon


def _request_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    retries: int = 3,
) -> Dict[str, Any]:
    """repeat if error."""
    last_error: Optional[Exception] = None

    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                params=params,
                headers=OSRM_HEADERS,
                timeout=timeout,
            )

            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"error: HTTP {response.status_code}",
                    response=response,
                )

            response.raise_for_status()
            return response.json()

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))

    raise RuntimeError(f"couldn't connect to OSRM service: {last_error}")


def vectorized_haversine(
    lat1: float,
    lon1: float,
    lat2_array: Any,
    lon2_array: Any,
) -> np.ndarray:
    earth_radius_km = 6371.0

    lat1_rad = np.radians(np.asarray(lat1, dtype=float))
    lon1_rad = np.radians(np.asarray(lon1, dtype=float))
    lat2_rad = np.radians(np.asarray(lat2_array, dtype=float))
    lon2_rad = np.radians(np.asarray(lon2_array, dtype=float))

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(dlon / 2.0) ** 2
    )
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arcsin(np.sqrt(a))

    return earth_radius_km * c


def get_osrm_route(coords_list: Sequence[Sequence[float]]) -> Dict[str, Any]:
    normalized_coords = [_normalize_coordinate(coords) for coords in coords_list]

    if len(normalized_coords) < 2:
        raise ValueError("Rota için en az iki koordinat gereklidir.")

    waypoints = ";".join(
        f"{lon:.7f},{lat:.7f}" for lat, lon in normalized_coords
    )
    url = f"{OSRM_BASE_URL}/route/v1/driving/{waypoints}"

    data = _request_json(
        url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        },
        timeout=35,
    )

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(
            f"OSRM rota oluşturamadı: {data.get('message', data.get('code'))}"
        )

    route = data["routes"][0]
    geometry = route.get("geometry", {}).get("coordinates", [])
    road_geometry = [(float(lat), float(lon)) for lon, lat in geometry]

    return {
        "geometry": road_geometry,
        "distance_km": float(route.get("distance", 0.0)) / 1000.0,
        "duration_minutes": float(route.get("duration", 0.0)) / 60.0,
    }


def get_real_road_route(coords_list: Sequence[Sequence[float]]) -> List[Coordinate]:
    """Harita için gerçek yol geometrisini döndürür; hata olursa düz çizgiye düşer."""
    normalized_coords = [_normalize_coordinate(coords) for coords in coords_list]

    try:
        return get_osrm_route(normalized_coords)["geometry"]
    except Exception as exc:
        print(f"OSRM rota geometrisi hatası: {exc}")
        return normalized_coords


@lru_cache(maxsize=1024)
def _cached_osrm_route_distance(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> float:
    result = get_osrm_route(
        [(start_lat, start_lon), (end_lat, end_lon)]
    )
    return float(result["distance_km"])


def get_osrm_route_distance(
    start_coords: Sequence[float],
    end_coords: Sequence[float],
) -> float:
    """calculates km between two coordinates."""
    start_lat, start_lon = _normalize_coordinate(start_coords)
    end_lat, end_lon = _normalize_coordinate(end_coords)

    return _cached_osrm_route_distance(
        round(start_lat, 7),
        round(start_lon, 7),
        round(end_lat, 7),
        round(end_lon, 7),
    )


def get_osrm_distance_matrix(
    coords_list: Sequence[Sequence[float]],
) -> np.ndarray:
    """Koordinatlar arasındaki gerçek sürüş mesafesi matrisini KM olarak döndürür."""
    normalized_coords = [_normalize_coordinate(coords) for coords in coords_list]

    if len(normalized_coords) < 2:
        raise ValueError("Mesafe matrisi için en az iki koordinat gereklidir.")

    coordinate_string = ";".join(
        f"{lon:.7f},{lat:.7f}" for lat, lon in normalized_coords
    )
    url = f"{OSRM_BASE_URL}/table/v1/driving/{coordinate_string}"

    data = _request_json(
        url,
        params={"annotations": "distance"},
        timeout=40,
    )

    if data.get("code") != "Ok" or "distances" not in data:
        raise RuntimeError(
            "OSRM mesafe matrisi oluşturamadı: "
            f"{data.get('message', data.get('code'))}"
        )

    return np.array(
        [
            [
                np.nan if value is None else float(value) / 1000.0
                for value in row
            ]
            for row in data["distances"]
        ],
        dtype=float,
    )


def _station_records_for_ui(
    candidates_df: pd.DataFrame,
    leg_index: int,
    global_stop_index: int,
) -> List[Dict[str, Any]]:
    """İç hesaplama sütunlarını temizleyip UI için kayıt listesi üretir."""
    records: List[Dict[str, Any]] = []

    for _, row in candidates_df.iterrows():
        record = {
            key: value
            for key, value in row.to_dict().items()
            if not str(key).startswith("_")
        }

        record["lat"] = float(record["lat"])
        record["lon"] = float(record["lon"])
        record["detour"] = float(record.get("detour", 0.0))
        record["cost"] = float(record.get("cost", 0.0))
        record["distance_from_previous_km"] = float(
            row["_road_from_current"]
        )
        record["distance_to_leg_end_km"] = float(
            row["_road_to_destination"]
        )
        record["leg_index"] = int(leg_index)
        record["global_stop_index"] = int(global_stop_index)
        records.append(record)

    return records


def calculate_route(
    start_coords: Sequence[float],
    end_coords: Sequence[float],
    current_range: float,
    max_range: float,
    df_stations: pd.DataFrame,
    wc_bonus: float = 5.0,
    market_bonus: float = 3.0,
    force_forward: bool = False,
    range_safety_ratio: float = 0.80,
    choice_indices: Optional[Sequence[int]] = None,
    choice_offset: int = 0,
    leg_index: int = 0,
    max_stops: int = 20,
    max_osrm_candidates: int = 15,
    tortuosity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    calculates the real OSRM route.
    """
    del tortuosity

    if not 0.50 <= float(range_safety_ratio) <= 1.0:
        raise ValueError("range_safety_ratio 0.50 ile 1.00 arasında olmalıdır.")

    if float(current_range) <= 0 or float(max_range) <= 0:
        raise ValueError("Menzil değerleri sıfırdan büyük olmalıdır.")

    current_loc = _normalize_coordinate(start_coords)
    end_coords_normalized = _normalize_coordinate(end_coords)
    current_remaining_range = float(current_range)

    required_columns = {
        "id",
        "lat",
        "lon",
        "provider",
        "has_wc",
        "has_market",
    }
    missing_columns = required_columns.difference(df_stations.columns)
    if missing_columns:
        raise ValueError(
            "İstasyon verisinde eksik sütunlar var: "
            + ", ".join(sorted(missing_columns))
        )

    df_work = (
        df_stations.copy()
        .dropna(subset=["id", "lat", "lon"])
        .reset_index(drop=True)
    )

    route_history: List[List[Dict[str, Any]]] = []
    selected_stops: List[Dict[str, Any]] = []
    choice_cursor = int(choice_offset)
    choices = list(choice_indices or [])

    for stop_in_leg in range(max_stops):
        direct_road_distance = get_osrm_route_distance(
            current_loc,
            end_coords_normalized,
        )

        if direct_road_distance <= current_remaining_range:
            return {
                "candidate_groups": route_history,
                "selected_stops": selected_stops,
                "next_choice_offset": choice_cursor,
                "remaining_range": max(
                    0.0,
                    current_remaining_range - direct_road_distance,
                ),
                "leg_distance_to_end_km": direct_road_distance,
            }

        if df_work.empty:
            raise ValueError("couldn't find any station(s).")

        lats = pd.to_numeric(df_work["lat"], errors="coerce").to_numpy()
        lons = pd.to_numeric(df_work["lon"], errors="coerce").to_numpy()

        valid_coordinate_mask = np.isfinite(lats) & np.isfinite(lons)
        df_work = df_work.loc[valid_coordinate_mask].reset_index(drop=True)
        lats = lats[valid_coordinate_mask]
        lons = lons[valid_coordinate_mask]

        if df_work.empty:
            raise ValueError("couldn't find any station(s).")

        air_from_current = vectorized_haversine(
            current_loc[0],
            current_loc[1],
            lats,
            lons,
        )
        air_to_destination = vectorized_haversine(
            lats,
            lons,
            end_coords_normalized[0],
            end_coords_normalized[1],
        )
        current_air_to_destination = float(
            vectorized_haversine(
                current_loc[0],
                current_loc[1],
                end_coords_normalized[0],
                end_coords_normalized[1],
            )
        )

        safe_range = current_remaining_range * float(range_safety_ratio)
        preliminary_mask = air_from_current <= safe_range
        preliminary_df = df_work.loc[preliminary_mask].copy()

        if preliminary_df.empty:
            raise ValueError(
                "couldn't find any station(s)."
            )

        preliminary_df["_air_from_current"] = air_from_current[preliminary_mask]
        preliminary_df["_air_to_destination"] = air_to_destination[preliminary_mask]
        preliminary_df["_approx_detour"] = (
            preliminary_df["_air_from_current"]
            + preliminary_df["_air_to_destination"]
            - current_air_to_destination
        ).clip(lower=0.0)

        wc_discount = (
            preliminary_df["has_wc"]
            .fillna(False)
            .astype(float)
            * float(wc_bonus)
        )
        market_discount = (
            preliminary_df["has_market"]
            .fillna(False)
            .astype(float)
            * float(market_bonus)
        )

        if force_forward:
            preliminary_forward_penalty = np.where(
                preliminary_df["_air_to_destination"]
                < current_air_to_destination,
                0.0,
                10000.0,
            )
        else:
            preliminary_forward_penalty = 0.0

        preliminary_df["_approx_cost"] = (
            preliminary_df["_approx_detour"]
            - wc_discount
            - market_discount
            + preliminary_forward_penalty
        )

        aggressive_candidates = (
            preliminary_df
            .sort_values(["_approx_cost", "_air_to_destination"])
            .head(int(max_osrm_candidates) - 5)
        )

        safe_candidates = (
            preliminary_df
            .sort_values(["_approx_cost", "_air_from_current"])
            .head(5)
        )

        shortlist = pd.concat([aggressive_candidates, safe_candidates]).drop_duplicates(subset=["id"]).copy()

        matrix_coords: List[Coordinate] = [
            current_loc,
            end_coords_normalized,
        ] + [
            (float(lat), float(lon))
            for lat, lon in zip(shortlist["lat"], shortlist["lon"])
        ]

        distance_matrix = get_osrm_distance_matrix(matrix_coords)

        base_road_distance = float(distance_matrix[0, 1])
        road_to_station = distance_matrix[0, 2:]
        station_to_destination = distance_matrix[2:, 1]

        if not np.isfinite(base_road_distance):
            raise ValueError("Başlangıç ile hedef arasında sürüş rotası bulunamadı.")

        shortlist["_road_from_current"] = road_to_station
        shortlist["_road_to_destination"] = station_to_destination

        valid_mask = (
            np.isfinite(road_to_station)
            & np.isfinite(station_to_destination)
            & (road_to_station <= safe_range)
        )

        if force_forward:
            minimum_forward_progress_km = 0.5
            valid_mask &= (
                station_to_destination
                <= base_road_distance - minimum_forward_progress_km
            )

        reachable_df = shortlist.loc[valid_mask].copy()

        if reachable_df.empty:
            if force_forward:
                raise ValueError(
                    "couldn't find any station(s)."
                )

            raise ValueError(
                "couldn't find any station(s)."
            )

        # cost =  detour - advantages + remanining range (we will go as far as we can)
        reachable_df["cost"] = (
            reachable_df["detour"]
            - wc_discount
            - market_discount
            + reachable_df["_road_to_destination"]
        ).clip(lower=0.0)


        wc_discount = (
            reachable_df["has_wc"]
            .fillna(False)
            .astype(float)
            * float(wc_bonus)
        )
        market_discount = (
            reachable_df["has_market"]
            .fillna(False)
            .astype(float)
            * float(market_bonus)
        )

        reachable_df["cost"] = (
            reachable_df["detour"]
            - wc_discount
            - market_discount
        )

        top_candidates = (
            reachable_df
            .sort_values(["cost", "_road_to_destination"])
            .drop_duplicates(subset=["id"])
            .head(3)
            .copy()
        )

        if top_candidates.empty:
            raise ValueError("couldn't choose any station(s).")

        candidate_records = _station_records_for_ui(
            top_candidates,
            leg_index=leg_index,
            global_stop_index=choice_cursor,
        )
        route_history.append(candidate_records)

        requested_choice = choices[choice_cursor] if choice_cursor < len(choices) else 0
        try:
            selected_index = int(requested_choice)
        except (TypeError, ValueError):
            selected_index = 0

        if selected_index < 0 or selected_index >= len(candidate_records):
            selected_index = 0

        selected_station = dict(candidate_records[selected_index])
        selected_station["selected_option_index"] = selected_index
        selected_stops.append(selected_station)

        current_loc = (
            float(selected_station["lat"]),
            float(selected_station["lon"]),
        )
        current_remaining_range = float(max_range)
        choice_cursor += 1

        df_work = (
            df_work[df_work["id"] != selected_station["id"]]
            .reset_index(drop=True)
        )

    raise ValueError(
        f"too much stops: {max_stops}"
    )


def calculate_multi_waypoint_route(
    waypoints_list: Sequence[Sequence[float]],
    current_range: float,
    max_range: float,
    df_stations: pd.DataFrame,
    wc_bonus: float = 5.0,
    market_bonus: float = 3.0,
    force_forward: bool = False,
    range_safety_ratio: float = 0.80,
    choice_indices: Optional[Sequence[int]] = None,
    tortuosity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    divides route into pieces.
    """
    del tortuosity

    normalized_waypoints = [
        _normalize_coordinate(coords) for coords in waypoints_list
    ]

    if len(normalized_waypoints) < 2:
        raise ValueError("please enter the start and final destinations")

    all_candidate_groups: List[List[Dict[str, Any]]] = []
    all_selected_stops: List[Dict[str, Any]] = []
    route_coords: List[Coordinate] = [normalized_waypoints[0]]

    simulated_range = float(current_range)
    choice_cursor = 0
    choices = list(choice_indices or [])

    for leg_index in range(len(normalized_waypoints) - 1):
        start_leg = normalized_waypoints[leg_index]
        end_leg = normalized_waypoints[leg_index + 1]

        leg_plan = calculate_route(
            start_coords=start_leg,
            end_coords=end_leg,
            current_range=simulated_range,
            max_range=max_range,
            df_stations=df_stations,
            wc_bonus=wc_bonus,
            market_bonus=market_bonus,
            force_forward=force_forward,
            range_safety_ratio=range_safety_ratio,
            choice_indices=choices,
            choice_offset=choice_cursor,
            leg_index=leg_index,
        )

        all_candidate_groups.extend(leg_plan["candidate_groups"])
        all_selected_stops.extend(leg_plan["selected_stops"])

        for selected_stop in leg_plan["selected_stops"]:
            route_coords.append(
                (
                    float(selected_stop["lat"]),
                    float(selected_stop["lon"]),
                )
            )

        route_coords.append(end_leg)
        simulated_range = float(leg_plan["remaining_range"])
        choice_cursor = int(leg_plan["next_choice_offset"])

    route_summary = get_osrm_route(route_coords)
    selected_choice_indices = [
        int(stop.get("selected_option_index", 0))
        for stop in all_selected_stops
    ]

    return {
        "candidate_groups": all_candidate_groups,
        "selected_stops": all_selected_stops,
        "selected_choice_indices": selected_choice_indices,
        "route_coords": route_coords,
        "road_geometry": route_summary["geometry"],
        "distance_km": float(route_summary["distance_km"]),
        "duration_minutes": float(route_summary["duration_minutes"]),
        "remaining_range_at_destination": float(simulated_range),
    }