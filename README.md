# GasGraph: Custom Routing & Gas Station Optimization Engine

**GasGraph** is an advanced, self-contained spatial routing and analytics platform designed to solve the optimal gas station selection problem for long-distance transit. By synthesizing concepts from **Mathematical Engineering, Data Operations (DataOps), Operations Research (OR), and Machine Learning (ML)**, GasGraph calculates the most efficient refueling paths across major fuel networks in Turkey (e.g., Shell, Opet, Petrol Ofisi) with minimal cost, distance, and time overhead.

Crucially, **GasGraph operates independently of external black-box routing APIs** (such as OSRM or Google Maps API). It constructs its own topological graph engine directly from raw geospatial datasets.

![GasGraph MVP Dashboard](/Users/simonxji/Documents/GasGraph_AI/src/assets/mvpProduct.png) *(Değiştir: Buraya GitHub'a yüklediğin harita SS'inin yolunu koy)*

---

## 🚀 Key Features & Architectural Core

1. **Interactive Spatial MVP (Current Phase):** A stream-reactive frontend built with **Streamlit** and **Folium** utilizing `MarkerCluster` algorithms to visualize target routes, nodes, and spatial proximity parameters across 10,000+ data points.
2. **Custom Graph Routing Engine (In Progress):** Built from the ground up using **A\* Search** and **Contraction Hierarchies (CH)** algorithms over localized OpenStreetMap (OSM) topological networks.
3. **Modern Data Engineering (ELT Philosophy):**
   - **Extract:** Scraped heterogeneous datasets spanning tens of thousands of gas stations nationwide.
   - **Load:** Semi-structured raw JSON layers are directly loaded into a unified `JSONB` column structure within the production database to maximize ingestion velocity.
   - **Transform:** Raw JSON blobs are schema-standardized dynamically via database **SQL Views** and prepared for geospatial processing using **PostGIS**.

---

## 🛠️ Technology Stack

- **Data Processing & Pipeline:** Python 3.13, Pandas, Supabase-py client
- **Database Engine:** Supabase (PostgreSQL 15+) equipped with the **PostGIS** spatial extension
- **Network & Topology Analysis:** NetworkX, OSMnx
- **Visualization & UI:** Streamlit, Streamlit-Folium
- **Backend Architecture (Target):** FastAPI
- **Mobile Client (Target):** Flutter

---

## 📁 Repository Structure

```text
├── notebooks/
│   └── datasetEDA.ipynb        # Data cleaning, standardization, and NLP transformations
│   └── gasgraph_clean_data.csv # Silver layer clean dataset
├── src/
│   ├── app.py                  # Streamlit MVP visualization dashboard
│   ├── config.py               # Environment and DB configuration
│   ├── resize_logos.py         # Image optimization script for Folium rendering
│   ├── assets/                 # Brand logos for UI mapping
│   └── pipelines/              # ELT Python execution scripts
├── turkey-gas-station-data/
│   └── raw-json/               # Scraped raw heterogeneous JSON datasets
├── .gitignore
├── requirements.txt            # Core project dependencies
└── README.md                   # System documentation