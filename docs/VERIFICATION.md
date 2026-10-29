# Workflow verification — version 0.3.0, 29 October 2026

The app is Python 3.12.3 / Qt-PySide6 6.8.3 / embedded SQLite on Ubuntu 24.04 amd64. This repair keeps that architecture. No server, online account or network service is required. Implementation and verification were completed locally. The user subsequently authorized pushing the source update to `soawarden-droid/Dental_clinic`. No clinic database or private backup is included.

## Defects and repair

The pre-implementation reproduction checklist is `REPAIR-CHECKLIST.md`. The highest-impact gaps were missing standalone consultation fees, a poorly explained separation between saved planned/completed work and issued bills, absent invoice payment statuses, no pre-billing edit route, no retry-safe payment identity, and no complete account statement. Reception also could not register a basic visit. SQLite's integer column affinity did not by itself reject fractional monetary values supplied directly to the service. Forms closed before persistence errors could be corrected.

`finance.py` now owns standalone draft consultation/procedure/other charges, completed-treatment billing, immutable invoice line snapshots, dated payments/refunds, audited void/reissue and the chronological patient statement. Every balance uses the `invoice_balances` view: valid finalized invoice lines minus discounts minus net payments. Neither drafts nor planned treatments invent debt. Billed and collected amounts are distinct metrics. No independently editable patient balance is stored.

Every financial action obtains a write transaction before reading the balance. Payment forms use a stable request key; retries return the original receipt, conflicting key reuse is rejected, and concurrent overpayments are rejected. UI Save/actions disable re-entry. Validation or persistence failure leaves the form and values open for correction. New amounts must be exact integer minor units, with database checks as well as service validation.

Draft fees and unbilled treatments can be edited. Finalized invoices, lines and payments cannot be silently overwritten/deleted or have more items appended. An administrator refunds received money with a reason, voids with a reason, edits the draft and reissues. The statement retains original charges, discounts, receipts, refunds and a separate void reversal, so running balances reflect the correction sequence. Existing legacy voids did not record a void timestamp; their display order uses the last recorded invoice/payment date, without claiming an exact historical time.

The patient workspace now emphasizes balance, Add charge, Record payment, saved unbilled drafts and the account timeline. Invoice states are unpaid, partial, paid or void. Later payments explicitly select the original bill, including from a newer visit. The dashboard shows distinct patients seen today, net finalized bills issued today, today's receipts minus refunds, total outstanding, appointments, recent visits/payments and stock warnings. The selected chart period is labelled. Empty charts and reduced motion remain supported.

## Data preservation

The user confirmed that the current profile contains test records. Complete private local backups were made before changes under `FaramarzRepairBackups` beside the normal profile. An isolated copy of the actual existing profile was upgraded and compared column-for-column across patients, visits, treatments, invoices/items, payments, attachments, users and settings: all original values remained unchanged. Integrity and foreign keys passed. No legacy negative/fractional balance anomalies were found in that copy. The live profile was not used as a development/test database.

Schema migration 5 adds fee records, payment request keys, timeline timestamps, finalized-bill guards and the balance view. Existing IDs, financial entries, clinical information, password hashes and attachment links remain intact. Every existing-profile upgrade first makes a complete backup; migrations remain transactional. A regression deliberately interrupts a migration and verifies rollback, the old version, records and the safety backup.

## Automated coverage

`test-results.txt` records the final full pytest result. The baseline was 32 passing tests; the repaired suite has 47 tests, including:

