# AutoCare Garage — Step 2

## Customer & Vehicle Management

This package continues from **Step 1B — Backend Architecture** and adds a complete customer/vehicle management layer.

### Added
- Customer search by name, phone, or email.
- Add customer with phone, email, address, and notes.
- Edit customer details.
- Customer profile dashboard with vehicle/booking/job counts.
- Add multiple vehicles per customer.
- Vehicle fields: registration, brand, model, year, fuel, color, VIN, notes.
- Edit vehicle details.
- Safe vehicle deletion when there is no service history.
- Safe customer deletion when there is no service history.
- Protection against assigning a vehicle to the wrong customer through the existing database foreign keys.
- Registration and VIN normalization to uppercase.
- Validation for vehicle year and required model.
- Responsive management UI and search bar.
- CSRF protection remains enabled for all POST actions.

### Important
- This is still a **fresh-start database project**. No previous customer, vehicle, booking, job, estimate, invoice, or payment records are imported.
- Do not run `migrate_legacy.py` if you want to keep the fresh database.
- Step 2 includes the database schema update for unique VIN values.

## Run

1. Extract the ZIP.
2. Open a terminal in the project folder.
3. Install dependencies:
   `pip install -r requirements.txt`
4. Set a strong admin password using environment variables, for example:
   - `AUTOCARE_ADMIN_USER=admin`
   - `AUTOCARE_ADMIN_PASSWORD=change-this-password`
5. Start:
   `python run.py`

The application will initialize the fresh database and seed the service master data/admin account when required.

## Testing note

Python syntax/compile checks and SQLite schema checks were performed in the build environment. A full live Flask browser/server integration test was not performed because Flask was unavailable in that build environment.
