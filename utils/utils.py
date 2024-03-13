import ast
import math
import os
import subprocess
import streamlit as st
import pandas as pd
from constant.index_names_subs import INDEX_NAMES_THAT_NEED_CHANGING, MAIN_NAMES_THAT_NEED_CHANGING
from constant.tips import (
    GET_TIP_PATTERN_LENGTH_RANGE_SLIDER,
    GET_TIP_STARTING_YEAR_SLIDER,
    GET_TIP_YEAR_GAP_RANGE_SLIDER,
    TIP_ALIGN_TOGGLE,
    TIP_COUNTRY_A_SELECT,
    TIP_COUNTRY_B_SELECT,
    GET_TIP_CORRELATION_RANGE_SLIDER,
    TIP_SELECT_PATTERN_LENGTH,
    TIP_TRANSFORMATION_CAPTIONS,
    TIP_TRANSFORMATION_RADIO)


BAT_PATH                                    = "/mount/src/qgi/.bat"
COUNTRIES_PATH                              = "data/countries/"
COUNTRY_DICTIONARY_PATH                     = "data/country.csv"
COUNTRY_ID_COLUMN                           = "id"
CORRELATION_COLUMN                          = "correlation_column"
COUNTRY_TABLE_NAME                          = "country"
COUNTRY_PATTERN_TABLE_NAME                  = "country_pattern"
COUNTRY_PATTERN_COUNTRY_A_ID_FK_COLUMN_NAME = "country_a_id_fk"


def run_requirements():
    ## TODO WARNING: You are using pip version 22.0.3; however, version 23.3.2 is available.
    # You should consider upgrading via the '/home/adminuser/venv/bin/python -m pip install --upgrade pip' command.
    # /bin/sh: 1: /mount/src/qgi/.bat: Permission denied
    subprocess.run(BAT_PATH, shell = True)


def process_display_dataframe(df, DISPLAY_DF_NEW_COLUMN_NAMES, countries_df):
    """
    Processes a DataFrame by renaming columns, replacing country IDs with names, and converting correlation values to percentages.

    Parameters:
    - df (pd.DataFrame): The DataFrame to process.
    - DISPLAY_DF_NEW_COLUMN_NAMES (dict): Dictionary of new column names to replace old ones.
    - db_manager (DatabaseManager): Instance of DatabaseManager to execute queries.

    Returns:
    - pd.DataFrame: The processed DataFrame.
    """

    if len(df) < 1:
        return df


    # Rename columns
    df.rename(columns = {
        "country_b_id_fk":   DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"],
        "start_year_a_fk":   DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"],
        "start_year_b_fk":   DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_B_RENAME"],
        "pattern_length_fk": DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"],
        "indexes":           DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_NUMBER_OF_INDEXES_RENAME"],
        "avg_corr":          DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"],
        "Power":             DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_POWER_SCORE_RENAME"]
    }, inplace = True)

    # Replace country IDs with names
    country_names = []
    for country_id in df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]]:
        country_names.append(get_country_name(countries_df, country_id))

    df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]] = country_names

    # Convert correlation to percentage
    if DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"] in df.columns:
        df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"]] = (
            df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"]] * 100).apply(lambda x: f"{x:.2f}%")
    else:
        print(f"Column '{DISPLAY_DF_NEW_COLUMN_NAMES['DISPLAY_DF_AVERAGE_CORRELATION_RENAME']}' not found in the DataFrame.")

    return df


def get_country_names_and_ids(directory):
    country_names = []
    country_ids = []

    # Iterate over all files in the specified directory
    for filename in os.listdir(directory):
        if filename.endswith("_patterns.csv"):  # Check if the file is a CSV file
            if "solos" not in filename:
                parts = filename.split('_')  # Split the filename into parts

                # Extract ID and country name
                country_id = parts[0]
                country_name = '_'.join(parts[1:-1])

                country_ids.append(country_id)
                country_names.append(country_name)

    return country_names, country_ids


