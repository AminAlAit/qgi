import streamlit as st
import pandas as pd
from constant.constant import NEW_PPR_PATH, OLD_PPR_PATH
from constant.sectors import (
    INVESTMENTS_SECTOR,
    TRADE_SECTOR,
    FINANCE_ECONOMY_SECTOR,
    MILITARY_SECTOR,
    HUMAN_RIGHTS_DEVELOPMENT,
    SOVEREIGNTY,
    SOCIAL_SECTOR,
    POLITICAL_STATE_SECTOR,
    ENERGY_SECTOR
)
from constant.tips import (
    BASE_PPR_LEADERBOARD,
)
from utils.patterns import compare_rankings, get_base_dot_plot_data
from streamlit_extras.customize_running import center_running
from streamlit_echarts import st_echarts


st.set_page_config(layout = "wide", page_title = "QG Intelligence", page_icon = "📈")
center_running()


old_ppr_df = pd.read_csv(OLD_PPR_PATH)
new_ppr_df = pd.read_csv(NEW_PPR_PATH)


def show_base_page():
    st.markdown("# QG Intelligence")

    col1, col2 = st.columns([3, 1])
    ppr_df = compare_rankings(old_ppr_df, new_ppr_df, make_countries_index = False)

    with col1:
        with st.container(border = True):
            grouped = get_base_dot_plot_data(ppr_df)
            top_ranked = grouped.head(1).reset_index(drop=True)
            
            # Normalize the Pattern Power Ranking for determining the point sizes
            pattern_power_ranking_normalized = (top_ranked["Pattern Power Ranking"] - top_ranked["Pattern Power Ranking"].min()) / (top_ranked["Pattern Power Ranking"].max() - top_ranked["Pattern Power Ranking"].min())
            point_sizes = pattern_power_ranking_normalized * 20 + 5  # Adjust size scaling as needed

            scatter_data = [
                {
                    "value": [row["Pattern Length"], row["Number of Indexes"]],
                    "name": f"{row['Country A']} - {row['Country B']}",
                    "symbolSize": point_sizes.iloc[index]
                }
                for index, row in top_ranked.iterrows()
            ]

            options = {
                "tooltip": {
                    "trigger": "item",
                    "formatter": "{b}: ({c})"
                },
                "xAxis": {
                    "type": "value",
                    "name": "Pattern Length\n(Years)",
                    "min":  min(top_ranked["Pattern Length"]),
                    "max":  max(top_ranked["Pattern Length"])
                },
                "yAxis": {
                    "type": "value",
                    "name": "Number of Indexes",
                    "min":  min(top_ranked["Number of Indexes"]),
                    "max":  max(top_ranked["Number of Indexes"])
                },
                "series": [
                    {
                        "data": scatter_data,
                        "type": "scatter",
                        "itemStyle": {
                            "color": '#8B0000'  # Dark red
                        }
                    }
                ],
                "title": {
                    "text": "The Strengths & Lengths of International Relationships",
                    #"subtext": "",
                    "left": "center"
                },
                "legend": {
                    "data": ["Series 1"],
                    "top": "bottom"
                },
            }

            st_echarts(options = options, height = "500px")    
    with col2:
        with st.container(border = True, height = 537):
            st.markdown("Patterns Leaderboard", help = BASE_PPR_LEADERBOARD)
            mini_ppr_df = ppr_df.head(1000)
            #mini_ppr_df.set_index("Country A", inplace = True)
            mini_ppr_df = mini_ppr_df.iloc[:, :2]
            mini_ppr_df.index = [i + 1 for i in range(len(mini_ppr_df))]
            #st.dataframe(mini_ppr_df, use_container_width = True)
            st.table(mini_ppr_df)
    col1, col2 = st.columns([1, 3])
    with col1:
        with st.container(border = True, height = 640):
            indexes  = INVESTMENTS_SECTOR + FINANCE_ECONOMY_SECTOR + SOCIAL_SECTOR + TRADE_SECTOR + MILITARY_SECTOR + HUMAN_RIGHTS_DEVELOPMENT + POLITICAL_STATE_SECTOR + SOVEREIGNTY + ENERGY_SECTOR
            df       = pd.DataFrame({"Indexes": indexes})
            df.index = [i + 1 for i in range(len(df))]
            #st.dataframe(df, height = 640)
            st.table(df)
    with col2:
        with st.container(border = True, height = 640):
            data = [
                {"value": len(INVESTMENTS_SECTOR),       "name": f"Investments ({len(INVESTMENTS_SECTOR)} indexes)"},
                {"value": len(FINANCE_ECONOMY_SECTOR),   "name": f"Finance & Economy ({len(FINANCE_ECONOMY_SECTOR)} indexes)"},
                {"value": len(SOCIAL_SECTOR),            "name": f"Social ({len(SOCIAL_SECTOR)} indexes)"},
                {"value": len(TRADE_SECTOR),             "name": f"Trade ({len(TRADE_SECTOR)} indexes)"},
                {"value": len(MILITARY_SECTOR),          "name": f"Military ({len(MILITARY_SECTOR)} indexes)"},
                {"value": len(HUMAN_RIGHTS_DEVELOPMENT), "name": f"Human Rights & Development ({len(HUMAN_RIGHTS_DEVELOPMENT)} indexes)"},
                {"value": len(POLITICAL_STATE_SECTOR),   "name": f"Political State ({len(POLITICAL_STATE_SECTOR)} indexes)"},
                {"value": len(SOVEREIGNTY),              "name": f"Sovereignty ({len(SOVEREIGNTY)} indexes)"},
                {"value": len(ENERGY_SECTOR),            "name": f"Energy ({len(ENERGY_SECTOR)} indexes)"},
            ]
            
            option = {
                "legend": {
                    "top": "bottom",
                    "textStyle": {
                        "color": "#808080"
                    }
                },
                "toolbox": {
                    "show":    True,
                    "feature": {
                        "mark":     {"show": True},
                        "dataView": {
                            "show":     True, 
                            "readOnly": False
                        },
                        "restore":     {"show": True},
                        "saveAsImage": {"show": True},
                    },
                },
                "series": [
                    {
                        "name":      "Sectors",
                        "type":      "pie",
                        "radius":    [50, 250],
                        "center":    ["50%", "50%"],
                        "roseType":  "area",
                        "itemStyle": {"borderRadius": 8},
                        "data":      data,
                    }
                ],
            }

            st_echarts(options = option, height = "600px")

    # col1, col2 = st.columns([3, 1])
    # with col1:
    #     with st.container(border = True, height = 640):
    #         data_df = pd.DataFrame(
    #             {
    #                 "sales": [
    #                     [0, 4, 26, 80, 100, 40],
    #                     [80, 20, 80, 35, 40, 100],
    #                     [10, 20, 80, 80, 70, 0],
    #                     [10, 100, 20, 100, 30, 100],
    #                 ],
    #             }
    #         )

    #         st.data_editor(
    #             data_df,
    #             column_config={
    #                 "sales": st.column_config.ListColumn(
    #                     "Sales (last 6 months)",
    #                     help="The sales volume in the last 6 months",
    #                     width="medium",
    #                 ),
    #             },
    #             hide_index=True,
    #         )
        
show_base_page()