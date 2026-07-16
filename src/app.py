import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import streamlit as st
from supabase import create_client, Client
import pandas as pd
import folium
from folium.plugins import MarkerCluster 
from streamlit_folium import st_folium
import os
import sys
from utils.geocoder import get_coordinates
from utils.optimizer import calculate_route, get_real_road_route

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from config import supabase
except ModuleNotFoundError:
    # Buluttayken (config.py olmadığı için) Streamlit Secrets'ı kullanır
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)

st.set_page_config(page_title="GasGraph Optimizer", layout="wide", initial_sidebar_state="expanded", page_icon=":no_mouth:")


# ==========================================
# 0. SESSION STATE
# ==========================================
if "remaining_range" not in st.session_state:
    st.session_state.remaining_range = 150 
if "current_location" not in st.session_state:
    st.session_state.current_location = "Istanbul" 

# ==========================================
# 1. LOAD REAL CLOUD DATA
# ==========================================
@st.cache_data(ttl=3600)
def load_gold_data():
    all_data = []
    offset = 0
    chunk_size = 1000
    
    while True:
        # Supabase'den veriyi .range() ile sayfa sayfa (1000'er 1000'er) çekiyoruz
        response = supabase.table("gasgraph_gold_stations").select("*").range(offset, offset + chunk_size - 1).execute()
        chunk = response.data
        
        # Eğer çekilen sayfada hiç veri yoksa döngüyü kır
        if not chunk:
            break
            
        all_data.extend(chunk)
        
        # Eğer gelen veri 1000'den azsa, son sayfaya ulaşmışız demektir
        if len(chunk) < chunk_size:
            break
            
        offset += chunk_size

    return pd.DataFrame(all_data)

df = load_gold_data()

# ==========================================
# 2. SIDEBAR & UI FORM
# ==========================================
col1, col_logo, col2 = st.sidebar.columns([1, 4, 1]) 
with col_logo:
    st.image("src/assets/gasgraph_logo.png", use_container_width=True)

with st.sidebar.form(key="route_setup_form"):
    st.title("Route Setup")
    start_loc = st.text_input("Start Location", value=st.session_state.current_location)
    end_loc = st.text_input("Destination", value="Ankara")

    st.divider()
    
    st.title("Vehicle & Capacity")
    engine_type = st.selectbox("Vehicle Type", ["Combustion (Fuel)", "Electric (EV)"])
    
    current_range = st.number_input("Current Dashboard Range (KM)", min_value=10, max_value=1500, value=st.session_state.remaining_range, step=10)
    max_range = st.number_input("Vehicle Max Capacity (Full Tank/Battery KM)", min_value=100, max_value=1500, value=400, step=10)

    st.divider()
    
    st.title("Preferences")
    raw_brands = sorted(df['provider'].dropna().unique().tolist())
    brand_options = ["All Brands"] + raw_brands
    
    # Kullanıcıya gösterilecek metni güzelleştiren küçük bir fonksiyon
    def format_brand_name(brand):
        if brand == "All Brands":
            return brand
        # Alt çizgileri sil, boşluk koy ve Baş Harflerini Büyüt (title)
        return brand.replace("_", " ").title()

    # format_func parametresi ile arka planda orijinal veriyi tutup, ekranda makyajlı halini gösteriyoruz
    selected_brand = st.selectbox("Preferred Brand", options=brand_options, format_func=format_brand_name)
    
    req_wc = st.checkbox("WC Available (Bonus)")
    req_market = st.checkbox("Market Available (Bonus)")
    req_strict = st.checkbox("LPG (Fuel) / Fast Charge (EV) Only (Strict)")

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_space1, col_btn, col_space2 = st.columns([1, 4, 1])
    with col_btn:
        submit_button = st.form_submit_button(label="Optimize Route", use_container_width=True)

# ==========================================
# 3. FILTERING THE DATA (YUKARI TAŞINDI)
# ==========================================
target_type = "fuel" if "Fuel" in engine_type else "ev"
filtered_df = df[df['station_type'] == target_type].copy()

# Marka filtresi eğer "All Brands" değilse, sadece seçilen markayı filtrele
if selected_brand != "All Brands":
    filtered_df = filtered_df[filtered_df['provider'] == selected_brand]

if "Fuel" in engine_type and req_strict:
    filtered_df = filtered_df[filtered_df['has_lpg'] == True]
elif "EV" in engine_type and req_strict:
    filtered_df = filtered_df[filtered_df['has_fast_charge'] == True]