def get_countries_a_list():
    country_names, country_ids = get_country_names_and_ids(COUNTRIES_PATH)
    countries_df               = pd.DataFrame()
    countries_df["id"]         = country_ids
    countries_df["country"]    = country_names
    return countries_df


def str_to_list(s):
    return list(ast.literal_eval(s))


def get_country_id(countries_df, country_name):
    """
    Return the ID for a given country name.

    Parameters:
    countries_df (pd.DataFrame): DataFrame containing 'country' and 'id' columns.
    country_name (str): The name of the country.

    Returns:
    str: The ID of the given country, or None if not found.
    """
    match = countries_df[countries_df["country"] == country_name]
    if not match.empty:
        return match["id"].iloc[0]
    else:
        return None


def get_country_name(countries_df, country_id):
    """
    Return the country name for a given ID.

    Parameters:
    countries_df (pd.DataFrame): DataFrame containing 'country' and 'id' columns.
    country_id (str): The ID of the country.

    Returns:
    str: The name of the country corresponding to the given ID, or None if not found.
    """
    match = countries_df[countries_df["id"] == str(country_id)]
    if not match.empty:
        return match["country"].iloc[0]
    else:
        return None


def combine_values(df_row):
    # Convert string representations to lists
    values_a = str_to_list(df_row["index_values_a"])
    values_b = str_to_list(df_row["index_values_b"])

    # Calculate year ranges
    start_year_a   = int(df_row["start_year_a_fk"])
    start_year_b   = int(df_row["start_year_b_fk"])
    pattern_length = int(df_row["pattern_length_fk"])
    end_year_a     = start_year_a + pattern_length
    end_year_b     = start_year_b + pattern_length

    # Create year range
    years_a = list(range(start_year_a, end_year_a))
    years_b = list(range(start_year_b, end_year_b))

    # Create DataFrames from the inputs
    df_a = pd.DataFrame({"Year": years_a, "Value_A": values_a})
    df_b = pd.DataFrame({"Year": years_b, "Value_B": values_b})

    # Merge the DataFrames on 'Year', treating 'Year' as a key
    combined_df = pd.merge(df_a, df_b, on = "Year", how = "outer")

    # Sort by year
    combined_df = combined_df.sort_values(by = "Year")

    return combined_df


def round_list_items(lst, rounding = 3):
    for i in range(len(lst)):
        if lst[i] != "":
            lst[i] = round(lst[i], rounding)
    return lst


def replace_item_in_list(lst, old_value, new_value):
    """
    Replace all occurrences of old_value with new_value in the list.

    Parameters:
    lst (list): The list to modify.
    old_value: The value to be replaced.
    new_value: The new value to replace with.

    Returns:
    list: The modified list with replaced values.
    """
    res = lst
    for i in range(len(res)):
        if str(res[i]) == old_value:
            res[i] = new_value
    return res


def display_index_csv_and_download_buttons(row):
    download_display_index_df = combine_values(row).rename(columns = {
        "Value_A": row["country_a"], 
        "Value_B": row["country_b"]
    })
    st.markdown("##### " + row["index_name_fk"])
    st.download_button(
        label     = "Download CSV",
        data      = download_display_index_df.to_csv(index = False),
        file_name = f"{row['index_name_fk']}.csv",
        mime      = "text/csv",
    )
    st.dataframe(download_display_index_df)


def remove_duplicates(lst):
    unique_items = []
    result = []
    
    for item in lst:
        if item not in unique_items:
            unique_items.append(item)
            result.append(item)
    
    return result


# def filter_by_grouping_indexes(df, country_a, min_ind, max_ind):
#     # Group the DataFrame by the specified columns
# 
#     df["country_a_id_fk"] = [country_a for _ in range(len(df))]
# 
#     grouped = df.groupby(["country_a_id_fk", "country_b_id_fk", "pattern_length_fk", "start_year_a_fk", "start_year_b_fk"])
# 
#     # Calculate the count of rows in each group
#     group_counts = grouped.size().reset_index(name = "count")
# 
#     # Filter the groups based on the count
#     filtered_groups = group_counts[(group_counts["count"] >= min_ind) & (group_counts["count"] <= max_ind)]
# 
#     # Get the rows corresponding to the filtered groups
#     filtered_df = df.merge(filtered_groups, on = ["country_a_id_fk", "country_b_id_fk", "pattern_length_fk", "start_year_a_fk", "start_year_b_fk"])
#     
#     # Delete the rows from the original DataFrame
#     df = df[~df.index.isin(filtered_df.index)]
#    
#     return filtered_df, df


