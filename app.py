## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all magic strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings
## TODO save strings in constant, to avoid magic strings


import sys
import subprocess
import streamlit as st

from utils.utils import switch_country_ids_to_names_for_ppr
from pages import base, patterns, experimental, faq, contact


if "set_page_config_bool" not in st.session_state:
    st.session_state["set_page_config_bool"] = True
if st.session_state["set_page_config_bool"]:
    st.set_page_config(layout = "wide", page_title = "QG Intelligence", page_icon = "🌐")
    st.session_state["set_page_config_bool"] = False


# Data Prep
# References: 
# https://discuss.streamlit.io/t/new-package-st-pages-change-page-names-and-icons-in-sidebar-without-changing-filenames/33969/56
# https://st-pages.streamlit.app
subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit-timeline"])
switch_country_ids_to_names_for_ppr()


pages = [
    st.Page(page = base.show_base_page,                      title = "Base",               icon = "🌐"),
    st.Page(page = patterns.show_patterns_portal_page,       title = "Patterns",           icon = "📈"),
    st.Page(page = experimental.show_experimental_feat_page, title = "Under Construction", icon = "🚧"),
    st.Page(page = faq.show_faq_page,                        title = "FAQ",                icon = "❓"),
    st.Page(page = contact.show_contact_us_page,             title = "Contact",            icon = "📬"),
]


pg = st.navigation(pages)
pg.run()
