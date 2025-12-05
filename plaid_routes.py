import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# -------------------------
# Plaid Client Setup
# -------------------------
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

# Configure Plaid environment
if PLAID_ENV == "sandbox":
    host = plaid.Environment.Sandbox
elif PLAID_ENV == "development":
    host = plaid.Environment.Development
else:
    host = plaid.Environment.Production

configuration = plaid.Configuration(
    host=host,
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
    }
)

api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)


# -------------------------
# Known SaaS Vendors (for classification)
# -------------------------
SAAS_VENDORS = [
    "slack", "notion", "figma", "zoom", "dropbox", "github", "gitlab",
    "atlassian", "jira", "confluence", "asana", "monday", "trello",
    "salesforce", "hubspot", "zendesk", "intercom", "freshdesk",
    "aws", "amazon web services", "google cloud", "gcp", "azure", "microsoft",
    "heroku", "vercel", "netlify", "cloudflare", "datadog", "new relic",
    "twilio", "sendgrid", "mailchimp", "stripe", "braintree",
    "quickbooks", "xero", "gusto", "rippling", "workday",
    "adobe", "canva", "miro", "loom", "calendly", "docusign",
    "openai", "anthropic", "cohere", "linear", "clickup",
    "1password", "lastpass", "okta", "auth0",
    "snowflake", "databricks", "tableau", "looker", "amplitude", "mixpanel",
    "airtable", "coda", "webflow", "squarespace", "shopify",
    "grammarly", "notion", "evernote", "todoist",
    "spotify", "netflix", "hulu", "disney", "hbo",
    "nytimes", "wsj", "bloomberg", "economist", "ft.com", "financial times",
    "reuters", "ap news", "washington post", "new yorker",
]


def is_saas_vendor(merchant_name: str) -> bool:
    """Check if a merchant name looks like a SaaS vendor."""
    if not merchant_name:
        return False
    name_lower = merchant_name.lower()
    return any(vendor in name_lower for vendor in SAAS_VENDORS)


def classify_transaction(txn) -> dict:
    """Classify a transaction and return enriched data."""
    merchant = txn.get("merchant_name") or txn.get("name", "Unknown")
    amount = txn.get("amount", 0)
    date = txn.get("date")
    category = txn.get("category", [])
    
    is_saas = is_saas_vendor(merchant)
    is_subscription = "Subscription" in category if category else False
    
    return {
        "merchant": merchant,
        "amount": amount,
        "date": str(date),
        "category": category,
        "is_saas": is_saas or is_subscription,
        "confidence": "high" if is_saas else ("medium" if is_subscription else "low")
    }


# -------------------------
# Routes
# -------------------------

@router.get("/spend")
def spend_home(request: Request):
    """Spend visibility home - shows connect button or transaction data."""
    plaid_token = request.session.get("plaid_access_token")
    
    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/spend'>Spend</a><a href='/'>Home</a></div>"
    
    if not plaid_token:
        html += """
        <div class='card'>
            <h1>💳 Spend Visibility</h1>
            <p>Connect your bank account to see SaaS spending across your organization.</p>
            <button onclick="connectBank()">Connect Bank Account</button>
        </div>
        
        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
        <script>
        async function connectBank() {
            const response = await fetch('/plaid/create-link-token');
            const data = await response.json();
            
            if (data.error) {
                alert('Error: ' + data.error);
                return;
            }
            
            const handler = Plaid.create({
                token: data.link_token,
                onSuccess: async (public_token, metadata) => {
                    await fetch('/plaid/exchange-token', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({public_token: public_token})
                    });
                    window.location.reload();
                },
                onExit: (err, metadata) => {
                    if (err) console.error(err);
                }
            });
            
            handler.open();
        }
        </script>
        """
    else:
        html += """
        <div class='card'>
            <h1>💳 Spend Visibility</h1>
            <p>✅ Bank connected. <a href='/spend/transactions'>View SaaS Transactions →</a></p>
            <p><a href='/plaid/disconnect'>Disconnect Bank</a></p>
        </div>
        """
    
    return HTMLResponse(html)


