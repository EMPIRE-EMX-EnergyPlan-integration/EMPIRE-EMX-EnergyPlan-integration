import os
import sys
import yaml
import spinedb_api as api
from sqlalchemy.exc import DBAPIError
from spinedb_api.exception import NothingToCommit


def add_transport_data(target_db, old_alts, target_name, params, years_in_use, scenarios_in_use):
    new_alts = []
    for param in params:
        #scenario creation loop
        new_alt = param["alternative_name"]
        if scenarios_in_use and new_alt not in scenarios_in_use:
            continue
        if any(new_alt in s["name"] for s in old_alts):
            continue
        for old_alt in old_alts:
            new_alt_name = old_alt["name"] + "-" + new_alt
            if new_alt_name not in new_alts:
                new_alts.append(new_alt_name)
                target_db.add_alternative_item(name=new_alt_name)
        
            #value creation loop
            value_map = api.from_database(param["value"], param["type"])
            out_map = dict()
            counter = 0
            indexes = list()
            values = list()
            for year_in_use in years_in_use:
                found = False
                inter_indexes = list()
                inter_vals = list()
                counter += 1
                for i, year in enumerate(value_map.indexes):
                    if int(year) == year_in_use:
                        found = True
                        indexes.append(str(counter))
                        values.append(float(value_map.values[i]) * 1000000)    # TWh to MWh
                    else:
                        inter_indexes.append(float(year))
                        inter_vals.append(float(value_map.values[i]) * 1000000)    # TWh to MWh
                #interpolate between years if needed
                if not found:
                    if float(year_in_use) < inter_indexes[0] or float(year_in_use) > inter_indexes[-1]:
                        exit("The year in use is before the first year or after the last. Would require extrapolation")
                    else:
                        for index, key in enumerate(inter_indexes):
                            if float(year_in_use) < key:
                                dist_to_last = float(year_in_use) - last_key
                                dist_to_next = key - float(year_in_use)
                                slope = (inter_vals[index] - last_val) / (dist_to_next + dist_to_last)
                                indexes.append(str(counter))
                                values.append(last_val + slope * dist_to_last)
                                break
                            else:
                                last_key = key
                                last_val = inter_vals[index]
            
            target_old_val = target_db.get_parameter_value_item(entity_class_name='Node', 
                                                            parameter_definition_name=target_name,
                                                            entity_byname=param["entity_byname"],
                                                            alternative_name = old_alt["name"])
            if target_old_val:
                old_value_map = api.from_database(target_old_val["value"], target_old_val["type"])
                new_values = list()
                if len(values) != len(old_value_map.values):
                    print("The number of years in the empire database does not match with the years in use")
                    exit(-1)
                for i, val in enumerate(old_value_map.values):
                    new_values.append(float(val) + values[i])
                out_map = api.Map(indexes, new_values)
                p_value, p_type = api.to_database(out_map)
                target_db.add_update_parameter_value_item(entity_class_name="Node",
                                                    parameter_definition_name=target_name,
                                                    entity_byname=param["entity_byname"],
                                                    alternative_name=new_alt_name,
                                                    value=p_value,
                                                    type=p_type)
    return target_db

