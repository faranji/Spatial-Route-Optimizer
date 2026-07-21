import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import streamlit as st
from supabase import create_client, Client
from streamlit_searchbox import st_searchbox
import pandas as pd
import folium
from folium.plugins import MarkerCluster 
from streamlit_folium import st_folium
import os
import sys
import math
from utils.geocoder import get_coordinates
from utils.optimizer import calculate_route, get_real_road_route, calculate_multi_waypoint_route

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import supabase
except ModuleNotFoundError:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)

st.set_page_config(page_title="SRO | Spatial Route Optimizer", layout="wide", initial_sidebar_state="expanded", page_icon=":no_mouth:")

# ==========================================
# CUSTOM CSS
# ==========================================
st.markdown("""
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
""", unsafe_allow_html=True)

# ==========================================
# 0. SESSION STATE
# ==========================================
if "remaining_range" not in st.session_state:
    st.session_state.remaining_range = 150 
if "current_location" not in st.session_state:
    st.session_state.current_location = "Istanbul" 
if "waypoint_count" not in st.session_state:
    st.session_state.waypoint_count = 0

# ==========================================
# 1. LOAD REAL CLOUD DATA
# ==========================================
@st.cache_data(ttl=3600)
def load_gold_data():
    all_data = []
    offset = 0
    chunk_size = 1000
    
    while True:
        response = supabase.table("sro_gold_stations").select("*").range(offset, offset + chunk_size - 1).execute()
        chunk = response.data
        if not chunk:
            break
        all_data.extend(chunk)
        if len(chunk) < chunk_size:
            break
        offset += chunk_size
    return pd.DataFrame(all_data)

df = load_gold_data()

# ==========================================
# 2. SIDEBAR & UI FORM (MULTI-WAYPOINT)
# ==========================================
col1, col_logo, col2 = st.sidebar.columns([1, 4, 1]) 
with col_logo:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, "assets", "gasgraph_logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)

st.sidebar.markdown("<br>", unsafe_allow_html=True)

def create_search_function(box_key):
    """
    Her arama kutusuna özel bir hafıza alanı yaratır.
    Sayfa yenilendiğinde listenin kaybolmasını ve IndexError vermesini engeller.
    """
    def search_for_dropdown(searchterm: str):
        if not searchterm:
            return st.session_state.get(f"{box_key}_options", [])
        
        results = get_coordinates(searchterm)
        if isinstance(results, dict):
            options = [(address, coords) for address, coords in results.items()]
            st.session_state[f"{box_key}_options"] = options
            return options
        return []
    return search_for_dropdown

with st.sidebar:
    
    st.markdown("**Start Location**")
    start_coords_final = st_searchbox(
        create_search_function("start"),
        key="start_searchbox",
        placeholder="Start typing... (e.g., Istanbul)"
    )

    waypoint_coords_list = []
    for i in range(st.session_state.waypoint_count):
        st.markdown(f"**Stopover {i+1}**")
        wp_coords = st_searchbox(
            create_search_function(f"wp_{i}"),
            key=f"wp_searchbox_{i}",
            placeholder="Add a stopover..."
        )
        if wp_coords:
            waypoint_coords_list.append(wp_coords)

    st.markdown("**Final Destination**")
    end_coords_final = st_searchbox(
        create_search_function("end"),
        key="end_searchbox",
        placeholder="Start typing... (e.g., Ankara)"
    )

    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("Add Stop", use_container_width=True):
            st.session_state.waypoint_count += 1
            st.rerun()
    with col_clear:
        if st.button("Clear Stops", use_container_width=True) and st.session_state.waypoint_count > 0:
            st.session_state.waypoint_count = 0
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

st.sidebar.markdown("---")