- Name/phone-only patients, NULL optional values, Afghan phone formats, duplicate warnings, reopen/edit/PDF and legacy missing values.
- AFN 500 consultation + AFN 2,000 treatment → unpaid AFN 2,500 → AFN 1,000 receipt → restart → later visit and AFN 1,500 receipt → paid/zero balance. Both service and real receptionist Qt dialogs are exercised.
- Statement lists both charges and both receipts; dashboard/report billed and collected figures reconcile. Date scopes distinguish money on older bills from bills issued today, and statements preserve opening balances.
- Same-key retries, conflicting retries, re-entrant Save/receipt actions and concurrent payment attempts; invalid input leaves no partial bill/payment.
- Draft edits, refunds, void/reissue, append/edit/delete guards and patient financial-history deletion protection.
- Existing migrations, SQLite restart persistence, exact dates/calendars and FDI tooth sets.
- Stock/purchase transactions, insufficient/duplicate usage, multiple materials, supplier/lab ledgers, expenses and reports. Stock quantities and monetary service inputs are checked explicitly.
- Complete checksummed backups and isolated restoration; corrupt/unsafe archives and interrupted restore handling.
- Profile/patient image import, replace/remove/reopen, retained originals and shared references; attachment batches commit together.
- All screens in English/Dari and light/dark, reception clinical restrictions, worker operations and PDF export.
- Explicit Forgot password recovery from the real login screen, new-password login, complete pre-reset backup and audit. There is no hardcoded master password.

## Packaged verification and artifacts

The exact `dist/faramarz-dental_0.3.0_amd64.deb` payload is tested in a fresh extraction, with networking disabled. `packaged-acceptance.json` records real first-account/forms, fees, treatment, invoices, installments, PDF/statement and backup restoration. A separate process reopened the acceptance profile and preserved the paid invoice and both receipts (`process-restart.json`). The exact Debian executable also upgraded an isolated copy of the existing clinic profile offline without changing original values. A second run uses 125% Qt scaling; `packaged-acceptance-scaled.json` and `network-check.json` record that run and network syscall counts. Build checksums and executable identity are in `BUILD_MANIFEST.json`.

Actual packaged screenshots under `screenshots/` include dashboard summaries and charts, minimal registration, patient timeline, billing and image settings in English/Dari and light/dark. Long pages scroll. A 1000×650 logical window was also exercised at 125% scaling across every page and patient tab, with no forced widening or action errors. A Dari status-badge clipping issue was repaired during visual review. PDF output is rendered for review and bundled fonts are checked with `pdffonts`; fictional examples are under `examples/`. Physical printers remain untested.

The Debian archive is suitable for Ubuntu 24.04 amd64. APT's simulated upgrade is recorded. Passwordless sudo is unavailable, so system-wide APT installation of 0.3.0 is not claimed. The supported per-user installer copies the bundle while preserving symlinks, switches the current version atomically and refreshes the Applications/command shortcut. It never opens or resets records. An already open older window must be closed and reopened; old application files remain available. The old system package can still be replaced through APT later.

Five fresh-profile packaged X11 startup trials had a 1.299-second median (`startup-xcb.json`), with warm OS caches. Earlier offscreen/search measurements are historical and are not new 0.3.0 benchmarks.

## Feature and platform boundaries

- Reception can create non-clinical visits, draft fees, invoices and receipts. Medical notes, treatment editing, refunds, voids, reports and administrator settings retain their role restrictions.
- Multiple bills are settled separately; there is no overpayment/credit-account workflow. Recording a procedure as both a standalone fee and a completed treatment would intentionally create two different charge sources; the guide explains choosing one route per procedure.
- No doctor compensation/payroll calculation is implemented. Patient consultation fees, bill totals and received cash are separate from payroll.
- Windows PyInstaller/Inno Setup 0.3.0 configuration and a Windows 2022 CI workflow are prepared. The workflow parses as YAML and includes tests, packaged full financial acceptance and screenshots. No Windows toolchain is available here, so no Windows executable, installer, installation or DPI result is claimed. Run `powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1` on Windows 10/11 x64, then exercise the installed app and upgrade.
- Local owner recovery is explicit on the login screen or via `--recover-password`, uses the normal exclusive profile lock, requires a new password and ownership confirmation, and backs up/audits the change. SQLite and backups are not encrypted; protect the OS account and disks.
- Dari terminology, the clinic's actual hardware, physical/thermal printers, USB removal/failure, clean-VM package installation and large attachment/history stress tests still need on-site review. Automatic backups run while the app is open and an administrator is signed in.
