# -*- coding: utf-8 -*-
"""
Created on Mon Nov 11 14:26:42 2024

@author: dimitrip
"""

import osmium as osm
import pandas as pd
import geopandas
# from shapely.geometry import shape, Point
from tqdm import tqdm
import numpy as np
import os

#%% Function definition
# Define handler for reading OSM file
class PowerlineHandler(osm.SimpleHandler):
    def __init__(self):
        osm.SimpleHandler.__init__(self)
        self.num_nodes = 0
        self.num_ways = 0
        self.power_nodes = []
        self.power_ways = []
        self.wkbfab = osm.geom.WKBFactory()
    # def node(self, n):
    #     if 'power' in n.tags and n.tags['power'] == 'line':
    #         self.nodes.append(n)

    def way(self, w):
        if 'power' in w.tags and ((w.tags['power'] == 'line') or (w.tags['power'] == 'cable')):
            if 'voltage' in w.tags:
                voltage=w.tags['voltage'].split(';')
                if any([int(i)>110000 for i in voltage if i.isdigit()]): 
                    row = { "w_id": w.id}
                    node_list=[]
                    for n in w.nodes:
                        coord={}
                        tmp = str(n.location).split('/')
                        coord["lon"] = tmp[0]
                        coord["lat"] = tmp[1]
                        node_list.append(coord)
                    row["nodes"] = node_list
                    
                    for key, value in w.tags:
                        row[key] = value
                        
                    self.power_ways.append(row)
                    self.num_ways += 1

def extract_start_end_nodes(power_ways_df):
    start_nodes = []
    end_nodes = []
    for idx, row in power_ways_df.iterrows():
        start_node = row['nodes'][0]
        end_node = row['nodes'][-1]
        start_nodes.append({'w_id': row['w_id'], 'lon': float(start_node['lon']), 'lat': float(start_node['lat'])})
        end_nodes.append({'w_id': row['w_id'], 'lon': float(end_node['lon']), 'lat': float(end_node['lat'])})
    start_nodes_df = pd.DataFrame(start_nodes)
    end_nodes_df = pd.DataFrame(end_nodes)
    return start_nodes_df, end_nodes_df

def extract_nodes(power_ways_df):
    nodes = []
    for idx, row in power_ways_df.iterrows():
        for node in row['nodes']:
            nodes.append({'w_id': row['w_id'], 'lon': float(node['lon']), 'lat': float(node['lat'])}) 
    nodes_df = pd.DataFrame(nodes)
    return nodes_df

def sum_separated_values(value):
    if isinstance(value, str) and ';' in value:
        return sum(map(int, value.split(';')))
    return value

#%% Read OSM File                    
# https://download.geofabrik.de/europe.html
# area = 'luxembourg'
# area = 'europe'
# area = 'sweden'
# area = 'denmark'
# area = 'finland'
# area = 'norway'

# areas = ['norway']
# areas = ['europe']
read_osm = False
plot_nodes = True
areas = ['norway','finland','denmark','sweden']
NUTS_level = 3

