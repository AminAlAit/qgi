"""Dummy docstring"""

import streamlit as st
from utils.utils import get_sorted_countries_list, find_csv_files, FETCHING_INDEXES
from streamlit_extras.customize_running import center_running
from streamlit_echarts import st_echarts


def experimental():

    center_running()
    INDEXES_ROOT_PATH   = r"/workspaces/qgi/data/indexes"
    TIP_EXP_COUNTRY     = ""
    TIP_EXP_INDEX       = ""
    TIP_EXP_YEARS_RANGE = ""


    # Country names
    countries              = get_sorted_countries_list(False)
    index_dfs, index_names = FETCHING_INDEXES(find_csv_files(INDEXES_ROOT_PATH))

    country                = st.sidebar.selectbox("Country", countries, help = TIP_EXP_COUNTRY)
    index_name             = st.sidebar.selectbox("Index", index_names, help = TIP_EXP_INDEX)

    df = index_dfs[index_names.index(index_name)]

    def plot_index_values(df, country):
        df = df.sort_values("Year")
        index_name = df.columns[-1]
        df.set_index('Year', inplace=True)
        st.dataframe(df)
        st.line_chart(df, use_container_width = True) # title=f"{index_name} over Years")

        # correlation = ...
        
        years  = list(df.index)
        values = list(df[index_name])

        option = {
            "title": {
                #"text": df_row["index_name"],
                #"subtext": "Correlation: " + str(correlation) + "%",
                #"sublink": "http://example.com/",
            },
            "xAxis": {
                "type": "category",
                "boundaryGap": False,
                "data": years,
            },
            "tooltip": {"trigger": "axis"},
            # "tooltip": {
            #     "trigger": "axis",
            #     "axisPointer": {"type": "shadow"},
            #     "formatter": JsCode(
            #         "function(params){var tar;if(params[1].value!=='-'){tar=params[1]}else{tar=params[0]}return tar.name+'<br/>'+tar.seriesName+' : '+tar.value}"
            #     ).js_code,
            # },
            "legend": {"data": [country]},
            "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
            #"toolbox": {"feature": {"saveAsImage": {}}}, <<< add image saving function + watermark
            "yAxis": {"type": "value"},
            "series": [
                {
                    #"areaStyle": {},
                    "name": country,
                    #"label": {"show": True},
                    "data": values, 
                    "type": "line", # "bar"
                    "name": country, 
                    "emphasis": {"focus": "series"}
                }, 
                # {
                #     #"areaStyle": {}
                #     "name": country_b,
                #     #"label": {"show": True},
                #     "data": values_b, 
                #     "type": "line", # "bar"
                #     "name": country_b,
                #     "emphasis": {"focus": "series"}
                # }
            ],
        }
        events = {
            #"click": "function(params) { console.log(params.name); return params.name }",
            #"dblclick":"function(params) { return [params.type, params.name, params.value] }"
        }

        st_echarts(options = option, events = events, height = "400px", width = "100%")


    if country != "" and index_name != "":
        if len(df) > 0 and country in list(df["Country"]):
            df          = df[df["Country"] == country]

            # Year filtering
            years       = list(set(df["Year"]))
            min_year    = min(years)
            max_year    = max(years)
            years = st.sidebar.slider("Years Range", min_year, max_year, (min_year, max_year), help = TIP_EXP_YEARS_RANGE)
            df = df[df["Year"] >= years[0]]
            df = df[df["Year"] <= years[1]]

            df = df.drop_duplicates()

            st.markdown(f"### {index_name}")
            #st.markdown(f"### {country}")

            df = df.drop(["Country"], axis = 1)
            plot_index_values(df, country)
            
        else:
            st.markdown(f"### {country} does not have values in {index_name}.")


        # col1, col2 = st.columns(2)
        #with col1:
