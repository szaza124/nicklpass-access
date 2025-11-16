from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router


# -------------------------
# FastAPI app
# -------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.include_router(auth_router)


# -------------------------
# HOME PAGE
# -------------------------
@app.get("/")
def home():
    return HTMLResponse("""
        <h1>Nicklpass Access Visibility</h1>
        <a href="/login">Sign in with Google</a>
    """)


# -------------------------
# NON-ADMIN PAGE
# -------------------------
@app.get("/not_admin")
def not_admin():
    return HTMLResponse("""
        <h1>Admin Access Required</h1>
        <p>This tool requires a Google Workspace Admin to review connected apps for the organization.</p>
        <a href="/">← Back to Home</a>
    """)


# -------------------------
# USERS LIST (Admins only)
# -------------------------
@app.get("/users")
def list_users(request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import build_credentials, fetch_workspace_graph

    creds = build_credentials(token)

    # Get org-wide data
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    html = "<h1>Users</h1><ul>"
    for email, apps in user_to_apps.items():
        html += f"<li><a href='/users/{email}'>{email}</a> — {len(apps)} apps</li>"
    html += "</ul>"

    html += "<br><a href='/apps'>View apps ranked by usage →</a>"

    return HTMLResponse(html)


# -------------------------
# USER DETAIL PAGE
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
        fetch_interactive_logins,   # NEW
        is_google_app
    )
    from googleapiclient.discovery import build
    from datetime import datetime, timezone

    creds = build_credentials(token)

    # -------------------------
    # Fetch org-wide graph
    # -------------------------
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    # -------------------------
    # Fetch last user login (Google login)
    # -------------------------
    service = build("admin", "directory_v1", credentials=creds)
    record = service.users().get(userKey=email).execute()

    last_login = record.get("lastLoginTime")
    days = days_since(last_login)
    status = activity_status(days)

    # -------------------------
    # Apps for this user
    # -------------------------
    apps = user_to_apps.get(email, [])

    # -------------------------
    # TRUE INTERACTIVE USAGE
    # Fetch *actual* login events (Reports API)
    # -------------------------
    interactive = fetch_interactive_logins(creds, email)

    # -------------------------
    # HTML + CSS header
    # -------------------------
    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += """
    <div class="nav">
        <a href="/users">Users</a>
        <a href="/apps">Apps</a>
        <a href="/">Home</a>
    </div>
    """

    html += f"<div class='card'><h1>{email}</h1>"
    html += f"<p><strong>Google account activity:</strong> {status} — {days} days ago</p>"

    html += "<h2>Connected Apps</h2>"
    html += "<table><tr><th>App</th><th>Status</th><th>Last Used</th></tr>"

    # -------------------------
    # Loop through apps
    # -------------------------
    for t in apps:
        name = t.get("displayText", "Unknown App")
        client_id = t.get("clientId")

        # Skip Google-native apps
        if is_google_app(name):
            continue

        # Interactive login check
        last_interactive = interactive.get(client_id)

        if last_interactive:
            dt = datetime.fromisoformat(last_interactive.replace("Z", "+00:00"))
            days_int = (datetime.now(timezone.utc) - dt).days

            if days_int <= 30:
                badge = "<span class='badge green'>Active</span>"
            elif days_int <= 90:
                badge = "<span class='badge yellow'>Maybe</span>"
            else:
                badge = "<span class='badge red'>Inactive</span>"

            last_used_str = f"{days_int} days ago"

        else:
            badge = "<span class='badge red'>Inactive</span>"
            last_used_str = "No recent login"

        html += f"<tr><td><a href='/apps/{client_id}'>{name}</a></td><td>{badge}</td><td>{last_used_str}</td></tr>"

    html += "</table></div>"
    html += "<a href='/users'>← Back to Users</a>"

    return HTMLResponse(html)


# -------------------------
# APPS RANKED BY USER COUNT
# -------------------------
@app.get("/apps")
def list_apps(request: Request):
    token = request.session.get("google_token")
    if not token:
        return RedirectResponse("/")

    from google_admin import build_credentials, fetch_workspace_graph

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    # Sort apps descending by # of users
    sorted_apps = sorted(
        app_to_users.items(),
        key=lambda entry: len(entry[1]["users"]),
        reverse=True
    )

    html = "<h1>Apps (Ranked by Usage)</h1><ul>"
    for client_id, data in sorted_apps:
        app_name = data["displayText"]
        count = len(data["users"])
        html += f"<li><a href='/apps/{client_id}'>{app_name}</a> — {count} users</li>"
    html += "</ul>"
    html += "<br><a href='/users'>← Back to Users</a>"

    return HTMLResponse(html)


# -------------------------
# APP DETAIL PAGE
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
        activity_status
    )
    from googleapiclient.discovery import build

    creds = build_credentials(token)
    user_to_apps, app_to_users = fetch_workspace_graph(creds)

    app_data = app_to_users.get(client_id)
    if not app_data:
        return HTMLResponse("<h1>App Not Found</h1>")

    app_name = app_data["displayText"]
    users = app_data["users"]

    service = build("admin", "directory_v1", credentials=creds)

    # Build list of (email, days, status)
    rows = []
    for email in users:
        record = service.users().get(userKey=email).execute()
        last_login = record.get("lastLoginTime")
        days = days_since(last_login)
        status = activity_status(days)
        rows.append((email, days, status))

    # Sort by last login: most active → least active
    rows.sort(key=lambda x: x[1])

    html = f"<h1>{app_name}</h1><h2>Users</h2><ul>"
    for email, days, status in rows:
        html += f"<li>{status} — <a href='/users/{email}'>{email}</a> ({days} days ago)</li>"

    html += "</ul>"
    html += "<br><a href='/apps'>← Back to Apps</a>"

    return HTMLResponse(html)