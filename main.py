from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router


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

    from google_admin import build_credentials, fetch_workspace_graph

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += "<div class='card'><h1>Users</h1>"

    html += "<table><tr><th>User</th><th>Apps</th></tr>"
    for email, apps in user_to_apps.items():
        html += f"<tr><td><a href='/users/{email}'>{email}</a></td><td>{len(apps)}</td></tr>"
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
        fetch_interactive_logins,
        blended_activity_status,
        is_google_app
    )
    from googleapiclient.discovery import build
    from datetime import datetime, timezone

    creds = build_credentials(token)

    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    directory = build("admin", "directory_v1", credentials=creds)
    record = directory.users().get(userKey=email).execute()

    last_login = record.get("lastLoginTime")
    days = days_since(last_login)
    google_status = activity_status(days)

    apps = user_to_apps.get(email, [])

    # TRUE USAGE
    interactive = fetch_interactive_logins(creds, email)

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"

    html += f"<div class='card'><h1>{email}</h1>"
    html += f"<p><strong>Google Login Activity:</strong> {google_status} — {days} days ago</p>"

    html += "<h2>Connected Apps</h2>"
    html += "<table><tr><th>App</th><th>Status</th><th>Detail</th></tr>"

    for t in apps:
        name = t.get("displayText", "Unknown App")
        client = t.get("clientId")

        if is_google_app(name):
            continue

        last_interactive = interactive.get(client)
        emoji, status_text, detail = blended_activity_status(t, last_interactive)

        html += f"<tr><td><a href='/apps/{client}'>{name}</a></td><td>{emoji} {status_text}</td><td>{detail}</td></tr>"

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
    html += "<div class='card'><h1>Apps (Ranked by Usage)</h1>"

    html += "<table><tr><th>App</th><th># Users</th></tr>"
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
        fetch_interactive_logins,
        blended_activity_status
    )
    from googleapiclient.discovery import build
    from datetime import datetime, timezone

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

    html += "<table><tr><th>User</th><th>Status</th><th>Detail</th></tr>"

    for email in users:
        record = directory.users().get(userKey=email).execute()
        last_login = record.get("lastLoginTime")

        interactive = fetch_interactive_logins(creds, email)
        last_interactive = interactive.get(client_id)

        # Get this user's tokens for background activity
        tokens = directory.tokens().list(userKey=email).execute().get("items", [])
        token = next((t for t in tokens if t.get("clientId") == client_id), None)

        emoji, status_text, detail = blended_activity_status(token, last_interactive)

        html += f"<tr><td><a href='/users/{email}'>{email}</a></td><td>{emoji} {status_text}</td><td>{detail}</td></tr>"

    html += "</table></div>"
    html += "<a href='/apps'>← Back to Apps</a>"

    return HTMLResponse(html)

@app.get("/debug/audit/{email}")
def debug_audit(email: str, request: Request):
    from google_admin import build_credentials, fetch_interactive_logins
    token = request.session["google_token"]
    creds = build_credentials(token)
    return fetch_interactive_logins(creds, email)