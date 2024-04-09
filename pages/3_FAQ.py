import streamlit as st

# Title for the FAQ page
st.title("Frequently Asked Questions")

faqs = [
    (
        "What is QGI?",
        "QGI (Quantitative Geopolitical Intelligence) is a data analytics platform that identifies patterns in geopolitical and economic indicators across countries, aiming to bridge data science with geopolitics."
    ),
    (
        "How does QGI find patterns between countries?",
        "QGI analyzes over a million patterns by comparing specific indexes like energy exports and military expenditure across different countries and time spans. It looks for correlations of 90% or more in these indexes to identify significant patterns."
    ),
    (
        "Can QGI predict future geopolitical events?",
        "While QGI is not a predictive tool, it helps identify historical patterns that may provide insights into potential future trends. It's meant to aid in understanding geopolitical dynamics and not to predict specific events."
    ),
    (
        "How can I use QGI?",
        "Users can explore patterns between countries, examine detailed index plots, and view significant events that correspond with the data. It's designed for anyone interested in geopolitics, from researchers to policy makers."
    ),
    (
        "Do I need a technical background to use QGI?",
        "No, QGI is designed to be accessible to users with varied backgrounds. We provide clear explanations and visualizations to make the data understandable without requiring expertise in data science or geopolitics."
    ),
    (
        "What are the sectors covered by QGI indexes?",
        "QGI covers a wide range of sectors including Social, Political, Energy, Military, and more. This diverse coverage allows for a comprehensive analysis of geopolitical behavior."
    ),
    (
        "What is the Pattern Power Score?",
        "The Pattern Power Score (PPS) is a unique metric created by QGI to measure the strength of identified patterns, taking into account the number of indexes involved, their average correlation, and the length of the pattern."
    ),
    (
        "How current is the data in QGI?",
        "QGI's database includes data from 1990 to 2023, ensuring that users have access to both historical and recent patterns."
    ),
    (
        "How is QGI different from other geopolitical analysis tools?",
        "QGI stands out by offering a quantitative approach to understanding geopolitical relationships, backed by a vast dataset and a unique algorithm for identifying patterns."
    ),
    (
        "Who can benefit from using QGI?",
        "Policymakers, researchers, educators, students, journalists, and anyone with an interest in geopolitics can find QGI's insights valuable."
    ),
    (
        "How can I provide feedback or suggest a feature?",
        "We welcome your feedback and suggestions. You can contact us through the platform or via our support email to share your thoughts."
    ),
]

# Iterating through the list of FAQs to create an expander for each
for question, answer in faqs:
    with st.expander(question):
        st.markdown(answer)

# Optionally, add a contact form or additional information at the bottom
st.markdown("## Your questions is not answered?")
st.markdown("Feel free to [contact us](https://qgintelligence.streamlit.app/Contact) with any additional questions or feedback!")