# ==========================================
# 4. OPTIMIZATION TRIGGER (AŞAĞI TAŞINDI)
# ==========================================
if submit_button:
    st.session_state.current_location = start_loc
    st.session_state.remaining_range = current_range 
    
    with st.spinner("🗺️ Calculating coordinates and optimizing route..."): 
        start_coords = get_coordinates(start_loc)
        end_coords = get_coordinates(end_loc)
        
        if start_coords == (None, None) or end_coords == (None, None):
            st.error("City not found. Please enter a valid location name.")
        else:
            # Koordinatlar bulundu, algoritmayı çalıştırıyoruz!
            try:
                # Kullanıcının bonus tercihlerini ayarlıyoruz
                w_bonus = 5.0 if req_wc else 0.0
                m_bonus = 3.0 if req_market else 0.0
                
                # Rota hesaplama fonksiyonunu çağırıyoruz (filtered_df artık tanımlı!)
                optimized_route = calculate_route(
                    start_coords=start_coords,
                    end_coords=end_coords,
                    current_range=current_range,
                    max_range=max_range,
                    df_stations=filtered_df,
                    wc_bonus=w_bonus,
                    market_bonus=m_bonus
                )
                
                st.success(f"Route generated successfully with {len(optimized_route)} stops!")
                
                # Çıkan rotayı haritada gösterebilmek için Session State (Hafıza) içine kaydediyoruz
                st.session_state.optimized_route = optimized_route 
                
            except Exception as e:
                st.error(f"Optimization failed. Try a different route or increase your current range. Error: {e}")

# ==========================================
# 5. MAIN DASHBOARD UI
# ==========================================
col1, col2, col3 = st.columns(3)
col1.metric(label="Distance to Destination", value="~450 KM") 
col2.metric(label="Current Range", value=f"{st.session_state.remaining_range} KM", delta="- Critical Refuel Needed" if st.session_state.remaining_range < 150 else "")
col3.metric(label="Scanned Stations", value=len(filtered_df))

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 6. MAP CREATION
# ==========================================
m = folium.Map(location=[39.2, 35.6], zoom_start=6)
marker_cluster = MarkerCluster().add_to(m)

filtered_df = filtered_df.dropna(subset=['lat', 'lon'])

# 1. Filtrelenen tüm istasyonları haritaya küme (cluster) olarak ekle
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
            icon=folium.Icon(color='blue' if row['station_type'] == 'ev' else 'red', icon='info-sign')
        ).add_to(marker_cluster) 

# 2. EĞER OPTİMİZE EDİLMİŞ BİR ROTA VARSA (A* ALGORİTMASI ÇALIŞMIŞSA) ÇİZGİ ÇEK VE VURGULA
if "optimized_route" in st.session_state and st.session_state.optimized_route:
    route_coords = []
    
    try:
        # Çizginin uçtan uca gitmesi için Başlangıç ve Bitiş koordinatlarını alıyoruz
        start_c = get_coordinates(start_loc)
        end_c = get_coordinates(end_loc)
        
        # Başlangıç İkonu (Yeşil)
        if start_c != (None, None):
            route_coords.append(start_c)
            folium.Marker(start_c, tooltip="Start Location", icon=folium.Icon(color="green", icon="play")).add_to(m)
            
        # Rota üzerindeki "Optimal" İstasyon İkonları (Turuncu Yıldız)
        for stop in st.session_state.optimized_route:
            stop_coord = (stop['lat'], stop['lon'])
            route_coords.append(stop_coord)
            
            folium.Marker(
                stop_coord, 
                tooltip=f"🛑 OPTIMAL STOP: {stop['provider']}", 
                icon=folium.Icon(color="orange", icon="star", prefix="fa")
            ).add_to(m)

        # Hedef İkonu (Kırmızı)
        if end_c != (None, None):
            route_coords.append(end_c)
            folium.Marker(end_c, tooltip="Destination", icon=folium.Icon(color="red", icon="flag")).add_to(m)

        real_road_path = get_real_road_route(route_coords)

        # Koordinatları birbirine bağlayan Navigasyon Çizgisini Çek
        folium.PolyLine(
            real_road_path,  # route_coords yerine real_road_path verdik!
            color="#FF9B9B", 
            weight=6,        
            opacity=0.8      
        ).add_to(m)
        
        # Haritanın kamerasını rotaya ortala
        m.fit_bounds([start_c, end_c])
        
    except Exception as e:
        st.warning(f"Harita çiziminde ufak bir hata oluştu: {e}")

st_folium(m, width="100%", height=600, returned_objects=[])