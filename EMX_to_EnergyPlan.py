import sys
from pathlib import Path
import os
import yaml
import csv


def main(settings_file, EMX_output_folder, EnergyPlan_folder):

    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            settings = yaml.safe_load(file)
    output_file_mapping = settings["Country_filename"]
    year_mapping = settings["Years_modelled"]

    folder = EnergyPlan_folder
    
    for country, file in output_file_mapping.items():
        country_years = list()
        for year in year_mapping:
            country_years.append((country,year))
        for country_year in country_years:
            country_name, year = country_year
            add_from_EMX(Path(folder,file.replace('.txt', f'_{country_name}_{year}.txt')), EMX_output_folder, country_year, settings)
            print("written EMX results to EnergyPlan file for node ", country, " for years ", year, "to", Path(folder,file.replace('.txt', f'_{country}_{year}.txt')))

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


def add_from_EMX(file, EMX_output_folder, country_year, settings):

    emx_file = Path(EMX_output_folder, 'trans_cap_current.csv')
    result_map = get_emx_file(emx_file)
    
    if settings["H2_transport_capacity"]:
        #for param_name, emx_param in param_mapping.items():
        powerline_cap = 0
        h2_transport_cap = 0

        transport_capacity_map = dict()
        for i in settings["EMX_powerline"]:
            transport_capacity_map[i] = 0
        for i in settings["EMX_H2_transport"]:
            transport_capacity_map[i] = 0

        transport_capacity_map = sum_technologies(result_map, transport_capacity_map, settings, country_year, transport = True)
        
        for transport_type, capacity in transport_capacity_map.items():
            if transport_type in settings["EMX_powerline"]:
                powerline_cap += capacity
            elif transport_type in settings["EMX_H2_transport"]:
                h2_transport_cap += capacity

        #write_param(file, "input_fuel_Transport[6]=", h2_transport_cap, next_line = True) #wrong
        #write_param(file, "input_transport_TWh=", powerline_cap, next_line = True)  #wrong 
        #input_max_imp_exp=

    if settings["H2_transport_capex"]:
        emx_file = Path(EMX_output_folder, 'trans_cap_capex.csv')
        result_map = get_emx_file(emx_file)

        #transport capex
        powerline_capex = 0
        h2_transport_capex = 0

        transport_capex_map = dict()
        for i in settings["EMX_powerline"]:
            transport_capex_map[i] = 0
        for i in settings["EMX_H2_transport"]:
            transport_capex_map[i] = 0
        
        transport_capex_map = sum_technologies(result_map, transport_capex_map, settings, country_year, transport = True)

        for transport_type, capex in transport_capex_map.items():
            if transport_type in settings["EMX_powerline"]:
                if powerline_cap <= 0:
                    powerline_capex += capex / len(list(x for x in transport_capex_map.keys() if x in settings["EMX_powerline"]))
                else:
                    powerline_capex += capex * transport_capacity_map[transport_type] / powerline_cap
            elif transport_type in settings["EMX_H2_transport"]:
                if h2_transport_cap <= 0:
                    h2_transport_capex += capex / len(list(x for x in transport_capex_map.keys() if x in settings["EMX_H2_transport"]))
                else:
                    h2_transport_capex += capex * transport_capacity_map[transport_type] / h2_transport_cap

        #write_param(file, "input_inv_Transport[6]=", h2_transport_capex, next_line = True) #???
        write_param(file, "Input_inv_Interconnection=", powerline_capex, next_line = True)

    #H2 production
    emx_file = Path(EMX_output_folder, 'cap_current.csv')
    result_map = get_emx_file(emx_file)

    h2_production_cap = 0
    h2_production_map = dict()
    for i in settings["EMX_H2_production"]:
        h2_production_map[i] = 0
    
    h2_production_map = sum_technologies(result_map, h2_production_map, settings, country_year, transport = False)

    for production_type, cap in h2_production_map.items():
        if production_type in settings["EMX_H2_production"]:
            h2_production_cap += cap
    
    if settings["H2_production_capacity"]:
        pass

    if settings["H2_production_capex"]:
        #H2 production capex
        emx_file = Path(EMX_output_folder, 'cap_capex.csv')
        result_map = get_emx_file(emx_file)

        h2_production_capex = 0
        h2_production_capex_map = dict()
        for i in settings["EMX_H2_production"]:
            h2_production_capex_map[i] = 0
        
        h2_production_capex_map = sum_technologies(result_map, h2_production_capex_map, settings, country_year, transport = False)

        for production_type, capex in h2_production_capex_map.items():
            if production_type in settings["EMX_H2_production"]:
                if h2_production_cap <= 0:
                    h2_production_capex += capex / len(list(x for x in h2_production_capex_map.keys() if x in settings["EMX_H2_production"]))
                else:
                    h2_production_capex += capex * h2_production_map[production_type] / h2_production_cap

        write_param(file, "input_Inv_Electrolyser=", h2_production_capex, next_line = True) #???

    #H2 storage
    emx_file = Path(EMX_output_folder, 'stor_level_current.csv')
    result_map = get_emx_file(emx_file)

    h2_storage_cap = 0
    h2_storage_map = dict()
    for i in settings["EMX_H2_storage"]:
        h2_storage_map[i] = 0
    
    h2_storage_map = sum_technologies(result_map, h2_storage_map, settings, country_year, transport = False)
    for storage_type, cap in h2_storage_map.items():
        if storage_type in settings["EMX_H2_storage"]:
            h2_storage_cap += cap

    if settings["H2_storage_capacity"]:
        pass
    
    #H2 storage capex
    if settings["H2_storage_capex"]:
        emx_file = Path(EMX_output_folder, 'stor_level_capex.csv')
        result_map = get_emx_file(emx_file)

        h2_storage_capex = 0
        h2_storage_capex_map = dict()
        for i in settings["EMX_H2_storage"]:
            h2_storage_capex_map[i] = 0
        
        h2_storage_capex_map = sum_technologies(result_map, h2_storage_capex_map, settings, country_year, transport = False)

        for storage_type, capex in h2_storage_capex_map.items():
            if storage_type in settings["EMX_H2_storage"]:
                if h2_storage_cap <= 0:
                    h2_storage_capex += capex / len(list(x for x in h2_storage_capex_map.keys() if x in settings["EMX_H2_storage"]))
                else:
                    h2_storage_capex += capex * h2_storage_map[storage_type] / h2_storage_cap

        write_param(file, "input_Inv_HydrogenStorage=", h2_storage_capex, next_line = True) #???   