def percentage_str_to_float(percentage_str):
    return float(percentage_str.strip("%")) / 100


def sidebar_correlation_filter(display_df: pd.DataFrame, DISPLAY_DF_NEW_COLUMN_NAMES: dict) -> pd.DataFrame:
    # Convert the correlation column to float for filtering
    correlation_col_name = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"]
    display_df["correlation_float"] = display_df[correlation_col_name].apply(percentage_str_to_float)
    # Find the min and max values for the slider
    min_corr = min(display_df["correlation_float"])
    max_corr = max(display_df["correlation_float"])
    
    # Create a slider using the min and max values
    min_corr, max_corr = st.slider("Correlation Range", min_corr, max_corr, (min_corr, max_corr), help = GET_TIP_CORRELATION_RANGE_SLIDER(min_corr, max_corr))
    # Filter the DataFrame based on the correlation range
    display_df = display_df[(display_df["correlation_float"] >= min_corr) & (display_df["correlation_float"] <= max_corr)]
    # Optionally, drop the temporary float column if no longer needed
    display_df.drop("correlation_float", axis = 1, inplace = True)
    
    return [display_df, min_corr, max_corr]


# def sidebar_indexes_number_filter(display_df: pd.DataFrame, DISPLAY_DF_NUMBER_OF_INDEXES_RENAME) -> pd.DataFrame:
#     ## Filter the DataFrame based on the selected number of indexes
#     max_nb_indexes = max(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME])
#     min_nb_indexes = min(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME])
#     if min_nb_indexes < max_nb_indexes:
#         min_ind, max_ind = st.slider("Number of Indexes", min_nb_indexes, max_nb_indexes, (2, max_nb_indexes))
#         display_df       = display_df[(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] >= min_ind) \
#                                     & (display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] <= max_ind)]
#     else:
#         min_ind, max_ind = (1, 1)
#         display_df       = display_df[(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] >= min_ind) \
#                                     & (display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] <= max_ind)]
# 
#     return [display_df, min_ind, max_ind]


def sidebar_pattern_lengths_filter(display_df: pd.DataFrame, DISPLAY_DF_PATTERN_LENGTH_RENAME: str) -> pd.DataFrame:
    ## Filter the DataFrame based on the selected pattern length range
    max_pattern_length = max(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME])
    min_pattern_length = min(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME])
    if min_pattern_length < max_pattern_length:
        min_patt_len, max_patt_len = st.slider(
            "Pattern Length Range", 
            min_pattern_length, 
            max_pattern_length, 
            (min_pattern_length, max_pattern_length),
            help = GET_TIP_PATTERN_LENGTH_RANGE_SLIDER(min_pattern_length, max_pattern_length)
        )
        display_df = display_df[(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] >= min_patt_len) \
                            & (display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] <= max_patt_len)]
    else:
        min_patt_len, max_patt_len = (1, 1)
        display_df = display_df[(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] >= min_patt_len) \
                            & (display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] <= max_patt_len)]

    return display_df


