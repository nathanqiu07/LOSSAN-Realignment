import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
import numpy as np
import pandas as pd
from folium.plugins import AntPath
from utils import create_curved_path, create_circular_curve, create_spiral_curve
from utils.engineering_coords import (
    calculate_track_parameters, 
    station_to_gis, 
    parse_station,
    parse_angle,
    calculate_radius_from_degree_of_curve,
    format_station
)
from utils.spiral_curve import create_railway_spiral, add_railway_spiral_to_map
from utils.circular_curve import create_railway_circular_curve, add_railway_circular_curve_to_map
from utils.tangent_line import add_railway_tangent_to_map
from utils.railway_curve import add_complete_railway_curve_to_map, add_complete_railway_alignment_to_map
from utils.railway_alignment import RailwayAlignment, TangentSegment, CurveSegment
from utils.portal import Portal
from opencage.geocoder import OpenCageGeocode
from utils.chatbot import ask as ask_chatbot, HAVE_LANGCHAIN

try:
    from shapely.geometry import LineString, Point
except ImportError:
    st.error("Failed to import Shapely. Please check your installation.")
    LineString = None
    Point = None

# Set page config first
st.set_page_config(layout="wide")

# Hide default Streamlit footer and add padding
st.markdown(
    """
    <style>
    footer {visibility: hidden;}
    /* Make the main content area fill available space but not overflow */
    .main {
        flex: 1 1 auto;
        overflow: auto;
    }
    /* Make overall container fill the viewport exactly */
    .stApp {
        display: flex;
        flex-direction: column;
        height: 100vh;
        overflow: hidden;
    }
    /* Fix the footer at the bottom */
    .custom-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background-color: white;
        padding: 10px 20px;
        border-top: 1px solid #ddd;
        z-index: 999;
    }
    /* Ensure content doesn't get hidden behind the footer */
    [data-testid="stAppViewBlockContainer"] {
        padding-bottom: 60px;
    }
    /* Make sidebar wider to fit table contents but not too wide */
    [data-testid="stSidebar"] {
        min-width: 380px !important;
        max-width: 380px !important;
    }
    /* Adjust for sidebar */
    [data-testid="stSidebar"][aria-expanded="true"] ~ div .custom-footer {
        left: var(--sidebar-width, 380px);
    }
    [data-testid="stSidebar"][aria-expanded="false"] ~ div .custom-footer {
        left: 0;
    }
    /* Adjust the height of the map container */
    iframe {
        height: calc(100vh - 200px) !important;
    }
    .folium-map .leaflet-pane path:not(.yellow-bridge-overlay) {
        pointer-events: none !important;
    }
    /* Style for instructions */
    .instruction-box {
        background-color: #e6f2ff;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #4b92e5;
        margin-bottom: 20px;
        overflow-wrap: break-word;
        word-wrap: break-word;
        word-break: break-word;
        white-space: normal;
        overflow-x: hidden;
        max-width: 100%;
        display: block;
    }
    .instruction-box h3 {
        color: #1e3a8a;
        margin-bottom: 15px;
        font-size: 1.3em;
    }
    .instruction-box p {
        margin-bottom: 15px;
        width: 100%;
        display: block;
    }
    .instruction-box strong {
        display: block;
        margin-bottom: 5px;
        color: #2c5282;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("LOSSAN Rail Realignment Explorer")

# Create a container for the main content
main_content = st.container()

with main_content:
    # Add instructions to the main page using a blue box
    st.markdown("""
    <div style="background-color: #e6f2ff; padding: 20px; border-radius: 10px; border-left: 5px solid #4b92e5; 
         margin-bottom: 20px; border: 2px solid #4b92e5; box-shadow: 0 0 10px rgba(75, 146, 229, 0.3);">
        <h2>How to Use the Interactive Map</h2>
        
        Search Your Address:
        Enter your home address in the search bar and click "Search." The map will display the shortest distance from your location to each proposed rail realignment route and the nearest boring site.
        
        Explore Infrastructure Details:
        Hover over each alignment line to view detailed infrastructure components—such as portals, bored tunnels, cut-and-cover sections, trenches, and U-structures. Hover on pins to view boring locations for geotechnical and geological data collection.
        
        Customize the View:
        Use the checkboxes to toggle individual alignments and boring locations on or off, depending on what you'd like to explore.
    </div>
    """, unsafe_allow_html=True)
    
    # --- 1. define your four alignments (lat, lon) lists here ---
    # Green track will now be an engineering track, so we'll remove it from ALIGNMENTS
    ALIGNMENTS = {}

    # --- 2. address input & geocoding ---
    st.sidebar.subheader("Search Location")
    
    # Simple text input for address without autocomplete
    address_input = st.sidebar.text_input("Enter address", value=st.session_state.get("address", ""), key="address_input")
    
    # Check if Enter key was pressed (when the text input value changes)
    if "address_input" in st.session_state and "previous_address" not in st.session_state:
        st.session_state.previous_address = ""
        
    enter_pressed = False
    if "address_input" in st.session_state and "previous_address" in st.session_state:
        if st.session_state.address_input != st.session_state.previous_address and st.session_state.address_input:
            enter_pressed = True
        st.session_state.previous_address = st.session_state.address_input
    
    # Initialize session state for track visibility if not present
    if "track_visibility" not in st.session_state:
        st.session_state.track_visibility = {
            "yellow": True,
            "blue": True,
            "purple": True,
            "green": True,
            "northern_yellow": True
        }
    
    # Check if any tracks are visible
    any_tracks_visible = any(st.session_state.track_visibility.values())
    
    # Search button - disable if no tracks are visible
    if not any_tracks_visible and address_input:
        st.sidebar.warning("Please enable at least one track before searching")
        search = False
    else:
        # Trigger search either by button or Enter key
        button_search = st.sidebar.button("Search")
        search = button_search or enter_pressed
    
    # Track visibility options
    st.sidebar.subheader("Track Visibility")
    
    # Create toggle options for each track
    st.sidebar.checkbox("Yellow Track", value=st.session_state.track_visibility["yellow"], 
                        key="yellow_track_visible", 
                        on_change=lambda: st.session_state.track_visibility.update({"yellow": st.session_state.yellow_track_visible}))
    
    st.sidebar.checkbox("Blue Track", value=st.session_state.track_visibility["blue"], 
                        key="blue_track_visible", 
                        on_change=lambda: st.session_state.track_visibility.update({"blue": st.session_state.blue_track_visible}))
    
    st.sidebar.checkbox("Purple Track", value=st.session_state.track_visibility["purple"], 
                        key="purple_track_visible", 
                        on_change=lambda: st.session_state.track_visibility.update({"purple": st.session_state.purple_track_visible}))
    
    st.sidebar.checkbox("Green Track", value=st.session_state.track_visibility["green"], 
                        key="green_track_visible", 
                        on_change=lambda: st.session_state.track_visibility.update({"green": st.session_state.green_track_visible}))
    
    st.sidebar.checkbox("Northern Yellow Track", value=st.session_state.track_visibility["northern_yellow"], 
                        key="northern_yellow_track_visible", 
                        on_change=lambda: st.session_state.track_visibility.update({"northern_yellow": st.session_state.northern_yellow_track_visible}))

    # Add boring locations control
    st.sidebar.subheader("Boring Locations")
    
    # Initialize boring visibility in session state if not present
    if "boring_visibility" not in st.session_state:
        st.session_state.boring_visibility = True
    
    # Initialize boring year selection in session state if not present
    if "boring_year" not in st.session_state:
        st.session_state.boring_year = "2025"
        
    # Add checkbox to toggle boring locations
    st.sidebar.checkbox("Show Boring Locations", value=st.session_state.boring_visibility,
                        key="boring_locations_visible",
                        on_change=lambda: setattr(st.session_state, "boring_visibility", st.session_state.boring_locations_visible))
    
    # Add radio buttons to select boring year
    st.sidebar.radio("Boring Location Year", 
                     options=["2025", "2024"],
                     key="boring_year_selection",
                     on_change=lambda: setattr(st.session_state, "boring_year", st.session_state.boring_year_selection))
    
    # Add info about boring locations
    with st.sidebar.expander("Boring Locations Info"):
        st.write("These markers represent boring locations used for geological surveys along the proposed railway alignments.")
        st.write("The 'R-' prefix indicates regular borings, while 'RC-' indicates rock core samples.")
        st.write("You can toggle between 2024 and 2025 boring locations using the radio buttons above.")

    st.sidebar.subheader("Ask the Map")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.sidebar.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if not HAVE_LANGCHAIN:
        st.sidebar.warning("LangChain dependencies are missing; chat is unavailable.")
    elif question := st.sidebar.chat_input("Ask a question about the realignment"):
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.sidebar.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = ask_chatbot(question)
            st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})

    # Initialize session state for location if not present
    if "location" not in st.session_state:
        st.session_state["location"] = None

    if search and address_input:
        # Initialize OpenCage geocoder with API key
        opencage_api_key = "e4a3fe37fe3d469499dc77e798f65245"  # Replace with your OpenCage API key
        geocoder = OpenCageGeocode(opencage_api_key)
        
        try:
            # Define bounds for San Diego area
            socal_bounds = "-117.4,32.5,-116.8,33.3"  # San Diego County area
            
            # Perform geocoding with bounds constraint
            results = geocoder.geocode(address_input, bounds=socal_bounds)
            
            if results and len(results):
                # Extract location data from the first result
                location_data = results[0]
                
                # Create a location object with the required attributes
                class LocationResult:
                    def __init__(self, lat, lng, formatted):
                        self.latitude = lat
                        self.longitude = lng
                        self.address = formatted
                
                location = LocationResult(
                    location_data['geometry']['lat'],
                    location_data['geometry']['lng'],
                    location_data['formatted']
                )
                
                st.session_state["address"] = address_input
                st.session_state["location"] = location
            else:
                st.sidebar.error("Address not found")
                st.session_state["location"] = None
        except Exception as e:
            st.sidebar.error(f"Geocoding service error: {str(e)}")
            st.session_state["location"] = None

    # Use session state location for display
    location = st.session_state.get("location", None)
    address = st.session_state.get("address", "")

    # --- 3. build the Folium map ---
    # default center over Del Mar
    center = (32.975, -117.245)
    initial_zoom = 13
    if location:
        center = (location.latitude, location.longitude)
        initial_zoom = 15

    m = folium.Map(location=center, zoom_start=initial_zoom, tiles="OpenStreetMap")

    # Dictionary to store expanded coordinates for each alignment
    expanded_alignments = {}

    

    # === YELLOW TRACK ENGINEERING MODEL ===
    # Create the yellow track using the engineering specifications and directly add to map
    
    # Known engineering data for the first curve of the yellow track
    station_2000_coords = (32.9740081, -117.2669915)  # 20+00 station
    station_2500_coords = (32.9726647, -117.2666647)  # 25+00 station
    
    # Create a new Railway Alignment for the Yellow route
    yellow_alignment = RailwayAlignment(name="Yellow Route: Engineering Alignment", color="#FFD700")  # Gold yellow - less bright
    
    # Add reference points
    yellow_alignment.add_reference_point("STA_2000", station_2000_coords, 2000)
    yellow_alignment.add_reference_point("STA_2500", station_2500_coords, 2500)
    
    # Calculate track parameters based on reference points
    track_params = yellow_alignment.calculate_track_params("STA_2000", "STA_2500")
    
    # Define segments for the Yellow route
    
    # First tangent segment
    yellow_first_tangent = yellow_alignment.add_tangent("20+00", "24+04.67", name="Initial Tangent")
    
    # First spiral-curve-spiral segment
    yellow_first_curve = yellow_alignment.add_curve(
        ts_station="24+04.67", 
        sc_station="25+44.67", 
        cs_station="30+43.75", 
        st_station="31+83.75",
        degree_of_curve="9 00'00\"", 
        direction="right",
        name="First Curve"
    )
    
    # Second tangent segment
    yellow_second_tangent = yellow_alignment.add_tangent("31+83.75", "37+45.96", name="Middle Tangent")
    
    # Second spiral-curve-spiral segment
    yellow_second_curve = yellow_alignment.add_curve(
        ts_station="37+45.96", 
        sc_station="39+05.96",  # 39+05.96 = 37+45.96 + 160' (corrected spiral length)
        cs_station="40+60.67", 
        st_station="42+20.67",  # 42+20.67 = 40+60.67 + 160' (corrected spiral length)
        degree_of_curve="9 30'00\"",  # Corrected degree of curve: 9° 30' 00"
        direction="left",
        name="Second Curve"
    )
    
    # Third tangent segment (extended alignment)
    yellow_third_tangent = yellow_alignment.add_tangent("42+20.67", "75+17.38", name="Extended Tangent")
    
    # Manually set bearing for the extended tangent
    # This is useful to follow the coastline more accurately
    yellow_third_tangent.manual_bearing = 142.25  # Southeast direction (0=North, 90=East, 180=South)
    
    # Third spiral-curve-spiral segment
    yellow_third_curve = yellow_alignment.add_curve(
        ts_station="75+17.38", 
        sc_station="79+17.38",  # 79+17.38 = 75+17.38 + 400' (spiral length)
        cs_station="87+52.17", 
        st_station="91+52.17",  # 91+52.17 = 87+52.17 + 400' (spiral length)
        degree_of_curve="2 24'00\"",  # Degree of curve: 2° 24' 00"
        direction="right",
        name="Third Curve"
    )
    
    # Fourth tangent segment
    yellow_fourth_tangent = yellow_alignment.add_tangent("91+52.17", "94+72.45", name="Fourth Tangent")
    
    # Fourth spiral-curve-spiral segment
    yellow_fourth_curve = yellow_alignment.add_curve(
        ts_station="94+72.45", 
        sc_station="98+72.45",  # 98+72.45 = 94+72.45 + 400' (spiral length)
        cs_station="119+62.32", 
        st_station="123+62.32",  # 123+62.32 = 119+62.32 + 400' (spiral length)
        degree_of_curve="2 24'00\"",  # Degree of curve: 2° 24' 00"
        direction="left",
        name="Fourth Curve"
    )
    
    # Fifth tangent segment
    yellow_fifth_tangent = yellow_alignment.add_tangent("123+62.32", "162+59.46", name="Fifth Tangent")
    yellow_fifth_tangent.manual_bearing = 171  # Southeast direction (0=North, 90=East, 180=South)
    
    # Fifth spiral-curve-spiral segment
    yellow_fifth_curve = yellow_alignment.add_curve(
        ts_station="162+59.46", 
        sc_station="169+09.46",  # 169+09.46 = 162+59.46 + 650' (spiral length)
        cs_station="175+18.79",  # Note: This was labeled as SC in the query but should be CS
        st_station="181+68.79",  # 181+68.79 = 175+18.79 + 650' (spiral length)
        degree_of_curve="0 44'30\"",  # Degree of curve: 0° 44' 30" (very gentle curve)
        direction="left",
        name="Fifth Curve"
    )
    
    # Sixth tangent segment
    yellow_sixth_tangent = yellow_alignment.add_tangent("181+68.79", "196+22.24", name="Sixth Tangent")
    
    # Sixth spiral-curve-spiral segment (MT1 CURVE #6)
    yellow_sixth_curve = yellow_alignment.add_curve(
        ts_station="196+22.24", 
        sc_station="202+72.24",  # 202+72.24 = 196+22.24 + 650' (spiral length from box)
        cs_station="208+28.94", 
        st_station="214+78.94",  # 216+43.12 = 209+93.12 + 650' (spiral length from box)
        degree_of_curve="0 44'30\"",  # Degree of curve from box: 0° 44' 30"
        direction="right",
        name="Sixth Curve (MT1 CURVE #6)"
    )
    
    # Seventh tangent segment
    yellow_seventh_tangent = yellow_alignment.add_tangent("214+78.94", "235+49.79", name="Seventh Tangent")
    
    # Seventh spiral-curve-spiral segment (CURVE #7)
    yellow_seventh_curve = yellow_alignment.add_curve(
        ts_station="235+49.79", 
        sc_station="242+29.79",  # 242+29.79 = 235+49.79 + 680' (spiral length)
        cs_station="275+32.84", 
        st_station="282+12.84",  # 282+12.84 = 275+32.84 + 680' (spiral length)
        degree_of_curve="0 49'11\"",  # Degree of curve: 0° 49' 11"
        direction="right",  # Alternating direction from previous curve
        name="Seventh Curve"
    )
    
    # Eighth tangent segment
    yellow_eighth_tangent = yellow_alignment.add_tangent("282+12.84", "285+53.12", name="Eighth Tangent")
    
    # Eighth spiral-curve-spiral segment (CURVE #8)
    yellow_eighth_curve = yellow_alignment.add_curve(
        ts_station="285+53.12", 
        sc_station="287+93.12",  # 287+93.12 = 285+53.12 + 240' (spiral length)
        cs_station="294+53.38", 
        st_station="296+93.38",  # 296+93.38 = 294+53.38 + 240' (spiral length)
        degree_of_curve="0 15'00\"",  # Degree of curve: 0° 15' 00"
        direction="right",  # Alternating direction from previous curve
        name="Eighth Curve"
    )
    
    # Ninth tangent segment
    yellow_ninth_tangent = yellow_alignment.add_tangent("296+93.38", "304+93.02", name="Ninth Tangent")

    
    # === BLUE TRACK ENGINEERING MODEL ===
    # Create the blue track using the engineering specifications and directly add to map

    # Create a new Railway Alignment for the Blue route
    blue_alignment = RailwayAlignment(name="Blue Route: Under Crest Canyon", color="blue")
    
    # Add reference points for the blue track
    blue_sta_500_coords = (32.9731225, -117.2667758)  # 5+00 station
    blue_sta_1000_coords = (32.9717752, -117.2664515)  # 10+00 station
    
    blue_alignment.add_reference_point("STA_500", blue_sta_500_coords, 500)
    blue_alignment.add_reference_point("STA_1000", blue_sta_1000_coords, 1000)
    
    # Calculate track parameters based on reference points
    blue_track_params = blue_alignment.calculate_track_params("STA_500", "STA_1000")
    
    # Define segments for the Blue route - initial tangent
    blue_first_tangent = blue_alignment.add_tangent("5+00", "17+46.12", name="Initial Tangent")
    
    # Add a curve similar to the first segment of the original blue route
    blue_first_curve = blue_alignment.add_curve(
        ts_station="17+46.12",
        sc_station="23+96.12",
        cs_station="54+05.81",
        st_station="60+55.81",
        degree_of_curve="0 48'00\"",
        direction="right",
        name="First Curve"
    )
    
    # Add next tangent
    blue_second_tangent = blue_alignment.add_tangent("60+55.81", "64+00.52", name="Second Tangent")
    blue_second_tangent.manual_bearing = 141.5  # Southeast direction (0=North, 90=East, 180=South)

    # Add second curve (sharper turn toward southeast)
    blue_second_curve = blue_alignment.add_curve(
        ts_station="64+00.52",
        sc_station="70+80.52",
        cs_station="96+80.99",
        st_station="103+60.99",
        degree_of_curve="0 49'35\"",
        direction="left",
        name="Second Curve"
    )
    
    # Add third tangent going southeast
    blue_third_tangent = blue_alignment.add_tangent("103+60.99", "116+60.92", name="Third Tangent")
    
    # Add the curve near Del Mar Heights Road
    blue_third_curve = blue_alignment.add_curve(
        ts_station="116+60.92",
        sc_station="123+40.92",
        cs_station="146+18.69",
        st_station="152+98.69",
        degree_of_curve="0 49'35\"",
        direction="right",
        name="Third Curve"
    )
    
    # Add fourth tangent 
    blue_fourth_tangent = blue_alignment.add_tangent("152+98.69", "156+48.69", name="Fourth Tangent")
    blue_fourth_tangent.manual_bearing = 141.5
    
    # Add fourth curve to align with endpoint
    blue_fourth_curve = blue_alignment.add_curve(
        ts_station="156+48.69",
        sc_station="163+28.69",
        cs_station="192+18.38",
        st_station="198+98.38",
        degree_of_curve="0 49'35\"",
        direction="left",
        name="Fourth Curve"
    )
    
    # Add fifth tangent to reach the end point
    blue_fifth_tangent = blue_alignment.add_tangent("198+98.38", "204+89.02", name="Fifth Tangent")
    #blue_fifth_tangent.manual_bearing = 170  # Southeast direction (0=North, 90=East, 180=South)
    
    # Add fifth curve
    blue_fifth_curve = blue_alignment.add_curve(
        ts_station="204+89.02",
        sc_station="211+69.02",
        cs_station="244+71.53",
        st_station="251+51.53",
        degree_of_curve="0 49'11\"",
        direction="right",
        name="Fifth Curve"
    )
    
    # Add sixth tangent
    blue_sixth_tangent = blue_alignment.add_tangent("251+51.53", "255+07.34", name="Sixth Tangent")
    
    # Add sixth curve
    blue_sixth_curve = blue_alignment.add_curve(
        ts_station="255+07.34",
        sc_station="257+27.34",
        cs_station="264+05.11",
        st_station="266+25.11",
        degree_of_curve="0 15'00\"",
        direction="left",
        name="Sixth Curve"
    )

    blue_seventh_tangent = blue_alignment.add_tangent("266+25.11", "274+32.35", name="Seventh Tangent")
    blue_seventh_tangent.manual_bearing = 135

    # === PURPLE TRACK ENGINEERING MODEL ===
    # Create the purple track using the engineering specifications and directly add to map

    # Create a new Railway Alignment for the Purple route
    purple_alignment = RailwayAlignment(name="Purple Route: Under Camino Del Mar", color="magenta")

    # Add reference points for the purple track
    purple_sta_500_coords = (32.9731225, -117.2667758)  # 5+00 station
    purple_sta_1000_coords = (32.9717752, -117.2664515)  # 10+00 station

    purple_alignment.add_reference_point("STA_500", purple_sta_500_coords, 500)
    purple_alignment.add_reference_point("STA_1000", purple_sta_1000_coords, 1000)

    # Calculate track parameters based on reference points
    purple_track_params = purple_alignment.calculate_track_params("STA_500", "STA_1000")

    # Define segments for the Purple route - initial tangent
    purple_first_tangent = purple_alignment.add_tangent("5+00", "33+23.02", name="Initial Tangent")

    # Add first curve (gentle curve to follow Camino Del Mar)
    purple_first_curve = purple_alignment.add_curve(
        ts_station="33+23.02",
        sc_station="35+73.02",
        cs_station="46+03.60",
        st_station="48+53.60", #48+53.60
        degree_of_curve="1 25'00\"", #1 00'00\"
        direction="left",
        name="First Curve"
    )

    # Add second tangent
    purple_second_tangent = purple_alignment.add_tangent("48+53.60", "51+91.55", name="Second Tangent")
    purple_second_tangent.manual_bearing = 181.75  # Southeast direction

    # Add second curve (sharper turn toward southeast)
    purple_second_curve = purple_alignment.add_curve(
        ts_station="51+91.55",
        sc_station="54+41.55",
        cs_station="71+12.55",
        st_station="73+62.55",
        degree_of_curve="1 00'00\"",
        direction="right",
        name="Second Curve"
    )

    # Add third tangent going southeast
    purple_third_tangent = purple_alignment.add_tangent("73+62.55", "91+37.23", name="Third Tangent")

    # Add the curve near Del Mar Heights Road
    purple_third_curve = purple_alignment.add_curve(
        ts_station="91+37.23",
        sc_station="94+37.23",
        cs_station="108+41.79",
        st_station="111+41.79",
        degree_of_curve="1 06'00\"",
        direction="left",
        name="Third Curve"
    )

    # Add fourth tangent 
    purple_fourth_tangent = purple_alignment.add_tangent("111+41.79", "114+31.56", name="Fourth Tangent")
    #purple_fourth_tangent.manual_bearing = 150  # More southerly direction

    # Add fourth curve to align with endpoint
    purple_fourth_curve = purple_alignment.add_curve(
        ts_station="114+31.56",
        sc_station="117+01.56",
        cs_station="152+41.45",
        st_station="155+11.45",
        degree_of_curve="1 03'30\"",
        direction="right",
        name="Fourth Curve"
    )

    # Add fifth tangent to reach the end point
    purple_fifth_tangent = purple_alignment.add_tangent("155+11.45", "183+01.22", name="Fifth Tangent")

    # Add fifth curve
    purple_fifth_curve = purple_alignment.add_curve(
        ts_station="183+01.22",
        sc_station="188+81.22",
        cs_station="197+17.88",
        st_station="202+97.88",
        degree_of_curve="0 30'00\"",
        direction="right",
        name="Fifth Curve"
    )

    # Add sixth tangent
    purple_sixth_tangent = purple_alignment.add_tangent("202+97.88", "226+46.37", name="Sixth Tangent")
    purple_sixth_tangent.manual_bearing = 133  # More southerly direction

    # Add sixth curve
    purple_sixth_curve = purple_alignment.add_curve(
        ts_station="226+46.37",
        sc_station="233+26.37",
        cs_station="237.58+89",
        st_station="244+38.89",
        degree_of_curve="0 49'35\"",
        direction="left",
        name="Sixth Curve"
    )

    purple_seventh_tangent = purple_alignment.add_tangent("244+38.89", "280+89.19", name="Seventh Tangent")
    #purple_seventh_tangent.manual_bearing = 160  # More southerly direction

    

    # === GREEN TRACK ENGINEERING MODEL ===
    # Create the green track using the engineering specifications based on the purple track
    
    # Create a new Railway Alignment for the Green route
    green_alignment = RailwayAlignment(name="Green Route: Del Mar Bluffs Double-Track", color="green")
    
    # Add reference points for the green track
    green_sta_500_coords = (32.9731225, -117.2667758)  # 5+00 station
    #green_sta_1000_coords = (32.9716252, -117.2664515)  # 10+00 station (mannually edited)
    green_sta_1000_coords = (32.9717752, -117.2664515)  # 10+00 station
    
    green_alignment.add_reference_point("STA_500", green_sta_500_coords, 500)
    green_alignment.add_reference_point("STA_1000", green_sta_1000_coords, 1000)
    
    # Calculate track parameters directly using the engineering_coords function
    # This ensures precise alignment between reference points
    green_track_params = calculate_track_parameters(
        point1=green_sta_500_coords,
        station1=500,
        point2=green_sta_1000_coords,
        station2=1000
    )
    
    # Define segments for the Green route - initial tangent
    # First tangent from STA_500 to STA_1000 (exactly between reference points)
    green_first_tangent = green_alignment.add_tangent("5+00", "10+00", name="Initial Reference Tangent")
    
    # Continue with the rest of the alignment
    green_pre_tangent = green_alignment.add_tangent("10+00", "12+05.15", name="Pre-Curve Tangent")
    
    green_pre_curve = green_alignment.add_curve(
        ts_station="12+05.15",
        sc_station="14+15.15",
        cs_station="17+79.87",
        st_station="19+89.87",
        degree_of_curve="0 40'00\"",
        direction="left",
        name="First Curve"
    )
    
    # Add first curve (gentle curve to follow bluffs)
    green_first_curve = green_alignment.add_curve(
        ts_station="19+89.87",
        sc_station="35+22.79",
        cs_station="36+28.04",
        st_station="37+28.04",
        degree_of_curve="2 55'00\"", #2 09'01
        direction="left",
        name="First Curve"
    )
    
    # Add second tangent
    green_second_tangent = green_alignment.add_tangent("37+28.04", "53+08.78", name="Second Tangent")
    #green_second_tangent.manual_bearing = 178.5
    
    # Add second curve
    green_second_curve = green_alignment.add_curve(
        ts_station="53+08.78",
        sc_station="55+58.78",
        cs_station="60+27.97",
        st_station="62+77.96",
        degree_of_curve="4 09'00\"",
        direction="right",
        name="Second Curve"
    )
    
    # Add third tangent
    green_third_tangent = green_alignment.add_tangent("62+77.96", "71+41.19", name="Third Tangent")
    
    # Add third curve
    green_third_curve = green_alignment.add_curve(
        ts_station="71+41.19",
        sc_station="73+81.19",
        cs_station="76+68.70",
        st_station="79+08.70",
        degree_of_curve="1 20'00\"",
        direction="right",
        name="Third Curve"
    )
    
    # Add fourth tangent
    green_fourth_tangent = green_alignment.add_tangent("79+08.70", "101+45.73", name="Fourth Tangent")
    green_fourth_tangent.manual_bearing = 161
    
    # Add fourth curve
    green_fourth_curve = green_alignment.add_curve(
        ts_station="101+45.73",
        sc_station="105+05.73",
        cs_station="109+96.76",
        st_station="113+56.76",
        degree_of_curve="0 44'35\"",
        direction="left",
        name="Fourth Curve"
    )
    
    # Add fifth tangent
    green_fifth_tangent = green_alignment.add_tangent("113+56.76", "129+11.51", name="Fifth Tangent")
    
    # Add fifth curve
    green_fifth_curve = green_alignment.add_curve(
        ts_station="129+11.51",
        sc_station="131+61.51",
        cs_station="138+79.54",
        st_station="141+29.54",
        degree_of_curve="2 45'00\"", #3 07'00
        direction="right",
        name="Fifth Curve"
    )
    
    # Add sixth tangent
    green_sixth_tangent = green_alignment.add_tangent("141+29.54", "187+10.02", name="Sixth Tangent")
    #green_sixth_tangent.manual_bearing = 135
    
    # Add sixth curve
    green_sixth_curve = green_alignment.add_curve(
        ts_station="187+10.02",
        sc_station="192+90.02",
        cs_station="201+26.67",
        st_station="207+06.67",
        degree_of_curve="0 30'00\"",
        direction="right",
        name="Sixth Curve"
    )
    
    # Add seventh tangent
    green_seventh_tangent = green_alignment.add_tangent("207+06.67", "230+55.17", name="Seventh Tangent")
    
    # Add seventh curve
    green_seventh_curve = green_alignment.add_curve(
        ts_station="230+55.17",
        sc_station="237+35.17",
        cs_station="241+67.68",
        st_station="248+47.68",
        degree_of_curve="0 45'35\"",
        direction="left",
        name="Seventh Curve"
    )

    # Add eighth tangent
    green_eighth_tangent = green_alignment.add_tangent("248+47.68", "284+97.94", name="Eighth Tangent")


    # === NORTHERN YELLOW TRACK ENGINEERING MODEL ===
    # Create the Northern Yellow track following the San Dieguito River path shown in the image
    
    # Create a new Railway Alignment for the Northern Yellow route with orange color
    northern_yellow_alignment = RailwayAlignment(name="Northern Yellow Route", color="orange")
    
    # Use the same reference points as the original Yellow track
    northern_yellow_alignment.add_reference_point("STA_2000", station_2000_coords, 2000)
    northern_yellow_alignment.add_reference_point("STA_2500", station_2500_coords, 2500)
    
    # Calculate track parameters based on reference points - same as yellow track
    northern_yellow_track_params = yellow_alignment.calculate_track_params("STA_2000", "STA_2500")
    
    # Define segments for the Northern Yellow route
    # Start further back with initial tangent from the coast
    northern_yellow_first_tangent = northern_yellow_alignment.add_tangent("10+00", "19+00", name="First Tangent")
    
    # First curve to approach the river
    northern_yellow_first_curve = northern_yellow_alignment.add_curve(
        ts_station="19+00",
        sc_station="22+00",
        cs_station="25+00",
        st_station="28+00",
        degree_of_curve="9 00'00\"",
        direction="right",
        name="First Curve"
    )
    
    # Second tangent (along Del Mar Fairgrounds)
    northern_yellow_second_tangent = northern_yellow_alignment.add_tangent("28+00", "35+00", name="Second Tangent")
    
    # Second curve
    northern_yellow_river_curve = northern_yellow_alignment.add_curve(
        ts_station="35+00",
        sc_station="37+00",
        cs_station="40+00",
        st_station="43+00",
        degree_of_curve="7 00'00\"",
        direction="right",
        name="Second Curve"
    )
    
    # Third tangent (along the south side of Del Mar Racing)
    northern_yellow_third_tangent = northern_yellow_alignment.add_tangent("43+00", "65+00", name="Third Tangent")
    northern_yellow_third_tangent.manual_bearing = 75

    # Third curve
    northern_yellow_third_curve = northern_yellow_alignment.add_curve(
        ts_station="65+00",
        sc_station="68+00",
        cs_station="73+00",
        st_station="76+00",
        degree_of_curve="9 30'00\"",
        direction="left",
        name="Third Curve"
    )

    # Fourth Tangent
    northern_yellow_fourth_tangent = northern_yellow_alignment.add_tangent("76+00", "120+00", name="Fourth Tangent")
    northern_yellow_fourth_tangent.manual_bearing = 163
    
    # Fourth spiral-curve-spiral segment
    northern_yellow_fourth_curve = northern_yellow_alignment.add_curve(
        ts_station="120+00",
        sc_station="125+00",
        cs_station="126+00",
        st_station="131+00",
        degree_of_curve="2 00'00\"",
        direction="left",
        name="Fourth Curve"
    )
    
    # Fifth tangent segment
    northern_yellow_fifth_tangent = northern_yellow_alignment.add_tangent("123+62.32", "175+59.46", name="Fifth Tangent")
    northern_yellow_fifth_tangent.manual_bearing = 171  # Southeast direction (0=North, 90=East, 180=South)
    
    # Fifth spiral-curve-spiral segment
    northern_yellow_fifth_curve = northern_yellow_alignment.add_curve(
        ts_station="175+59.46",
        sc_station="182+09.46",
        cs_station="188+18.79",
        st_station="194+68.79",
        degree_of_curve="0 44'30\"",
        direction="left",
        name="Fifth Curve"
    )
    
    # Sixth tangent segment
    northern_yellow_sixth_tangent = northern_yellow_alignment.add_tangent("194+68.79", "209+22.24", name="Sixth Tangent")
    
    # Sixth spiral-curve-spiral segment (MT1 CURVE #6)
    northern_yellow_sixth_curve = northern_yellow_alignment.add_curve(
        ts_station="209+22.24", 
        sc_station="215+72.24",
        cs_station="221+28.94", 
        st_station="227+78.94",
        degree_of_curve="0 44'30\"",
        direction="right",
        name="Sixth Curve (MT1 CURVE #6)"
    )
    
    # Seventh tangent segment
    northern_yellow_seventh_tangent = northern_yellow_alignment.add_tangent("227+78.94", "248+49.79", name="Seventh Tangent")
    
    # Seventh spiral-curve-spiral segment (CURVE #7)
    northern_yellow_seventh_curve = northern_yellow_alignment.add_curve(
        ts_station="248+49.79", 
        sc_station="255+29.79",
        cs_station="288+32.84", 
        st_station="295+12.84",
        degree_of_curve="0 49'11\"",
        direction="right",
        name="Seventh Curve"
    )
    
    # Eighth tangent segment
    northern_yellow_eighth_tangent = northern_yellow_alignment.add_tangent("295+12.84", "298+53.12", name="Eighth Tangent")
    
    # Eighth spiral-curve-spiral segment (CURVE #8)
    northern_yellow_eighth_curve = northern_yellow_alignment.add_curve(
        ts_station="298+53.12", 
        sc_station="300+93.12",
        cs_station="307+53.38", 
        st_station="309+93.38",
        degree_of_curve="0 15'00\"",
        direction="right",
        name="Eighth Curve"
    )
    
    # Ninth tangent segment
    northern_yellow_ninth_tangent = northern_yellow_alignment.add_tangent("309+93.38", "317+93.02", name="Ninth Tangent")
    # Add CSS to disable hover/tooltips on original polylines
    css = """
    <style>
    .folium-map .leaflet-pane path:not(.yellow-bridge-overlay) {
        pointer-events: none !important;
    }
    </style>
    """
    
    # Add the CSS to the map
    m.get_root().html.add_child(folium.Element(css))
    
    # Add the entire alignment to the map
    if st.session_state.track_visibility["yellow"]:
        yellow_alignment.add_to_map(
            m=m, 
            start_ref_point_name="STA_2000", 
            track_params=track_params,
            add_markers=False,  # Hide all pin points
            hide_technical_info=True  # Hide tangent/curve information
        )
        
        # Define track type sections for the Yellow alignment
        yellow_alignment.add_track_type_section(
            track_type="Yellow Track Initial Tangent",
            start_station="20+00",
            end_station="24+00",
            color="#FFD700",
            tooltip="Yellow Track"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="Bridge",
            start_station="24+00",
            end_station="78+00",
            color="#FFD700",
            tooltip="Yellow Track: Bridge"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="78+00",
            end_station="86+00",
            color="#FFD700",
            tooltip="Yellow Track: Cut and Cover Tunnel"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="Bored Tunnel",
            start_station="86+00",
            end_station="226+00",
            color="#FFD700",
            tooltip="Yellow Track: Bored Tunnel"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="226+00",
            end_station="234+00",
            color="#FFD700",
            tooltip="Yellow Track: Cut and Cover Tunnel"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="U-Section",
            start_station="234+00",
            end_station="255+00",
            color="#FFD700",
            tooltip="Yellow Track: U-Section"
        )
        
        yellow_alignment.add_track_type_section(
            track_type="Yellow Track Last Tangent",
            start_station="255+00",
            end_station="304+93.02",
            color="#FFD700",
            tooltip="Yellow Track"
        )
    
    # Render the yellow track type sections
    if st.session_state.track_visibility["yellow"]:
        yellow_alignment.render_track_type_sections(m)
    
    # Add the blue alignment to the map with hidden technical details
    if st.session_state.track_visibility["blue"]:
        blue_alignment.add_to_map(
            m=m,
            start_ref_point_name="STA_500",
            track_params=blue_track_params,
            add_markers=False,  # Hide all pin points
            hide_technical_info=True  # Hide tangent/curve information
        )
        
        # Define track type sections for the Blue alignment
        blue_alignment.add_track_type_section(
            track_type="Blue Track Initial Tangent",
            start_station="5+00",
            end_station="14+00",
            color="blue",
            tooltip="Blue Track"
        )
        
        blue_alignment.add_track_type_section(
            track_type="Floodwalls",
            start_station="14+00",
            end_station="20+00",
            color="blue",
            tooltip="Blue Track: Floodwalls"
        )
        
        blue_alignment.add_track_type_section(
            track_type="U-Section",
            start_station="20+00",
            end_station="26+00",
            color="blue",
            tooltip="Blue Track: U-Section"
        )
        
        blue_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="26+00",
            end_station="30+00",
            color="blue",
            tooltip="Blue Track: Cut and Cover Tunnel"
        )
        
        blue_alignment.add_track_type_section(
            track_type="Bored Tunnel",
            start_station="30+00",
            end_station="195+00",
            color="blue",
            tooltip="Blue Track: Bored Tunnel"
        )
        
        blue_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="195+00",
            end_station="204+00",
            color="blue",
            tooltip="Blue Track: Cut and Cover Tunnel"
        )
        
        blue_alignment.add_track_type_section(
            track_type="U-Section",
            start_station="204+00",
            end_station="224+00",
            color="blue",
            tooltip="Blue Track: U-Section"
        )

        blue_alignment.add_track_type_section(
            track_type="Blue Track Last Tangent",
            start_station="224+00",
            end_station="274+32.35",
            color="blue",
            tooltip="Blue Track"
        )
        
        # Render the blue track type sections
        blue_alignment.render_track_type_sections(m)
    
    # Add the purple alignment to the map
    if st.session_state.track_visibility["purple"]:
        purple_alignment.add_to_map(
            m=m,
            start_ref_point_name="STA_500",
            track_params=purple_track_params,
            add_markers=False,  # Hide all pin points
            hide_technical_info=True  # Hide tangent/curve information
        )
        
        # Define track type sections for the Purple alignment
        purple_alignment.add_track_type_section(
            track_type="Purple Track Initial Tangent",
            start_station="5+00",
            end_station="11+00",
            color="magenta",
            tooltip="Purple Track"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Floodwalls",
            start_station="11+00",
            end_station="19+00",
            color="magenta",
            tooltip="Purple Track: Floodwalls"
        )
        
        purple_alignment.add_track_type_section(
            track_type="U-Section",
            start_station="19+00",
            end_station="26+00",
            color="magenta",
            tooltip="Purple Track: U-Section"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="26+00",
            end_station="30+00",
            color="magenta",
            tooltip="Purple Track: Cut and Cover Tunnel"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Bored Tunnel",
            start_station="30+00",
            end_station="129+00",
            color="magenta",
            tooltip="Purple Track: Bored Tunnel"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Cut and Cover Tunnel",
            start_station="129+00",
            end_station="130+00",
            color="magenta",
            tooltip="Purple Track: Cut and Cover Tunnel"
        )
        
        purple_alignment.add_track_type_section(
            track_type="U-Section",
            start_station="130+00",
            end_station="133+00",
            color="magenta",
            tooltip="Purple Track: U-Section"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Bridge",
            start_station="133+00",
            end_station="180+00",
            color="magenta",
            tooltip="Purple Track: Bridge"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Purple Track Middle Tangent",
            start_station="180+00",
            end_station="187+00",
            color="magenta",
            tooltip="Purple Track"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Bridge",
            start_station="187+00",
            end_station="199+00",
            color="magenta",
            tooltip="Purple Track: Bridge"
        )
        
        purple_alignment.add_track_type_section(
            track_type="Purple Track Last Tangent",
            start_station="199+00",
            end_station="280+89.19",
            color="magenta",
            tooltip="Purple Track"
        )
        
        # Render the purple track type sections
        purple_alignment.render_track_type_sections(m)
    
    # Add the green alignment to the map
    if st.session_state.track_visibility["green"]:
        green_alignment.add_to_map(
            m=m,
            start_ref_point_name="STA_500",
            track_params=green_track_params,
            add_markers=False,  # Hide all pin points
            hide_technical_info=True  # Hide tangent/curve information
        )
        
        # Define track type sections for the Green alignment
        green_alignment.add_track_type_section(
            track_type="Green Track Initial Tangent",
            start_station="5+00",
            end_station="48+00",
            color="green",
            tooltip="Green Track"
        )
        
        green_alignment.add_track_type_section(
            track_type="Trench",
            start_station="48+00",
            end_station="89+00",
            color="green",
            tooltip="Green Track: Trench"
        )
        
        green_alignment.add_track_type_section(
            track_type="Green Track Middle Tangent",
            start_station="89+00",
            end_station="141+00",
            color="green",
            tooltip="Green Track"
        )
        
        green_alignment.add_track_type_section(
            track_type="Bridge",
            start_station="141+00",
            end_station="184+00",
            color="green",
            tooltip="Green Track: Bridge"
        )
        
        green_alignment.add_track_type_section(
            track_type="Green Track Short Tangent",
            start_station="184+00",
            end_station="191+00",
            color="green",
            tooltip="Green Track"
        )
        
        green_alignment.add_track_type_section(
            track_type="Bridge",
            start_station="191+00",
            end_station="203+00",
            color="green",
            tooltip="Green Track: Bridge"
        )
        
        green_alignment.add_track_type_section(
            track_type="Green Track Last Tangent",
            start_station="203+00",
            end_station="284+97.94",
            color="green",
            tooltip="Green Track"
        )
        
        # Render the green track type sections
        green_alignment.render_track_type_sections(m)
    
    # Add the Northern Yellow alignment to the map
    if st.session_state.track_visibility["northern_yellow"]:
        northern_yellow_alignment.add_to_map(
            m=m,
            start_ref_point_name="STA_2000",
            track_params=northern_yellow_track_params,
            add_markers=False,  # Hide all pin points
            hide_technical_info=True  # Hide tangent/curve information
        )

        northern_yellow_alignment.render_track_type_sections(m)
    
    # Define all portals using the Portal class
    portals = [
        # Blue track portals
        Portal(
            name="Jimmy Durante Blvd Portal",
            track_alignment=blue_alignment,
            station_value=2600,  # 26+00
            color="blue",
            description="Western portal of the Blue Route tunnel under Jimmy Durante Blvd"
        ),
        
        # Purple track portals
        Portal(
            name="Torrey Pines Rd West Portal",
            track_alignment=purple_alignment,
            station_value=13000,  # 130+00
            color="magenta",
            description="Western portal of the Purple Route tunnel under Torrey Pines Road"
        ),
        
        # Yellow track portals
        Portal(
            name="Racetrack View Dr Portal",
            track_alignment=yellow_alignment,
            station_value=7800,  # 82+00
            color="red",
            description="Northern portal of the Yellow Route tunnel at Racetrack View Drive"
        ),
        
        Portal(
            name="I-5 Knoll Portal",
            track_alignment=yellow_alignment,
            station_value=parse_station("234+00"),  # TS station of the seventh curve
            color="#B8860B",  # Dark goldenrod
            description="Southern portal of the Yellow Route tunnel at I-5 Knoll"
        )
    ]
    
    # Add all portals to the map
    for portal in portals:
        # Only add portals for tracks that are visible
        track_alignment = portal.track_alignment
        if track_alignment == yellow_alignment and st.session_state.track_visibility["yellow"]:
            portal.add_to_map(m)
        elif track_alignment == blue_alignment and st.session_state.track_visibility["blue"]:
            portal.add_to_map(m)
        elif track_alignment == purple_alignment and st.session_state.track_visibility["purple"]:
            portal.add_to_map(m)
        elif track_alignment == green_alignment and st.session_state.track_visibility["green"]:
            portal.add_to_map(m)
        elif track_alignment == northern_yellow_alignment and st.session_state.track_visibility["northern_yellow"]:
            portal.add_to_map(m)
    
    # Add animated path for the Northern Yellow track
    if northern_yellow_alignment.all_coords:
        # Add a solid base line
        folium.PolyLine(
            locations=northern_yellow_alignment.all_coords,
            color='orange',
            weight=7,
            opacity=0.7,
            tooltip="Northern Yellow Route"
        ).add_to(m)
        
        # Add animated path
        AntPath(
            locations=northern_yellow_alignment.all_coords,
            dash_array=[10, 20],
            delay=800,
            color='orange',
            pulseColor='white',
            paused=False,
            weight=5,
            opacity=0.9,
            tooltip="Northern Yellow Route",
            className="northern-yellow-route-overlay"  # Special class to allow hover
        ).add_to(m)
    
    # Add boring location markers
    boring_locations_2024 = [
        {"name": "R-24-002", "latitude": 32.919826, "longitude": -117.239439},
        {"name": "R-24-004", "latitude": 32.919798, "longitude": -117.241627},
        {"name": "R-24-005B", "latitude": 32.93025, "longitude": -117.245635},
        {"name": "R-24-008", "latitude": 32.970812, "longitude": -117.266118},
        {"name": "RC-24-11", "latitude": 32.965970, "longitude": -117.264261},
        {"name": "RC-24-12", "latitude": 32.967189, "longitude": -117.265276},
        {"name": "RC-24-13", "latitude": 32.939822, "longitude": -117.260618},
        {"name": "RC-24-14", "latitude": 32.933054, "longitude": -117.246391},
        {"name": "RC-24-15", "latitude": 32.926628, "longitude": -117.241601},
        {"name": "RC-24-16", "latitude": 32.947879, "longitude": -117.261747},
        {"name": "RC-24-17", "latitude": 32.951342, "longitude": -117.255873},
        {"name": "RC-24-18", "latitude": 32.954228, "longitude": -117.262734},
        {"name": "RC-24-30", "latitude": 32.980163, "longitude": -117.268140},
        {"name": "RC-24-31", "latitude": 32.973985, "longitude": -117.265193},
        {"name": "RC-24-32", "latitude": 32.969438, "longitude": -117.261282},
        {"name": "RC-24-33", "latitude": 32.969282, "longitude": -117.258178},
        {"name": "RC-24-34", "latitude": 32.967745, "longitude": -117.259878},
        {"name": "RC-24-35", "latitude": 32.967481, "longitude": -117.251245},
        {"name": "RC-24-36", "latitude": 32.963180, "longitude": -117.255802},
        {"name": "RC-24-37", "latitude": 32.961115, "longitude": -117.248894},
        {"name": "RC-24-38", "latitude": 32.951487, "longitude": -117.244680},
        {"name": "RC-24-38 (Alternate)", "latitude": 32.945097, "longitude": -117.243998},
        {"name": "RC-24-39", "latitude": 32.938215, "longitude": -117.242444}
    ]
    
    # Add 2025 boring location markers from the table
    boring_locations_2025 = [
        {"name": "R-25-001", "latitude": 32.971046, "longitude": -117.264254},
        {"name": "R-25-001 (ALT)", "latitude": 32.970734, "longitude": -117.264221},
        {"name": "R-25-002", "latitude": 32.969379, "longitude": -117.261362},
        {"name": "R-25-003", "latitude": 32.966078, "longitude": -117.258489},
        {"name": "R-25-004", "latitude": 32.970336, "longitude": -117.265995},
        {"name": "R-25-005", "latitude": 32.971853, "longitude": -117.260492},
        {"name": "R-25-006", "latitude": 32.959975, "longitude": -117.26774},
        {"name": "R-25-007", "latitude": 32.9728194, "longitude": -117.2562306},
        {"name": "RC-25-008", "latitude": 32.950464, "longitude": -117.26495},
        {"name": "R-25-009", "latitude": 32.971503, "longitude": -117.250369},
        {"name": "RC-25-010", "latitude": 32.941742, "longitude": -117.261893},
        {"name": "RC-25-010 (ALT)", "latitude": 32.941251, "longitude": -117.26162},
        {"name": "RC-25-011", "latitude": 32.9653444, "longitude": -117.2489528},
        {"name": "R-25-012", "latitude": 32.920027, "longitude": -117.241851},
        {"name": "R-25-013", "latitude": 32.921952, "longitude": -117.239029},
        {"name": "SR-4", "latitude": 32.928348, "longitude": -117.251231},
        {"name": "SR-4", "latitude": 32.925997, "longitude": -117.248887},
        {"name": "SR-5", "latitude": 32.932889, "longitude": -117.256222},
        {"name": "SR-5", "latitude": 32.930735, "longitude": -117.254084},
        {"name": "RC-25-014", "latitude": 32.967197, "longitude": -117.265296},
        {"name": "RC-25-015", "latitude": 32.965777, "longitude": -117.26387},
        {"name": "RC-25-016", "latitude": 32.954454, "longitude": -117.263053},
        {"name": "RC-25-017", "latitude": 32.94787, "longitude": -117.261761},
        {"name": "RC-25-018", "latitude": 32.939808, "longitude": -117.260643},
        {"name": "RC-25-019", "latitude": 32.957757, "longitude": -117.258327},
        {"name": "RC-25-019 (ALT)", "latitude": 32.955799, "longitude": -117.257076},
        {"name": "RC-25-020", "latitude": 32.949152, "longitude": -117.253271},
        {"name": "RC-25-020 (ALT)", "latitude": 32.949558, "longitude": -117.253189},
        {"name": "RC-25-021", "latitude": 32.934571, "longitude": -117.245331},
        {"name": "RC-25-021 (ALT)", "latitude": 32.935461, "longitude": -117.246732},
        {"name": "RC-25-022", "latitude": 32.930696, "longitude": -117.242233},
        {"name": "RC-25-023", "latitude": 32.926629, "longitude": -117.241608},
        {"name": "RC-25-024", "latitude": 32.9629, "longitude": -117.254686},
        {"name": "RC-25-025", "latitude": 32.957772, "longitude": -117.252188},
        {"name": "RC-25-025 (ALT)", "latitude": 32.95783, "longitude": -117.252372},
        {"name": "RC-25-026", "latitude": 32.930579, "longitude": -117.241966},
        {"name": "RC-25-027", "latitude": 32.95108, "longitude": -117.244676},
        {"name": "RC-25-028", "latitude": 32.937633, "longitude": -117.242141}
    ]
    
    # Select the boring locations based on the selected year
    boring_locations = boring_locations_2024 if st.session_state.boring_year == "2024" else boring_locations_2025
    
    # Create a feature group for boring markers so they can be toggled as a group
    boring_markers = folium.FeatureGroup(name=f"Boring Locations ({st.session_state.boring_year})")
    
    # Add each boring marker to the map if boring visibility is enabled
    if st.session_state.boring_visibility:
        for boring in boring_locations:
            # Use CircleMarker instead of DivIcon for better compatibility
            folium.CircleMarker(
                location=[boring["latitude"], boring["longitude"]],
                radius=6,
                color='white',
                fill=True,
                fill_color='#4B0082' if st.session_state.boring_year == "2024" else '#006400',  # Purple for 2024, Dark Green for 2025
                fill_opacity=1.0,
                weight=2,
                tooltip=boring["name"],
                popup=folium.Popup(
                    f"""
                    <div style="min-width: 150px; text-align: center;">
                        <h4>{boring["name"]}</h4>
                        <p>Latitude: {boring["latitude"]}<br>
                        Longitude: {boring["longitude"]}<br>
                        Year: {st.session_state.boring_year}</p>
                    </div>
                    """,
                    max_width=300
                )
            ).add_to(boring_markers)
    
    # Add the feature group to the map
    boring_markers.add_to(m)
    
    # Add a control to toggle boring markers
    folium.LayerControl().add_to(m)
                
    # if we have a valid location, plot it + compute distances
    if location:
        addr_pt = (location.latitude, location.longitude)
        folium.Marker(addr_pt, tooltip=address, icon=folium.Icon(color="red")).add_to(m)

        # Create Point object for shapely operations
        pt = Point(location.longitude, location.latitude)

        st.sidebar.markdown("## Distances to Each Alignment")
        
        # Create dictionary to store all route distances
        distance_data = {
            "Route": [],
            "Feet": [],
            "Meters": []
        }
        
        for name, data in expanded_alignments.items():
            # Skip if the track is not visible
            track_name = name.lower().split()[0]  # Extract first word (yellow, blue, etc.)
            
            # Special case for "Northern Yellow"
            if "northern" in track_name:
                track_name = "northern_yellow"
                
            if track_name in st.session_state.track_visibility and not st.session_state.track_visibility[track_name]:
                continue
                
            # Create a LineString from the coordinates
            smoothed_coords = data
            
            # Create a LineString from the smoothed coordinates
            line = LineString([(lon, lat) for lat, lon in smoothed_coords])
            pt = Point(location.longitude, location.latitude)

            # find nearest point on the line
            nearest = line.interpolate(line.project(pt))
            nearest_lat, nearest_lon = nearest.y, nearest.x

            # geodesic distance in meters
            dist_m = geodesic(addr_pt, (nearest_lat, nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            dist_ft = int(round(dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            dist_m_rounded = int(round(dist_m / 10) * 10)  # Round to nearest 10 meters

            # draw a connector
            folium.PolyLine(
                [addr_pt, (nearest_lat, nearest_lon)],
                color="magenta" if "Purple" in name else "green" if "Green" in name else "#FF7700",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Get simplified route name
            if "Yellow" in name and "Northern" not in name:
                simple_name = "Yellow Route"
            elif "Blue" in name:
                simple_name = "Blue Route"
            elif "Purple" in name:
                simple_name = "Purple Route"
            elif "Green" in name:
                simple_name = "Green Route"
            elif "Northern Yellow" in name:
                simple_name = "Northern Yellow Route"
            else:
                simple_name = name
                
            # Add to distance data dictionary
            distance_data["Route"].append(simple_name)
            distance_data["Feet"].append(f"{dist_ft}")
            distance_data["Meters"].append(f"{dist_m_rounded}")
            
        # Calculate distance to yellow track
        if st.session_state.track_visibility["yellow"] and yellow_alignment.all_coords:
            yellow_line = LineString([(lon, lat) for lat, lon in yellow_alignment.all_coords])
            yellow_nearest = yellow_line.interpolate(yellow_line.project(pt))
            yellow_nearest_lat, yellow_nearest_lon = yellow_nearest.y, yellow_nearest.x
            yellow_dist_m = geodesic(addr_pt, (yellow_nearest_lat, yellow_nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            yellow_dist_ft = int(round(yellow_dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            yellow_dist_m_rounded = int(round(yellow_dist_m / 10) * 10)  # Round to nearest 10 meters
            
            # Draw a connector
            folium.PolyLine(
                [addr_pt, (yellow_nearest_lat, yellow_nearest_lon)],
                color="#FF7700",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Add to distance data dictionary
            distance_data["Route"].append("Yellow Route")
            distance_data["Feet"].append(str(yellow_dist_ft))
            distance_data["Meters"].append(str(yellow_dist_m_rounded))
        
        # Calculate distance to blue track
        if st.session_state.track_visibility["blue"] and blue_alignment.all_coords:
            blue_line = LineString([(lon, lat) for lat, lon in blue_alignment.all_coords])
            blue_nearest = blue_line.interpolate(blue_line.project(pt))
            blue_nearest_lat, blue_nearest_lon = blue_nearest.y, blue_nearest.x
            blue_dist_m = geodesic(addr_pt, (blue_nearest_lat, blue_nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            blue_dist_ft = int(round(blue_dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            blue_dist_m_rounded = int(round(blue_dist_m / 10) * 10)  # Round to nearest 10 meters
            
            # Draw a connector
            folium.PolyLine(
                [addr_pt, (blue_nearest_lat, blue_nearest_lon)],
                color="blue",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Add to distance data dictionary
            distance_data["Route"].append("Blue Route")
            distance_data["Feet"].append(str(blue_dist_ft))
            distance_data["Meters"].append(str(blue_dist_m_rounded))
        
        # Calculate distance to purple track
        if st.session_state.track_visibility["purple"] and purple_alignment.all_coords:
            purple_line = LineString([(lon, lat) for lat, lon in purple_alignment.all_coords])
            purple_nearest = purple_line.interpolate(purple_line.project(pt))
            purple_nearest_lat, purple_nearest_lon = purple_nearest.y, purple_nearest.x
            purple_dist_m = geodesic(addr_pt, (purple_nearest_lat, purple_nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            purple_dist_ft = int(round(purple_dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            purple_dist_m_rounded = int(round(purple_dist_m / 10) * 10)  # Round to nearest 10 meters
            
            # Draw a connector
            folium.PolyLine(
                [addr_pt, (purple_nearest_lat, purple_nearest_lon)],
                color="magenta",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Add to distance data dictionary
            distance_data["Route"].append("Purple Route")
            distance_data["Feet"].append(str(purple_dist_ft))
            distance_data["Meters"].append(str(purple_dist_m_rounded))
        
        # Calculate distance to green track
        if st.session_state.track_visibility["green"] and green_alignment.all_coords:
            green_line = LineString([(lon, lat) for lat, lon in green_alignment.all_coords])
            green_nearest = green_line.interpolate(green_line.project(pt))
            green_nearest_lat, green_nearest_lon = green_nearest.y, green_nearest.x
            green_dist_m = geodesic(addr_pt, (green_nearest_lat, green_nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            green_dist_ft = int(round(green_dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            green_dist_m_rounded = int(round(green_dist_m / 10) * 10)  # Round to nearest 10 meters
            
            # Draw a connector
            folium.PolyLine(
                [addr_pt, (green_nearest_lat, green_nearest_lon)],
                color="green",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Add to distance data dictionary
            distance_data["Route"].append("Green Route")
            distance_data["Feet"].append(str(green_dist_ft))
            distance_data["Meters"].append(str(green_dist_m_rounded))
        
        # Calculate distance to Northern Yellow track
        if st.session_state.track_visibility["northern_yellow"] and northern_yellow_alignment.all_coords:
            northern_yellow_line = LineString([(lon, lat) for lat, lon in northern_yellow_alignment.all_coords])
            northern_yellow_nearest = northern_yellow_line.interpolate(northern_yellow_line.project(pt))
            northern_yellow_nearest_lat, northern_yellow_nearest_lon = northern_yellow_nearest.y, northern_yellow_nearest.x
            northern_yellow_dist_m = geodesic(addr_pt, (northern_yellow_nearest_lat, northern_yellow_nearest_lon)).meters
            
            # Convert to different units and round (ensure integers)
            northern_yellow_dist_ft = int(round(northern_yellow_dist_m * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
            northern_yellow_dist_m_rounded = int(round(northern_yellow_dist_m / 10) * 10)  # Round to nearest 10 meters
            
            # Draw a connector
            folium.PolyLine(
                [addr_pt, (northern_yellow_nearest_lat, northern_yellow_nearest_lon)],
                color="orange",
                weight=2,
                dash_array="5,5"
            ).add_to(m)
            
            # Add to distance data dictionary
            distance_data["Route"].append("Northern Yellow Route")
            distance_data["Feet"].append(str(northern_yellow_dist_ft))
            distance_data["Meters"].append(str(northern_yellow_dist_m_rounded))
            
            # Find which segment of the northern yellow track is closest
            northern_yellow_min_distance = float('inf')
            northern_yellow_closest_segment = None
            northern_yellow_segment_index = None
            
            for i, segment in enumerate(northern_yellow_alignment.segments):
                segment_linestring = LineString([(lon, lat) for lat, lon in northern_yellow_alignment.segment_coords[i]])
                segment_nearest = segment_linestring.interpolate(segment_linestring.project(pt))
                segment_dist = geodesic(addr_pt, (segment_nearest.y, segment_nearest.x)).meters
                
                if segment_dist < northern_yellow_min_distance:
                    northern_yellow_min_distance = segment_dist
                    northern_yellow_closest_segment = segment
                    northern_yellow_segment_index = i
        
        # Calculate distance to each boring location if they're visible
        if st.session_state.boring_visibility and boring_locations:
            
            # Find the closest boring location
            closest_boring = None
            closest_boring_dist = float('inf')
            
            for boring in boring_locations:
                boring_point = (boring["latitude"], boring["longitude"])
                dist = geodesic(addr_pt, boring_point).meters
                
                if dist < closest_boring_dist:
                    closest_boring_dist = dist
                    closest_boring = boring
            
            if closest_boring:
                # Convert to different units (ensure integers)
                closest_boring_dist_ft = int(round(closest_boring_dist * 3.28084 / 10) * 10)  # Convert meters to feet and round to nearest 10 feet
                closest_boring_dist_m_rounded = int(round(closest_boring_dist / 10) * 10)  # Round to nearest 10 meters
                
                # Draw a connector to the closest boring location
                folium.PolyLine(
                    [addr_pt, (closest_boring["latitude"], closest_boring["longitude"])],
                    color="purple" if st.session_state.boring_year == "2024" else "darkgreen",
                    weight=2,
                    dash_array="5,5"
                ).add_to(m)
                
                # Add boring location to distance data
                distance_data["Route"].append(f"Boring ({st.session_state.boring_year}): {closest_boring['name']}")
                distance_data["Feet"].append(str(closest_boring_dist_ft))
                distance_data["Meters"].append(str(closest_boring_dist_m_rounded))
                
        # Display all distances in a table
        if distance_data["Route"]:
            # First, let's add custom CSS to control table column widths and prevent wrapping
            st.markdown("""
                <style>
                    /* Make sure the table cells don't wrap text */
                    .dataframe td, .dataframe th {
                        white-space: nowrap !important;
                        text-align: left !important;
                        padding: 6px 8px !important;
                        overflow: visible !important;
                    }
                    /* Set fixed widths for table columns */
                    .dataframe {
                        width: 100% !important;
                        table-layout: fixed !important;
                    }
                    /* Adjust column widths */
                    .dataframe th:nth-child(1), .dataframe td:nth-child(1) {
                        width: 50% !important; /* Route name column */
                        font-size: 13px !important;
                    }
                    .dataframe th:nth-child(2), .dataframe td:nth-child(2),
                    .dataframe th:nth-child(3), .dataframe td:nth-child(3) {
                        width: 25% !important; /* Numeric columns */
                        text-align: right !important;
                        font-size: 13px !important;
                    }
                    /* Fix the index column width */
                    .dataframe th:first-child, .dataframe td:first-child {
                        width: 25px !important;
                        max-width: 25px !important;
                        min-width: 25px !important;
                        padding-left: 4px !important;
                        padding-right: 2px !important;
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Format all values consistently before display
            formatted_data = {
                "Route": distance_data["Route"].copy(),
                "Feet": [],
                "Meters": []
            }
            
            # Format the feet and meters values to ensure they're integers
            for i in range(len(distance_data["Route"])):
                try:
                    formatted_data["Feet"].append(int(distance_data["Feet"][i]))
                    formatted_data["Meters"].append(int(distance_data["Meters"][i]))
                except:
                    formatted_data["Feet"].append(distance_data["Feet"][i])
                    formatted_data["Meters"].append(distance_data["Meters"][i])
            
            # Create the DataFrame with consistent formatting
            df = pd.DataFrame(formatted_data)
            
            # Display the table with right alignment for numeric columns
            # First convert the numeric columns to strings with right alignment
            df['Feet'] = df['Feet'].apply(lambda x: str(x))
            df['Meters'] = df['Meters'].apply(lambda x: str(x))
            st.sidebar.table(df)

    # --- 4. render ---
    # Set the map height to fill available space while leaving room for header and footer
    st_folium(m, width="100%")

# --- 5. Footer with credits and disclaimer ---
# Create footer using native Streamlit elements
st.markdown("<div class='custom-footer'>", unsafe_allow_html=True)
footer_cols = st.columns([3, 1])
with footer_cols[0]:
    st.markdown("""
    Disclaimer:
    The four proposed routes and their associated distance calculations presented in this interactive map are based on the most recent publicly available documentation from SANDAG: San Diego LOSSAN Rail Realignment Project Post Value Analysis Study Assessment – Appendix A: Exhibits of the Staff-Recommended Alignments (published May 16, 2025). This tool is for informational and educational purposes only and is not an official source of project data. Users should refer directly to SANDAG for authoritative and up-to-date project information. 
    """)
with footer_cols[1]:
    st.markdown("""
    **Created by:** Nathan Q. \\
    **Contact:** [lossanrealignment@gmail.com](mailto:lossanrealignment@gmail.com) \\
    **For Questions Regarding the Alignments Contact:** Coalition for Safter Trains
    """)
    
st.markdown("</div>", unsafe_allow_html=True)

#test