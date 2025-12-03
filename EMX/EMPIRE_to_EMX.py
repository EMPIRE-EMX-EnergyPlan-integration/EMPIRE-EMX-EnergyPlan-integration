import spinedb_api as api
from spinedb_api import DatabaseMapping
from pathlib import Path
import sys
import numpy as np
import shutil
import yaml
import os

def main():
    template_folder = Path("./template_files")
    output_folder = Path("./EMX_input_files")
    output_folder.mkdir(parents=True, exist_ok=True)
    for file in template_folder.iterdir():
        if file.is_file():
            if file.suffix in ['.yml', '.yaml']:
                shutil.copy(file, output_folder / file.name)

    with DatabaseMapping(url_db_in) as source_db:
        #Allow resources to be excluded?
        #Requires separate handling of technologies regions
        if settings["Resources"]:
            data, resource_sources  = create_resources(source_db)
            write_yml(data, Path(output_folder,"resources.yml"), override = False)
        if settings["generators"]:
            generator_data = create_generators(source_db)
        else:
            generator_data = []
        if settings["storages"]:
            storage_data = create_storages(source_db)
        else:
            storage_data = []
        if settings["Techs"]:
            tech_data = resource_sources + generator_data + storage_data
            write_yml(tech_data, Path(output_folder,"techs.yml"), override = False)
        if settings["regions"]:
            regions = create_regions(source_db)
            write_yml(regions, Path(output_folder,"regions.yml"), override = False)
        if settings["global_data"]:
            global_data = create_global_data(source_db)
            write_yml(global_data, Path(output_folder,"global_data.yml"), override = False)


def create_resources(source_db):
    data = []
    resource_sources = []
    for technology in source_db.find_entities(entity_class_name="Technology"):
        co2_contents = []
        fuel_costs = []
        for t_g in source_db.find_entities(entity_class_name="Technology__Generator"):
            if t_g["entity_byname"][0] == technology["entity_byname"][0]:
                if t_g["entity_byname"][1] in settings["empire_to_EMX_tech_mapping"].keys():
                    for CO2_intensity in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "CO2Content", entity_byname = (t_g["entity_byname"][1],)):
                        val = get_value_from_db(CO2_intensity)
                        co2_contents.append(val)
                    for fuelcosts in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "FuelCosts", entity_byname = (t_g["entity_byname"][1],)):
                        val = get_value_from_db(fuelcosts, multiplier= 1/1000)
                        fuel_costs.append([float(x) for x in val.values])
        
        if fuel_costs:
            # Transpose the list of lists to group corresponding elements together
            transposed = zip(*fuel_costs)
            # Calculate the average for each group of elements
            fuelcost_average_list = [sum(group) / len(group) for group in transposed]
        
        if technology["name"] in settings["techs_excluded_from_mapping"]:
            continue

        if co2_contents:
            co2_avg = np.mean(co2_contents)
            if float(co2_avg) > 0:
                data.append("")
                data.append(f'{technology["name"]}:')
                data.append(f'  type : ResourceCarrier')
                data.append(f'  co2_intensity : {co2_avg}')

                resource_sources.append("")
                resource_sources.append(f'{technology["name"]}_source: &{technology["name"]}_source')
                resource_sources.append(f'  type : RefSource')
                resource_sources.append(f'  capacity: 99999')
                if fuelcosts:
                    resource_sources.append(f'  OPEX_variable: {fuelcost_average_list}')
                resource_sources.append(f'  OPEX_fixed: 0')
                resource_sources.append(f'  output:')
                resource_sources.append(f'    {technology["name"]}: 1.0')
                resource_sources.append(f'  additional_data: []')

    data.append("Power:")
    data.append(f'  type : ResourceCarrier')
    data.append(f'  co2_intensity : 0.0')
    data.append("CO2:")
    data.append(f'  type : ResourceEmit')
    data.append(f'  co2_intensity : 1.0')

    for resource in settings["additional_resources"]: #h2 and NH3
        data.append(f"{resource}:")
        data.append(f'  type : ResourceCarrier')
        data.append(f'  co2_intensity : 0.0')
    data.append("")

    return data, resource_sources


