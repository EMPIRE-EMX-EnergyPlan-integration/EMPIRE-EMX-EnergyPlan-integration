
using CSV
using DataFrames
using Dates

## Function definition
function enumerate_column!(df::DataFrame, col::Symbol)
    # Create a dictionary to map unique values to indices
    val_dict = Dict{eltype(df[!, col]), Int}()

    # Assign a unique index to each unique value in the order of appearance
    for val in df[!, col]
        if !haskey(val_dict, val)
            val_dict[val] = length(val_dict) + 1
        end
    end

    # Replace the column values with their corresponding indices
    df[!, col] = [val_dict[val] for val in df[!, col]]

    return df
end

function write_ts_csv(df, folder, reg, node_type, var_type, ts_meta)
    path = joinpath(folder,"$(node_type)/$(var_type)")
    mkpath(path)
    filename = "$(reg).csv"
    temp_csv = "temp_$(reg).csv"
    # Write CSV content to a temporary file
    CSV.write(temp_csv, df)
    # Write metadata + CSV content to final file
    open(joinpath(path,filename), "w") do io
        write(io, "#metadata: $(var_type) for $(reg)\n")
        write(io, "#metadata: $(ts_meta[1]) \n")
        write(io, "#metadata:  $(ts_meta[2]) \n")
        write(io, "#metadata: Unit: $(ts_meta[3]) \n")
        # Append the CSV content
        open(temp_csv, "r") do temp_io
            write(io, read(temp_io, String))
        end
    end
    # Delete the temporary file
    rm(temp_csv)
end

function process_h2_demand(df::DataFrame)
    h2_use_cols = ["Hydrogen burned for power and heat [ton]",
    "Hydrogen used for steel [ton]",
    "Hydrogen used for cement [ton]",
    "Hydrogen used for ammonia [ton]",
    "Hydrogen used for oil refining [ton]",
    "Hydrogen used for transport [ton]",
    ]
    df.val .= sum.(eachrow(df[!, h2_use_cols])) # sum all the columns to get total H2 demand
    select!(df, [:Period, :Scenario, :Season, :Hour, :val]) # remove unnecessary columns
    # for each period and scenario, replace val by the average of the values in the period and scenario while maintaining the season and hours
    for (period,scenario) in unique(zip(df.Period, df.Scenario))
        sub_df= filter(x-> x.Period == period && x.Scenario == scenario, df)
        avg_val = DataFrames.mean(sub_df.val)
        df[df.Period .== period .&& df.Scenario .== scenario,:val] .= avg_val
    end
    return df
end

only_EMPIRE_data = true # Set to false if using atlite data for RES
number_sp = 4 #number of strategic periods
scenario_nb = 1
#only_EMPIRE_data = false # Set to false if using atlite data for RES

case_folder = "" # Case folder inside EMPIRE_res_folder

EMPIRE_res_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/$case_folder"# Folder containing the EMPIRE results and input data
case_name = "Test"
if length(ARGS) > 0
    tab_files_folder = ARGS[1]
else
    tab_files_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/Tab_Files_full_model_$(case_name)"
end
if length(ARGS) > 1
    scenario_csv_files_folder = ARGS[2]
else
    scenario_csv_files_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/Tab_Files_full_model_$(case_name)"
end

if length(ARGS) > 2
    results_folder = ARGS[3]
else
    results_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/$case_folder"
end
#tab_files_folder = Case_Generation/InputOutput/$(EMPIRE_res_folder)/Tab_Files_full_model_$(case_name)
#tab_files_folder = "../../InternalEMPIRE/Data handler/full_model/Tab_Files_full_model"
#scenario_csv_files_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/Tab_Files_full_model_$(case_name)"
#scenario_csv_files_folder = "../../InternalEMPIRE/Data handler/full_model/ScenarioData"
#results_folder = "Case_Generation/InputOutput/$(EMPIRE_res_folder)/$case_folder"
#results_folder = "../EMPIRE_Results"
out_folder = "$(case_name)/Default/Timeseries"
region_file = "InputOutput/Region_Mapping.csv"

