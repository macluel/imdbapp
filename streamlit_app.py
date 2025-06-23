import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import bcrypt

# Google Sheets Setup
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds_dict = st.secrets["google"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(credentials)

# Replace with your Google Sheet name
SHEET_NAME = "UserCredentials"
sheet = gc.open(SHEET_NAME).sheet1

# Helper functions
def get_user_row(username):
    users = sheet.get_all_records()
    for i, user in enumerate(users):
        if user['username'] == username:
            return i+2, user  # +2 because get_all_records skips header, and Google Sheets is 1-indexed
    return None, None

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def register_user(username, password):
    hashed = hash_password(password)
    sheet.append_row([username, hashed, '', '', ''])

def update_credentials(username, notion_token, database_id, tmdb_api_key):
    row, _ = get_user_row(username)
    if row:
        sheet.update(f'C{row}:E{row}', [[notion_token, database_id, tmdb_api_key]])

def get_credentials(username):
    _, user = get_user_row(username)
    if user:
        return user['notion_token'], user['database_id'], user['tmdb_api_key']
    return '', '', ''

# Streamlit UI
st.title("🔑 Login")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

mode = st.radio("Choose mode:", ["Login", "Register"])

if mode == "Register":
    st.subheader("Create Account")
    reg_username = st.text_input("Username", key="reg_user")
    reg_password = st.text_input("Password", type="password", key="reg_pass")
    if st.button("Register"):
        row, _ = get_user_row(reg_username)
        if row:
            st.error("Username already exists.")
        else:
            register_user(reg_username, reg_password)
            st.success("Registered! Now log in.")

if mode == "Login":
    st.subheader("Login")
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Login"):
        row, user = get_user_row(username)
        if not row:
            st.error("User not found.")
        elif not check_password(password, user['password_hash']):
            st.error("Wrong password.")
        else:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("Logged in! Reload the page if you don't see the credential form.")

if st.session_state.get("logged_in"):
    st.subheader("Save your API credentials")
    notion_token, database_id, tmdb_api_key = get_credentials(st.session_state.username)
    notion_token = st.text_input("Notion Token", value=notion_token or "")
    database_id = st.text_input("Database ID", value=database_id or "")
    tmdb_api_key = st.text_input("TMDb API Key", value=tmdb_api_key or "")
    if st.button("Save API Credentials"):
        update_credentials(st.session_state.username, notion_token, database_id, tmdb_api_key)
        st.success("Credentials saved!")

    # You can now use these credentials in your app!
    # st.write("Use your credentials here:", notion_token, database_id, tmdb_api_key)

    if st.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()