def create_generators(source_db):

    RampingGenerators = [x["entity_byname"] for x in source_db.find_entities(entity_class_name="RampingGenerators")]
    HydroGeneratorWithReservoirs = [x["entity_byname"] for x in source_db.find_entities(entity_class_name="HydroGeneratorWithReservoir")]

    data = []

    for generator in source_db.find_entities(entity_class_name="Generator"):
        gen_by =generator["entity_byname"]

        if gen_by in RampingGenerators:
            gen_type = "RefNetworkNode"
        elif gen_by in HydroGeneratorWithReservoirs:
            gen_type = "HydroStor"
        else:
            gen_type = "NonDisRES"
        
        dis = ""
        if gen_type == "HydroStor":
            dis = "discharge_"

        if generator["name"] not in settings["empire_to_EMX_tech_mapping"].keys():
            continue
        data.append(f'{settings["empire_to_EMX_tech_mapping"][generator["name"]]}: &{settings["empire_to_EMX_tech_mapping"][generator["name"]]}')
        data.append(f'  type : {gen_type}')
        if gen_type =="HydroStor":
            data.append(f'  storage_behavior : CyclicStrategic')
            data.append(f'  level_parameters_type : StorCapOpexFixed')
            data.append(f'  discharge_parameters_type : StorCapOpexVar')
            data.append(f'  level_capacity : 99999')
            data.append(f'  level_initial : 0')
            data.append(f'  level_inflow : 0')
            data.append(f'  level_min : 0')
            data.append(f'  stored_resource : Power')
        else:
            data.append(f'  capacity : 0')
        
        if gen_type != "HydroStor":
            for VOM_cost in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "VariableOMCosts", entity_byname = gen_by):
                VOM_val = get_value_from_db(VOM_cost, multiplier = 1 / 1000)
                data.append(f'  OPEX_variable : {VOM_val}')
            for FOM_cost in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "FixedOMCosts", entity_byname = gen_by):
                FOM_val = get_value_from_db(FOM_cost, multiplier = 1 / 1000, value_type= "list")
                data.append(f'  OPEX_fixed : {FOM_val}')
        
        for tech in source_db.find_entities(entity_class_name="Technology__Generator"):
            if tech["entity_byname"] not in ["Hcoal","Existing", "CoFire", "CSS"]:
                technology = tech["entity_byname"][0]
                break
        if gen_type == "RefNetworkNode":
            data.append(f'  input :')
            data.append(f'    {technology} : 1.0')
        elif gen_type == "HydroStor":
            data.append(f'  input :')
            data.append(f'    Power : 1.0')
        else:
            data.append(f'  profile : 0')
        for Efficiency in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "Efficiency", entity_byname = gen_by):
            eff = np.mean(get_value_from_db(Efficiency, value_type= "list"))
            data.append(f'  output:')
            data.append(f'    Power: {eff}')
        

        if gen_type =="HydroStor":
            data.append(f'  level_OPEX_variable : 0')
            data.append(f'  level_OPEX_fixed : 0')
            for VOM_cost in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "VariableOMCosts", entity_byname =(gen_by)):
                VOM_val = get_value_from_db(VOM_cost, multiplier = 1/ 1000)
                data.append(f'  discharge_OPEX_variable : {VOM_val}')
            for FOM_cost in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "FixedCosts", entity_byname = gen_by):
                FOM_val = get_value_from_db(FOM_cost, multiplier =  1 / 1000, value_type= "list")
                data.append(f'  discharge_OPEX_fixed : {FOM_val}')
            data.append(f'  level_OPEX_fixed: 25.500') #????

        additional_data = []
        if any(source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "CO2Content", entity_byname = gen_by)):
            additional_data.append("EmissionData")
        if any(source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "CapitalCosts", entity_byname = gen_by)):
            additional_data.append("InvestmentData")
        data.append(f'  additional_data: {additional_data}')
        if "EmissionData" in additional_data:
            data.append(f'  emissions_type: EmissionsEnergy')
        
        if "InvestmentData" in additional_data:
            for cap_cost in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "CapitalCosts", entity_byname = gen_by):
                cap_val = np.mean(get_value_from_db(cap_cost, multiplier = 1000, value_type= "list"))
                data.append(f'  invest_{dis}capacity_CAPEX : {cap_val}')
            data.append(f'  invest_{dis}capacity_max_installed : 100000')
            data.append(f'  invest_{dis}capacity_max_add : 9999')
            data.append(f'  invest_{dis}capacity_min_add : 0')
            data.append(f'  invest_{dis}capacity_investment_mode : Continuous')
            data.append(f'  invest_{dis}capacity_lifetime_mode : Rolling')
            for lifetime in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "Lifetime", entity_byname = gen_by):
                lifetime_val = api.from_database(lifetime["value"],lifetime["type"])
                data.append(f'  invest_{dis}capacity_lifetime : {lifetime_val}')
        data.append("")
        
    return data

