import math
import numpy as np
import pandas as pd
from constant.constant import EVENTS_CSVS_FOLDER_PATH
from constant.sectors import SECTOR_MAPPING
from constant.tips import TIP_TRANSFORMATION_CAPTIONS, TIP_TRANSFORMATION_RADIO
from database.db_manager import get_alpha2_by_name, get_country_b_counts_for_country_a
from utils.utils import check_file_exists, combine_values, final_touches_to_df, get_correlated_events_details, get_index_metadata, replace_item_in_list, round_list_items, validate_five_params
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


def get_annotations(similar_events):
    annotations_a = []
    annotations_b = []
    for _, event_row in similar_events.iterrows():
        # Annotations for Country A
        annotations_a.append({
            "type": "line",
            "xAxis": str(event_row['Year A']),
            "name": event_row['Event'],
            "label": {
                "show": True,
                "formatter": event_row['Event']
            },
            "lineStyle": {
                "color": "red",
                "type": "solid"
            }
        })
        # Annotations for Country B
        annotations_b.append({
            "type": "line",
            "xAxis": str(event_row['Year B']),
            "name": event_row['Event'],
            "label": {
                "show": True,
                "formatter": event_row['Event']
            },
            "lineStyle": {
                "color": "blue",
                "type": "solid"
            }
        })
    return annotations_a, annotations_b


def plot_index_values(df_row):
    country_a = df_row['country_a_id_fk']
    country_b = df_row['country_b_id_fk']

    # st.write(df_row)
    with st.expander(df_row["index_name_fk"], expanded=True):
        st.markdown(f"##### {df_row['org_fk']}")
        #st.markdown(f"### {substitute_index_display_names(df_row)}")
        st.markdown(f"### {df_row['index_name_fk']}")

        merged_df = combine_values(df_row)
        values_a = round_list_items(replace_item_in_list(list(merged_df["Value_A"]), "nan", ""))
        values_b = round_list_items(replace_item_in_list(list(merged_df["Value_B"]), "nan", ""))

        plot_mods, plot_events = st.columns(2)

        with plot_mods:
            with st.popover("Modify plot representation"):
                align = False
                if df_row["start_year_a_fk"] != df_row["start_year_b_fk"]:
                    align = st.toggle("Align Index Couples", key = "toggle_" + df_row["index_name_fk"], help = "Aligns both index segments to start from the same year. ")

                method = st.radio(
                    "Choose Representation method", 
                    ["Raw Representation", "Normalize", "Standardize", "Base Year Indexing", "Logarithmic Scaling", "Growth Rates"],
                    key = f"temp_{df_row['index_name_fk']}",
                    captions=TIP_TRANSFORMATION_CAPTIONS,
                    help=TIP_TRANSFORMATION_RADIO
                )
        #similar_events = get_correlated_events_details(df_row)
        # if len(similar_events) > 0:
        #     with plot_events:
        #         add_similar_events = st.toggle(
        #             "Add Similar Events", 
        #             key = "toggle_" + df_row["index_name_fk"] + str(df_row["start_year_b_fk"]), 
        #             help = "Highlights similar pattern events in the plot"
        #         )
        
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
                    "emphasis": {"focus": "series"},
                    # "markLine": {
                    #     "symbol": ["none", "none"],  # Hides the markLine symbol
                    #     "data": []  # We will populate this with our event data
                    #     },
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

        # if add_similar_events:
        #     annotations_a, annotations_b = get_annotations(similar_events)
        # 
        #     if not option.get('xAxis').get('axisPointer'):
        #         option['xAxis']['axisPointer'] = {'show': True}
        #     if not option.get('annotations'):
        #         option['annotations'] = []

        #     option['annotations'].extend(annotations_a)
        #     option['annotations'].extend(annotations_b)

        events = {
            #"click": "function(params) { console.log(params.name); return params.name }",
            #"dblclick":"function(params) { return [params.type, params.name, params.value] }"
        }

        st_echarts(options = option, events = events, height = "400px", width = "100%", key = df_row["index_name_fk"])

        metadata = get_index_metadata(df_row)
        if metadata is not None:
            description, tips, source, citation = metadata
            description_col, tips_col, source_col = st.columns([1, 1, 1], gap = "small")
            with description_col:
                with st.popover("Description"):
                    st.markdown(description)
            with tips_col:
                with st.popover("Tips 💡"):
                    st.markdown(tips)
            with source_col:
                with st.popover("Source 🔗"):
                    st.markdown(source)
            st.markdown("""<style>.big-font {font-size:12px !important;}</style>""", unsafe_allow_html = True)
            st.markdown(f'<p class="big-font">{citation}</p>', unsafe_allow_html = True)
        else:
            coming_soon_message = "Index metadata coming soon ⏳"
            st.markdown("""<style>.big-font {font-size:12px !important;}</style>""", unsafe_allow_html = True)
            st.markdown(f'<p class="big-font">{coming_soon_message}</p>', unsafe_allow_html = True)


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


