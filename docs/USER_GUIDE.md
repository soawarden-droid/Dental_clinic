# Your clinic, on one computer

Install the Ubuntu package using your system's package installer. Open **Faramarz Dental Clinic** from Applications. Create your own administrator name and a password of at least ten characters; there is no default account. Remember this password. A backup restores the accounts and passwords that existed when it was made.

The app works without internet. Everything is saved on this computer. English and دری are available at the top of the window; switch at any time. In Settings choose Light, Dark, or System, and Gregorian or Solar Hijri dates. Solar date fields use `1405/08/06`; Gregorian fields use `2026-10-28`. Dates and appointments use Kabul time. Dari wording is an initial Afghan adaptation and should be reviewed by the clinic before routine use.

## A normal visit

1. Select **New patient**. Enter only the full name and phone number in Essential details. Additional information starts collapsed; all of it is optional, including age, date of birth, gender and clinical notes. Local Afghan and +93 phone formats are accepted. A shared family number can be saved after confirming the duplicate warning. No age, date or gender is invented.
2. Search by the beginning of the patient's name, phone, or `P-000001`. Double-click to open the patient. Important alerts are shown above the record. **Edit patient** updates demographics and, for the administrator, medical notes.
3. Select **New visit**. Record the doctor, date, notes, and an optional follow-up date. Use **Visits & treatments** for the visit history and **Dental chart** for permanent or primary teeth. Choose the visit before adding work. The chart is viewed facing the patient: the patient's right is on your left, in both languages. Click a tooth to add work. A blank tooth is allowed for whole-mouth work. The catalogue price fills automatically and can be changed. Enter the condition and notes yourself. Amber indicates planned work; teal indicates completed work. The list below contains the history. Double-click a treatment for its details. Planned work across visits forms the patient's ongoing treatment plan.
4. Select a planned treatment and **Complete treatment** when the work is done. Only completed, unbilled work goes onto an invoice. Select **Issue invoice**, review the discount, and save. Invoices keep their original item descriptions and prices when catalogue prices change.
5. In **Invoices & payments**, select an invoice and **Record payment**. Enter only the amount received. Partial payments leave a remaining balance. Save to open the receipt. **Receipt** reopens a selected payment receipt later. **Print preview** opens your system's printer controls; **Export PDF** saves a file. Choose A4 or 80 mm receipt paper. Printer drivers must support the selected paper. Printing never records a payment.
6. If a payment is wrong, an administrator can record a **Refund** with a reason. For an incorrect invoice, refund any collected balance, **Void invoice** with a reason, and issue the corrected invoice. The old invoice and payment entries remain in the history and audit trail. Refund receipts show a negative amount.

No diagnosis, medicine, dose, or treatment is suggested by the app. The doctor writes prescriptions and aftercare instructions in the patient's **Prescriptions** tab and can print them.

## Reception and appointments

Choose **Appointments** to see the agenda, day list, or seven-day calendar. Enter a date in your selected calendar and press Apply. Add an appointment with its duration. Conflicting times cause a warning; deliberate overlaps require confirmation. **Walk-in** creates an arrived appointment for an existing or newly registered patient. Change the status to arrived, in treatment, completed, cancelled, or missed. Double-click an appointment to open the patient. Follow-ups appear on the Overview page; there are no SMS messages.

An administrator creates receptionist accounts in Settings. Receptionists can register demographics, handle appointments, issue invoices for completed work, and collect payments. Clinical notes, files, prescriptions, refunds, reports, stock editing, profile changes, and restoration require the administrator. Clinical alerts remain visible for reception safety. Each account has its own password. **Lock** or Ctrl+L hides the record until an account signs in again.

## Materials and money out

- In **Materials**, add a name, smallest practical whole-number unit (for example syringe, capsule, or millilitre), and minimum stock. Quantities are whole numbers in that unit.
- Add a supplier in **Purchases**, then **Record purchase**. Add each item separately, including quantity, unit cost, batch and expiry when relevant. Add multiple items before Save. Enter the amount paid. Later, select the purchase and **Record payment** for its supplier balance. Double-click a purchase to inspect its items.
- In **Materials**, select the material and **Stock movement**. Select an existing batch for a deduction. Use negative quantities for consumption, wastage and returns to the supplier, and a reason for every adjustment. An optional treatment number links usage to the clinical work. Confirm deductions; the same treatment and material cannot be deducted twice through this action. Different materials can be linked to the same treatment. Additional later consumption must be recorded explicitly as a separate adjustment with an explanatory reason. Low stock and batches expiring within 60 days (including overdue batches) are listed. These are recordkeeping alerts, not advice about using a material.
- Use **Expenses** for rent, electricity, salaries, maintenance and other expenses. **Laboratory** tracks the patient, optional treatment, laboratory, sent/expected/actual dates, status, cost and cumulative payment. Update a case when it returns or you pay more. Purchase and lab payments are dated ledger entries. Do not enter a lab payment again as an expense, or it will be counted twice.
- **Reports** compares a selected period with the preceding equally long period. It separates billed work, net collected payments, expenses, supplier payments and lab payments. Outstanding balance is the current balance across all dates. Cash surplus is an estimate of cash in minus recorded cash out; it is not accounting profit. Export CSV or print/PDF the report.

## Clinic information and documents

