import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster 
from streamlit_folium import st_folium
import os

st.set_page_config(page_title="GasGraph MVP", layout="wide")
st.title("GasGraph - Turkey Gas Stations Map")

# ==========================================
# 1. LOAD REAL DATA
# ==========================================
@st.cache_data
def load_data():
    return pd.read_csv("notebooks/gasgraph_clean_data.csv")

df = load_data()

# ==========================================
# 2. FILTERING UI (DROPDOWNS)
# ==========================================
col1, col2 = st.columns(2)

city_list = ["All"] + sorted(df['unified_city'].dropna().unique().tolist())
selected_city = col1.selectbox("Select City", city_list)

if selected_city != "All":
    district_list = ["All"] + sorted(df[df['unified_city'] == selected_city]['unified_district'].dropna().unique().tolist())
else:
    district_list = ["All"]

selected_district = col2.selectbox("Select District", district_list)

# ==========================================
# 3. FILTERING THE DATA
# ==========================================
filtered_df = df.copy()

if selected_city != "All":
    filtered_df = filtered_df[filtered_df['unified_city'] == selected_city]
    
if selected_district != "All":
    filtered_df = filtered_df[filtered_df['unified_district'] == selected_district]

# ==========================================
# 4. MAP CREATION & DYNAMIC ZOOM
# ==========================================
m = folium.Map(location=[39.2, 35.6], zoom_start=6)

if not filtered_df.empty and (selected_city != "All" or selected_district != "All"):
    sw = filtered_df[['unified_lat', 'unified_lon']].min().values.tolist()
    ne = filtered_df[['unified_lat', 'unified_lon']].max().values.tolist()
    m.fit_bounds([sw, ne])

marker_cluster = MarkerCluster().add_to(m)

# ==========================================
# 5. ADDING MARKERS TO THE CLUSTER
# ==========================================
for idx, row in filtered_df.iterrows():
    marka = str(row['source_provider'])
    icon_path = f"src/assets/{marka}.png"
    
    if os.path.exists(icon_path):
        custom_icon = folium.CustomIcon(icon_path, icon_size=(35, 35))
        folium.Marker(
            location=[row['unified_lat'], row['unified_lon']],
            tooltip=f"{marka} - {row['unified_district']}",
            icon=custom_icon
        ).add_to(marker_cluster)  
    else:
        folium.Marker(
            location=[row['unified_lat'], row['unified_lon']],
            tooltip=f"{marka} (No Logo) - {row['unified_district']}",
            icon=folium.Icon(color='gray', icon='info-sign')
        ).add_to(marker_cluster) 


st_folium(m, width=1000, height=600, returned_objects=[])