# Verification — 29 October 2026

Version **0.2.0**, built on Ubuntu 24.04 amd64 with Python 3.12.3 and Qt/PySide6 6.8.3. All verification used isolated fictional profiles. The normal clinic profile was never opened or changed during development.

## Results

**32 tests passed** (`test-results.txt`). The suite covers exact AFN arithmetic, Afghan phone normalization, all FDI tooth numbers, Gregorian/Solar Hijri dates, roles, registration, billing/refunds/corrections, appointment conflicts, stock transactions, supplier/lab ledgers, reports, PDF output, image workers and complete backup/restoration.

New checks specifically prove:

- Name and phone alone save, reopen and edit; all omitted optional patient fields are SQL NULL. Real registration dialogs show inline errors and collapsed Additional information. PDF output has the patient's identity/phone and no literal `None`.
- Shared family phone numbers normalize consistently and produce a warning without preventing a confirmed registration.
- A synthetic version-2 database upgrades through transaction-safe migrations to version 4 without changing patient/visit/invoice IDs, attachments or payment balances. Legacy missing phones do not block unrelated section edits. Existing recorded ages are preserved.
- Dashboard collections equal payments minus refunds; outstanding balances equal active invoices minus payments. Treatment distribution excludes planned work. Empty charts show empty states, and reduced motion disables entry animations, including a simulated system preference.
- Upload → remove → reopen persists; replacement keeps original user files and unrelated qualification documents. Managed image copies remain while another image slot or setting references them. Real Qt image controls are exercised as well as service methods.
- Reception roles still hide clinical details; patient tabs and all navigation pages render in both languages and both themes.

## Exact Debian payload

`faramarz-dental_0.2.0_amd64.deb` was inspected and extracted to a fresh staging directory. Its exact executable passed the real first-account → minimal patient → visit → completed treatment → discounted invoice → partial payment → PDF workflow inside `unshare -Urn` with network access disabled. It then restored its complete backup into a fresh profile and verified accounts, patients, attachment bytes, settings and a 1,500 AFN remaining balance. See `packaged-acceptance.json`.

A second packaged acceptance run passed at **125% Qt scaling**, also offline (`packaged-acceptance-scaled.json`). A syscall trace of that complete run recorded **zero IPv4/IPv6 sockets, bind or listen calls** (`network-check.json`). There is no development server or external database.

APT's simulated upgrade from 0.1.0 resolved successfully with no additional packages on this host (`package-install-simulation.txt`). Passwordless sudo is unavailable, so **0.2.0 has not been installed system-wide with APT**. Extracted payload execution tests runtime/loading and application workflows; clean-machine installation and uninstall/reinstall remain deployment checks. User records live outside program files.

## Visual and print review

Eight actual screenshots from the packaged executable are in `screenshots/`: dashboard, patient details, minimal registration and image settings, with English/Dari and light/dark examples. They use a 1366×768 window (registration images capture the dialog). Screenshots were taken after layout and chart entry settled. Longer pages scroll; controls remain reachable. The screenshots contain fictional demo data only.

The ivory/rose and plum palettes share reusable tokens, locally drawn charts and bundled fonts/icons. Noto Sans Arabic UI supplies compact Dari text shaping. No network fonts or image services are required. Charts enter once for 260 ms; no continuous animation is used. The Linux/Windows system reduced-motion preference is used where available, with an explicit setting in the app.

Dari A4 PDF was generated from the packaged executable, rendered to PNG and inspected. Fonts are embedded (`pdf-fonts.txt`); current fictional English/Dari A4 and 80 mm examples are in `examples/`. Printing does not change invoice/payment totals. No physical printer was available.

## Performance

Five packaged X11 startup trials with fresh profiles and isolated networking had a **1.080-second median**, range 0.928–1.524 seconds, approximately 90 MiB resident memory at the first-account screen (`startup-xcb.json`). These measurements include process/import time, use warm OS caches and exclude human account entry. `startup.json` retains historical 0.1.0 offscreen measurements.

On 10,000 synthetic patients, 100 warm searches per query had medians 8.890 ms (name), 8.852 ms (phone), 8.199 ms (patient ID) and 7.900 ms (no match); maximum observed 18.463 ms (`benchmark.json`). The host is an Intel i5-6200U with four logical CPUs. These are development-host measurements, not a guarantee for every clinic dataset. File import, thumbnails, backup and PDF export use workers.

## Remaining checks

- **Windows:** native PyInstaller configuration, updated icon, per-user Inno Setup 0.2.0 installer, Start Menu shortcut and Windows CI workflow are prepared. There is no Windows tooling here; no Windows installer build, installation, DPI or runtime test is claimed. Run the workflow or `scripts/build-windows.ps1` on Windows 10/11 x64, then verify install/upgrade and daily workflows. The Ubuntu executable cannot be used as a Windows installer.
- **Physical devices:** printer/thermal margins, USB removal/failure and the clinic's actual display need on-site checks.
- **Clinic review:** Dari terminology and clinical/document wording require clinic review. The app does not suggest diagnosis, medicines or doses.
- **Data:** local roles and salted passwords restrict app actions; SQLite, attachments and backup files are not encrypted. Scheduled backups run while the app is open and an administrator is signed in. Keep separate copies.
- **Legacy images:** older unmanaged image records are conservatively retained as documents when a setting is cleared; their original source cannot be inferred safely. They can be explicitly removed from the legacy image/document list after references are cleared.
- **Scale:** very large attachment libraries and long clinical histories have not been stress-tested. Stock quantities remain whole units. No cloud, SMS, sync or mobile client is included.
