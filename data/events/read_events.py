import pandas as pd
import os
import streamlit as st

def read_events_as_df(country_name):
    dir_path = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(dir_path, country_name + ".csv")
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    else:
        print(f"No data available for {country_name}.")
        return None