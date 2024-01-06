import math
from streamlit_extras.customize_running import center_running
import pandas                           as pd
import streamlit                        as st


st.set_page_config(layout = "wide") #, page_title = "Trojan Geopolitics", page_icon = "📈")
center_running()
st.title("Pattern Power Rankings")
old_ppr_df = pd.read_csv("data/ppr/old_ppr.csv")
new_ppr_df = pd.read_csv("data/ppr/new_ppr.csv")





def show_search_page():
    
    ppr_df = compare_rankings(old_ppr_df, new_ppr_df)
    st.dataframe(ppr_df, use_container_width = True)

show_search_page()
