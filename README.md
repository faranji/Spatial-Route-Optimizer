# GasGraph: Custom Routing & Gas Station Optimization Engine

GasGraph is an advanced, self-contained spatial routing and analytics platform designed to solve the optimal gas station selection problem for long-distance transit. By synthesizing concepts from **Mathematical Engineering, Data Operations (DataOps), Operational Research (OR), and Machine Learning (ML)**, GasGraph calculates the most efficient refueling paths across 9 major fuel networks in Turkey (e.g., Shell, Opet, TP) with minimal cost, distance, and time overhead.

Crucially, **GasGraph operates independently of external black-box routing APIs** (such as OSRM or Google Maps API). It constructs its own topological graph engine directly from raw geospatial datasets.

---

## 🚀 Key Features & Architectural Core

1. **Custom Graph Routing Engine:** Built from the ground up using **A\* Search** and **Contraction Hierarchies (CH)** algorithms over localized OpenStreetMap (OSM) topological networks.
2. **Modern Data Engineering (ELT Philosophy):**
   - **Extract:** Scraped heterogeneous datasets spanning tens of thousands of gas stations nationwide.
   - **Load:** Semi-structured raw JSON layers are directly loaded into a unified `JSONB` column structure within the production database to maximize ingestion velocity and preserve schema flexibility.
   - **Transform:** Raw JSON blobs are schema-standardized dynamically via database **SQL Views** and prepared for geospatial processing using **PostGIS**.
3. **Interactive MVP Dashboard:** A stream-reactive frontend built with **Streamlit** and **Folium** to visualize target routes, nodes, and spatial proximity parameters.

---

## 🛠️ Technology Stack

- **Data Processing & Pipeline:** Python 3.13, Pandas, Supabase-py client
- **Database Engine:** Supabase (PostgreSQL 15+) equipped with the **PostGIS** spatial extension
- **Network & Topology Analysis:** NetworkX, OSMnx
- **Visualization & UI (MVP):** Streamlit, Streamlit-Folium
- **Backend Architecture (Target):** FastAPI
- **Mobile Client (Target):** Flutter

---

## 📁 Repository Structure

```text
├── .venv/                  # Virtual Environment (gasgraph-env)
├── data/                   # Scraped raw heterogeneous JSON datasets
├── database/
│   └── schema.sql          # PostGIS configurations, tables, and views definitions
├── pipeline/
│   └── data_loader.py      # ELT Python execution scripts for raw JSON ingestion
├── app.py                  # Streamlit MVP visualization dashboard
├── requirements.txt        # Core project dependencies
└── README.md               # System documentation