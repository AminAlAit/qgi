## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all magic strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings


import sys
import subprocess
from utils.utils import run_requirements
def install_package(package):
    """dummy docstring"""
    #subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
run_requirements()
install_package("streamlit-modal")
install_package("streamlit-echarts")
install_package("streamlit-extras")
install_package("streamlit-lottie")


# References: 
# https://discuss.streamlit.io/t/new-package-st-pages-change-page-names-and-icons-in-sidebar-without-changing-filenames/33969/56
# https://st-pages.streamlit.app

import streamlit as st
from st_pages import Page, add_page_title, show_pages
show_pages(
    [
        # Page("pages/0_Base.py",         "Base",         ""),
        Page("pages/1_Patterns.py",       "Patterns",     ""),
        # Page("pages/2_Experimental.py", "Experimental", ""),
        Page("pages/9_Contact.py",        "Contact",      "")
    ]
)

st.rerun()
