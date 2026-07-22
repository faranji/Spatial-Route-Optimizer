import html
import os
import ssl
import sys
from pathlib import Path
from typing import Any, Dict, List

ssl._create_default_https_context = ssl._create_unverified_context

import folium
import pandas as pd
import streamlit as st
from folium.plugins import FastMarkerCluster
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
    page_icon=":no_mouth:",
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

        .sro-hitl-header {
            margin: 0.25rem 0 1.25rem 0;
        }

        .sro-hitl-header p {
            color: #667085;
            font-size: 0.98rem;
            line-height: 1.65;
            margin: 0.35rem 0 0 0;
        }

        .sro-stop-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: 1.45rem 0 0.7rem 0;
        }

        .sro-stop-title {
            color: #243447;
            font-size: 1.08rem;
            font-weight: 700;
        }

        .sro-leg-pill,
        .sro-badge {
            display: inline-flex;
            align-items: center;
            width: fit-content;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 600;
            line-height: 1;
            white-space: nowrap;
        }

        .sro-leg-pill {
            color: #475467;
            background: #f2f4f7;
            padding: 0.38rem 0.62rem;
        }

        .sro-badge-row {
            min-height: 1.7rem;
            margin-bottom: 0.3rem;
        }

        .sro-badge {
            color: #344054;
            background: #f2f4f7;
            padding: 0.34rem 0.55rem;
            margin: 0 0.28rem 0.28rem 0;
        }

        .sro-badge-recommended {
            color: #17603a;
            background: #eaf8f0;
        }

        .sro-badge-selected {
            color: #175cd3;
            background: #eaf2ff;
        }

        .sro-station-name {
            color: #1d2939;
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.4;
            min-height: 2.8rem;
            margin: 0.1rem 0 0.8rem 0;
        }

        .sro-card-metric-label {
            color: #667085;
            font-size: 0.72rem;
            margin-bottom: 0.06rem;
        }

        .sro-card-metric-value {
            color: #101828;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }

        .sro-card-footer {
            color: #667085;
            font-size: 0.78rem;
            line-height: 1.4;
            min-height: 2.15rem;
            margin-top: 0.35rem;
        }

        .sro-selected-summary {
            color: #344054;
            background: #f8fafc;
            border: 1px solid #e4e7ec;
            border-radius: 10px;
            padding: 0.7rem 0.85rem;
            margin: 0.7rem 0 0.3rem 0;
            font-size: 0.88rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
            border-color: #e4e7ec !important;
            box-shadow: 0 4px 14px rgba(16, 24, 40, 0.045);
            background: #ffffff;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: #b9c8dc !important;
            box-shadow: 0 7px 20px rgba(16, 24, 40, 0.075);
            transition: 0.18s ease;
        }

        div[data-testid="stButton"] > button {
            border-radius: 10px;
            font-weight: 600;
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
        "active_stop_index": 0,
        "show_full_station_map": False,
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
        raise RuntimeError("couldn't load data.")

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

    def search_for_dropdown(searchterm: str):
        if not searchterm:
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
    selected_brands: List[str],
    strict_requirement: bool,
) -> pd.DataFrame:
    result = source_df[source_df["station_type"] == station_type].copy()

    # Hiç marka seçilmemişse tüm markaları kullan.
    if selected_brands:
        result = result[result["provider"].isin(selected_brands)]

    if strict_requirement:
        if station_type == "fuel":
            result = result[result["has_lpg"].fillna(False) == True]
        else:
            result = result[
                result["has_fast_charge"].fillna(False) == True
            ]

    return (
        result
        .dropna(subset=["id", "lat", "lon"])
        .reset_index(drop=True)
    )


def run_route_optimization(
    route_request: Dict[str, Any],
    choice_indices: List[int],
) -> Dict[str, Any]:
    request_stations = build_filtered_stations(
        source_df=df,
        station_type=route_request["station_type"],
        selected_brands=route_request["selected_brands"],
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


def select_station_card(stop_index: int, candidate_index: int) -> None:
    st.session_state[f"radio_stop_{stop_index}"] = int(candidate_index)

    existing_plan = st.session_state.get("route_plan") or {}
    group_count = len(existing_plan.get("candidate_groups", []))

    # Değişen durağın ardından gelen seçimler artık eski rota zincirine aittir.
    for next_index in range(stop_index + 1, group_count):
        next_key = f"radio_stop_{next_index}"
        if next_key in st.session_state:
            del st.session_state[next_key]

    st.session_state.route_status_message = None
    st.session_state.active_stop_index = int(stop_index)
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



def sample_route_geometry(
    geometry: List[List[float]],
    maximum_points: int = 2200,
) -> List[List[float]]:
    if not geometry or len(geometry) <= maximum_points:
        return geometry

    step = max(1, len(geometry) // maximum_points)
    sampled = geometry[::step]

    if sampled[-1] != geometry[-1]:
        sampled.append(geometry[-1])

    return sampled


def add_route_layers(
    target_map: folium.Map,
    current_route_plan: Dict[str, Any],
    current_route_request: Dict[str, Any],
    show_alternatives: bool,
) -> None:
    user_waypoints = current_route_request["waypoints"]

    for waypoint_index, waypoint in enumerate(user_waypoints):
        if waypoint_index == 0:
            tooltip = "Start Location"
            icon = folium.Icon(color="green", icon="play")
        elif waypoint_index == len(user_waypoints) - 1:
            tooltip = "Final Destination"
            icon = folium.Icon(color="red", icon="flag")
        else:
            tooltip = f"User Stopover {waypoint_index}"
            icon = folium.Icon(color="purple", icon="info-sign")

        folium.Marker(
            location=[float(waypoint[0]), float(waypoint[1])],
            tooltip=tooltip,
            icon=icon,
        ).add_to(target_map)

    selected_indices = current_route_plan.get("selected_choice_indices", [])
    candidate_groups = current_route_plan.get("candidate_groups", [])

    if show_alternatives:
        for stop_index, candidates in enumerate(candidate_groups):
            selected_index = (
                int(selected_indices[stop_index])
                if stop_index < len(selected_indices)
                else 0
            )

            for candidate_index, candidate in enumerate(candidates):
                if candidate_index == selected_index:
                    continue

                provider = html.escape(format_station_name(candidate))
                distance = float(candidate.get("distance_from_previous_km", 0.0))
                detour = float(candidate.get("detour", 0.0))

                folium.CircleMarker(
                    location=[float(candidate["lat"]), float(candidate["lon"])],
                    radius=6,
                    color="#64748B",
                    weight=2,
                    fill=True,
                    fill_color="#CBD5E1",
                    fill_opacity=0.9,
                    tooltip=(
                        f"Alternative for Stop {stop_index + 1}: {provider} | "
                        f"{distance:.1f} km away | +{detour:.1f} km detour"
                    ),
                ).add_to(target_map)

    for stop_index, selected_stop in enumerate(
        current_route_plan.get("selected_stops", [])
    ):
        folium.Marker(
            location=[
                float(selected_stop["lat"]),
                float(selected_stop["lon"]),
            ],
            tooltip=(
                f"Selected Stop {stop_index + 1}: "
                f"{format_station_name(selected_stop)}"
            ),
            icon=folium.Icon(
                color="orange",
                icon="star",
                prefix="fa",
            ),
        ).add_to(target_map)

    road_geometry = sample_route_geometry(
        current_route_plan.get("road_geometry", [])
    )
    if road_geometry:
        folium.PolyLine(
            road_geometry,
            color="#1E88E5",
            weight=5,
            opacity=0.88,
        ).add_to(target_map)

    route_bounds = [
        [float(lat), float(lon)]
        for lat, lon in current_route_plan.get("route_coords", [])
    ]
    if route_bounds:
        target_map.fit_bounds(route_bounds, padding=(28, 28))


def build_route_overview_map(
    current_route_plan: Dict[str, Any],
    current_route_request: Dict[str, Any],
) -> folium.Map:
    """Yalnızca rota ve HITL adaylarını gösteren hızlı önizleme haritası."""
    first_coord = current_route_plan["route_coords"][0]
    overview_map = folium.Map(
        location=[float(first_coord[0]), float(first_coord[1])],
        zoom_start=7,
        tiles="CartoDB positron",
        control_scale=True,
    )

    add_route_layers(
        target_map=overview_map,
        current_route_plan=current_route_plan,
        current_route_request=current_route_request,
        show_alternatives=True,
    )

    legend_html = """
    <div style="position: fixed; bottom: 22px; left: 22px; z-index: 9999;
                background: white; border: 1px solid #d0d5dd; border-radius: 10px;
                padding: 10px 12px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.10);">
        <div style="font-weight: 700; margin-bottom: 5px;">Route overview</div>
        <div><span style="color:#F59E0B;">★</span> Selected station</div>
        <div><span style="color:#64748B;">●</span> Alternative station</div>
        <div><span style="color:#1E88E5;">━</span> Optimized road route</div>
    </div>
    """
    overview_map.get_root().html.add_child(folium.Element(legend_html))
    return overview_map


def build_full_station_map(
    current_route_plan: Dict[str, Any],
    current_route_request: Dict[str, Any],
    station_df: pd.DataFrame,
) -> folium.Map:
    """Tüm istasyonları FastMarkerCluster ile isteğe bağlı olarak gösterir."""
    first_coord = current_route_plan["route_coords"][0]
    full_map = folium.Map(
        location=[float(first_coord[0]), float(first_coord[1])],
        zoom_start=6,
        tiles="CartoDB positron",
        control_scale=True,
    )

    station_locations = (
        station_df[["lat", "lon"]]
        .astype(float)
        .values
        .tolist()
    )
    FastMarkerCluster(station_locations).add_to(full_map)

    add_route_layers(
        target_map=full_map,
        current_route_plan=current_route_plan,
        current_route_request=current_route_request,
        show_alternatives=False,
    )
    return full_map


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

    def format_brand_name(brand: str) -> str:
        return brand.replace("_", " ").title()

    selected_brands = st.multiselect(
        "Preferred Brands",
        options=raw_brands,
        format_func=format_brand_name,
        placeholder="All brands",
        help="Select one or more brands. Leave empty to include all brands.",
    )

    # req_wc = st.checkbox("WC Available")
    # req_market = st.checkbox("Market Available")
    req_strict = st.checkbox("LPG / Fast Charge Only")

    # st.markdown("<br>", unsafe_allow_html=True)
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


# Mevcut kontroller için önizleme filtresi
current_station_type = "fuel" if "Fuel" in engine_type else "ev"
filtered_df = build_filtered_stations(
    source_df=df,
    station_type=current_station_type,
    selected_brands=selected_brands,
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
            "selected_brands": selected_brands,
            "strict_requirement": bool(req_strict),
            "wc_bonus": 0.0,
            "market_bonus": 0.0,
            "force_forward": bool(force_forward),
            "range_safety_ratio": (100.0 - safety_reserve_percent) / 100.0,
        }

        clear_station_radio_state()
        st.session_state.active_stop_index = 0
        st.session_state.show_full_station_map = False

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
# FAST ROUTE OVERVIEW MAP
# ==========================================
if route_plan and route_request and route_plan.get("route_coords"):
    st.markdown("---")
    st.subheader("Route Overview")
    st.caption(
        "Orange stars show the currently selected stations. "
        "Gray points show the available HITL alternatives. "
        "Changing a station updates this map automatically."
    )

    selected_ids = "-".join(
        str(stop.get("id", index))
        for index, stop in enumerate(route_plan.get("selected_stops", []))
    )
    overview_map = build_route_overview_map(route_plan, route_request)
    st_folium(
        overview_map,
        width="100%",
        height=430,
        key=f"route_overview_{selected_ids}",
        returned_objects=[],
    )


# ==========================================
# HUMAN-IN-THE-LOOP STATION SELECTION
# ==========================================
if route_plan and route_plan.get("candidate_groups"):
    st.markdown(
        """
        <div class="sro-hitl-header">
            <h2>Choose Your Preferred Stations</h2>
            <p>
                Open a required stop to compare its three recommended stations.
                Changing a selection automatically recalculates every following
                stop from the newly selected station.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_indices = route_plan.get("selected_choice_indices", [])
    active_stop_index = int(st.session_state.get("active_stop_index", 0))

    for stop_index, candidates in enumerate(route_plan["candidate_groups"]):
        if not candidates:
            continue

        leg_number = int(candidates[0].get("leg_index", 0)) + 1
        default_index = (
            int(selected_indices[stop_index])
            if stop_index < len(selected_indices)
            else 0
        )
        if default_index < 0 or default_index >= len(candidates):
            default_index = 0

        choice_key = f"radio_stop_{stop_index}"
        stored_choice = st.session_state.get(choice_key, default_index)
        if (
            not isinstance(stored_choice, int)
            or stored_choice < 0
            or stored_choice >= len(candidates)
        ):
            stored_choice = default_index

        st.session_state[choice_key] = stored_choice
        selected_candidate = candidates[stored_choice]
        selected_name = format_station_name(selected_candidate)
        selected_detour = float(selected_candidate.get("detour", 0.0))

        expander_title = (
            f"Required Stop {stop_index + 1} · "
            f"{selected_name} · +{selected_detour:.1f} km detour"
        )

        with st.expander(
            expander_title,
            expanded=(stop_index == active_stop_index),
        ):
            st.caption(
                "Compare distance, extra detour and station facilities, "
                "then choose the option that best fits your trip."
            )

            card_columns = st.columns(len(candidates), gap="medium")

            for candidate_index, candidate in enumerate(candidates):
                is_selected = candidate_index == stored_choice
                is_recommended = candidate_index == 0

                provider_name = html.escape(format_station_name(candidate))
                distance_from_previous = float(
                    candidate.get("distance_from_previous_km", 0.0)
                )
                distance_to_leg_end = float(
                    candidate.get("distance_to_leg_end_km", 0.0)
                )
                detour = float(candidate.get("detour", 0.0))

                badge_parts = []
                if is_selected:
                    badge_parts.append(
                        '<span class="sro-badge sro-badge-selected">Selected</span>'
                    )
                elif is_recommended:
                    badge_parts.append(
                        '<span class="sro-badge sro-badge-recommended">Best Match</span>'
                    )

                if candidate.get("has_wc"):
                    badge_parts.append('<span class="sro-badge">WC</span>')
                if candidate.get("has_market"):
                    badge_parts.append('<span class="sro-badge">Market</span>')
                if candidate.get("has_lpg"):
                    badge_parts.append('<span class="sro-badge">LPG</span>')
                if candidate.get("has_fast_charge"):
                    badge_parts.append('<span class="sro-badge">Fast Charge</span>')

                badge_html = "".join(badge_parts) or (
                    '<span class="sro-badge">Standard Station</span>'
                )

                with card_columns[candidate_index]:
                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div class="sro-badge-row">{badge_html}</div>
                            <div class="sro-station-name">{provider_name}</div>
                            """,
                            unsafe_allow_html=True,
                        )

                        metric_left, metric_right = st.columns(2)
                        with metric_left:
                            st.markdown(
                                f"""
                                <div class="sro-card-metric-label">Distance</div>
                                <div class="sro-card-metric-value">
                                    {distance_from_previous:.1f} km
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with metric_right:
                            st.markdown(
                                f"""
                                <div class="sro-card-metric-label">Extra detour</div>
                                <div class="sro-card-metric-value">
                                    +{detour:.1f} km
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                        st.markdown(
                            f"""
                            <div class="sro-card-footer">
                                {distance_to_leg_end:.1f} km remains to the end of this route leg.
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        if is_selected:
                            st.button(
                                "Selected",
                                key=f"selected_card_{stop_index}_{candidate_index}",
                                type="primary",
                                use_container_width=True,
                                disabled=True,
                            )
                        else:
                            st.button(
                                "Choose This Station",
                                key=f"choose_card_{stop_index}_{candidate_index}",
                                type="secondary",
                                use_container_width=True,
                                on_click=select_station_card,
                                args=(stop_index, candidate_index),
                            )

            st.markdown(
                f"""
                <div class="sro-selected-summary">
                    <strong>Current selection:</strong>
                    {html.escape(selected_name)}.
                    The next required stop is calculated from this station.
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

elif route_plan:
    st.info("The destination is reachable without a fueling or charging stop.")


# ==========================================
# OPTIONAL FULL STATION NETWORK MAP
# ==========================================
if route_plan and route_request:
    st.markdown("---")
    st.subheader("Full Station Network")
    st.caption(
        "The route overview above is loaded immediately for fast interaction. "
        "Load the complete station network only when you need to inspect all stations."
    )

    show_full_station_map = st.toggle(
        f"Load all {int(route_plan.get('scanned_station_count', len(filtered_df))):,} station markers",
        key="show_full_station_map",
        help="This view can take longer to render because it contains the complete station dataset.",
    )

    if show_full_station_map:
        map_station_df = build_filtered_stations(
            source_df=df,
            station_type=route_request["station_type"],
            selected_brands=route_request["selected_brands"],
            strict_requirement=route_request["strict_requirement"],
        )

        with st.spinner("Loading the complete station network..."):
            full_station_map = build_full_station_map(
                current_route_plan=route_plan,
                current_route_request=route_request,
                station_df=map_station_df,
            )
            st_folium(
                full_station_map,
                width="100%",
                height=600,
                key="full_station_network_map",
                returned_objects=[],
            )