def create_storages(source_db):

    data = []

    for storage in source_db.find_entities(entity_class_name="Storage"):
        sto_by =storage["entity_byname"]
        if storage["name"] not in settings["empire_to_EMX_tech_mapping"].keys():
            continue
        data.append(f'{settings["empire_to_EMX_tech_mapping"][storage["name"]]}: &{settings["empire_to_EMX_tech_mapping"][storage["name"]]}')
        if storage["name"] == "HydroPumpStorage":
            data.append(f'  type : PumpedHydroStor')
            data.append(f'  storage_behavior : CyclicStrategic')
            data.append(f'  charge_parameters_type : StorCapOpexFixed')
            data.append(f'  level_parameters_type : StorCap')
            data.append(f'  discharge_parameters_type: StorCap')
        elif storage["name"] == "Li-Ion_BESS":
            data.append(f'  type : BatteryStor')
            data.append(f'  storage_behavior : CyclicStrategic')
            data.append(f'  charge_parameters_type : StorCapOpexFixed')
            data.append(f'  level_parameters_type : StorCap') 
        data.append(f'  charge_capacity: 0')
        data.append(f'  charge_OPEX_variable: 0')
        for FOM_cost in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "PowerFixedOMCost", entity_byname = sto_by):
            FOM_val = get_value_from_db(FOM_cost, multiplier  = 1 / 1000, value_type= "list")
            data.append(f'  charge_OPEX_fixed : {FOM_val}')
        data.append(f'  level_capacity : 0')
        data.append(f'  level_OPEX_variable : 0')
        for FOM_cost in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "EnergyFixedOMCost", entity_byname = sto_by):
            FOM_val = get_value_from_db(FOM_cost, multiplier  = 1 / 1000, value_type= "list")
            data.append(f'  level_OPEX_fixed : {FOM_val}')
        data.append(f'  stored_resource : Power')

        #calc efficiency
        for Efficiency in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "StorageChargeEff", entity_byname = sto_by):
            cha_eff = get_value_from_db(Efficiency)
        data.append(f'  input:')
        data.append(f'    Power : {1 / cha_eff}')

        for Efficiency in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "StorageDischargeEff", entity_byname = sto_by):
            dis_eff = get_value_from_db(Efficiency)
        data.append(f'  output:')
        data.append(f'    Power : {dis_eff}')

        data.append(f'  additional_data : [StorageInvestmentData]')

        data.append(f'  invest_charge_capacity_CAPEX: 0') # kEUR per MW
        data.append(f'  invest_charge_capacity_max_installed: 100000') # MW
        data.append(f'  invest_charge_capacity_max_add: 5000') # MW
        data.append(f'  invest_charge_capacity_min_add: 0')
        data.append(f'  invest_charge_capacity_investment_mode: Continuous')
        data.append(f'  invest_charge_capacity_lifetime_mode: Rolling')
        for lifetime in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "Lifetime", entity_byname = sto_by):
            lifetime_val = get_value_from_db(lifetime)
            data.append(f'  invest_charge_capacity_lifetime: {lifetime_val}')
        for cap_cost in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "StorageEnergyCapitalCost", entity_byname = sto_by):
            cap_val = get_value_from_db(cap_cost, multiplier = 1000)
            data.append(f'  invest_level_CAPEX: {cap_val}')
        data.append(f'  invest_level_max_installed: 100000') # MWh
        data.append(f'  invest_level_max_add: 5000') # MWh
        data.append(f'  invest_level_min_add: 0')
        data.append(f'  invest_level_investment_mode: Continuous')
        data.append(f'  invest_level_lifetime_mode: Rolling')
        for lifetime in source_db.find_parameter_values(entity_class_name="Storage", parameter_definition_name = "Lifetime", entity_byname = sto_by):
            lifetime_val = get_value_from_db(lifetime)
            data.append(f'  invest_level_lifetime: {lifetime_val}')
        data.append("")
    return data

