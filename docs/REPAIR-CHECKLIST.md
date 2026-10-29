# Workflow repair checklist — 29 October 2026

Pre-change complete clinic backup: private local `FaramarzRepairBackups` folder beside the clinic profile. No clinic records or backup archives belong in the repository.

| Priority | Reproduction in 0.2.0 | Root cause | Repair/verification |
|---|---|---|---|
| P0 | Save a planned treatment and look at the patient's balance | Planned/completed clinical records and issued charges are not explained; only a separate completed-treatment invoice contributes debt | Explicit draft charges, consultation fee, finalization and clear unbilled summary |
| P0 | Try to record a consultation fee as reception | No standalone fee model/action; visit creation requires clinical administrator | Non-clinical reception visits and draft charges; clinical details remain restricted |
| P0 | Retry a payment request or activate the action twice | No request key or UI in-flight protection; check-before-write transaction is deferred | Unique idempotency keys, write lock before validation, disabled/re-entrant action protection |
| P0 | Pass fractional minor units directly to the service | SQLite INTEGER affinity alone accepts REAL; no service integer check | Exact integer validation plus database checks on new financial writes |
| P1 | Save charges, pay in two installments and reopen profile | Fragmented history, no explicit unpaid/partial/paid status, no patient statement or easy later-payment action | One balance view, selected outstanding invoice, chronological account activity and statement |
| P1 | Correct an unbilled treatment price | No edit action, even before billing | Editable draft treatments/fees; finalized records use audited refund/void/reissue |
| P1 | Compare dashboard billed charges against receipts | Dashboard has collections but no billed metric | Separate billed/collected metrics with saved-record drilldowns and date scope |
| P1 | Lock/unlock after importing an attachment | Attachment worker commits records separately; saved UI paths must be audited | Verify all feature routes, transactional image registration and restart/restore |
| P1 | Forget local password | Only an ad-hoc recovery was available | Documented explicit local-owner recovery, backup, lock and audit; no master password |
| P1 | Launch system version after newer app changed schema | Old system package and newer user copy can coexist | Versioned user installer and launcher verification; clear compatible-version error |
| P2 | Trigger unknown validation error while using Dari | Error fallback hides actionable detail | Translated known errors plus original details for unexpected errors |

All listed repairs are implemented. Regression and packaged evidence, plus platform boundaries, are recorded in VERIFICATION.md. Source publication was subsequently authorized by the user; clinic databases and private backups remain excluded. Existing working inventory, appointment, profile, image, PDF and backup checks remain part of the suite.
