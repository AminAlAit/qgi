import pandas as pd
from datetime import datetime


# Assign weights to each metric
WEIGHT_PATTERN_LENGTH      = 0.1
WEIGHT_INDEXES             = 0.3
WEIGHT_AVERAGE_CORR        = 0.6
COUNTRY_PATTERN_TABLE_NAME = "country_pattern"
COUNTRIES_PATH             = "data/countries/"


REGION_COUNTRIES = {
    "North Africa":    ["Algeria", "Egypt", "Libya", "Morocco", "Tunisia", "Western Sahara", "Sudan", "South Sudan"],
    "West Africa":     ["Nigeria", "Cabo Verde", "Ghana", "Senegal", "Mali", "Ivory Coast", "Benin", "Burkina Faso", "Cape Verde", "Gambia", "Guinea", "Guinea-Bissau", "Liberia", "Niger", "Sierra Leone", "Togo", "Mauritania"],
    "Central Africa":  ["Angola", "Republic of the Congo", "Cameroon", "Central African Republic", "Chad", "Congo", "Democratic Republic of the Congo", "Equatorial Guinea", "Gabon", "Sao Tome and Principe"],
    "East Africa":     ["Burundi", "Comoros", "Djibouti", "Eritrea", "Ethiopia", "Kenya", "Madagascar", "Malawi", "Mauritius", "Mozambique", "Rwanda", "Seychelles", "Somalia", "Tanzania", "Uganda", "Zambia", "Zimbabwe"],
    "Southern Africa": ["Botswana", "Eswatini", "Lesotho", "Namibia", "South Africa"],
    
    "North America":   ["United States", "Canada", "Mexico", "Greenland", "Bermuda"],
    "Central America": ["Belize", "Costa Rica", "El Salvador", "Guatemala", "Honduras", "Nicaragua", "Panama"],
    "Caribbean":       ["Cuba", "Haiti", "Dominican Republic", "Jamaica", "Trinidad and Tobago", "Puerto Rico", "Bahamas", "Barbados", "Saint Lucia", "Grenada", "Antigua and Barbuda", "Dominica", "Cayman Islands", "Saint Kitts and Nevis", "Saint Vincent and the Grenadines", "Aruba", "United States Virgin Islands", "British Virgin Islands", "Turks and Caicos Islands", "Anguilla", "Saint Martin", "Saint Barthélemy", "Guadeloupe", "Martinique", "Curacao", "Sint Maarten", "Bonaire, Sint Eustatius and Saba", "Montserrat"],
    "South America":   ["Brazil", "Argentina", "Colombia", "Venezuela", "Peru", "Chile", "Ecuador", "Bolivia", "Paraguay", "Uruguay", "Guyana", "Suriname", "French Guiana"],
    
    "Europe":          ["United Kingdom", "Germany", "Russia", "Czechia", "Serbia", "France", "Italy", "Spain", "Ukraine", "Poland", "Cyprus", "Romania", "Netherlands", "Belgium", "Czech Republic", "Greece", "Portugal", "Sweden", "Hungary", "Belarus", "Austria", "Switzerland", "Bulgaria", "Denmark", "Finland", "Slovakia", "Norway", "Ireland", "Croatia", "Moldova", "Bosnia and Herzegovina", "Albania", "Lithuania", "North Macedonia", "Slovenia", "Latvia", "Estonia", "Montenegro", "Luxembourg", "Malta", "Iceland", "Andorra", "Monaco", "Liechtenstein", "San Marino", "Gibraltar", "Vatican City", "Kosovo"],
    
    "Caucasus":        ["Azerbaijan", "Georgia", "Armenia"],
    "Middle East":     ["Saudi Arabia", "Iran", "United Arab Emirates", "Israel", "Iraq", "Qatar", "Kuwait", "Bahrain", "Oman", "Yemen", "Jordan", "Lebanon", "Syria", "Palestine"],
    "Central Asia":    ["Kazakhstan", "Uzbekistan", "Turkmenistan", "Kyrgyzstan", "Tajikistan"],
    "South Asia":      ["India", "Pakistan", "Bangladesh", "Nepal", "Bhutan", "Sri Lanka", "Maldives"],
    "West Asia":       ["Turkiye", "Afghanistan"],
    "East Asia":       ["China", "Japan", "South Korea", "North Korea", "Mongolia", "Taiwan", "Hong Kong", "Macao"],
    "Southeast Asia":  ["Indonesia", "Thailand", "Vietnam", "Malaysia", "Philippines", "Singapore", "Myanmar", "Cambodia", "Laos", "Brunei", "Timor-Leste"],
    "Oceania":         ["Australia", "New Zealand", "Papua New Guinea", "Fiji", "Solomon Islands", "Vanuatu", "Samoa", "Kiribati", "Federated States of Micronesia", "Tonga", "Marshall Islands", "Palau", "Tuvalu", "Nauru", "New Caledonia", "French Polynesia", "Micronesia", "Guam", "American Samoa", "Northern Mariana Islands", "Cook Islands", "Wallis and Futuna", "Tokelau", "Niue", "Pitcairn Islands"]
}
REGION_COLORS = {
    "Caucasus":        "wheat",
    "North Africa":    "#6495ED", # Cornflower Blue
    "West Africa":     "#008000", # Green
    "Central Africa":  "#FFD700", # Gold
    "East Africa":     "#B22222", # Firebrick
    "Southern Africa": "#FF69B4", # Hot Pink
    "North America":   "#FF4500", # Orange Red
    "Central America": "#20B2AA", # Light Sea Green
    "Caribbean":       "#1E90FF", # Dodger Blue
    "South America":   "#DAA520", # Goldenrod
    "Europe":          "#708090", # Slate Gray
    "Middle East":     "#2E8B57", # Sea Green
    "Central Asia":    "#800080", # Purple
    "South Asia":      "#FF8C00", # Dark Orange
    "East Asia":       "#4682B4", # Steel Blue
    "Southeast Asia":  "#6A5ACD", # Slate Blue
    "Oceania":         "#DB7093"  # Pale Violet Red
}


