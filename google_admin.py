from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timezone


def build_credentials(token_data):
    return Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )


def days_since(timestamp_str):
    if not timestamp_str:
        return 999
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - dt).days


def activity_status(days):
    if days <= 30:
        return "🟢 Active"
    elif days <= 90:
        return "🟡 Maybe Active"
    else:
        return "🔴 Inactive"


GOOGLE_APPS = [
    "google", "gmail", "calendar", "drive", "docs",
    "sheets", "slides", "chrome", "workspace", "meet", "gcp"
]

def is_google_app(name):
    if not name:
        return False
    return any(g in name.lower() for g in GOOGLE_APPS)


def fetch_workspace_graph(creds):
    service = build("admin", "directory_v1", credentials=creds)

    users = service.users().list(customer="my_customer").execute().get("users", [])

    user_to_apps = {}
    app_to_users = {}

    for user in users:
        email = user["primaryEmail"]
        tokens = service.tokens().list(userKey=email).execute().get("items", [])

        filtered = []
        for t in tokens:
            name = t.get("displayText", "")
            if is_google_app(name):
                continue

            filtered.append(t)

            client = t.get("clientId")
            if client not in app_to_users:
                app_to_users[client] = {"displayText": name, "users": []}
            app_to_users[client]["users"].append(email)

        user_to_apps[email] = filtered

    return user_to_apps, app_to_users