def main():
    if sys.argv[3]:
        if os.path.exists(sys.argv[3]):
            with open(sys.argv[3], 'r') as file:
                settings_file = yaml.safe_load(file)
        else:
            exit("The third argument is not a valid path")
    else:
        exit("Please provide a years_in_use.yaml file with the years in use as the third argument.")
    years_in_use = settings_file["years_in_use"]
    scenarios_in_use = settings_file["scenarios_in_use"]
    # transform spine db with backbone data (source db) into a spine db that already has the ines structure (target_db)
    with api.DatabaseMapping(url_db_in) as source_db:
        with api.DatabaseMapping(url_db_out) as target_db:

            electricity = source_db.get_parameter_value_items(entity_class_name='Country', parameter_definition_name='Electricity')
            Hydrogen = source_db.get_parameter_value_items(entity_class_name='Country', parameter_definition_name='Hydrogen')
            Natural_gas = source_db.get_parameter_value_items(entity_class_name='Country', parameter_definition_name='Natural gas')
            Industrial_demand = source_db.get_parameter_value_items(entity_class_name='Country', parameter_definition_name='Industrial_demand')
            base_year_industrial_demands = source_db.get_parameter_value_items(entity_class_name='Country', 
                                                                              parameter_definition_name='Industrial_demand', 
                                                                              alternative_name="Base year")
            #add transport demand data
            old_alts = target_db.get_alternative_items()
            target_db = add_transport_data(target_db, old_alts, "ElectricityDemand", electricity, years_in_use, scenarios_in_use)
            target_db = add_transport_data(target_db, old_alts, "HydrogenDemand", Hydrogen, years_in_use, scenarios_in_use)
            target_db = add_transport_data( target_db, old_alts, "NaturalGasDemand", Natural_gas, years_in_use, scenarios_in_use)
            
            #add industrial demand data
            old_alts = target_db.get_alternative_items()
            new_alts = []
            for param in Industrial_demand:
                if param["alternative_name"] == "Base year":
                    continue
                #scenario creation loop
                new_alt = param["alternative_name"]
                if scenarios_in_use and new_alt not in scenarios_in_use:
                    continue
                exists = False
                done = False
                if any(new_alt in s["name"] for s in old_alts):
                    exists = True             
                for old_alt in old_alts:
                    if exists: 
                        if new_alt in old_alt["name"]:
                            new_alt_name = old_alt["name"]
                        else:
                            continue
                    else:
                        new_alt_name = old_alt["name"] + "-" + new_alt
                        if new_alt_name not in new_alts:
                            new_alts.append(new_alt_name)
                            target_db.add_alternative_item(name=new_alt_name)
                    #value creation loop
                    value_map = api.from_database(param["value"], param["type"])
                    out_map = dict()
                    fuel_use = dict(dict())
                    for i, fuel in enumerate(value_map.indexes):
                        if fuel == "Natural gas" or fuel == "Electricity" or fuel == "Hydrogen":
                            if fuel == "Natural gas":
                                definition_name = "NaturalGasDemand"
                            elif fuel == "Electricity": 
                                definition_name = "ElectricAnnualDemand"
                            elif fuel == "Hydrogen":
                                definition_name = "HydrogenDemand"
                            else:
                                continue
                            #get old value for summing
                            target_old_val = target_db.get_parameter_value_item(entity_class_name='Node', 
                                                                        parameter_definition_name=definition_name,
                                                                        entity_byname=param["entity_byname"],
                                                                        alternative_name = old_alt["name"])
                            if target_old_val:
                                old_value_map = api.from_database(target_old_val["value"], target_old_val["type"])
                                if len(years_in_use) != len(old_value_map.values):
                                    print("The number of years in the empire database does not match with the years in use")
                                    exit(-1)
                                year_use = dict()
                                indexes = list()
                                counter = 0
                                for index, year_in_use in enumerate(years_in_use):
                                    inter_year_use = dict()
                                    found = False
                                    counter += 1
                                    for j, year in enumerate(value_map.values[i].indexes):
                                            indexes.append(str(counter))
                                            vals = list()
                                            for k, sector in enumerate(value_map.values[i].values[j].indexes):
                                                vals.append(float(value_map.values[i].values[j].values[k] * 277.78))    # TJ to MWh
                                            if int(year) == year_in_use:
                                                found = True
                                                year_use[str(counter)] = sum(vals) + float(old_value_map.values[index])
                                            else:
                                                inter_year_use[float(year)] = sum(vals)
                                    #interpolate between years if needed
                                    if not found:
                                        #special case, if the value is between the base year and the first source year
                                        if float(year_in_use) < list(inter_year_use.keys())[0]:
                                            for base_year in base_year_industrial_demands:
                                                if base_year["entity_byname"] == param["entity_byname"]:
                                                    base_year_map = api.from_database(base_year["value"], base_year["type"])
                                                    base_year_values = base_year_map.values[i].values[0].values
                                                    if float(year_in_use) < float(base_year_map.values[0].indexes[0]):
                                                        exit("The year in use is before the base year. Would require extrapolation")
                                                    elif int(year_in_use) ==  int(base_year_map.values[0].indexes[0]):
                                                        year_use[str(counter)] = sum(base_year_values) + float(old_value_map.values[index])
                                                    else:
                                                        last_val = sum(base_year_values)
                                                        last_key = float(base_year_map.values[0].indexes[0])
                                                        #calulate the slope
                                                        key = float(list(inter_year_use.keys())[0])
                                                        dist_to_last = float(year_in_use) - last_key
                                                        dist_to_next = key - float(year_in_use)
                                                        slope = (inter_year_use[key] - last_val) / (dist_to_next + dist_to_last)
                                                        year_use[str(counter)] = last_val + slope * dist_to_last + float(old_value_map.values[index])
                                                    break
                                        else:
                                            for key in inter_year_use.keys():
                                                if float(year_in_use) < key:
                                                    dist_to_last = float(year_in_use) - float(last_key)
                                                    dist_to_next = float(key) - float(year_in_use)
                                                    slope = (inter_year_use[key] - last_val) / (dist_to_next + dist_to_last)
                                                    year_use[str(counter)] = last_val + slope * dist_to_last + float(old_value_map.values[index])
                                                    break
                                                else:
                                                    last_key = key
                                                    last_val = inter_year_use[key]

                            fuel_use[fuel] = year_use
                    for fuel, val in fuel_use.items():
                        out_map = api.Map(list(val.keys()), list(val.values()))
                        p_value, p_type = api.to_database(out_map)
                        if fuel == "Natural gas":
                            definition_name = "NaturalGasDemand"
                        elif fuel == "Electricity": 
                            definition_name = "ElectricAnnualDemand"
                        elif fuel == "Hydrogen":
                            definition_name = "HydrogenDemand"
                        else:
                            continue

                        target_db.add_update_parameter_value_item(entity_class_name="Node",
                                                            parameter_definition_name=definition_name,
                                                            entity_byname=param["entity_byname"],
                                                            alternative_name=new_alt_name,
                                                            value=p_value,
                                                            type=p_type)
            try:
                target_db.commit_session("Added entities")
            except NothingToCommit:
                pass
            except DBAPIError as e:
                print("failed to commit entities and entity_alternatives")

if __name__ == "__main__":
    developer_mode = False
    url_db_in = sys.argv[1]
    url_db_out = sys.argv[2]
    main()