with st.sidebar.form(key="route_setup_form"):
    st.subheader("Vehicle & Capacity")
    engine_type = st.selectbox("Vehicle Type", ["Combustion (Fuel)", "Electric (EV)"])
    
    col_range1, col_range2 = st.columns(2)
    with col_range1:
        current_range = st.number_input("Current (KM)", min_value=10, max_value=1500, value=st.session_state.remaining_range, step=10)
    with col_range2:
        max_range = st.number_input("Max (KM)", min_value=100, max_value=1500, value=400, step=10)

    st.markdown("---")
    
    st.subheader("Preferences")
    raw_brands = sorted(df['provider'].dropna().unique().tolist())
    brand_options = ["All Brands"] + raw_brands
    
    def format_brand_name(brand):
        if brand == "All Brands":
            return brand
        return brand.replace("_", " ").title()

    selected_brand = st.selectbox("Preferred Brand", options=brand_options, format_func=format_brand_name)
    
    req_wc = st.checkbox("WC Available (Bonus)")
    req_market = st.checkbox("Market Available (Bonus)")
    req_strict = st.checkbox("LPG / Fast Charge Only (Strict)")

    st.markdown("<br>", unsafe_allow_html=True)
    
    submit_button = st.form_submit_button(label="Optimize Route", use_container_width=True)

with st.sidebar.expander("Advanced Settings"):
    user_tortuosity = st.slider("Tortuosity Factor (Road Curvature)", min_value=1.0, max_value=1.5, value=1.3, step=0.1)
    force_forward = st.checkbox("Force Forward Progress", value=False)

# ==========================================
# 3. FILTERING THE DATA 
# ==========================================
target_type = "fuel" if "Fuel" in engine_type else "ev"
filtered_df = df[df['station_type'] == target_type].copy()

if selected_brand != "All Brands":
    filtered_df = filtered_df[filtered_df['provider'] == selected_brand]

if "Fuel" in engine_type and req_strict:
    filtered_df = filtered_df[filtered_df['has_lpg'] == True]
elif "EV" in engine_type and req_strict:
    filtered_df = filtered_df[filtered_df['has_fast_charge'] == True]

# ==========================================
# 4. OPTIMIZATION TRIGGER
# ==========================================
if submit_button:
    st.session_state.remaining_range = current_range 
    
    with st.spinner("Calculating coordinates and optimizing route..."): 
        if start_coords_final is None or end_coords_final is None:
            st.error("Please explicitly select Start and Destination locations.")
        else:
            try:
                w_bonus = 5.0 if req_wc else 0.0
                m_bonus = 3.0 if req_market else 0.0
                
                full_waypoints = [start_coords_final] + waypoint_coords_list + [end_coords_final]
                
                optimized_route = calculate_multi_waypoint_route(
                    waypoints_list=full_waypoints,
                    current_range=current_range,
                    max_range=max_range,
                    df_stations=filtered_df,
                    wc_bonus=w_bonus,
                    market_bonus=m_bonus,
                    tortuosity=user_tortuosity,
                    force_forward=force_forward
                )
                
                st.success(f"Multi-Waypoint Route generated successfully with {len(optimized_route)} fueling stops!")
                st.session_state.optimized_route = optimized_route 
                st.session_state.full_waypoints = full_waypoints
                
            except Exception as e:
                st.error(f"Optimization failed. Try a different route or increase your current range. Error: {e}")

# ==========================================
# 5. MAIN DASHBOARD UI (Dinamik Metrikler)
# ==========================================
def calculate_total_distance(coords_list):
    total_dist = 0.0
    for i in range(len(coords_list) - 1):
        lat1, lon1 = coords_list[i]
        lat2, lon2 = coords_list[i+1]
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        total_dist += R * c
    return total_dist

display_distance = "-- KM"
if "full_waypoints" in st.session_state and st.session_state.full_waypoints:
    raw_dist = calculate_total_distance(st.session_state.full_waypoints)
    final_dist = int(raw_dist * user_tortuosity)
    display_distance = f"~{final_dist} KM"

col1, col2, col3 = st.columns(3)
col1.metric(label="Distance to Destination", value=display_distance, delta_color="inverse")
col2.metric(label="Current Range", value=f"{st.session_state.remaining_range} KM", delta_color="inverse")
col3.metric(label="Scanned Stations", value=len(filtered_df), delta_color="off")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5.5. HITL (Human-in-the-Loop) SELECTION PANEL
# ==========================================
final_selected_stops = []

