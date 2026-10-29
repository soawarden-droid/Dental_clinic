MIGRATIONS = [r'''
CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','receptionist')));
CREATE TABLE patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, father TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '', dob TEXT DEFAULT '', estimated_age TEXT DEFAULT '', history TEXT DEFAULT '', allergies TEXT DEFAULT '', medications TEXT DEFAULT '', alerts TEXT DEFAULT '', emergency TEXT DEFAULT '', consent TEXT DEFAULT '', archived INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE INDEX patient_name ON patients(name COLLATE NOCASE);
CREATE INDEX patient_phone ON patients(phone);
CREATE TABLE visits(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES patients(id), date TEXT NOT NULL, doctor TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', followup TEXT NOT NULL DEFAULT '');
CREATE INDEX visits_patient ON visits(patient_id,date);
CREATE TABLE catalogue(id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0));
CREATE TABLE treatments(id INTEGER PRIMARY KEY AUTOINCREMENT, visit_id INTEGER NOT NULL REFERENCES visits(id), procedure TEXT NOT NULL, tooth TEXT NOT NULL DEFAULT '', condition TEXT DEFAULT '', price INTEGER NOT NULL CHECK(price>=0), status TEXT NOT NULL CHECK(status IN ('planned','completed')), notes TEXT DEFAULT '', stock_confirmed INTEGER DEFAULT 0);
CREATE TABLE invoices(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES patients(id), visit_id INTEGER REFERENCES visits(id), date TEXT NOT NULL, discount INTEGER NOT NULL DEFAULT 0 CHECK(discount>=0), void INTEGER NOT NULL DEFAULT 0, reason TEXT DEFAULT '');
CREATE TABLE invoice_items(id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id), treatment_id INTEGER REFERENCES treatments(id), description TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>=0));
CREATE TABLE payments(id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL REFERENCES invoices(id), date TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount<>0), method TEXT NOT NULL, reason TEXT DEFAULT '', reversal_of INTEGER REFERENCES payments(id));
CREATE INDEX invoice_patient ON invoices(patient_id);
CREATE INDEX payments_invoice ON payments(invoice_id);
CREATE TABLE appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL REFERENCES patients(id), starts TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes BETWEEN 5 AND 480), status TEXT NOT NULL CHECK(status IN ('scheduled','arrived','in treatment','completed','cancelled','missed')), notes TEXT DEFAULT '');
CREATE INDEX appointment_start ON appointments(starts);
CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL, minimum INTEGER NOT NULL DEFAULT 0 CHECK(minimum>=0));
CREATE TABLE suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT DEFAULT '', address TEXT DEFAULT '');
CREATE TABLE purchases(id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_id INTEGER NOT NULL REFERENCES suppliers(id), date TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0 CHECK(paid>=0));
CREATE TABLE purchase_items(id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES purchases(id), material_id INTEGER NOT NULL REFERENCES materials(id), quantity INTEGER NOT NULL CHECK(quantity>0), unit_cost INTEGER NOT NULL CHECK(unit_cost>=0), batch TEXT DEFAULT '', expiry TEXT DEFAULT '');
CREATE TABLE stock(id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL REFERENCES materials(id), quantity INTEGER NOT NULL CHECK(quantity<>0), kind TEXT NOT NULL, date TEXT NOT NULL, batch TEXT DEFAULT '', expiry TEXT DEFAULT '', treatment_id INTEGER REFERENCES treatments(id), reason TEXT NOT NULL DEFAULT '');
CREATE INDEX stock_material ON stock(material_id);
CREATE TABLE expenses(id INTEGER PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), notes TEXT DEFAULT '');
CREATE TABLE labs(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), treatment_id INTEGER REFERENCES treatments(id), laboratory TEXT NOT NULL, description TEXT NOT NULL, sent TEXT NOT NULL, expected TEXT NOT NULL, returned TEXT DEFAULT '', status TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>=0), paid INTEGER NOT NULL CHECK(paid>=0 AND paid<=cost));
CREATE TABLE prescriptions(id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), date TEXT NOT NULL, content TEXT NOT NULL, aftercare TEXT NOT NULL);
CREATE TABLE attachments(id INTEGER PRIMARY KEY, patient_id INTEGER REFERENCES patients(id), scope TEXT NOT NULL CHECK(scope IN ('patient','profile')), name TEXT NOT NULL, stored TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL);
CREATE TABLE audit(id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
''']

MIGRATIONS.append(r'''
CREATE TABLE supplier_payments(id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES purchases(id), date TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0));
CREATE TABLE lab_payments(id INTEGER PRIMARY KEY, lab_id INTEGER NOT NULL REFERENCES labs(id), date TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0));
INSERT INTO supplier_payments(purchase_id,date,amount) SELECT id,date,paid FROM purchases WHERE paid>0;
INSERT INTO lab_payments(lab_id,date,amount) SELECT id,sent,paid FROM labs WHERE paid>0;
CREATE INDEX supplier_payment_date ON supplier_payments(date);
CREATE INDEX lab_payment_date ON lab_payments(date);
''')

