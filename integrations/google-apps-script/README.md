# Contact relay (Google Apps Script)

The shop's contact form ends up in a Google Sheet that the team uses as a lightweight helpdesk.

```
Angular /contact ──POST /api/v1/system/contact──▶ FastAPI ──(stores feedback in PostgreSQL)
                                                    │
                                                    └─ background task: signed JSON ──▶ Apps Script Web App
                                                                                          ├─ append row to "Contacts" sheet
                                                                                          ├─ email the admins (reply-to = customer)
                                                                                          └─ auto-reply to the customer with a ticket id
```

| File | Role |
|---|---|
| `Code.gs` | `doPost` / `doGet` entry points, request parsing and validation |
| `Security.gs` | HMAC-SHA256 signature check, replay window, rate limit for unsigned posts |
| `Sheet.gs` | Ticket table: formatting, status dropdown, idempotent insert, formula-injection guard |
| `Mailer.gs` + `*.html` | Admin notification, customer auto-reply, daily digest (HtmlService templates) |
| `Triggers.gs` | `setup()`, daily digest trigger, `onEdit` that stamps *Resolved at*, `testSignedRequest()` |

## Why the request is signed

Apps Script web apps are public URLs and cannot read HTTP headers, so the backend proves
authenticity inside the body:

```
payload   = JSON string of the message
timestamp = unix seconds
signature = hex(HMAC_SHA256(SHARED_SECRET, timestamp + "." + payload))
```

The script rejects bad signatures and anything older than 5 minutes. A leaked web app URL
is therefore useless without the secret, and the URL is never shipped to the browser.
Retries from the backend are idempotent thanks to the `Backend ID` column.

## Setup

1. Create a Google Sheet, then **Extensions > Apps Script** (the script must be bound to the sheet).
2. Push the code:
   ```bash
   cd integrations/google-apps-script
   npm install
   npx clasp login
   cp .clasp.json.example .clasp.json   # paste the Script ID from Project Settings
   npx clasp push
   ```
3. **Project Settings > Script properties**:
   - `SHARED_SECRET`: `openssl rand -hex 32` (same value as `GAS_SHARED_SECRET` in the backend)
   - `ADMIN_EMAILS`: `support@example.com,owner@example.com`
   - optional: `SHOP_NAME`, `SHOP_URL`, `SHEET_NAME`, `ALLOW_UNSIGNED_FORM`
4. Run `setup` once from the editor and accept the permissions.
5. **Deploy > New deployment > Web app**, execute as *Me*, access *Anyone*.
   Put the `/exec` URL in `GAS_WEBHOOK_URL` of `deploy/.env`.
6. Run `testSignedRequest` from the editor: a row appears and two emails arrive.

To roll out a new version keep the same deployment (**Manage deployments > Edit > New version**)
so the URL stays the same. If the URL ever leaks, rotate `SHARED_SECRET`; if the secret leaks,
also create a new deployment and archive the old one.

## Limits

Consumer Gmail accounts can send ~100 emails/day from Apps Script (Workspace: 1,500).
The auto-reply is skipped when the remaining quota drops below 20 so that admin
notifications keep working.