def sidebar_years_gap_filter(display_df: pd.DataFrame, DISPLAY_DF_START_YEAR_B_RENAME: str, DISPLAY_DF_START_YEAR_A_RENAME: str, country_a) -> pd.DataFrame:
    ## Filter the DataFrame based on the selected year gap
    max_gap = (display_df[DISPLAY_DF_START_YEAR_B_RENAME] - display_df[DISPLAY_DF_START_YEAR_A_RENAME]).max()
    year_gap = st.slider(
        "Minimum Year Gap",
        min_value = 0,
        max_value = max_gap,
        value     = 0,
        step      = 1,
        key       = "year_gap_slider",
        help      = GET_TIP_YEAR_GAP_RANGE_SLIDER(0, max_gap, country_a)
    )
    display_df = display_df[(abs(display_df[DISPLAY_DF_START_YEAR_B_RENAME] - display_df[DISPLAY_DF_START_YEAR_A_RENAME])) >= year_gap]

    return display_df


def apply_advanced_filters(display_df: pd.DataFrame, DISPLAY_DF_NEW_COLUMN_NAMES, country_a) -> pd.DataFrame:
    if not isinstance(display_df, pd.DataFrame) or len(display_df) == 0:
        return [display_df, "", "", "", ""]

    ## Sidebar sliders for advanced options 
    with st.sidebar.expander("Advanced Filters"):
        display_df, min_corr, max_corr = sidebar_correlation_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES)
        #display_df, min_ind, max_ind   = sidebar_indexes_number_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_NUMBER_OF_INDEXES_RENAME"])
        display_df                     = sidebar_pattern_lengths_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"])
        display_df                     = sidebar_years_gap_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_B_RENAME"], DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"], country_a)
        return display_df, min_corr, max_corr, 0, 0 ## TODO fix: remove these zeros. 


#@st.cache_data(ttl=300)
def get_country_a_from_user():
    countries_list, countries_df = get_sorted_countries_list(True)
    return st.sidebar.selectbox("Country A", countries_list, help=TIP_COUNTRY_A_SELECT), countries_df


@st.cache_data(ttl=300)
def get_sorted_countries_list(return_countries_df = True):
    countries_df = get_countries_a_list()
    countries_df = countries_df.sort_values(by = "country")
    if return_countries_df:
        return [""] + list(countries_df["country"]), countries_df
    return [""] + list(countries_df["country"])


def find_csv_files(root_path):
    """
    Finds all CSV files in the given root path and its subdirectories
    that start with 'MAIN - ' and end with '.csv'.
    
    Parameters:
    - root_path (str): The root directory path to start the search from.
    
    Returns:
    - list: A list of paths to the CSV files that match the criteria.
    """
    csv_files = []
    for subdir, dirs, files in os.walk(root_path):
        for file in files:
            if file.startswith("MAIN - ") and file.endswith(".csv"):
                csv_files.append(os.path.join(subdir, file))
    
    return csv_files

PATTERNIZED_INDEXES = ""

@st.cache_data(ttl=300)
def FETCHING_INDEXES(csv_files):
    index_dfs = []
    index_names = []
    for index_path in csv_files:
        index_name = index_path.split("/")[-1].replace("MAIN - ", "").replace(".csv", "")
        # if index_name in PATTERNIZED_INDEXES:
        index_names.append(index_name)
        index_dfs.append(pd.read_csv(index_path))
    return [pd.DataFrame()] + index_dfs, [""] + index_names


def rename_display_df_columns(country_a: str) -> dict:
    return {
        "DISPLAY_DF_COUNTRY_B_RENAME":           country_a + " has Patterns with",
        "DISPLAY_DF_START_YEAR_A_RENAME":        "Starting Year for " + country_a,
        "DISPLAY_DF_START_YEAR_B_RENAME":        "Starting Year for Second Country",
        "DISPLAY_DF_PATTERN_LENGTH_RENAME":      "Pattern Length",
        "DISPLAY_DF_NUMBER_OF_INDEXES_RENAME":   "Number of Indexes",
        "DISPLAY_DF_AVERAGE_CORRELATION_RENAME": "Correlation",
        "DISPLAY_DF_PATTERN_POWER_SCORE_RENAME": "Pattern Power Score"
    }


