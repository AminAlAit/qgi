from streamlit_extras.customize_running import center_running
import streamlit                        as st


st.set_page_config(layout = "wide", page_title = "Say Hi!", page_icon = "👋")
center_running()


st.header(":mailbox: Get it touch!")


# "https://qgintelligence.streamlit.app"

contact_form_html = """
<form action="https://formsubmit.co/qgintelligence@gmail.com" method="POST">
     <input type="hidden" name="_captcha" value="false">
     <input type="text" name="name" placeholder="Your name" required>
     <input type="email" name="email" placeholder="Your email" required>
     <input type="hidden" name="_next" value=http://localhost:8501>
     <textarea name="message" placeholder="Your message here"></textarea>
     <button type="submit">Send</button>
</form>
"""

st.markdown(contact_form_html, unsafe_allow_html = True)

# Use Local CSS File
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

CONTACT_CSS_PATH = "css/Contact.css"
local_css(CONTACT_CSS_PATH)