def create_regions(source_db):

    source_technology_list = []
    other_data = []
    norway_data = []
    added_norway = {"Technology": [], "Generator": [], "Storage": []}
    Norway = ["NO1", "NO2", "NO3", "NO4", "NO5"]

    #search for the technologies, currently excludes the technologies without CO2 content defined. It can be 0 as well.
    for technology in source_db.find_entities(entity_class_name="Technology"):
        if technology["name"] in settings["techs_excluded_from_mapping"]:
            continue
        co2_contents = []
        for t_g in source_db.find_entities(entity_class_name="Technology__Generator"):
            if t_g["entity_byname"][0] == technology["entity_byname"][0]:
                for CO2_intensity in source_db.find_parameter_values(entity_class_name="Generator", parameter_definition_name = "CO2Content", entity_byname = (t_g["entity_byname"][1],)):
                    val = get_value_from_db(CO2_intensity)
                    co2_contents.append(val)
        if co2_contents:
            source_technology_list.append(technology["name"])
    
    for node in source_db.find_entities(entity_class_name="Node"):
        if node["name"] in Norway:
            node_name =  "NO"
            if not norway_data:
                norway_data.append(f'default_{node_name}: &default_{node_name}')
            norway_data, added_norway = add_region_data(node, node_name, norway_data, source_db, source_technology_list, added_norway)
        else:
            if node["name"] not in settings["country_codes"].keys():
                continue
            node_name = settings["country_codes"][node["name"]]
            other_data.append(f'default_{node_name}: &default_{node_name}')
            other_data, added = add_region_data(node, other_data, source_db, source_technology_list, {"Technology": [], "Generator": [], "Storage": []})

    return other_data + norway_data

