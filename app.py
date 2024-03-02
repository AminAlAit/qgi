## TODO optimize requirements.txt to include only libraries we use
## TODO resolve the library importing mess
## TODO see if you can work with "dotlottie" files instead of normal files. "dotlottie" file sizes are less. Or transition to URLs.
## TODO echarts link: https://echarts.streamlit.app https://github.com/andfanilo/streamlit-echarts
## TODO country_a South Africa, Antigua and Barbuda returns error
## TODO categorize indexes
## TODO consolidate all magic strings in the streamlit project into global variables, for better centralization maybe have another constant.py script here too.
## TODO checkout similar page-runtime settings


# from st_pages import show_pages_from_config
# show_pages_from_config()

import streamlit as st
from st_pages import Page, add_page_title, show_pages
show_pages(
    [
        Page("pages/0_Base.py",    "Base", ""),
        Page("pages/9_Contact.py", "Contact", "")
    ]
)

st.experimental_rerun()