if read_osm == True:
    for area in areas:
        file = f'InputOutput/OSM/{area}-latest.osm.pbf'
        
        # Initialize the handler with the limit
        handler = PowerlineHandler()
        
        # Apply the handler to the input file
        handler.apply_file(file, locations=True)
        
        # show stats
        print(area)
        print(f"num_ways: {handler.num_ways}")
        print(f"num_nodes: {handler.num_nodes}")
        
        if area == areas[0]:
            power_ways_df = pd.DataFrame(handler.power_ways)
        else:
            power_ways_df = pd.concat([power_ways_df,pd.DataFrame(handler.power_ways)], ignore_index=True)
    
    # Define the output file path
    output_file = f'InputOutput/{area}_filtered_powerlines.xlsx'
    
    # Remove the output file if it already exists
    if os.path.exists(output_file):
        os.remove(output_file)
        
    power_ways_df.to_excel(output_file)
    
    # Read shape of NUTS3 regions and find nodes inside
    # Read shapes of NUTS regions for europe
    # https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/territorial-units-statistics
    gdf = geopandas.read_file("InputOutput/NUTS_RG_01M_2024_4326.geojson")
    gdf = gdf[gdf['LEVL_CODE'] == NUTS_level]
    
    nodes_df = extract_nodes(power_ways_df)
    
    # Create GeoDataFrames for nodes
    nodes_gdf = geopandas.GeoDataFrame(nodes_df, geometry=geopandas.points_from_xy(nodes_df.lon, nodes_df.lat), crs='EPSG:4326')
    
    # Perform spatial join
    nodes_gdf = nodes_gdf.to_crs(gdf.crs)
    
    nodes_joined = geopandas.sjoin(nodes_gdf, gdf, how='left', predicate='within')
    
    # Extract unmatched nodes
    unmatched_nodes = nodes_gdf[nodes_joined['NUTS_ID'].isna()]
    
    # Initialize buffer size and matched flag
    buffer_size = 0  # Initial buffer size in meter
    max_buffer_size = 15000  # Maximum buffer size to prevent infinite loop
    
    progress_bar = tqdm(total=max_buffer_size, desc="Buffering Nodes", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
    all_duplicates = geopandas.GeoDataFrame(columns=unmatched_nodes.columns)
    while not unmatched_nodes.empty and buffer_size <= max_buffer_size:
        # Re-project to a projected CRS (UTM)
        unmatched_nodes = unmatched_nodes.to_crs(epsg=3857)
        gdf = gdf.to_crs(epsg=3857)
        
        # Apply buffer to unmatched nodes
        unmatched_nodes['geometry'] = unmatched_nodes.geometry.buffer(buffer_size)
        
        # Perform spatial join with buffer
        nodes_joined_buffered = geopandas.sjoin(unmatched_nodes, gdf, how='left', predicate='intersects')
        
        # Re-project back to the original CRS
        nodes_joined_buffered = nodes_joined_buffered.to_crs(epsg=4326)
        
        # Identify duplicates
        duplicates = nodes_joined_buffered[nodes_joined_buffered.index.duplicated(keep=False)]
    
        # Append duplicates to the all_duplicates DataFrame
        all_duplicates = pd.concat([all_duplicates, duplicates])
        
        nodes_joined_buffered = nodes_joined_buffered[~nodes_joined_buffered.index.duplicated(keep='first')]
    
        # Update the original join results with the buffered join results
        nodes_joined.update(nodes_joined_buffered)
        
        # Extract still unmatched nodes
        unmatched_nodes = nodes_gdf[nodes_joined['NUTS_ID'].isna()]
        
        # Increase buffer size
        if buffer_size < 1000:
            buffer_size += 10
        elif buffer_size < 10000:
            buffer_size += 100
        else: 
            buffer_size += 500
            
        # Update the progress bar
        progress_bar.update(buffer_size)
        progress_bar.set_description(f"Buffering Nodes (Current buffer size: {buffer_size})")
    progress_bar.close()
        
    if nodes_joined['NUTS_ID'].isna().sum() > 0:
        print("Not matched: ",nodes_joined['NUTS_ID'].isna().sum())
        nodes_joined = nodes_joined.dropna(subset=['NUTS_ID'])
        print("Dropped not matched")
        
    # only keep one instance per NUTS region
    nodes_joined_unique = nodes_joined.drop_duplicates(subset=['w_id', 'NUTS_ID'])
    
    # filter w_id that hove only one NUTS_ID to only keep lines connecting different NUTS regions
    # Step 1: Group by 'w_id' and count unique 'NUTS_ID'
    w_id_counts = nodes_joined_unique.groupby('w_id')['NUTS_ID'].nunique()
    
    # Step 2: Filter 'w_id' values that have more than one unique 'NUTS_ID'
    w_id_multiple_nuts = w_id_counts[w_id_counts > 1].index
    
    # Step 3: Filter 'nodes_joined_unique' to keep only these 'w_id' values
    filtered_nodes_joined_unique = nodes_joined_unique[nodes_joined_unique['w_id'].isin(w_id_multiple_nuts)]
    
    # Filter 'power_ways_df' to keep only 'w_id' values present in 'filtered_nodes_joined_unique'
    filtered_power_ways_df_tmp = power_ways_df[power_ways_df['w_id'].isin(filtered_nodes_joined_unique['w_id'])]
    
    # merge useful information from nodes_joined_unique into power_ways_df
    filtered_power_ways_df = filtered_power_ways_df_tmp.merge(
        filtered_nodes_joined_unique[['w_id', 'NUTS_ID', 'NUTS_NAME', 'CNTR_CODE', 'NAME_LATN']],
        on='w_id',
        how='left'
    )
    
    # Remove the output file if it already exists
    if os.path.exists(output_file):
        os.remove(output_file)
        
    filtered_power_ways_df.to_excel(output_file)

#%% Calculate the transmission capacities of the lines
# We use a linear regression made from the following data point fo common ratings at different voltage levels:
    # 132 kV -> 75 MVA
    # 220 kV -> 200 MVA
    # 400 kV -> 500 MVA
    # 500 kV -> 800 MVA
# This gives the relation P = 1.917V - 206 with P in MVA and V in kV

if read_osm == False:
    filtered_power_ways_df = pd.read_excel(f'InputOutput/{areas[-1]}_filtered_powerlines.xlsx')
    
filtered_power_ways_df['circuits'] = filtered_power_ways_df['circuits'].fillna(1).apply(sum_separated_values)
filtered_power_ways_df['circuits'] = filtered_power_ways_df['circuits'].astype(int)
filtered_power_ways_df.loc[:,"Circuits_Assumed"] = [int(x) for x in filtered_power_ways_df["circuits"].fillna(1)]
filtered_power_ways_df['voltage'] = filtered_power_ways_df['voltage'].str.lstrip(';')
filtered_power_ways_df.loc[:,"Voltage_Assumed_kV"] = [np.mean([int(y) for y in x.split(';')])/1000 for x in filtered_power_ways_df["voltage"]]
filtered_power_ways_df.loc[:,"Transmission_Capacity_MVA"] = filtered_power_ways_df["Circuits_Assumed"] * (1.917 * filtered_power_ways_df["Voltage_Assumed_kV"]- 206)

# Make a df with from/to structure

from_to_list = []
for w_id, group in filtered_power_ways_df.groupby('w_id'):
    group = group.reset_index(drop=True)
    for i in range(len(group) - 1):
        from_to_list.append(pd.concat([group.iloc[i], group.iloc[i + 1][['NUTS_ID', 'NUTS_NAME', 'CNTR_CODE', 'NAME_LATN']].add_prefix('To_')]))
    
power_ways_from_to_df = pd.DataFrame(from_to_list)

# Rename the columns for the 'From' node
power_ways_from_to_df = power_ways_from_to_df.rename(columns={'NUTS_ID': 'From_NUTS_ID', 'NUTS_NAME': 'From_NUTS_NAME', 'CNTR_CODE': 'From_CNTR_CODE', 'NAME_LATN': 'From_NAME_LATN'})

#%% Group by from/to

# Create a new column with sorted 'from' and 'to' pairs
power_ways_from_to_df['pair'] = power_ways_from_to_df.apply(lambda row: tuple(sorted([row['From_NUTS_ID'], row['To_NUTS_ID']])), axis=1)

# Group by the new 'pair' column and sum the 'value' column
result = power_ways_from_to_df.groupby('pair')['Transmission_Capacity_MVA'].sum().reset_index()

# Manual fix for some missing lines in due to interrupted powerways
if tuple(("NO092","DK050")) not in map(tuple,result.pair.unique()) and tuple(("DK050","NO092")) not in map(tuple,result.pair.unique()):
    result.loc[len(result)]=[("NO092","DK050"),1763]
if tuple(("SE232","DK050")) not in map(tuple,result.pair.unique()) and tuple(("DK050","SE232")) not in map(tuple,result.pair.unique()):
    result.loc[len(result)]=[("SE232","DK050"),709]

# If you want to split the pair back into two columns
result[['From_NUTS_ID', 'To_NUTS_ID']] = pd.DataFrame(result['pair'].tolist(), index=result.index)
result = result.drop(columns=['pair'])

#%% save to excel

result.to_csv("InputOutput/Transmission_Capacities.csv",index=False)

#%% plot nodes

if plot_nodes:
    import pandas as pd
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from shapely.geometry import LineString
    import numpy as np
    
    gdf = gdf.to_crs(epsg=4326)
    # Filter out overseas territories by focusing on the main European continent
    gdf = gdf.cx[-10:40, 53:70]
    # Filter to focus on the Nordics (Norway, Denmark, Finland, and Sweden) and the specific German region DEF0C
    gdf = gdf[(gdf['CNTR_CODE'].isin(['NO', 'DK', 'FI', 'SE', 'DE', 'NL', 'EE', 'LT', 'LV', 'PL', 'UK', 'BE']))] #| (gdf['NUTS_ID'] == 'DEF0C')]

    # plot all nodes
    fig, ax = plt.subplots(figsize=(30, 30))
    gdf.plot(ax=ax, color='grey', markersize=50)
    nodes_gdf.plot(ax=ax, color='red',markersize=1)

    # Add labels for the regions
    # for x, y, label in zip(gdf.geometry.centroid.x, gdf.geometry.centroid.y, gdf['NUTS_ID']):
    #     ax.text(x, y, label, fontsize=12, ha='right')

    plt.title('Map with Unmatched Nodes')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig("Figures/all_nodes.png", dpi=300, bbox_inches='tight')
    plt.show()
    
    fig, ax = plt.subplots(figsize=(30, 30))
    gdf.plot(ax=ax, color='grey', markersize=50)
    nodes_gdf.plot(ax=ax, column='w_id', cmap='Spectral',markersize=1)

    plt.title('Map with Unmatched Nodes')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig("Figures/all_nodes_.png", dpi=300, bbox_inches='tight')
    plt.show()
    
    # Test
    lat_min=57
    lat_max=58.5
    lon_min=7.5
    lon_max=9.5
    test = nodes_gdf[(nodes_gdf.lon < lon_max) & (nodes_gdf.lon > lon_min) & (nodes_gdf.lat < lat_max) & (nodes_gdf.lat > lat_min)]
    gdf_ = gdf.cx[lon_min:lon_max, lat_min:lat_max]
    fig, ax = plt.subplots(figsize=(30, 30))
    gdf_.plot(ax=ax, color='grey', markersize=50)
    test.plot(ax=ax, column='w_id', cmap='Spectral',markersize=1)

    plt.title('Map with Unmatched Nodes')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig("Figures/test.png", dpi=300, bbox_inches='tight')
    plt.show()


    # plot joined nodes
    fig, ax = plt.subplots(figsize=(30, 30))
    gdf.plot(ax=ax, color='grey', markersize=50)
    nodes_joined.plot(ax=ax, color='red',markersize=1)

    # Add labels for the regions
    # for x, y, label in zip(gdf.geometry.centroid.x, gdf.geometry.centroid.y, gdf['NUTS_ID']):
    #     ax.text(x, y, label, fontsize=12, ha='right')

    plt.title('Map with Unmatched Nodes')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig("Figures/joined_nodes.png", dpi=300, bbox_inches='tight')
    plt.show()

    # plot unmatched nodes
    fig, ax = plt.subplots(figsize=(30, 30))
    gdf.plot(ax=ax, color='grey', markersize=50)
    unmatched_nodes.plot(ax=ax, color='red') 

    # Add labels for the regions
    # for x, y, label in zip(gdf.geometry.centroid.x, gdf.geometry.centroid.y, gdf['NUTS_ID']):
    #     ax.text(x, y, label, fontsize=12, ha='right')

    plt.title('Map with Unmatched Nodes')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.savefig("Figures/unmatched_nodes.png", dpi=300, bbox_inches='tight')
    plt.show()