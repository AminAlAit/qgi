import math
import numpy as np
import pandas as pd
from constant.sectors import SECTOR_MAPPING
from database.db_manager import get_alpha2_by_name, get_country_b_counts_for_country_a
from utils.utils import combine_values, final_touches_to_df, replace_item_in_list, round_list_items, validate_five_params
from streamlit_echarts import st_echarts, JsCode
import streamlit as st
from streamlit_extras.dataframe_explorer import dataframe_explorer
# import sys
# import subprocess
# subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-timeline"])
import streamlit_timeline as st_t


def substitute_index_display_names(df_row: pd.Series) -> str:
    names_that_need_changing = [{
        "org_fk":        "The Fund For Peace",
        "main_name_fk":  "Fragile State Index",
        "index_name_fk": "Total",
        "new_name":      "Fragile State Index - Total"
    },
    ]

    for sub_name in names_that_need_changing:
        if sub_name["org_fk"] == df_row["org_fk"] and sub_name["main_name_fk"] == df_row["main_name_fk"] and sub_name["index_name_fk"] == df_row["index_name_fk"]:
            return sub_name["new_name"]

    return df_row["index_name_fk"]


def clean_list_edges(lst):
    """
    Removes empty string elements ("") from the beginning and end of a list.

    Parameters:
    lst (list): The list to clean.

    Returns:
    list: The cleaned list with no empty string elements at the beginning or end.
    """
    while lst and lst[0] == "":
        lst.pop(0)
    while lst and lst[-1] == "":
        lst.pop()
    return lst


def plot_index_values(df_row, method, align):
    st.markdown(f"##### {df_row['org_fk']}")
    #st.markdown(f"### {substitute_index_display_names(df_row)}")
    st.markdown(f"### {df_row['index_name_fk']}")

    # Combine values into a DataFrame
    merged_df = combine_values(df_row)

    values_a = round_list_items(replace_item_in_list(list(merged_df["Value_A"]), "nan", ""))
    values_b = round_list_items(replace_item_in_list(list(merged_df["Value_B"]), "nan", ""))
    
    if method != "" or method == "Raw Representation":
        values_a, values_b = apply_method_on_plots(method, values_a, values_b)
    
    alt_x_values = merged_df["Year"].tolist()
    
    if align:
        values_a = clean_list_edges(values_a)
        values_b = clean_list_edges(values_b)
        
        alt_x_values = ["Year " + str(x_val + 1) for x_val in range(len(merged_df["Year"].tolist()) - 1)]

    country_a = df_row["country_a_id_fk"] # db.get_value_by_id("country", df_row["country_a_id_fk"], "name_1")
    country_b = df_row["country_b_id_fk"] # db.get_value_by_id("country", df_row["country_b_id_fk"], "name_1")

    # Prepare data for ECharts
    option = {
        "title": {
            #"text": df_row["index_name"],
            "subtext": "Correlation: " + str(round(float(df_row["correlation"]) * 100, 2)) + "%",
            #"sublink": "http://example.com/",
        },
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": alt_x_values if align else merged_df["Year"].tolist(),
        },
        "tooltip": {"trigger": "axis"},
        # "tooltip": {
        #     "trigger": "axis",
        #     "axisPointer": {"type": "shadow"},
        #     "formatter": JsCode(
        #         "function(params){var tar;if(params[1].value!=='-'){tar=params[1]}else{tar=params[0]}return tar.name+'<br/>'+tar.seriesName+' : '+tar.value}"
        #     ).js_code,
        # },
        "legend": {"data": [country_a, country_b]},
        "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
        #"toolbox": {"feature": {"saveAsImage": {}}}, <<< add image saving function + watermark
        "yAxis": {"type": "value"},
        "series": [
            {
                #"areaStyle": {},
                "name": country_a ,
                #"label": {"show": True},
                "data": values_a, 
                "type": "line", # "bar"
                "name": country_a, 
                "emphasis": {"focus": "series"}
            }, 
            {
                #"areaStyle": {}
                "name": country_b,
                #"label": {"show": True},
                "data": values_b, 
                "type": "line", # "bar"
                "name": country_b,
                "emphasis": {"focus": "series"}
            }
        ],
    }
    events = {
        #"click": "function(params) { console.log(params.name); return params.name }",
        #"dblclick":"function(params) { return [params.type, params.name, params.value] }"
    }


    st_echarts(options = option, events = events, height = "400px", width = "100%", key = df_row["index_name_fk"])