# Define the power distribution across household and industry for each EMPIRE region
# These values are based on the IEA statistics for the Nordic countries except Norway where SSB data is used
Power_distribution = Dict( # Household corresponds to residential and commertcial and public services in IEA stats
    #"Norway" => Dict("Household" => 0.58, "Industry" => 0.42),
    "Sweden" => Dict("Household" => 0.605, "Industry" => 0.395),
    "Finland" => Dict("Household" => 0.535, "Industry" => 0.465),
    "Denmark" => Dict("Household" => 0.677, "Industry" => 0.323),
    "NO1" => Dict("Household" => 0.67, "Industry" => 0.33),
    "NO2" => Dict("Household" => 0.42, "Industry" => 0.58),
    "NO3" => Dict("Household" => 0.59, "Industry" => 0.41),
    "NO4" => Dict("Household" => 0.63, "Industry" => 0.37),
    "NO5" => Dict("Household" => 0.34, "Industry" => 0.66),
)

# Mapping regions from EMX to EMPIRE
regions = CSV.read(region_file, DataFrame)
EMX_to_EMPIRE_dict = Dict(row.Mapped_Area_Code => row.Empire_zone for row in eachrow(regions))
Empire_zones = keys(Power_distribution)
Hydro_regions = ["Sweden", "NO1", "NO2", "NO3", "NO4", "NO5"]
ISO_codes = Dict("Sweden" => "SE", "Finland" => "FI", "Denmark" => "DK", "NO1" => "NO1", "NO2" => "NO2", "NO3" => "NO3", "NO4" => "NO4", "NO5" => "NO5")

column_rename = Dict(
    "Period" => "sp",
    "Scenario" => "scp",
    "Season" => "rp",
    "Hour" => "op",
)

season_start = Dict(
    "winter" => 1,
    "spring" => 169,
    "summer" => 337,
    "autumn" => 505,
    "peak1" => 673,
    "peak2" => 697,
    )
season_end= Dict(
    "winter" => 168,
    "spring" => 336,
    "summer" => 504,
    "autumn" => 672,
    "peak1" => 696,
    "peak2" => 720,
)

# Check that allocation key sum to 1 for the EMPIRE regions
if any(r->!isapprox(sum(filter(x-> x.Empire_zone == r ,regions)[!,"Population_Key"]), 1;atol=0.1), Empire_zones)
    for r in keys(Power_distribution)
    println(r," :",sum(filter(x-> x.Empire_zone == r ,regions)[!,"Population_Key"]))
    end
    throw(ArgumentError("The sum of Population_Key for EMPIRE areas must be equal to 1."))
end
if any(r->!isapprox(sum(filter(x-> x.Empire_zone == r ,regions)[!,"Industry_Allocation"]), 1;atol=0.1), Empire_zones)
    for r in keys(Power_distribution)
    println(r," :",sum(filter(x-> x.Empire_zone == r ,regions)[!,"Industry_Allocation"]))
    end
    throw(ArgumentError("The sum of Industry_Allocation for EMPIRE areas must be equal to 1."))
end
if any(r->!isapprox(sum(filter(x-> x.Empire_zone == r ,regions)[!,"Hydro_Key"]), 1;atol=0.1), Hydro_regions)
    for r in Hydro_regions
    println(r," :",sum(filter(x-> x.Empire_zone == r ,regions)[!,"Hydro_Key"]))
    end
    throw(ArgumentError("The sum of Hydro_Key for EMPIRE areas must be equal to 1."))
end

