"""Faulty Index Info"""

from datetime import datetime


## Organizations
OECD               = "OECD"
The_Fund_For_Peace = "The Fund For Peace"
World_Bank         = "World Bank"
SIPRI              = "SIPRI"


## Main Names
FDI_Total_Restrictiveness_Index = "FDI Total Restrictiveness Index" # OECD
Trade_in_Goods_and_Services     = "Trade in Goods & Services"       # OECD - New Main Name
Inflation_CPI_Index             = "Inflation (CPI) Index"           # OECD
Fragile_State_Index             = "Fragile State Index"             # The Fund for Peace


## Index Names (old and new)
Total                                           = "Total"                                                   # Index Old Names - The Fund for Peace
Fragile_State_Index_Total                       = "Fragile State Index - Total"                             # Index New Names - The Fund for Peace
E1_Economy                                      = "E1: Economy"                                             # Index Old Names - The Fund for Peace
E1_Economic_Decline_and_Poverty                 = "E1: Economic Decline and Poverty"                        # Index New Names - The Fund for Peace
E2_Economic_Inequality                          = "E2: Economic Inequality"                                 # Index Old Names - The Fund for Peace
E2_Uneven_Economic_Development                  = "E2: Uneven Economic Development"                         # Index New Names - The Fund for Peace
P3_Human_Rights                                 = "P3: Human Rights"                                        # Index Old Names - The Fund for Peace
P3_Human_Rights_and_Rule_of_Law                 = "P3: Human Rights and Rule of Law"                        # Index New Names - The Fund for Peace

Primary_Sector                                  = "Primary Sector"                                          # Index Old Names - OECD
FDI_Restrictiveness_Primary_Sector              = "FDI Restrictiveness - Primary Sector"                    # Index New Names - OECD
Manufacturing                                   = "Manufacturing"                                           # Index Old Names - OECD
FDI_Restrictiveness_Manufacturing               = "FDI Restrictiveness - Manufacturing"                     # Index New Names - OECD
Distribution                                    = "Distribution"                                            # Index Old Names - OECD
FDI_Restrictiveness_Distribution                = "FDI Restrictiveness - Distribution"                      # Index New Names - OECD
Transport                                       = "Transport"                                               # Index Old Names - OECD
FDI_Restrictiveness_Transport                   = "FDI Restrictiveness - Transport"                         # Index New Names - OECD
Media                                           = "Media"                                                   # Index Old Names - OECD
FDI_Restrictiveness_Media                       = "FDI Restrictiveness - Media"                             # Index New Names - OECD
Telecommunications                              = "Telecommunications"                                      # Index Old Names - OECD
FDI_Restrictiveness_Telecommunications          = "FDI Restrictiveness - Telecommunications"                # Index New Names - OECD
Electricity                                     = "Electricity"                                             # Index Old Names - OECD
FDI_Restrictiveness_Electricity                 = "FDI Restrictiveness - Electricity"                       # Index New Names - OECD
Financial_Services                              = "Financial Services"                                      # Index Old Names - OECD
FDI_Restrictiveness_Financial_Services          = "FDI Restrictiveness - Financial Services"                # Index New Names - OECD
Business_Services                               = "Business Services"                                       # Index Old Names - OECD
FDI_Restrictiveness_Business_Services           = "FDI Restrictiveness - Business Services"                 # Index New Names - OECD
Net_Trade                                       = "Net Trade"                                               # Index Old Names - OECD
Trade_in_Goods_and_Services_Net_Trade           = "Trade in Goods & Services - Net Trade"                   # Index New Names - OECD - Old Main Name
Imports                                         = "Imports"                                                 # Index Old Names - OECD
Trade_in_Goods_and_Services_Imports             = "Trade in Goods & Services - Imports"                     # Index New Names - OECD
Exports                                         = "Exports"                                                 # Index Old Names - OECD
Trade_in_Goods_and_Services_Exports             = "Trade in Goods & Services - Exports"                     # Index New Names - OECD
Food                                            = "Food"                                                    # Index Old Names - OECD
Total_Inflation_CPI_Index_Food                  = "Total Inflation (CPI) Index - Food"                      # Index New Names - OECD
Energy                                          = "Energy"                                                  # Index Old Names - OECD
Total_Inflation_CPI_Index_Energy                = "Total Inflation (CPI) Index - Energy"                    # Index New Names - OECD
Total_less_Food_less_Energy                     = "Total less Food, less Energy"                            # Index Old Names - OECD
Total_Inflation_CPI_Index_less_Food_less_Energy = "Total Inflation (CPI) Index - less Food, less Energy"    # Index New Names - OECD


