import streamlit as st
import requests
import json

def show_credentials_page():
    st.title("🔐 Insira suas credenciais")
    with st.form("credentials_form"):
        NOTION_TOKEN = st.text_input("Notion Token", type="password")
        DATABASE_ID = st.text_input("Notion Database ID")
        TMDB_API_KEY = st.text_input("TMDb API Key", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            if NOTION_TOKEN and DATABASE_ID and TMDB_API_KEY:
                st.session_state["NOTION_TOKEN"] = NOTION_TOKEN
                st.session_state["DATABASE_ID"] = DATABASE_ID
                st.session_state["TMDB_API_KEY"] = TMDB_API_KEY
                st.session_state["authenticated"] = True
                st.success("Credenciais salvas! Recarregando app...")
                st.experimental_rerun()
            else:
                st.error("Por favor, preencha todas as credenciais.")

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
        if title_obj and isinstance(title_obj, list):
            return title_obj[0].get("plain_text", "")
    except Exception as e:
        st.warning(f"Erro ao extrair título: {e}")
    return ""

def safe_extract_original_title(page):
    try:
        orig_obj = page.get("properties", {}).get("Original Title", {}).get("rich_text", [])
        if orig_obj and isinstance(orig_obj, list):
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

def main_app():
    st.title("🎬 Notion + TMDb Poster Picker & Atualizador")

    # Recupera credenciais da sessão
    notion_token = st.session_state.get("NOTION_TOKEN")
    database_id = st.session_state.get("DATABASE_ID")
    tmdb_api_key = st.session_state.get("TMDB_API_KEY")

    # Busca filmes do Notion
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

    # -- Buscar no TMDb --
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

    # -- Atualizar campos do Notion (opcional) --
    if st.button("Atualizar campos principais do Notion com dados do TMDb"):
        tmdb_details = get_tmdb_details(tmdb_movie["id"], tmdb_api_key)
        update_movie_fields_in_notion(notion_token, selected_page["id"], tmdb_details)

    # -- Escolher e atualizar pôster --
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
        st.session_state["chosen_poster_url"] = None  # Limpa para evitar múltiplas atualizações

def main():
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        show_credentials_page()
    else:
        main_app()
        if st.button("Sair"):
            st.session_state.clear()
            st.experimental_rerun()

if __name__ == "__main__":
    main()
