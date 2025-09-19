# LOSSAN Rail Realignment Explorer

Interactive web application to explore different rail realignment options for the LOSSAN corridor in Del Mar, CA.

## Features
- View four different proposed rail alignment options
- Search for addresses to see proximity to alignments
- Calculate distances from any location to each alignment option
- Ask questions with an AI "Ask the Map" chat assistant powered by local planning documents

## How to Use
1. Visit the deployed application
2. Enter an address in the search box
3. Click "Search" to find distances to each alignment
4. Use the sidebar's "Ask the Map" chat to query planning documents

## Local Development
To run this application locally:
```
pip install -r requirements.txt
streamlit run app.py
```
The "Ask the Map" chat requires an OpenAI API key and the `openai` Python package.
