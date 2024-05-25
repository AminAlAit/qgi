from constant.index_metadata import (
    E1_Economic_Decline_and_Poverty,
    E2_Uneven_Economic_Development,
    P3_Human_Rights_and_Rule_of_Law
)


INVESTMENTS_SECTOR = [
    "FDI Flows - Inward (% of GDP)",
    "FDI Flows - Outward (% of GDP)",
    "FDI Stocks - Inward (% of GDP)",
    "FDI Stocks - Outward (% of GDP)",
    "FDI Total Restrictiveness Index",
    "FDI Restrictiveness - Primary Sector",
    "FDI Restrictiveness - Manufacturing",
    "FDI Restrictiveness - Electricity",
    "FDI Restrictiveness - Distribution",
    "FDI Restrictiveness - Transport",
    "FDI Restrictiveness - Media",
    "FDI Restrictiveness - Telecommunications",
    "FDI Restrictiveness - Financial Services",
    "FDI Restrictiveness - Business Services",
]


ECONOMY_SECTOR = [
    "GDP (current US$)",
    "Total Employment Rate",
    E1_Economic_Decline_and_Poverty,
    "Total Inflation (CPI) Index",
    "Total Inflation (CPI) Index - Food",
    "Total Inflation (CPI) Index - Energy",
    "Total Inflation (CPI) Index - less Food, less Energy",
    "Inflation, consumer prices (annual %)",
    "Unemployment, total (% of total labor force) (modeled ILO estimate)",
    "GDP per Hour Worked",
    "General Government Deficit",
    "Total Labour Force",
    ""
]


SOCIAL_SECTOR = [
    "S1: Demographic Pressures",
    "S2: Refugees and IDPs",
    "C3: Group Grievance",
    E2_Uneven_Economic_Development,
    "E3: Human Flight and Brain Drain",
    "Suicide Rates",
]


STATE_INTEGRITY_SECTOR = [
    "X1: External Intervention",
    "C1: Security Apparatus",
    "P1: State Legitimacy",
    "Fragile State Index - Total",
]


TRADE_SECTOR = [
    "Trade in Goods & Services - Net Trade",
    "Trade in Goods & Services - Imports",
    "Trade in Goods & Services - Exports"
]


MILITARY_SECTOR = [
    "Military Expenditure - Share of GDP (%)",
    "Military Expenditure - Per Capita",
    "Military Expenditure - Share of Government Spending (%)"
]


HEALTH_SECTOR = [
    "Health Spending",
    "Infant Mortality Rates"
]


HUMAN_RIGHTS_DEVELOPMENT_SECTOR = [
    P3_Human_Rights_and_Rule_of_Law
]


RESOURCES = [
    "Primary Energy Supply",
]


PUBLIC_SERVICES_SECTOR = [
    "P2: Public Services",
]


EDUCATION_SECTOR = [
    "Education Spending",
    "Youth not in employment, education or training (NEET)",
    "Private spending on education",
    "Public spending on education"
]


POLITICAL_STATE_SECTOR = [
    "C2: Factionalized Elites",
]


ENERGY_SECTOR =[
    "Primary Energy Supply"
]


SECTOR_MAPPING = {
    "Investments":                  INVESTMENTS_SECTOR,
    "Economy":                      ECONOMY_SECTOR,
    "Social":                       SOCIAL_SECTOR,
    "State Integrity":              STATE_INTEGRITY_SECTOR,
    "Trade":                        TRADE_SECTOR,
    "Military":                     MILITARY_SECTOR,
    "Health":                       HEALTH_SECTOR,
    "Human Rights & \nDevelopment": HUMAN_RIGHTS_DEVELOPMENT_SECTOR,
    "Resources":                    RESOURCES,
    "Public Services":              PUBLIC_SERVICES_SECTOR,
    "Education":                    EDUCATION_SECTOR,
    "Political State":              POLITICAL_STATE_SECTOR,
    "Energy":                       ENERGY_SECTOR,
}


ALL_SECTORS = [
    INVESTMENTS_SECTOR,
    ECONOMY_SECTOR,
    SOCIAL_SECTOR,
    STATE_INTEGRITY_SECTOR,
    TRADE_SECTOR,
    MILITARY_SECTOR,
    HEALTH_SECTOR,
    HUMAN_RIGHTS_DEVELOPMENT_SECTOR,
    RESOURCES,
    PUBLIC_SERVICES_SECTOR,
    EDUCATION_SECTOR,
    POLITICAL_STATE_SECTOR,
    ENERGY_SECTOR,
]
