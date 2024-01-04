import ast
import subprocess
import streamlit as st
import pandas as pd
from database.db_manager import DatabaseManager



BAT_PATH                                    = r"C:\Users\Amin\Desktop\trojan\trojan 2.0\streamlit\.bat"
COUNTRY_ID_COLUMN                           = "id"
CORRELATION_COLUMN                          = "correlation_column"
COUNTRY_TABLE_NAME                          = "country"
COUNTRY_PATTERN_TABLE_NAME                  = "country_pattern"
COUNTRY_PATTERN_COUNTRY_A_ID_FK_COLUMN_NAME = "country_a_id_fk"


def process_display_dataframe(db, df, DISPLAY_DF_NEW_COLUMN_NAMES):
    """
    Processes a DataFrame by renaming columns, replacing country IDs with names, and converting correlation values to percentages.

    Parameters:
    - df (pd.DataFrame): The DataFrame to process.
    - DISPLAY_DF_NEW_COLUMN_NAMES (dict): Dictionary of new column names to replace old ones.
    - db_manager (DatabaseManager): Instance of DatabaseManager to execute queries.

    Returns:
    - pd.DataFrame: The processed DataFrame.
    """
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

    # Get country mapping using DatabaseManager
    country_mapping_query = "SELECT id, name_1 FROM country"
    country_mapping_df = db.execute_this_query(country_mapping_query)
    country_mapping = dict(zip(country_mapping_df['id'], country_mapping_df['name_1']))

    # Replace country IDs with names
    df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]] = df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]].map(country_mapping)

    # Convert correlation to percentage
    if DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"] in df.columns:
        df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"]] = (
            df[DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_AVERAGE_CORRELATION_RENAME"]] * 100).apply(lambda x: f"{x:.2f}%")
    else:
        print(f"Column '{DISPLAY_DF_NEW_COLUMN_NAMES['DISPLAY_DF_AVERAGE_CORRELATION_RENAME']}' not found in the DataFrame.")

    return df


def get_countries_a_list(db = None):
    db            = DatabaseManager()
    query         = f"SELECT DISTINCT `{COUNTRY_PATTERN_COUNTRY_A_ID_FK_COLUMN_NAME}` FROM country_pattern"
    country_a_ids = list(db.execute_this_query(query)[COUNTRY_PATTERN_COUNTRY_A_ID_FK_COLUMN_NAME])
    countries_a   = [db.get_value_by_id("country", country_id, "name_1") for country_id in country_a_ids]
    return [""] + countries_a


def run_requirements():
    subprocess.run(BAT_PATH, shell = True)


def str_to_list(s):
    return list(ast.literal_eval(s))


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


def filter_by_grouping_indexes(dataframe, min_ind, max_ind):
    # Group the DataFrame by the specified columns
    grouped = dataframe.groupby(["country_a_id_fk", "country_b_id_fk", "pattern_length_fk", "start_year_a_fk", "start_year_b_fk"])

    # Calculate the count of rows in each group
    group_counts = grouped.size().reset_index(name = "count")

    # Filter the groups based on the count
    filtered_groups = group_counts[(group_counts["count"] >= min_ind) & (group_counts["count"] <= max_ind)]

    # Get the rows corresponding to the filtered groups
    filtered_data = dataframe.merge(filtered_groups, on = ["country_a_id_fk", "country_b_id_fk", "pattern_length_fk", "start_year_a_fk", "start_year_b_fk"])
    
    # Delete the rows from the original DataFrame
    dataframe = dataframe[~dataframe.index.isin(filtered_data.index)]
    
    return filtered_data, dataframe


def replace_country_ids_with_names(df):
    """
    Replaces country IDs in 'country_a_id_fk' and 'country_b_id_fk' with country names and renames these columns.

    Parameters:
    - df (pd.DataFrame): The DataFrame containing the country IDs.

    Returns:
    - pd.DataFrame: The DataFrame with country IDs replaced by country names.
    """
    db = DatabaseManager()
    # Columns to replace and their new names
    columns_to_replace = {
        "country_a_id_fk": "country_a",
        "country_b_id_fk": "country_b"
    }

    for old_col, new_col in columns_to_replace.items():
        if old_col in df.columns:
            # Replace each ID in the column with its corresponding country name
            df[new_col] = df[old_col].apply(lambda x: db.get_value_by_id("country", x, "name_1") if x else None)
    
    # Drop old columns if new columns have been successfully created
    for old_col in columns_to_replace:
        if old_col in df.columns and columns_to_replace[old_col] in df.columns:
            df.drop(columns=[old_col], inplace=True)

    return df


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
    min_corr, max_corr = st.slider("Correlation Range", min_corr, max_corr, (min_corr, max_corr))
    # Filter the DataFrame based on the correlation range
    display_df = display_df[(display_df["correlation_float"] >= min_corr) & (display_df["correlation_float"] <= max_corr)]
    # Optionally, drop the temporary float column if no longer needed
    display_df.drop("correlation_float", axis = 1, inplace = True)
    
    return [display_df, min_corr, max_corr]


def sidebar_indexes_number_filter(display_df: pd.DataFrame, DISPLAY_DF_NUMBER_OF_INDEXES_RENAME) -> pd.DataFrame:
    ## Filter the DataFrame based on the selected number of indexes
    max_nb_indexes = max(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME])
    min_nb_indexes = min(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME])
    if min_nb_indexes < max_nb_indexes:
        min_ind, max_ind = st.slider("Number of Indexes", min_nb_indexes, max_nb_indexes, (2, max_nb_indexes))
        display_df       = display_df[(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] >= min_ind) \
                                    & (display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] <= max_ind)]
    else:
        min_ind, max_ind = (1, 1)
        display_df       = display_df[(display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] >= min_ind) \
                                    & (display_df[DISPLAY_DF_NUMBER_OF_INDEXES_RENAME] <= max_ind)]

    return [display_df, min_ind, max_ind]


