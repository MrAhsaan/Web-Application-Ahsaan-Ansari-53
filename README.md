# AutoCare Garage PRO — Full Workshop Management System

## Included
- Customer-facing responsive garage website
- Admin login
- Customer management
- Vehicle management
- Appointment booking
- Booking status workflow
- Job cards
- Technician, complaint, diagnosis, work done and cost tracking
- Invoice creation
- Discount and tax
- Payment recording
- Payment status: Unpaid / Partially Paid / Paid
- PDF invoice generation
- Dashboard with customers, vehicles, job cards and collected revenue
- SQLite database

## Run on Windows / VS Code

**Open the extracted project root** in VS Code — the same folder that contains `run.py`, `config.py`, `app`, `templates`, and `static`. Do not open only the `app` folder. The templates and CSS/JS folders intentionally live at the project root, and Flask is configured to find them there.

In VS Code, choose **Terminal → New Terminal** and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

Open:
- Website: http://127.0.0.1:5000
- Admin: http://127.0.0.1:5000/login
- Dashboard: http://127.0.0.1:5000/admin


### First-run credentials in PowerShell

Before the first `python run.py`, set your own local administrator credentials in the same terminal:

```powershell
$env:AUTOCARE_ADMIN_USER = "admin"
$env:AUTOCARE_ADMIN_PASSWORD = "Choose-A-Strong-Password-Here"
$env:AUTOCARE_SECRET = "Use-A-Long-Random-Secret-Here"
```

Then visit `http://127.0.0.1:5000`. Keep the terminal open while using the application and press `Ctrl+C` to stop it. These environment variables only bootstrap the first administrator; changing them later does not reset an existing account.

## First-run administrator account

The app creates the first administrator in the `users` table when the database has no users.
For a predictable local login, set these environment variables **before the first run**:

- `AUTOCARE_ADMIN_USER` (example: `admin`)
- `AUTOCARE_ADMIN_PASSWORD` (choose your own strong password)
- `AUTOCARE_SECRET` (use a long random secret)

If `AUTOCARE_ADMIN_PASSWORD` is not set, the app generates a random password for the first admin; it is not `admin123`, and the generated value is not displayed. Set the variables first to avoid losing access. These credentials are only used when the database has no users; changing the environment later does not reset an existing account.

Never use a weak/demo password on a public deployment.

## Database
SQLite is used so the project works immediately without installing MySQL.
For a production deployment, migrate to MySQL/PostgreSQL.

## PDF
Invoices are generated with ReportLab.

## Production checklist
- Add HTTPS
- Use a strong admin password and secret
- Add CSRF protection
- Add an admin UI for managing staff accounts and roles
- Validate/normalize phone numbers and money server-side
- Add backups
- Use PostgreSQL/MySQL
- Add secure file/image uploads if gallery is added
- Add real payment gateway only after business/legal setup


## Step 1 Architecture Upgrade

The project now uses a Flask application factory, Blueprints, a dedicated database module, configuration, and a normalized core schema. The original frontend templates are retained.

Run with `python run.py`. The database is initialized automatically.

**Important:** If you already have an old `autocare.db`, back it up before testing the new architecture. This Step 1 package deliberately avoids destructive automatic migration.

## Fresh Database

This version intentionally starts with a **new empty database**.
Previous records are not imported.

`autocare.db` is included as the fresh database. The `services` table contains
the default AutoCare services. All transactional tables start empty.


## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production environment variables, Gunicorn startup, persistent database storage, health checks, backups, and pre-launch acceptance testing. Production startup requires an explicitly configured `AUTOCARE_SECRET` and an explicit initial admin password if the database has no users.

## Customer booking notifications (Email + SMS + WhatsApp)

When an authorized staff member changes a booking's status, AutoCare saves the new status first, then attempts configured notifications. Provider failures are logged and do not undo the booking update. Re-saving the same status does not send another notification. Admins and managers can view the latest attempts at **Notification Logs**.

A log status of **Submitted** means the SMTP/Twilio provider accepted the request; it does **not** guarantee the message reached the customer's inbox or device. This version does not include delivery-receipt webhooks. Failed/skipped attempts show a reason in Notification Logs.

### Email setup (SMTP)

Configure these environment variables in the same terminal for local testing, or in the hosting provider's secret settings in production:

- `AUTOCARE_NOTIFY_EMAIL=1`
- `AUTOCARE_SMTP_HOST` and `AUTOCARE_SMTP_PORT` (usually `587` with STARTTLS)
- `AUTOCARE_SMTP_USERNAME` and `AUTOCARE_SMTP_PASSWORD` (if your SMTP provider requires login)
- `AUTOCARE_SMTP_FROM` (verified sender address)
- `AUTOCARE_SMTP_USE_TLS=1`

Example PowerShell (use real provider values; never commit them):

```powershell
$env:AUTOCARE_NOTIFY_EMAIL = "1"
$env:AUTOCARE_SMTP_HOST = "smtp.your-provider.example"
$env:AUTOCARE_SMTP_PORT = "587"
$env:AUTOCARE_SMTP_USERNAME = "your-smtp-username"
$env:AUTOCARE_SMTP_PASSWORD = "your-smtp-password"
$env:AUTOCARE_SMTP_FROM = "verified-sender@your-domain.example"
$env:AUTOCARE_SMTP_USE_TLS = "1"
```

### SMS and WhatsApp setup (Twilio)

Install the updated dependencies with `python -m pip install -r requirements.txt`. Configure:

- `AUTOCARE_TWILIO_ACCOUNT_SID`
- `AUTOCARE_TWILIO_AUTH_TOKEN`
- `AUTOCARE_TWILIO_SMS_FROM` (a Twilio SMS-capable sender)
- `AUTOCARE_TWILIO_WHATSAPP_FROM` (a Twilio WhatsApp sender, for example the sandbox sender while testing)

Customer phone numbers must be in E.164 format, for example `+919876543210`. For WhatsApp, the booking form includes an explicit opt-in checkbox; WhatsApp notifications are skipped unless the customer opted in for that booking. For Twilio WhatsApp sandbox testing, the recipient must first join the sandbox. Production WhatsApp messaging may require an approved sender and approved templates, depending on the account and message rules. SMS and WhatsApp usage may incur charges.

Channels are independently configured. Missing credentials, missing contact details, invalid phone formats, and missing WhatsApp consent are recorded as **Skipped** instead of pretending the message was delivered. Provider/network errors are recorded as **Failed**.

### Local testing without sending real messages

Automated tests mock SMTP/Twilio calls and never send real customer messages. To test manually, use your own verified test email and phone numbers first. Check **Notification Logs** after changing a booking status. Do not paste provider secrets into source files or screenshots.

## Tests

After installing `requirements.txt`, run the automated test suite with:

```powershell
python -m pytest -q
```

Notification tests mock SMTP/Twilio providers; they do not send real messages.


## Home-visit advance payment (Razorpay)

AutoCare supports a fixed home-visit fee paid in advance through Razorpay Checkout. Admins/managers set the fee from **Bookings**. Customers receive a payment URL, and staff dispatch is blocked until the server verifies the captured payment. The charge is kept separate from repair costs.

Configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, and `AUTOCARE_HOME_VISIT_CHARGE`; see `DEPLOYMENT.md` for the complete Test Mode setup and webhook instructions. Start with Test Mode keys only. Never treat a browser success callback or payment screenshot as payment proof.

Run tests with `python -m pytest -q`.
