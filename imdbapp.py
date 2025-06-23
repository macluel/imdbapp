import streamlit as st
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
import bcrypt

# --- Google Sheets Setup ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds_dict = st.secrets["google"]
credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(credentials)

SHEET_NAME = "UserCredentials"
sheet = gc.open(SHEET_NAME).sheet1

# --- Helper Functions for User Auth ---
def get_user_row(username):
    users = sheet.get_all_records()
    for i, user in enumerate(users):
        if user['username'] == username:
            return i+2, user  # +2 for 1-indexed + header
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

# --- Movie/Notion/TMDB logic (your original functions) ---
def get_notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

def get_movies_from_notion(token, database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    try:
        response = requests.post(url, headers=get_notion_headers(token), timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.RequestException as e:
        st.error(f"Erro ao buscar filmes do Notion: {e}")
        return []

def safe_extract_title(page):
    try:
        title_obj = page.get("properties", {}).get("Title", {}).get("title", [])
        if title_obj and isinstance(title_obj, list) and len(title_obj) > 0:
            return title_obj[0].get("plain_text", "")
    except Exception as e:
        st.warning(f"Erro ao extrair título: {e}")
    return ""

def safe_extract_original_title(page):
    try:
        orig_obj = page.get("properties", {}).get("Original Title", {}).get("rich_text", [])
        if orig_obj and isinstance(orig_obj, list) and len(orig_obj) > 0:
            return orig_obj[0].get("plain_text", "")
    except Exception as e:
        st.warning(f"Erro ao extrair título original: {e}")
    return ""

def search_tmdb_movie(query, api_key):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&language=pt-BR&query={requests.utils.quote(query)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])

def get_tmdb_details(movie_id, api_key):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={api_key}&language=pt-BR"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_posters_from_tmdb(movie_id, api_key):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={api_key}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    posters = resp.json().get("posters", [])
    poster_infos = []
    for poster in posters:
        url = "https://image.tmdb.org/t/p/original" + poster["file_path"]
        lang = poster.get("iso_639_1", "??")
        country = poster.get("iso_3166_1", "??")
        poster_infos.append({
            "url": url,
            "lang": lang,
            "country": country,
        })
    return poster_infos

def update_poster_in_notion(token, page_id, poster_url):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "Poster": {
                "files": [{
                    "type": "external",
                    "name": "Poster",
                    "external": {"url": poster_url}
                }]
            }
        }
    }
    try:
        response = requests.patch(url, headers=get_notion_headers(token), data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        st.success("Poster atualizado no Notion! ✅")
    except requests.RequestException as e:
        st.error(f"Falha ao atualizar o poster: {e}")
        if hasattr(e, 'response') and e.response is not None:
            st.error(f"Response: {e.response.text}")

def update_movie_fields_in_notion(token, page_id, movie):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    properties = {}
    if movie.get("title"):
        properties["Title"] = {"title": [{"text": {"content": movie["title"]}}]}
    if movie.get("original_title"):
        properties["Original Title"] = {"rich_text": [{"text": {"content": movie["original_title"]}}]}
    if movie.get("overview"):
        properties["Synopsis"] = {"rich_text": [{"text": {"content": movie["overview"]}}]}
    if movie.get("release_date"):
        properties["Release Date"] = {"date": {"start": movie["release_date"]}}
    if movie.get("original_language"):
        properties["Language"] = {"select": {"name": movie["original_language"]}}
    payload = {"properties": properties}
    try:
        response = requests.patch(url, headers=get_notion_headers(token), data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        st.success("Dados do filme atualizados no Notion! ✅")
    except requests.RequestException as e:
        st.error(f"Falha ao atualizar campos: {e}")
        if hasattr(e, 'response') and e.response is not None:
            st.error(f"Response: {e.response.text}")

# --- Main App Logic ---
def main_app(notion_token, database_id, tmdb_api_key):
    st.title("🎬 Notion + TMDb Poster Picker & Atualizador")

    movies = get_movies_from_notion(notion_token, database_id)
    if not movies:
        st.warning("Nenhum filme encontrado no Notion.")
        return

    movie_options = ["-- Escolha um filme --"] + [
        f"{safe_extract_title(m)} | {safe_extract_original_title(m)}" for m in movies
    ]
    selected_idx = st.selectbox(
        "Escolha o filme para atualizar o pôster:",
        range(len(movie_options)),
        format_func=lambda x: movie_options[x]
    )

    if selected_idx == 0:
        st.info("Selecione um filme para continuar.")
        return

    selected_page = movies[selected_idx - 1]
    selected_title = safe_extract_title(selected_page)
    selected_orig_title = safe_extract_original_title(selected_page)
    st.markdown(f"**Selecionado:** `{selected_title}` (`{selected_orig_title}`)")

    st.subheader("1️⃣ Buscar filme no TMDb")
    search_query = st.text_input("Título para buscar no TMDb:", value=selected_orig_title or selected_title)
    tmdb_results = search_tmdb_movie(search_query, tmdb_api_key)
    if not tmdb_results:
        st.warning("Nenhum resultado encontrado no TMDb.")
        return

    tmdb_options = [f"{res['title']} ({res.get('release_date', '??')[:4]}) | {res['original_title']}" for res in tmdb_results]
    tmdb_idx = st.selectbox("Escolha o resultado TMDb:", range(len(tmdb_options)), format_func=lambda x: tmdb_options[x])
    tmdb_movie = tmdb_results[tmdb_idx]
    st.write(f"Selecionado TMDb: {tmdb_movie['title']} ({tmdb_movie.get('release_date', '??')[:4]})")

    if st.button("Atualizar campos principais do Notion com dados do TMDb"):
        tmdb_details = get_tmdb_details(tmdb_movie["id"], tmdb_api_key)
        update_movie_fields_in_notion(notion_token, selected_page["id"], tmdb_details)

    st.subheader("2️⃣ Escolher o pôster")
    posters = get_posters_from_tmdb(tmdb_movie["id"], tmdb_api_key)
    if not posters:
        st.warning("Nenhum pôster encontrado no TMDb para este filme.")
        return

    columns = st.columns(3)
    chosen_poster_url = st.session_state.get("chosen_poster_url", None)
    for idx, poster in enumerate(posters):
        col = columns[idx % 3]
        with col:
            st.image(poster["url"], use_container_width=True, caption=f"{idx} | Idioma: {poster['lang']} | País: {poster['country']}")
            if st.button(f"Usar este pôster [{idx}]", key=f"posterbtn{idx}"):
                st.session_state["chosen_poster_url"] = poster["url"]
                chosen_poster_url = poster["url"]

    if chosen_poster_url:
        st.success("Pôster selecionado! Atualizando Notion...")
        update_poster_in_notion(notion_token, selected_page["id"], chosen_poster_url)
        st.session_state["chosen_poster_url"] = None

# --- Login & Sign Up UI ---
def login_signup():
    st.title("🔑 Login/Cadastro de Usuário")
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    mode = st.radio("Escolha:", ["Entrar", "Registrar"])

    if mode == "Registrar":
        st.subheader("Criar Conta")
        reg_username = st.text_input("Usuário", key="reg_user")
        reg_password = st.text_input("Senha", type="password", key="reg_pass")
        if st.button("Registrar"):
            row, _ = get_user_row(reg_username)
            if row:
                st.error("Usuário já existe.")
            else:
                register_user(reg_username, reg_password)
                st.success("Registrado! Agora faça login.")

    if mode == "Entrar":
        st.subheader("Login")
        username = st.text_input("Usuário", key="login_user")
        password = st.text_input("Senha", type="password", key="login_pass")
        if st.button("Entrar"):
            row, user = get_user_row(username)
            if not row:
                st.error("Usuário não encontrado.")
            elif not check_password(password, user['password_hash']):
                st.error("Senha incorreta.")
            else:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Logado! Avance para salvar credenciais ou usar o app.")

def credentials_ui():
    st.subheader("Salve suas credenciais de API")
    notion_token, database_id, tmdb_api_key = get_credentials(st.session_state.username)
    notion_token = st.text_input("Notion Token", value=notion_token or "")
    database_id = st.text_input("Database ID", value=database_id or "")
    tmdb_api_key = st.text_input("TMDb API Key", value=tmdb_api_key or "")
    if st.button("Salvar Credenciais"):
        update_credentials(st.session_state.username, notion_token, database_id, tmdb_api_key)
        st.success("Credenciais salvas!")
    return notion_token, database_id, tmdb_api_key

def main():
    if not st.session_state.get("logged_in", False):
        login_signup()
    else:
        notion_token, database_id, tmdb_api_key = get_credentials(st.session_state.username)
        # If any credentials missing, ask user to save them
        if not (notion_token and database_id and tmdb_api_key):
            notion_token, database_id, tmdb_api_key = credentials_ui()
        # If still missing, wait for user
        if not (notion_token and database_id and tmdb_api_key):
            st.info("Por favor, salve todas as credenciais para usar o app.")
        else:
            main_app(notion_token, database_id, tmdb_api_key)
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