if "optimized_route" in st.session_state and st.session_state.optimized_route:
    st.markdown("---")
    st.subheader("Station Selection")
    st.write("Algorithm generated top options based on cost, distance, and amenities. Select your preferred stations.")
    
    if "user_selections" not in st.session_state:
        st.session_state.user_selections = {}
        
    for stop_idx, candidates in enumerate(st.session_state.optimized_route):
        st.markdown(f"**Required Stop {stop_idx + 1}**")

        options = []
        for c in candidates:
            wc_tag = " | WC" if c.get('has_wc') else ""
            mkt_tag = " | Market" if c.get('has_market') else ""
            ekstra_km = c.get('detour', 0.0)
            
            options.append(f"{c['provider']}{wc_tag}{mkt_tag} (+{ekstra_km:.1f} KM Uzama)")
            
        current_choice = st.session_state.user_selections.get(stop_idx, 0)
        if current_choice >= len(options):
            current_choice = 0
            
        selected_idx = st.radio(
            label=f"Stop {stop_idx + 1} Options",
            options=range(len(options)),
            format_func=lambda x: options[x],
            index=current_choice,
            key=f"radio_stop_{stop_idx}",
            horizontal=True,
            label_visibility="collapsed"
        )
        
        st.session_state.user_selections[stop_idx] = selected_idx
        final_selected_stops.append(candidates[selected_idx])
        
    st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 6. MAP CREATION
# ==========================================
m = folium.Map(
    location=[39.0, 35.0], 
    zoom_start=6, 
    tiles="CartoDB positron" 
)
marker_cluster = MarkerCluster().add_to(m)

filtered_df = filtered_df.dropna(subset=['lat', 'lon'])

for idx, row in filtered_df.iterrows():
    marka = str(row['provider'])
    img_name = marka.replace(" ", "_") 
    icon_path = f"src/assets/{img_name}.png"
    
    tooltip_text = f"<b>{marka}</b><br>Type: {row['station_type'].upper()}"
    if row['has_wc'] == True: tooltip_text += "<br>WC: Available"
    if row['has_market'] == True: tooltip_text += "<br>Market: Available"
    
    if os.path.exists(icon_path):
        custom_icon = folium.CustomIcon(icon_path, icon_size=(35, 35))
        folium.Marker(
            location=[row['lat'], row['lon']],
            tooltip=tooltip_text,
            icon=custom_icon
        ).add_to(marker_cluster)  
    else:
       folium.Marker(
            location=[row['lat'], row['lon']],
            tooltip=tooltip_text,
            icon=folium.Icon(
                color='blue' if row['station_type'] == 'ev' else 'lightgray', 
                icon='info-sign'
            )
        ).add_to(marker_cluster)

if "optimized_route" in st.session_state and st.session_state.optimized_route:
    try:
        user_waypoints = st.session_state.full_waypoints
        
        for idx, wp in enumerate(user_waypoints):
            if idx == 0:
                folium.Marker(wp, tooltip="Start Location", icon=folium.Icon(color="green", icon="play")).add_to(m)
            elif idx == len(user_waypoints) - 1:
                folium.Marker(wp, tooltip="Destination", icon=folium.Icon(color="red", icon="flag")).add_to(m)
            else:
                folium.Marker(wp, tooltip=f"Waypoint {idx}", icon=folium.Icon(color="purple", icon="info-sign")).add_to(m)
            
        for best_stop in final_selected_stops:
            stop_coord = (best_stop['lat'], best_stop['lon'])
            folium.Marker(
                stop_coord, 
                tooltip=f"OPTIMAL STOP: {best_stop['provider']}", 
                icon=folium.Icon(color="orange", icon="star", prefix="fa")
            ).add_to(m)

        start_coord = user_waypoints[0]
        dest_coord = user_waypoints[-1]
        
        middle_coords = []
        if len(user_waypoints) > 2:
            middle_coords.extend(user_waypoints[1:-1])
            
        for best_stop in final_selected_stops:
            middle_coords.append((best_stop['lat'], best_stop['lon']))
            
        middle_coords.sort(
            key=lambda x: math.sqrt((x[0] - dest_coord[0])**2 + (x[1] - dest_coord[1])**2), 
            reverse=True
        )
        
        route_coords = [start_coord] + middle_coords + [dest_coord]

        real_road_path = get_real_road_route(route_coords)

        folium.PolyLine(
            real_road_path, 
            color="#1E88E5", 
            weight=5,        
            opacity=0.8      
        ).add_to(m)
        
        m.fit_bounds([user_waypoints[0], user_waypoints[-1]])
        
    except Exception as e:
        st.warning(f"Map rendering error: {e}")

st_folium(m, width="100%", height=600, returned_objects=[])