def index_to_base_year(list1, list2):
    # Helper function to perform indexing on a single list
    def index_list(lst):
        base_year_value = next((float(val) for val in lst if val), None)
        if base_year_value is None or base_year_value == 0:
            raise ValueError("Base year value cannot be zero or missing")
        return [((float(val) / base_year_value) * 100 if val else None) for val in lst]

    # Check if lists are not empty
    if not list1 or not list2:
        raise ValueError("Lists must be non-empty")

    indexed_list1 = replace_item_in_list(index_list(list1), "nan", "")
    indexed_list2 = replace_item_in_list(index_list(list2), "nan", "")

    return indexed_list1, indexed_list2


def normalize_lists(list_a, list_b):
    # Convert string values to numbers, replacing empty strings with NaN
    numeric_a = pd.to_numeric(list_a, errors='coerce')
    numeric_b = pd.to_numeric(list_b, errors='coerce')

    # Convert numpy arrays to pandas Series
    series_a = pd.Series(numeric_a)
    series_b = pd.Series(numeric_b)

    # Combine Series to find global min and max
    combined_numeric = pd.concat([series_a, series_b])

    min_val = combined_numeric.min()
    max_val = combined_numeric.max()

    # Apply normalization, replacing NaN with empty strings
    normalized_a = [(x - min_val) / (max_val - min_val) if not pd.isna(x) else "" for x in numeric_a]
    normalized_b = [(x - min_val) / (max_val - min_val) if not pd.isna(x) else "" for x in numeric_b]

    return normalized_a, normalized_b


def standardize_lists(list_a, list_b):
    # Convert string values to numbers, replacing empty strings with NaN
    numeric_a = pd.to_numeric(list_a, errors='coerce')
    numeric_b = pd.to_numeric(list_b, errors='coerce')

    # Convert numpy arrays to pandas Series
    series_a = pd.Series(numeric_a)
    series_b = pd.Series(numeric_b)

    # Combine Series to calculate global mean and standard deviation
    combined = pd.concat([series_a, series_b]).dropna()
    mean = combined.mean()
    std_dev = combined.std()

    # Apply standardization, replacing NaN with empty strings
    standardized_a = [(x - mean) / std_dev if not pd.isna(x) else "" for x in numeric_a]
    standardized_b = [(x - mean) / std_dev if not pd.isna(x) else "" for x in numeric_b]

    return standardized_a, standardized_b


def logarithmic_scaling(list_a, list_b):
    numeric_a = pd.to_numeric(list_a, errors = "coerce")
    numeric_b = pd.to_numeric(list_b, errors = "coerce")

    log_scaled_a = [math.log(x) if x > 0 and not pd.isna(x) else None for x in numeric_a]
    log_scaled_b = [math.log(x) if x > 0 and not pd.isna(x) else None for x in numeric_b]

    log_scaled_a = replace_item_in_list(log_scaled_a, "nan", "")
    log_scaled_b = replace_item_in_list(log_scaled_b, "nan", "")

    return log_scaled_a, log_scaled_b


def calculate_growth_rates(list_a, list_b):
    numeric_a = pd.to_numeric(list_a, errors = "coerce")
    numeric_b = pd.to_numeric(list_b, errors = "coerce")

    growth_rates_a = [(numeric_a[i] - numeric_a[i - 1]) / numeric_a[i - 1] if i != 0 and not pd.isna(numeric_a[i]) and not pd.isna(numeric_a[i - 1]) else None for i in range(len(numeric_a))]
    growth_rates_b = [(numeric_b[i] - numeric_b[i - 1]) / numeric_b[i - 1] if i != 0 and not pd.isna(numeric_b[i]) and not pd.isna(numeric_b[i - 1]) else None for i in range(len(numeric_b))]

    growth_rates_a = replace_item_in_list(growth_rates_a, "nan", "")
    growth_rates_b = replace_item_in_list(growth_rates_b, "nan", "")

    return growth_rates_a, growth_rates_b


def apply_method_on_plots(method, values_a, values_b):
    if method == "Normalize":
        return normalize_lists(values_a, values_b)
    elif method == "Standardize":
        return standardize_lists(values_a, values_b)
    elif method == "Base Year Indexing":
        return index_to_base_year(values_a, values_b)
    elif method == "Logarithmic Scaling":
        return logarithmic_scaling(values_a, values_b)
    elif method == "Growth Rates":
        return calculate_growth_rates(values_a, values_b)
    return values_a, values_b


