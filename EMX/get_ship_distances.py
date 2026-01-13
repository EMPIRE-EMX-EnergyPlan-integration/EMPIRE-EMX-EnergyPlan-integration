import pandas as pd
import searoute as sr

#%%
# Load your CSV file
df = pd.read_csv("InputOutput/Ship_Routes.csv", encoding='latin1')

# Function to calculate sea distance
def calculate_sea_distance(row):
    origin = [row['from lon'], row['from lat']]
    destination = [row['to lon'], row['to lat']]
    try:
        route = sr.searoute(origin, destination)
        distance_km = route.properties['length']
        return round(distance_km, 3)
    except Exception as e:
        print(f"Error calculating route for row {row.name}: {e}")
        return None

# function to retrieve geojson feature from searoute
def get_searoute_feature(row):
    origin = [row['from lon'], row['from lat']]
    destination = [row['to lon'], row['to lat']]
    try:
        route = sr.searoute(origin, destination)
        return route["geometry"]["coordinates"]
    except Exception as e:
        print(f"Error calculating route from {origin} to {destination}: {e}")
        return None

# Apply the function to each row
df['distance_km'] = df.apply(calculate_sea_distance, axis=1)
df['route'] = df.apply(get_searoute_feature, axis=1)


# Save the result
df.to_csv("InputOutput/Ship_Distances.csv", index=False)
print("Distances calculated and saved to ports_with_distances.csv")
