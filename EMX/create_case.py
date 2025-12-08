# -*- coding: utf-8 -*-
"""
Created on Fri Dec 13 09:28:54 2024

@author: dimitrip
"""
#%% Imports
import pandas as pd
import numpy as np
import geopandas
from google_api_get_road_distances import get_road_distances, get_road_distances_by_pairs
from math import radians, cos, sin, asin, sqrt
import sys


#%% Helper functions
def write_to_yaml(output, filename):
    with open(filename, 'w') as file:
        for line in output:
            file.write(f"{line}\n")
            
def find_pairs(tuples_set, target_string):
    result = set()
    for a, b in tuples_set:
        if a == target_string:
            result.add(b)
        elif b == target_string:
            result.add(a)
    return result

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians 
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula 
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371 # Radius of earth in kilometers. Use 3956 for miles. Determines return value units.
    return c * r

def main():
    #%% User Input
    case_name = "eur_15x_elec"
    case_folder = f"full_model_{case_name}" # Case folder inside EMPIRE_res_folder
    if len(sys.argv) > 2:
        EMPIRE_res_folder = sys.argv[2]
    else:
        EMPIRE_res_folder = "../EMPIRE_results"
    if len(sys.argv) > 1:
        EMPIRE_input_folder = sys.argv[1]
    else:
        EMPIRE_input_folder = f'InputOutput/{EMPIRE_res_folder}/Tab_Files_full_model_{case_name}'
    # Define the NUTS_level we are working with
    NUTS_level = 3
    # Recalculate road distances between regions
    recalc_road_distances = False
    #Google API key path
    google_api_key_path = "google_API_key.json"
    # Countries in spatial scope
    country_scope = ["SE","DK","FI","NO"]
    # Name of default area used in EMX modelling for nordic regions
    default_area = {"SE":"default_SE","DK":"default_DK","FI":"default_FI","NO":"default_NO"}
    default_external= "default_external_region"
    # Name of transmission modes in EMX modelling to consider for neighboring regions
    default_neighboring_tm = ["H2_Pipeline","LH2_Road","H2_Road"]
    # Name of transmission modes in EMX modelling to consider for regions with LNG terminal
    #default_coastal_tm = ["NH3_Ship","LH2_Ship"]
    default_coastal_tm = ["LH2_Ship"]
    ship_speed = 30 #km/h - 16 knots
    t_load_unload = 24 # hours
    t_safety_margin = 24 # hours
    # Number of strategic periods, used only for our dummy case
    n_str_period = 4
    n_scenario = 1

    # Mapping of technologies from ENTSOE to EMPIRE
    entsoe_to_empire_tech_mapping = {"Biomass":"Bioexisting",
    "Fossil Gas":"Gasexisting",
    "Fossil Gas":"Gas_OCGT",
    "Fossil Hard Coal":"Coalexisting",
    "Fossil Oil":None,  # No fossil oil in EMPIRE 
    "Fossil Peat":"Ligniteexisting",
    "Hydro Pumped Storage":"HydroPumpStorage",
    "Hydro Run-of-river and poundage":"Hydrorun-of-the-river",
    "Hydro Water Reservoir":"Hydroregulated",
    "Nuclear":"Nuclear",
    "Other":None,  # corresponds to CHPs that do not seem to be in EMPIRE 
    "Solar":"Solar",
    "Wind Offshore":"Windoffshoregrounded",
    "Wind Onshore":"Windonshore"}
    #empire_to_entsoe_tech_mapping = {v: k for k, v in entsoe_to_empire_tech_mapping.items() if v is not None}
    empire_to_entsoe_tech_mapping = {
        "Bioexisting":"Biomass",
        "Gasexisting":"Fossil Gas",
        "GasOCGT":"Fossil Gas",
        "Coalexisting":"Fossil Hard Coal",
        # No fossil oil in EMPIRE 
        "Ligniteexisting":"Fossil Peat",
        "Liginiteexisting":"Fossil Peat", # TYPO in EMPIRE tech name sometime?
        "HydroPumpStorage":"Hydro Pumped Storage",
        "Hydrorun-of-the-river":"Hydro Run-of-river and poundage",
        "Hydroregulated":"Hydro Water Reservoir",
        "Nuclear":"Nuclear",
        "Solar":"Solar",
        "Windoffshoregrounded":"Wind Offshore",
        "Windonshore":"Wind Onshore",
        "Waste":"Biomass", # is there a better mappinbg for this?
        # "Other" in ENTSO-e data corresponds to CHPs that do not seem to be in EMPIRE 
    }

    empire_to_EMX_tech_mapping = {
        "Bioexisting":"Bio_existing",
        "Gasexisting":"Gas_existing",
        "GasOCGT":"Gas_OCGT",
        "Coalexisting":"Coal_existing",
        # No fossil oil in EMPIRE 
        "Ligniteexisting":"Lignite_existing",
        "Liginiteexisting":"Lignite_existing", # TYPO in EMPIRE tech name sometime?
        "HydroPumpStorage":"Hydro_Pump_Storage",
        "Hydrorun-of-the-river":"Hydro_run-of-the-river",
        "Hydroregulated":"Hydro_regulated",
        "Nuclear":"Nuclear",
        "Solar":"Solar",
        "Windoffshoregrounded":"Wind_offshore_grounded",
        "Windoffshorefloating":"Wind_offshore_floating",
        "Windonshore":"Wind_onshore",
        "Waste":"Waste", # is there a better mappinbg for this?
        "Wave":"Wave",
        # "Other" in ENTSO-e data corresponds to CHPs that do not seem to be in EMPIRE 
    }

    techs_ts_mapping = {"Hydrorun-of-the-river": "profile",
                        "Hydroregulated": "level_inflow",
                        "Windonshore": "profile",
                        "Windoffshoregrounded": "profile",
                        "Windoffshorefloating": "profile",
                        "Solar": "profile",
                        }

    # Name or path to the different files:
        # regionmap_file -> grouping of NUTS region into the regions we want to include in our modelling
            # contains the follwing columns ['Country', 'NUTS_level', 'NUTS_name', 'NUTS_code', 'Mapped_Area_Code',
            #      'Empire_zone', 'Industry_Allocation', 'Power_Allocation', 'Coastal',
            #      'LNG_Terminal', 'LNG_Export_Terminal', 'Comment']
        # NUTS_geojson -> geojson file of NUTS regions
            # from https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/territorial-units-statistics
        # EMPIRE_dem_file -> File containing the demand profiles in the different EMPIRE nodes
        # powergrid_file -> Description of power grid between NUTS3 regions from grid_extraction.py

    regionmap_file = "InputOutput/Region_Mapping.csv"
    rest_file = "InputOutput/Rest_Areas.csv"
    NUTS_geojson = "InputOutput/NUTS_RG_01M_2024_4326.geojson"
    powergrid_file = "InputOutput/Transmission_Capacities.csv"
    rest_tm_file = "InputOutput/Transmission_Capacities_external.csv"
    initial_capacity_file_timeserie = f"{EMPIRE_input_folder}/Generator_InitialCapacity.tab"
    initial_capacity_file_value = f"{EMPIRE_input_folder}/Generator_RefInitialCap.tab"
    initial_capacity_storage_power_file = f"{EMPIRE_input_folder}/Storage_InitialPowerCapacity.tab"
    initial_capacity_storage_eneergy_file = f"{EMPIRE_input_folder}/Storage_EnergyInitialCapacity.tab"
    cap_entsoe_25_file = "./ENTSOE/Installed Capacity Per Production Unit_merged.xlsx"
    sets_generator_EMPIRE_file = f"{EMPIRE_input_folder}/Sets_Generator.tab"
    sets_storage_EMPIRE_file = f"{EMPIRE_input_folder}/Sets_Storage.tab"
    empire_powerline_OPEX_fixed_file = f"{EMPIRE_input_folder}/Transmission_TypeFixedOMCost.tab"
    empire_powerline_CAPEX_file = f"{EMPIRE_input_folder}/Transmission_TypeCapitalCost.tab"
    power_co2_price_file = f"{EMPIRE_res_folder}/results_output_EuropeSummary.csv"
    if not recalc_road_distances:
        road_distance_file = "InputOutput/Road_Distances.csv"
    ship_distance_file = "InputOutput/Ship_Distances.csv"
    global_data_file = f"../{case_name}/Default/global_data.yml"

    #emission_price = [150e-3, 70e-3, 290e-3] #k€/tonCO2 for the three strategic periods
    #%% Read the files

    nodes_df = pd.read_csv(regionmap_file, encoding='latin1')
    rest_df= pd.read_csv(rest_file, encoding='utf8')
    gdf = geopandas.read_file(NUTS_geojson)
    gdf = gdf[gdf['LEVL_CODE'] == NUTS_level]
    gdf=gdf[gdf.CNTR_CODE.isin(country_scope)]
    power_grid = pd.read_csv(powergrid_file)
    rest_tm = pd.read_csv(rest_tm_file)
    init_cap_ts = pd.read_csv(initial_capacity_file_timeserie, sep="\t", encoding='latin1')
    init_cap_val = pd.read_csv(initial_capacity_file_value, sep="\t", encoding='latin1')
    init_cap_stor_pow = pd.read_csv(initial_capacity_storage_power_file, sep="\t", encoding='latin1')
    init_cap_stor_en = pd.read_csv(initial_capacity_storage_eneergy_file, sep="\t", encoding='latin1')
    cap_entsoe_25 = pd.read_excel(cap_entsoe_25_file)
    sets_generator_EMPIRE = pd.read_csv(sets_generator_EMPIRE_file, sep="\t", encoding='latin1')
    sets_storage_EMPIRE = pd.read_csv(sets_storage_EMPIRE_file, sep="\t", encoding='latin1')
    empire_powerline_OPEX_fixed = pd.read_csv(empire_powerline_OPEX_fixed_file, sep="\t", encoding='latin1')
    empire_powerline_CAPEX = pd.read_csv(empire_powerline_CAPEX_file, sep="\t", encoding='latin1')
    power_co2_price = pd.read_csv(power_co2_price_file, encoding='latin1')
    if not recalc_road_distances:
        road_distance = pd.read_csv(road_distance_file, encoding='latin1')
    ship_distance = pd.read_csv(ship_distance_file, encoding='latin1')

    #%% Define some parameters from read files

    #EMPIRE techs:
    all_EMPIRE_techs = sets_generator_EMPIRE.Generator.unique().tolist() + sets_storage_EMPIRE.Storage.unique().tolist()
    # areas in our modelling, i.e. NUTS regions and grouping of NUTS regions
    modelled_areas = nodes_df.Mapped_Area_Code.unique()
    modelled_areas = np.setdiff1d(modelled_areas, ["Not Included"])
    rest_areas = rest_df.Name.unique()
    # regions in our modelling with LNG terminal(s)
    areas_with_LNGport = nodes_df[nodes_df.LNG_Terminal==1].Mapped_Area_Code.unique()
    areas_with_LNGport = np.setdiff1d(areas_with_LNGport, ["Not Included"])

    coastal_areas = nodes_df[nodes_df.Coastal==1].Mapped_Area_Code.unique()
    coastal_areas = np.setdiff1d(coastal_areas, ["Not Included"])

    # Coordinates of modelled regions and geometry of all modelled regions
    area_coord = {}
    modelled_geometries = {}
    for area in modelled_areas:
        tmp_df = nodes_df[nodes_df.Mapped_Area_Code == area]
        sub_areas = tmp_df.NUTS_code.tolist()
        # Find area centroid coordinates
        sub_gdf = gdf[gdf.NUTS_ID.isin(sub_areas)]
        combined_area = sub_gdf.geometry.union_all()
        modelled_geometries[area] = combined_area
        area_centroid = combined_area.centroid
        area_coord[area] = {"lat":area_centroid.y,"lon":area_centroid.x}

    # Find neighbouring regions
    # Initialize a set to store unique neighbor pairs
    neighbor_pairs = set()
    # Initialize a dictionary to store the count of neighbors for each region
    neighbor_count = {area: 0 for area in modelled_geometries}

    # Iterate over each area in the dictionary
    for area_name, area_geometry in modelled_geometries.items():
        # Find neighbors by checking for intersection
        for neighbor_name, neighbor_geometry in modelled_geometries.items():
            if area_name != neighbor_name and area_geometry.touches(neighbor_geometry):
                # Create a sorted tuple of the area names to ensure uniqueness
                pair = tuple(sorted((area_name, neighbor_name)))
                if pair not in neighbor_pairs:
                    neighbor_pairs.add(pair)
                    # Increment the neighbor count for both areas
                    neighbor_count[area_name] += 1
                    neighbor_count[neighbor_name] += 1

    unique_neighbor_pairs = list(neighbor_pairs)

    #%% process the initial capacity data
    # Share of technologies in initial capacity in ENTSO-E data
    # process init_cap_distribkey by grouping by production type and location NUTS3
    cap_entsoe_grouped = cap_entsoe_25.groupby(['Production Type', 'Location NUTS 3']).sum().reset_index()
    cap_entsoe_grouped = cap_entsoe_grouped[["Production Type", "Location NUTS 3", "Current Installed Capacity [MW]"]]

    #initialize init_cap_distribkey with the columns ['Production Type', 'Country', 'Share']
    init_cap_distribkey = pd.DataFrame(columns=['Production Type', 'Location NUTS 3', 'Share'])
    for country in country_scope:
        # Filter the grouped data for the current country
        country_data = cap_entsoe_grouped[cap_entsoe_grouped['Location NUTS 3'].str.startswith(country)]
        
        # Calculate the total capacity by production type for the country
        total_capacity = country_data.groupby(by="Production Type").sum()

        #Add column in country data with the total capacity for the corresponding production type
        country_data = country_data.merge(total_capacity, on='Production Type', suffixes=('', ' Total Capacity [MW]'))

        # Divide the apacity in the region by the total capacity in the country for each technology and region
        country_data['Share'] = country_data['Current Installed Capacity [MW]'] / country_data['Current Installed Capacity [MW] Total Capacity [MW]']
        
        # Remove columns that are not needed
        country_data = country_data[['Production Type', 'Location NUTS 3', 'Share']]
        
        # Append to the main DataFrame
        if 'init_cap_distribkey' not in locals():
            init_cap_distribkey = country_data
        else:
            init_cap_distribkey = pd.concat([init_cap_distribkey, country_data], ignore_index=True)

    # Aggregate to the modelled geographical areas
    # Replace the name ofthe nuts3 region by the name of the aggregate region
    init_cap_distribkey = init_cap_distribkey.replace({"Location NUTS 3": {row["NUTS_code"]: row["Mapped_Area_Code"] for idx, row in nodes_df.iterrows()}})
    # Rename the column Location NUTS3 to Mapped_Area_Code
    init_cap_distribkey = init_cap_distribkey.rename(columns={"Location NUTS 3": "Mapped_Area_Code"})
    # Group by Mapped_Area_Code and Production Type and sum the shares
    init_cap_distribkey = init_cap_distribkey.groupby(['Mapped_Area_Code', 'Production Type']).sum().reset_index()
    # Sum values based on production type and the two first letters in Mapped Area Code and check tghat everything is 1
    init_cap_distribkey['Country_Code'] = init_cap_distribkey['Mapped_Area_Code'].str[:2]
    # Check that all sums are 1
    if any(round(x, ndigits=2)!=1.0 for x in init_cap_distribkey.groupby(['Country_Code', 'Production Type']).sum().Share):
        raise ValueError("The sum of shares for each country and production type is not equal to 1.0. Please check the input data.")

    # Denmark is missing onshore wind power, so we add it from the global energy monitor data
    # read global energy monitor data
    glob_wind_track_file="InputOutput/GlobalEnergyMonitor/Global-Wind-Power-Tracker-February-2025.xlsx"
    glob_wind_track = pd.read_excel(glob_wind_track_file, sheet_name="Data")

    # Filter for Denmark and onshore wind
    glob_wind_track_dk = glob_wind_track[(glob_wind_track["Country/Area"] == "Denmark") & (glob_wind_track["Installation Type"] == "Onshore")]

    # Use the mapped area shape files to determine based on the latitude and longitude ofeach wind farm to which area it belongs
    # Create a GeoDataFrame from the wind data
    gdf_wind = geopandas.GeoDataFrame(glob_wind_track_dk, geometry=geopandas.points_from_xy(glob_wind_track_dk["Longitude"], glob_wind_track_dk["Latitude"]), crs="EPSG:4326")
    # Use modelled geometries created earlier to find which area the plants are in
    gdf_wind['Mapped_Area_Code'] = gdf_wind.geometry.apply(lambda x: next((area for area, geom in modelled_geometries.items() if geom.contains(x)), None))
    # Calculate the share of onshore wind in each area
    total_onshore_wind_dk = gdf_wind.groupby('Mapped_Area_Code')['Capacity (MW)'].sum().reset_index()
    # Sum of onshore wind in each mapped area
    total_onshore_wind_dk['Share'] = total_onshore_wind_dk['Capacity (MW)'] / total_onshore_wind_dk['Capacity (MW)'].sum()
    # Add the share of onshore wind in denmark to the init_cap_distribkey 
    for idx, row in total_onshore_wind_dk.iterrows():
        area = row['Mapped_Area_Code']
        share = row['Share']
        # Check if the production type is already in the init_cap_distribkey
        if "Wind Onshore" in init_cap_distribkey[init_cap_distribkey.Mapped_Area_Code == area]["Production Type"].unique():
            # Update the previous share
            init_cap_distribkey.loc[(init_cap_distribkey.Mapped_Area_Code == area) & (init_cap_distribkey["Production Type"] == "Wind Onshore"), 'Share'] = share
        else:
            # Add a new row for the onshore wind share
            new_row = pd.DataFrame({'Mapped_Area_Code': [area], 'Production Type': ["Wind Onshore"], 'Share': [share], 'Country_Code': ["DK"]})
            init_cap_distribkey = pd.concat([init_cap_distribkey, new_row], ignore_index=True)

    # Check that all sums are 1
    if any(round(x, ndigits=2)!=1.0 for x in init_cap_distribkey.groupby(['Country_Code', 'Production Type']).sum().Share):
        raise ValueError("The sum of shares for each country and production type is not equal to 1.0 after adding onshore wind in Denmark. Please check the input data.")

    #%% Get Road distance if recalc_road_distances:
    if recalc_road_distances:
        coord_dict = {area: (area_coord[area]['lat'], area_coord[area]['lon']) for area in modelled_areas}
        road_distance = get_road_distances(google_api_key_path, coord_dict, mode="driving", units="metric")
        matrix = road_distance.pivot(index='from', columns='to', values='distance_m')
        nodes_to_snap = matrix[matrix.isna().all(axis=1)].index.tolist()
        # Manually snapping known problematic regions
        manual_snaps = {
            "DK01": (55.793496,12.262660),
            "NO073": (69.997928,24.948841),
            "SE332": (66.969108,19.834771),
        }
        # check if some of the nodes to snapped are not manually handled and print nodes that must be snapped
        if nodes_to_snap:
            for node in nodes_to_snap:
                if node not in manual_snaps:
                    print(f"Node {node} must be snapped manually, please provide coordinates.")
                else:
                    coord_dict[node] = manual_snaps[node]
            pairs = [(origin, destination) for origin in nodes_to_snap for destination in modelled_areas if origin != destination]
            pairs += [(origin, destination) for origin in modelled_areas for destination in nodes_to_snap if origin != destination]
            # retry to get road distances for the snapped nodes
            road_distance_missing = get_road_distances_by_pairs(google_api_key_path, pairs, coord_dict, mode="driving", units="metric")
            # update the road_distance dataframe with the missing values from road_distance_missing
            # Combine the original and missing distances
            combined_distances = pd.concat([road_distance, road_distance_missing])
            # Drop duplicates, keeping the last occurrence (i.e., from road_distance_missing)
            combined_distances = combined_distances.drop_duplicates(subset=['from', 'to'], keep='last')
        else:
            combined_distances = road_distance
        # Save to file
        combined_distances.to_csv(road_distance_file, index=False)

    #process the ship distances
    # Aggregate the ship distances that are at NUTS3 level to our modelled areas
    # Replace the name ofthe nuts3 region by the name of the aggregate region
    ship_distance = ship_distance.replace({"from NUTS3 name": {row["NUTS_code"]: row["Mapped_Area_Code"] for idx, row in nodes_df.iterrows()}})
    ship_distance = ship_distance.replace({"To NUTS3 name": {row["NUTS_code"]: row["Mapped_Area_Code"] for idx, row in nodes_df.iterrows()}})
    # only keep the columns ['from NUTS3 name', 'To NUTS3 name', 'distance_km']
    ship_distance = ship_distance[['from NUTS3 name', 'To NUTS3 name', 'distance_km']]
    #groupby "from NUTS3 name", "To NUTS3 name" and average the distances if there are several ports in the same region
    ship_distance = ship_distance.groupby(['from NUTS3 name', 'To NUTS3 name']).mean().reset_index()
    # rename the columns to ['from', 'to', 'distance_km']
    ship_distance = ship_distance.rename(columns={'from NUTS3 name': 'from', 'To NUTS3 name': 'to'})

    #%% retrieve power prices and co2 prices from EMPIRE results
    # retrieve the first table from power_co2_price. Find index of the first row of only nan and use it to cut the table
    first_nan_index = power_co2_price[power_co2_price.isnull().all(axis=1)].index[0]
    power_co2_price = power_co2_price.iloc[:first_nan_index]
    startyear=2025
    years = [f"{startyear + i*5}-{startyear + (i+1)*5}" for i in range(n_str_period)]
    scenarios = [f"scenario{i+1}" for i in range(n_scenario)]

    power_co2_price = power_co2_price[power_co2_price['Period'].isin(years) & power_co2_price['Scenario'].isin(scenarios)]
    emission_price = [round(float(x)/1000,ndigits=4) for x in power_co2_price["CO2Price_EuroPerTon"].tolist()] # divide by 1000 to have k€/ton
    print("emission_price:", emission_price)
    power_price = [round(float(x)/1000,ndigits=4) for x in power_co2_price["AvgPowerPrice_Euro"].tolist()] # divide by 1000 to have k€/MWh

    #%% Build output file line by line in list
    # Initialize output case file that will be built line by line
    output=[]
    output.append("Areas:")

    # Add each region and relevant data
    for area in modelled_areas:
        tmp_df = nodes_df[nodes_df.Mapped_Area_Code == area]
        sub_areas = tmp_df.NUTS_code.tolist()
        
        # Read and distribute power and hydrogen demands
        EMPIRE_area = tmp_df.Empire_zone.unique()[0]
        if tmp_df.Empire_zone.unique().size > 1:
            raise ValueError(f"Multiple Empire zones found for area {area}. Please check code/data.")
        #el_dem = [round(float(
        #    sum(dem_EMPIRE.loc[(dem_EMPIRE.Nodes == nodes_df.loc[nodes_df.NUTS_code == ar,"Empire_zone"].iloc[0]) 
        #    & (dem_EMPIRE["Demand Type"] == "Power")
        #    & (dem_EMPIRE["Period"] == i),"Demand [MWh/y]"].iloc[0]
        #    * nodes_df.loc[nodes_df.NUTS_code == ar,"Population_Key"].iloc[0] for ar in sub_areas))
        #    ,ndigits=4) for i in range(1,n_str_period+1)]
        #h2_dem = [round(float(sum(dem_EMPIRE.loc[(dem_EMPIRE.Nodes == nodes_df.loc[nodes_df.NUTS_code == ar,"Empire_zone"].iloc[0])
        #    & (dem_EMPIRE["Demand Type"] == "H2")
        #    & (dem_EMPIRE["Period"] == i),"Demand [MWh/y]"].iloc[0]
        #    * nodes_df.loc[nodes_df.NUTS_code == ar,"Industry_Allocation"].iloc[0] for ar in sub_areas))
        #    ,ndigits=4) for i in range(1,n_str_period+1)]
        # Add area to output
        output.append(f"  {area}:")
        output.append(f"    latitude: {round(area_coord[area]['lat'],ndigits=4)}")
        output.append(f"    longitude: {round(area_coord[area]['lon'],ndigits=4)}")
        output.append( "    type: RefArea")
        output.append( "    techs:")
        output.append(f"      <<: *{default_area[area[:2]]}")
        output.append( "      Electricity_demand:")
        output.append( "        <<: *Electricity_demand")
        output.append(f"        capacity: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"El_demand\",\"capacity\",\"{area}.csv\")")
        output.append( "      Hydrogen_demand:")
        output.append( "        <<: *Hydrogen_demand")
        output.append(f"        capacity: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"H2_demand\",\"capacity\",\"{area}.csv\")")

        # Add technologies with initial capacity
        init_cap_ts_country = init_cap_ts[init_cap_ts.Node == EMPIRE_area]
        init_cap_val_country = init_cap_val[init_cap_val.Node == EMPIRE_area]
        init_cap_stor_pow_country = init_cap_stor_pow[init_cap_stor_pow.Nodes == EMPIRE_area]
        init_cap_stor_en_country = init_cap_stor_en[init_cap_stor_en.Nodes == EMPIRE_area]

        for tech in all_EMPIRE_techs:
            techdata_overwrite = False
            # Adding the inital capacities to each regions
            if tech in init_cap_ts_country.GeneratorTechnology.unique():
                share_in_region = init_cap_distribkey[(init_cap_distribkey.Mapped_Area_Code == area) & (init_cap_distribkey["Production Type"] == empire_to_entsoe_tech_mapping[tech])]
                if not share_in_region.empty:
                    if techdata_overwrite == False:
                        output.append(f"      {empire_to_EMX_tech_mapping[tech]}:")
                        output.append(f"        <<: *{empire_to_EMX_tech_mapping[tech]}")
                    techdata_overwrite = True

                    share = share_in_region.Share.iloc[0]
                    # Get the initial capacity time series for the technology
                    init_cap_ts_tech = (round(init_cap_ts_country[init_cap_ts_country.GeneratorTechnology == tech].generatorInitialCapacity_in_MW*share,ndigits=4)).tolist()
                    # Add technology to output
                    output.append(f"        capacity: {init_cap_ts_tech[:n_str_period]}")
            if tech in init_cap_val_country.GeneratorTechnology.unique():
                share_in_region = init_cap_distribkey[(init_cap_distribkey.Mapped_Area_Code == area) & (init_cap_distribkey["Production Type"] == empire_to_entsoe_tech_mapping[tech])]
                if not share_in_region.empty:
                    if techdata_overwrite == False:
                        output.append(f"      {empire_to_EMX_tech_mapping[tech]}:")
                        output.append(f"        <<: *{empire_to_EMX_tech_mapping[tech]}")
                    techdata_overwrite = True

                    share = share_in_region.Share.iloc[0]
                    # Get the initial capacity time series for the technology
                    init_cap_val_tech = (round(init_cap_val_country[init_cap_val_country.GeneratorTechnology == tech].generatoReferenceInitialCapacity_in_MW*share,ndigits=4)).tolist()[0]
                    # Add technology to output
                    if tech == "Hydroregulated":
                        output.append(f"        discharge_capacity: {init_cap_val_tech}")
                        output.append(f"        level_initial: 0")
                    else:
                        output.append(f"        capacity: {[init_cap_val_tech]*n_str_period}")
            if tech in init_cap_stor_pow_country.StorageTypes.unique():
                share_in_region = init_cap_distribkey[(init_cap_distribkey.Mapped_Area_Code == area) & (init_cap_distribkey["Production Type"] == empire_to_entsoe_tech_mapping[tech])]
                if not share_in_region.empty:
                    if techdata_overwrite == False:
                        output.append(f"      {empire_to_EMX_tech_mapping[tech]}:")
                        output.append(f"        <<: *{empire_to_EMX_tech_mapping[tech]}")
                    techdata_overwrite = True

                    share = share_in_region.Share.iloc[0]
                    # Get the initial capacity time series for the technology
                    init_cap_stor_pow_tech = (round(init_cap_stor_pow_country[init_cap_stor_pow_country.StorageTypes == tech].InitialPowerCapacity*share,ndigits=4)).tolist()
                    init_cap_stor_en_tech = (round(init_cap_stor_en_country[init_cap_stor_en_country.StorageTypes == tech].EnergyInitialCapacity*share,ndigits=4)).tolist()
                    # Add technology to output
                    output.append(f"        level_capacity: {init_cap_stor_en_tech[:n_str_period]}")
                    output.append(f"        discharge_capacity: {init_cap_stor_pow_tech[:n_str_period]}")
                    output.append(f"        level_initial: {init_cap_stor_en_tech[0]*0.5}")
            # Adding the timeseries for the relevant technologies
            if tech in techs_ts_mapping.keys():
                if techdata_overwrite == False:
                    output.append(f"      {empire_to_EMX_tech_mapping[tech]}:")
                    output.append(f"        <<: *{empire_to_EMX_tech_mapping[tech]}")
                techdata_overwrite = True
                # Add technology to output
                output.append(f"        {techs_ts_mapping[tech]}: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"{empire_to_EMX_tech_mapping[tech]}\",\"{techs_ts_mapping[tech]}\",\"{area}.csv\")")
            if (not area in coastal_areas) and (tech in ["Windoffshoregrounded","Windoffshorefloating","Wave"]):
                if techdata_overwrite == False:
                    output.append(f"      {empire_to_EMX_tech_mapping[tech]}:")
                    output.append(f"        <<: *{empire_to_EMX_tech_mapping[tech]}")
                techdata_overwrite = True
                # Resttrict invest_capacity_max_installed and invest_capacity_max_add to 0
                output.append(f"        invest_capacity_max_installed: 0")
                output.append(f"        invest_capacity_max_add: 0")
    for area in rest_areas:
        # Add area to output
        output.append(f"  {area}:")
        output.append(f"    latitude: {rest_df.loc[rest_df.Name==area]['Lat'][0]}")
        output.append(f"    longitude: {rest_df.loc[rest_df.Name==area]['Lon'][0]}")
        output.append( "    type: RefArea")
        output.append( "    techs:")
        output.append(f"      <<: *{default_external}")
        output.append( "      Hydrogen_demand_external:")
        output.append( "        <<: *Hydrogen_demand_external")
        output.append(f"        capacity: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"H2_demand\",\"capacity\",\"Rest.csv\")")
        output.append( "      Electricity_demand_external:")
        output.append( "        <<: *Electricity_demand_external")
        output.append(f"        capacity: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"El_demand\",\"capacity\",\"Rest.csv\")")
        output.append( "      Electricity_source_external:")
        output.append( "        <<: *Electricity_source_external")
        output.append(f"        capacity: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"El_source\",\"capacity\",\"Rest.csv\")")
        output.append(f"        profile: joinpath(@__DIR__,\"{case_name}\",\"Default\",\"Timeseries\",\"El_source\",\"profile\",\"Rest.csv\")")
        output.append(f"        OPEX_variable: {power_price}")

    #%% Process Transmissions    
    # Process Transmissions
    # Apply merging of NUTS areas to transmissions
    NUTS_mapping = {row["NUTS_code"]:row["Mapped_Area_Code"] for idx, row in nodes_df.iterrows()}
    merged_power_grid = power_grid.replace(NUTS_mapping)
    # groupby without changing columns
    merged_power_grid = merged_power_grid.groupby(by=["From_NUTS_ID","To_NUTS_ID","HVDC"], as_index = False).sum()
    # remove rows where From_NUTS_ID == To_NUTS_ID
    merged_power_grid = merged_power_grid[merged_power_grid.From_NUTS_ID != merged_power_grid.To_NUTS_ID]

    merged_rest_tm = rest_tm.replace(NUTS_mapping)
    merged_rest_tm = merged_rest_tm.groupby(by=["From_NUTS_ID","To_NUTS_ID", "HVDC"], as_index = False).sum()
    merged_rest_tm = merged_rest_tm[merged_rest_tm.From_NUTS_ID != merged_rest_tm.To_NUTS_ID]

    # create new column with a sorted tuple from and to to make sure that A->B and B->A are treated the same
    merged_power_grid['pair'] = merged_power_grid.apply(lambda row: tuple(sorted((row['From_NUTS_ID'], row['To_NUTS_ID']))), axis=1)
    #group by the new column and sum the Transmission_Capacity_MVA
    merged_power_grid = merged_power_grid.groupby(by=['pair','HVDC'], as_index = False).sum()

    #remove unnecessary columns
    merged_power_grid = merged_power_grid.drop(columns=['From_NUTS_ID','To_NUTS_ID'])

    # save to csv
    merged_power_grid.to_csv("InputOutput/Merged_Transmission_Capacities.csv")

    #%% parameters for trucks and ships
    # shipping parameters based on paper by Restelli et al 2024 https://doi.org/10.1016/j.ijhydene.2023.10.107#
    cap_ship = 469 #tonH2
    CAPEX_ship = 57.81 #M€
    loss_ship = 0.2/100 # 0.2% per day
    loss_other = 0.01/100 # 0.01% per day, assumption for not having 0 losses
    OPEX_fixed_ship = 1664 #k€/y based on 2 crews of 16 persons at 52000€/y
    C_fuel_ship = 580 #€/ton of fuel
    spec_fuel_cons_ship = 0.1587 #kg/kWh
    P_motor_ship = 3000 #kW
    fuel_volum_density_ship = 990 #kg/m3
    specific_emission_fuel_ship = 11.24 #kgCO2/gallon
    conv_gallon_m3 = 264.2 #gallon/m3 
    # truck parameters based on paper by Restelli et al 2024 https://doi.org/10.1016/j.ijhydene.2023.10.107#
    CAPEX_tractor_unit = 290 #k€
    CAPEX_trailer_LH2 = 1190 #k€
    CAPEX_trailer_H2 = 570 #k€
    cap_trailer_LH2 = 4 #tonH2
    cap_trailer_H2 = 0.5 #tonH2
    OPEX_fixed_truck = 5 * 40 #k€/y based on 5 drivers at 40000€/y driving 45 weeks of 5 days of 8 hours
    C_fuel_truck = 1.8155 #€/liter
    spec_fuel_cons_truck = 35 #liter/100km 
    avg_truck_speed = 60 #km/h
    spec_em_diesel = 10.19 #kgCO2/gallon
    #%% write transmissions
    output.append("")
    output.append("Transmissions:")
    covered_areas = {}
    for ar1 in modelled_areas:
        covered_areas[ar1] = []
        for ar2 in modelled_areas:
            tms_added = []
            if ar2 != ar1:
                if ar2 in np.setdiff1d(list(find_pairs(neighbor_pairs,ar1)),covered_areas[ar1]):
                    covered_areas[ar1].append(ar2)
                    output.append(f"  {ar1}-{ar2}:")
                    output.append(f"    from: {ar1}")
                    output.append(f"    to: {ar2}")
                    output.append( "    modes:")
                    for tm in default_neighboring_tm:
                        distance = float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000) # km
                        if "Road" in tm:
                            t_trip = 2*distance/avg_truck_speed # hours for a round trip
                            Cons_fuel_trip = C_fuel_truck * spec_fuel_cons_truck * 2 * distance / 100 /1000 # k€/trip, 100 is conversion from liter/100km to liter/km
                            Em_trip = (spec_fuel_cons_truck/ 100) * spec_em_diesel * (conv_gallon_m3/1000) * 2 * distance  / 1000 # tonCO2/trip, 100 is conversion from liter/100km to liter/km, 264.2/1000 is conversion from gallon to Liter
                            if tm == "H2_Road":
                                cap_truck = cap_trailer_H2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_H2
                            elif tm == "LH2_Road":
                                cap_truck = cap_trailer_LH2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_LH2
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            #output.append(f"        capacity: {round(cap_truck/t_trip,ndigits=4)}") # cap in tonH2/h
                            #output.append(f"        loss: {round(loss_other*t_trip/2/24,ndigits=5)}")
                            output.append(f"        OPEX_variable: {[round((Cons_fuel_trip+Em_trip*emission_price[i])/cap_truck, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                            output.append(f"        OPEX_fixed: {round(OPEX_fixed_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h)/y
                            output.append(f"        invest_capacity_CAPEX: {round(CAPEX_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€
                        else:
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            output.append(f"        dist: {float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000)}")
                        tms_added.append(tm)
                if ar1 in areas_with_LNGport:
                    if ar2 in np.setdiff1d(areas_with_LNGport,covered_areas[ar1]) and ship_distance[(ship_distance['from'] == ar1) & (ship_distance['to'] == ar2)].empty == False:
                        if ar2 not in covered_areas[ar1]:
                            covered_areas[ar1].append(ar2)
                            output.append(f"  {ar1}-{ar2}:")
                            output.append(f"    from: {ar1}")
                            output.append(f"    to: {ar2}")
                            output.append( "    modes:")
                        for tm in default_coastal_tm:
                            distance = float(ship_distance[(ship_distance['from'] == ar1) & (ship_distance['to'] == ar2)]['distance_km'].iloc[0])
                            t_trip = 2*distance/ship_speed # hours for a round trip
                            t_prod_to_store = t_trip + t_load_unload + t_safety_margin
                            # base numbers from paper by Restelli et al 2024 https://doi.org/10.1016/j.ijhydene.2023.10.107#
                            Cons_fuel = spec_fuel_cons_ship*P_motor_ship*t_trip/1000 # ton of fuel per trip, 1000 is conversion from kg to ton
                            OPEX_fuel_trip = C_fuel_ship*Cons_fuel/1000 #k€ per trip, 1000 is conversion from € to k€
                            trip_emission = Cons_fuel*specific_emission_fuel_ship*conv_gallon_m3/fuel_volum_density_ship #tonCo2 per trip
                            OPEX_emission_trip = [trip_emission*emission_price[i] for i in range(n_str_period)] #k€/tonCO2
                            # cost associated with emissions from transport ignored at the moment
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            #output.append(f"        capacity: {round(cap_ship/t_prod_to_store, ndigits=4)}") # cap in tonH2/h
                            output.append(f"        loss: {round(loss_ship*t_trip/2/24, ndigits=5)}")
                            output.append(f"        OPEX_variable: {[round((OPEX_fuel_trip+OPEX_emission_trip[i])/cap_ship, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                            output.append(f"        OPEX_fixed: {round(OPEX_fixed_ship/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h)/y
                            output.append(f"        invest_capacity_CAPEX: {round(CAPEX_ship*1000/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€
                            tms_added.append(tm)
                if any((ar1, ar2) == pair for pair in merged_power_grid.pair):# or (ar2,ar1) in merged_power_grid.pair:
                    #if (ar1,ar2) in merged_power_grid.pair:
                    cap_overhead = merged_power_grid.loc[(merged_power_grid.pair == (ar1,ar2)) & (merged_power_grid.HVDC == 0), 'Transmission_Capacity_MVA'].sum()
                    cap_hvdc = merged_power_grid.loc[(merged_power_grid.pair == (ar1,ar2)) & (merged_power_grid.HVDC == 1), 'Transmission_Capacity_MVA'].sum()
                    #if (ar2,ar1) in merged_power_grid.index:
                    #    cap = merged_power_grid.loc[ar2,ar1].iloc[0]
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    if cap_hvdc != 0:
                        output.append(f"      HVDC:")
                        output.append( "        <<: *default_HVDC")
                        output.append(f"        capacity: {cap_hvdc}")
                        tmp_capex = [float(empire_powerline_CAPEX[(empire_powerline_CAPEX.Type == "HVDC_Cable") & (empire_powerline_CAPEX.Period == i)].TypeCapitalCost_in_euro_per_MWkm.sum())/1000 for i in range(1,n_str_period+1)] #divide by thousand for kEUR
                        tmp_opex = [float(empire_powerline_OPEX_fixed[(empire_powerline_OPEX_fixed.Type == "HVDC_Cable") & (empire_powerline_OPEX_fixed.Period == i)].TypeFixedOMCost_in_euro_per_MW_per_km.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                        output.append(f"        invest_capacity_CAPEX: {[round(x,ndigits=4) for x in tmp_capex]}")
                        output.append(f"        OPEX_fixed: {[round(x,ndigits=4) for x in tmp_opex]}")
                        #output.append(f"        invest_capacity_initial: {cap_hvdc}")
                        tms_added.append("HVDC")
                    if cap_overhead != 0:
                        output.append( "      Powerline:")
                        output.append( "        <<: *default_Powerline")
                        output.append(f"        capacity: {cap_overhead}")
                        tmp_capex = [float(empire_powerline_CAPEX[(empire_powerline_CAPEX.Type == "HVAC_OverheadLine") & (empire_powerline_CAPEX.Period == i)].TypeCapitalCost_in_euro_per_MWkm.sum())/1000 for i in range(1,n_str_period+1)] #divide by thousand for kEUR
                        tmp_opex = [float(empire_powerline_OPEX_fixed[(empire_powerline_OPEX_fixed.Type == "HVAC_OverheadLine") & (empire_powerline_OPEX_fixed.Period == i)].TypeFixedOMCost_in_euro_per_MW_per_km.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                        output.append(f"        invest_capacity_CAPEX: {[round(x,ndigits=4) for x in tmp_capex]}")
                        output.append(f"        OPEX_fixed: {[round(x,ndigits=4) for x in tmp_opex]}")
                        #output.append(f"        invest_capacity_initial: {cap_overhead}")
                    tms_added.append("Powerline")
                if (ar1=="DK01" and ar2=="SE22+") or (ar1=="SE22+" and ar2=="DK01"):
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    for tm in default_neighboring_tm:
                        distance = float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000) # km
                        if "Road" in tm:
                            t_trip = 2*distance/avg_truck_speed # hours for a round trip
                            Cons_fuel_trip = C_fuel_truck * spec_fuel_cons_truck * 2 * distance / 100 /1000 # k€/trip, 100 is conversion from liter/100km to liter/km
                            Em_trip = (spec_fuel_cons_truck/ 100) * spec_em_diesel * (conv_gallon_m3/1000) * 2 * distance  / 1000 # tonCO2/trip, 100 is conversion from liter/100km to liter/km, 264.2/1000 is conversion from gallon to Liter
                            if tm == "H2_Road":
                                cap_truck = cap_trailer_H2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_H2
                            elif tm == "LH2_Road":
                                cap_truck = cap_trailer_LH2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_LH2
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            #output.append(f"        capacity: {round(cap_truck/t_trip,ndigits=4)}") # cap in tonH2/h
                            #output.append(f"        loss: {round(loss_other*t_trip/2/24,ndigits=5)}")
                            output.append(f"        OPEX_variable: {[round((Cons_fuel_trip+Em_trip*emission_price[i])/cap_truck, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                            output.append(f"        OPEX_fixed: {round(OPEX_fixed_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h)/y
                            output.append(f"        invest_capacity_CAPEX: {round(CAPEX_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€
                        else:
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            output.append(f"        dist: {float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000)}")
                        tms_added.append(tm)
                if (ar1=="DK02" and ar2=="DK03") or (ar1=="DK03" and ar2=="DK02"):
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    for tm in default_neighboring_tm:
                        distance = float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000) # km
                        if "Road" in tm:
                            t_trip = 2*distance/avg_truck_speed # hours for a round trip
                            Cons_fuel_trip = C_fuel_truck * spec_fuel_cons_truck * 2 * distance / 100 /1000 # k€/trip, 100 is conversion from liter/100km to liter/km
                            Em_trip = (spec_fuel_cons_truck/ 100) * spec_em_diesel * (conv_gallon_m3/1000) * 2 * distance  / 1000 # tonCO2/trip, 100 is conversion from liter/100km to liter/km, 264.2/1000 is conversion from gallon to Liter
                            if tm == "H2_Road":
                                cap_truck = cap_trailer_H2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_H2
                            elif tm == "LH2_Road":
                                cap_truck = cap_trailer_LH2
                                CAPEX_truck = CAPEX_tractor_unit + CAPEX_trailer_LH2
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            #output.append(f"        capacity: {round(cap_truck/t_trip,ndigits=4)}") # cap in tonH2/h
                            #output.append(f"        loss: {round(loss_other*t_trip/2/24,ndigits=5)}")
                            output.append(f"        OPEX_variable: {[round((Cons_fuel_trip+Em_trip*emission_price[i])/cap_truck, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                            output.append(f"        OPEX_fixed: {round(OPEX_fixed_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h)/y
                            output.append(f"        invest_capacity_CAPEX: {round(CAPEX_truck/(cap_truck/t_trip), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€
                        else:
                            output.append(f"      {tm}:")
                            output.append(f"        <<: *default_{tm}")
                            output.append(f"        dist: {float(road_distance[(road_distance['from'] == ar1) & (road_distance['to'] == ar2)]['distance_m'].iloc[0]/1000)}")
                        tms_added.append(tm)
                if (("Powerline" in tms_added or "HVDC" in tms_added) or (any((ar2, ar1) == pair for pair in merged_power_grid.pair) and merged_power_grid.loc[merged_power_grid.pair == (ar2,ar1)].Transmission_Capacity_MVA.sum() != 0)) and "H2_Pipeline" not in tms_added:
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    output.append(f"      H2_Pipeline:")
                    output.append(f"        <<: *default_H2_Pipeline")
                    output.append(f"        capacity: 0") #haversine distance will be used automatically
                    tms_added.append("H2_Pipeline")
        
    for ar1 in modelled_areas:
        covered_areas[ar1] = []
        for ar2 in rest_areas:
            tms_added = []
            if ar1 in areas_with_LNGport:
                if ar2 in np.setdiff1d(np.concatenate((areas_with_LNGport,rest_areas)),covered_areas[ar1]) and ship_distance[(ship_distance['from'] == ar1) & (ship_distance['to'] == ar2)].empty == False:
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    for tm in default_coastal_tm:
                        distance = float(ship_distance[(ship_distance['from'] == ar1) & (ship_distance['to'] == ar2)]['distance_km'].iloc[0])
                        t_trip = 2*distance/ship_speed # hours for a round trip
                        t_prod_to_store = t_trip + t_load_unload + t_safety_margin
                        # base numbers from paper by Restelli et al 2024 https://doi.org/10.1016/j.ijhydene.2023.10.107#
                        Cons_fuel = spec_fuel_cons_ship*P_motor_ship*t_trip/1000 # ton of fuel per trip, 1000 is conversion from kg to ton
                        OPEX_fuel_trip = C_fuel_ship*Cons_fuel/1000 #k€ per trip, 1000 is conversion from € to k€
                        trip_emission = Cons_fuel*specific_emission_fuel_ship*conv_gallon_m3/fuel_volum_density_ship #tonCo2 per trip
                        OPEX_emission_trip = [trip_emission*emission_price[i] for i in range(n_str_period)] #k€/tonCO2
                        # cost associated with emissions from transport ignored at the moment
                        output.append(f"      {tm}:")
                        output.append(f"        <<: *default_{tm}")
                        #output.append(f"        capacity: {round(cap_ship/t_prod_to_store, ndigits=4)}") # cap in tonH2/h
                        output.append(f"        loss: {round(loss_ship*t_trip/2/24, ndigits=5)}")
                        output.append(f"        OPEX_variable: {[round((OPEX_fuel_trip+OPEX_emission_trip[i])/cap_ship, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                        output.append(f"        OPEX_fixed: {round(OPEX_fixed_ship/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h)/y
                        output.append(f"        invest_capacity_CAPEX: {round(CAPEX_ship*1000/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€
                        tms_added.append(tm)
            if any((ar1, ar2) == (row.From_NUTS_ID, row.To_NUTS_ID) for idx,row in merged_rest_tm.iterrows()) or any((ar2, ar1) == (row.From_NUTS_ID, row.To_NUTS_ID) for idx,row in merged_rest_tm.iterrows()):
                if any((ar1, ar2) == (row.From_NUTS_ID, row.To_NUTS_ID) for idx,row in merged_rest_tm.iterrows()):
                    cap_hvdc = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar1) & (merged_rest_tm.To_NUTS_ID == ar2) & (merged_rest_tm.HVDC == 1), 'Transmission_Capacity_MVA'].sum()
                    cap_overhead = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar1) & (merged_rest_tm.To_NUTS_ID == ar2) & (merged_rest_tm.HVDC == 0), 'Transmission_Capacity_MVA'].sum()
                    dist_hvdc = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar1) & (merged_rest_tm.To_NUTS_ID == ar2) & (merged_rest_tm.HVDC == 1), 'distance'].mean()
                    dist_overhead = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar1) & (merged_rest_tm.To_NUTS_ID == ar2) & (merged_rest_tm.HVDC == 0), 'distance'].mean()
                elif any((ar2, ar1) == (row.From_NUTS_ID, row.To_NUTS_ID) for idx,row in merged_rest_tm.iterrows()):
                    cap_hvdc = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar2) & (merged_rest_tm.To_NUTS_ID == ar1) & (merged_rest_tm.HVDC == 1), 'Transmission_Capacity_MVA'].sum()
                    cap_overhead = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar2) & (merged_rest_tm.To_NUTS_ID == ar1) & (merged_rest_tm.HVDC == 0), 'Transmission_Capacity_MVA'].sum()
                    dist_hvdc = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar2) & (merged_rest_tm.To_NUTS_ID == ar1) & (merged_rest_tm.HVDC == 1), 'distance'].mean()
                    dist_overhead = merged_rest_tm.loc[(merged_rest_tm.From_NUTS_ID == ar2) & (merged_rest_tm.To_NUTS_ID == ar1) & (merged_rest_tm.HVDC == 0), 'distance'].mean()
                if ar2 not in covered_areas[ar1]:
                    covered_areas[ar1].append(ar2)
                    output.append(f"  {ar1}-{ar2}:")
                    output.append(f"    from: {ar1}")
                    output.append(f"    to: {ar2}")
                    output.append( "    modes:")
                if cap_hvdc != 0:
                    output.append(f"      HVDC:")
                    output.append( "        <<: *default_HVDC")
                    output.append(f"        capacity: {cap_hvdc}")
                    tmp_capex = [float(empire_powerline_CAPEX[(empire_powerline_CAPEX.Type == "HVDC_Cable") & (empire_powerline_CAPEX.Period == i)].TypeCapitalCost_in_euro_per_MWkm.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                    tmp_opex = [float(empire_powerline_OPEX_fixed[(empire_powerline_OPEX_fixed.Type == "HVDC_Cable") & (empire_powerline_OPEX_fixed.Period == i)].TypeFixedOMCost_in_euro_per_MW_per_km.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                    output.append(f"        invest_capacity_CAPEX: {[round(x,ndigits=4) for x in tmp_capex]}")
                    output.append(f"        OPEX_fixed: {[round(x,ndigits=4) for x in tmp_opex]}")
                    output.append(f"        dist: {round(dist_hvdc, ndigits=4)}")
                    #output.append(f"        invest_capacity_initial: {cap_hvdc}")
                    tms_added.append("HVDC")
                if cap_overhead != 0:
                    output.append(f"      Powerline:")
                    output.append( "        <<: *default_Powerline")
                    output.append(f"        capacity: {cap_overhead}")
                    tmp_capex = [float(empire_powerline_CAPEX[(empire_powerline_CAPEX.Type == "HVAC_OverheadLine") & (empire_powerline_CAPEX.Period == i)].TypeCapitalCost_in_euro_per_MWkm.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                    tmp_opex = [float(empire_powerline_OPEX_fixed[(empire_powerline_OPEX_fixed.Type == "HVAC_OverheadLine") & (empire_powerline_OPEX_fixed.Period == i)].TypeFixedOMCost_in_euro_per_MW_per_km.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                    output.append(f"        invest_capacity_CAPEX: {[round(x,ndigits=4) for x in tmp_capex]}")
                    output.append(f"        OPEX_fixed: {[round(x,ndigits=4) for x in tmp_opex]}")
                    output.append(f"        dist: {round(dist_overhead, ndigits=4)}")
                    #output.append(f"        invest_capacity_initial: {cap_overhead}")
                    tms_added.append("Powerline")
            elif ar1 == "NO0A2":
                if ar2 not in covered_areas[ar1]:
                    covered_areas[ar1].append(ar2)
                    output.append(f"  {ar1}-{ar2}:")
                    output.append(f"    from: {ar1}")
                    output.append(f"    to: {ar2}")
                    output.append( "    modes:")
                output.append( "      Powerline:")
                output.append( "        <<: *default_Powerline")
                output.append(f"        capacity: 0")
                tmp_capex = [float(empire_powerline_CAPEX[(empire_powerline_CAPEX.Type == "HVDC_Cable") & (empire_powerline_CAPEX.Period == i)].TypeCapitalCost_in_euro_per_MWkm.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                tmp_opex = [float(empire_powerline_OPEX_fixed[(empire_powerline_OPEX_fixed.Type == "HVDC_Cable") & (empire_powerline_OPEX_fixed.Period == i)].TypeFixedOMCost_in_euro_per_MW_per_km.sum())/1000 for i in range(1,n_str_period+1)]#divide by thousand for kEUR
                output.append(f"        invest_capacity_CAPEX: {[round(x,ndigits=4) for x in tmp_capex]}")
                output.append(f"        OPEX_fixed: {[round(x,ndigits=4) for x in tmp_opex]}")
                tms_added.append("Powerline")
            if ("Powerline" in tms_added or "HVDC" in tms_added) and "H2_Pipeline" not in tms_added:
                lat1 = area_coord[ar1]['lat']
                lon1 = area_coord[ar1]['lon']
                tmp = rest_df.loc[rest_df.Name==ar2]
                #for each row in tmp calculate the distance from ar1 using haversine then take the average and use that as distance
                i=0
                total_dist=0
                for index, row in tmp.iterrows():
                    hversine = haversine(lon1, lat1, row['Lon'], row['Lat'])
                    total_dist += hversine
                    i+=1
                dist= round(total_dist/i,ndigits=4)
                output.append(f"      H2_Pipeline:")
                output.append(f"        <<: *default_H2_Pipeline")
                output.append(f"        capacity: 0")
                output.append(f"        dist: {dist}")

    # shipping hydrogen from rest to study area
    for ar1 in rest_areas:
        covered_areas[ar1] = []
        for ar2 in modelled_areas:
            if ar2 in areas_with_LNGport:
                if ar2 in np.setdiff1d(np.concatenate((areas_with_LNGport,rest_areas)),covered_areas[ar1]) and ship_distance[(ship_distance['from'] == ar2) & (ship_distance['to'] == ar1)].empty == False:
                    if ar2 not in covered_areas[ar1]:
                        covered_areas[ar1].append(ar2)
                        output.append(f"  {ar1}-{ar2}:")
                        output.append(f"    from: {ar1}")
                        output.append(f"    to: {ar2}")
                        output.append( "    modes:")
                    for tm in default_coastal_tm:
                        distance = float(ship_distance[(ship_distance['from'] == ar1) & (ship_distance['to'] == ar2)]['distance_km'].iloc[0])
                        t_trip = 2*distance/ship_speed # hours for a round trip
                        t_prod_to_store = t_trip + t_load_unload + t_safety_margin
                        # base numbers from paper by Restelli et al 2024 https://doi.org/10.1016/j.ijhydene.2023.10.107#
                        Cons_fuel = spec_fuel_cons_ship*P_motor_ship*t_trip/1000 # ton of fuel per trip, 1000 is conversion from kg to ton
                        OPEX_fuel_trip = C_fuel_ship*Cons_fuel/1000 #k€ per trip, 1000 is conversion from € to k€
                        trip_emission = Cons_fuel*specific_emission_fuel_ship*conv_gallon_m3/fuel_volum_density_ship #tonCo2 per trip
                        OPEX_emission_trip = [trip_emission*emission_price[i] for i in range(n_str_period)] #k€/tonCO2
                        # cost associated with emissions from transport ignored at the moment
                        output.append(f"      {tm}:")
                        output.append(f"        <<: *default_{tm}")
                        #output.append(f"        capacity: {round(cap_ship/t_prod_to_store, ndigits=4)}") # cap in tonH2/h
                        output.append(f"        loss: {round(loss_ship*t_trip/2/24, ndigits=5)}")
                        output.append(f"        OPEX_variable: {[round((OPEX_fuel_trip+OPEX_emission_trip[i])/cap_ship, ndigits=4) for i in range(n_str_period)]}") #k€/tonH2
                        output.append(f"        OPEX_fixed: {round(OPEX_fixed_ship/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h)/y
                        output.append(f"        invest_capacity_CAPEX: {round(CAPEX_ship*1000/(cap_ship/t_prod_to_store), ndigits=4)}") #k€/(tonH2/h), 1000 is conversion from M€ to k€

    #%% Print the output line by line to yaml file
    write_to_yaml(output, "EMX_input_files/case.yml")
if __name__ == "__main__":
    main()