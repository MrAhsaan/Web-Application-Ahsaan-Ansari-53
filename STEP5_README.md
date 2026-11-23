# AutoCare Garage — Step 5: Estimate & Invoice System

This version builds on Step 4 and adds the billing workflow:

**Job Card → Estimate → Approval → Invoice → Payment → Balance**

## Added
- Billing dashboard for estimates and invoices
- Estimate creation from a Job Card
- Estimate line items (service, part, labour, other)
- Discount and tax amounts
- Estimate statuses: Draft, Sent, Approved, Rejected, Expired
- Approved estimate → invoice conversion
- Invoice numbering: `INV-YYYYMMDD-JOBID`
- Payment recording with Cash / UPI / Card / Bank Transfer / Other
- Overpayment protection
- Invoice PDF with items, totals and payment history
- Billing navigation
- Estimate and invoice links from Job Cards
- Role restrictions for billing mutations

## Fresh database
No previous transactional records are imported. If using the already-created Step 4 database, Step 5 adds only the `invoices.estimate_id` linkage needed for the new workflow.

## Important
The execution environment used to package this project does not have Flask installed, so a live Flask server integration test was not possible here. Python syntax compilation and ZIP integrity were checked.
