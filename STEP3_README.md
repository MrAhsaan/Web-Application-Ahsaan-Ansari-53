# AutoCare Garage — Step 3: Booking System

This checkpoint continues from Step 2 and implements the appointment workflow.

## Added
- Unique booking IDs such as `AC20260914001`
- Normalized customer → vehicle → service booking flow
- Fixed service IDs instead of storing service names in bookings
- Date validation (no past dates)
- Fixed selectable time slots
- Duplicate vehicle/date/time protection
- Preferred contact method: Phone, WhatsApp, Email
- Pickup and drop-service options
- Booking confirmation page with booking ID
- Admin booking management page
- Search by booking ID, customer, phone, registration or model
- Status filtering
- Booking status workflow: Pending, Confirmed, In Progress, Completed, Cancelled
- Role protection for booking management
- CSRF protection retained

## Fresh database policy
No previous customer, vehicle, booking, job, invoice or payment records are imported. The database remains a fresh-start database.

## Run
Set the admin credentials before first startup if desired, then run:

```bash
python run.py
```

Install dependencies with:

```bash
pip install -r requirements.txt
```

## Next
Step 4 will build the Job Card workflow around confirmed bookings and vehicles.