def sidebar_pattern_lengths_filter(display_df: pd.DataFrame, DISPLAY_DF_PATTERN_LENGTH_RENAME: str) -> pd.DataFrame:
    ## Filter the DataFrame based on the selected pattern length range
    max_pattern_lengths = max(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME])
    min_pattern_lengths = min(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME])
    if min_pattern_lengths < max_pattern_lengths:
        min_patt_len, max_patt_len = st.slider("Pattern Length Range", min_pattern_lengths, max_pattern_lengths, (min_pattern_lengths, max_pattern_lengths))
        display_df = display_df[(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] >= min_patt_len) \
                            & (display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] <= max_patt_len)]
    else:
        min_patt_len, max_patt_len = (1, 1)
        display_df = display_df[(display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] >= min_patt_len) \
                            & (display_df[DISPLAY_DF_PATTERN_LENGTH_RENAME] <= max_patt_len)]

    return display_df


def sidebar_years_gap_filter(display_df: pd.DataFrame, DISPLAY_DF_START_YEAR_B_RENAME: str, DISPLAY_DF_START_YEAR_A_RENAME: str) -> pd.DataFrame:
    ## Filter the DataFrame based on the selected year gap
    max_gap = (display_df[DISPLAY_DF_START_YEAR_B_RENAME] - display_df[DISPLAY_DF_START_YEAR_A_RENAME]).max()
    year_gap = st.slider(
        "Minimum Year Gap",
        min_value = 0,
        max_value = max_gap,
        value     = 0,
        step      = 1,
        key       = "year_gap_slider"
    )
    display_df = display_df[(abs(display_df[DISPLAY_DF_START_YEAR_B_RENAME] - display_df[DISPLAY_DF_START_YEAR_A_RENAME])) >= year_gap]

    return display_df


