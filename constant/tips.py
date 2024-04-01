TIP_COUNTRY_A_SELECT = "Select first country in the pattern"
TIP_COUNTRY_B_SELECT = "Select second country in the pattern"

def GET_TIP_CORRELATION_RANGE_SLIDER(min_corr: float, max_corr: float):
    return f"""
        Select the correlation range to better filter the results. The range starts from the minimum of {min_corr}%
        up to the maximum of {max_corr}%.         
    """


def GET_TIP_PATTERN_LENGTH_RANGE_SLIDER(min_patt_len: float, max_patt_len: float):
    return f"""
        Select the pattern length range to better filter results. The range starts from the minimum of {min_patt_len} 
        years up to the maximum of {max_patt_len} years.         
    """


def GET_TIP_YEAR_GAP_RANGE_SLIDER(min_gap: float, max_gap: float, country_a):
    return f"""
        Choose any number above 0 if you want to have a gap, in terms of years, between Starting Years for {country_a} and second countries. 
        The range starts with a minimum of {min_gap} years up to the maximum of {max_gap} years.
    """


def GET_TIP_STARTING_YEAR_SLIDER(country_a):
    return f"""
        Select when you want your pattern to start for {country_a}.
    """


TIP_SELECT_PATTERN_LENGTH = "Select how long you want your pattern to be"


TIP_ALIGN_TOGGLE = "When enabled, all index pairs are aligned to the same year, so you can better view the correlation."
TIP_TRANSFORMATION_CAPTIONS = [
    "Displays data in its initial, unmodified form",
    "Scales data to a range between 0 and 1. Use when you want all data on a similar scale, especially for comparing discrepancies between datasets.",
    "Shifts data to have a mean of 0, variance of 1. Use when data needs to be centered around zero.",
    "Use when you want to set a common starting point, ideal for economic data.",
    "Use logarithmic scaling to handle wide-ranging values, ideal for economic data.",
    "Calculates growth rates to highlight changes over time, useful for understanding the pace of increase or decrease of the data."
]
TIP_TRANSFORMATION_RADIO = "Sometimes it is best to transform the data to better view the correlation."

BASE_PPR_LEADERBOARD = """
    These country pairs (A & B) are the
    pairs of patterns,\nranked from
    highest to lowest in terms of
    Pattern Power Score.
"""