def sum_technologies(result_map, tech_map, settings, country_year, transport = False):

    #print(result_map)
    for i, row in result_map.items():
        print(row[0])
        countries, techology = parse_name(row[0], transport=transport)
        print("eka")
        print(countries)
        if transport:
            #only transport between countries
            if countries[0] == countries[1]:
                continue
        print(countries)
        if settings["Country_codes_EMX"][country_year[0]] not in countries:
            continue
        print(country_year[1])
        if country_year[1] not in settings["Year_mapping_EMX"].keys():
            continue
        print("row1" + str(row[1]))
        if settings["Year_mapping_EMX"][country_year[1]] != row[1]:
            continue
        print(techology)
        if techology not in tech_map.keys():
            continue
        tech_map[techology] += float(row[2])

    return tech_map

def parse_name(name, transport = False):

    if transport:
        name_parts = name.split('-')
        transport_type = name_parts[-1]
        #node_codes = name_parts[0]
        node_codes = name[:-len(transport_type)]
        countries = [node[0:2]for node in node_codes.split('_')]
        return countries, transport_type
    else:
        name_parts = name.split('_')
        countries = name_parts[1][0:2]
        technology = name[len(name_parts[2]):]
        return countries, technology

def get_emx_file(emx_file):

    with open(emx_file, 'r') as file:
        csv_reader = csv.reader(file)
        header = next(csv_reader)
        result_map = dict()
        row_number = 0
        for row in csv_reader:
            result_map[row_number] = row
            row_number +=1

    return result_map


if __name__ == "__main__":
    settings_file = sys.argv[1]
    EMX_output_folder = sys.argv[2]
    EnergyPlan_folder = sys.argv[3]
    main(settings_file, EMX_output_folder, EnergyPlan_folder)