def extract_and_rank_patterns_for_country(country_a_id: str, country_a):
    if country_a == ""  or country_a_id == "":
        return pd.DataFrame()
    try:
        grouped = pd.read_csv(COUNTRIES_PATH + country_a_id + "_" + country_a + "_patterns.csv")
        return grouped
        # # Converting columns into numericals
        # grouped["pattern_length_fk"] = pd.to_numeric(grouped["pattern_length_fk"], errors = "coerce")
        # grouped["correlation"]       = pd.to_numeric(grouped["correlation"],       errors = "coerce")

        # # Group by "country_b_id_fk" and "pattern_length"
        # grouped = grouped.groupby(["country_b_id_fk", "pattern_length_fk", "start_year_a_fk", "start_year_b_fk"]).agg(
        #     indexes  = ("index_name_fk", "nunique"),
        #     avg_corr = ("correlation", "mean")
        # ).reset_index()
        
        # Calculate the "Power" score using weighted sum
        # grouped["Power"] = (grouped["pattern_length_fk"] * WEIGHT_PATTERN_LENGTH +
        #                     grouped["indexes"]           * WEIGHT_INDEXES +
        #                     grouped["avg_corr"]          * WEIGHT_AVERAGE_CORR)
        
        # display_df_cols = ["country_b_id_fk", "start_year_a_fk", "start_year_b_fk", "pattern_length_fk", "indexes", "avg_corr", "Power"]
        # grouped         = pd.DataFrame(grouped)[display_df_cols]

        # Sort the DataFrame based on the "Power" score
        sorted_patterns = grouped.sort_values(by = "Power", ascending = False)
        return sorted_patterns

    except Exception as e:
        print(f"Error occured in `extract_and_rank_patterns_for_country`: {e}")
        return None


