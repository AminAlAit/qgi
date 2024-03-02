"""Dummy docstring"""

import streamlit as st
from utils.utils import get_sorted_countries_list, find_csv_files, FETCHING_INDEXES


INDEXES_ROOT_PATH = r"/workspaces/qgi/data/indexes"
TIP_EXP_COUNTRY = ""
TIP_EXP_INDEX   = ""
TIP_EXP_YEARS_RANGE = ""


# Country names
countries              = get_sorted_countries_list(False)
index_dfs, index_names = FETCHING_INDEXES(find_csv_files(INDEXES_ROOT_PATH))

country                = st.sidebar.selectbox("Country", countries, help = TIP_EXP_COUNTRY)
index_name             = st.sidebar.selectbox("Index", index_names, help = TIP_EXP_INDEX)

df = index_dfs[index_names.index(index_name)]

if len(df) > 0 and country != "" and country in list(df["Country"]):
    df          = df[df["Country"] == country]
    years       = list(set(df["Year"]))
    min_year    = min(years)
    max_year    = max(years)
    years = st.sidebar.slider("Years Range", min_year, max_year, (min_year, max_year), help = TIP_EXP_YEARS_RANGE)
    st.write(years)
    
    st.dataframe(df)
else:
    st.markdown(f"{country} does not have values in {index_name}.")


    # col1, col2 = st.columns(2)
    #with col1:
    