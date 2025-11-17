import streamlit as st

st.title("🎬 Content Discovery App")
st.write(
    "Let's start building! For help and inspiration, head over to [docs.streamlit.io](https://docs.streamlit.io/)."
)
import streamlit as st
import json
import os
import base64
import bcrypt
from email.mime.text import MIMEText
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from simplejustwatchapi.justwatch import search as jw_search
from tmdbv3api import TMDb, Movie
import pandas as pd

# --- Configure TMDb ---
tmdb = TMDb()
tmdb.api_key = "YOUR_TMDB_API_KEY"
movie_api = Movie()

# --- Genre Mapping ---
GENRE_MAP = {
    12: "Adventure", 18: "Drama", 99: "Documentary", 10764: "Reality",
    80: "Crime", 35: "Comedy", 28: "Action"
}

# --- Gmail OAuth ---
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def gmail_send_email(to_email, subject, body):
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(userId='me', body={'raw': raw_message}).execute()

# --- User Authentication ---
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

users = load_users()

st.sidebar.title("User Login")
username = st.sidebar.text_input("Username:")
password = st.sidebar.text_input("Password:", type="password")
action = st.sidebar.radio("Action:", ["Login", "Register"])

if st.sidebar.button("Submit"):
    if action == "Register":
        if username in users:
            st.sidebar.error("Username already exists.")
        else:
            hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            users[username] = hashed_pw
            save_users(users)
            st.sidebar.success("Registration successful! Please log in.")
    elif action == "Login":
        if username in users and bcrypt.checkpw(password.encode(), users[username].encode()):
            st.sidebar.success(f"Welcome {username}!")
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
        else:
            st.sidebar.error("Invalid credentials.")

# --- Main App ---
if st.session_state.get("logged_in"):
    PREF_FILE = f"preferences_{st.session_state['username']}.json"

    def load_preferences():
        if os.path.exists(PREF_FILE):
            with open(PREF_FILE, "r") as f:
                return json.load(f)
        return {"query": "", "genres": ["Adventure"], "rating": 6.0, "year": 2015, "sort": "Rating"}

    def save_preferences(prefs):
        with open(PREF_FILE, "w") as f:
            json.dump(prefs, f)

    prefs = load_preferences()

    if "filters" not in st.session_state:
        st.session_state.filters = prefs
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = []

    st.title("🎬 Advanced Streaming Discovery Agent")
    st.write(f"Logged in as **{st.session_state['username']}**")

    # Inputs
    query = st.text_input("Enter what you want to watch:", st.session_state.filters["query"])
    genres = st.multiselect("Select preferred genres:", list(GENRE_MAP.values()), default=st.session_state.filters["genres"])
    rating = st.slider("Minimum Rating (0-10)", 0.0, 10.0, st.session_state.filters["rating"])
    year = st.number_input("Minimum Release Year", min_value=1900, max_value=2025, value=st.session_state.filters["year"])
    sort_by = st.radio("Sort results by:", ["Rating", "Release Year"], index=0 if st.session_state.filters["sort"] == "Rating" else 1)

    # Update filters and save permanently
    st.session_state.filters.update({"query": query, "genres": genres, "rating": rating, "year": year, "sort": sort_by})
    save_preferences(st.session_state.filters)

    # --- TMDb Search ---
    def tmdb_tool(query: str) -> list:
        search_results = movie_api.search(query)
        filtered_results = []
        for m in search_results[:20]:
            genres = [GENRE_MAP.get(gid, str(gid)) for gid in m.genre_ids]
            rating = getattr(m, "vote_average", 0)
            year = int(m.release_date.split("-")[0]) if m.release_date else 0
            if any(g in genres for g in ["Crime"]):
                continue
            if (any(g in genres for g in st.session_state.filters["genres"]) or any(g in ["Adventure", "Reality", "Documentary"] for g in genres)) and rating >= st.session_state.filters["rating"] and year >= st.session_state.filters["year"]:
                poster_url = f"https://image.tmdb.org/t/p/w500{m.poster_path}" if m.poster_path else None
                filtered_results.append({
                    "title": m.title,
                    "genres": ", ".join(genres),
                    "rating": rating,
                    "year": year,
                    "poster": poster_url
                })
        if st.session_state.filters["sort"] == "Rating":
            filtered_results.sort(key=lambda x: x["rating"], reverse=True)
        else:
            filtered_results.sort(key=lambda x: x["year"], reverse=True)
        return filtered_results

    # --- JustWatch Search ---
    def justwatch_tool(query: str) -> str:
        results = jw_search(query, country="GB", language="en", count=5, best_only=True)
        output = []
        for r in results:
            offers = ", ".join(r.offers)
            link = r.url if hasattr(r, "url") else "#"
            output.append(f"{r.title} - Available on: {offers} - {link}")
        return "\n".join(output)

    # --- Display Results ---
    if st.session_state.filters["query"]:
        tmdb_results = tmdb_tool(st.session_state.filters["query"])
        st.subheader("Results:")
        for item in tmdb_results:
            st.markdown(f"**{item['title']}** ({item['year']}) - ⭐ {item['rating']}")
            st.write(f"Genres: {item['genres']}")
            if item['poster']:
                st.image(item['poster'], width=150)
            if st.button(f"Add '{item['title']}' to Watchlist", key=item['title']):
                st.session_state.watchlist.append(item['title'])
        st.subheader("Streaming Availability:")
        st.markdown(justwatch_tool(st.session_state.filters["query"]))

    # --- Watchlist ---
    st.subheader("📌 Your Watchlist")
    if st.session_state.watchlist:
        st.write(", ".join(st.session_state.watchlist))

        if st.button("Export Watchlist to CSV"):
            df = pd.DataFrame(st.session_state.watchlist, columns=["Title"])
            df.to_csv(f"watchlist_{st.session_state['username']}.csv", index=False)
            st.success("Watchlist exported.")

        st.subheader("📧 Send Watchlist via Email")
        recipient_email = st.text_input("Enter recipient email:")
        if st.button("Send Email"):
            if recipient_email:
                try:
                    body = "Your Watchlist:\n" + "\n".join(st.session_state.watchlist)
                    gmail_send_email(recipient_email, "Your Streaming Watchlist", body)
                    st.success(f"Watchlist sent to {recipient_email}")
                except Exception as e:
                    st.error(f"Failed to send email: {e}")
            else:
                st.warning("Please enter an email address.")
    else:
        st.write("Your watchlist is empty.")
else:
    st.warning("Please log in to use the app.")
