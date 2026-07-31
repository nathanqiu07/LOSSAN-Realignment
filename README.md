# LOSSAN Rail Realignment Explorer

An interactive web map for exploring proposed rail realignment concepts along the Los Angeles–San Diego–San Luis Obispo (LOSSAN) corridor near Del Mar, California.

The application converts railway engineering station data into map coordinates, renders each alignment and its construction types, and lets users compare the distance between a searched address and the proposed routes.

[Open the deployed LOSSAN Rail Realignment Explorer](https://lossan-realignment.streamlit.app/)

![Overview of the LOSSAN rail realignment alternatives](LOSSAN%20Rail%20Realignment%20Tracks.png)

## Features

- Explore five alignment concepts:
  - Yellow — San Dieguito Bridge to I-5
  - Blue — Under Crest Canyon
  - Purple — Under Camino Del Mar
  - Green — Del Mar Bluffs double track
  - Northern Yellow — a more northerly alternative
- Toggle individual alignments on and off.
- Inspect bridges, bored tunnels, cut-and-cover tunnels, trenches, floodwalls, U-sections, and portals.
- Search for an address in the San Diego area.
- Calculate the shortest distance from a searched location to each visible alignment.
- Display the nearest geological boring location.
- Switch between the 2024 and 2025 boring datasets.
- View measurements in both feet and meters.

## Running locally

### Prerequisites

- Python 3.11 or newer
- `pip`
- GEOS development libraries, if they are not already available on your system

### Installation

Clone the repository, create a virtual environment, and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Debian- or Ubuntu-based systems, the required native libraries can be installed with:

```bash
sudo apt-get update
sudo apt-get install libgeos-dev python3-rtree
```

### Start the application

```bash
streamlit run app.py
```

Streamlit will normally open the application at `http://localhost:8501`.

## Using the map

1. Use the sidebar checkboxes to select the alignments you want to compare.
2. Choose whether to display boring locations and select a survey year.
3. Enter a San Diego-area address and select **Search**.
4. Review the distance table in the sidebar.
5. Hover over route sections and markers for construction and location details.

At least one alignment must be enabled before an address search can be performed.

## Project structure

```text
.
├── app.py                       # Primary Streamlit application (Phase 1)
├── utils/
│   ├── engineering_coords.py    # Station parsing and coordinate conversion
│   ├── tangent_line.py          # Tangent geometry and rendering
│   ├── spiral_curve.py          # Railway transition spirals
│   ├── circular_curve.py        # Circular railway curves
│   ├── railway_curve.py         # Complete spiral-curve-spiral assemblies
│   ├── railway_alignment.py     # Alignment, segment, and track-type models
│   └── portal.py                # Portal positioning and map markers
├── Phase 1/                     # Snapshot matching the primary application
├── Phase 2/                     # Track-width and elevation/depth enhancements
├── requirements.txt             # Python dependencies
├── packages.txt                 # Native deployment dependencies
└── setup.sh                     # Native-library setup helper
```

Historical Python prototypes are kept locally in the ignored `unused-python/` directory.

## How alignment geometry works

Each route is defined from:

- known latitude/longitude reference points;
- engineering station values such as `24+04.67`;
- tangent lengths and optional manual bearings; and
- spiral and circular curve parameters.

`RailwayAlignment` chains these segments together to generate an ordered coordinate path. Construction-type station ranges are then overlaid on that path. For address comparisons, Shapely finds the nearest point on each visible alignment and Geopy calculates the geodesic distance to that point.

## Phase variants

The root application represents the Phase 1 experience. The `Phase 2` snapshot builds on the same alignment model with:

- approximate track-width buffer zones;
- ground and track elevation profiles;
- station-based depth interpolation; and
- more detailed elevation/depth tooltips.

To explore a phase snapshot directly:

```bash
streamlit run "Phase 1/app.py"
streamlit run "Phase 2/app.py"
```

## Geocoding

Address search uses the OpenCage geocoding service and constrains results to the San Diego area. An OpenCage API key is required for this feature.

Before deploying the project publicly, configure the key through Streamlit secrets or an environment variable rather than committing it to source control.

## Technology

- [Streamlit](https://streamlit.io/) — application interface
- [Folium](https://python-visualization.github.io/folium/) and Leaflet — interactive map
- [Shapely](https://shapely.readthedocs.io/) — nearest-point calculations
- [Geopy](https://geopy.readthedocs.io/) — geodesic distances
- [OpenCage](https://opencagedata.com/) — address geocoding
- NumPy and Pandas — geometry support and distance-table formatting

## Data and accuracy

The proposed routes are approximations based on publicly available SANDAG alignment exhibits referenced in the application. The map, station calculations, construction boundaries, boring locations, and distance results are provided for informational and educational purposes only.

This project is not an official SANDAG application, engineering survey, environmental document, or source of authoritative project data. Consult SANDAG and the relevant published studies for current project information.

## Contact

Created by Nathan Q.

Questions and feedback: [lossanrealignment@gmail.com](mailto:lossanrealignment@gmail.com)
