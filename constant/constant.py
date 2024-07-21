import os
import streamlit as st

QGI_ROOT_DIR_PATH       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPR_PATH                = QGI_ROOT_DIR_PATH + "/data/ppr/ppr.csv"
EVENTS_TXTS_FOLDER_PATH = QGI_ROOT_DIR_PATH + "/data/events/"
COUNTRIES_CSV_PATH      = QGI_ROOT_DIR_PATH + "/data/country.csv"
COUNTRIES_PATTERNS_PATH = QGI_ROOT_DIR_PATH + "/data/countries/"
BAT_PATH                = QGI_ROOT_DIR_PATH + ".bat"