An administrator edits **Clinic profile**: names, biography, qualifications, hours, contact details, photograph, logo, background and supporting documents. No qualifications or photographs are invented. The logo appears on printed patient documents. Patient photos and documents belong to their patient; clinic materials are stored separately. Use **Documents → Open document** to open a file in its installed local viewer. A viewer may be needed for some file types. Archive a patient to remove them from active search; use Archived patients to restore them. The app deliberately provides no permanent patient deletion button.

## Back up every day

Choose **Backup now**, then a local folder or mounted USB drive. A successful backup contains the database, accounts, settings, patient files and clinic images/documents in one `.fdbackup` file. A CSV or PDF is not a complete backup. In Settings choose the folder, how many backups to keep, and whether to back up daily while the app is open and an administrator is signed in. Keep a second copy on a different device. Scheduled backups cannot run while the app is closed, locked, or signed in only as reception.

To restore, sign in as administrator, choose **Restore backup**, select a backup and read the replacement warning. All current records, accounts, files and settings will be replaced. The app checks the backup first and makes a safety backup beside the application data folder before replacement. Sign in using an account from the restored backup. A failed check leaves the current records in place. Restoration to another computer requires installing the app there first and selecting the backup.

Local accounts protect access through this app. They do **not** encrypt the database, files or backups. Protect the computer account, use full-disk encryption, and keep backup drives private. There is no online password recovery or shared master password.

## Shortcuts and help

Ctrl+N: New patient. Ctrl+F: Search. Ctrl+L: Lock. Ctrl+B: Backup (administrator). Tab moves through fields; Enter activates the focused default action. Forms warn before discarding edits. A successful save appears in the bottom status bar. If an action fails, review the entry and try again. Never overwrite your only backup.

The ordinary profile is stored under `~/.local/share/FaramarzDental` on Ubuntu (or the configured XDG data directory), and `%LOCALAPPDATA%\FaramarzDental` on Windows. Updates replace program files, not this data folder. An optional developer demo uses a separate `FaramarzDental-Demo` folder and fictional records. Normal first launch is empty.

## Dashboard and appearance

The dashboard shows today’s visits, net payments collected today (receipts minus refunds), outstanding active invoice balances and upcoming appointments over seven days. The trend uses the selected 7/30/90-day period; the donut counts completed treatments by visit date. Click a metric or chart to open its saved records. Empty periods contain no invented activity. In Settings, Reduce motion disables chart entry animations; the system preference is also respected when available.

Open **Clinic profile → Images & appearance** to add, replace, remove or preview the doctor photo, logo, background and gallery. Restore default clears the custom image. Background opacity is adjustable from 0–30%. Changes survive restart; only managed copies without other references are removed. Your original files and unrelated documents are retained. Patient photos have matching controls under **Photos & documents**.

## Fees, partial payments and later visits (0.3.0)

1. Register the patient using name and phone. Open the patient and select **New visit**. Reception can register a non-clinical visit; clinical notes remain restricted to the doctor.
2. Select **Add charge**. Choose **Doctor consultation fee**, enter a description and `500`, then Save. Add another charge of type **Treatment charge** for `2000`, or have the doctor record and complete a treatment priced at `2000`. Use one of those routes for a given procedure to avoid charging it twice.
3. In **Invoices & payments**, the saved drafts show AFN 2,500. Drafts survive restart but do not count as debt yet. Select **Issue invoice**, choose the visit and any discount, then Save. The invoice now shows total AFN 2,500, paid AFN 0, balance AFN 2,500 and **unpaid** status. No payment is implied by saving.
4. Select **Record payment**, choose that invoice, enter the date and `1000`, then Save. Paid becomes AFN 1,000, balance AFN 1,500 and status **partial**. Print or export the receipt. Printing again records no additional money.
5. On a later visit, reopen the patient and record the new visit if needed. Select **Record payment**, choose the original outstanding invoice and enter `1500`. Balance becomes AFN 0 and status **paid**. Multiple outstanding invoices remain separate; choose which bill this receipt settles.
6. Select **Statement** for a printable chronological list of visits, final charges, discounts, receipts/refunds and running balance. Drafts are excluded and voided charges remain visible as history.

Before finalization, **Edit draft charge** or the doctor's **Edit treatment** changes the saved draft. After finalization, an administrator must refund any received money with a reason, void the incorrect invoice with a reason, edit the draft, then issue the corrected invoice. Previous invoices and receipts remain in history. No credit/overpayment workflow exists; amounts above the selected invoice's balance are rejected.

Dashboard **Billed today** means invoices issued today, after discounts and excluding voids. **Collected today** means today's receipts minus today's refunds, including payments on older invoices. These two metrics can differ legitimately. Outstanding includes all valid invoices regardless of date. No doctor compensation is calculated from these patient fees.

## Forgotten local password

On the login screen choose **Forgot password?**, select the local account, enter and repeat a new password of at least ten characters, confirm that you own this local profile, then reset. A complete private backup is created under `FaramarzPasswordRecoveryBackups` beside the profile before the password changes. Sign in normally afterward. Records, other accounts and attachments are preserved; the reset is audited.

For local owner support with the clinic app closed, run `faramarz-dental --recover-password` (or `faramarz-dental.exe --recover-password` on Windows). Windows also has a Start Menu recovery shortcut. Recovery is available to the operating-system user who can access the local profile; protect that OS account and use disk encryption. There is no master password or remote password recovery.

If an update reports that the database needs a newer app, open the newest version instead of deleting or downgrading the database. On Ubuntu a per-user install may override an older system package. The supplied `python3 scripts/install-user.py dist/faramarz-dental` refreshes that user installation and Applications shortcut without opening records. Close the old window and reopen afterward.
