## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all magic strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings
## TODO save strings in constant, to avoid magic strings

from utils.utils import switch_country_ids_to_names_for_ppr
import sys
import subprocess
import os

subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-timeline"])

# References: 
# https://discuss.streamlit.io/t/new-package-st-pages-change-page-names-and-icons-in-sidebar-without-changing-filenames/33969/56
# https://st-pages.streamlit.app


# Data Prep
script_path = os.path.abspath(__file__)
# st.write("Script directory:", script_path)

script_dir = os.path.dirname(script_path)
# st.write("Script directory:", script_dir)

# ppr_path = r"/workspaces/qgi/data/ppr/ppr.csv"
# countries_path = r"/workspaces/qgi/data/country.csv"

ppr_path = script_dir + "/data/ppr/ppr.csv"
countries_path = script_dir + "/data/country.csv"

switch_country_ids_to_names_for_ppr(ppr_path, countries_path)

import streamlit as st
from st_pages import Page, add_page_title, show_pages
show_pages(
    [
        Page("pages/0_Base.py",          "Base",               "🌐"),
        Page("pages/1_Patterns.py",      "Patterns",           "📈"),
        # Page("pages/0_Base.py",         "Patterns",           "📈"),
        Page("pages/2_Experimental.py",  "Under Construction", "🚧"),
        Page("pages/3_FAQ.py",           "FAQ",                "❓"),
        Page("pages/9_Contact.py",       "Contact",            "📬")
    ]
)

st.rerun()
