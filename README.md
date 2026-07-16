# SRO (Spatial Route Optimizer): Advanced Spatial Routing & Range Optimization Engine
[![Live Dashboard](https://img.shields.io/badge/LIVE_DASHBOARD-1E1E1E?style=for-the-badge&logo=streamlit&logoColor=white)](https://gasgraph-ws9tmhabavrjwnxypbv7hi.streamlit.app/)

**SRO** is an advanced spatial routing and analytics platform designed to solve "range anxiety" for both Electric Vehicles (EVs) and traditional combustion engine vehicles during long-distance transit. By synthesizing concepts from **Data Engineering, Operations Research (OR), and Mathematical Optimization**, SRO calculates the most efficient refueling and recharging paths across major networks in Turkey (e.g., Shell, Opet, Trugo, ZES) with minimal cost, distance, and detour overhead.

---

## 🚀 Key Features & Architectural Core

1. **Interactive Spatial Dashboard:** A stream-reactive frontend built with **Streamlit** and **Folium** utilizing `MarkerCluster` algorithms to visualize target routes, nodes, and spatial proximity parameters across 7,200+ data points.
2. **Vectorized Mathematical Engine & OSRM Integration:** Replaced inefficient procedural iterations with **NumPy Vectorization** for high-performance, matrix-level distance calculations. The engine integrates the **Open Source Routing Machine (OSRM) API** to generate exact real-world highway polylines, applying a mathematical *Tortuosity Factor* to account for actual road curvature.
3. **Human-in-the-Loop (HITL) Architecture:** Instead of a deterministic "dictator algorithm," the system dynamically presents the Top 3 optimal station candidates for every required stop, empowering the user to make decisions based on subjective preferences (amenities, brand loyalty).
4. **Directional Penalty & Multi-Waypoint Routing:** The optimization cost function includes a strict *Directional Penalty* to prevent backward-routing in short-distance scenarios, seamlessly supporting complex, multi-leg journeys.
5. **Modern Data Engineering (ELT Philosophy):**
   - **Extract:** Scraped heterogeneous datasets spanning thousands of gas and EV stations nationwide.
   - **Load:** Semi-structured raw JSON layers are ingested directly into a cloud database (Supabase) to maximize ingestion velocity.
   - **Transform:** Data is standardized dynamically via **SQL Views, CTEs, and Geofencing** to isolate the Turkish coordinate space and prepare it for geospatial processing.

---

## MVP Dashboard Preview

<p align="center">
  <img src="notebooks/mvpProduct.png" width="400" alt="GasGraph MVP Dashboard">
</p>

---
## Technology Stack

- **Data Processing & Pipeline:** Python 3.13, NumPy, Pandas, Supabase-py client
- **Database Engine:** Supabase (PostgreSQL 15+)
- **External APIs:** OSRM (Open Source Routing Machine), Nominatim Geocoder
- **Visualization & UI:** Streamlit, Streamlit-Folium

---

## Repository Structure

```text
├── notebooks/
│   └── datasetEDA.ipynb        # Data cleaning, standardization, and exploratory data analysis
│   └── gasgraph_clean_data.csv # Final structured dataset
├── src/
│   ├── app.py                  # Streamlit MVP visualization dashboard
│   ├── config.py               # Environment and DB configuration
│   ├── resize_logos.py         # Image optimization script for Folium rendering
│   ├── assets/                 # Brand logos for UI mapping
│   ├── pipelines/              # ELT Python execution scripts
│   └── utils/                  
│       ├── router.py           # Core optimization engine, NumPy vectorization, and OSRM logic
│       └── geocoder.py         # Nominatim geocoding functions for coordinate retrieval
├── turkey-gas-station-data/
│   └── raw-json/               # Scraped raw heterogeneous JSON datasets
├── .gitignore
├── requirements.txt            # Core project dependencies
└── README.md                   # System documentation