def apply_advanced_filters(display_df: pd.DataFrame, DISPLAY_DF_NEW_COLUMN_NAMES) -> pd.DataFrame:
    if not isinstance(display_df, pd.DataFrame) or len(display_df) == 0:
        return [display_df, "", "", "", ""]

    ## Sidebar sliders for advanced options 
    with st.sidebar.expander("Advanced Filters"):
        display_df, min_corr, max_corr = sidebar_correlation_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES)
        display_df, min_ind, max_ind   = sidebar_indexes_number_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_NUMBER_OF_INDEXES_RENAME"])
        display_df                     = sidebar_pattern_lengths_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"])
        display_df                     = sidebar_years_gap_filter(display_df, DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_B_RENAME"], DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"])
        return display_df, min_corr, max_corr, min_ind, max_ind


def get_country_a_from_user():
        return st.sidebar.selectbox("Select Any Country", get_countries_a_list())


def rename_display_df_columns(country_a: str) -> dict:
    return {
        "DISPLAY_DF_COUNTRY_B_RENAME":           country_a + " has Patterns with",
        "DISPLAY_DF_START_YEAR_A_RENAME":        "Starting Year for " + country_a,
        "DISPLAY_DF_START_YEAR_B_RENAME":        "Starting Year for Second Country",
        "DISPLAY_DF_PATTERN_LENGTH_RENAME":      "Pattern Length (in years)",
        "DISPLAY_DF_NUMBER_OF_INDEXES_RENAME":   "Number of Indexes",
        "DISPLAY_DF_AVERAGE_CORRELATION_RENAME": "Pattern's Average Correlation",
        "DISPLAY_DF_PATTERN_POWER_SCORE_RENAME": "Pattern Power Score"
    }


def replace_country_ids_with_names(df, column_name, db):
    """
    Replaces country IDs in a specified column with country names.

    Parameters:
    - df (pd.DataFrame): The DataFrame to be processed.
    - column_name (str): The name of the column containing country IDs.
    - db: An instance of the database manager class.

    Returns:
    - pd.DataFrame: The DataFrame with country IDs replaced by country names.
    """

    if column_name in df.columns:
        # Replace each country ID in the column with its corresponding country name
        df[column_name] = df[column_name].apply(lambda x: db.get_value_by_id("country", x, "name_1") if pd.notnull(x) else x)
    else:
        print(f"Column '{column_name}' not found in the DataFrame.")

    return df


def get_country_b_and_id_from_user(db, display_df: pd.DataFrame, DISPLAY_DF_NEW_COLUMN_NAMES: dict) -> str:
    if not isinstance(display_df, pd.DataFrame) or len(display_df) == 0:
        return ["", "", display_df]
    
    ## Country B Filtering
    pattern_power_score_col_name = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_POWER_SCORE_RENAME"]
    country_b_col_name           = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_COUNTRY_B_RENAME"]
    
    countries_b = [""] + remove_duplicates(list(display_df[country_b_col_name]))

    # countries_b_ids = remove_duplicates(display_df.sort_values(by = pattern_power_score_col_name, ascending = False)\
    #     [country_b_col_name].tolist())

    # countries_b = [""] + [db.get_value_by_id("country", country_id, "name_1") for country_id in countries_b_ids]
    # display_df  = replace_country_ids_with_names(display_df, country_b_col_name, db)

    if len(countries_b) > 2:
        country_b = st.sidebar.selectbox("Select Second Country", countries_b)
    else:
        st.sidebar.selectbox("Select Second Country", [countries_b[1]])
        country_b = countries_b[1]

    country_b_id = db.get_id_by_value("country", country_b, "name_1")
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
        patt_len = st.sidebar.selectbox("Pattern Length", patt_lengths)
    else:
        st.sidebar.selectbox("Pattern Length", [patt_lengths[1]])
        patt_len = patt_lengths[1]
    
    return [patt_len, display_message, display_df]

