# AutoCare Step 9 — Security, Testing & Production Hardening

## Security improvements
- CSRF protection on every POST request using a per-session token and constant-time comparison.
- Secure session-cookie defaults: HttpOnly + SameSite=Lax; Secure is enabled automatically in production.
- Security response headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, and HSTS in production.
- Authentication validates active users from the database on every request.
- Logout is now POST-only and CSRF-protected.
- Login input length validation and safe local `next` redirect handling.
- Maximum request body size limited to 2 MB.
- Generic 500 error page prevents internal exception details from being shown to users; errors are logged server-side.
- Development server no longer runs with debug mode by default.
- Default admin password is no longer hard-coded; set AUTOCARE_ADMIN_PASSWORD explicitly for predictable credentials.

## Production environment
Set these environment variables before deployment:
- AUTOCARE_ENV=production
- AUTOCARE_SECRET=<long-random-secret>
- AUTOCARE_ADMIN_USER=<admin-username>
- AUTOCARE_ADMIN_PASSWORD=<strong-password>
- AUTOCARE_DB=<absolute-path-to-database>
- AUTOCARE_COOKIE_SECURE=1 (when HTTPS is enabled)

## Testing
Run:
```bash
pip install -r requirements.txt
pytest -q
```

The included tests cover configuration/security defaults, database constraints, and source-level safety checks. A full live Flask test suite requires the dependencies to be installed in the target environment.

## Important
This project intentionally remains a fresh-start database. `migrate_legacy.py` is not used.
