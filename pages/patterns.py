"""Patterns script"""

from streamlit_extras.customize_running import center_running
from streamlit_modal import Modal
import streamlit as st
from constant.constant import PPR_PATH
from utils.patterns import compare_rankings, extract_and_rank_patterns_for_country
from plotting.plotting import couple_countries_dashboard, display_timeline, visualize_plots, visualize_table
from utils.utils import (
    get_country_id,
    apply_advanced_filters,
    get_country_a_from_user,
    get_country_b_and_id_from_user,
    get_pattern_length_from_user,
    get_pattern_power_score,
    get_start_year_a,
    get_start_year_b,
    prepare_display_df_for_viz,
    process_display_dataframe,
    rename_display_df_columns,
    update_names_of_main_and_index_names,
    validate_five_params)


def patterns_portal():
    center_running()

    ## Splash window
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


    ppr_df = compare_rankings(PPR_PATH, rows_count = 95000, show_event_cols = False)


    with st.expander("You can take some inspiration from the Pattern Power Ranking table here"):
        # unique_sectors = sorted(set(x for l in ppr_df["Sectors"] for x in l))
        # selected_sectors = st.multiselect("Filter based on Sectors:", unique_sectors)
        # if selected_sectors:
        #     ppr_df = ppr_df[ppr_df["Sectors"].apply(lambda x: all(sector in x for sector in selected_sectors))]
        
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

    couple_countries_dashboard(five_params, couple_of_countries, display_df, pattern_power_score, countries_df, plotting_df)

    with st.expander("Timeline of events for " + country_a + " and " + country_b):
        display_timeline(five_params, country_a, start_year_a, country_b, start_year_b, patt_len)

    visualize_table(display_df, display_message, validate_five_params(five_params), country_a, country_b)
    visualize_plots(plotting_df, five_params)
