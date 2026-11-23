# Review summary and known limitations

## Fixes in this review

- Explicitly points Flask to the root `templates/` and `static/` directories (preserved from the working version).
- Adds `/health` readiness check that verifies the database can answer a query.
- Creates the parent directory for a configured SQLite database path, enabling a mounted persistent data directory.
- Requires an explicitly configured `AUTOCARE_SECRET` in production and forces secure session cookies in production.
- Refuses to bootstrap the first production administrator with an unreported generated password.
- Applies role checks to customer/vehicle management, job-card management, billing, payment views, and reports.
- Validates the public booking contact preference before writing to the constrained database column.
- Adds a production WSGI entry point, optional Gunicorn requirements, and deployment guidance.
- Adds static regression checks for these changes.

## Important: not yet a fully audited commercial deployment

The available environment used for this review had no Flask package installed and could not reach the package index. Therefore, live Flask route tests and browser workflows could not be run here. The existing 10 tests were mostly source/configuration checks; 5 additional regression checks were added, but they are also static checks. The application must still be installed and tested on the target host before real users rely on it.

Before public launch, the following work is still recommended:

1. Add a staff administration UI for creating/deactivating staff accounts, changing roles, and resetting passwords. Roles are enforced on routes, but account-management screens are not included.
2. Add login throttling/rate limiting and a documented password-reset process.
3. Add integration tests using Flask's test client for login, role permissions, CSRF, booking creation, booking conversion, invoice creation, partial/full payment, PDF export, and reports.
4. Exercise all monetary calculations and transaction rollback paths with realistic cases.
5. Configure automated backups and perform a restore test.
6. Use PostgreSQL if multiple application instances or high concurrent booking/payment traffic are expected. SQLite remains the default.
7. Configure HTTPS, persistent storage, monitoring, and secrets in the selected hosting provider.

Do not accept real customer or payment data until these acceptance checks have been completed on the deployed environment.

## Razorpay home-visit advance payment update (2026-10-16)

- Added a fixed home-visit charge per booking, configurable with `AUTOCARE_HOME_VISIT_CHARGE` (default ₹299).
- Added server-created Razorpay Orders in INR, a tokenized public payment link, Razorpay Checkout, checkout signature validation, and server-side payment fetch verification requiring `captured` status, matching order ID, currency, and exact amount.
- Added signed `payment.captured` and `payment.failed` webhook handling using the raw request body and `X-Razorpay-Signature`; the webhook route is exempted from form CSRF only because the HMAC signature is validated.
- Added persistent `home_visit_payments` records and additive booking schema fields. Existing records are preserved; take a database backup before deployment.
- Dispatch requires a verified paid visit charge and an active technician. Dispatch creates or updates a job card and assigns the technician so inspection findings can be recorded.
- Added mocked tests for payment-before-confirmation, signed/invalid webhooks, amount mismatch, and dispatch gating/assignment.
- Validation performed here: Python syntax compilation and fresh SQLite schema/foreign-key checks passed. Full pytest/live Flask and Razorpay provider tests could not be run in this environment because Flask/Razorpay dependencies could not be downloaded. Run `python -m pip install -r requirements.txt` then `python -m pytest -q` locally, using Razorpay Test Mode before any live deployment.
- No real Razorpay payment has been made or verified in this build environment. Configure API keys, a webhook secret, and a public HTTPS webhook endpoint in Razorpay Test Mode before testing end-to-end.