INDEX_NAMES_THAT_NEED_CHANGING = [
    # The Fund for Peace
    {
        "org_fk":        f"{The_Fund_For_Peace}",
        "main_name_fk":  f"{Fragile_State_Index}",
        "index_name_fk": f"{Total}",
        "new_name":      f"{Fragile_State_Index_Total}",
    },
    {
        "org_fk":        f"{The_Fund_For_Peace}",
        "main_name_fk":  f"{Fragile_State_Index}",
        "index_name_fk": f"{E1_Economy}",
        "new_name":      f"{E1_Economic_Decline_and_Poverty}",
    },
    {
        "org_fk":        f"{The_Fund_For_Peace}",
        "main_name_fk":  f"{Fragile_State_Index}",
        "index_name_fk": f"{E2_Economic_Inequality}",
        "new_name":      f"{E2_Uneven_Economic_Development}",
    },
    {
        "org_fk":        f"{The_Fund_For_Peace}",
        "main_name_fk":  f"{Fragile_State_Index}",
        "index_name_fk": f"{P3_Human_Rights}",
        "new_name":      f"{P3_Human_Rights_and_Rule_of_Law}",
    },
    # OECD
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Primary_Sector}",
        "new_name":      f"{FDI_Restrictiveness_Primary_Sector}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Manufacturing}",
        "new_name":      f"{FDI_Restrictiveness_Manufacturing}",
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Distribution}",
        "new_name":      f"{FDI_Restrictiveness_Distribution}",
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Transport}",
        "new_name":      f"{FDI_Restrictiveness_Transport}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Media}",
        "new_name":      f"{FDI_Restrictiveness_Media}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Telecommunications}",
        "new_name":      f"{FDI_Restrictiveness_Telecommunications}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Electricity}",
        "new_name":      f"{FDI_Restrictiveness_Electricity}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Financial_Services}",
        "new_name":      f"{FDI_Restrictiveness_Financial_Services}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{FDI_Total_Restrictiveness_Index}",
        "index_name_fk": f"{Business_Services}",
        "new_name":      f"{FDI_Restrictiveness_Business_Services}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services}",
        "index_name_fk": f"{Net_Trade}",
        "new_name":      f"{Trade_in_Goods_and_Services_Net_Trade}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services}",
        "index_name_fk": f"{Imports}",
        "new_name":      f"{Trade_in_Goods_and_Services_Imports}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services}",
        "index_name_fk": f"{Exports}",
        "new_name":      f"{Trade_in_Goods_and_Services_Exports}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Inflation_CPI_Index}",
        "index_name_fk": f"{Food}",
        "new_name":      f"{Total_Inflation_CPI_Index_Food}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Inflation_CPI_Index}",
        "index_name_fk": f"{Energy}",
        "new_name":      f"{Total_Inflation_CPI_Index_Energy}"
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Inflation_CPI_Index}",
        "index_name_fk": f"{Total_less_Food_less_Energy}",
        "new_name":      f"{Total_Inflation_CPI_Index_less_Food_less_Energy}"
    },
]


MAIN_NAMES_THAT_NEED_CHANGING = [
    # OECD
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services_Net_Trade}",
        "new_name":      f"{Trade_in_Goods_and_Services}",
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services_Net_Trade}",
        "index_name_fk": f"{Imports}",
        "new_name":      f"{Trade_in_Goods_and_Services}",
    },
    {
        "org_fk":        f"{OECD}",
        "main_name_fk":  f"{Trade_in_Goods_and_Services_Net_Trade}",
        "index_name_fk": f"{Exports}",
        "new_name":      f"{Trade_in_Goods_and_Services}",
    },
]


## Sources
The_Fund_For_Peace_Source = "https://fragilestatesindex.org"
World_Bank_Source         = "World Bank national accounts data, and OECD National Accounts data files."
SIPRI_Source              = "https://www.sipri.org/databases/milex"


## Citations
The_Fund_For_Peace_Citation = f"The Fund for Peace. {str(datetime.today().year)}. 'Fragile States Index.' Washington, D.C.: The Fund for Peace. Accessed on {str(datetime.today().year)}. "
def get_world_bank_citation(World_Bank, indicator_name, url):
    date = str(datetime.today().strftime('%d/%m/%Y'))
    return World_Bank + '. ' + '"' + indicator_name + '" World Development Indicators. Accessed ' + date + "\n" + url
