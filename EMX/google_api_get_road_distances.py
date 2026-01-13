#import googlemaps
import json
#import requests
import pandas as pd

def get_road_distances(api_key_path, nodes_dict, mode="driving", units="metric"):
    """
    Computes road distances and durations between all pairs of nodes using Google Maps Distance Matrix API.

    Parameters:
    - api_key_path (str): Path to the JSON file containing {"API_key": "your_key"}
    - nodes_dict (dict): Dictionary of node names to (lat, lon) tuples
    - mode (str): Travel mode (default "driving")
    - units (str): Units for distance (default "metric")

    Returns:
    - pd.DataFrame: DataFrame with columns ['from', 'to', 'distance_m', 'duration_s']
    """
    # Load API key
    with open(api_key_path, "r") as f:
        api_key = json.load(f)["API_key"]

    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=api_key)

    # Create origin-destination pairs
    pairs = [(origin, destination) for origin in nodes_dict for destination in nodes_dict if origin != destination]

    results = []

    for origin, destination in pairs:
        origin_coords = nodes_dict[origin]
        destination_coords = nodes_dict[destination]

        response = gmaps.distance_matrix(
            origins=[origin_coords],
            destinations=[destination_coords],
            mode=mode,
            units=units
        )

        element = response['rows'][0]['elements'][0]

        if element.get('status') == 'OK':
            distance = element['distance']['value']
            duration = element['duration']['value']
        else:
            distance = None
            duration = None

        results.append({
            "from": origin,
            "to": destination,
            "distance_m": distance,
            "duration_s": duration
        })

    return pd.DataFrame(results)

def get_road_distances_by_pairs(api_key_path, pairs, nodes_dict, mode="driving", units="metric"):
    """
    Computes road distances and durations between all pairs of nodes using Google Maps Distance Matrix API.

    Parameters:
    - api_key_path (str): Path to the JSON file containing {"API_key": "your_key"}
    - nodes_dict (dict): Dictionary of node names to (lat, lon) tuples
    - mode (str): Travel mode (default "driving")
    - units (str): Units for distance (default "metric")

    Returns:
    - pd.DataFrame: DataFrame with columns ['from', 'to', 'distance_m', 'duration_s']
    """
    # Load API key
    with open(api_key_path, "r") as f:
        api_key = json.load(f)["API_key"]

    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=api_key)

    results = []

    for origin, destination in pairs:
        origin_coords = nodes_dict[origin]
        destination_coords = nodes_dict[destination]

        response = gmaps.distance_matrix(
            origins=[origin_coords],
            destinations=[destination_coords],
            mode=mode,
            units=units
        )

        element = response['rows'][0]['elements'][0]

        if element.get('status') == 'OK':
            distance = element['distance']['value']
            duration = element['duration']['value']
        else:
            distance = None
            duration = None

        results.append({
            "from": origin,
            "to": destination,
            "distance_m": distance,
            "duration_s": duration
        })

    return pd.DataFrame(results)