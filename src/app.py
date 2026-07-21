import os
import ssl
import sys
from pathlib import Path
from typing import Any, Dict, List

ssl._create_default_https_context = ssl._create_unverified_context

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from streamlit_searchbox import st_searchbox
from supabase import Client, create_client

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from utils.geocoder import get_coordinates
from utils.optimizer import calculate_multi_waypoint_route

try:
    from config import supabase
except ModuleNotFoundError:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(supabase_url, supabase_key)


st.set_page_config(
    page_title="SRO | Spatial Route Optimizer",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🚗",
)


# ==========================================
# CUSTOM CSS
# ==========================================
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

        html, body, p, div, span, label {
            font-family: 'Poppins', sans-serif;
        }

        h1, h2, h3 {
            font-family: 'Poppins', sans-serif !important;
            font-weight: 600 !important;
            color: #2C3E50 !important;
        }

        .material-icons, [class*="icon"], [data-testid="stIconMaterial"] {
            font-family: 'Material Symbols Rounded' !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# SESSION STATE
# ==========================================
def initialize_session_state() -> None:
    defaults = {
        "remaining_range": 150,
        "current_location": "Istanbul",
        "waypoint_count": 0,
        "route_plan": None,
        "route_request": None,
        "route_needs_recompute": False,
        "route_status_message": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


# ==========================================
# LOAD CLOUD DATA
# ==========================================
@st.cache_data(ttl=3600)
def load_gold_data() -> pd.DataFrame:
    all_data: List[Dict[str, Any]] = []
    offset = 0
    chunk_size = 1000

    while True:
        response = (
            supabase.table("sro_gold_stations")
            .select("*")
            .range(offset, offset + chunk_size - 1)
            .execute()
        )
        chunk = response.data

        if not chunk:
            break

        all_data.extend(chunk)

        if len(chunk) < chunk_size:
            break

        offset += chunk_size

    loaded_df = pd.DataFrame(all_data)

    if loaded_df.empty:
        raise RuntimeError("sro_gold_stations tablosundan veri alınamadı.")

    return loaded_df


try:
    df = load_gold_data()
except Exception as exc:
    st.error(f"İstasyon verisi yüklenemedi: {exc}")
    st.stop()


# ==========================================
# HELPERS
# ==========================================
def create_search_function(box_key: str):
    """Her arama kutusu için bağımsız seçenek hafızası oluşturur."""

    def search_for_dropdown(searchterm: str):
        # DÜZELTME 3: 3 harften kısa yazımlarda boşuna API isteği atıp sistemi kilitleme
        if not searchterm or len(searchterm) < 3:
            return st.session_state.get(f"{box_key}_options", [])

        results = get_coordinates(searchterm)

        if isinstance(results, dict):
            options = [
                (address, coords)
                for address, coords in results.items()
            ]
            st.session_state[f"{box_key}_options"] = options
            return options

        return []

    return search_for_dropdown


def clear_station_radio_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("radio_stop_"):
            del st.session_state[key]


def build_filtered_stations(
    source_df: pd.DataFrame,
    station_type: str,
    selected_brand: str,
    strict_requirement: bool,
) -> pd.DataFrame:
    result = source_df[source_df["station_type"] == station_type].copy()

    if selected_brand != "All Brands":
        result = result[result["provider"] == selected_brand]

    if strict_requirement:
        if station_type == "fuel":
            result = result[result["has_lpg"].fillna(False) == True]
        else:
            result = result[result["has_fast_charge"].fillna(False) == True]

    return result.dropna(subset=["id", "lat", "lon"]).reset_index(drop=True)


def run_route_optimization(
    route_request: Dict[str, Any],
    choice_indices: List[int],
) -> Dict[str, Any]:
    request_stations = build_filtered_stations(
        source_df=df,
        station_type=route_request["station_type"],
        selected_brand=route_request["selected_brand"],
        strict_requirement=route_request["strict_requirement"],
    )

    if request_stations.empty:
        raise ValueError("Seçilen filtrelere uygun istasyon bulunamadı.")

    route_plan = calculate_multi_waypoint_route(
        waypoints_list=route_request["waypoints"],
        current_range=route_request["current_range"],
        max_range=route_request["max_range"],
        df_stations=request_stations,
        wc_bonus=route_request["wc_bonus"],
        market_bonus=route_request["market_bonus"],
        force_forward=route_request["force_forward"],
        range_safety_ratio=route_request["range_safety_ratio"],
        choice_indices=choice_indices,
    )

    route_plan["scanned_station_count"] = len(request_stations)
    return route_plan


def handle_station_change(changed_stop_index: int) -> None:
    """Bir istasyon seçimi değişince sonraki seçimleri sıfırlar."""
    existing_plan = st.session_state.get("route_plan") or {}
    group_count = len(existing_plan.get("candidate_groups", []))

    for next_index in range(changed_stop_index + 1, group_count):
        key = f"radio_stop_{next_index}"
        if key in st.session_state:
            del st.session_state[key]

    st.session_state.route_needs_recompute = True


def format_station_name(candidate: Dict[str, Any]) -> str:
    provider = str(candidate.get("provider") or "Unknown").replace("_", " ").title()

    detail = None
    for field_name in ("station_name", "name", "address", "district"):
        candidate_value = candidate.get(field_name)
        if candidate_value is not None and pd.notna(candidate_value):
            candidate_text = str(candidate_value).strip()
            if candidate_text and candidate_text.lower() != "nan":
                detail = candidate_text
                break

    if detail and str(detail).strip().lower() != provider.lower():
        shortened = str(detail).strip()
        if len(shortened) > 42:
            shortened = shortened[:39] + "..."
        return f"{provider} — {shortened}"

    return provider


# ==========================================
# SIDEBAR
# ==========================================
col_left, col_logo, col_right = st.sidebar.columns([1, 4, 1])
with col_logo:
    logo_path = CURRENT_DIR / "assets" / "gasgraph_logo.png"
    if logo_path.exists():
        st.image(str(logo_path), use_container_width=True)

st.sidebar.markdown("<br>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("**Start Location**")
    start_coords_final = st_searchbox(
        create_search_function("start"),
        key="start_searchbox",
        placeholder="Start typing... (e.g., Istanbul)",
    )

    waypoint_coords_list = []
    for waypoint_index in range(st.session_state.waypoint_count):
        st.markdown(f"**Stopover {waypoint_index + 1}**")
        waypoint_coords = st_searchbox(
            create_search_function(f"wp_{waypoint_index}"),
            key=f"wp_searchbox_{waypoint_index}",
            placeholder="Add a stopover...",
        )

        if waypoint_coords:
            waypoint_coords_list.append(waypoint_coords)

    st.markdown("**Final Destination**")
    end_coords_final = st_searchbox(
        create_search_function("end"),
        key="end_searchbox",
        placeholder="Start typing... (e.g., Ankara)",
    )

    add_column, clear_column = st.columns(2)

    with add_column:
        if st.button("Add Stop", use_container_width=True):
            st.session_state.waypoint_count += 1
            st.rerun()

    with clear_column:
        if (
            st.button("Clear Stops", use_container_width=True)
            and st.session_state.waypoint_count > 0
        ):
            st.session_state.waypoint_count = 0
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

st.sidebar.markdown("---")

with st.sidebar.form(key="route_setup_form"):
    st.subheader("Vehicle & Capacity")
    engine_type = st.selectbox(
        "Vehicle Type",
        ["Combustion (Fuel)", "Electric (EV)"],
    )

    range_column, max_range_column = st.columns(2)

    with range_column:
        current_range = st.number_input(
            "Current (KM)",
            min_value=10,
            max_value=1500,
            value=int(st.session_state.remaining_range),
            step=10,
        )

    with max_range_column:
        max_range = st.number_input(
            "Max (KM)",
            min_value=100,
            max_value=1500,
            value=400,
            step=10,
        )

    st.markdown("---")
    st.subheader("Preferences")

    raw_brands = sorted(df["provider"].dropna().astype(str).unique().tolist())
    brand_options = ["All Brands"] + raw_brands

    def format_brand_name(brand: str) -> str:
        if brand == "All Brands":
            return brand
        return brand.replace("_", " ").title()

    selected_brand = st.selectbox(
        "Preferred Brand",
        options=brand_options,
        format_func=format_brand_name,
    )

    req_wc = st.checkbox("WC Available (Bonus)")
    req_market = st.checkbox("Market Available (Bonus)")
    req_strict = st.checkbox("LPG / Fast Charge Only (Strict)")

    st.markdown("<br>", unsafe_allow_html=True)
    submit_button = st.form_submit_button(
        label="Optimize Route",
        use_container_width=True,
    )

with st.sidebar.expander("Advanced Settings"):
    safety_reserve_percent = st.slider(
        "Range Safety Reserve (%)",
        min_value=0,
        max_value=30,
        value=20,
        step=5,
        help="İstasyona ulaşırken menzilin bu yüzdesi güvenlik payı olarak kullanılmaz.",
    )
    force_forward = st.checkbox(
        "Force Forward Progress",
        value=False,
        help="Hedefe gerçek yol mesafesi bakımından yaklaşmayan istasyonları eler.",
    )


current_station_type = "fuel" if "Fuel" in engine_type else "ev"
filtered_df = build_filtered_stations(
    source_df=df,
    station_type=current_station_type,
    selected_brand=selected_brand,
    strict_requirement=req_strict,
)


# ==========================================
# OPTIMIZATION TRIGGER
# ==========================================
if submit_button:
    st.session_state.remaining_range = int(current_range)

    if start_coords_final is None or end_coords_final is None:
        st.error("Please explicitly select Start and Destination locations.")
    elif len(waypoint_coords_list) != st.session_state.waypoint_count:
        st.error("Please explicitly select every added stopover.")
    else:
        full_waypoints = (
            [start_coords_final]
            + waypoint_coords_list
            + [end_coords_final]
        )

        route_request = {
            "waypoints": full_waypoints,
            "current_range": float(current_range),
            "max_range": float(max_range),
            "station_type": current_station_type,
            "selected_brand": selected_brand,
            "strict_requirement": bool(req_strict),
            "wc_bonus": 5.0 if req_wc else 0.0,
            "market_bonus": 3.0 if req_market else 0.0,
            "force_forward": bool(force_forward),
            "range_safety_ratio": (100.0 - safety_reserve_percent) / 100.0,
        }

        clear_station_radio_state()

        with st.spinner("Calculating real road distances and optimizing route..."):
            try:
                route_plan = run_route_optimization(
                    route_request=route_request,
                    choice_indices=[],
                )

                st.session_state.route_request = route_request
                st.session_state.route_plan = route_plan
                st.session_state.route_needs_recompute = False
                st.session_state.route_status_message = (
                    f"Route generated successfully with "
                    f"{len(route_plan['selected_stops'])} required stop(s)."
                )

            except Exception as exc:
                st.session_state.route_plan = None
                st.session_state.route_request = None
                st.session_state.route_status_message = None
                st.error(
                    "Optimization failed. Try another route, increase the range, "
                    f"or reduce the safety reserve. Error: {exc}"
                )


# Kullanıcı radio seçimini değiştirince sonraki rota zincirini yeniden hesapla.
if (
    st.session_state.get("route_needs_recompute")
    and st.session_state.get("route_request")
    and st.session_state.get("route_plan")
):
    previous_groups = st.session_state.route_plan.get("candidate_groups", [])
    current_choices = [
        int(st.session_state.get(f"radio_stop_{index}", 0))
        for index in range(len(previous_groups))
    ]

    with st.spinner("Recalculating the remaining route from your selection..."):
        try:
            recomputed_plan = run_route_optimization(
                route_request=st.session_state.route_request,
                choice_indices=current_choices,
            )
            st.session_state.route_plan = recomputed_plan
            st.session_state.route_needs_recompute = False
            st.session_state.route_status_message = (
                "Route updated according to your station selection."
            )

            new_group_count = len(recomputed_plan.get("candidate_groups", []))
            for key in list(st.session_state.keys()):
                if key.startswith("radio_stop_"):
                    try:
                        index = int(key.rsplit("_", 1)[1])
                    except ValueError:
                        continue
                    if index >= new_group_count:
                        del st.session_state[key]

        except Exception as exc:
            st.session_state.route_needs_recompute = False
            st.error(f"Route could not be recalculated: {exc}")


route_plan = st.session_state.get("route_plan")
route_request = st.session_state.get("route_request")

if route_plan and st.session_state.get("route_status_message"):
    st.success(st.session_state.route_status_message)


# ==========================================
# METRICS
# ==========================================
display_distance = "-- KM"
display_duration = "--"
display_remaining = f"{st.session_state.remaining_range} KM"
scanned_station_count = len(filtered_df)

if route_plan:
    display_distance = f"{route_plan['distance_km']:.1f} KM"
    display_duration = f"{route_plan['duration_minutes'] / 60.0:.1f} h"
    display_remaining = (
        f"{route_plan['remaining_range_at_destination']:.1f} KM"
    )
    scanned_station_count = int(route_plan.get("scanned_station_count", 0))

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Optimized Road Distance", display_distance)
metric_2.metric("Estimated Drive Time", display_duration)
metric_3.metric("Range at Destination", display_remaining)
metric_4.metric("Scanned Stations", scanned_station_count)

st.markdown("<br>", unsafe_allow_html=True)


# ==========================================
# HUMAN-IN-THE-LOOP STATION SELECTION
# ==========================================
if route_plan and route_plan.get("candidate_groups"):
    st.markdown("---")
    st.subheader("Station Selection")
    st.write(
        "Select an alternative station. Every change automatically recalculates "
        "all following stops from the selected station."
    )

    selected_indices = route_plan.get("selected_choice_indices", [])

    for stop_index, candidates in enumerate(route_plan["candidate_groups"]):
        leg_number = int(candidates[0].get("leg_index", 0)) + 1
        st.markdown(
            f"**Required Stop {stop_index + 1}**"
        )

        option_labels = []
        for candidate in candidates:
            wc_tag = " | WC" if candidate.get("has_wc") else ""
            market_tag = " | Market" if candidate.get("has_market") else ""
            distance_from_previous = float(
                candidate.get("distance_from_previous_km", 0.0)
            )
            detour = float(candidate.get("detour", 0.0))

            option_labels.append(
                f"{format_station_name(candidate)}"
                f"{wc_tag}{market_tag} "
                f"| {distance_from_previous:.1f} KM away "
                f"| +{detour:.1f} KM detour"
            )

        default_index = (
            int(selected_indices[stop_index])
            if stop_index < len(selected_indices)
            else 0
        )
        if default_index < 0 or default_index >= len(candidates):
            default_index = 0

        radio_key = f"radio_stop_{stop_index}"
        stored_value = st.session_state.get(radio_key, default_index)
        if not isinstance(stored_value, int) or stored_value not in range(len(candidates)):
            st.session_state[radio_key] = default_index

        st.radio(
            label=f"Stop {stop_index + 1} Options",
            options=range(len(candidates)),
            format_func=lambda option_index, labels=option_labels: labels[option_index],
            index=default_index,
            key=radio_key,
            horizontal=True,
            label_visibility="collapsed",
            on_change=handle_station_change,
            args=(stop_index,),
        )

    st.markdown("<br>", unsafe_allow_html=True)

elif route_plan:
    st.info("The destination is reachable without a fueling or charging stop.")


# ==========================================
# MAP
# ==========================================
map_center = [39.0, 35.0]
map_zoom = 6

if route_plan and route_plan.get("route_coords"):
    first_coord = route_plan["route_coords"][0]
    map_center = [first_coord[0], first_coord[1]]
    map_zoom = 9

route_map = folium.Map(
    location=map_center,
    zoom_start=map_zoom,
    tiles="CartoDB positron",
)

marker_cluster = MarkerCluster().add_to(route_map)

map_station_df = filtered_df
if route_request:
    map_station_df = build_filtered_stations(
        source_df=df,
        station_type=route_request["station_type"],
        selected_brand=route_request["selected_brand"],
        strict_requirement=route_request["strict_requirement"],
    )

assets_dir = CURRENT_DIR / "assets"
available_icons = {p.stem for p in assets_dir.glob("*.png")} if assets_dir.exists() else set()

display_map_df = map_station_df if route_plan else map_station_df.head(300)


for _, row in display_map_df.iterrows():
    provider = str(row.get("provider") or "Unknown")
    image_name = provider.replace(" ", "_")

    tooltip_text = (
        f"<b>{provider}</b><br>"
        f"Type: {str(row.get('station_type', '')).upper()}"
    )
    has_wc_value = row.get("has_wc")
    has_market_value = row.get("has_market")
    if pd.notna(has_wc_value) and bool(has_wc_value):
        tooltip_text += "<br>WC: Available"
    if pd.notna(has_market_value) and bool(has_market_value):
        tooltip_text += "<br>Market: Available"

    if image_name in available_icons:
        icon_file_path = assets_dir / f"{image_name}.png"
        station_icon = folium.CustomIcon(
            str(icon_file_path),
            icon_size=(35, 35),
        )
    else:
        station_icon = folium.Icon(
            color="blue" if row.get("station_type") == "ev" else "lightgray",
            icon="info-sign",
        )

    folium.Marker(
        location=[float(row["lat"]), float(row["lon"])],
        tooltip=tooltip_text,
        icon=station_icon,
    ).add_to(marker_cluster)