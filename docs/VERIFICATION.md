# Verification — 28 October 2026

This is a working native desktop release, version 0.1.0, with persistent local records. This report distinguishes automated workflow checks from operating-system and physical-device checks. No pre-existing clinic data was read, migrated or changed. Synthetic and fictional profiles were used throughout.

## Environment and foundation

Ubuntu 24.04.4 LTS amd64; Python 3.12.3; Qt/PySide6 6.8.3. Intel Core i5-6200U at 2.30 GHz, 4 logical CPUs, 7.6 GiB available physical RAM, Micron MTFDDAV256TBN SSD. The development desktop was under normal background load; these are not controlled laboratory measurements.

The initial milestone was built and packaged before replacing the minimal UI with clinic workflows. The packaged foundation wrote a SQLite launch counter and read counts 1, 2 and 3 on successive executions. The third run used the extracted `.deb` payload inside `unshare -Urn`, with no network interface enabled. `docs/foundation-main.py.txt` records that minimal entrypoint. The full app uses the same direct SQLite approach, not the counter UI.

The final `.deb` is inspected with `dpkg-deb`, extracted into a clean staging directory, and its exact executable is run with networking disabled. There is no development server in the application architecture. Other unrelated programs on the host were not stopped; the isolated app cannot reach their TCP listeners. APT’s simulated install resolved the package successfully without additional dependencies on this host (`docs/package-install-simulation.txt`). The desktop launcher validates with a non-fatal category suggestion. An actual privileged installation with Ubuntu's package manager has **not** been performed because passwordless sudo is unavailable. Thus archive installation layout, launcher metadata, runtime loading and payload workflows are tested; package-manager integration on a clean Ubuntu installation remains a deployment check.

## Automated checks

The final pytest run passed **23 tests**. The suite covers:

- Exact AFN parsing/rendering, invalid inputs and large amounts beyond binary floating-point precision.
- Password salts, verification and minimum length; Afghan and international phone normalization.
- Exact permanent/primary FDI sets and patient-facing orientation.
- Solar Hijri/Gregorian round trips for every day from 1900 through 2100, a known Nowruz date, Dari digits and an invalid leap day.
- Patient → visit → completed treatment → discounted invoice → partial payment → refund → correction/void and reissue, including failed-payment rollback and duplicate active billing prevention.
- Purchase item/stock transactions, insufficient stock, batch accounting, duplicate treatment/material deduction prevention, and multiple materials per treatment.
- Appointment overlap boundaries and statuses; archived/active search; foreign keys, migration version and restart persistence.
- Administrator/receptionist write permissions and hiding clinical pages from reception.
- Reports reconciling invoices, net payments, expenses, supplier and laboratory payment ledgers.
- Complete backup into a fresh profile with patient/clinic attachments, account, settings, invoices and payment totals; checksum damage, unsafe archive paths and interrupted-restore recovery.
- Actual Qt form interactions for registration, visit, treatment, invoice and payment, PDF output, and printing leaving payment totals unchanged.
- Every navigation page in both languages and light/dark themes.
- Worker-thread image import/thumbnail generation, backup and UI restore, including restored-account unlock; worker-thread PDF export.

The packaged acceptance runner independently drives the real first-account and daily-workflow dialogs, renders every page in both languages/themes, saves A4 PDFs and four actual application screenshots, then restores its complete backup into a fresh profile and verifies the records, totals, attachments, account and settings. The normal clinic profile is never opened by that runner. Its JSON results are in `docs/packaged-acceptance.json`. A network syscall trace also recorded zero IPv4/IPv6 socket creations, zero bind calls and zero listen calls (`docs/network-check.json`).

## Rendering and printing

Actual English/Dari and light/dark application screenshots are in `screenshots/`, captured from the built executable at 1366×768. A source acceptance run also completed at 125% Qt display scaling. This does not replace testing the clinic's display/printer hardware. Windows DPI behavior remains untested.

Dari A4 PDF output was rendered to a PNG and visually inspected for joined glyphs, text direction, patient identity, line items and readable values. `pdffonts` confirms that fonts are embedded. Bundled regular/bold Noto Sans, Noto Sans Arabic and DejaVu fonts supply Latin/Dari glyphs. Fictional A4 and 80 mm PDF examples are in `docs/examples/`. A4 and compact layouts are implemented; no physical printer or thermal printer was available, so paper feed, margins, driver settings and actual output have not been verified. Native OS printer/file-picker chrome may follow the operating-system language; application labels and document content use the selected language.

## Measurements

`docs/benchmark.json` records 100 warm searches per query on 10,000 synthetic patients. Name-prefix median: 9.136 ms; phone-prefix median: 6.832 ms; patient-number median: 5.003 ms; no-match median: 5.123 ms. Maximum observed: 35.793 ms. This measures database/service queries, not human input or every possible dataset distribution. Global search also has a deliberate 180 ms input debounce. Patient lists page at 100 rows.

`docs/startup.json` and `docs/startup-xcb.json` record five external process-to-first-account-screen trials on fresh profiles, including interpreter and Qt loading, with network isolation. Final X11 trials: median 1.253 seconds, range 1.081–1.381 seconds; approximately 88 MiB resident memory at that screen. The OS cache was warm after building; cold boot and larger real attachments were not benchmarked. The packaged acceptance JSON's internal timing starts after imports and includes its automated account creation; it must not be mistaken for full process startup.

File copying/hashing, thumbnail generation, backup validation/archive/replacement and PDF export use worker threads with progress feedback. Very large clinical histories, huge attachment libraries and long print-preview documents have not been stress-tested. Report tables and charts contain saved record values; there are no decorative analytics or invented counts.

## Boundaries and remaining verification

- **Windows:** native build spec, PowerShell script, Inno Setup installer and Windows CI configuration prepared; no Windows executable/installer built or tested here. The workflow has not been pushed or run.
- **Clinic review:** Afghan Dari terminology requires a Dari-speaking clinic user's review. No clinician has signed off the dental workflow or receipt wording. Tooth surfaces are deliberately not implemented; the chart records teeth, conditions and treatment notes.
- **Physical devices:** no physical printer, thermal printer or USB-removal/failure test. Local folder backup/restore and failure validation are automated. A mounted USB folder uses the same file path mechanism.
- **Installation:** extracted Debian payload tested; privileged package-manager installation, uninstall/reinstall and a clean-VM deployment still require verification. Records are architecturally separate from program files and SQLite restart/migrations are tested.
- **Accounts/data:** local access roles and salted scrypt hashes; the database, images and archives are not encrypted. This is accurately disclosed in the app and guide. There is no online recovery, shared password or remote service.
- **Scheduled backups:** run only with the app open and an administrator signed in. They cannot protect records while the program is closed. Retention is applied only after a successful complete archive.
- **Stock/plans:** stock quantities are whole numbers of the chosen unit. A material can be deducted once per linked treatment; an explicit adjustment with a reason handles additional later use. Planned treatments across visits form the ongoing plan; there is no separate named-plan object.
- **Scope:** no sync, cloud accounts, SMS, automated diagnosis, automatic medication/dose recommendations, mobile client or encrypted database. None is represented as implemented.