def add_region_data(node,  data, source_db, source_technology_list, added_before):
    extra_techs = settings["techs_outside_empire_to_regions"]
    if settings["techs"]:
        for node__technology in source_db.find_entities(entity_class_name="Node__Technology"):
            if node__technology["entity_byname"][0] == node["entity_byname"][0]:
                technology = node__technology["entity_byname"][1]
                if technology in source_technology_list:
                    if technology not in added_before["Technology"]:
                        added_before["Technology"].append(technology)
                        data.append(f'  {technology}_source:')
                        data.append(f'    <<: *{technology}_source')
    if settings["generators"]:
        for node__generator in source_db.find_entities(entity_class_name="Node__Generator"):
            if node__generator["entity_byname"][0] == node["entity_byname"][0]:
                generator = node__generator["entity_byname"][1]
                if generator not in added_before["Generator"]:
                    added_before["Generator"].append(generator) 
                    data.append(f'  {generator}:')
                    data.append(f'    <<: *{generator}')
                    #add special cases
    if settings["storages"]:
        for node__storage in source_db.find_entities(entity_class_name="Node__Storage"):
            if node__storage["entity_byname"][0] == node["entity_byname"][0]:
                storage = node__storage["entity_byname"][1]
                if storage not in added_before["Storage"]:
                    added_before["Storage"].append(storage)
                    data.append(f'  {storage}:')
                    data.append(f'    <<: *{storage}')
                    #add special cases

    for e_t in extra_techs:
        if e_t not in added_before["Technology"]:
            added_before["Technology"].append(e_t)
            data.append(f'  {e_t}:')
            data.append(f'    <<: *{e_t}')

    return data, added_before

def create_global_data(source_db):
    data = []
    #add global data if needed

    if settings["CO2_cap"]:
        for cap in source_db.find_parameter_values(entity_class_name="General", parameter_definition_name = "CO2Cap"):
            cap_val = get_value_from_db(cap, value_type= "list")
            data.append(f'emission_limit:')
            data.append(f'  CO2 : {cap_val}')
    if settings["CO2_price"]:
        for price in source_db.find_parameter_values(entity_class_name="General", parameter_definition_name = "CO2Price"):
            price_val = get_value_from_db(price, multiplier = 1/1000, value_type= "list")
            data.append(f'emission_price:')
            data.append(f'  CO2 : {price_val}')

    return data

def write_yml(data, path, override = False):
    if override:
        with open(path, 'w') as file:
            for line in data:
                file.write(f"{line}\n")
    else:
        #Get the existing lines and append them to the end of the new file, avoiding duplicates
        existing_lines = list()
        if path.exists():
            with open(path, 'r') as file:
                for line in file:
                    existing_lines.append(line)
        with open(path, 'w') as file:
            for line in data:
                file.write(f"{line}\n")
            
            exists = False

            for line in existing_lines:
                if exists:
                    if line[:1].isspace() or line.startswith("#"):
                        continue
                    else:
                        exists = False
                if not exists:
                    if not line[:1].isspace() and not line.startswith("#"):
                        start = line.split(":")[0]
                        for old_line in data:
                            if old_line.startswith(start):
                                exists = True
                if not exists:
                    if not line.startswith("#"):
                        file.write(f"{line}")


def multiply_all_datatypes(param_value, factor):
    if isinstance(param_value, api.Map):
        for i, val in enumerate(param_value.values):
            param_value.values[i] = round(float(val) * factor,6)
        return param_value
    elif isinstance(param_value, float):
        return round(param_value * factor)
    else:
        return param_value

def get_value_from_db(param, value_type = "original" ,multiplier = None):
    val = api.from_database(param["value"], param["type"])
    if multiplier:
        val = multiply_all_datatypes(val, multiplier)
    if value_type == "single_value":
        if isinstance(val, api.Map):
            val = float(val.values[0])
        elif isinstance(val, api.Array):
            val = float(val[0])
        elif isinstance(val, float):
            val = val
    elif value_type == "list":
        if isinstance(val, api.Map):
            val = [float(x) for x in val.values]
        elif isinstance(val, api.Array):
            val = [float(x) for x in val]
        else:
            print("Value type is set as list, but the retrieved value is not a list or map.")
            sys.exit(-1)

    return val

if __name__ == "__main__":
    
    if len(sys.argv) > 1:
        settings_file = sys.argv[1]
    else:
        print("Please provide the settings file as the first argument.")
        sys.exit(-1)
    if len(sys.argv) > 2:
        url_db_in = sys.argv[2]
    else:
        print("Please provide the database URL as the second argument.")
        sys.exit(-1)
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as file:
            settings = yaml.safe_load(file)
    main()
