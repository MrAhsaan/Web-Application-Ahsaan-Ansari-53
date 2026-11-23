# AutoCare Garage deployment notes

## Before going public

- Use a managed host or Linux server with HTTPS enabled.
- Set `AUTOCARE_ENV=production`.
- Set `AUTOCARE_SECRET` to a unique, long random value. Do not use the example value.
- Set `AUTOCARE_ADMIN_USER` and `AUTOCARE_ADMIN_PASSWORD` before the first production startup. The password is only used when the database has no users.
- Set `AUTOCARE_DB` to a path on persistent storage. The parent directory is created automatically. Do not rely on an ephemeral container filesystem for the database.
- Keep secrets out of source control and logs. Do not expose Flask's development server or enable `AUTOCARE_DEBUG` in production.
- Configure TLS/HTTPS at the hosting platform or reverse proxy. Production sessions use secure cookies.
- Set up automated encrypted backups and test restoring one before accepting real business data.
- Use PostgreSQL instead of SQLite for multiple app instances or heavier concurrent workloads. This project currently uses SQLite.

## Linux/Gunicorn example

Install production requirements:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-production.txt
```

Set the environment variables in the hosting provider's secret/configuration panel, then run:

```bash
gunicorn --workers 2 --bind 0.0.0.0:${PORT:-8000} wsgi:app
```

The host should route HTTPS traffic to the service. Make sure the database path points to persistent storage.

## Health check

`GET /health` returns JSON with `status: ok` if the application can execute a simple database query. Configure the hosting platform to use this endpoint if supported.

## Fresh database policy

This project does not migrate previous customer, vehicle, booking, job, estimate, invoice, or payment records. It creates the schema, default service catalog, and first administrator account only. Back up any database before replacing or upgrading a deployed instance.

## Pre-launch acceptance checklist

- [ ] Create and test the initial administrator account.
- [ ] Verify login/logout, CSRF rejection, and staff-role access restrictions.
- [ ] Create a public booking and confirm it appears in the staff portal.
- [ ] Convert a booking to a job card, add labor/parts, create an estimate/invoice, record a partial payment, and verify the balance.
- [ ] Download an invoice PDF and export a report.
- [ ] Verify duplicate booking and invalid form handling.
- [ ] Confirm HTTPS, secure cookies, secrets, persistent storage, backups, and restore procedure.
- [ ] Test the site on mobile and desktop.

This checklist is not a claim that every item has already been live-tested. Run it against the actual deployment before inviting customers.

## Booking notification providers

Notification sending is optional until configured. SMTP credentials are required for email; Twilio credentials and channel senders are required for SMS/WhatsApp. See the **Customer booking notifications** section in `README.md` for exact environment variable names and local PowerShell examples.

- The booking status is committed before provider calls. Provider failures are logged and do not revert the booking status.
- The app sends only when the status actually changes; posting the existing status does not create a new notification attempt.
- WhatsApp requires the customer's explicit opt-in checkbox for that booking.
- The `submitted` log state means provider accepted the request, not confirmed delivery. Delivery receipts/webhooks are not implemented yet.
- Review the Notification Logs page after test updates and verify your providers' own delivery dashboards before public launch.


## Razorpay home-visit advance payment

1. Install the updated requirements with `python -m pip install -r requirements.txt`.
2. In the Razorpay Dashboard, use **Test Mode** and create API keys. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, and `AUTOCARE_HOME_VISIT_CHARGE` in the same environment as the app. Do not put live secrets in source code or commit `.env`.
3. In Razorpay Test Mode, create a webhook pointing to `https://YOUR-PUBLIC-HOST/webhooks/razorpay`, with the same webhook secret and the `payment.captured` event enabled. Razorpay cannot deliver webhooks to plain localhost without a secure public tunnel.
4. In Bookings, an admin/manager sets the fixed home-visit charge. AutoCare creates a Razorpay Order server-side and provides a public payment link. The customer pays through Razorpay Checkout.
5. The payment is marked paid only after the Checkout response signature is checked and the server fetch confirms the payment is `captured` for the expected order and amount, or a valid signed `payment.captured` webhook arrives. Browser redirects alone never mark payment paid.
6. Dispatch is blocked until `visit_payment_status='paid'`; the admin/manager must assign an active technician. The home-visit charge is separate from the repair estimate and invoice.
7. Verify in Test Mode first. Only switch to live keys after successful end-to-end testing, a public HTTPS URL, webhook delivery verification, and your Razorpay account's go-live checks.

Payment records are stored in `home_visit_payments`; booking summary fields are stored on `bookings`. Startup applies additive schema changes to existing databases and does not delete existing records. Back up your database before deploying schema updates.

**Important cancellation note:** cancelling a booking prevents further use of its payment link and blocks dispatch. If a payment was already captured before cancellation, staff must review it and initiate any required refund in the Razorpay Dashboard; this version does not automatically issue refunds.
