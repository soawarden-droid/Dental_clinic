"""Business operations. All mutations pass through permissions and transactions."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timedelta
from .domain import now, today, password_hash, password_verify, check_date, phone_normalize, TEETH


class Service:
    def __init__(self, store):
        self.s = store
        self.s.migrate()
        self.user = None

    def allowed(self, clinical=False, admin=False):
        if not self.user:
            raise PermissionError('Please unlock the application')
        if (clinical or admin) and self.user['role'] != 'admin':
            raise PermissionError('Administrator access required')

    @contextmanager
    def action(self, name, details='', clinical=False, admin=False):
        self.allowed(clinical, admin)
        with self.s.db:
            yield self.s.db
            self.s.db.execute('INSERT INTO audit(at,actor,action,details) VALUES(?,?,?,?)', (now(), self.user['username'], name, str(details)))

    def register(self, username, password, role='admin'):
        if self.s.rows('SELECT id FROM users'):
            self.allowed(admin=True)
        elif role != 'admin':
            raise ValueError('First account must be an administrator')
        username = username.strip()
        if not username or role not in ('admin','receptionist'):
            raise ValueError('Invalid account')
        hashed = password_hash(password)
        with self.s.db:
            self.s.db.execute('INSERT INTO users(username,password,role) VALUES(?,?,?)', (username, hashed, role))
            self.s.db.execute('INSERT INTO audit(at,actor,action,details) VALUES(?,?,?,?)', (now(), username, 'account created', role))

    def login(self, username, password):
        r = self.s.one('SELECT * FROM users WHERE username=?', (username.strip(),))
        if not r or not password_verify(password, r['password']):
            raise ValueError('Incorrect username or password')
        self.user = {k:v for k,v in r.items() if k != 'password'}

    def search(self, term='', archived=False, limit=100, offset=0):
        self.allowed()
        term = term.strip()
        # Indexed exact ID and phone, prefix range for names. Escape LIKE wildcards.
        pattern = term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        number = term.upper().removeprefix('P-').lstrip('0') or '0'
        return self.s.rows("SELECT * FROM patients WHERE archived=? AND (name LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\' OR id=?) ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", (int(archived), pattern, pattern, number, limit, offset))

    def save_patient(self, values, patient_id=None):
        values = dict(values)
        values['name'] = values.get('name','').strip()
        if not values['name']:
            raise ValueError('Full name is required')
        values['phone'] = phone_normalize(values.get('phone',''))
        if values.get('dob'):
            check_date(values['dob'])
            if values['dob'] > today():
                raise ValueError('Birth date cannot be in the future')
        if values.get('estimated_age'):
            if not values['estimated_age'].isdigit() or not 0 <= int(values['estimated_age']) <= 130:
                raise ValueError('Estimated age must be between 0 and 130')
        keys = ['name','father','phone','address','dob','estimated_age','history','allergies','medications','alerts','emergency','consent']
        data = [values.get(k,'') for k in keys]
        if patient_id and self.user and self.user['role'] != 'admin':
            old = self.s.one('SELECT * FROM patients WHERE id=?', (patient_id,))
            for key in ('history','allergies','medications','alerts','consent'):
                if values.get(key,'') != old[key]:
                    raise PermissionError('Administrator access required')
        elif self.user and self.user['role'] != 'admin' and any(values.get(k) for k in ('history','allergies','medications','alerts','consent')):
            raise PermissionError('Administrator access required')
        with self.action('patient saved', patient_id or values['name']) as db:
            if patient_id:
                db.execute('UPDATE patients SET '+','.join(k+'=?' for k in keys)+' WHERE id=?', data+[patient_id])
            else:
                patient_id = db.execute('INSERT INTO patients('+','.join(keys)+',created) VALUES('+','.join('?' for _ in range(len(keys)+1))+')', data+[now()]).lastrowid
        return patient_id

    def duplicates(self, name, phone, exclude=0):
        return self.s.rows('SELECT id,name,phone FROM patients WHERE id<>? AND (lower(name)=lower(?) OR (phone<>\'\' AND phone=?))', (exclude, name.strip(), phone_normalize(phone)))

    def archive(self, pid, value):
        with self.action('patient archive status', f'{pid}: {value}', admin=True) as db:
            db.execute('UPDATE patients SET archived=? WHERE id=?', (int(value), pid))

    def visit(self, pid, doctor, notes='', followup='', date=None):
        check_date(followup, True)
        check_date(date or today())
        if not doctor.strip():raise ValueError('Please check your entry')
        with self.action('visit created', pid, clinical=True) as db:
            return db.execute('INSERT INTO visits(patient_id,date,doctor,notes,followup) VALUES(?,?,?,?,?)', (pid,date or today(),doctor,notes,followup)).lastrowid

    def treatment(self, visit_id, procedure, price, tooth='', condition='', status='planned', notes=''):
        if not procedure.strip() or (tooth and tooth not in TEETH) or price < 0:
            raise ValueError('Invalid treatment or tooth number')
        with self.action('treatment recorded', visit_id, clinical=True) as db:
            return db.execute('INSERT INTO treatments(visit_id,procedure,price,tooth,condition,status,notes) VALUES(?,?,?,?,?,?,?)', (visit_id,procedure,price,tooth,condition,status,notes)).lastrowid

    def complete(self, treatment_id):
        with self.action('treatment completed', treatment_id, clinical=True) as db:
            db.execute("UPDATE treatments SET status='completed' WHERE id=?", (treatment_id,))

    def invoice(self, visit_id, discount=0):
        with self.action('invoice issued', visit_id) as db:
            visit = db.execute('SELECT * FROM visits WHERE id=?', (visit_id,)).fetchone()
            items = db.execute("SELECT * FROM treatments WHERE visit_id=? AND status='completed' AND id NOT IN (SELECT ii.treatment_id FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.treatment_id IS NOT NULL AND i.void=0)", (visit_id,)).fetchall()
            if not items:
                raise ValueError('No completed unbilled treatments for this visit')
            if not 0 <= discount <= sum(r['price'] for r in items):
                raise ValueError('Discount exceeds invoice subtotal')
            iid = db.execute('INSERT INTO invoices(patient_id,visit_id,date,discount) VALUES(?,?,?,?)', (visit['patient_id'],visit_id,today(),discount)).lastrowid
            db.executemany('INSERT INTO invoice_items(invoice_id,treatment_id,description,amount) VALUES(?,?,?,?)', [(iid,r['id'],r['procedure']+(' · '+r['tooth'] if r['tooth'] else ''),r['price']) for r in items])
            return iid

    def invoice_totals(self, iid):
        r = self.s.one('SELECT * FROM invoices WHERE id=?', (iid,))
        total = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM invoice_items WHERE invoice_id=?', (iid,))['n'] - r['discount']
        paid = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM payments WHERE invoice_id=?', (iid,))['n']
        return {'total': 0 if r['void'] else total, 'paid': paid, 'balance': (0 if r['void'] else total)-paid}

    def payment(self, iid, amount, method, reason='', reversal_of=None):
        with self.action('payment recorded' if amount>0 else 'payment refunded', iid, admin=amount<0) as db:
            totals = self.invoice_totals(iid)
            inv = self.s.one('SELECT * FROM invoices WHERE id=?', (iid,))
            if amount == 0 or inv['void'] or (amount>0 and amount>totals['balance']) or (amount<0 and -amount>totals['paid']):
                raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            if amount<0 and not reason.strip():
                raise ValueError('A refund reason is required')
            if reversal_of is not None:
                original = self.s.one('SELECT * FROM payments WHERE id=? AND invoice_id=?', (reversal_of, iid))
                if not original or original['amount']<=0:
                    raise ValueError('Invalid original payment')
                refunded = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM payments WHERE reversal_of=?', (reversal_of,))['n']
                if amount>=0 or -amount > original['amount']+refunded:
                    raise ValueError('Refund exceeds original payment')
            return db.execute('INSERT INTO payments(invoice_id,date,amount,method,reason,reversal_of) VALUES(?,?,?,?,?,?)', (iid,today(),amount,method,reason,reversal_of)).lastrowid

    def void_invoice(self, iid, reason):
        if not reason.strip():
            raise ValueError('A correction reason is required')
        with self.action('invoice voided', f'{iid}: {reason}', admin=True) as db:
            if self.invoice_totals(iid)['paid']:
                raise ValueError('Refund payments before voiding this invoice')
            db.execute('UPDATE invoices SET void=1,reason=? WHERE id=?', (reason,iid))

    def appointment(self, pid, starts, minutes, status='scheduled', notes='', override=False):
        start = datetime.fromisoformat(starts)
        if not 5 <= minutes <= 480:
            raise ValueError('Duration must be 5 to 480 minutes')
        end = start+timedelta(minutes=minutes)
        conflicts = self.s.rows("SELECT * FROM appointments WHERE status NOT IN ('cancelled','missed') AND starts<? AND datetime(starts,'+'||minutes||' minutes')>datetime(?)", (end.isoformat(timespec='minutes'),start.isoformat(timespec='minutes')))
        if conflicts and not override:
            raise ValueError('Appointment time conflicts with another appointment')
        with self.action('appointment created', pid) as db:
            return db.execute('INSERT INTO appointments(patient_id,starts,minutes,status,notes) VALUES(?,?,?,?,?)', (pid,start.isoformat(timespec='minutes'),minutes,status,notes)).lastrowid

    def status(self, aid, status):
        with self.action('appointment status', f'{aid}: {status}') as db:
            db.execute('UPDATE appointments SET status=? WHERE id=?', (status,aid))

    def add_record(self, table, values, clinical=False):
        permitted = {'catalogue','materials','suppliers','expenses','labs','prescriptions'}
        if table not in permitted:
            raise ValueError('Unsupported record')
        allowed_cols = {r['name'] for r in self.s.rows('PRAGMA table_info('+table+')')}-{'id'}
        if not set(values)<=allowed_cols:
            raise ValueError('Unsupported field')
        with self.action(table+' added', '', clinical=clinical, admin=table in {'catalogue','materials','suppliers','expenses','labs'}) as db:
            rid = db.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')', list(values.values())).lastrowid
            if table=='labs' and values.get('paid',0)>0:
                db.execute('INSERT INTO lab_payments(lab_id,date,amount) VALUES(?,?,?)', (rid,values['sent'],values['paid']))
            return rid

    def stock_quantity(self, mid):
        return self.s.one('SELECT COALESCE(SUM(quantity),0) n FROM stock WHERE material_id=?', (mid,))['n']

    def stock(self, mid, quantity, kind, reason='', batch='', expiry='', treatment_id=None):
        check_date(expiry, True)
        if not quantity or not reason.strip() or kind not in ('use','wastage','return','adjustment'):
            raise ValueError('Quantity, movement type and reason are required')
        if kind in ('use','wastage','return') and quantity>0:
            raise ValueError('Use a negative quantity for use, wastage or supplier return')
        with self.action('stock movement', f'{mid}: {quantity} {reason}', admin=True) as db:
            if self.stock_quantity(mid)+quantity<0:
                raise ValueError('Insufficient stock')
            batch_quantity=self.s.one('SELECT COALESCE(SUM(quantity),0) n FROM stock WHERE material_id=? AND batch=? AND expiry=?',(mid,batch,expiry))['n']
            if quantity<0 and batch_quantity+quantity<0:
                raise ValueError('Insufficient stock in the selected batch')
            if treatment_id:
                t = self.s.one('SELECT stock_confirmed FROM treatments WHERE id=?', (treatment_id,))
                if not t or self.s.one('SELECT id FROM stock WHERE treatment_id=? AND material_id=?',(treatment_id,mid)):
                    raise ValueError('Treatment stock already deducted or treatment missing')
                db.execute('UPDATE treatments SET stock_confirmed=1 WHERE id=?', (treatment_id,))
            db.execute('INSERT INTO stock(material_id,quantity,kind,date,batch,expiry,treatment_id,reason) VALUES(?,?,?,?,?,?,?,?)', (mid,quantity,kind,today(),batch,expiry,treatment_id,reason))

    def purchase(self, supplier, items, paid):
        total = sum(i['quantity']*i['unit_cost'] for i in items)
        if not items or not 0<=paid<=total:
            raise ValueError('Invalid purchase or paid amount')
        with self.action('purchase recorded', supplier, admin=True) as db:
            pid = db.execute('INSERT INTO purchases(supplier_id,date,paid) VALUES(?,?,?)', (supplier,today(),paid)).lastrowid
            if paid:
                db.execute('INSERT INTO supplier_payments(purchase_id,date,amount) VALUES(?,?,?)',(pid,today(),paid))
            for i in items:
                check_date(i.get('expiry',''), True)
                db.execute('INSERT INTO purchase_items(purchase_id,material_id,quantity,unit_cost,batch,expiry) VALUES(?,?,?,?,?,?)', (pid,i['material_id'],i['quantity'],i['unit_cost'],i.get('batch',''),i.get('expiry','')))
                db.execute("INSERT INTO stock(material_id,quantity,kind,date,batch,expiry,reason) VALUES(?,?,'purchase',?,?,?,?)", (i['material_id'],i['quantity'],today(),i.get('batch',''),i.get('expiry',''),f'Purchase {pid}'))
            return pid

    def attach(self, source, pid=None):
        self.allowed(clinical=pid is not None, admin=pid is None)
        source = Path(source)
        folder = self.s.root/'attachments'
        folder.mkdir(exist_ok=True)
        stored = uuid.uuid4().hex + source.suffix.lower()
        target = folder/stored
        shutil.copyfile(source,target)
        try:
            with target.open('rb') as file:
                digest = hashlib.file_digest(file, 'sha256').hexdigest()
            with self.action('attachment added', source.name, clinical=pid is not None, admin=pid is None) as db:
                return db.execute('INSERT INTO attachments(patient_id,scope,name,stored,sha256) VALUES(?,?,?,?,?)', (pid,'patient' if pid else 'profile',source.name,stored,digest)).lastrowid
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def report(self, start, end):
        check_date(start); check_date(end)
        if start>end:
            raise ValueError('Start date must precede end date')
        self.allowed(admin=True)
        collected = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM payments WHERE date BETWEEN ? AND ?', (start,end))['n']
        expenses = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM expenses WHERE date BETWEEN ? AND ?', (start,end))['n']
        billed = sum(self.invoice_totals(r['id'])['total'] for r in self.s.rows('SELECT id FROM invoices WHERE date BETWEEN ? AND ?', (start,end)))
        purchases = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM supplier_payments WHERE date BETWEEN ? AND ?', (start,end))['n']
        lab = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM lab_payments WHERE date BETWEEN ? AND ?', (start,end))['n']
        outstanding = sum(self.invoice_totals(r['id'])['balance'] for r in self.s.rows('SELECT id FROM invoices'))
        return dict(billed=billed,collected=collected,expenses=expenses,purchases=purchases,lab=lab,outstanding=outstanding,cash_surplus=collected-expenses-purchases-lab)


    def supplier_payment(self, purchase_id, amount):
        with self.action('supplier payment', purchase_id, admin=True) as db:
            r = self.s.one('SELECT p.paid,COALESCE(SUM(i.quantity*i.unit_cost),0) total FROM purchases p JOIN purchase_items i ON i.purchase_id=p.id WHERE p.id=? GROUP BY p.id',(purchase_id,))
            if not r or amount<=0 or amount>r['total']-r['paid']:
                raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            db.execute('INSERT INTO supplier_payments(purchase_id,date,amount) VALUES(?,?,?)',(purchase_id,today(),amount))
            db.execute('UPDATE purchases SET paid=paid+? WHERE id=?',(amount,purchase_id))

    def update_lab(self, lid, status, returned, paid):
        check_date(returned,True)
        with self.action('lab updated',lid,admin=True) as db:
            r=self.s.one('SELECT * FROM labs WHERE id=?',(lid,))
            if not r or not r['paid']<=paid<=r['cost']:
                raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            if paid>r['paid']:
                db.execute('INSERT INTO lab_payments(lab_id,date,amount) VALUES(?,?,?)',(lid,today(),paid-r['paid']))
            db.execute('UPDATE labs SET status=?,returned=?,paid=? WHERE id=?',(status,returned,paid,lid))

    def record_attachment(self, meta, pid=None):
        with self.action('attachment added',meta['name'],clinical=pid is not None,admin=pid is None) as db:
            return db.execute('INSERT INTO attachments(patient_id,scope,name,stored,sha256) VALUES(?,?,?,?,?)', (pid,'patient' if pid else 'profile',meta['name'],meta['stored'],meta['sha256'])).lastrowid


def prepare_attachment(root, source, thumbnail=False):
    """Only file and image work; safe to call on a worker without a DB connection."""
    source=Path(source);folder=Path(root)/'attachments';folder.mkdir(exist_ok=True)
    stored=uuid.uuid4().hex+source.suffix.lower();target=folder/stored
    try:
        shutil.copyfile(source,target)
        with target.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
        result=[dict(name=source.name,stored=stored,sha256=digest)]
        if thumbnail:
            from PySide6.QtGui import QImageReader
            from PySide6.QtCore import Qt,QSize
            reader=QImageReader(str(target));reader.setAutoTransform(True)
            size=reader.size()
            if not size.isValid():raise ValueError('Please check your entry')
            reader.setScaledSize(size.scaled(QSize(256,256),Qt.KeepAspectRatio))
            image=reader.read()
            preview=folder/(uuid.uuid4().hex+'.png')
            if image.isNull() or not image.save(str(preview),'PNG'):raise ValueError('Please check your entry')
            with preview.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
            result.append(dict(name=source.stem+' (preview).png',stored=preview.name,sha256=digest))
        return result
    except Exception:
        target.unlink(missing_ok=True)
        raise