def get_country_b_and_id_from_user(display_df: pd.DataFrame, countries_df, DISPLAY_DF_NEW_COLUMN_NAMES: dict, countries_a, countries_a_ids) -> str:
    if not isinstance(display_df, pd.DataFrame) or len(display_df) == 0:
        return ["", "", display_df]

    ## Country B Filtering
    pattern_power_score_col_name = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_POWER_SCORE_RENAME"]
    country_b_col_name           = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]

    countries_b = [""] + remove_duplicates(list(display_df[country_b_col_name]))

    if len(countries_b) > 2:
        country_b = st.sidebar.selectbox("Country B", countries_b, help = TIP_COUNTRY_B_SELECT)
    else:
        st.sidebar.selectbox("Select Second Country", [countries_b[1]], help = TIP_COUNTRY_B_SELECT)
        country_b = countries_b[1]

    country_b_id = get_country_id(countries_df, country_b)
    return [country_b, country_b_id, display_df]


def get_pattern_length_from_user(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, country_a, country_b) -> list:
    if not country_b or country_b == "":
        return ["", "", display_df]
    
    display_message = f"___\n### All Patterns between {country_a} and {country_b}"
    #warnings        = warnings[warnings[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]] == country_b]
    display_df      = display_df[display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]] == country_b]

    ## Pattern Length Filtering
    patt_lengths = [""] + list(set(display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"]]))
    if len(patt_lengths) > 2:
        patt_len = st.sidebar.selectbox("Pattern Length", patt_lengths, help = TIP_SELECT_PATTERN_LENGTH)
    else:
        st.sidebar.selectbox("Pattern Length", [patt_lengths[1]], help = TIP_SELECT_PATTERN_LENGTH)
        patt_len = patt_lengths[1]
    
    return [patt_len, display_message, display_df]


def get_start_year_a(
    display_message,
    display_df,
    country_a,
    country_a_id,
    country_b,
    country_b_id,
    patt_len,
    DISPLAY_DF_NEW_COLUMN_NAMES,
    min_corr, max_corr) -> list:
    
    if not patt_len or patt_len == "" or min_corr == "" or max_corr == "":
        return ["", "", display_df]

    pattern_length_col_name = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"]
    start_year_a_col_name   = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"]

    #warnings          = warnings[warnings[DISPLAY_DF_PATTERN_LENGTH_RENAME] == country_b]
    display_df        = display_df[display_df[pattern_length_col_name] == patt_len]

    df = pd.read_csv(COUNTRIES_PATH + country_a_id + "_" + country_a + "_patterns.csv")
    df = df[df["country_b_id_fk"] == country_b_id]
    df = df[df["pattern_length_fk"] == patt_len]
    df = df[df["avg_corr"] >= min_corr]
    df = df[df["avg_corr"] <= max_corr]

    df["avg_corr"] = pd.to_numeric(df["avg_corr"], errors = "coerce")
    # df             = filter_by_grouping_indexes(df, country_a, min_ind, max_ind)[0]

    start_years_a = [""] + list(set(display_df[start_year_a_col_name]))
    if len(start_years_a) > 2:
        start_year_a = st.sidebar.selectbox("Starting Year for " + country_a, start_years_a, help = GET_TIP_STARTING_YEAR_SLIDER(country_a))
    else:
        st.sidebar.selectbox("Starting Year for " + country_a, [start_years_a[1]], help = GET_TIP_STARTING_YEAR_SLIDER(country_a))
        start_year_a = start_years_a[1]

    display_message = f"### All Patterns between {country_a} ({start_year_a}) and {country_b}"

    return [start_year_a, display_message, display_df]


def get_start_year_b(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, start_year_a, country_b, display_message, country_a) -> list:
    if not start_year_a or start_year_a == "":
        return ["", display_df, ""]

    #warnings   = warnings[warnings[DISPLAY_DF_START_YEAR_A_RENAME] == country_b]
    display_df = display_df[display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"]] == start_year_a]

    start_years_b = [""] + list(set(display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_B_RENAME"]]))
    if len(start_years_b) > 2:
        start_year_b = st.sidebar.selectbox("Starting Year for " + country_b, start_years_b, help = GET_TIP_STARTING_YEAR_SLIDER(country_b))
    else:
        st.sidebar.selectbox("Starting Year for " + country_b, [start_years_b[1]], help = GET_TIP_STARTING_YEAR_SLIDER(country_b))
        start_year_b = start_years_b[1]
    
    display_message   = f"### All Patterns between {country_a} ({start_year_a}) and {country_b} ({start_year_b})"

    return [start_year_b, display_df, display_message]


def prepare_display_df_for_viz(display_df: pd.DataFrame, country_a, country_b, five_params: list, countries_a, countries_a_ids, countries_df):
    for param in five_params:
        if param == "":
            return display_df, pd.DataFrame()
    
    country_a_id = five_params[0]
    country_b_id = five_params[1]
    patt_len     = five_params[2]
    start_year_a = five_params[3]
    start_year_b = five_params[4]

    df = pd.read_csv(COUNTRIES_PATH + str(country_a_id) + "_" + country_a + "_solos_patterns.csv")
    df = df[df["country_b_id_fk"] == int(country_b_id)]
    df = df[df["pattern_length_fk"] == int(patt_len)]
    df = df[df["start_year_a_fk"] == int(start_year_a)]
    df = df[df["start_year_b_fk"] == int(start_year_b)]
    df.drop("unique_id", axis = 1, inplace = True)

    display_df = display_df.sort_values(by = "Correlation", ascending = False)

    display_df["country_a_id_fk"] = [country_a for _ in range(len(display_df))]
    display_df["country_b_id_fk"] = [country_b for _ in range(len(display_df))]

    df["country_a_id_fk"] = [country_a for _ in range(len(df))]
    df["country_b_id_fk"] = [country_b for _ in range(len(df))]

    return display_df, df


def validate_five_params(lst):
    for i in lst:
        if i == "" or i is None:
            return False
    return True


def merge_dataframes(df1, df2):
    combined_df = pd.concat([df1, df2], ignore_index = True)
    return combined_df


def transformation_method_radio_buttons(five_params):
    if validate_five_params(five_params):
        return st.sidebar.radio(
            "Choose Transformation Method",
            ("Raw Representation", "Normalize", "Standardize", "Base Year Indexing", "Logarithmic Scaling", "Growth Rates/Ratios")
        )

def align_toggle(five_params):
    if validate_five_params(five_params) and five_params[-1] != five_params[-2]:
        return st.sidebar.toggle("Algin Index Couples")


def plotting_transformations(five_params):
    align  = False
    method = "Raw Representation"
    if validate_five_params(five_params):
        if five_params[-1] != five_params[-2]:
            align = st.sidebar.toggle("Align Index Couples", help = TIP_ALIGN_TOGGLE)

        method = st.sidebar.radio(
            "Choose Transformation Method",
            [
                "Original Representation",
                "Normalize",
                "Standardize",
                "Base Year Indexing",
                "Logarithmic Scaling",
                "Growth Rates/Ratios"
            ],
            captions=TIP_TRANSFORMATION_CAPTIONS,
            help=TIP_TRANSFORMATION_RADIO
        )

    return align, method


def get_pattern_power_score(display_df, start_year_b, DISPLAY_DF_NEW_COLUMN_NAMES):
    if (display_df is None or len(display_df) < 1) or start_year_b is None:
        return 0
    elif len(display_df) == 1:
        pps = round(list(display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_POWER_SCORE_RENAME"]])[0], 4)    
        return pps

    filtered_df = display_df[display_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_B_RENAME"]] == start_year_b]
    if len(filtered_df) == 1:
        pps = round(list(filtered_df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_POWER_SCORE_RENAME"]])[0], 4)
        return pps
    return 0


def update_names_of_main_and_index_names(df: pd.DataFrame, five_params) -> pd.DataFrame:
    """
    Update the 'index_name_fk' column in the DataFrame using the substitute_index_display_names function.

    Parameters:
    - df (pd.DataFrame): The DataFrame to update.

    Returns:
    - pd.DataFrame: The updated DataFrame with new values in the 'index_name_fk' column.
    """
    if not validate_five_params(five_params):
        return df

    # Apply the substitute function to each row's index and main index names
    df["main_name_fk"]  = df.apply(substitute_main_names,          axis = 1)
    df["index_name_fk"] = df.apply(substitute_index_display_names, axis = 1)
    df = df.drop(["creation_date"], axis = 1)
    df = df.drop_duplicates()
    return df


def substitute_index_display_names(df_row: pd.Series) -> str:
    for alt_dict in INDEX_NAMES_THAT_NEED_CHANGING:
        if alt_dict["org_fk"] == df_row["org_fk"] and alt_dict["main_name_fk"] == df_row["main_name_fk"] and alt_dict["index_name_fk"] == df_row["index_name_fk"]:
            return alt_dict["new_name"]
    return df_row["index_name_fk"]


def substitute_main_names(df_row: pd.Series) -> str:
    for alt_dict in MAIN_NAMES_THAT_NEED_CHANGING:
        if alt_dict["org_fk"] == df_row["org_fk"] and alt_dict["main_name_fk"] == df_row["main_name_fk"]:
            if "index_name_fk" in alt_dict and alt_dict["index_name_fk"] == df_row["index_name_fk"]:
                return alt_dict["new_name"]
            return alt_dict["new_name"]
    return df_row["main_name_fk"]


def final_touches_to_df(df):
    df = df.drop(["country_a_id_fk"], axis = 1)
    df.rename(columns = {"orgs": "Organizations"}, inplace = True)
    df = switch_columns(df)
    df = convert_str_to_list(df, "Sectors")
    return df


def switch_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Switches the 6th and 7th columns of a given DataFrame.

    Parameters:
    - df: The DataFrame whose columns are to be switched.

    Returns:
    - A DataFrame with the 6th and 7th columns switched.
    """
    # Ensure that the DataFrame has at least 7 columns
    if df.shape[1] < 7:
        raise ValueError("DataFrame must have at least 7 columns to switch the 6th and 7th columns.")
    
    # Generating a new column order
    new_order = list(range(df.shape[1]))
    new_order[5], new_order[6] = new_order[6], new_order[5]  # Switching the positions of the 6th and 7th columns
    
    # Reordering the DataFrame columns
    return df.iloc[:, new_order]


def convert_str_to_list(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Converts a DataFrame column that contains string representations of lists
    into actual lists for each row.

    Parameters:
    - df: The DataFrame containing the column to convert.
    - column_name: The name of the column to convert.

    Returns:
    - A DataFrame with the specified column converted from string representations of lists to actual lists.
    """
    if column_name in df.columns:
        # Using `ast.literal_eval` to safely evaluate the string as a Python expression
        df[column_name] = df[column_name].apply(ast.literal_eval)
    else:
        raise ValueError(f"Column '{column_name}' not found in DataFrame.")
    
    return df


def get_alpha2_by_name(country_name: str) -> str:
    """
    Retrieves the ISO 3166-1 alpha-2 country code for a given country name, searching all columns.

    Parameters:
    - country_name (str): The name of the country.

    Returns:
    - str: The ISO 3166-1 alpha-2 country code if found, otherwise None.
    """
    countries_df = pd.read_csv(COUNTRY_DICTIONARY_PATH)
    # Search across all columns for the country_name
    match_index = countries_df.apply(lambda row: country_name in row.values, axis=1)
    match = countries_df[match_index]
    if not match.empty:
        return match["alpha_2"].iloc[0]
    else:
        return None


def get_country_name_by_id(country_id: str) -> str:
    """
    Retrieves the ISO 3166-1 alpha-2 country code for a given country name.

    Parameters:
    - country_name (str): The name of the country.

    Returns:
    - str: The ISO 3166-1 alpha-2 country code.
    """
    countries_df = pd.read_csv(COUNTRY_DICTIONARY_PATH)
    match = countries_df[countries_df["id"] == country_id]
    if not match.empty:
        return match["name_1"].iloc[0]
    else:
        return None
