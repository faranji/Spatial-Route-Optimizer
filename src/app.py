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
col1, col_logo, col2 = st.sidebar.columns([0.5, 8, 0.5]) 
with col_logo:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, "assets", "gasgraph_logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)

st.sidebar.markdown("<br>", unsafe_allow_html=True)

st.sidebar.title("Route Setup")

def search_for_dropdown(searchterm: str):
    if not searchterm:
        return []
    results = get_coordinates(searchterm)
    if isinstance(results, dict):
        return [(address, coords) for address, coords in results.items()]
    return []

with st.sidebar:
    st.markdown("**📍 Start Location**")
    start_coords_final = st_searchbox(
        search_for_dropdown,
        key="start_searchbox",
        placeholder="Start typing... (e.g., Istanbul)"
    )

    # Dinamik olarak araya giren duraklar (Waypoints)
    waypoint_coords_list = []
    for i in range(st.session_state.waypoint_count):
        st.markdown(f"**🛑 Stopover {i+1}**")
        wp_coords = st_searchbox(
            search_for_dropdown,
            key=f"wp_searchbox_{i}",
            placeholder="Add a stopover..."
        )
        if wp_coords:
            waypoint_coords_list.append(wp_coords)

    # Yeni durak ekleme ve sıfırlama butonları
    col_add, col_clear = st.columns(2)
    with col_add:
        if st.button("➕ Add Stop"):
            st.session_state.waypoint_count += 1
            st.rerun()
    with col_clear:
        if st.button("🗑️ Clear Stops") and st.session_state.waypoint_count > 0:
            st.session_state.waypoint_count = 0
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("**🚩 Final Destination**")
    end_coords_final = st_searchbox(
        search_for_dropdown,
        key="end_searchbox",
        placeholder="Start typing... (e.g., Ankara)"
    )

st.sidebar.divider()

with st.sidebar.form(key="route_setup_form"):
    st.title("Vehicle & Capacity")
    engine_type = st.selectbox("Vehicle Type", ["Combustion (Fuel)", "Electric (EV)"])
    
    current_range = st.number_input("Current Dashboard Range (KM)", min_value=10, max_value=1500, value=st.session_state.remaining_range, step=10)
    max_range = st.number_input("Vehicle Max Capacity (Full Tank/Battery KM)", min_value=100, max_value=1500, value=400, step=10)

    st.divider()
    
    st.title("Preferences")
    raw_brands = sorted(df['provider'].dropna().unique().tolist())
    brand_options = ["All Brands"] + raw_brands
    
    def format_brand_name(brand):
        if brand == "All Brands":
            return brand
        return brand.replace("_", " ").title()

    selected_brand = st.selectbox("Preferred Brand", options=brand_options, format_func=format_brand_name)
    
    req_wc = st.checkbox("WC Available (Bonus)")
    req_market = st.checkbox("Market Available (Bonus)")
    req_strict = st.checkbox("LPG (Fuel) / Fast Charge (EV) Only (Strict)")

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_space1, col_btn, col_space2 = st.columns([1, 4, 1])
    with col_btn:
        submit_button = st.form_submit_button(label="Optimize Route", use_container_width=True)

with st.sidebar.expander("Advanced Settings"):
    user_tortuosity = st.slider("Tortuosity Factor (Road Curvature)", min_value=1.0, max_value=1.5, value=1.3, step=0.1)
    force_forward = st.checkbox("Force Forward Progress (Directional Penalty)", value=False)

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
    
    with st.spinner("🗺️ Calculating coordinates and optimizing route..."): 
        
        if start_coords_final is None or end_coords_final is None:
            st.error("Please explicitly select Start and Destination locations.")
        else:
            try:
                w_bonus = 5.0 if req_wc else 0.0
                m_bonus = 3.0 if req_market else 0.0
                
                # Başlangıç, Ara Duraklar ve Bitişi tek bir listede birleştiriyoruz
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
col1, col2, col3 = st.columns(3)
col1.metric(label="Distance to Destination", value="~450 KM", delta_color="inverse")
col2.metric(label="Current Range", value=f"{st.session_state.remaining_range} KM", delta_color="inverse")
col3.metric(label="Scanned Stations", value=len(filtered_df), delta_color="off")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 6. MAP CREATION
# ==========================================
m = folium.Map(
    location=[39.0, 35.0], 
    zoom_start=6, 
    tiles="CartoDB dark_matter" 
)
marker_cluster = MarkerCluster().add_to(m)

filtered_df = filtered_df.dropna(subset=['lat', 'lon'])

for idx, row in filtered_df.iterrows():
    marka = str(row['provider'])
    img_name = marka.replace(" ", "_") 
    icon_path = f"src/assets/{img_name}.png"
    
    tooltip_text = f"<b>{marka}</b><br>Type: {row['station_type'].upper()}"
    if row['has_wc'] == True: tooltip_text += "<br>WC: ✔️"
    if row['has_market'] == True: tooltip_text += "<br>Market: ✔️"
    
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
                color='blue' if row['station_type'] == 'ev' else 'orange', 
                icon='info-sign'
            )
        ).add_to(marker_cluster)

if "optimized_route" in st.session_state and st.session_state.optimized_route:
    route_coords = []
    try:
        user_waypoints = st.session_state.full_waypoints
        
        # Kullanıcının seçtiği ana durakları (Start, Stopovers, End) haritaya ekle
        for idx, wp in enumerate(user_waypoints):
            route_coords.append(wp)
            if idx == 0:
                folium.Marker(wp, tooltip="Start Location", icon=folium.Icon(color="green", icon="play")).add_to(m)
            elif idx == len(user_waypoints) - 1:
                folium.Marker(wp, tooltip="Destination", icon=folium.Icon(color="red", icon="flag")).add_to(m)
            else:
                folium.Marker(wp, tooltip=f"Waypoint {idx}", icon=folium.Icon(color="purple", icon="info-sign")).add_to(m)
            
        # Algoritmanın bulduğu istasyon duraklarını haritaya ekle ve rotaya dahil et
        for stop in st.session_state.optimized_route:
            if isinstance(stop, list) and len(stop) > 0:
                best_stop = stop[0]
            else:
                best_stop = stop
                
            stop_coord = (best_stop['lat'], best_stop['lon'])
            route_coords.append(stop_coord)
            
            folium.Marker(
                stop_coord, 
                tooltip=f"🛑 OPTIMAL STOP: {best_stop['provider']}", 
                icon=folium.Icon(color="orange", icon="star", prefix="fa")
            ).add_to(m)

        real_road_path = get_real_road_route(route_coords)

        folium.PolyLine(
            real_road_path, 
            color="#FF9B9B", 
            weight=6,        
            opacity=0.8      
        ).add_to(m)
        
        m.fit_bounds([user_waypoints[0], user_waypoints[-1]])
        
    except Exception as e:
        st.warning(f"Harita çiziminde ufak bir hata oluştu: {e}")

st_folium(m, width="100%", height=600, returned_objects=[])