if only_EMPIRE_data
    ts_files = Dict(
    "El_demand" => "$(tab_files_folder)/Stochastic_ElectricLoadRaw.tab",
    "Hydro_run-of-the-river" => "$(tab_files_folder)/Stochastic_StochasticAvailability.tab",
    "Hydro_regulated" => "$(tab_files_folder)/Stochastic_HydroGenMaxSeasonalProduction.tab",
    "Wind_onshore" => "$(tab_files_folder)/Stochastic_StochasticAvailability.tab",
    "Wind_offshore_floating" => "$(tab_files_folder)/Stochastic_StochasticAvailability.tab",
    "Wind_offshore_grounded" => "$(tab_files_folder)/Stochastic_StochasticAvailability.tab",
    "Solar" => "$(tab_files_folder)/Stochastic_StochasticAvailability.tab",
    "H2_demand" => "$(results_folder)/results_hydrogen_use.csv",
    )

    ts_type_EMPIRE = Dict(
    "Hydro_run-of-the-river" => "Hydrorun-of-the-river",
    "Hydro_regulated" => "Hydroregulated",
    "Wind_onshore" => "Windonshore",
    "Wind_offshore_floating" => "Windoffshorefloating",
    "Wind_offshore_grounded" => "Windoffshoregrounded",
    "Solar" => "Solar",
    )

    for (ts_type,ts_file) ∈ ts_files
        #Read timeserie file
        ts = CSV.read(ts_file, DataFrame)
        if "IntermitentGenerators" ∈ names(ts)
            filter!(x-> x.IntermitentGenerators == ts_type_EMPIRE[ts_type], ts)
        end
        for country ∈ Empire_zones
            df = copy(filter(x-> x.Node == country, ts))
            if isempty(df)
                #copy the values for another country
                tmp_df= copy(filter(x-> x.Node == "Sweden", ts))
                tmp_df[!,names(df)[end]] .= 0.0
                tmp_df[!,"Node"] .= country
                df = copy(tmp_df)
            end
            if ts_type == "H2_demand"
                df = process_h2_demand(df)
            elseif ts_type == "Hydro_regulated"
                rename!(df, Dict(names(df)[end] => "val"))
                rename!(df, Dict("Operationalhour" => "Hour"))
                # if Hydro_regulated, sum the values for each period, scenario and season abd assign it to the first hour of the season and change the rest to 0
                for (period, scenario, season) in unique(zip(df.Period, df.Scenario, df.Season))
                    sub_df = filter(x-> x.Period == period && x.Scenario == scenario && x.Season == season, df)
                    val = sum(sub_df.val)
                    df[df.Period .== period .&& df.Scenario .== scenario .&& df.Season .== season,:val] .= val
                    # Set all other hours to 0
                    df[df.Period .== period .&& df.Scenario .== scenario .&& df.Season .== season .&& df.Hour .!= sub_df.Hour[1],:val] .= 0.0
                end

            else
                rename!(df, Dict(names(df)[end] => "val"))
                rename!(df, Dict("Operationalhour" => "Hour"))
                # Add season column if it does not exist
                if "Season" ∉ names(df)
                    # Add Season column based on Hour
                    tmp = String[]
                    for hour in df.Hour
                        for season in keys(season_start)
                            if hour in season_start[season]:season_end[season]
                                push!(tmp, season)
                                break
                            end
                        end
                    end
                    df.Season = tmp
                end
            end

            enumerate_column!(df, :Period)
            enumerate_column!(df, :Scenario)
            enumerate_column!(df, :Season)

            rename!(df, column_rename)
            select!(df, [:sp, :rp, :scp, :op, :val])

            filter!(df-> df.sp .<= number_sp, df)

            for reg in unique(filter(x-> x.Empire_zone == country, regions)[!,"Mapped_Area_Code"])
                df_reg= copy(df)
                if ts_type == "El_demand"
                    node_type = "El_demand"
                    var_type = "capacity"
                    reg_pop_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Population_Key"])
                    reg_ind_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Industry_Allocation"])
                    factor = (Power_distribution[country]["Household"] * reg_pop_key + Power_distribution[country]["Industry"] * reg_ind_key)
                    df_reg.val = df_reg.val * factor
                elseif ts_type == "H2_demand"
                    node_type = "H2_demand"
                    var_type = "capacity"
                    reg_ind_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Industry_Allocation"])
                    factor = reg_ind_key
                    df_reg.val = df_reg.val * reg_ind_key
                elseif ts_type == "Hydro_regulated"
                    node_type = ts_type
                    var_type = "level_inflow"
                    hydro_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Hydro_Key"])
                    factor = hydro_key
                    df_reg.val = df_reg.val * hydro_key
                else
                    node_type = ts_type
                    var_type = "profile"
                    factor = 0
                end

                ts_meta = Dict(
                "El_demand" => ("From EMPIRE inputs $(ts_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Electricity demand in the node","MWh"),
                "Hydro_run-of-the-river" => ("From EMPIRE inputs $(ts_file), not distributed","Availability factor of run of river","N/A"),
                "Hydro_regulated" => ("From EMPIRE inputs $(ts_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Energy equivalent amount of water that can be used in each representative period (RP), set at the beginning of the RP","MWh"),
                "Wind_onshore" => ("From EMPIRE inputs $(ts_file), not distributed","Availability factor of onshore wind","N/A"),
                "Wind_offshore_floating" => ("From EMPIRE inputs $(ts_file), not distributed","Availability factor of offshore wind grounded","N/A"),
                "Wind_offshore_grounded" => ("From EMPIRE inputs $(ts_file), not distributed","Availability factor of offshore wind floating","N/A"),
                "Solar" => ("From EMPIRE inputs $(ts_file), not distributed","Availability factor of solar","N/A"),
                "H2_demand" => ("From EMPIRE results $(ts_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Total Hydrogen use in the node","ton"),
                )

                # round all values to 3 decimals
                df_reg.val = round.(df_reg.val; digits=3)
                write_ts_csv(df_reg, out_folder, reg, node_type, var_type, ts_meta[ts_type])
            end
        end
    end