def visualize_table(df, display_message, params_validation):
    if df is not None and len(df) > 0 and not params_validation:
        st.markdown(display_message)

        df = final_touches_to_df(df)

        ## TODO improve sector fileration
        ###################################################################################################
        unique_sectors = sorted(set(x for l in df["Sectors"] for x in l))
        selected_sectors = st.multiselect("Filter based on Sectors:", unique_sectors)
        if selected_sectors:
            df = df[df["Sectors"].apply(lambda x: all(sector in x for sector in selected_sectors))]


        # # Initialize session state for selected sectors if not already done
        # if "selected_sectors" not in st.session_state:
        #     st.session_state.selected_sectors = []

        # # Function to filter DataFrame based on selected sectors
        # def filter_df_by_sectors(df, sectors):
        #     if sectors:
        #         return df[df["Sectors"].apply(lambda x: all(sector in x for sector in sectors))]
        #     return df

        # # Always start with the original DataFrame to determine selectable options
        # filtered_df = filter_df_by_sectors(df, st.session_state.selected_sectors)

        # # Determine selectable options based on the filtered DataFrame
        # selectable_options = sorted(set(x for l in filtered_df["Sectors"] for x in l))

        # # Update multiselect with selectable options (includes previously selected sectors)
        # selected_sectors = st.multiselect("Filter based on sectors:", options=selectable_options, default=st.session_state.selected_sectors)

        # # Update session state with the latest selection
        # st.session_state.selected_sectors = selected_sectors

        # # Refilter DataFrame based on the updated selection
        # df = filter_df_by_sectors(df, selected_sectors)
        ###################################################################################################

        flags_column                                   = "Flags"
        country_b_column                               = [col for col in list(df) if "has Patterns with" in col][0]
        country_b                                      = country_b_column.split(" ")[0]
        starting_year_column_a, starting_year_column_b = [col for col in list(df) if "Starting Year" in col]
        sectors_column                                 = "Sectors"
        pattern_length_column                          = "Pattern Length"
        number_of_indexes_column                       = "Number of Indexes"
        organizations_column                           = "Organizations"
        correlation_column                             = "Correlation"
        pattern_power_score_column                     = "Pattern Power Score"

        st.dataframe(
            df, # dataframe_explorer(df, case = False), 
            column_config = {
                ## TODO save tips strings in the tips.py script
                country_b_column:           st.column_config.Column(help = "All the **countries** " + country_b + " currently has patterns with"), 
                starting_year_column_a:     st.column_config.NumberColumn(format = "%d", help = "At which **year** these patterns start at for " + country_b),
                starting_year_column_b:     st.column_config.NumberColumn(format = "%d", help = "At which **year** these patterns start at for the second country"),
                pattern_length_column:      st.column_config.NumberColumn(help = "**Measure of Length**: **How long** the patterns are in terms of **years**"),
                number_of_indexes_column:   st.column_config.NumberColumn(help = "**Measure of Strength**: how many **indexes** each pattern has"),
                organizations_column:       st.column_config.NumberColumn(help = "How many **organizations** are behind the indexes in these patterns"),
                correlation_column:         st.column_config.Column(help = "**Measure of Strength**: The Average **correlation** of all indexes"),
                pattern_power_score_column: st.column_config.NumberColumn(help = "This metric summarizes **'Pattern Length'**, **'Number of Indexes'** and **'Correlation'**"),
                sectors_column:             st.column_config.ListColumn(
                    sectors_column,
                    help  = "**Sectors** these patterns cover",
                    width = "medium"
                )
            },
            use_container_width = True
        )


def visualize_plots(df, five_params, page_cols, method, align):
    if isinstance(df, pd.DataFrame) and len(df) > 0 and validate_five_params(five_params):
        # if not warnings.empty:
        #     st.markdown(f"### {country_a} can Learn from These Past Patterns")
        #     st.dataframe(warnings[[
        #         DISPLAY_DF_COUNTRY_B_RENAME,
        #         DISPLAY_DF_START_YEAR_A_RENAME,
        #         DISPLAY_DF_START_YEAR_B_RENAME,
        #         "Year Gap",
        #         DISPLAY_DF_PATTERN_LENGTH_RENAME,
        #         DISPLAY_DF_NUMBER_OF_INDEXES_RENAME,
        #         DISPLAY_DF_AVERAGE_CORRELATION_RENAME,
        #         DISPLAY_DF_PATTERN_POWER_SCORE_RENAME
        #         ]], use_container_width = True)
        #graphs_rows = []
        i = 1
        for _, row in df.iterrows():
            #graphs_rows.append(row)
            if i == 1:
                i = 2
                with page_cols[0]:
                    plot_index_values(row, method, align)
            elif i == 2:
                i = 3
                with page_cols[1]:
                    plot_index_values(row, method, align)
            elif i == 3:
                i = 1
                with page_cols[2]:
                    plot_index_values(row, method, align)


