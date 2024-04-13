from streamlit_extras.customize_running import center_running
import streamlit                        as st


st.set_page_config(layout = "wide", page_title = "Say Hi!", page_icon = "👋")
center_running()

st.write(st.query_params)

if 'message_sent' in st.query_params:
    st.query_params.clear()
    st.toast("Thank you for your message! We will get back to you shortly.", icon='👋')


st.header(":mailbox: Get it touch!")


# contact_form_html = """
#  <form action="https://formsubmit.co/qgintelligence@gmail.com" method="POST">
#       <input type="hidden" name="_captcha" value="false">
#       <input type="text" name="name" placeholder="Your name" required>
#       <input type="email" name="email" placeholder="Your email" required>
#       <input type="hidden" name="_next" value="https://qgintelligence.streamlit.app/Contact?message_sent=true">
#       <textarea name="message" placeholder="Your message here"></textarea>
#       <button type="submit">Send</button>
#  </form>
#  """
# st.markdown(contact_form_html, unsafe_allow_html = True)


contact_form_html = """
<form action="https://formsubmit.co/qgintelligence@gmail.com" method="POST" onsubmit="disableSubmitButton()">
     <input type="hidden" name="_captcha" value="false">
     <input type="text" name="name" placeholder="Your name" required>
     <input type="email" name="email" placeholder="Your email" required>
     <input type="hidden" name="_next" value="https://qgintelligence.streamlit.app/Contact?message_sent=true">
     <textarea name="message" placeholder="Your message here"></textarea>
     <button type="submit" id="submitBtn">Send</button>
</form>
<script>
function disableSubmitButton() {
    document.getElementById('submitBtn').disabled = true;
    document.getElementById('submitBtn').innerText = 'Sending...';
    return true; // Ensure form still submits
}
</script>
"""

st.markdown(contact_form_html, unsafe_allow_html=True)



def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
CONTACT_CSS_PATH = "css/Contact.css"
local_css(CONTACT_CSS_PATH)
