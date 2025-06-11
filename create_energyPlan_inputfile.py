import sys
import shutil
from pathlib import Path
import spinedb_api as api
from collections import defaultdict
from sqlalchemy.exc import DBAPIError
import os
import yaml

def write_fom_share(file, output_sum, output_FOM_sum , param_name):
    if output_sum == 0:
        FOM_share = 0
    else:
        FOM_share = output_FOM_sum/output_sum
    write_param(file, f'{param_name}', FOM_share, next_line = True)

def sum_params(param, node_year, output_sum):

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
                year_val = float(node_year[1])
            except ValueError:
                year_val = node_year[1]
            if comp_val == year_val:
                output_sum += float(value_map.values[i])
                break
    else: #float
        output_sum += value_map
    return output_sum

def sum_storage(elec_params, storage_params, storage_mapping, node_year):
    elec_output_sum = 0
    stor_output_sum = 0
    for storage_list in storage_mapping:
        for param in elec_params:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in storage_list:
                continue
            elec_output_sum = sum_params(param, node_year, elec_output_sum)
        for param in storage_params:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in storage_list:
                continue
            stor_output_sum = sum_params(param, node_year, stor_output_sum)
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


def add_from_empire_db(file, empire_db, node_year, settings):
    with api.DatabaseMapping(empire_db) as source_db:
        # Electricity demand
        # Should the transport demand be included?
        params_from_db = source_db.find_parameter_values(entity_class_name='Node', parameter_definition_name='ElectricAnnualDemand')
        output_sum = 0
        for param in params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'Input_el_demand_Twh=', output_sum/1000, next_line = True)

        ##production
        #CAPEX
        RES_capacity_mapping = settings["RES"]
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='CapitalCosts')
        wind_output_sum = 0
        solar_output_sum = 0
        wind_offshore_output_sum = 0
        hydro_ror_output_sum = 0
        nuclear_output_sum = 0
        hydro_output_sum = 0

        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_output_sum = sum_params(param, node_year, wind_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_output_sum = sum_params(param, node_year, solar_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_offshore_output_sum = sum_params(param, node_year, wind_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_ror_output_sum = sum_params(param, node_year, hydro_ror_output_sum)
            if param["entity_byname"][0] in settings["Nuclear"]:
                nuclear_output_sum = sum_params(param, node_year, nuclear_output_sum)
            if param["entity_byname"][0] in settings["Hydro_prod"]:
                hydro_output_sum = sum_params(param, node_year, hydro_output_sum)
        
        write_param(file, f'input_Inv_Wind=', wind_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_PV=', solar_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_WindOffshore=', wind_offshore_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_RiverOffHydro=', hydro_ror_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_Nuclear=', nuclear_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_HydroPower=', hydro_output_sum/1000, next_line = True)

        #FOM %/of CAPEX
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='FixedOMCosts')
        wind_FOM_output_sum = 0
        solar_FOM_output_sum = 0
        wind_FOM_offshore_output_sum = 0
        hydro_FOM_ror_output_sum = 0
        nuclear_FOM_output_sum = 0
        hydro_FOM_output_sum = 0
    
        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_FOM_output_sum = sum_params(param, node_year, wind_FOM_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_FOM_output_sum = sum_params(param, node_year, solar_FOM_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_FOM_offshore_output_sum = sum_params(param, node_year, wind_FOM_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_FOM_ror_output_sum = sum_params(param, node_year, hydro_FOM_ror_output_sum)
            if param["entity_byname"][0] in settings["Nuclear"]:
                nuclear_FOM_output_sum = sum_params(param, node_year, nuclear_FOM_output_sum)
            if param["entity_byname"][0] in settings["Hydro_prod"]:
                hydro_FOM_output_sum = sum_params(param, node_year, hydro_FOM_output_sum)

        write_fom_share(file, wind_output_sum, wind_FOM_output_sum, 'input_FOM_Wind=')
        write_fom_share(file, solar_output_sum, solar_FOM_output_sum, 'input_FOM_PV=')
        write_fom_share(file, wind_offshore_output_sum, wind_FOM_offshore_output_sum, 'input_FOM_WindOffshore=')
        write_fom_share(file, hydro_ror_output_sum, hydro_FOM_ror_output_sum, 'input_FOM_RiverOffHydro=')
        write_fom_share(file, nuclear_output_sum, nuclear_FOM_output_sum, 'input_FOM_Nuclear=')
        write_fom_share(file, hydro_output_sum, hydro_FOM_output_sum, 'input_FOM_HydroPower=')

        #Lifetime
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='Lifetime')
        wind_output_sum = 0
        solar_output_sum = 0
        wind_offshore_output_sum = 0
        hydro_ror_output_sum = 0
        nuclear_output_sum = 0
        hydro_output_sum = 0
    
        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_output_sum = sum_params(param, node_year, wind_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_output_sum = sum_params(param, node_year, solar_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_offshore_output_sum = sum_params(param, node_year, wind_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_ror_output_sum = sum_params(param, node_year, hydro_ror_output_sum)
            if param["entity_byname"][0] in settings["Nuclear"]:
                nuclear_output_sum = sum_params(param, node_year, nuclear_output_sum)
            if param["entity_byname"][0] in settings["Hydro_prod"]:
                hydro_output_sum = sum_params(param, node_year, hydro_output_sum)
        
        write_param(file, f'input_Period_Wind=', wind_output_sum, next_line = True)
        write_param(file, f'input_Period_PV=', solar_output_sum, next_line = True)
        write_param(file, f'input_Period_WindOffshore=', wind_offshore_output_sum, next_line = True)
        write_param(file, f'input_Period_RiverOffHydro=', hydro_ror_output_sum, next_line = True)
        write_param(file, f'input_Period_Nuclear=', nuclear_output_sum, next_line = True)
        write_param(file, f'input_Period_HydroPower=', hydro_output_sum, next_line = True)

        ##storage

        #CAPEX
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
                energy_battery_output_sum = sum_params(param, node_year, energy_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                energy_hydro_pump_output_sum = sum_params(param, node_year, energy_hydro_pump_output_sum)
        for param in power_params_from_db:
            if param["entity_byname"][0] in Battery_storage:
                power_battery_output_sum = sum_params(param, node_year, power_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                power_hydro_pump_output_sum = sum_params(param, node_year, power_hydro_pump_output_sum)

        #write_param(file, f'input_H2storage_capex', str(round(float(energy_hydrogen_output_sum/1000),4)), next_line = True)
        #write_param(file, f'input_H2storage_power_capex', str(round(float(power_hydrogen_output_sum/1000),4)), next_line = True)

        #Should input_Inv_HydroStorage= or input_Inv_PumpStorage ie. separate storage or part of hydro?
        write_param(file, f'input_Inv_PumpStorage2=', energy_battery_output_sum, next_line = True)
        write_param(file, f'input_Inv_pump2=', power_battery_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_turbine2=', power_battery_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_HydroStorage=', energy_hydro_pump_output_sum/1000, next_line = True)
        write_param(file, f'input_Inv_HydroPump=', power_hydro_pump_output_sum, next_line = True)

        #FOM
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
                energy_FOM_battery_output_sum = sum_params(param, node_year, energy_FOM_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                energy_FOM_hydro_pump_output_sum = sum_params(param, node_year, energy_FOM_hydro_pump_output_sum)
        for param in power_FOM_params_from_db:
            if param["entity_byname"][0] in Battery_storage:
                power_FOM_battery_output_sum = sum_params(param, node_year, power_FOM_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                power_FOM_hydro_pump_output_sum = sum_params(param, node_year, power_FOM_hydro_pump_output_sum)

        write_fom_share(file, energy_battery_output_sum, energy_FOM_battery_output_sum, 'input_FOM_PumpStorage2=')
        write_fom_share(file, power_battery_output_sum, power_FOM_battery_output_sum, 'input_FOM_PumpStorage2=')
        write_fom_share(file, power_battery_output_sum, power_FOM_battery_output_sum, 'input_FOM_PumpStorage2=')
        write_fom_share(file, energy_hydro_pump_output_sum, energy_FOM_hydro_pump_output_sum, 'input_FOM_HydroStorage=')
        write_fom_share(file, power_hydro_pump_output_sum, power_FOM_hydro_pump_output_sum, 'input_FOM_HydroPump=')

        #Lifetime
        params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='Lifetime')
        Battery_storage = settings["Battery_storage"]
        HydroPump_storage = settings["HydroPump_storage"]
        battery_output_sum = 0
        hydro_pump_output_sum = 0

        for param in params_from_db:
            if param["entity_byname"][0] in Battery_storage:
                battery_output_sum = sum_params(param, node_year, battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                hydro_pump_output_sum = sum_params(param, node_year, hydro_pump_output_sum)

        #write_param(file, f'input_H2storage_capex', str(round(float(energy_hydrogen_output_sum/1000),4)), next_line = True)
        #write_param(file, f'input_H2storage_power_capex', str(round(float(power_hydrogen_output_sum/1000),4)), next_line = True)


        #Should input_Inv_HydroStorage= or input_Inv_PumpStorage ie. separate storage or part of hydro?
        write_param(file, f'input_Period_PumpStorage2=', battery_output_sum, next_line = True)
        write_param(file, f'input_Period_pump2=', battery_output_sum, next_line = True)
        write_param(file, f'input_Period_turbine2=', battery_output_sum, next_line = True)
        write_param(file, f'input_Period_HydroStorage=', hydro_pump_output_sum, next_line = True)
        write_param(file, f'input_Period_HydroPump=', hydro_pump_output_sum, next_line = True)

        #Efficiency
        charge_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='StorageChargeEff')
        discharge_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='StorageDischargeEff')
        charge_battery_output_sum = 0
        charge_hydro_pump_output_sum = 0
        discharge_battery_output_sum = 0
        discharge_hydro_pump_output_sum = 0

        for param in charge_params_from_db:
            if param["entity_byname"][0] in Battery_storage:
                charge_battery_output_sum = sum_params(param, node_year, charge_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                charge_hydro_pump_output_sum = sum_params(param, node_year, charge_hydro_pump_output_sum)
        for param in discharge_params_from_db:
            if param["entity_byname"][0] in Battery_storage:
                discharge_battery_output_sum = sum_params(param, node_year, discharge_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                discharge_hydro_pump_output_sum = sum_params(param, node_year, discharge_hydro_pump_output_sum)
        
        write_param(file, f'input_eff_pump_el2=', charge_battery_output_sum, next_line = True)
        write_param(file, f'input_eff_turbine_el2=', discharge_battery_output_sum, next_line = True)
        write_param(file, f'input_hydro_pump_eff=', charge_hydro_pump_output_sum, next_line = True)
        write_param(file, f'input_hydro_eff=', discharge_hydro_pump_output_sum , next_line = True)

        #Electrolyzer efficiency
        Hydrogen_ton_to_MWh = settings["Hydrogen_ton_to_MWh"]
        electrolyzer_fuel_use = 0
        #Power use MW for ton of H2
        params_from_db = source_db.find_parameter_values(entity_class_name='General', parameter_definition_name='ElectrolyzerPowerUse')
        for param in params_from_db:
            electrolyzer_fuel_use = sum_params(param, node_year, electrolyzer_fuel_use)
            write_param(file, f'input_eff_ELTtrans_fuel=', 1/(electrolyzer_fuel_use * Hydrogen_ton_to_MWh), next_line = True)
            break
        

        #Hydro storage params that are not from the results
        output_sum = 0
        stor_params_from_db = source_db.find_parameter_values(entity_class_name='Node__Technology', parameter_definition_name='MaxInstalledCapacity')
        for param in stor_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in settings["Hydro_stor"]:
                continue
            output_sum = sum_params(param, node_year, output_sum)
        hydro_storage_capacity = output_sum

        output_sum = 0
        params_from_db = source_db.find_parameter_values(entity_class_name='Node', parameter_definition_name='HydroGenMaxAnnualProduction')
        for param in params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            value_map = api.from_database(param["value"], param["type"])
            write_param(file, f'input_hydro_watersupply=', value_map/1000/1000, next_line = True)
            break

        #C02 price
        params_from_db = source_db.find_parameter_values(entity_class_name='General', parameter_definition_name='CO2Price') 
        co2_price = 0
        for param in params_from_db:
            co2_price = sum_params(param, node_year, co2_price)
            write_param(file, f'input_CO2_price=', co2_price, next_line = True)
            break

        #Transmission line invest params
        node__node__linetypes = source_db.find_entities(entity_class_name='Node__Node__LineType')
        length_db = source_db.find_parameter_values(entity_class_name='Node__Node', parameter_definition_name='Length')
        linetype_capex_db = source_db.find_parameter_values(entity_class_name='LineType', parameter_definition_name='TypeCapitalCost')
        linetype_FOM_db = source_db.find_parameter_values(entity_class_name='LineType', parameter_definition_name='TypeFixedOMCost')
        lifetime_params_from_db = source_db.find_parameter_values(entity_class_name='Node__Node', parameter_definition_name='Lifetime') 

        #average lifetime of interconnections where this node is involved
        lifetime = 0
        count = 0
        for param in lifetime_params_from_db:
            if param["entity_byname"][0] == node_year[0] or param["entity_byname"][1] == node_year[0]:
                count +=1
                lifetime = sum_params(param, node_year, lifetime)
        write_param(file, f'Input_Period_Interconnection=', lifetime/count, next_line = True)

        #average capex and fom share where this node is involved and investment parameters exist
        capex = 0
        capex_count = 0
        fom = 0
        fom_count = 0
        length = 0
        length_count = 0
        for n_n_l in node__node__linetypes:
            if n_n_l["entity_byname"][0] == node_year[0] or n_n_l["entity_byname"][1] == node_year[0]:
                for length_param in length_db:
                    if n_n_l["entity_byname"][0] == length_param["entity_byname"][0] and n_n_l["entity_byname"][1] == length_param["entity_byname"][1]:
                        length_count += 1
                        length = sum_params(length_param, node_year, length)
                for capex_param in linetype_capex_db:
                    if n_n_l["entity_byname"][2] == capex_param["entity_byname"][0]:
                        capex_count += 1
                        capex = sum_params(capex_param, node_year, capex)
                for fom_param in linetype_FOM_db:
                    if n_n_l["entity_byname"][2] == fom_param["entity_byname"][0]:
                        fom_count += 1
                        fom = sum_params(fom_param, node_year, fom)
        if length_count > 0 and capex_count > 0 and fom_count > 0: 
            capex = capex/capex_count * length/length_count
            fom = fom/fom_count * length/length_count
        write_param(file, f'Input_inv_Interconnection=', capex/count, next_line = True)
        write_fom_share(file, capex, fom, f'Input_FOM_Interconnection=')    

    return hydro_storage_capacity 

def add_from_empire_results_db(file, empire_results_db, node_year, settings, hydro_storage_capacity):
    
    ### RES capacity
    RES_capacity_mapping = settings["RES"]
    Condensing_PP_mapping = settings["Condensing_PP"]
    nuclear_PP_list = settings["Nuclear"]

    with api.DatabaseMapping(empire_results_db) as source_db:
        params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
        for RESnum, prod_names in RES_capacity_mapping.items():
            output_sum = 0
            for output_name, input_name_list in prod_names.items():
                for param in params_from_db:
                    if param["entity_byname"][0] != node_year[0]:
                        continue
                    if param["entity_byname"][1] not in input_name_list:
                        continue
                    value_map = api.from_database(param["value"], param["type"])
                    if isinstance(value_map, api.Map):
                        for i, val in enumerate(value_map.indexes):
                            if val == node_year[1]:
                                output_sum += round(float(value_map.values[i]),4)
                                break
                    else: #float
                        output_sum = value_map
            #write_param(file, f'Name{RESnum}', str(output_name), next_line = True)
            write_param(file, f'input_{RESnum}_capacity', output_sum, next_line = True)
        
        ##condensing power plants
        output_sum = 0
        for PP_type, PP_list in Condensing_PP_mapping.items():
            for param in params_from_db:
                if param["entity_byname"][0] != node_year[0]:
                    continue
                if param["entity_byname"][1] not in PP_list:
                    continue
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_cap_pp_el=', output_sum, next_line = True)
        
        #Nuclear power plants
        output_sum = 0
        for param in params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in nuclear_PP_list:
                continue
            output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_nuclear_cap=', output_sum, next_line = True)

        #transmission capacity
        params_from_db = source_db.find_parameter_values(entity_class_name='node__node', parameter_definition_name='transmissionInstalledCap_MW')
        output_sum = 0
        for param in params_from_db:
            if param ["entity_byname"][0] == node_year[0] or param["entity_byname"][1] == node_year[0]:
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_max_imp_exp=', output_sum, next_line = True)
        
        #storage capacity
        elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storPWInstalledCap_MW')
        stor_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storENInstalledCap_MWh')
        
        #Battery capacity
        capacity_mapping = settings["Battery_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, capacity_mapping, node_year)
        write_param(file, f'input_cap_pump_el2=', elec_output_sum, next_line = True)
        write_param(file, f'input_cap_turbine_el2=', elec_output_sum, next_line = True)
        write_param(file, f'input_storage_pump_cap2=', stor_output_sum/1000, next_line = True)

        #HydroPump capacity
        capacity_mapping = settings["HydroPump_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, capacity_mapping, node_year)
        write_param(file, f'input_hydro_pump_cap=', elec_output_sum, next_line = True)
        write_param(file, f'input_hydro_storage=', (hydro_storage_capacity + stor_output_sum)/1000, next_line = True)
        
        #Hydro capacity (How related to the the hydro pump in ENERGYPLAN?)

        #node_technology: 
        # #Max installed capacity: model #current?
        # #Max built capacity: period

        #In energyPlan: Turbine cap, turbine eff, storage cap, pump cap, pump eff, water inflow
        #In EMPIRE: Turbine cap, turbine eff, storage cap, storage eff, water inflow +
        # pump cap, pump eff, pump storage, pump turbine cap? pump turbine eff?
        elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__genType', parameter_definition_name='genInstalledCap_MW')
        for param in elec_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in settings["Hydro_prod"]:
                continue
            output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_hydro_cap=', output_sum, next_line = True)

        #Hydrogen storage capacity
        Hydrogen_ton_to_MWh = settings["Hydrogen_ton_to_MWh"]
        total_hydrogen_capacity_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name= 'H2_storage_capacity_total_ton')
        for param in total_hydrogen_capacity_db:
            if param["entity_byname"][0] != node_year[0]:
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_H2storage_trans_cap=', output_sum * Hydrogen_ton_to_MWh / 1000, next_line = True)

        #Electrolyzer capacity
        electrolyzer_params_from_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='electrolyzer_capacity_total_MW')
        for param in electrolyzer_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            value_map = api.from_database(param["value"], param["type"])
            if isinstance(value_map, api.Map):
                for i, val in enumerate(value_map.indexes):
                    if val == node_year[1]:
                        write_param(file, f'input_cap_ELTtrans_el=', value_map.values[i], next_line = True)
                        break

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
    output_file_mapping = settings["Node_filename"]
    year_mapping = settings["Year_mapping"]

    for node, file in output_file_mapping.items():
        node_years = list()
        for year in year_mapping.keys():
            node_years.append((node,year))
        for node_year in node_years:
            node_name, year = node_year
            print(node_year)
            shutil.copyfile(file, file.replace('.txt', f'_{node}_{year}.txt'))
            node_year_input = (node_name, year_mapping[year][0])
            node_year_output = (node_name, year_mapping[year][1])

            hydro_storage_capacity = add_from_empire_db(file.replace('.txt', f'_{node_name}_{year}.txt'), empire_db, node_year_input, settings)
            add_from_empire_results_db(file.replace('.txt', f'_{node_name}_{year}.txt'), empire_results_db, node_year_output, settings, hydro_storage_capacity)



if __name__ == "__main__":
    developer_mode = False
    settings_file = sys.argv[1]
    empire_db = sys.argv[2]
    empire_results_db = sys.argv[3]
    #EMX_output_file = sys.argv[4]
    main(settings_file, empire_db, empire_results_db)