SIPRI_Citation = "Information from the Stockholm International Peace Research Institute (SIPRI), URL ADDRESS' (e.g. ‘Information from the Stockholm International Peace Research Institute (SIPRI) Military Expenditure Database, https://doi.org/10.55163/CQGC9685"
def get_oecd_citation(indicator_name, url):
    date = datetime.today().strftime('%d/%m/%Y')
    year = str(datetime.today().year)
    return f"OECD ({year}), {indicator_name} (indicator), URL: {url} (Accessed on {date})."

INDEX_METADATA = {
    f"{The_Fund_For_Peace}": [
        {
            "main_name":  Fragile_State_Index,
            "index_name": Fragile_State_Index_Total,
            "description": """
            The Fragile States Index, produced by The Fund for Peace, is a critical tool in highlighting not only the normal pressures that all states experience, but also in identifying when those pressures are pushing a state towards the brink of failure.
            """,
            "tips": """
            📈 If the index score goes up, it suggests an increase in fragility, indicating that a country is facing heightened pressures that may threaten its stability and potentially lead to conflict or failure.
            \n📉 If the index score goes down, it indicates an improvement in a country's stability and resilience, suggesting that it is better managing its social, economic, and political pressures, thereby reducing the risk of conflict and enhancing prospects for peace and development.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "C1: Security Apparatus",
            "description": """
            The Security Apparatus indicator considers the security threats to a state, such as bombings, attacks and battle-related deaths, rebel movements, mutinies, coups, or terrorism. The Security Apparatus also takes into account serious criminal factors, such as organized crime and homicides, and perceived trust of citizens in domestic security. In some instances, the security apparatus may extend beyond traditional military or police forces to include state-sponsored or state-supported private militias that terrorize political opponents, suspected “enemies,” or civilians seen to be sympathetic to the opposition. In other instances, the security apparatus of a state can include a “deep state”, that may consist of secret intelligence units, or other irregular security forces, that serve the interests of a political leader or clique. As a counter example, the indicator will also take into account armed resistance to a governing authority, particularly the manifestation of violent uprisings and insurgencies, proliferation of independent militias, vigilantes, or mercenary groups that challenge the state’s monopoly of the use of force.
            """,
            "tips": """
            📈 If the index score goes up, it suggests an increase in security threats, higher levels of violence, and a possible decrease in public trust in security apparatuses, indicating a deterioration in state security and stability.
            \n📉 If the index score goes down, it implies a reduction in security threats, lower levels of violence, and potentially greater public trust in the security forces, signaling an improvement in state security and stability.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "C2: Factionalized Elites",
            "description": """
            The Factionalized Elites indicator considers the fragmentation of state institutions along ethnic, class, clan, racial or religious lines, as well as and brinksmanship and gridlock between ruling elites. It also factors the use of nationalistic political rhetoric by ruling elites, often in terms of nationalism, xenophobia, communal irredentism (e.g., a “greater Serbia”) or of communal solidarity (e.g., “ethnic cleansing” or “defending the faith”). In extreme cases, it can be representative of the absence of legitimate leadership widely accepted as representing the entire citizenry. The Factionalized Elites indicator measures power struggles, political competition, political transitions, and where elections occur will factor in the credibility of electoral processes (or in their absence, the perceived legitimacy of the ruling class).
            """,
            "tips": """
            📈 If the index score goes up, it implies an increase in the division and factionalism among a country's elites, signaling deeper societal fractures and potential for conflict due to power struggles and lack of consensus on governance.
            \n📉 If the index score goes down, it suggests a decrease in elite factionalism, indicating a move towards greater unity among ruling classes and potentially more stable and inclusive governance, improving the country's prospects for peace and development.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "C3: Group Grievance",
            "description": """
            The Group Grievance Indicator focuses on divisions and schisms between different groups in society – particularly divisions based on social or political characteristics – and their role in access to services or resources, and inclusion in the political process. Group Grievance may also have a historical component, where aggrieved communal groups cite injustices of the past, sometimes going back centuries, that influence and shape that group’s role in society and relationships with other groups. This history may in turn be shaped by patterns of real or perceived atrocities or “crimes” committed with apparent impunity against communal groups. Groups may also feel aggrieved because they are denied autonomy, self-determination or political independence to which they believe they are entitled. The Indicator also considers where specific groups are singled out by state authorities, or by dominant groups, for persecution or repression, or where there is public scapegoating of groups believed to have acquired wealth, status or power “illegitimately”, which may manifest itself in the emergence of fiery rhetoric, such as through “hate” radio, pamphleteering, and stereotypical or nationalistic political speech.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an escalation in societal divisions and grievances among different groups, reflecting increased tension, potential for conflict, and challenges in achieving social cohesion and harmony.
            \n📉 If the index score goes down, it signifies a reduction in group grievances, suggesting improved social integration, greater equality in access to resources and political participation, and a more inclusive society that is moving towards reconciliation and unity.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": E1_Economic_Decline_and_Poverty,
            "description": """
            The Economic Decline Indicator considers factors related to economic decline within a country. For example, the Indicator looks at patterns of progressive economic decline of the society as a whole as measured by per capita income, Gross National Product, unemployment rates, inflation, productivity, debt, poverty levels, or business failures. It also takes into account sudden drops in commodity prices, trade revenue, or foreign investment, and any collapse or devaluation of the national currency. The Economic Decline Indicator further considers the responses to economic conditions and their consequences, such as extreme social hardship imposed by economic austerity programs, or perceived increasing group inequalities. The Economic Decline Indicator is focused on the formal economy – as well as illicit trade, including the drug and human trafficking, and capital flight, or levels of corruption and illicit transactions such as money laundering or embezzlement.
            """,
            "tips": """
            📈 If the index score goes up, it suggests worsening economic conditions, marked by increased unemployment, inflation, debt, and social inequalities, potentially leading to greater societal distress and instability.
            \n📉 If the index score goes down, it indicates an improvement in economic stability and health, characterized by lower unemployment rates, stabilized prices, reduced debt, and diminished social hardships, contributing to a more stable and prosperous society.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": E2_Uneven_Economic_Development,
            "description": """
            The Uneven Economic Development Indicator considers inequality within the economy, irrespective of the actual performance of an economy. For example, the Indicator looks at structural inequality that is based on group (such as racial, ethnic, religious, or other identity group) or based on education, economic status, or region (such as urban-rural divide). The Indicator considers not only actual inequality, but also perceptions of inequality, recognizing that perceptions of economic inequality can fuel grievance as much as real inequality, and can reinforce communal tensions or nationalistic rhetoric. Further to measuring economic inequality, the Indicator also takes into account the opportunities for groups to improve their economic status, such as through access to employment, education, or job training such that even if there is economic inequality present, to what degree it is structural and reinforcing.
            """,
            "tips": """
            📈 If the index score goes up, it indicates increasing economic disparities and perceived inequalities within the society, potentially exacerbating social tensions and undermining social cohesion.
            \n📉 If the index score goes down, it suggests a reduction in economic inequalities and an improvement in the equitable distribution of resources, enhancing social harmony and opportunities for all societal groups.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "E3: Human Flight and Brain Drain",
            "description": """
            The Human Flight and Brain Drain Indicator considers the economic impact of human displacement (for economic or political reasons) and the consequences this may have on a country’s development. On the one hand, this may involve the voluntary emigration of the middle class – particularly economically productive segments of the population, such as entrepreneurs, or skilled workers such as physicians – due to economic deterioration in their home country and the hope of better opportunities farther afield. On the other hand, it may involve the forced displacement of professionals or intellectuals who are fleeing their country due to actual or feared persecution or repression, and specifically the economic impact that displacement may wreak on an economy through the loss of productive, skilled professional labor.
            """,
            "tips": """
            📈 If the index score goes up, it suggests an increase in human flight and brain drain, highlighting a loss of skilled professionals and a potential decline in the country's developmental prospects due to economic or political instability.
            \n📉 If the index score goes down, it indicates a decrease in human flight and brain drain, signifying stability and potentially improved economic or political conditions that retain or attract skilled professionals, enhancing the country's development.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "P1: State Legitimacy",
            "description": """
            The State Legitimacy Indicator considers the representativeness and openness of government and its relationship with its citizenry. The Indicator looks at the population’s level of confidence in state institutions and processes, and assesses the effects where that confidence is absent, manifested through mass public demonstrations, sustained civil disobedience, or the rise of armed insurgencies. Though the State Legitimacy indicator does not necessarily make a judgment on democratic governance, it does consider the integrity of elections where they take place (such as flawed or boycotted elections), the nature of political transitions, and where there is an absence of democratic elections, the degree to which the government is representative of the population of which it governs. The Indicator takes into account openness of government, specifically the openness of ruling elites to transparency, accountability and political representation, or conversely the levels of corruption, profiteering, and marginalizing, persecuting, or otherwise excluding opposition groups. The Indicator also considers the ability of a state to exercise basic functions that infer a population’s confidence in its government and institutions, such as through the ability to collect taxes.
            """,
            "tips": """
            📈 If the index score goes up, it suggests a decrease in state legitimacy, marked by reduced public confidence in institutions and governance, potentially leading to increased civil unrest, demonstrations, or challenges to the state's authority.
            \n📉 If the index score goes down, it indicates an increase in state legitimacy, reflecting greater public trust in government and institutions, possibly resulting from improved transparency, accountability, and representation, thereby enhancing stability and governance effectiveness.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "P2: Public Services",
            "description": """
            The Public Services Indicator refers to the presence of basic state functions that serve the people. On the one hand, this may include the provision of essential services, such as health, education, water and sanitation, transport infrastructure, electricity and power, and internet and connectivity. On the other hand, it may include the state’s ability to protect its citizens, such as from terrorism and violence, through perceived effective policing. Further, even where basic state functions and services are provided, the Indicator further considers to whom – whether the state narrowly serves the ruling elites, such as security agencies, presidential staff, the central bank, or the diplomatic service, while failing to provide comparable levels of service to the general populace – such as rural versus urban populations. The Indicator also considers the level and maintenance of general infrastructure to the extent that its absence would negatively affect the country’s actual or potential development.
            """,
            "tips": """
            📈 If the index score goes up, it suggests a deterioration in the provision of public services and basic state functions, potentially indicating that services are becoming less accessible or of lower quality, particularly to the general populace, and possibly leading to increased dissatisfaction and disparities within the society.
            \n📉 If the index score goes down, it indicates improvements in the availability and quality of essential public services and basic state functions, suggesting a more equitable distribution of services across different segments of society, which can contribute to overall societal development and stability.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": P3_Human_Rights_and_Rule_of_Law,
            "description": """
            The Human Rights and Rule of Law Indicator considers the relationship between the state and its population insofar as fundamental human rights are protected and freedoms are observed and respected. The Indicator looks at whether there is widespread abuse of legal, political and social rights, including those of individuals, groups and institutions (e.g. harassment of the press, politicization of the judiciary, internal use of military for political ends, repression of political opponents). The Indicator also considers outbreaks of politically inspired (as opposed to criminal) violence perpetrated against civilians. It also looks at factors such as denial of due process consistent with international norms and practices for political prisoners or dissidents, and whether there is current or emerging authoritarian, dictatorial or military rule in which constitutional and democratic institutions and processes are suspended or manipulated.
            """,
            "tips": """
            📈 If the index score goes up, it signifies an increase in human rights violations and a decline in the rule of law, indicating that legal, political, and social rights are under threat, and there may be a rise in politically inspired violence against civilians and a suppression of democratic processes.
            \n📉 If the index score goes down, it suggests an improvement in the protection of human rights and the strengthening of the rule of law, reflecting a societal move towards greater respect for individual and group rights, due process, and the maintenance of democratic institutions and practices.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "S1: Demographic Pressures",
            "description": """
            The Demographic Pressures Indicator considers pressures upon the state deriving from the population itself or the environment around it. For example, the Indicator measures population pressures related to food supply, access to safe water, and other life-sustaining resources, or health, such as prevalence of disease and epidemics. The Indicator considers demographic characteristics, such as pressures from high population growth rates or skewed population distributions, such as a “youth or age bulge,” or sharply divergent rates of population growth among competing communal groups, recognizing that such effects can have profound social, economic, and political effects. Beyond the population, the Indicator also takes into account pressures stemming from extreme weather events (hurricanes, earthquakes, floods or drought), and pressures upon the population from environmental hazards.
            """,
            "tips": """
            📈 If the index score goes up, it indicates increasing demographic pressures and environmental challenges, such as higher population growth, inadequate access to resources, and increased vulnerability to natural disasters, potentially exacerbating social, economic, and political tensions.
            \n📉 If the index score goes down, it suggests a reduction in demographic pressures and an improvement in managing environmental risks, pointing to better resource availability, stable population growth, and enhanced resilience to natural disasters, contributing to social and economic stability.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "S2: Refugees and IDPs",
            "description": """
            The Refugees and Internally Displaced Persons Indicator measures the pressure upon states caused by the forced displacement of large communities as a result of social, political, environmental or other causes, measuring displacement within countries, as well as refugee flows into others. The indicator measures refugees by country of Asylum, recognizing that population inflows can put additional pressure on public services, and can sometimes create broader humanitarian and security challenges for the receiving state, if that state does not have the absorption capacity and adequate resources. The Indicator also measures the Internally Displaced Persons (IDP) and Refugees by country of origin, which signifies internal state pressures as a result of violence, environmental or other factors such as health epidemics. These measures are considered within the context of the state’s population (per capita) and human development trajectory, and over time (year on year spikes), recognizing that some IDPs or refugees for example, may have been displaced for long periods of time.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in refugees and internally displaced persons, signifying heightened social, political, or environmental pressures that force populations to flee, thereby increasing the burden on public services and potentially leading to broader humanitarian and security challenges.
            \n📉 If the index score goes down, it suggests a decrease in the number of refugees and internally displaced persons, indicating an improvement in the underlying causes of displacement such as violence, environmental issues, or health epidemics, and a positive shift towards stability and human development.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
        {
            "main_name":  Fragile_State_Index,
            "index_name": "X1: External Intervention",
            "description": """
            The External Intervention Indicator considers the influence and impact of external actors in the functioning – particularly security and economic – of a state. On the one hand, External Intervention focuses on security aspects of engagement from external actors, both covert and overt, in the internal affairs of a state at risk by governments, armies, intelligence services, identity groups, or other entities that may affect the balance of power (or resolution of a conflict) within a state. On the other hand, External Intervention also focuses on economic engagement by outside actors, including multilateral organizations, through large-scale loans, development projects, or foreign aid, such as ongoing budget support, control of finances, or management of the state’s economic policy, creating economic dependency. External Intervention also takes into account humanitarian intervention, such as the deployment of an international peacekeeping mission.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in the level of external intervention in a state, highlighting growing dependencies on foreign assistance, or interference in its internal affairs, which could potentially destabilize the balance of power or economic independence.
            \n📉 If the index score goes down, it suggests a reduction in external intervention, signifying a move towards greater autonomy and stability in managing internal affairs without significant influence or dependency on foreign entities or multilateral organizations.
            """,
            "source": The_Fund_For_Peace_Source,
            "citation": The_Fund_For_Peace_Citation
        },
    ],
    f"{World_Bank}": [
        {
            "main_name":  "GDP (current US$)",
            "index_name": "GDP (current US$)",
            "description": """
            GDP at purchaser's prices is the sum of gross value added by all resident producers in the economy plus any product taxes and minus any subsidies not included in the value of the products. It is calculated without making deductions for depreciation of fabricated assets or for depletion and degradation of natural resources. Data are in current U.S. dollars. Dollar figures for GDP are converted from domestic currencies using single year official exchange rates. For a few countries where the official exchange rate does not reflect the rate effectively applied to actual foreign exchange transactions, an alternative conversion factor is used.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in the overall economic activity and value generated within a country, reflecting growth in production, higher product taxes, or a decrease in subsidies, signifying an expanding economy.
            \n📉 If the index score goes down, it suggests a decrease in the total economic output, which could be due to lower production levels, increased subsidies, or higher product taxes, indicating a contraction in the country's economic activity.
            """,
            "source": World_Bank_Source + "\n https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
            "citation": get_world_bank_citation(World_Bank, "GDP (current US$)", "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",)
        },
    ],
    f"{SIPRI}": [
        {
            "main_name":  "Military Expenditure",
            "index_name": "Military Expenditure - Share of GDP (%)",
            "description": """
            The SIPRI Military Expenditure Database contains consistent time series on the military spending of countries. \nMilitary expenditure in local currency at current prices is presented according to both the financial year of each country and according to calendar year, calculated on the assumption that, where financial years do not correspond to calendar years, spending is distributed evenly through the year. Figures in share of gross domestic product (GDP) are presented according to calendar year. Figures given as a share of government expenditure are presented according to financial year.
            \n Military expenditures data from SIPRI are derived from the NATO definition, which includes all current and capital expenditures on the armed forces, including peacekeeping forces; defense ministries and other government agencies engaged in defense projects; paramilitary forces, if these are judged to be trained and equipped for military operations; and military space activities. Such expenditures include military and civil personnel, including retirement pensions of military personnel and social services for personnel; operation and maintenance; procurement; military research and development; and military aid (in the military expenditures of the donor country). Excluded are civil defense and current expenditures for previous military activities, such as for veterans' benefits, demobilization, conversion, and destruction of weapons. This definition cannot be applied for all countries, however, since that would require much more detailed information than is available about what is included in military budgets and off-budget military expenditure items. (For example, military budgets might or might not cover civil defense, reserves and auxiliary forces, police and paramilitary forces, dual-purpose forces such as military and civilian police, military grants in kind, pensions for military personnel, and social security contributions paid by one part of government to another.)
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in a country's military spending, suggesting a potential escalation in military readiness, defense capabilities, or response to perceived threats, which can have implications for national security and international relations.
            \n📉 If the index score goes down, it signifies a reduction in military expenditures, potentially reflecting a country's shift towards peace and stability, reallocation of resources to non-military sectors, or an indication of improved security perceptions and decreased threat levels.
            """,
            "source": SIPRI_Source,
            "citation": SIPRI_Citation
        },
        {
            "main_name":  "Military Expenditure",
            "index_name": "Military Expenditure - Per Capita",
            "description": """
            The SIPRI Military Expenditure Database contains consistent time series on the military spending of countries. \nMilitary expenditure in local currency at current prices is presented according to both the financial year of each country and according to calendar year, calculated on the assumption that, where financial years do not correspond to calendar years, spending is distributed evenly through the year. Figures in per capita are presented according to calendar year. Figures given as a share of government expenditure are presented according to financial year.
            \n Military expenditures data from SIPRI are derived from the NATO definition, which includes all current and capital expenditures on the armed forces, including peacekeeping forces; defense ministries and other government agencies engaged in defense projects; paramilitary forces, if these are judged to be trained and equipped for military operations; and military space activities. Such expenditures include military and civil personnel, including retirement pensions of military personnel and social services for personnel; operation and maintenance; procurement; military research and development; and military aid (in the military expenditures of the donor country). Excluded are civil defense and current expenditures for previous military activities, such as for veterans' benefits, demobilization, conversion, and destruction of weapons. This definition cannot be applied for all countries, however, since that would require much more detailed information than is available about what is included in military budgets and off-budget military expenditure items. (For example, military budgets might or might not cover civil defense, reserves and auxiliary forces, police and paramilitary forces, dual-purpose forces such as military and civilian police, military grants in kind, pensions for military personnel, and social security contributions paid by one part of government to another.)
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in a country's military spending, suggesting a potential escalation in military readiness, defense capabilities, or response to perceived threats, which can have implications for national security and international relations.
            \n📉 If the index score goes down, it signifies a reduction in military expenditures, potentially reflecting a country's shift towards peace and stability, reallocation of resources to non-military sectors, or an indication of improved security perceptions and decreased threat levels.
            """,
            "source": SIPRI_Source,
            "citation": SIPRI_Citation
        },
        {
            "main_name":  "Military Expenditure",
            "index_name": "Military Expenditure - Share of Government Spending",
            "description": """
            The SIPRI Military Expenditure Database contains consistent time series on the military spending of countries. \nMilitary expenditure in local currency at current prices is presented according to both the financial year of each country and according to calendar year, calculated on the assumption that, where financial years do not correspond to calendar years, spending is distributed evenly through the year. Figures in constant (2021) and current US dollars are presented according to calendar year. Figures given as a share of government expenditure are presented according to financial year.
            \n Military expenditures data from SIPRI are derived from the NATO definition, which includes all current and capital expenditures on the armed forces, including peacekeeping forces; defense ministries and other government agencies engaged in defense projects; paramilitary forces, if these are judged to be trained and equipped for military operations; and military space activities. Such expenditures include military and civil personnel, including retirement pensions of military personnel and social services for personnel; operation and maintenance; procurement; military research and development; and military aid (in the military expenditures of the donor country). Excluded are civil defense and current expenditures for previous military activities, such as for veterans' benefits, demobilization, conversion, and destruction of weapons. This definition cannot be applied for all countries, however, since that would require much more detailed information than is available about what is included in military budgets and off-budget military expenditure items. (For example, military budgets might or might not cover civil defense, reserves and auxiliary forces, police and paramilitary forces, dual-purpose forces such as military and civilian police, military grants in kind, pensions for military personnel, and social security contributions paid by one part of government to another.)
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in a country's military spending, suggesting a potential escalation in military readiness, defense capabilities, or response to perceived threats, which can have implications for national security and international relations.
            \n📉 If the index score goes down, it signifies a reduction in military expenditures, potentially reflecting a country's shift towards peace and stability, reallocation of resources to non-military sectors, or an indication of improved security perceptions and decreased threat levels.
            """,
            "source": SIPRI_Source,
            "citation": SIPRI_Citation
        },
    ],
    f"{OECD}": [
        {
            "main_name":  "FDI Flows (Inward)",
            "index_name": "FDI Flows - Inward (% of GDP)",
            "description": """
            Foreign Direct Investment (FDI) flows record the value of cross-border transactions related to direct investment during a given period of time, usually a quarter or a year. Financial flows consist of equity transactions, reinvestment of earnings, and intercompany debt transactions. 
            Inward flows represent transactions that increase the investment that foreign investors have in enterprises resident in the reporting economy less transactions that decrease the investment of foreign investors in resident enterprises. 
            FDI flows are measured in USD and as a share of GDP. FDI creates stable and long-lasting links between economies.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in foreign direct investment flows into the country, suggesting growing confidence from foreign investors and a strengthening connection with global economies, which could lead to enhanced economic growth and job creation.
            \n📉 If the index score goes down, it signifies a decrease in foreign direct investment, potentially reflecting reduced investor confidence or less favorable economic conditions in the country, which could impact long-term economic stability and growth prospects.
            """,
            "source": "https://data.oecd.org/fdi/fdi-flows.htm",
            "citation": get_oecd_citation("FDI Flows - Inward (% of GDP)", "https://data.oecd.org/fdi/fdi-flows.htm")
        },
        {
            "main_name":  "FDI Flows (Outward)",
            "index_name": "FDI Flows - Outward (% of GDP)",
            "description": """
            Foreign Direct Investment (FDI) flows record the value of cross-border transactions related to direct investment during a given period of time, usually a quarter or a year. Financial flows consist of equity transactions, reinvestment of earnings, and intercompany debt transactions. 
            Outward flows represent transactions that increase the investment that investors in the reporting economy have in enterprises in a foreign economy, such as through purchases of equity or reinvestment of earnings, less any transactions that decrease the investment that investors in the reporting economy have in enterprises in a foreign economy, such as sales of equity or borrowing by the resident investor from the foreign enterprise. 
            FDI flows are measured in USD and as a share of GDP. FDI creates stable and long-lasting links between economies.
            """,
            "tips": """
            📈 If the index score goes up, it signifies an increase in foreign direct investment flows, indicating growing investor confidence in the economy and a strengthening of economic ties with other countries, which can lead to enhanced technological transfer and job creation.
            \n📉 If the index score goes down, it reflects a decrease in foreign direct investment flows, suggesting a potential decline in investor confidence or economic attractiveness, which could impact the economy's long-term growth prospects and its integration into the global market.
            """,
            "source": "https://data.oecd.org/fdi/fdi-flows.htm",
            "citation": get_oecd_citation("FDI Flows - Outward (% of GDP)", "https://data.oecd.org/fdi/fdi-flows.htm")
        },
        {
            "main_name":  "FDI Stocks (Outward)",
            "index_name": "FDI Stocks - Outward (% of GDP)",
            "description": """
            Foreign Direct Investment (FDI) stocks measure the total level of direct investment at a given point in time, usually the end of a quarter or of a year. 
            The outward FDI stock is the value of the resident investors' equity in and net loans to enterprises in foreign economies. 
            FDI stocks are measured in USD and as a share of GDP. FDI creates stable and long-lasting links between economies.
            """,
            "tips": """
            📈 If the index score goes up, it suggests an increase in the country's outward Foreign Direct Investment, indicating a growing confidence and expansion of its investors into foreign markets, reflecting economic strength and international engagement.
            \n📉 If the index score goes down, it indicates a decrease in the country's outward Foreign Direct Investment, possibly signaling a retreat from international markets or a shift towards more domestic-focused investment strategies, potentially due to economic challenges or strategic realignments.
            """,
            "source": "https://data.oecd.org/fdi/fdi-stocks.htm",
            "citation": get_oecd_citation("FDI Stocks - Outward (% of GDP)", "https://data.oecd.org/fdi/fdi-stocks.htm")
        },
        {
            "main_name":  "FDI Stocks (Inward)",
            "index_name": "FDI Stocks - Inward (% of GDP)",
            "description": """
            Foreign Direct Investment (FDI) stocks measure the total level of direct investment at a given point in time, usually the end of a quarter or of a year. \n
            The inward FDI stock is the value of foreign investors' equity in and net loans to enterprises resident in the reporting economy. \n
            FDI stocks are measured in USD and as a share of GDP. FDI creates stable and long-lasting links between economies.
            """,
            "tips": """
            📈 If the index score goes up, it indicates an increase in foreign investors' equity in and net loans to enterprises within the reporting economy, suggesting growing international confidence in the economy and the establishment of more stable economic connections.
            \n📉 If the index score goes down, it signifies a decrease in the level of foreign direct investment, which could reflect a declining international confidence in the economy or less stable economic connections, potentially impacting economic growth and development negatively.
            """,
            "source": "https://data.oecd.org/fdi/fdi-stocks.htm",
            "citation": get_oecd_citation("FDI Stocks - Inward (% of GDP)", "https://data.oecd.org/fdi/fdi-stocks.htm")
        },
    ]
    
}
