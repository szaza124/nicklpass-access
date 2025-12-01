from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone


# ------------------------------------------------------
# Build credentials from session token
# ------------------------------------------------------
def build_credentials(token_data):
    return Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )


# ------------------------------------------------------
# Convert timestamp → days since
# ------------------------------------------------------
def days_since(timestamp_str):
    if not timestamp_str:
        return 999
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - dt).days


# ------------------------------------------------------
# Google Login Activity Status (used for user-level info)
# ------------------------------------------------------
def activity_status(days):
    if days <= 30:
        return "🟢 Active"
    elif days <= 90:
        return "🟡 Maybe Active"
    return "🔴 Inactive"


# ------------------------------------------------------
# Identify Google-native apps (Drive, Gmail, etc.)
# ------------------------------------------------------
GOOGLE_APPS = [
    "google", "gmail", "calendar", "drive",
    "docs", "sheets", "slides", "chrome",
    "workspace", "meet", "gcp"
]

def is_google_app(name):
    if not name:
        return False
    return any(g in name.lower() for g in GOOGLE_APPS)


# ------------------------------------------------------
# Fetch org-wide app graph via Directory API
# ------------------------------------------------------
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


# ------------------------------------------------------
# TRUE INTERACTIVE LOGIN from Reports API (OAuth login events)
# ------------------------------------------------------
def fetch_interactive_logins(creds, user_email, lookback_days=180):
    """
    Returns:
        { client_id: last_interactive_login_timestamp }

    Uses only human-triggered events:
        - oauth_authorization
        - login_success
        - id_token
    """
    service = build("admin", "reports_v1", credentials=creds)

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=lookback_days)).isoformat()

    results = {}

    try:
        activities = (
            service.activities()
            .list(
                userKey=user_email,
                applicationName="login",
                startTime=start_date,
                maxResults=500,
            )
            .execute()
        )

        for item in activities.get("items", []):
            event_time = item["id"]["time"]

            for event in item.get("events", []):
                if event["name"] in ["oauth_authorization", "login_success", "id_token"]:

                    client_id = None
                    for p in event.get("parameters", []):
                        if p.get("name") == "client_id":
                            client_id = p.get("value")

                    if client_id:
                        results[client_id] = event_time

    except Exception as e:
        print("Reports API error:", e)

    return results


# ------------------------------------------------------
# BLENDED USAGE SCORING
# (Green = True login, Yellow = Token refresh, Red = Inactive)
# ------------------------------------------------------
def blended_activity_status(app_token, last_interactive=None):
    """
    Simplified MVP logic:
    Green = app_token exists (connected)
    Red   = no app_token (not connected)
    """
    if app_token:
        return ("🟢", "Connected", "")
    else:
        return ("🔴", "Not Connected", "")