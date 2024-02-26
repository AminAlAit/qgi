"""main script"""

import sys
import subprocess
import pandas as pd
import streamlit as st
from utils.patterns import compare_rankings, extract_and_rank_patterns_for_country
from plotting.plotting import couple_countries_dashboard, visualize_plots, visualize_table
from utils.utils import (
    get_country_id,
    apply_advanced_filters,
    get_country_a_from_user,
    get_country_b_and_id_from_user,
    get_pattern_length_from_user,
    get_pattern_power_score,
    get_start_year_a,
    get_start_year_b,
    plotting_transformations,
    prepare_display_df_for_viz,
    process_display_dataframe,
    rename_display_df_columns,
    run_requirements,
    update_names_of_main_and_index_names,
    validate_five_params)
def install_package(package):
    """dummy docstring"""
    #subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
install_package("streamlit-echarts")
install_package("streamlit-extras")
install_package("streamlit-lottie")
run_requirements()
from streamlit_extras.customize_running import center_running
from st_pages import show_pages_from_config
import sys
import subprocess
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
install_package("streamlit-modal")
from streamlit_modal import Modal


## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all magic strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings
st.set_page_config(layout = "wide", page_title = "QG Intelligence", page_icon = "📈")
center_running()

show_pages_from_config()

#st.sidebar.markdown("# QG Intelligence")
old_ppr_df = pd.read_csv("data/ppr/old_ppr.csv")
new_ppr_df = pd.read_csv("data/ppr/new_ppr.csv")


if "show_patterns_popup" not in st.session_state:
    st.session_state["show_patterns_popup"] = True
if st.session_state["show_patterns_popup"]:
    with Modal(key = "Demo Key", title = "Welcome to the Patterns Portal! :wave:").container():
        st.markdown("""
            Before browsing the millions of patterns, here are some some tips on how to do so:

            Every pattern is composed of 5 elements: 
            - Country A: select any country in the beginning, so you can see who has patterns with it.
            - Country B: then, you can select which country to pair with.
            - Pattern Length (in years): then, you can refine your search by selecting the pattern's length.
            - Starting Year A: select when tha pattern should start for Country A.
            - Starting Year B: finally, select when the pattern should start for Country B.
            
            Inputting these 5 key elements, will present you with the pattern dashboard. Go crazy! 🤘
        """)
    st.session_state["show_patterns_popup"] = False


def show_search_page():
    with st.expander("Hey, welcome to **QG Intelligence**!"):
        st.markdown("""
            # Welcome to QG Intelligence

            QGI is a powerful tool designed to demonstrate and visualise over a **million** patterns 
            between any two countries, providing insights into political, economic and social 
            dynamics. A pattern, in our context, is a set of correlations across various indexes 
            that indicate a significant relationship between two countries over a specific period.

            ### Understanding Patterns
            A pattern between two countries comprises five key elements:
            - **Country A Name:** The initiating country in the pattern.
            - **Country B Name:** The responding country in the pattern.
            - **Pattern Length (in years):** The duration over which the pattern extends.
            - **Starting Year for Country A:** The year from which the pattern begins for Country A.
            - **Starting Year for Country B:** The corresponding starting year for Country B.

            Each pattern is supported by at least two indexes that highly correlate during the 
            pattern length, illustrating synchronous, mirrored activities and trends in sectors 
            such as Economy, Finance, Investments, Sovereignty, Society, Human Rights, Military, 
            and Energy, among others.

            ### How to Use QGI
            To explore the geopolitical patterns:
            1. **Expand the Sidebar Menu:** If not visible, click on the ">" symbol at the top 
                left of the screen to reveal the menu.
            2. **Input Parameters:** Sequentially input Country A, Country B, pattern length, 
                and the starting years for each country. With each input, QGI will fetch and 
                display relevant patterns and their details, allowing for an iterative 
                selection process.

            ### Pattern's Power Score
            The displayed patterns are sorted using a formula that accounts for three metrics, 
            enabling users to discern the most significant relationships quickly.
            The Pattern Power Score is determined by the following three metrics:
            1. **Pattern Length**: The duration of the pattern measured in calendar years.
            2. **Number of Indexes:** The total indexes involved in the pattern.
            3. **Average Correlation:** The mean correlation value of these indexes, signifying 
                the pattern's intensity and coherence.

            For inspiration, you can explore the Pattern Power Ranking in the expander box below 
            this one. 
            
            Good luck in your journey!

        """)
    # Pattern Power Ranking Section
    ppr_df = compare_rankings(old_ppr_df, new_ppr_df)

    with st.expander("You can take some inspiration from the Pattern Power Ranking table here"):
        st.dataframe(ppr_df, use_container_width = True)
    st.markdown("___")

    # Discovery section
    country_a, countries_df                          = get_country_a_from_user()

    display_message                                  = f"\n### All Patterns for {country_a}"
    countries_ids, countries_a                       = list(countries_df["id"]), list(countries_df["country"])

    country_a_id                                     = get_country_id(countries_df, country_a)
    display_df                                       = extract_and_rank_patterns_for_country(country_a_id, country_a)

    DISPLAY_DF_NEW_COLUMN_NAMES                      = rename_display_df_columns(country_a)
    display_df                                       = process_display_dataframe(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, countries_df)
    display_df, min_corr, max_corr, __, ___          = apply_advanced_filters(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, country_a)

    country_b, country_b_id, display_df              = get_country_b_and_id_from_user(display_df, countries_df, DISPLAY_DF_NEW_COLUMN_NAMES, countries_a, countries_ids)
    patt_len, display_message, display_df            = get_pattern_length_from_user(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, country_a, country_b)
    couple_of_countries                              = [country_a, country_b]

    start_year_a, display_message, display_df        = get_start_year_a(display_message, display_df, country_a, country_a_id, country_b, country_b_id, patt_len, DISPLAY_DF_NEW_COLUMN_NAMES, min_corr, max_corr)
    start_year_b, display_df, display_message        = get_start_year_b(display_df, DISPLAY_DF_NEW_COLUMN_NAMES, start_year_a, country_b, display_message, country_a)

    pattern_power_score                              = get_pattern_power_score(display_df, start_year_b, DISPLAY_DF_NEW_COLUMN_NAMES)

    display_df, plotting_df                          = prepare_display_df_for_viz(display_df, country_a, country_b, [country_a_id, country_b_id, patt_len, start_year_a, start_year_b], countries_a, countries_ids, countries_df)
    five_params                                      = [country_a_id, country_b_id, patt_len, start_year_a, start_year_b]
    plotting_df                                      = update_names_of_main_and_index_names(plotting_df, five_params)

    align, method                                    = plotting_transformations(five_params)

    couple_countries_dashboard(five_params, couple_of_countries, display_df, pattern_power_score, countries_df, plotting_df)
    col1, col2, col3 = st.columns(3)
    visualize_table(display_df, display_message, plotting_df, validate_five_params(five_params))
    visualize_plots(plotting_df, five_params, [col1, col2, col3], method, align)

show_search_page()