# Existing optional columns already allow NULL. Normalize only blank values;
# never guess missing ages/dates or rebuild the parent table and its links.
MIGRATIONS.append(r'''
ALTER TABLE patients ADD COLUMN gender TEXT;
ALTER TABLE patients ADD COLUMN email TEXT;
UPDATE patients SET father=NULLIF(TRIM(father),''), address=NULLIF(TRIM(address),''),
 dob=NULLIF(TRIM(dob),''), estimated_age=NULLIF(TRIM(estimated_age),''),
 history=NULLIF(TRIM(history),''), allergies=NULLIF(TRIM(allergies),''),
 medications=NULLIF(TRIM(medications),''), alerts=NULLIF(TRIM(alerts),''),
 emergency=NULLIF(TRIM(emergency),''), consent=NULLIF(TRIM(consent),'');
CREATE TRIGGER patient_essential_insert BEFORE INSERT ON patients
WHEN NEW.name IS NULL OR TRIM(NEW.name)='' OR NEW.phone IS NULL OR TRIM(NEW.phone)=''
BEGIN SELECT RAISE(ABORT,'Name and phone are required'); END;
CREATE TRIGGER patient_essential_update BEFORE UPDATE OF name,phone ON patients
WHEN NEW.name IS NULL OR TRIM(NEW.name)='' OR ((NEW.phone IS NULL OR TRIM(NEW.phone)='') AND NEW.phone IS NOT OLD.phone)
BEGIN SELECT RAISE(ABORT,'Name and phone are required'); END;
''')

MIGRATIONS.append(r'''
ALTER TABLE attachments ADD COLUMN image_owned INTEGER NOT NULL DEFAULT 0;
CREATE TABLE image_assets(slot TEXT PRIMARY KEY,original_id INTEGER NOT NULL REFERENCES attachments(id),preview_id INTEGER NOT NULL REFERENCES attachments(id));
''')

# Normalize legacy blank defaults even for direct inserts, keeping optional values nullable.
MIGRATIONS[2] += r'''
CREATE TRIGGER patient_optional_insert AFTER INSERT ON patients BEGIN UPDATE patients SET father=NULLIF(TRIM(father),''),address=NULLIF(TRIM(address),''),dob=NULLIF(TRIM(dob),''),estimated_age=NULLIF(TRIM(estimated_age),''),history=NULLIF(TRIM(history),''),allergies=NULLIF(TRIM(allergies),''),medications=NULLIF(TRIM(medications),''),alerts=NULLIF(TRIM(alerts),''),emergency=NULLIF(TRIM(emergency),''),consent=NULLIF(TRIM(consent),''),gender=NULLIF(TRIM(gender),''),email=NULLIF(TRIM(email),'') WHERE id=NEW.id; END;
CREATE TRIGGER patient_optional_update AFTER UPDATE OF father,address,dob,estimated_age,history,allergies,medications,alerts,emergency,consent,gender,email ON patients WHEN (NEW.father IS NOT NULL AND TRIM(NEW.father)='') OR (NEW.address IS NOT NULL AND TRIM(NEW.address)='') OR (NEW.dob IS NOT NULL AND TRIM(NEW.dob)='') OR (NEW.estimated_age IS NOT NULL AND TRIM(NEW.estimated_age)='') OR (NEW.history IS NOT NULL AND TRIM(NEW.history)='') OR (NEW.allergies IS NOT NULL AND TRIM(NEW.allergies)='') OR (NEW.medications IS NOT NULL AND TRIM(NEW.medications)='') OR (NEW.alerts IS NOT NULL AND TRIM(NEW.alerts)='') OR (NEW.emergency IS NOT NULL AND TRIM(NEW.emergency)='') OR (NEW.consent IS NOT NULL AND TRIM(NEW.consent)='') OR (NEW.gender IS NOT NULL AND TRIM(NEW.gender)='') OR (NEW.email IS NOT NULL AND TRIM(NEW.email)='') BEGIN UPDATE patients SET father=NULLIF(TRIM(father),''),address=NULLIF(TRIM(address),''),dob=NULLIF(TRIM(dob),''),estimated_age=NULLIF(TRIM(estimated_age),''),history=NULLIF(TRIM(history),''),allergies=NULLIF(TRIM(allergies),''),medications=NULLIF(TRIM(medications),''),alerts=NULLIF(TRIM(alerts),''),emergency=NULLIF(TRIM(emergency),''),consent=NULLIF(TRIM(consent),''),gender=NULLIF(TRIM(gender),''),email=NULLIF(TRIM(email),'') WHERE id=NEW.id; END;
'''