def get_start_year_a(
    db,
    display_message,
    display_df,
    country_a,
    country_a_id,
    country_b,
    country_b_id,
    patt_len,
    DISPLAY_DF_NEW_COLUMN_NAMES,
    min_corr, max_corr, min_ind, max_ind) -> list:
    
    if not patt_len or patt_len == "" or min_corr == "" or max_corr == "" or min_ind == "" or max_ind == "":
        return ["", "", display_df]

    pattern_length_col_name = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_PATTERN_LENGTH_RENAME"]
    start_year_a_col_name   = DISPLAY_DF_NEW_COLUMN_NAMES["DISPLAY_DF_START_YEAR_A_RENAME"]

    #warnings          = warnings[warnings[DISPLAY_DF_PATTERN_LENGTH_RENAME] == country_b]
    display_df        = display_df[display_df[pattern_length_col_name] == patt_len]

    query  = f"SELECT * FROM {COUNTRY_PATTERN_TABLE_NAME} "
    query += f"WHERE `country_a_id_fk` = {country_a_id} "
    query += f"AND `country_b_id_fk` = {country_b_id} "
    query += f"AND `pattern_length_fk` = {patt_len} "
    query += f"AND `correlation` >= {min_corr} AND `correlation` <= {max_corr}"
    #query += f"AND `correlation` BETWEEN {min_corr} AND {max_corr}"
    df     = db.execute_this_query(query)
    
    df["correlation"] = pd.to_numeric(df["correlation"], errors = "coerce")
    df                = filter_by_grouping_indexes(df, min_ind, max_ind)[0]

    start_years_a = [""] + list(set(display_df[start_year_a_col_name]))
    if len(start_years_a) > 2:
        start_year_a = st.sidebar.selectbox("Starting Year for " + country_a, start_years_a)
    else:
        st.sidebar.selectbox("Starting Year for " + country_a, [start_years_a[1]])
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
        start_year_b = st.sidebar.selectbox("Starting Year for " + country_b, start_years_b)
    else:
        st.sidebar.selectbox("Starting Year for " + country_b, [start_years_b[1]])
        start_year_b = start_years_b[1]
    
    display_message   = f"### All Patterns between {country_a} ({start_year_a}) and {country_b} ({start_year_b})"

    return [start_year_b, display_df, display_message]


def prepare_display_df_for_viz(db, display_df: pd.DataFrame, five_params: list):
    for param in five_params:
        if param == "":
            return display_df
    
    country_a_id = five_params[0]
    country_b_id = five_params[1]
    patt_len     = five_params[2]
    start_year_a = five_params[3]
    start_year_b = five_params[4]
    
    query =  f"SELECT * FROM {COUNTRY_PATTERN_TABLE_NAME} " 
    query += f"WHERE `country_a_id_fk` = {country_a_id} "
    query += f"AND `country_b_id_fk` = {country_b_id} "
    query += f"AND `pattern_length_fk` = {patt_len} "
    query += f"AND `start_year_a_fk` = {start_year_a} "
    query += f"AND `start_year_b_fk` = {start_year_b}"
    
    display_df = db.execute_this_query(query)

    display_df.drop("unique_id", axis = 1, inplace = True)
    display_df = display_df.sort_values(by = "correlation", ascending = False)
    display_df = replace_country_ids_with_names(display_df, "country_a_id_fk", db)
    display_df = replace_country_ids_with_names(display_df, "country_b_id_fk", db)
    return display_df


def validate_five_params(lst):
    for i in lst:
        if i == "" or i is None:
            return False
    return True


def merge_dataframes(df1, df2):
    combined_df = pd.concat([df1, df2], ignore_index = True)
    return combined_df


def get_country_id_of_country_name(db, country_name):
    return db.get_id_by_value("country", country_name, "name_1")


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
            align = st.sidebar.toggle("Align Index Couples")

        method = st.sidebar.radio(
            "Choose Transformation Method",
            (
                "Raw Representation",
                "Normalize",
                "Standardize",
                "Base Year Indexing",
                "Logarithmic Scaling",
                "Growth Rates/Ratios"
            )
        )

    return align, method
