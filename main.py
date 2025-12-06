from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# -------------------------
# FastAPI Setup
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
# Users List (Admin Only)
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
# Admin View of Single User
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
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    directory = build("admin", "directory_v1", credentials=creds)
    record = directory.users().get(userKey=email).execute()
    last_login = record.get("lastLoginTime")
    days = days_since(last_login)
    google_status = activity_status(days)

    apps = user_to_apps.get(email, [])

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/'>Home</a></div>"
    html += f"<div class='card'><h1>{email}</h1>"
    html += f"<p><strong>Google Login Activity:</strong> {google_status}<br>Last login: {days} days ago</p>"

    html += "<h2>Connected Apps</h2>"
    html += "<table><tr><th>App</th><th>Status</th></tr>"

    for t in apps:
        name = t.get("displayText", "Unknown App")
        client = t.get("clientId")

        if is_google_app(name):
            continue

        html += f"<tr><td><a href='/apps/{client}'>{name}</a></td><td>🟢 Connected</td></tr>"

    html += "</table></div>"
    return HTMLResponse(html)


# -------------------------
# Apps List (Admin Only)
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
# View App Detail (Admin Only)
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

    html = """<link rel='stylesheet' href='/static/style.css'>"""
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
        </tr>"""

    html += "</table></div>"
    return HTMLResponse(html)


# -------------------------
# MY APPS — NON-ADMIN WORKSPACE USERS
# -------------------------
@app.get("/my-apps")
def my_apps(request: Request):
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

    # Fetch authenticated user's email
    oauth = build("oauth2", "v2", credentials=creds)
    user_email = oauth.userinfo().get().execute().get("email")

    # Fetch ONLY apps connected to this user
    directory = build("admin", "directory_v1", credentials=creds)

    try:
        tokens = directory.tokens().list(userKey=user_email).execute()
        items = tokens.get("items", [])
    except Exception as e:
        return HTMLResponse(f"<h1>Unable to fetch connected apps</h1><p>{e}</p>")

    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/'>Home</a></div>"
    html += f"<div class='card'><h1>Your Connected Apps</h1>"
    html += "<table><tr><th>App</th><th>Client ID</th><th>Scopes</th></tr>"

    for app in items:
        html += f"""
        <tr>
            <td>{app.get('displayText')}</td>
            <td>{app.get('clientId')}</td>
            <td>{', '.join(app.get('scopes', []))}</td>
        </tr>
        """

    html += "</table></div>"
    return HTMLResponse(html)