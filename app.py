import subprocess
import sys
def install_package(package):
    #subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
install_package("streamlit-echarts")
install_package("streamlit-extras")
install_package("streamlit-lottie")
import pandas as pd
from utils.patterns import compare_rankings, extract_and_rank_patterns_for_country
from plotting.plotting import visualize_plots, visualize_table
from utils.utils import (
    apply_advanced_filters,
    get_country_a_from_user,
    get_country_b_and_id_from_user,
    get_id_by_value,
    get_pattern_length_from_user,
    get_start_year_a,
    get_start_year_b,
    plotting_transformations,
    prepare_display_df_for_viz,
    process_display_dataframe,
    rename_display_df_columns,
    run_requirements,
)
run_requirements()
import streamlit as st
from streamlit_extras.customize_running import center_running
import os


## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings 
st.set_page_config(layout = "wide", page_title = "QG Intelligence", page_icon = "📈")
center_running()


st.sidebar.markdown("# QG Intelligence")
old_ppr_df = pd.read_csv("data/ppr/old_ppr.csv")
new_ppr_df = pd.read_csv("data/ppr/new_ppr.csv")


# def image_to_base64(img_path, output_size = (64, 64)):
#     # Check if the image path exists
#     if os.path.exists(img_path):
#         with Image.open(img_path) as img:
#             img      = img.resize(output_size)
#             buffered = io.BytesIO()
#             img.save(buffered, format = "PNG")
#             return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
#     return ""


def show_search_page():
    # Pattern Power Ranking Section
    #st.title("Pattern Power Rankings")
    ppr_df = compare_rankings(old_ppr_df, new_ppr_df)
    with st.expander("Pattern Power Rankings"):
        st.dataframe(ppr_df, use_container_width = True)
    st.markdown("___")

    # Discovery section
    #db                                               = DatabaseManager()
    col1, col2                                       = st.columns(2)
    country_a, countries_df                          = get_country_a_from_user()
    display_message                                  = f"\n### All Patterns for {country_a}"

    country_a_id                                     = get_id_by_value(countries_df["id"], countries_df["country"], country_a)
    display_df                                       = extract_and_rank_patterns_for_country(country_a_id, country_a)

    DISPLAY_DF_NEW_COLUMN_NAMES                      = rename_display_df_columns(country_a)
    display_df                                       = process_display_dataframe(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, countries_df["country"], countries_df["id"])
    display_df, min_corr, max_corr, min_ind, max_ind = apply_advanced_filters(display_df, DISPLAY_DF_NEW_COLUMN_NAMES)

    country_b, country_b_id, display_df              = get_country_b_and_id_from_user(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, countries_df["country"], countries_df["id"])
    patt_len, display_message, display_df            = get_pattern_length_from_user(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, country_a, country_b)

    start_year_a, display_message, display_df        = get_start_year_a(display_message, display_df, country_a, country_a_id, country_b, country_b_id, patt_len, DISPLAY_DF_NEW_COLUMN_NAMES, min_corr, max_corr, min_ind, max_ind)
    start_year_b, display_df, display_message        = get_start_year_b(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, start_year_a, country_b, display_message, country_a)

    display_df                                       = prepare_display_df_for_viz(display_df, country_a, [country_a_id, country_b_id, patt_len, start_year_a, start_year_b], countries_df["country"], countries_df["id"])

    five_params                                      = [country_a_id, country_a_id, patt_len, start_year_a, start_year_b]
    align, method                                    = plotting_transformations(five_params)

    visualize_table(display_df, display_message)
    visualize_plots(display_df, five_params, col1, col2, method, align)


show_search_page()
