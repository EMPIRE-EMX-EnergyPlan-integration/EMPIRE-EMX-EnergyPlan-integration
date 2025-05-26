import sys
import shutil
from pathlib import Path
import spinedb_api as api
from collections import defaultdict
from sqlalchemy.exc import DBAPIError
import os
import yaml


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
    if not found:
        with open(file, "a", encoding='utf-16 LE') as output_file:
            if next_line:
                output_file.write(f'{param_name} = \n')
                output_file.write(f'{param_value}\n')
            else:
                output_file.write(f'{param_name} = {param_value}\n')


def add_from_empire_db(file, empire_db, param_mapping):
    pass
def add_from_empire_results_db(file, empire_results_db, node_year, settings):
    
    ### RES capacity
    RES_capacity_mapping = settings["RES"]
    Condensing_PP_mapping = settings["Condensing_PP"]
    nuclear_PP_mapping = settings["Nuclear_PP"]

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
                                output_sum += round(float(value_map.values[i]),2)
                                break
                    else: #float
                        output_sum = value_map
            write_param(file, f'Name{RESnum}', str(output_name), next_line = True)
            write_param(file, f'input_{RESnum}_capacity', str(round(output_sum,2)), next_line = True)
        
        ##condensing power plants
        output_sum = 0
        for PP_type, PP_list in Condensing_PP_mapping.items():
            for param in params_from_db:
                if param["entity_byname"][0] != node_year[0]:
                    continue
                if param["entity_byname"][1] not in PP_list:
                    continue
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_cap_pp_el', str(round(float(output_sum),2)), next_line = True)
        
        #Nuclear power plants
        output_sum = 0
        for PP_list in nuclear_PP_mapping:
            for param in params_from_db:
                if param["entity_byname"][0] != node_year[0]:
                    continue
                if param["entity_byname"][1] not in PP_list:
                    continue
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_nuclear_cap', str(round(float(output_sum),2)), next_line = True)

        #transmission capacity
        #transmission_capacity_mapping = settings["Transmission_capacity"]
        params_from_db = source_db.find_parameter_values(entity_class_name='node__node', parameter_definition_name='transmisionInstalledCap_MW')
        output_sum = 0
        for param in params_from_db:
            if param ["entity_byname"][0] == node_year[0] or param["entity_byname"][1] == node_year[0]:
                output_sum = sum_params(param, node_year, output_sum)
        write_param(file, f'input_max_imp_exp', str(round(float(output_sum),2)), next_line = True)
        
        #storage capacity
        elec_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storPWInstalledCap_MW')
        stor_params_from_db = source_db.find_parameter_values(entity_class_name='node__storage', parameter_definition_name='storENInstalledCap_MW')
        
        #Hydrogen capacity
        hydrogen_capacity_mapping = settings["Hydrogen_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, hydrogen_capacity_mapping, node_year)
        write_param(file, f'input_cap_ELTtrans_el', str(round(float(elec_output_sum),2)), next_line = True)
        write_param(file, f'input_H2storage_trans_cap', str(round(float(stor_output_sum/1000),2)), next_line = True)
        
        #Battery capacity
        hydrogen_capacity_mapping = settings["Battery_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, hydrogen_capacity_mapping, node_year)
        write_param(file, f'input_cap_pump_el2', str(round(float(elec_output_sum),2)), next_line = True)
        write_param(file, f'input_cap_turbine_el2', str(round(float(elec_output_sum),2)), next_line = True)
        write_param(file, f'input_storage_pump_cap2', str(round(float(stor_output_sum/1000),2)), next_line = True)

        #HydroPump capacity
        hydrogen_capacity_mapping = settings["HydroPump_storage"]
        elec_output_sum, stor_output_sum = sum_storage(elec_params_from_db, stor_params_from_db, hydrogen_capacity_mapping, node_year)
        write_param(file, f'input_hydro_pump_cap', str(round(float(elec_output_sum),2)), next_line = True)
        write_param(file, f'input_hydro_cap', str(round(float(elec_output_sum),2)), next_line = True)
        write_param(file, f'input_hydro_storage', str(round(float(stor_output_sum/1000),2)), next_line = True)


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
    #output_file_mapping = {
    #    "Denmark": "./DK2020_2018edition.txt"
    #}
    #year_list = ["2020-2025"]

    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            settings = yaml.safe_load(file)
    output_file_mapping = settings["Node_filename"]
    year_list = settings["Year_list"]

    for node, file in output_file_mapping.items():
        node_years = list()
        for year in year_list:
            node_years.append((node,year))
        for node_year in node_years:
            node_name, year = node_year
            print(node_year)
            shutil.copyfile(file, file.replace('.txt', f'_{node}_{year}.txt'))

            #technology_mapping =  get_techology_mapping(empire_db)
            #add_from_empire_db(energyPlan_inputfile.replace('.csv', f'_{node_name}_{year}.csv'), empire_db, empire_param_mapping, node_year)
            add_from_empire_results_db(file.replace('.txt', f'_{node_name}_{year}.txt'), empire_results_db, node_year, settings)



if __name__ == "__main__":
    developer_mode = False
    settings_file = sys.argv[1]
    empire_db = sys.argv[2]
    empire_results_db = sys.argv[3]
    #EMX_output_file = sys.argv[4]
    main(settings_file, empire_db, empire_results_db)