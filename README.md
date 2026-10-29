# Faramarz Dental Clinic

A native offline dental clinic desktop application for Dr. Farshad Faramarz, Khair Khana, District 11, Kabul. English and Afghan Dari, AFN, adult/primary FDI charts, local SQLite, and local accounts. The older `../faramarz-clinic` project is untouched.

## Install and use

Ubuntu **24.04 amd64** is the build target. Open `dist/faramarz-dental_0.3.0_amd64.deb` with Ubuntu's package installer and install it, then launch **Faramarz Dental Clinic** from Applications. The package declares system runtime libraries. Python, Qt developer tools, Node, Flutter, a server, or an internet account are not needed to run the installed application. The application itself has no network dependency; OS dependencies should already be present or be supplied via Ubuntu packages for an entirely offline installation.

The first launch asks you to create your own local administrator. There are no shared credentials and no sample patients in the normal profile. Read the in-app Help → User guide, [English guide](docs/USER_GUIDE.md), or [Dari guide](docs/USER_GUIDE.fa_AF.md). Keep complete backups on a separate drive.

For package installation from a developer terminal:

```bash
sudo apt install ./dist/faramarz-dental_0.3.0_amd64.deb
```

Records are in the user's application data directory, separate from `/opt/faramarz-dental`. Package updates and removal do not delete those records. Local login restricts actions in the app; SQLite, attachments and backup archives are **not encrypted**. OS account protection and disk encryption provide protection at rest.

## Daily fees and payments

Open the patient → New visit → Add charge (consultation 500 AFN) → Add charge (treatment 2,000 AFN, or complete the doctor's treatment) → Issue invoice. The unpaid total is 2,500 AFN. Record payment 1,000 AFN: remaining 1,500 AFN. Reopen after a restart/later visit and record 1,500 AFN against the same invoice: paid, remaining zero. Statement lists both charges and both receipts. Saving a draft or issuing an invoice never invents a payment.

Draft fees and unbilled treatments can be edited; finalized financial records use audited refund/void/reissue. A unique request key and a write transaction prevent duplicate retries or concurrent overpayment. Invoice totals, patient balances, reports and dashboard read one balance view. The login screen has explicit local-owner password recovery with a complete backup and audit entry.

## What works

- Name and phone are the only required patient fields; optional information stays NULL. Shared family numbers are allowed after a duplicate warning.
- Ivory/rose and dark plum themes, English/Dari typography, patient workspace tabs and a dashboard with real collections, treatment and appointment charts.
- Image Add/Replace/Remove/Preview/Restore controls, background opacity and reduced motion. Original files remain untouched.
- Patient demographics, clinical alerts, archive/restore, photos and managed files.
- Visits and follow-ups, exact FDI adult/primary chart, planned/completed treatment records and editable procedure catalogue.
- Itemized invoices, discounts, partial payments, refunds, void/reissue corrections, receipts, A4/80 mm PDF and print preview.
- Agenda/day/seven-day reception views, walk-ins, appointment conflicts and waiting status.
- Structured purchase items, suppliers, later supplier payments, material quantities/batches/expiry, stock movements and confirmed treatment usage.
- Expenses, lab cases and dated lab payments, doctor-written prescriptions and aftercare.
- Editable clinic/doctor profile and documents; period reports, comparisons and CSV/PDF export.
- Consistent SQLite backups with attachments, account/settings snapshot, manifest/checksums, safety backup before restore, daily backups while open, and retention.
- Administrator/receptionist permissions, scrypt password hashing, local lock, audit entries, keyboard shortcuts, unsaved-form warnings, both themes and RTL.

Read [verification and limitations](docs/VERIFICATION.md) for evidence and boundaries. Windows installer configuration is provided; a Windows release is not claimed as tested on Ubuntu. No mobile, cloud sync, online reminders, automatic clinical advice or database encryption is included.

## Architecture decision

Flutter was present, but Python 3.12 + Qt/PySide6 6.8.3 was selected for direct embedded SQLite, desktop text shaping/RTL, native printing, and a maintainable single-process application. This is a measured choice, not a claim that Qt is inherently fastest. PyInstaller bundles the runtime with replaceable shared Qt libraries. No web view, browser storage, HTTP listener or external database is used. All fonts and visual assets are bundled. Unused Qt PDF-reading, virtual keyboard, QML/Quick and VNC plugins are excluded from the release bundle. PDF generation uses Qt PrintSupport.

`clinic/service.py` contains transaction/permission boundaries and audit writes; `finance.py` owns draft charges, immutable bill snapshots, exact payments and the statement; `schema.py` has ordered database migrations; `domain.py` owns exact AFN parsing, FDI numbering, calendar conversion and password hashing; `backup.py` uses SQLite `Connection.backup()` and validates complete archives. The UI uses focused dialogs and a central patient page. File copy/hashing, thumbnail generation, and archive operations use worker threads. Clinic data is protected by an application-profile process lock. SQL parameters bind input; dynamic identifiers are restricted to internal allowlists. The SQL data model and domain code can be reused for a later desktop/mobile phase.

## Build Ubuntu

Verified host: Ubuntu 24.04, Python 3.12.3, amd64. A system Python with venv support, standard build utilities, and Qt's declared runtime libraries must be installed on the developer machine.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
scripts/build.sh
```

For a per-user Ubuntu update that refreshes stale launchers without sudo, run `python3 scripts/install-user.py dist/faramarz-dental`, then close and reopen the clinic app. This does not open records.

The script builds an on-directory executable plus a `.deb` with launcher, icon and system dependencies. `faramarz.spec` is the canonical Linux/Windows packaging specification. The dependency lock pins the complete resolved Python graph. Build on Ubuntu 24.04 to reproduce this target; do not assume that this binary supports older glibc releases.

## Verify without clinic data

```bash
# All data for this command is fictional and isolated. Output must be new/empty.
dist/faramarz-dental/faramarz-dental --verify /tmp/faramarz-acceptance
# On Linux, additionally disable the network for the entire process:
unshare -Urn dist/faramarz-dental/faramarz-dental --verify /tmp/faramarz-offline-acceptance
# Synthetic 10,000-patient search benchmark in a temporary database:
.venv/bin/python scripts/benchmark.py
# Optional fictional demo, always a separate application profile:
.venv/bin/python main.py --demo
```

`--verify` drives the real account, patient, visit, treatment, invoice and payment dialogs, checks NULL optional fields, writes PDFs/screenshots, renders all pages in both languages/themes, and restores a complete backup into a fresh profile. It never opens the normal application profile. `--smoke` only tests a SQLite settings write/read and short window launch; use a temporary `FARAMARZ_PROFILE` when running it. `FARAMARZ_PROFILE` is a developer/testing override, not part of the clinic's normal setup.

## Windows preparation

Use a Windows 10/11 x64 runner with Python 3.12.3 and Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```

The script installs the pinned graph, runs the tests, builds the native Windows executable, and compiles the per-user installer described by `scripts/windows.iss`. `.github/workflows/windows.yml` provides a manually triggered/tag-triggered Windows build and packaged smoke/capture checks. It has not been run from this workspace. Build separately on Windows; the Ubuntu executable cannot be converted into a tested Windows installer.

## Licenses

Project source is MIT. See [asset and dependency attribution](docs/ATTRIBUTION.md), bundled font notices and LGPL notices in `assets/`. Original clinic icon and code are included. Apexo's manual was inspiration only; no Apexo code or assets were copied. No doctor credentials, years of experience, phone number, or photographs were invented.
