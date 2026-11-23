# AutoCare Garage — Step 4: Job Card Management

This package continues from Step 3 and adds the workshop Job Card workflow.

## Included
- Job Card list with search and status filters
- New Job Card creation from an existing booking or manually
- Customer/vehicle validation
- Technician assignment
- Complaint, diagnosis, work done, odometer and notes
- Service / part / labour / other line items
- Automatic line totals and job subtotal
- Edit Job Card and line items in one transaction
- Job Card status: Open, In Progress, Ready, Closed
- Booking status synchronization: active job -> In Progress, closed job -> Completed
- Job summary and vehicle details
- Existing invoice/payment integration retained
- CSRF and authentication retained

## Fresh database
No previous customer, vehicle, booking, job, estimate, invoice or payment records are imported.

## Run
1. Extract this ZIP.
2. Open a terminal in the extracted `autocare` folder.
3. Install dependencies: `pip install -r requirements.txt`
4. Set `AUTOCARE_ADMIN_USER` and `AUTOCARE_ADMIN_PASSWORD` for first startup if desired.
5. Run: `python run.py`
6. Open the local URL shown by Flask.

## Note
The package was syntax-checked and the SQLite schema was inspected in the build environment. A live Flask server integration test was not possible in the build environment because Flask was not installed there.
