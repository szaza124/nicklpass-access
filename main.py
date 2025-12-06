from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router

# Google APIs
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# -------------------------
# FastAPI App + Static
# -------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


# -------------------------
# Home
# -------------------------
@app.get("/")
def home():
    return HTMLResponse("""
        <link rel="stylesheet" href="/static/style.css">
        <div class="card">
            <h1>Nicklpass Access Visibility</h1>
            <a href="/login"><button>Sign in with Google</button></a>
        </div>
    """)


# -------------------------
# Not Admin
# -------------------------
@app.get("/not_admin")
def not_admin():
    return HTMLResponse("""
        <link rel="stylesheet" href="/static/style.css">
        <div class="card">
            <h1>Admin Access Required</h1>
            <p>This tool requires a Google Workspace Admin to view organizational data.</p>
            <a href="/">← Back to Home</a>
        </div>
    """)


# -------------------------
# Users List
# -------------------------
@app.get("/users")
def list_users(request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import (
        build_credentials,
        fetch_workspace_graph,
        days_since,
        activity_status,
    )

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    directory = build("admin", "directory_v1", credentials=creds)

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += "<div class='card'><h1>Users</h1>"

    html += "<table><tr><th>User</th><th>Google Activity</th><th># Connected Apps</th></tr>"

    for email, apps in user_to_apps.items():
        record = directory.users().get(userKey=email).execute()
        last_login = record.get("lastLoginTime")
        days = days_since(last_login)
        google_status = activity_status(days)

        html += f"""
        <tr>
            <td><a href='/users/{email}'>{email}</a></td>
            <td>{google_status}</td>
            <td>{len(apps)}</td>
        </tr>
        """

    html += "</table></div>"
    return HTMLResponse(html)


# -------------------------
# User Detail Page
# -------------------------
@app.get("/users/{email}")
def view_user(email: str, request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import (
        build_credentials,
        fetch_workspace_graph,
        days_since,
        activity_status,
        is_google_app
    )

    creds = build_credentials(token)

    # Fetch workspace data
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    # Fetch Google login recency
    directory = build("admin", "directory_v1", credentials=creds)
    record = directory.users().get(userKey=email).execute()
    last_login = record.get("lastLoginTime")
    days = days_since(last_login)
    google_status = activity_status(days)

    apps = user_to_apps.get(email, [])

    # ----------------------
    # PAGE HTML
    # ----------------------
    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += f"<div class='card'><h1>{email}</h1>"

    html += f"""
    <p style='font-size: 1.2rem;'>
        <strong>Google Login Activity:</strong> {google_status}<br>
        Last login: {days} days ago
    </p>
    """

    html += "<h2>Connected Apps</h2>"
    html += "<table><tr><th>App</th><th>Status</th></tr>"

    for t in apps:
        name = t.get("displayText", "Unknown App")
        client = t.get("clientId")

        if is_google_app(name):
            continue

        html += f"<tr><td><a href='/apps/{client}'>{name}</a></td><td>🟢 Connected</td></tr>"

    html += "</table></div>"
    html += "<a href='/users'>← Back to Users</a>"
    return HTMLResponse(html)


# -------------------------
# Apps List
# -------------------------
@app.get("/apps")
def list_apps(request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import build_credentials, fetch_workspace_graph

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    sorted_apps = sorted(
        app_to_users.items(),
        key=lambda x: len(x[1]["users"]),
        reverse=True
    )

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += "<div class='card'><h1>Apps (Ranked by Connections)</h1>"
    html += "<table><tr><th>App</th><th># Users Connected</th></tr>"

    for client_id, data in sorted_apps:
        html += f"<tr><td><a href='/apps/{client_id}'>{data['displayText']}</a></td><td>{len(data['users'])}</td></tr>"

    html += "</table></div>"
    return HTMLResponse(html)


# -------------------------
# App Detail Page
# -------------------------
@app.get("/apps/{client_id}")
def view_app(client_id: str, request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import (
        build_credentials,
        fetch_workspace_graph,
        days_since,
        activity_status,
    )

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    if client_id not in app_to_users:
        return HTMLResponse("<h1>App Not Found</h1>")

    app_data = app_to_users[client_id]
    app_name = app_data["displayText"]
    users = app_data["users"]

    directory = build("admin", "directory_v1", credentials=creds)

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += f"<div class='card'><h1>{app_name}</h1><h2>Users</h2>"
    html += "<table><tr><th>User</th><th>Google Activity</th><th>Status</th></tr>"

    for email in users:
        record = directory.users().get(userKey=email).execute()
        last_login = record.get("lastLoginTime")
        days = days_since(last_login)
        google_status = activity_status(days)

        html += f"""
        <tr>
            <td><a href='/users/{email}'>{email}</a></td>
            <td>{google_status} ({days} days ago)</td>
            <td>🟢 Connected</td>
        </tr>
        """

    html += "</table></div>"
    html += "<a href='/apps'>← Back to Apps</a>"
    return HTMLResponse(html)


# -------------------------
# Debug Endpoints
# -------------------------
@app.get("/debug/audit/{email}")
def debug_audit(email: str, request: Request):
    from google_admin import build_credentials, fetch_interactive_logins
    token = request.session["google_token"]
    creds = build_credentials(token)
    return fetch_interactive_logins(creds, email)


@app.get("/debug/tokens/{email}")
def debug_tokens(email: str, request: Request):
    token = request.session.get("google_token")
    if not token:
        return {"error": "Not logged in"}

    from google_admin import build_credentials
    creds = build_credentials(token)
    service = build("admin", "directory_v1", credentials=creds)

    try:
        return service.tokens().list(userKey=email).execute()
    except Exception as e:
        return {"error": str(e)}


# -------------------------
# Connected Apps (Personal User View)
# -------------------------
@app.get("/connected-apps")
def connected_apps(request: Request):
    token_data = request.session.get("google_token")

    if not token_data:
        return RedirectResponse("/")

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )

    service = build("people", "v1", credentials=creds)
    response = service.people().get(
        resourceName="people/me",
        personFields="metadata"
    ).execute()

    sources = response.get("metadata", {}).get("sources", []) or []

    apps = [
        s for s in sources
        if s.get("type") == "APPLICATION"
    ]

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/'>Home</a></div>"
    html += "<div class='card'><h1>Your Connected Apps</h1>"
    html += "<table><tr><th>App Name</th><th>Client ID</th><th>Last Updated</th></tr>"

    for a in apps:
        name = a.get("profileName", "Unknown App")
        client_id = a.get("clientId", "N/A")
        update = a.get("updateTime", "N/A")

        html += f"""
        <tr>
            <td>{name}</td>
            <td>{client_id}</td>
            <td>{update}</td>
        </tr>
        """

    html += "</table></div>"
    html += "<a href='/'>← Back to Home</a>"

    return HTMLResponse(html)