import sys
import shutil
from pathlib import Path
import spinedb_api as api
from collections import defaultdict
from sqlalchemy.exc import DBAPIError
import os
import yaml
import csv
from dateutil.parser import parse


def get_timeseries(file_name, settings, nodes, timestamp_col = 0):
    timeseries_folder = settings["Timeseries_folder"]
    file_path = os.path.join(timeseries_folder, file_name)
    all_timeseries_data = dict()
    nodes_with_keys = [settings["Node_key"][node] for node in nodes if node in settings["Node_key"].keys()]
    for node_key in nodes_with_keys:
        country_col = None
        if os.path.isfile(file_path):
            with open(file_path, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                headers = next(reader)
                for i, header in enumerate(headers):
                    if header == node_key:
                        country_col = i
                        break
                if country_col is None:
                    print(f"Country {node_key} not found in timeseries file {file_name}.")
                    continue
                else:
                    timeseries_data = [float(row[country_col]) for row in reader if str(parse(row[timestamp_col]).year) == str(settings["Timeseries_year"])]
        else:
            print(f"Timeseries file {file_name} not found in {timeseries_folder}. Please check the settings.")
            sys.exit(1)

        if len(timeseries_data) > 8783:
            pass
        elif len(timeseries_data) == 8760:
            #repeat 28.2 to get to 8784 hours
            #This is quite clumsy
            leap_day = timeseries_data[((31+28)*24):((31+28+1)*24)]
            timeseries_data[((31+28)*24):((31+28)*24)] = leap_day
        else:
            sys.exit(f"Timeseries file {file_name} does not have 8760 or 8784 hours. Please check the file.")
        all_timeseries_data[node_key] = timeseries_data
    return all_timeseries_data

def write_timeseries(file, timeseries_data):
    with open(file, 'w', encoding='utf-16 LE') as output_file:
        for i, value in enumerate(timeseries_data):
            output_file.write(f'{value}\n')

def get_weighted_timeseries(file_name, settings, capacity_for_nodes, nodes, timestamp_col = 0):
    all_timeseries = get_timeseries(file_name, settings, nodes, timestamp_col)
    if not all_timeseries:
        return []
    weighted_timeseries = [0]*len(next(iter(all_timeseries.values())))
    keys = settings["Node_key"]
    for country in capacity_for_nodes.keys():
        if country not in all_timeseries.keys():
            if keys[country] not in all_timeseries.keys():
                sys.exit(f"Country {country} not found in timeseries file {file_name}. Please check the settings and timeseries files."
                      f"If the problem cannot be resolved, set the RESCapacityFactorProfiles to False in the settings.")
    total_capacity = sum(capacity_for_nodes.values())
    if total_capacity > 0:
        for node, capacity in capacity_for_nodes.items():
            node_weight = capacity/total_capacity
            weighted_timeseries = [sum(x) for x in zip(weighted_timeseries, [val * node_weight for val in all_timeseries[keys[node]]])]
    return weighted_timeseries

def get_RES_order(file, settings):
    RES_mapping = settings["RES"]
    RES_order = dict()
    with open(file, 'r', encoding='utf-16 LE') as inp_file:
        lines = inp_file.readlines()
    for i, line in enumerate(lines):
        for RES_key, RES_list in RES_mapping.items():
            if RES_key in line and "NameRES" in lines[i-1]:
                RES_order[RES_key] = lines[i-1].strip()[-5:-1]
    return RES_order
    
def write_fom_share(file, output_sum, output_FOM_sum , param_name):
    if output_sum == 0:
        FOM_share = 0
    else:
        FOM_share = output_FOM_sum/output_sum * 100 # in %
    write_param(file, f'{param_name}', FOM_share, next_line = True)

def sum_params(param, year, output_sum):

    value_map = api.from_database(param["value"], param["type"])
    if isinstance(value_map, api.Map):
        for i, val in enumerate(value_map.indexes):
            #This is done as the period names are sometimes ints and floats for the same dataset.
            #They can also be strings on other datasets.
            try: 
                comp_val = float(val)
            except ValueError:
                comp_val = val
            try:
                year_val = float(year)
            except ValueError:
                year_val = year
            if comp_val == year_val:
                output_sum += float(value_map.values[i])
                break
    else: #float
        output_sum += value_map
    return output_sum

def sum_storage(elec_params, storage_params, storage_mapping, nodes, year):
    elec_output_sum = 0
    stor_output_sum = 0
    for storage_list in storage_mapping:
        for param in elec_params:
            if param["entity_byname"][0] not in nodes:
                continue
            if param["entity_byname"][1] not in storage_list:
                continue
            elec_output_sum = sum_params(param, year, elec_output_sum)
        for param in storage_params:
            if param["entity_byname"][0] not in nodes:
                continue
            if param["entity_byname"][1] not in storage_list:
                continue
            stor_output_sum = sum_params(param, year, stor_output_sum)
    return elec_output_sum, stor_output_sum


def replace_line(file, output_line, line_to_replace):

    # Read and replace
    with open(file, 'r', encoding='utf-16 LE') as inp_file:
        lines = inp_file.readlines()

    lines[line_to_replace] = output_line  # Replace the specific line

    # Write back to the file
    with open(file, 'w', encoding='utf-16 LE') as oup_file:
        oup_file.writelines(lines)

def write_param(file, param_name, param_value, next_line = False):
    try:
        param_value = str(round(float(param_value),4))
    except ValueError:
        param_value = param_value

    with open(file, 'r', encoding='utf-16 LE') as output_file:
        lines = output_file.readlines()
    found = False
    for i, line in enumerate(lines):
        if param_name in line:
            output_line = f'{param_value}'
            found = True
            if next_line:
                lines[i+1] = f'{output_line}\n'
                with open(file, "w", encoding='utf-16 LE') as output_file:
                    output_file.writelines(lines)
            else:
                lines[i] = f'{output_line}\n'
                with open(file, "w", encoding='utf-16 LE') as output_file:
                    output_file.writelines(lines)
            break
        if 'xxx' in line:
            if next_line:
                lines[i] = f'{param_name}\n'
                lines[i+1] = f'{param_value}\n'
            else:
                lines[i] = f'{param_name} = {param_value}\n'
            with open(file, "w", encoding='utf-16 LE') as output_file:
                    output_file.writelines(lines)
            found = True
            break
    if not found:
        with open(file, "a", encoding='utf-16 LE') as output_file:
            if next_line:
                output_file.write(f'{param_name}\n')
                output_file.write(f'{param_value}\n')
            else:
                output_file.write(f'{param_name} = {param_value}\n')

### The purose of this function is to get the weights for the "condensing power plants"
### In EnergyPlan this is a single technology, but in Empire it can be several technologies and plants
### The weights are based on the expected annual production of each technology
### This is problematic in two ways: 
### 1. The plants are used in the order of least costs
### 2. If investment decisions are the mix does not necessarily reflect the actual mix

def get_PP_weights(empire_db, nodes, year, settings, weight_type = 'production'):
    with api.DatabaseMapping(empire_db) as source_db:

        Condensing_PP_mapping = settings["Condensing_PP"]
        if weight_type == 'capacity':
            params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
        elif weight_type == 'production':
            params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genExpectedAnnualProduction_GWh')
        PP_weights = dict()

        for PP_type, PP_list in Condensing_PP_mapping.items():
            output_sum = 0
            for param in params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                if param["entity_byname"][1] not in PP_list:
                    continue
                output_sum = sum_params(param, year, output_sum)
                PP_weights[param["entity_byname"][1]] = output_sum
        sum_all = sum(PP_weights.values())
        for key in PP_weights.keys():
            if sum_all > 0:
                PP_weights[key] = PP_weights[key]/sum_all
            else:
                PP_weights[key] = 0
    return PP_weights

def add_from_empire_db(file, empire_db, country_year, settings, PP_weights_capacity, PP_weights_production):
    
    nodes = settings["Country_nodes"][country_year[0]] if country_year[0] in settings["Country_nodes"].keys() else [country_year[0]]
    year = country_year[1]

    with api.DatabaseMapping(empire_db) as source_db:
        # Electricity demand
        # Should the transport demand be included?
        if settings["Demand"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Node', parameter_definition_name='ElectricAnnualDemand')
            output_sum = 0
            for param in params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                output_sum = sum_params(param, year, output_sum)
            write_param(file, f'Input_el_demand_Twh=', output_sum/1000, next_line = True)
        if settings["DemandProfile"]:
            #write demand timeseries 
            file_name = f'{country_year[0]}_ElectricLoad_{country_year[1]}.txt'
            all_demand = get_timeseries("electricload.csv", settings, nodes, timestamp_col= -4)
            if all_demand:
                demand_timeseries = [sum(x) for x in zip(*all_demand.values())]
                write_timeseries(file_name, demand_timeseries)
                write_param(file, f'Filnavn_elbehov=', file_name, next_line = True)

        if settings["IndustrialDemand"]:
            #Industry demand   #Natural gas and hydrogen include also transport demand
            type_demand_mapping = {
                "CoalDemand": "input_fuel_CSHP[1]=",
                "OilDemand": "input_fuel_CSHP[2]=",
                "BiomassDemand": "input_fuel_CSHP[4]=",
                "NaturalGasDemand": "input_fuel_CSHP[3]=",
                "HydrogenDemand": "input_fuel_CSHP[5]="
            }
            for demand, output_name in type_demand_mapping.items():
                params = source_db.find_parameter_values(entity_class_name='Node', parameter_definition_name= demand)
                output_sum = 0
                for param in params:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    output_sum = sum_params(param, year, output_sum)
                write_param(file, output_name, output_sum/1000, next_line = True)
        
        ##production
        #CAPEX
        if settings["CAPEX"]:
            RES_capacity_mapping = settings["RES"]
            params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='CapitalCosts')
            wind_output_sum = 0
            solar_output_sum = 0
            wind_offshore_output_sum = 0
            hydro_ror_output_sum = 0
            nuclear_output_sum = 0
            hydro_output_sum = 0
            geothermal_output_sum = 0
            PP_CAPEXs = dict()

            for param in params_from_db:
                if param["entity_byname"][0] in RES_capacity_mapping["Wind"]:
                    wind_output_sum = sum_params(param, year, wind_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Photo Voltaic"]:
                    solar_output_sum = sum_params(param, year, solar_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Offshore Wind"]:
                    wind_offshore_output_sum = sum_params(param, year, wind_offshore_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["River Hydro"]:
                    hydro_ror_output_sum = sum_params(param, year, hydro_ror_output_sum)
                if param["entity_byname"][0] in settings["Nuclear"]:
                    nuclear_output_sum = sum_params(param, year, nuclear_output_sum)
                if param["entity_byname"][0] in settings["Hydro_prod"]:
                    hydro_output_sum = sum_params(param, year, hydro_output_sum)
                if param["entity_byname"][0] in settings["Geothermal"]:
                    geothermal_output_sum = sum_params(param, year, geothermal_output_sum)
                if param["entity_byname"][0] in PP_weights_capacity.keys():
                    condensing_CAPEX_output_sum = sum_params(param, year, 0)
                    PP_CAPEXs[param["entity_byname"][0]] = condensing_CAPEX_output_sum * PP_weights_capacity[param["entity_byname"][0]]
            
            write_param(file, f'input_Inv_Wind=', wind_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_PV=', solar_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_WindOffshore=', wind_offshore_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_RiverOffHydro=', hydro_ror_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_Nuclear=', nuclear_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_HydroPower=', hydro_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_GeoPower=', geothermal_output_sum/1000, next_line = True)

            condensing_CAPEX = sum(PP_CAPEXs.values())
            write_param(file, f'input_Inv_PP=', condensing_CAPEX/1000, next_line = True)

        #FOM %/of CAPEX
        if settings["FOM"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='FixedOMCosts')
            wind_FOM_output_sum = 0
            solar_FOM_output_sum = 0
            wind_FOM_offshore_output_sum = 0
            hydro_FOM_ror_output_sum = 0
            nuclear_FOM_output_sum = 0
            hydro_FOM_output_sum = 0
            geothermal_FOM_output_sum = 0
            PP_FOMs = dict()
        
            for param in params_from_db:
                if param["entity_byname"][0] in RES_capacity_mapping["Wind"]:
                    wind_FOM_output_sum = sum_params(param, year, wind_FOM_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Photo Voltaic"]:
                    solar_FOM_output_sum = sum_params(param, year, solar_FOM_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Offshore Wind"]:
                    wind_FOM_offshore_output_sum = sum_params(param, year, wind_FOM_offshore_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["River Hydro"]:
                    hydro_FOM_ror_output_sum = sum_params(param, year, hydro_FOM_ror_output_sum)
                if param["entity_byname"][0] in settings["Nuclear"]:
                    nuclear_FOM_output_sum = sum_params(param, year, nuclear_FOM_output_sum)
                if param["entity_byname"][0] in settings["Hydro_prod"]:
                    hydro_FOM_output_sum = sum_params(param, year, hydro_FOM_output_sum)
                if param["entity_byname"][0] in settings["Geothermal"]:
                    geothermal_FOM_output_sum = sum_params(param, year, geothermal_FOM_output_sum)
                if param["entity_byname"][0] in PP_weights_capacity.keys():
                    condensing_FOM_output_sum = sum_params(param, year, 0)
                    PP_FOMs[param["entity_byname"][0]] = condensing_FOM_output_sum * PP_weights_capacity[param["entity_byname"][0]]

            write_fom_share(file, wind_output_sum, wind_FOM_output_sum, 'input_FOM_Wind=')
            write_fom_share(file, solar_output_sum, solar_FOM_output_sum, 'input_FOM_PV=')
            write_fom_share(file, wind_offshore_output_sum, wind_FOM_offshore_output_sum, 'input_FOM_WindOffshore=')
            write_fom_share(file, hydro_ror_output_sum, hydro_FOM_ror_output_sum, 'input_FOM_RiverOffHydro=')
            write_fom_share(file, nuclear_output_sum, nuclear_FOM_output_sum, 'input_FOM_Nuclear=')
            write_fom_share(file, hydro_output_sum, hydro_FOM_output_sum, 'input_FOM_HydroPower=')
            write_fom_share(file, geothermal_output_sum, geothermal_FOM_output_sum, 'input_FOM_GeoPower=')

            condensing_FOM = sum(PP_FOMs.values())
            write_fom_share(file, condensing_CAPEX, condensing_FOM, 'input_FOM_PP=')

        #VOM 
        if settings["VOM"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='VariableOMCosts')
            hydro_VOM_output_sum = 0
            geothermal_VOM_output_sum = 0
            PP_VOMs = dict()
        
            for param in params_from_db:
                if param["entity_byname"][0] in settings["Hydro_prod"]:
                    hydro_VOM_output_sum = sum_params(param, year, hydro_VOM_output_sum)
                if param["entity_byname"][0] in settings["Geothermal"]:
                    geothermal_VOM_output_sum = sum_params(param, year, geothermal_VOM_output_sum)
                if param["entity_byname"][0] in PP_weights_production.keys():
                    condensing_VOM_output_sum = sum_params(param, year, 0)
                    PP_VOMs[param["entity_byname"][0]] = condensing_VOM_output_sum * PP_weights_production[param["entity_byname"][0]]

            write_param(file, f'input_VC_hydro=', hydro_VOM_output_sum, next_line = True)
            write_param(file, f'input_VC_geothermal=', geothermal_VOM_output_sum, next_line = True)

            condensing_VOM = sum(PP_VOMs.values())
            write_param(file, f'input_VC_pp=', condensing_VOM, next_line = True)

        #Lifetime
        if settings["Lifetime"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='Lifetime')
            wind_output_sum = 0
            solar_output_sum = 0
            wind_offshore_output_sum = 0
            hydro_ror_output_sum = 0
            nuclear_output_sum = 0
            hydro_output_sum = 0
            geothermal_output_sum = 0
            condensing_lifetime = dict()
        
            for param in params_from_db:
                if param["entity_byname"][0] in RES_capacity_mapping["Wind"]:
                    wind_output_sum = sum_params(param, year, wind_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Photo Voltaic"]:
                    solar_output_sum = sum_params(param, year, solar_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["Offshore Wind"]:
                    wind_offshore_output_sum = sum_params(param, year, wind_offshore_output_sum)
                if param["entity_byname"][0] in RES_capacity_mapping["River Hydro"]:
                    hydro_ror_output_sum = sum_params(param, year, hydro_ror_output_sum)
                if param["entity_byname"][0] in settings["Nuclear"]:
                    nuclear_output_sum = sum_params(param, year, nuclear_output_sum)
                if param["entity_byname"][0] in settings["Hydro_prod"]:
                    hydro_output_sum = sum_params(param, year, hydro_output_sum)
                if param["entity_byname"][0] in settings["Geothermal"]:
                    geothermal_output_sum = sum_params(param, year, geothermal_output_sum)
                if param["entity_byname"][0] in PP_weights_capacity.keys():
                    condensing_lifetime_output_sum = sum_params(param, year, 0)
                    condensing_lifetime[param["entity_byname"][0]] = condensing_lifetime_output_sum * PP_weights_capacity[param["entity_byname"][0]]
            
            write_param(file, f'input_Period_Wind=', wind_output_sum, next_line = True)
            write_param(file, f'input_Period_PV=', solar_output_sum, next_line = True)
            write_param(file, f'input_Period_WindOffshore=', wind_offshore_output_sum, next_line = True)
            write_param(file, f'input_Period_RiverOffHydro=', hydro_ror_output_sum, next_line = True)
            write_param(file, f'input_Period_Nuclear=', nuclear_output_sum, next_line = True)
            write_param(file, f'input_Period_HydroPower=', hydro_output_sum, next_line = True)
            write_param(file, f'input_Period_GeoPower=', geothermal_output_sum, next_line = True)

            condensing_lifetime = sum(condensing_lifetime.values())
            write_param(file, f'input_Period_PP=', condensing_lifetime, next_line = True)
      
        ##efficiency
        if settings["Efficiency"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='Efficiency')
            PP_effs = dict()
            for param in params_from_db:
                output_sum = 0
                if param["entity_byname"][0] not in PP_weights_production.keys():
                    continue
                output_sum = sum_params(param, year, output_sum)
                PP_effs[param["entity_byname"][0]] = output_sum * PP_weights_production[param["entity_byname"][0]]
            output_eff = sum(PP_effs.values())
            write_param(file, f'input_eff_pp_el=', output_eff, next_line = True)

        ##storage

        #CAPEX
        if settings["StorageCAPEX"]:
            energy_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='EnergyCapitalCost')
            power_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='PowerCapitalCost')
            Battery_storage = settings["Battery_storage"]
            HydroPump_storage = settings["HydroPump_storage"]
            energy_battery_output_sum = 0
            energy_hydro_pump_output_sum = 0
            power_battery_output_sum = 0
            power_hydro_pump_output_sum = 0

            for param in energy_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    energy_battery_output_sum = sum_params(param, year, energy_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    energy_hydro_pump_output_sum = sum_params(param, year, energy_hydro_pump_output_sum)
            for param in power_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    power_battery_output_sum = sum_params(param, year, power_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    power_hydro_pump_output_sum = sum_params(param, year, power_hydro_pump_output_sum)

            #write_param(file, f'input_H2storage_capex', str(round(float(energy_hydrogen_output_sum/1000),4)), next_line = True)
            #write_param(file, f'input_H2storage_power_capex', str(round(float(power_hydrogen_output_sum/1000),4)), next_line = True)

            #Should input_Inv_HydroStorage= or input_Inv_PumpStorage ie. separate storage or part of hydro?
            write_param(file, f'input_Inv_PumpStorage2=', energy_battery_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_pump2=', power_battery_output_sum/2000, next_line = True)
            write_param(file, f'input_Inv_turbine2=', power_battery_output_sum/2000, next_line = True)
            write_param(file, f'input_Inv_PumpStorage=', energy_hydro_pump_output_sum/1000, next_line = True)
            write_param(file, f'input_Inv_pump=', power_hydro_pump_output_sum/2000, next_line = True)
            write_param(file, f'input_Inv_turbine=', power_hydro_pump_output_sum/2000, next_line = True)

        #FOM
        if settings["StorageFOM"]:
            energy_FOM_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='EnergyFixedOMCost')
            power_FOM_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='PowerFixedOMCost')
            Battery_storage = settings["Battery_storage"]
            HydroPump_storage = settings["HydroPump_storage"]
            energy_FOM_battery_output_sum = 0
            energy_FOM_hydro_pump_output_sum = 0
            power_FOM_battery_output_sum = 0
            power_FOM_hydro_pump_output_sum = 0

            for param in energy_FOM_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    energy_FOM_battery_output_sum = sum_params(param, year, energy_FOM_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    energy_FOM_hydro_pump_output_sum = sum_params(param, year, energy_FOM_hydro_pump_output_sum)
            for param in power_FOM_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    power_FOM_battery_output_sum = sum_params(param, year, power_FOM_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    power_FOM_hydro_pump_output_sum = sum_params(param, year, power_FOM_hydro_pump_output_sum)

            write_fom_share(file, energy_battery_output_sum, energy_FOM_battery_output_sum, 'input_FOM_PumpStorage2=')
            write_fom_share(file, power_battery_output_sum, power_FOM_battery_output_sum, 'input_FOM_pump2=')
            write_fom_share(file, power_battery_output_sum, power_FOM_battery_output_sum, 'input_FOM_turbine2=')
            write_fom_share(file, energy_hydro_pump_output_sum, energy_FOM_hydro_pump_output_sum, 'input_FOM_PumpStorage=')
            write_fom_share(file, power_hydro_pump_output_sum, power_FOM_hydro_pump_output_sum, 'input_FOM_pump=')
            write_fom_share(file, power_hydro_pump_output_sum, power_FOM_hydro_pump_output_sum, 'input_FOM_turbine=')

        #Lifetime
        if settings["StorageLifetime"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='Lifetime')
            Battery_storage = settings["Battery_storage"]
            HydroPump_storage = settings["HydroPump_storage"]
            battery_output_sum = 0
            hydro_pump_output_sum = 0

            for param in params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    battery_output_sum = sum_params(param, year, battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    hydro_pump_output_sum = sum_params(param, year, hydro_pump_output_sum)

            #write_param(file, f'input_H2storage_capex', str(round(float(energy_hydrogen_output_sum/1000),4)), next_line = True)
            #write_param(file, f'input_H2storage_power_capex', str(round(float(power_hydrogen_output_sum/1000),4)), next_line = True)

            write_param(file, f'input_Period_PumpStorage2=', battery_output_sum, next_line = True)
            write_param(file, f'input_Period_pump2=', battery_output_sum, next_line = True)
            write_param(file, f'input_Period_turbine2=', battery_output_sum, next_line = True)
            write_param(file, f'input_Period_PumpStorage=', hydro_pump_output_sum, next_line = True)
            write_param(file, f'input_Period_pump=', hydro_pump_output_sum, next_line = True)
            write_param(file, f'input_Period_turbine=', hydro_pump_output_sum, next_line = True)

        #Efficiency
        if settings["StorageEfficiency"]:
            charge_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='StorageChargeEff')
            discharge_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='StorageDischargeEff')
            charge_battery_output_sum = 0
            charge_hydro_pump_output_sum = 0
            discharge_battery_output_sum = 0
            discharge_hydro_pump_output_sum = 0

            for param in charge_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    charge_battery_output_sum = sum_params(param, year, charge_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    charge_hydro_pump_output_sum = sum_params(param, year, charge_hydro_pump_output_sum)
            for param in discharge_params_from_db:
                if param["entity_byname"][0] in Battery_storage:
                    discharge_battery_output_sum = sum_params(param, year, discharge_battery_output_sum)
                if param["entity_byname"][0] in HydroPump_storage:
                    discharge_hydro_pump_output_sum = sum_params(param, year, discharge_hydro_pump_output_sum)
            
            write_param(file, f'input_eff_pump_el2=', charge_battery_output_sum, next_line = True)
            write_param(file, f'input_eff_turbine_el2=', discharge_battery_output_sum, next_line = True)
            write_param(file, f'input_eff_pump_el=', charge_hydro_pump_output_sum, next_line = True)
            write_param(file, f'input_eff_turbine_el=', discharge_hydro_pump_output_sum , next_line = True)

        #Electrolyzer efficiency
        if settings["ElectrolyzerEfficiency"]:
            Hydrogen_ton_to_MWh = settings["Hydrogen_ton_to_MWh"]
            electrolyzer_fuel_use = 0
            #Power use MW for ton of H2
            params_from_db = source_db.find_parameter_values(entity_class_name='General', parameter_definition_name='ElectrolyzerPowerUse')
            for param in params_from_db:
                electrolyzer_fuel_use = sum_params(param, year, electrolyzer_fuel_use)
                write_param(file, f'input_eff_ELTtrans_fuel=', 1/(electrolyzer_fuel_use * Hydrogen_ton_to_MWh), next_line = True)
                break
        
        #Hydro storage params that are not from the results
        if settings["HydroStorage"]:
            output_sum = 0
            stor_params_from_db = source_db.find_parameter_values(entity_class_name='Node__Technology', parameter_definition_name='MaxInstalledCapacity')
            for param in stor_params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                if param["entity_byname"][1] not in settings["Hydro_stor"]:
                    continue
                output_sum = sum_params(param, year, output_sum)
            hydro_storage_capacity = output_sum

            output_sum = 0
            params_from_db = source_db.find_parameter_values(entity_class_name='Node', parameter_definition_name='HydroGenMaxAnnualProduction')
            eff_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='Efficiency')
            node__gens = source_db.find_entities(entity_class_name='Node__Generator')
            for param in params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                effs = []
                for node_gen in node__gens:
                    if node_gen["entity_byname"][1] not in settings["Hydro_prod"] or node_gen["entity_byname"][0] != param["entity_byname"][0]:
                        continue
                    for eff_param in eff_from_db:
                        if node_gen["entity_byname"][1] == eff_param["entity_byname"][0]:
                            efficiency = api.from_database(eff_param["value"], eff_param["type"])
                            if isinstance(efficiency, api.Map):
                                for i, val in enumerate(efficiency.indexes):
                                    if val == year:
                                        effs.append(efficiency.values[i])
                            else:
                                effs.append(efficiency)
                if effs:
                    avg_eff = sum(effs)/len(effs)
                else:
                    avg_eff = 1
                value_map = api.from_database(param["value"], param["type"])
                write_param(file, f'input_hydro_watersupply=', value_map/avg_eff/1000/1000, next_line = True)
                break

        #C02 price
        if settings["CO2Price"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='General', parameter_definition_name='CO2Price') 
            co2_price = 0
            for param in params_from_db:
                co2_price = sum_params(param, year, co2_price)
                write_param(file, f'input_CO2_price=', co2_price, next_line = True)
                break

        #Transmission line invest params
        if settings["InterconnectionInvestment"]:
            node__node__linetypes = source_db.find_entities(entity_class_name='Node__Node__LineType')
            length_db = source_db.find_parameter_values(entity_class_name='Node__Node', parameter_definition_name='Length')
            linetype_capex_db = source_db.find_parameter_values(entity_class_name='LineType', parameter_definition_name='TypeCapitalCost')
            linetype_FOM_db = source_db.find_parameter_values(entity_class_name='LineType', parameter_definition_name='TypeFixedOMCost')
            lifetime_params_from_db = source_db.find_parameter_values(entity_class_name='Node__Node', parameter_definition_name='Lifetime') 

            #average lifetime of interconnections where this node is involved
            lifetime = 0
            count = 0
            for param in lifetime_params_from_db:
                if param["entity_byname"][0] in nodes or param["entity_byname"][1] in nodes:
                    count +=1
                    lifetime = sum_params(param, year, lifetime)
            write_param(file, f'Input_Period_Interconnection=', lifetime/count, next_line = True)

            #average capex and fom share where this node is involved and investment parameters exist
            capex = 0
            capex_count = 0
            fom = 0
            fom_count = 0
            length = 0
            length_count = 0
            exclude_nodes = settings["Exclude_connections_to_nodes"]
            for n_n_l in node__node__linetypes:
                #exclude connections to offshore nodes and connections between two nodes inside the country
                if (n_n_l["entity_byname"][0] in exclude_nodes and n_n_l["entity_byname"][0] not in nodes) or \
                    (n_n_l["entity_byname"][1] in exclude_nodes and n_n_l["entity_byname"][1] not in nodes):
                    continue
                if n_n_l["entity_byname"][0] in nodes and n_n_l["entity_byname"][1] in nodes:
                    continue
                if n_n_l["entity_byname"][0] in nodes or n_n_l["entity_byname"][1] in nodes:
                    for length_param in length_db:
                        if n_n_l["entity_byname"][0] == length_param["entity_byname"][0] and n_n_l["entity_byname"][1] == length_param["entity_byname"][1]:
                            length_count += 1
                            length = sum_params(length_param, year, length)
                    for capex_param in linetype_capex_db:
                        if n_n_l["entity_byname"][2] == capex_param["entity_byname"][0]:
                            capex_count += 1
                            capex = sum_params(capex_param, year, capex)
                    for fom_param in linetype_FOM_db:
                        if n_n_l["entity_byname"][2] == fom_param["entity_byname"][0]:
                            fom_count += 1
                            fom = sum_params(fom_param, year, fom)
            if length_count > 0 and capex_count > 0 and fom_count > 0: 
                capex = capex/capex_count * length/length_count
                fom = fom/fom_count * length/length_count
            write_param(file, f'Input_inv_Interconnection=', capex/count, next_line = True)
            write_fom_share(file, capex, fom, f'Input_FOM_Interconnection=')    

    return hydro_storage_capacity 

def add_from_empire_results_db(file, empire_results_db, country_year, settings, PP_weights_production):
    
    nodes = settings["Country_nodes"][country_year[0]] if country_year[0] in settings["Country_nodes"].keys() else [country_year[0]]
    year = country_year[1]

    ### RES capacity
    RES_capacity_mapping = settings["RES"]
    Condensing_PP_mapping = settings["Condensing_PP"]
    PP2_mapping = settings["Only_power_production"]
    nuclear_PP_list = settings["Nuclear"]
    Geo_PP_list = settings["Geothermal"]
    Waste_PP_list = settings["Waste"]
    RES_order = get_RES_order(file, settings)

    with api.DatabaseMapping(empire_results_db) as source_db:
        if settings["ResultsCapacity"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
            for RESname, prod_names in RES_capacity_mapping.items():
                output_sum = 0
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in prod_names:
                        continue
                    value_map = api.from_database(param["value"], param["type"])
                    if isinstance(value_map, api.Map):
                        for i, val in enumerate(value_map.indexes):
                            if val == year:
                                output_sum += round(float(value_map.values[i]),4)
                                break
                    else: #float
                        output_sum += value_map
                write_param(file, f'input_{RES_order[RESname]}_capacity', output_sum, next_line = True)

            
            ##condensing power plants
            output_sum = 0
            for PP_type, PP_list in Condensing_PP_mapping.items():
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in PP_list:
                        continue
                    output_sum = sum_params(param, year, output_sum)
                    pp1 = output_sum * settings["Share of Condensing_PP_to_PP2"][country_year[0]]
                    PP_to_PP2 = output_sum - pp1
            write_param(file, f'input_cap_pp_el=', pp1, next_line = True)
            write_param(file, f'input_cap_chp3_el=', pp1 * settings["Share of condensing_PP1_in_CHP3"][country_year[0]], next_line = True)
            
            #PP2
            output_sum = 0
            for PP_type, PP_list in PP2_mapping.items():
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in PP_list:
                        continue
                    output_sum = sum_params(param, year, output_sum)
                    pp2 = output_sum + PP_to_PP2
            write_param(file, f'input_cap_pp2_el=', pp2, next_line = True)
            
            # The rest of electricity production
            type_supply_mapping = {
                "input_nuclear_cap=": nuclear_PP_list,
                "input_GeoPower_cap=": Geo_PP_list,
                "input_Waste3_Waste=": Waste_PP_list
            }
            for output_name, input_name_list in type_supply_mapping.items():
                output_sum = 0
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in input_name_list:
                        continue
                    output_sum = sum_params(param, year, output_sum)
                write_param(file, output_name, output_sum, next_line = True)
            
        #shares of production
        params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genExpectedAnnualProduction_GWh')
        condensing_number_map = {
                "Bio": "4",
                "Coal": "1",
                "Gas": "3",
                "Hydrogen": "6",
                "Oil": "2"
            }
        if settings["SharesOfCondensingFuelTypes"]:
            ##condensing power plants
            for PP_type, PP_list in Condensing_PP_mapping.items():
                output_sum = 0
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in PP_list:
                        continue
                    output_sum = sum_params(param, year, output_sum)
                
                #Twh
                write_param(file, f'input_fuel_PP[{condensing_number_map[PP_type]}]=', output_sum/1000, next_line = True)
                write_param(file, f'input_fuel_chp3[{condensing_number_map[PP_type]}]=', output_sum/1000, next_line = True)
        
        if settings["SharesOfPP2FuelTypes"]:
            ##only power production plants
            for PP_type, PP_list in PP2_mapping.items():
                output_sum = 0
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in PP_list:
                        continue
                    output_sum = sum_params(param, year, output_sum)
            
                #Twh
                write_param(file, f'input_fuel_PP2[{condensing_number_map[PP_type]}]=', output_sum/1000, next_line = True)

                ## The order of the RES sources (RES1, RES2) can be changed
        ## Other issue is that the filenames aren't even RES coded but instead use names like wind onshore, solar etc.
        ## Here for example wind goes to Filnavn_wave=
        if settings["RESCapacityFactorProfile"]:
            RES_mapping = get_RES_order(file, settings)
            RES_Filenames = {
                "RES1": "Filnavn_wave=",
                "RES2": "Filnavn_windoffshore=",
                "RES3": "Filnavn_pv=",
                "RES4": "Filnavn_RES4=",
                "RES5": "Filnavn_RES5=",
                "RES6": "Filnavn_RES6=",
                "RES7": "Filnavn_RES7=",
            }
            #Get capacity for nodes to calculate weighted profiles
            capacity_for_nodes = dict(dict())
            params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
            for RESname, prod_names in RES_capacity_mapping.items():
                output_sum = dict()
                for param in params_from_db:
                    if param["entity_byname"][0] not in nodes:
                        continue
                    if param["entity_byname"][1] not in prod_names:
                        continue
                    value_map = api.from_database(param["value"], param["type"])
                    if isinstance(value_map, api.Map):
                        for i, val in enumerate(value_map.indexes):
                            if val == year:
                                if param["entity_byname"][0] not in output_sum.keys():
                                    output_sum[param["entity_byname"][0]] = 0
                                output_sum[param["entity_byname"][0]] += round(float(value_map.values[i]),4)
                                break
                    else: #float
                        output_sum += value_map
                capacity_for_nodes[RESname] = output_sum
            
            #RES profiles
            file_name = f'{country_year[0]}_PV_{country_year[1]}.txt'
            solar_timeseries = get_weighted_timeseries("solar.csv", settings, capacity_for_nodes["Photo Voltaic"], nodes)
            if solar_timeseries:
                write_timeseries(file_name, solar_timeseries)
                write_param(file, RES_Filenames[RES_mapping["Photo Voltaic"]], file_name, next_line = True)

            file_name = f'{country_year[0]}_WindOnshore_{country_year[1]}.txt'
            wind_timeseries = get_weighted_timeseries("windonshore.csv", settings, capacity_for_nodes["Wind"], nodes)
            if wind_timeseries:
                write_timeseries(file_name, wind_timeseries)
                write_param(file, RES_Filenames[RES_mapping["Wind"]], file_name, next_line = True)

            file_name = f'{country_year[0]}_WindOffshore_{country_year[1]}.txt'
            wind_offshore_timeseries = get_weighted_timeseries("windoffshore.csv", settings, capacity_for_nodes["Offshore Wind"], nodes)
            if wind_offshore_timeseries:
                write_timeseries(file_name, wind_offshore_timeseries)
                write_param(file, RES_Filenames[RES_mapping["Offshore Wind"]], file_name, next_line = True)

            file_name = f'{country_year[0]}_HydroRoR_{country_year[1]}.txt'
            hydro_ror_timeseries = get_weighted_timeseries("hydroror.csv", settings, capacity_for_nodes["River Hydro"], nodes, timestamp_col= -7)
            if hydro_ror_timeseries:
                write_timeseries(file_name, hydro_ror_timeseries)
                write_param(file, RES_Filenames[RES_mapping["River Hydro"]], file_name, next_line = True)

            file_name = f'{country_year[0]}_HydroSeasonal_{country_year[1]}.txt'
            all_hydro = get_timeseries("hydroseasonal.csv", settings, nodes, timestamp_col= -5)
            if all_hydro:
                hydro_timeseries = [sum(x) for x in zip(*all_hydro.values())]
                write_timeseries(file_name, hydro_timeseries)
                write_param(file,"filnavn_hydro_water=", file_name, next_line = True)

        #transmission capacity
        if settings["ResultsTransmissionCapacity"]:
            params_from_db = source_db.find_parameter_values(entity_class_name='node__node', parameter_definition_name='transmissionInstalledCap_MW')
            output_sum = 0
            exclude_nodes = settings["Exclude_connections_to_nodes"]
            for param in params_from_db:
                #exclude connections to offshore nodes and connections between two nodes inside the country
                if (param["entity_byname"][0] in exclude_nodes and param["entity_byname"][0] not in nodes) or \
                    (param["entity_byname"][1] in exclude_nodes and param["entity_byname"][1] not in nodes):
                    continue
                if param ["entity_byname"][0] in nodes and param["entity_byname"][1] in nodes:
                    continue
                if param ["entity_byname"][0] in nodes or param["entity_byname"][1] in nodes:
                    output_sum = sum_params(param, year, output_sum)
            write_param(file, f'input_max_imp_exp=', output_sum, next_line = True)
            
        #storage capacity
        if settings["ResultsStorageCapacity"]:
            elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storPWInstalledCap_MW')
            stor_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storENInstalledCap_MWh')
            
            #Battery capacity
            capacity_mapping = settings["Battery_storage"]
            elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, capacity_mapping, nodes, year)
            write_param(file, f'input_cap_pump_el2=', elec_output_sum, next_line = True)
            write_param(file, f'input_cap_turbine_el2=', elec_output_sum, next_line = True)
            write_param(file, f'input_storage_pump_cap2=', stor_output_sum/1000, next_line = True)

            #HydroPump capacity
            capacity_mapping = settings["HydroPump_storage"]
            elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, capacity_mapping, nodes, year)
            write_param(file, f'input_cap_pump_el=', elec_output_sum, next_line = True)
            write_param(file, f'input_cap_turbine_el=', elec_output_sum, next_line = True)
            write_param(file, f'input_storage_pump_cap=', stor_output_sum/1000, next_line = True)
        
        if settings["ResultsHydroCapacity"]:
            elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
            for param in elec_params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                if param["entity_byname"][1] not in settings["Hydro_prod"]:
                    continue
                output_sum = sum_params(param, year, output_sum)
            write_param(file, f'input_hydro_cap=', output_sum, next_line = True)

        #Hydrogen storage capacity
        if settings["ResultsHydrogenStorageCapacity"]:
            Hydrogen_ton_to_MWh = settings["Hydrogen_ton_to_MWh"]
            total_hydrogen_capacity_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name= 'H2_storage_capacity_total_ton')
            for param in total_hydrogen_capacity_db:
                if param["entity_byname"][0] not in nodes:
                    output_sum = sum_params(param, year, output_sum)
            write_param(file, f'input_H2storage_trans_cap=', output_sum * Hydrogen_ton_to_MWh / 1000, next_line = True)

        #Electrolyzer capacity
        if settings["ResultsElectrolyzerCapacity"]:
            electrolyzer_params_from_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='electrolyzer_capacity_total_MW')
            for param in electrolyzer_params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                value_map = api.from_database(param["value"], param["type"])
                if isinstance(value_map, api.Map):
                    for i, val in enumerate(value_map.indexes):
                        if val == year:
                            write_param(file, f'input_cap_ELTtrans_el=', value_map.values[i], next_line = True)
                            break
        
        if settings["HydrogenImport"]:
            H2_import_params_from_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='terminal_H2_import_exp_ton')
            H2_prod_params_from_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='electrolyzer_annual_prod_exp_ton')
            year_import = 0
            year_export = 0
            for param in H2_import_params_from_db + H2_prod_params_from_db:
                if param["entity_byname"][0] not in nodes:
                    continue
                value_map = api.from_database(param["value"], param["type"])
                if isinstance(value_map, api.Map):
                    for i, val in enumerate(value_map.indexes):
                        if val == year:
                            if value_map.values[i] < 0:
                                year_export = -value_map.values[i]
                            year_import += value_map.values[i]
                            break   
            write_param(file, f'input_HydrogenImport=', year_import, next_line = True)
            write_param(file, f'input_HydrogenExport=', year_export, next_line = True)

        if settings["HydrogenDemand"]:
            H2_use_params_from_db_1 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen used for ammonia [ton]')
            H2_use_params_from_db_2 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen used for cement [ton]')
            H2_use_params_from_db_3 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen used for oil refining [ton]')
            H2_use_params_from_db_4 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen used for steel [ton]')
            H2_use_params_from_db_5 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen used for transport [ton]')
            H2_use_params_from_db_6 = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='Hydrogen burned for power and heat [ton]')

            H2_use_params = H2_use_params_from_db_1 + H2_use_params_from_db_2 + H2_use_params_from_db_3 + \
                            H2_use_params_from_db_4 + H2_use_params_from_db_5 + H2_use_params_from_db_6
            year_demand = 0
            for param in H2_use_params:
                if param["entity_byname"][0] not in nodes:
                    continue
                value_map = api.from_database(param["value"], param["type"])
                if isinstance(value_map, api.Map):
                    for i, val in enumerate(value_map.indexes):
                        if val == year:
                            sum = 0
                            for i in value_map.values[i].values:
                                sum += float(i)
                            year_demand += sum
                            break   
            write_param(file, f'input_fuel_CSHP[6]=', year_demand, next_line = True)

def add_from_EMX(file, EMX_output_file, param_mapping):
    pass


def get_techology_mapping(empire_db):
    technology_mapping = dict(list())
    with api.DatabaseMapping(empire_db) as source_db:
        Technology__Generators = source_db.get_entity_items(entity_class_name='Technology__Generator')
        for rel in Technology__Generators:
            tech_gen = rel['entity_byname']
            if tech_gen[0] not in technology_mapping.keys():
                technology_mapping[tech_gen[0]] = list()
            technology_mapping[tech_gen[0]].append(tech_gen[1])
    return technology_mapping

def main(settings_file, empire_db, empire_results_db):

    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            settings = yaml.safe_load(file)
    output_file_mapping = settings["Country_filename"]
    year_mapping = settings["Year_mapping"]

    for country, file in output_file_mapping.items():
        country_years = list()
        for year in year_mapping.keys():
            country_years.append((country,year))
        for country_year in country_years:
            country_name, year = country_year
            shutil.copyfile(file, file.replace('.txt', f'_{country}_{year}.txt'))
            country_year_input = (country_name, year_mapping[year][0])
            country_year_output = (country_name, year_mapping[year][1])

            nodes = settings["Country_nodes"][country_year[0]] if country_year[0] in settings["Country_nodes"].keys() else [country_year[0]]

            PP_weights_capacity = get_PP_weights(empire_results_db, nodes, year, settings, weight_type='capacity')
            PP_weights_production = get_PP_weights(empire_results_db, nodes, year, settings, weight_type='production') 

            hydro_storage_capacity = add_from_empire_db(file.replace('.txt', f'_{country_name}_{year}.txt'), empire_db, country_year_input, settings, PP_weights_capacity, PP_weights_production)
            add_from_empire_results_db(file.replace('.txt', f'_{country_name}_{year}.txt'), empire_results_db, country_year_output, settings, PP_weights_production)
            print("written EnergyPlan file for node ", country, " for years ", year_mapping[year], "to", file.replace('.txt', f'_{country}_{year}.txt'))



if __name__ == "__main__":
    developer_mode = False
    settings_file = sys.argv[1]
    empire_db = sys.argv[2]
    empire_results_db = sys.argv[3]
    #EMX_output_file = sys.argv[4]
    main(settings_file, empire_db, empire_results_db)