def visualize_table(df, display_message, params_validation, country_a, country_b):
    if df is not None and len(df) > 0 and not params_validation:
        st.markdown(display_message)

        df = final_touches_to_df(df)

        if "Sectors" in list(df):
            df["Sectors"] = df["Sectors"].apply(lambda x: sorted(set(["Other" if i == "Unknown" else i for i in x]), key=lambda y: (y == "Other", y)))
            unique_sectors   = sorted(set(x for l in df["Sectors"] for x in l))
            selected_sectors = st.multiselect("Filter based on Sectors:", unique_sectors)
            if selected_sectors:
                df = df[df["Sectors"].apply(lambda x: all(sector in x for sector in selected_sectors))]

        #flags_column                                   = "Flags"
        country_b_column                               = [col for col in list(df) if "has Patterns with" in col][0]
        #country_b                                      = country_b_column.split(" ")[0]
        starting_year_column_a, starting_year_column_b = [col for col in list(df) if "Starting Year" in col]
        sectors_column                                 = "Sectors"
        pattern_length_column                          = "Pattern Length"
        number_of_indexes_column                       = "Number of Indexes"
        organizations_column                           = "Organizations"
        correlation_column                             = "Correlation"
        pattern_power_score_column                     = "Pattern Power Score"
        events_similarity_score                        = "ES Score"
        events_similarity_count                        = "event_correlation_count"
        similar_event_year_a                           = "similar_event_year_a"
        similar_raw_event                              = "similar_raw_event"
        similar_event_year_b                           = "similar_event_year_b"

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
                ),
                events_similarity_score:   st.column_config.NumberColumn(format = "%d", help = "Indicates similarity score between index segments of this single-index pattern. "),
                events_similarity_count:   st.column_config.NumberColumn(label = "ES Count", help = "Indicates how many events correlate in this pattern. "),
                similar_event_year_a:      st.column_config.NumberColumn(label = f"Similar Event Years - {country_a}", format = "%d", help = f"List of years of the similar events for {country_a}"),
                similar_raw_event:         st.column_config.Column(label = "Similar Events", help = f"List of similar events between in this pattern between {country_a} and {country_b}"),
                similar_event_year_b:      st.column_config.NumberColumn(label = f"Similar Event Years - {country_b}", format = "%d", help = f"List of years of the similar events for {country_b}")
            },
            use_container_width = True
        )


def visualize_plots(df, five_params):
    if isinstance(df, pd.DataFrame) and len(df) > 0 and validate_five_params(five_params):
        if len(df) >= 5:
            col1, col2, col3 = st.columns(3)
            i = 1
            for _, row in df.iterrows():
                #graphs_rows.append(row)
                if i == 1:
                    i = 2
                    with col1:
                        plot_index_values(row)
                elif i == 2:
                    i = 3
                    with col2:
                        plot_index_values(row)
                elif i == 3:
                    i = 1
                    with col3:
                        plot_index_values(row)
        else:
            col1, col2 = st.columns(2)
            i = 1
            for _, row in df.iterrows():
                #graphs_rows.append(row)
                if i == 1:
                    i = 2
                    with col1:
                        plot_index_values(row)
                elif i == 2:
                    i = 1
                    with col2:
                        plot_index_values(row)


def categorize_indexes(df):
    # Reverse mapping for easier lookup
    index_to_sector = {}
    for sector, indexes in SECTOR_MAPPING.items():
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
            st.markdown(f"<h3 style='text-align: center;'>{str(int(start_year_a))} - {str(int(start_year_a) + patt_len - 1)}</h3>", unsafe_allow_html = True)
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
            st.markdown(f"<h3 style='text-align: center;'>{str(int(start_year_b))} - {str(int(start_year_b) + patt_len - 1)}</h3>", unsafe_allow_html = True)
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


def display_timeline(five_params, country_a, start_year_a, country_b, start_year_b, patt_len):
    if validate_five_params(five_params):
        # Alt: https://github.com/giswqs/streamlit-timeline
        # https://github.com/innerdoc/nlp-history-timeline
        # https://github.com/innerdoc/streamlit-timeline
        # https://pypi.org/project/streamlit-timeline/
        # https://timeline.knightlab.com/docs/json-format.html#json-slide
        
        # with open(r"C:\Users\Amin\Desktop\trojan\trojan 2.0\data\events\JSON\sample.json", "r") as f:
        #     data = f.read()
        
        events = get_events(
            country_a, 
            (start_year_a, start_year_a + patt_len),
            country_b,
            (start_year_b, start_year_b + patt_len)
        )
        if events is not None:
            st.markdown("___")
            st_t.timeline(events, height = 750)
            st.markdown("___")


def get_events(country_a, year_range_a, country_b, year_range_b):
    EVENTS_CSVS_SOURCE_PATH = r"/workspaces/qgi/data/events/"




    st.write(country_a)
    st.write(country_b)

    st.write(EVENTS_CSVS_SOURCE_PATH, country_a + ".csv")
    st.write(EVENTS_CSVS_SOURCE_PATH, country_b + ".csv")

    st.write("////////////////////////////////////////////////////////////")
    st.write(check_file_exists(EVENTS_CSVS_SOURCE_PATH, country_a + ".csv"))
    st.write(check_file_exists(EVENTS_CSVS_SOURCE_PATH, country_b + ".csv"))
    st.write("////////////////////////////////////////////////////////////")

    if not (check_file_exists(EVENTS_CSVS_SOURCE_PATH, country_a + ".csv") and check_file_exists(EVENTS_CSVS_SOURCE_PATH, country_b + ".csv")):
        return None

    events_a = pd.read_csv(EVENTS_CSVS_SOURCE_PATH + country_a + ".csv")
    events_b = pd.read_csv(EVENTS_CSVS_SOURCE_PATH + country_b + ".csv")

    events_a = events_a[events_a["Year"].between(*year_range_a)]
    events_b = events_b[events_b["Year"].between(*year_range_b)]

    df_filtered = pd.concat([events_a, events_b], ignore_index = True)
    
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

