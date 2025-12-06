import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # REQUIRED for personal connected apps:
    "https://www.googleapis.com/auth/user.data.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.security",
    "https://www.googleapis.com/auth/admin.reports.audit.readonly"
]

def get_flow():
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI")],
        }
    }

    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
    )


@router.get("/login")
def login():
    flow = get_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return RedirectResponse(authorization_url)


@router.get("/oauth/callback")
def oauth_callback(request: Request):
    flow = get_flow()
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials

    request.session["google_token"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    oauth_service = build("oauth2", "v2", credentials=creds)
    user_email = oauth_service.userinfo().get().execute().get("email")
    
    # Personal Gmail users → always connected apps path
    if user_email.endswith("@gmail.com"):
        return RedirectResponse("/connected-apps")
    
    # Try admin directory lookup
    try:
        admin_service = build("admin", "directory_v1", credentials=creds)
        record = admin_service.users().get(userKey=user_email).execute()
        is_admin = record.get("isAdmin", False)
    except Exception:
        is_admin = False

    if is_admin:
        return RedirectResponse("/users")
    else:
        return RedirectResponse("/connected-apps")