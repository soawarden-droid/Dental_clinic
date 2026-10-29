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

# Additive financial migration: existing invoices, IDs and ledger entries stay intact.
MIGRATIONS.append(r'''
CREATE TABLE charges(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 visit_id INTEGER NOT NULL REFERENCES visits(id),
 kind TEXT NOT NULL CHECK(kind IN ('consultation','procedure','other')),
 description TEXT NOT NULL CHECK(TRIM(description)<>''),
 amount INTEGER NOT NULL CHECK(typeof(amount)='integer' AND amount>=0),
 created TEXT NOT NULL
);
CREATE INDEX charges_visit ON charges(visit_id);
ALTER TABLE invoice_items ADD COLUMN charge_id INTEGER REFERENCES charges(id);
ALTER TABLE payments ADD COLUMN request_key TEXT;
CREATE UNIQUE INDEX payment_request_key ON payments(request_key) WHERE request_key IS NOT NULL;
ALTER TABLE visits ADD COLUMN created TEXT;
ALTER TABLE invoices ADD COLUMN created TEXT;
ALTER TABLE invoices ADD COLUMN voided_at TEXT;
ALTER TABLE invoices ADD COLUMN finalized INTEGER NOT NULL DEFAULT 1 CHECK(finalized IN (0,1));
ALTER TABLE payments ADD COLUMN created TEXT;
UPDATE visits SET created=date||'T00:00:00+04:30';
UPDATE invoices SET created=date||'T00:00:00+04:30';
UPDATE payments SET created=date||'T00:00:00+04:30';
CREATE VIEW invoice_balances AS
 SELECT i.*,COALESCE(items.subtotal,0) subtotal,
 CASE WHEN i.void OR i.finalized=0 THEN 0 ELSE COALESCE(items.subtotal,0)-i.discount END total,
 COALESCE(pay.paid,0) paid,
 CASE WHEN i.void OR i.finalized=0 THEN 0 ELSE COALESCE(items.subtotal,0)-i.discount END-COALESCE(pay.paid,0) balance,
 CASE WHEN i.void THEN 'void' WHEN i.finalized=0 THEN 'draft' WHEN COALESCE(items.subtotal,0)-i.discount=COALESCE(pay.paid,0) THEN 'paid'
 WHEN COALESCE(pay.paid,0)=0 THEN 'unpaid' ELSE 'partial' END status
 FROM invoices i
 LEFT JOIN (SELECT invoice_id,SUM(amount) subtotal FROM invoice_items GROUP BY invoice_id) items ON items.invoice_id=i.id
 LEFT JOIN (SELECT invoice_id,SUM(amount) paid FROM payments GROUP BY invoice_id) pay ON pay.invoice_id=i.id;
CREATE TRIGGER invoice_valid_insert BEFORE INSERT ON invoices
 WHEN typeof(NEW.discount)<>'integer' OR NEW.discount<0 OR (NEW.visit_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM visits WHERE id=NEW.visit_id AND patient_id=NEW.patient_id))
 BEGIN SELECT RAISE(ABORT,'Invalid invoice or visit'); END;
CREATE TRIGGER invoice_finalize_valid BEFORE UPDATE OF finalized ON invoices
 WHEN OLD.finalized=1 OR NEW.finalized<>1 OR NEW.discount>(SELECT COALESCE(SUM(amount),0) FROM invoice_items WHERE invoice_id=NEW.id) OR NOT EXISTS(SELECT 1 FROM invoice_items WHERE invoice_id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'Invalid invoice finalization'); END;
CREATE TRIGGER invoice_identity_immutable BEFORE UPDATE OF patient_id,visit_id,date,discount,created ON invoices
 BEGIN SELECT RAISE(ABORT,'Finalized invoices cannot be edited; refund, void and reissue'); END;
CREATE TRIGGER invoice_void_valid BEFORE UPDATE OF void,reason ON invoices
 WHEN OLD.void=1 OR NEW.void<>1 OR TRIM(COALESCE(NEW.reason,''))='' OR (SELECT paid FROM invoice_balances WHERE id=OLD.id)<>0
 BEGIN SELECT RAISE(ABORT,'Refund payments and provide a reason before voiding'); END;
CREATE TRIGGER invoice_keep_history BEFORE DELETE ON invoices
 BEGIN SELECT RAISE(ABORT,'Financial records cannot be deleted'); END;
CREATE TRIGGER item_valid_insert BEFORE INSERT ON invoice_items
 WHEN typeof(NEW.amount)<>'integer' OR NEW.amount<0
 OR (NEW.treatment_id IS NOT NULL AND NEW.charge_id IS NOT NULL)
 OR (NEW.treatment_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM treatments t JOIN invoices i ON i.visit_id=t.visit_id WHERE i.id=NEW.invoice_id AND t.id=NEW.treatment_id))
 OR (NEW.charge_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM charges c JOIN invoices i ON i.visit_id=c.visit_id WHERE i.id=NEW.invoice_id AND c.id=NEW.charge_id))
 OR EXISTS(SELECT 1 FROM invoices WHERE id=NEW.invoice_id AND (void=1 OR finalized=1))
 OR (NEW.treatment_id IS NOT NULL AND EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.treatment_id=NEW.treatment_id AND i.void=0))
 OR (NEW.charge_id IS NOT NULL AND EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.charge_id=NEW.charge_id AND i.void=0))
 BEGIN SELECT RAISE(ABORT,'Invalid or already billed charge'); END;
CREATE TRIGGER item_immutable_update BEFORE UPDATE ON invoice_items
 BEGIN SELECT RAISE(ABORT,'Finalized charges cannot be edited; void and reissue'); END;
CREATE TRIGGER item_immutable_delete BEFORE DELETE ON invoice_items
 BEGIN SELECT RAISE(ABORT,'Finalized charges cannot be deleted'); END;
CREATE TRIGGER charge_finalized_update BEFORE UPDATE ON charges
 WHEN EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.charge_id=OLD.id AND i.void=0)
 BEGIN SELECT RAISE(ABORT,'Finalized charges cannot be edited; void and reissue'); END;
CREATE TRIGGER charge_finalized_delete BEFORE DELETE ON charges
 WHEN EXISTS(SELECT 1 FROM invoice_items ii WHERE ii.charge_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Financial records cannot be deleted'); END;
CREATE TRIGGER treatment_finalized_update BEFORE UPDATE OF price,procedure,tooth,status ON treatments
 WHEN (NEW.price IS NOT OLD.price OR NEW.procedure IS NOT OLD.procedure OR NEW.tooth IS NOT OLD.tooth OR NEW.status IS NOT OLD.status)
 AND EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.treatment_id=OLD.id AND i.void=0)
 BEGIN SELECT RAISE(ABORT,'Finalized treatments cannot be repriced; void and reissue'); END;
CREATE TRIGGER treatment_price_insert BEFORE INSERT ON treatments WHEN typeof(NEW.price)<>'integer' BEGIN SELECT RAISE(ABORT,'Use integer minor units'); END;
CREATE TRIGGER treatment_price_update BEFORE UPDATE OF price ON treatments WHEN typeof(NEW.price)<>'integer' BEGIN SELECT RAISE(ABORT,'Use integer minor units'); END;
CREATE TRIGGER payment_valid_insert BEFORE INSERT ON payments
 WHEN typeof(NEW.amount)<>'integer' OR NEW.amount=0 OR TRIM(NEW.method)=''
 OR NOT EXISTS(SELECT 1 FROM invoice_balances WHERE id=NEW.invoice_id AND void=0 AND finalized=1)
 OR (NEW.amount>0 AND NEW.amount>(SELECT balance FROM invoice_balances WHERE id=NEW.invoice_id))
 OR (NEW.amount<0 AND (-NEW.amount>(SELECT paid FROM invoice_balances WHERE id=NEW.invoice_id) OR TRIM(COALESCE(NEW.reason,''))=''))
 OR (NEW.reversal_of IS NOT NULL AND (NEW.amount>=0 OR NOT EXISTS(SELECT 1 FROM payments p WHERE p.id=NEW.reversal_of AND p.invoice_id=NEW.invoice_id AND p.amount>0)
 OR -NEW.amount>(SELECT amount FROM payments WHERE id=NEW.reversal_of)+COALESCE((SELECT SUM(amount) FROM payments WHERE reversal_of=NEW.reversal_of),0)))
 BEGIN SELECT RAISE(ABORT,'Invalid payment, overpayment or refund'); END;
CREATE TRIGGER payment_immutable_update BEFORE UPDATE ON payments
 BEGIN SELECT RAISE(ABORT,'Payments cannot be edited; record a refund'); END;
CREATE TRIGGER payment_immutable_delete BEFORE DELETE ON payments
 BEGIN SELECT RAISE(ABORT,'Payments cannot be deleted; record a refund'); END;
''')