def categorize_indexes(df):
    sector_mapping = {
        "Investments": INVESTMENTS_SECTOR,
        "Trade": TRADE_SECTOR,
        "Finance & \nEconomy": FINANCE_ECONOMY_SECTOR,
        "Military": MILITARY_SECTOR,
        "Human Rights & \nDevelopment": HUMAN_RIGHTS_DEVELOPMENT,
        "Sovereignty": SOVEREIGNTY,
        "Social": SOCIAL_SECTOR,
        "Political \n& State": POLITICAL_STATE_SECTOR,
        "Other": []
    }

    # Reverse mapping for easier lookup
    index_to_sector = {}
    for sector, indexes in sector_mapping.items():
        for index in indexes:
            index_to_sector[index] = sector

    # Add a new column for sector
    df["Sector"] = df["index_name_fk"].apply(lambda x: index_to_sector.get(x, "Other"))
    return df


def aggregate_data_for_chart(df):
    categorized_df = categorize_indexes(df)
    sector_counts = categorized_df["Sector"].value_counts().reset_index()
    sector_counts.columns = ["Sector", "Count"]
    return sector_counts


def generate_doughnut_chart(df):
    sector_counts = aggregate_data_for_chart(df)
    chart_data = [{"value": row['Count'], "name": row['Sector']} for index, row in sector_counts.iterrows()]

    options = {
        "tooltip": {"trigger": "item"},
        "legend": {"top": "5%", "left": "center", "textStyle": {"color": "#808080"}},  # Making legend text white as well
        "series": [
            {
                "name": "Sectors",
                "type": "pie",
                "radius": ["40%", "70%"],
                "avoidLabelOverlap": False,
                "itemStyle": {
                    "borderRadius": 10,
                    "borderColor": "#fff",
                    "borderWidth": 2,
                },
                "label": {
                    "show": False,
                    "position": "center",
                    "color": "#808080"  # Making label text white
                },
                "emphasis": {
                    "label": {
                        "show": True,
                        "fontSize": "30",
                        "fontWeight": "bold",
                        "color": "#808080"  # Making emphasized label text white
                    }
                },
                "labelLine": {"show": False},
                "data": chart_data,
            }
        ],
    }
    st_echarts(options=options, height="500px")


def couple_countries_dashboard(five_params, countries, display_df, pattern_power_score, countries_df, plotting_df):
    country_a_id, country_b_id, patt_len, start_year_a, start_year_b = five_params
    country_a, country_b                                             = countries

    if validate_five_params(five_params):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            #with st.container(border=True, height = 672):
            ## Pattern Partners Country A
            st.markdown("#### Pattern Partners")
            df = get_country_b_counts_for_country_a(country_a_id, country_a, countries_df)
            df.set_index("Country", inplace = True)
            st.dataframe(df, use_container_width = True, height = 430) #, height=650)
        with col2: 
            #with st.container(border = True, height = 672):
            ## Country A
            with st.container(border = True):
                st.image(f"https://flagcdn.com/h240/{get_alpha2_by_name(country_a).lower()}.png")
            st.markdown(f"<h2 style='text-align: center;'>{country_a}</h2>", unsafe_allow_html = True)
            st.markdown(f"<h3 style='text-align: center;'>{str(int(start_year_a))} - {str(int(start_year_a) + patt_len)}</h3>", unsafe_allow_html = True)
        with col3:
            ## Mid screen: Indexes
            #st.markdown(f"<h1 style='text-align: center;'>{len(display_df)}</h1>", unsafe_allow_html = True)
            #st.markdown("<h4 style='text-align: center;'>Indexes</h4>", unsafe_allow_html = True)
            #with st.container(border=True):
            # PPS
            st.markdown(f"<h2 style='text-align: center;'>{pattern_power_score}</h2>", unsafe_allow_html = True)
            st.markdown("<h4 style='text-align: center;'>Pattern Power Score</h4>", unsafe_allow_html = True)
            # pie chart
            generate_doughnut_chart(plotting_df)
        with col4:
            #with st.container(border=True, height = 672):
            ## Country B
            with st.container(border = True):
                st.image(f"https://flagcdn.com/h240/{get_alpha2_by_name(country_b).lower()}.png")    
            st.markdown(f"<h2 style='text-align: center;'>{country_b}</h2>", unsafe_allow_html = True)
            st.markdown(f"<h3 style='text-align: center;'>{str(int(start_year_b))} - {str(int(start_year_b) + patt_len)}</h3>", unsafe_allow_html = True)
        with col5:
            #with st.container(border=True, height = 672):
            ## Pattern Partners Country B
            st.markdown("#### Pattern Partners")
            df = get_country_b_counts_for_country_a(country_b_id, country_b, countries_df)
            df.set_index("Country", inplace = True)
            st.dataframe(df, use_container_width = True, height = 430)
        
        #st.markdown("___")


