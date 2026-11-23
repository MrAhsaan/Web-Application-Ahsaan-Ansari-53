# AutoCare Garage — Step 7: Admin Dashboard & Reports

Step 7 builds a management dashboard and reporting layer on top of Step 6.

## Added
- Expanded admin dashboard KPIs: customers, vehicles, bookings, open jobs, revenue, today's collection, outstanding balance.
- Booking status summary and payment-method summary.
- Top services by job-item revenue.
- Dedicated `/admin/reports` analytics page.
- Report periods: 7, 30, 90, and 365 days.
- Daily booking and collection table.
- Job status summary.
- Technician workload and closed-job count.
- Top services with quantity and revenue.
- Outstanding invoice report.
- Payment CSV export for admin/manager roles.
- Reports navigation and dashboard shortcut.

## Fresh database policy
No previous transactional records are imported. Existing Step 6 data is preserved when upgrading in-place, but for a fresh deployment use the fresh database supplied by the project and let the application initialize it.

## Important
Live Flask execution was not performed in the build container because Flask is not installed there. Python syntax/compile checks and archive integrity checks were performed.
