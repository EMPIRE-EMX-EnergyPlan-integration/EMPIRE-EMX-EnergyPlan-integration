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
    write_param(file, f'{param_name}', str(round(float(FOM_share),4)), next_line = True)


def sum_params(param, node_year, output_sum):

    value_map = api.from_database(param["value"], param["type"])
    if isinstance(value_map, api.Map):
        for i, val in enumerate(value_map.indexes):
            if val == node_year[1]:
                output_sum += float(value_map.values[i])
                break
    else: #float
        output_sum = value_map
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
    print(param_name)
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
                lines[i] = f'{param_name} = \n'
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
                output_file.write(f'{param_name} = \n')
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
        write_param(file, f'Input_el_demand_Twh', str(round(float(output_sum/1000),4)), next_line = True)

        #CAPEX
        RES_capacity_mapping = settings["RES"]
        Nuclear_PP = settings["Nuclear"]
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='CapitalCosts')
        wind_output_sum = 0
        solar_output_sum = 0
        wind_offshore_output_sum = 0
        hydro_ror_output_sum = 0
        nuclear_output_sum = 0

        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_output_sum = sum_params(param, node_year, wind_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_output_sum = sum_params(param, node_year, solar_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_offshore_output_sum = sum_params(param, node_year, wind_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_ror_output_sum = sum_params(param, node_year, hydro_ror_output_sum)
            if param["entity_byname"][0] in Nuclear_PP:
                nuclear_output_sum = sum_params(param, node_year, nuclear_output_sum)
        
        write_param(file, f'input_Inv_Wind=', str(round(float(wind_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_PV=', str(round(float(solar_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_WindOffshore=', str(round(float(wind_offshore_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_RiverOffHydro=', str(round(float(hydro_ror_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_Nuclear=', str(round(float(hydro_ror_output_sum/1000),4)), next_line = True)

        #FOM %/of CAPEX
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='FixedOMCosts')
        wind_FOM_output_sum = 0
        solar_FOM_output_sum = 0
        wind_FOM_offshore_output_sum = 0
        hydro_FOM_ror_output_sum = 0
        nuclear_FOM_output_sum = 0
    
        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_FOM_output_sum = sum_params(param, node_year, wind_FOM_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_FOM_output_sum = sum_params(param, node_year, solar_FOM_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_FOM_offshore_output_sum = sum_params(param, node_year, wind_FOM_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_FOM_ror_output_sum = sum_params(param, node_year, hydro_FOM_ror_output_sum)
            if param["entity_byname"][0] in Nuclear_PP:
                nuclear_FOM_output_sum = sum_params(param, node_year, nuclear_FOM_output_sum)

        write_fom_share(file, wind_output_sum, wind_FOM_output_sum, 'input_FOM_Wind=')
        write_fom_share(file, solar_output_sum, solar_FOM_output_sum, 'input_FOM_PV=')
        write_fom_share(file, wind_offshore_output_sum, wind_FOM_offshore_output_sum, 'input_FOM_WindOffshore=')
        write_fom_share(file, hydro_ror_output_sum, hydro_FOM_ror_output_sum, 'input_FOM_RiverOffHydro=')
        write_fom_share(file, nuclear_output_sum, nuclear_FOM_output_sum, 'input_FOM_Nuclear=')

        #Lifetime
        params_from_db = source_db.find_parameter_values(entity_class_name='Generator', parameter_definition_name='Lifetime')
        wind_output_sum = 0
        solar_output_sum = 0
        wind_offshore_output_sum = 0
        hydro_ror_output_sum = 0
        nuclear_output_sum = 0
    
        for param in params_from_db:
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES1"].values())[0]:
                wind_output_sum = sum_params(param, node_year, wind_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES2"].values())[0]:
                solar_output_sum = sum_params(param, node_year, solar_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES3"].values())[0]:
                wind_offshore_output_sum = sum_params(param, node_year, wind_offshore_output_sum)
            if param["entity_byname"][0] in list(RES_capacity_mapping["RES4"].values())[0]:
                hydro_ror_output_sum = sum_params(param, node_year, hydro_ror_output_sum)
            if param["entity_byname"][0] in Nuclear_PP:
                nuclear_output_sum = sum_params(param, node_year, nuclear_output_sum)
        
        write_param(file, f'input_Period_Wind=', str(round(float(wind_output_sum),4)), next_line = True)
        write_param(file, f'input_Period_PV=', str(round(float(solar_output_sum),4)), next_line = True)
        write_param(file, f'input_Period_WindOffshore=', str(round(float(wind_offshore_output_sum),4)), next_line = True)
        write_param(file, f'input_Period_RiverOffHydro=', str(round(float(hydro_ror_output_sum),4)), next_line = True)
        write_param(file, f'input_Period_Nuclear=', str(round(float(hydro_ror_output_sum),4)), next_line = True)

        ##storage

        #CAPEX
        energy_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='EnergyCapitalCost')
        power_params_from_db = source_db.find_parameter_values(entity_class_name='Storage', parameter_definition_name='PowerCapitalCost')
        Battery_storage = settings["Battery_storage"]
        HydroPump_storage = settings["HydroPump_storage"]
        energy_hydrogen_output_sum = 0
        energy_battery_output_sum = 0
        energy_hydro_pump_output_sum = 0
        power_hydrogen_output_sum = 0
        power_battery_output_sum = 0
        power_hydro_pump_output_sum = 0

        for param in energy_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][0] in Battery_storage:
                energy_battery_output_sum = sum_params(param, node_year, energy_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                energy_hydro_pump_output_sum = sum_params(param, node_year, energy_hydro_pump_output_sum)
        for param in power_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][0] in Battery_storage:
                power_battery_output_sum = sum_params(param, node_year, power_battery_output_sum)
            if param["entity_byname"][0] in HydroPump_storage:
                power_hydro_pump_output_sum = sum_params(param, node_year, power_hydro_pump_output_sum)

        write_param(file, f'input_H2storage_capex', str(round(float(energy_hydrogen_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_H2storage_power_capex', str(round(float(power_hydrogen_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_battery_capex', str(round(float(energy_battery_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_battery_power_capex', str(round(float(power_battery_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_PumpStorage', str(round(float(energy_hydro_pump_output_sum/1000),4)), next_line = True)
        write_param(file, f'input_Inv_Pump', str(round(float(power_hydro_pump_output_sum/1000),4)), next_line = True)


def add_from_empire_results_db(file, empire_results_db, node_year, settings):
    
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
            write_param(file, f'input_{RESnum}_capacity', str(round(output_sum,4)), next_line = True)
        
        ##condensing power plants
        output_sum = 0
        for PP_type, PP_list in Condensing_PP_mapping.items():
            for param in params_from_db:
                if param["entity_byname"][0] != node_year[0]:
                    continue
                if param["entity_byname"][1] not in PP_list:
                    continue
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_cap_pp_el', str(round(float(output_sum),4)), next_line = True)
        
        #Nuclear power plants
        output_sum = 0
        for param in params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            if param["entity_byname"][1] not in nuclear_PP_list:
                continue
            output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_nuclear_cap', str(round(float(output_sum),4)), next_line = True)

        #transmission capacity
        params_from_db = source_db.find_parameter_values(entity_class_name='node__node', parameter_definition_name='transmissionInstalledCap_MW')
        output_sum = 0
        for param in params_from_db:
            if param ["entity_byname"][0] == node_year[0] or param["entity_byname"][1] == node_year[0]:
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_max_imp_exp', str(round(float(output_sum),4)), next_line = True)
        
        #storage capacity
        elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storPWInstalledCap_MW')
        stor_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storENInstalledCap_MWh')
        
        #Battery capacity
        hydrogen_capacity_mapping = settings["Battery_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, hydrogen_capacity_mapping, node_year)
        write_param(file, f'input_cap_pump_el2', str(round(float(elec_output_sum),4)), next_line = True)
        write_param(file, f'input_cap_turbine_el2', str(round(float(elec_output_sum),4)), next_line = True)
        write_param(file, f'input_storage_pump_cap2', str(round(float(stor_output_sum/1000),4)), next_line = True)

        #HydroPump capacity
        hydrogen_capacity_mapping = settings["HydroPump_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, hydrogen_capacity_mapping, node_year)
        write_param(file, f'input_hydro_pump_cap', str(round(float(elec_output_sum),4)), next_line = True)
        write_param(file, f'input_hydro_cap', str(round(float(elec_output_sum),4)), next_line = True)
        write_param(file, f'input_hydro_storage', str(round(float(stor_output_sum/1000),4)), next_line = True)
        
        #Hydrogen storage capacity
        Hydrogen_ton_to_MWh = 1/33.3
        total_hydrogen_capacity_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name= 'H2_storage_capacity_total_ton')
        for param in total_hydrogen_capacity_db:
            if param["entity_byname"][0] != node_year[0]:
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_H2storage_trans_cap=', str(round(float(output_sum * Hydrogen_ton_to_MWh / 1000),4)), next_line = True)

        #Electrolyzer capacity
        electrolyzer_params_from_db = source_db.find_parameter_values(entity_class_name='node', parameter_definition_name='electrolyzer_capacity_total_MW')
        for param in electrolyzer_params_from_db:
            if param["entity_byname"][0] != node_year[0]:
                continue
            value_map = api.from_database(param["value"], param["type"])
            if isinstance(value_map, api.Map):
                for i, val in enumerate(value_map.indexes):
                    if val == node_year[1]:
                        write_param(file, f'input_cap_ELTtrans_el=', str(round(float(value_map.values[i])/1000,4)), next_line = True)
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

            add_from_empire_db(file.replace('.txt', f'_{node_name}_{year}.txt'), empire_db, node_year_input, settings)
            add_from_empire_results_db(file.replace('.txt', f'_{node_name}_{year}.txt'), empire_results_db, node_year_output, settings)



if __name__ == "__main__":
    developer_mode = False
    settings_file = sys.argv[1]
    empire_db = sys.argv[2]
    empire_results_db = sys.argv[3]
    #EMX_output_file = sys.argv[4]
    main(settings_file, empire_db, empire_results_db)