@router.get("/spend/transactions")
def spend_transactions(request: Request):
    """Show classified transactions."""
    plaid_token = request.session.get("plaid_access_token")
    
    if not plaid_token:
        return HTMLResponse("<script>window.location.href='/spend';</script>")
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=90)
    
    try:
        txn_request = TransactionsGetRequest(
            access_token=plaid_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(count=100)
        )
        response = client.transactions_get(txn_request)
        transactions = response.to_dict().get("transactions", [])
    except Exception as e:
        return HTMLResponse(f"<div class='card'><h1>Error</h1><p>{str(e)}</p></div>")
    
    classified = [classify_transaction(t) for t in transactions]
    saas_only = [t for t in classified if t["is_saas"]]
    
    total_saas_spend = sum(t["amount"] for t in saas_only if t["amount"] > 0)
    
    html = "<link rel='stylesheet' href='/static/style.css'>"
    html += "<div class='nav'><a href='/users'>Users</a><a href='/apps'>Apps</a><a href='/spend'>Spend</a><a href='/'>Home</a></div>"
    
    html += f"""
    <div class='card'>
        <h1>💳 SaaS Spend (Last 90 Days)</h1>
        <p style='font-size: 1.5rem;'><strong>Total SaaS Spend:</strong> ${total_saas_spend:,.2f}</p>
        <p>Found {len(saas_only)} SaaS transactions out of {len(transactions)} total.</p>
    </div>
    """
    
    html += "<div class='card'><h2>🟢 Identified SaaS Charges</h2>"
    html += "<table><tr><th>Vendor</th><th>Amount</th><th>Date</th><th>Confidence</th></tr>"
    
    for t in sorted(saas_only, key=lambda x: x["date"], reverse=True):
        conf_icon = "🟢" if t["confidence"] == "high" else "🟡"
        html += f"""
        <tr>
            <td>{t['merchant']}</td>
            <td>${t['amount']:,.2f}</td>
            <td>{t['date']}</td>
            <td>{conf_icon} {t['confidence']}</td>
        </tr>
        """
    
    html += "</table></div>"
    
    html += "<div class='card'><h2>📋 All Transactions</h2>"
    html += "<table><tr><th>Vendor</th><th>Amount</th><th>Date</th><th>SaaS?</th></tr>"
    
    for t in sorted(classified, key=lambda x: x["date"], reverse=True)[:50]:
        saas_icon = "✅" if t["is_saas"] else ""
        html += f"""
        <tr>
            <td>{t['merchant']}</td>
            <td>${t['amount']:,.2f}</td>
            <td>{t['date']}</td>
            <td>{saas_icon}</td>
        </tr>
        """
    
    html += "</table></div>"
    html += "<a href='/spend'>← Back to Spend</a>"
    
    return HTMLResponse(html)


@router.get("/plaid/create-link-token")
def create_link_token(request: Request):
    """Create a Plaid Link token for the frontend."""
    try:
        link_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="nicklpass-user"),
            client_name="Nicklpass",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en"
        )
        response = client.link_token_create(link_request)
        return JSONResponse({"link_token": response.link_token})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/plaid/exchange-token")
async def exchange_token(request: Request):
    """Exchange public token for access token and store in session."""
    try:
        body = await request.json()
        public_token = body.get("public_token")
        
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(exchange_request)
        
        request.session["plaid_access_token"] = response.access_token
        request.session["plaid_item_id"] = response.item_id
        
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/plaid/disconnect")
def disconnect_plaid(request: Request):
    """Remove Plaid connection from session."""
    request.session.pop("plaid_access_token", None)
    request.session.pop("plaid_item_id", None)
    return HTMLResponse("<script>window.location.href='/spend';</script>")


@router.get("/debug/plaid-status")
def debug_plaid_status(request: Request):
    """Check Plaid configuration status."""
    return {
        "client_id_set": bool(PLAID_CLIENT_ID),
        "secret_set": bool(PLAID_SECRET),
        "environment": PLAID_ENV,
        "session_has_token": bool(request.session.get("plaid_access_token"))
    }