else
    ts_files = Dict(
    "El_demand" => "$(scenario_csv_files_folder)/electricload.csv",
    "Hydro_run-of-the-river" => "$(scenario_csv_files_folder)/hydroror.csv",
    "Hydro_regulated" => "$(scenario_csv_files_folder)/hydroseasonal.csv",
    "Wind_onshore" => "$(scenario_csv_files_folder)/windonshore.csv",
    "Wind_offshore_floating" => "$(scenario_csv_files_folder)/windoffshore.csv",
    "Wind_offshore_grounded" => "$(scenario_csv_files_folder)/windoffshore.csv",
    "Solar" => "$(scenario_csv_files_folder)/solar.csv",
    "H2_demand" => "$(results_folder)/results_hydrogen_use.csv",
    )

    EMPIRE_ts_sampling_key_file = "$(scenario_csv_files_folder)/sampling_key.csv"

    # read EMPIRE sampling key
    EMPIRE_ts_sampling_key = CSV.read(EMPIRE_ts_sampling_key_file, DataFrame)

    #RES capacity factor timeseries
    for (ts_type,ts_file) ∈ ts_files
        #Read timeserie file
        ts = CSV.read(ts_file, DataFrame)
        if ts_type != "H2_demand"
            # check if data existy for all countries and if not add 0 and print warning
            for country ∈ Empire_zones
                if ISO_codes[country] ∉ names(ts)
                    # If country is one of the NO regions, check if there is data for NO
                    if country in ["NO1", "NO2", "NO3", "NO4", "NO5"]
                        if "NO" ∉ names(ts)
                            # If Norway is not in the timeseries, add a column with 0 values
                            ts[!,ISO_codes["Norway"]] = zeros(Float64, nrow(ts))
                            println("Warning: No data for Norway in $(ts_type) timeseries, adding 0 values.")
                        else
                            # If Norway is in the timeseries, copy the data to the NO region
                            ts[!,ISO_codes[country]] = ts[!,"NO"]
                            println("Warning: No data for $(country) in $(ts_type) timeseries, copying data from Norway.")
                        end
                    else
                        # If the country is not in the timeseries, add a column with 0 values
                        ts[!,ISO_codes[country]] = zeros(Float64, nrow(ts))
                        println("Warning: No data for $(country) in $(ts_type) timeseries, adding 0 values.")
                    end
                end
            end
            #Use sampling key to correctly sample from historical data
            select!(ts, push!([Symbol(x) for x in values(ISO_codes)],:time))
            # convert column to DateTime
            ts.time = DateTime.(ts.time, "dd/mm/yyyy HH:MM")
        else
            # For H2 demand, no sampling is needed, we select correct regions
            filter!(x-> x.Node in Empire_zones, ts)
        end

        for country in Empire_zones
            # Copy file to serve as basis for regional timeserie
            if ts_type == "H2_demand"
                df = copy(filter(x-> x.Node == country, ts))
                df = process_h2_demand(df)
            elseif ts_type == "Hydro_regulated"
                df = copy(EMPIRE_ts_sampling_key)
                df.val .= 0.0
                filter!(x-> x.Season != "peak", df)
                prev_Scenario = nothing

                for row ∈ eachrow(copy(df)) #use a copy since we change df in the loop
                    if row.Scenario != prev_Scenario
                        # reset counter if scenario changes
                        cnt = 0
                        prev_Scenario = row.Scenario
                    end
                    if row.Season == "peak1" || row.Season == "peak2"
                        p_length = 24
                        val = sum(filter(x-> x.time >= (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour-p_length/2)) &&
                            x.time < (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour+p_length/2)), ts)[!, ISO_codes[country]])
                        vals = append!([val],zeros(Float64, p_length-1))
                        # duplicate row for each values in vals, adding the value and updating Hour to count up from cnt
                        for i in eachindex(vals)
                            push!(df, merge(row, (Hour = cnt + i, val= vals[i],)))
                        end
                        cnt+= p_length
                    else
                        # define length of period
                        p_length = 24*7
                        # find the values corresponding to the current row in historical data
                        val = sum(filter(x-> x.time >= (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour-p_length/2)) &&
                            x.time < (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour+p_length/2)), ts)[!, ISO_codes[country]])
                        vals = append!([val],zeros(Float64, p_length-1))
                        for i in eachindex(vals)
                            push!(df, merge(row, (Hour = cnt + i, val= vals[i],)))
                        end
                        # update the counter
                        cnt+= p_length
                    end
                    delete!(df, 1)
                end
            else
                df = copy(EMPIRE_ts_sampling_key)
                df.val .= 0.0
                # remove the rows with peak, they are used internally in EMPIRE, we use peak1 and peak2
                filter!(x-> x.Season != "peak", df)
                prev_Scenario = nothing

                for row ∈ eachrow(copy(df)) #use a copy since we change df in the loop
                    if row.Scenario != prev_Scenario
                        # reset counter if scenario changes
                        cnt = 0
                        prev_Scenario = row.Scenario
                    end
                    if row.Season == "peak1" || row.Season == "peak2"
                        p_length = 24
                        vals = filter(x-> x.time >= (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour-p_length/2)) &&
                        x.time < (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour+p_length/2)), ts)[!, ISO_codes[country]]
                        # duplicate row for each values in vals, adding the value and updating Hour to count up from cnt
                        for i in eachindex(vals)
                            push!(df, merge(row, (Hour = cnt + i, val= vals[i],)))
                        end
                        cnt+= p_length
                    else
                        # define length of period
                        p_length = 24*7
                        # find the values corresponding to the current row in historical data
                        vals = filter(x-> x.time >= (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour)) &&
                            x.time < (DateTime(row.Year, 1,1,0,0,0) + Hour(row.Hour+p_length)), ts)[!, ISO_codes[country]]
                        # duplicate row for each values in vals, adding the value and updating Hour to count up from cnt
                        for i in eachindex(vals)
                            push!(df, merge(row, (Hour = cnt + i, val= vals[i],)))
                        end
                        # update the counter
                        cnt+= p_length
                    end
                    delete!(df, 1)
                end
            end

            enumerate_column!(df, :Period)
            enumerate_column!(df, :Scenario)
            enumerate_column!(df, :Season)

            rename!(df, column_rename)
            select!(df, [:sp, :rp, :scp, :op, :val])

            filter!(df-> df.sp .<= number_sp, df)

            for reg in unique(filter(x-> x.Empire_zone == country, regions)[!,"Mapped_Area_Code"])
                df_reg= copy(df)
                if ts_type == "El_demand"
                    node_type = "El_demand"
                    var_type = "capacity"
                    reg_pop_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Population_Key"])
                    reg_ind_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Industry_Allocation"])
                    factor = (Power_distribution[country]["Household"] * reg_pop_key + Power_distribution[country]["Industry"] * reg_ind_key)
                    df_reg.val = df_reg.val * factor
                elseif ts_type == "H2_demand"
                    node_type = "H2_demand"
                    var_type = "capacity"
                    reg_ind_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Industry_Allocation"])
                    factor = reg_ind_key
                    df_reg.val = df_reg.val * reg_ind_key
                elseif ts_type == "Hydro_regulated"
                    node_type = ts_type
                    var_type = "level_inflow"
                    hydro_key = sum(filter(x-> x.Mapped_Area_Code == reg ,regions)[!,"Hydro_Key"])
                    factor = hydro_key
                    df_reg.val = df_reg.val * hydro_key
                else
                    node_type = ts_type
                    var_type = "profile"
                    factor = 0
                end

                ts_meta = Dict(
                "El_demand" => ("From EMPIRE unsampled inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Electricity demand in the node","MWh"),
                "Hydro_run-of-the-river" => ("From inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), not distributed","Availability factor of run of river","N/A"),
                "Hydro_regulated" => ("From EMPIRE unsampled inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Energy equivalent amount of water that can be used in each representative period (RP), set at the beginning of the RP","MWh"),
                "Wind_onshore" => ("From inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), not distributed","Availability factor of onshore wind","N/A"),
                "Wind_offshore_floating" => ("From inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), not distributed","Availability factor of offshore wind grounded","N/A"),
                "Wind_offshore_grounded" => ("From inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), not distributed","Availability factor of offshore wind floating","N/A"),
                "Solar" => ("From inputs $(ts_file), sampled using $(EMPIRE_ts_sampling_key_file), not distributed","Availability factor of solar","N/A"),
                "H2_demand" => ("From EMPIRE results $(ts_file), distributed from $(country) to our spatial resolution with a factor $(factor)","Total Hydrogen use in the node","ton"),
                )

                df_reg.val = round.(df_reg.val; digits=3) # round all values to 3 decimals
                write_ts_csv(df_reg, out_folder, reg, node_type, var_type,ts_meta[ts_type])
            end
        end
    end