def calculate_early_warning_signals(display_df, DISPLAY_DF_START_YEAR_A_RENAME, DISPLAY_DF_START_YEAR_B_RENAME, DISPLAY_DF_PATTERN_LENGTH_RENAME):
    """
    Calculates early warning signals for a pattern where the starting year for country B is before
    that of country A, indicating that country A may be following a historical pattern of country B.
    Additionally, it filters for patterns where the sum of the starting year for country A and
    the pattern length equals the current year.

    Parameters:
    display_df (DataFrame): The dataframe containing patterns data.
    DISPLAY_DF_START_YEAR_A_RENAME (str): Column name for starting year of country A.
    DISPLAY_DF_START_YEAR_B_RENAME (str): Column name for starting year of country B.
    DISPLAY_DF_PATTERN_LENGTH_RENAME (str): Column name for pattern length.

    Returns:
    DataFrame: A dataframe with the early warning signals highlighted.
    """
    current_year = datetime.now().year

    # Existing filter for patterns where country B's starting year is before country A's
    warning_df = display_df[(display_df[DISPLAY_DF_START_YEAR_B_RENAME] < display_df[DISPLAY_DF_START_YEAR_A_RENAME])]

    # Calculate the years gap between the countries
    warning_df['years_gap'] = warning_df[DISPLAY_DF_START_YEAR_A_RENAME] - warning_df[DISPLAY_DF_START_YEAR_B_RENAME]
    
    # Identify if country A is in the early stage of following country B's pattern
    warning_df['early_warning'] = warning_df['years_gap'].apply(lambda x: x >= 0)

    # New filter for patterns ending in the current year
    warning_df = warning_df[(warning_df[DISPLAY_DF_START_YEAR_A_RENAME] + warning_df[DISPLAY_DF_PATTERN_LENGTH_RENAME]) == current_year]

    return warning_df


def color_countries(val):
    country_to_region = {country: region for region, countries in REGION_COUNTRIES.items() for country in countries}
    region            = country_to_region.get(val)
    
    if region:
        return f"background-color: {REGION_COLORS.get(region)}"
    return ""


def manual_merge_dfs(df1, df2, key_columns):
    """
    Manually merges two dataframes on the specified key columns.

    Parameters:
    df1 (pd.DataFrame): First DataFrame.
    df2 (pd.DataFrame): Second DataFrame.
    key_columns (list): List of columns to merge on.

    Returns:
    pd.DataFrame: Merged DataFrame.
    """
    merged_data = []

    # Iterating through each row of the first dataframe
    for _, row1 in df1.iterrows():
        # Finding the matching row in the second dataframe
        match = df2[(df2[key_columns] == row1[key_columns]).all(axis=1)]

        # If a match is found, append the combined row to the merged data
        if not match.empty:
            combined_row = row1.append(match.iloc[0].drop(key_columns))
            merged_data.append(combined_row)

    # Create a dataframe from the merged data
    return pd.DataFrame(merged_data).reset_index(drop=True)


def compare_rankings(old_df, new_df):
    merged_df = new_df
    merged_df["avg_corr"] = (merged_df["avg_corr"] * 100).round(2).astype(str) + "%"

    # Remove commas from Year columns and convert to proper format
    merged_df["start_year_a_fk"] = merged_df["start_year_a_fk"].fillna(0).astype(int).astype(str)
    merged_df["start_year_b_fk"] = merged_df["start_year_b_fk"].fillna(0).astype(int).astype(str)

    # Convert Pattern Length and Number of Indexes to integer
    merged_df["pattern_length_fk"] = merged_df["pattern_length_fk"].fillna(0).astype(int)
    merged_df["indexes"] = merged_df["indexes"].fillna(0).astype(int)
    #merged_df["indexes_new"] = merged_df["indexes_new"].fillna(0).astype(int)

    merged_df.rename(columns={
        "Rank_Change_Info": " ",
        "country_a_id_fk": "Country A",
        "country_b_id_fk": "Country B",
        "start_year_a_fk": "Starting Year A",
        "start_year_b_fk": "Starting Year B",
        "pattern_length_fk": "Pattern Length",
        "Power": "Pattern Power Ranking",
        "indexes": "Number of Indexes",
        "avg_corr": "Average Correlation"
    }, inplace = True)

    final_df = merged_df[["Country A", "Country B", "Starting Year A", "Starting Year B", "Pattern Length", "Number of Indexes", "Average Correlation", "Pattern Power Ranking"]]
    final_df = final_df[pd.notna(final_df["Pattern Power Ranking"])]
    final_df = final_df.head(2000) # `.style` can not style more than a certain limit, so 7000 is a safe maximum number to use. 
    #final_df = final_df[final_df["Sources"] > 1]
    final_df = final_df.style.applymap(color_countries, subset=["Country A", "Country B"])

    return final_df