def display_timeline(five_params, events_df, country_a, start_year_a, country_b, start_year_b, patt_len):
    if validate_five_params(five_params):
        # Alt: https://github.com/giswqs/streamlit-timeline
        # https://github.com/innerdoc/nlp-history-timeline
        # https://github.com/innerdoc/streamlit-timeline
        # https://pypi.org/project/streamlit-timeline/
        # https://timeline.knightlab.com/docs/json-format.html#json-slide
        st.markdown("___")
        # with open(r"C:\Users\Amin\Desktop\trojan\trojan 2.0\data\events\JSON\sample.json", "r") as f:
        #     data = f.read()
        
        events = get_events(
            events_df, 
            country_a, 
            (start_year_a, start_year_a + patt_len),
            country_b,
            (start_year_b, start_year_b + patt_len)
        )
        
        st_t.timeline(events, height = 750)
        st.markdown("___")


def display_timeline(five_params, events_df, country_a, start_year_a, country_b, start_year_b, patt_len):
    if validate_five_params(five_params):
        # Alt: https://github.com/giswqs/streamlit-timeline
        # https://github.com/innerdoc/nlp-history-timeline
        # https://github.com/innerdoc/streamlit-timeline
        # https://pypi.org/project/streamlit-timeline/
        # https://timeline.knightlab.com/docs/json-format.html#json-slide
        
        # with open(r"C:\Users\Amin\Desktop\trojan\trojan 2.0\data\events\JSON\sample.json", "r") as f:
        #     data = f.read()
        
        events = get_events(
            events_df, 
            country_a, 
            (start_year_a, start_year_a + patt_len),
            country_b,
            (start_year_b, start_year_b + patt_len)
        )

        if events is not None:
            st.markdown("___")
            st_t.timeline(events, height = 750)
            st.markdown("___")


def get_events(df, country_a, year_range_a, country_b, year_range_b):
    if country_a not in list(set(df["Country"])) or country_b not in list(set(df["Country"])):
        return None

    # Filter data for both countries within their respective year ranges
    df_filtered = df[((df["Country"] == country_a) & (df["Year"].between(*year_range_a))) |
                     ((df["Country"] == country_b) & (df["Year"].between(*year_range_b)))]
    
    # Sort by year for proper chronological order in the timeline
    df_filtered.sort_values(by='Year', inplace=True)
    
    # Combining Events together
    df_filtered["Event"] = "<b>" + df_filtered["Raw Event"].fillna("Missing Event").astype(str) + "</b>" + ": " + df_filtered["Desc"].fillna("No Description Available").astype(str) + "<br>"
    # df_filtered["Event"] = "<b>" + df_filtered["Raw Event"] + "</b>" + ": " + df_filtered["Desc"] + "<br>"

    formatted_df = df_filtered.groupby(["Year", "Country"])["Event"]
    formatted_df = formatted_df.apply("".join).reset_index()
    formatted_df = formatted_df.sort_values(by=["Year", "Country"])
    
    # Initialize the JSON structure
    timeline = {
        "title": {
            "media": {
              "url": "",  # URL to a relevant image or left empty
              "caption": "",
              "credit": ""
            },
            "text": {
              "headline": f"Timeline of Events:<br>{country_a} & {country_b}",
              "text": "" #f"<p>An exploration of key events in {country_a} and {country_b} over selected years.</p>"
            }
        },
        "events": []
    }
    

    # Populate the events
    for _, row in formatted_df.iterrows():
        event = {
            "start_date": {
                "year": str(row["Year"])
            },
            "text": {
                "headline": "<b>" + row["Country"] + "</b>",
                "text": row["Event"]
            },
            "media": {
                "url": "",  # Optional: URL to an image or video related to the event
                "caption": "",
                "credit": ""
            }
        }
        timeline["events"].append(event)
    
    return timeline