end

# process data for rest areas
ts_files = Dict(
    "H2_demand_rest" => "$(results_folder)/results_hydrogen_pipeline_operational.csv",
    "Power_demand_rest" => "$(results_folder)/results_elec_transmission_operational.csv",
)

for (ts_type,ts_file) ∈ ts_files
    #Read timeserie file
    ts = CSV.read(ts_file, DataFrame)

    if ts_type=="H2_demand_rest"
        # find flows in and out of rest areas
        df_out = filter(x-> x["To node"] ∈ Empire_zones && !(x["From node"] ∈ Empire_zones), ts)
        df_in = filter(x-> x["From node"] ∈ Empire_zones && !(x["To node"] ∈ Empire_zones), ts)
        #groupby and merge by Period, Season, Scenario, GasScenario and sum the flows
        df_in = combine(groupby(df_in, ["Period", "Season", "Scenario", "GasScenario", "Hour"]), "Hydrogen sent [ton]" => sum => "Hydrogen sent [ton]_in")
        df_out = combine(groupby(df_out, ["Period", "Season", "Scenario", "GasScenario", "Hour"]), "Hydrogen sent [ton]" => sum => "Hydrogen sent [ton]_out")
        df = innerjoin(df_in, df_out, on=["Period", "Season", "Scenario", "GasScenario", "Hour"], makeunique=true)
        df.val .= df[!,"Hydrogen sent [ton]_in"] .- df[!,"Hydrogen sent [ton]_out"]
        node_type = "H2"
    elseif ts_type=="Power_demand_rest"
        df_out = filter(x-> x["ToNode"] ∈ Empire_zones && !(x["FromNode"] ∈ Empire_zones), ts)
        df_in = filter(x-> x["FromNode"] ∈ Empire_zones && !(x["ToNode"] ∈ Empire_zones), ts)
        #groupby and merge by Period, Season, Scenario, GasScenario and sum the flows
        df_in = combine(groupby(df_in, ["Period", "Season", "Scenario", "GasScenario", "Hour"]), "TransmissionReceived_MW" => sum => "TransmissionReceived_MW_in")
        df_out = combine(groupby(df_out, ["Period", "Season", "Scenario", "GasScenario", "Hour"]), "TransmissionReceived_MW" => sum => "TransmissionReceived_MW_out")
        df = innerjoin(df_in, df_out, on=["Period", "Season", "Scenario", "GasScenario", "Hour"], makeunique=true)
        df.val .= df[!,"TransmissionReceived_MW_in"] .- df[!,"TransmissionReceived_MW_out"]
        node_type = "El"
    end
    ts_meta = Dict(
        "H2_demand_rest" => ("From EMPIRE results $(ts_file), based on pipeline flow in and out of our regional scope","Total Hydrogen flow in the Rest region from geographical scope","ton"),
        "Power_demand_rest" => ("From EMPIRE results $(ts_file), based on power flow in and out of our regional scope","Total Electricity flow in the Rest region from geographical scope","MWh"),
    )
    enumerate_column!(df, :Period)
    enumerate_column!(df, :Scenario)
    enumerate_column!(df, :Season)
    rename!(df, column_rename)
    select!(df, [:sp, :rp, :scp, :op, :val])
    filter!(df-> df.sp .<= number_sp, df)
    filter!(df-> df.scp .<= scenario_nb, df)
    df.val = round.(df.val; digits=3)
    #copy df to create df_neg and df_pos with respectively only the negative and positive values and 0 for the other indexes
    df_neg = copy(df)
    df_pos = copy(df)
    df_neg.val .= -min.(df_neg.val, -0.0)
    df_pos.val .= max.(df_pos.val, 0.0)
    #df_neg represents the sources, we extract the maximum value in each sp to define the capacity and normalise the timeserie by that value as the profile
    max_vals = [maximum(x.val) for x in groupby(df_neg, :sp)]
    # divide val in each sp by the corresponding max_val
    for (i, max_val) in enumerate(max_vals)
        df_neg[df_neg.sp .== i, :val] .= df_neg[df_neg.sp .== i, :val] ./ max(max_val,1.0) # avoid division by 0
    end
    df_neg.val = round.(df_neg.val; digits=3)
    # make a dataframe with the max_vals and sp
    max_vals = DataFrame(sp = 1:number_sp, val = max_vals)

    write_ts_csv(df_pos, out_folder, "Rest", node_type*"_demand", "capacity", ts_meta[ts_type])
    write_ts_csv(df_neg, out_folder, "Rest", node_type*"_source", "profile", ts_meta[ts_type])
    write_ts_csv(max_vals, out_folder, "Rest", node_type*"_source", "capacity", ts_meta[ts_type])
end
