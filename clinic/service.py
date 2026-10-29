"""Business operations. All mutations pass through permissions and transactions."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timedelta
from .domain import now, today, password_hash, password_verify, check_date, phone_normalize, TEETH


from .finance import Finance,minor_units,event_time


class Service(Finance):
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
            if not self.s.db.in_transaction:self.s.db.execute('BEGIN IMMEDIATE')
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
        import re
        phone_term=term.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
        phone_term=re.sub(r'[\s()\-.]','',phone_term)
        if re.fullmatch(r'\+?\d+',phone_term or ' '):
            if phone_term.startswith('00'):phone_term='+'+phone_term[2:]
            elif phone_term.startswith('0'):phone_term='+93'+phone_term[1:]
            elif phone_term.startswith('93'):phone_term='+'+phone_term
            phone_pattern=phone_term+'%'
        else:phone_pattern=pattern
        return self.s.rows("SELECT * FROM patients WHERE archived=? AND (name LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\' OR id=?) ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", (int(archived), pattern, phone_pattern, number, limit, offset))

    def save_patient(self, values, patient_id=None):
        self.allowed()
        provided=dict(values)
        old=self.s.one('SELECT * FROM patients WHERE id=?',(patient_id,)) if patient_id else None
        if patient_id and not old:raise ValueError('Choose a record first')
        values=dict(old or {});values.update(provided)
        values['name']=(values.get('name') or '').strip()
        if not values['name']:raise ValueError('Full name is required')
        raw_phone=(values.get('phone') or '').strip()
        # Legacy missing phones are preserved for unrelated section edits.
        if not raw_phone and (not old or 'phone' in provided):raise ValueError('Phone number is required')
        values['phone']=phone_normalize(raw_phone) if raw_phone else old['phone']
        optional=['father','address','dob','estimated_age','gender','email','history','allergies','medications','alerts','emergency','consent']
        for key in optional:
            value=values.get(key)
            values[key]=str(value).strip() or None if value is not None else None
        if values['dob']:
            check_date(values['dob'])
            if values['dob']>today():raise ValueError('Birth date cannot be in the future')
        if values['estimated_age'] is not None:
            if not values['estimated_age'].isdigit() or not 0<=int(values['estimated_age'])<=130:
                raise ValueError('Estimated age must be between 0 and 130')
        protected=('history','allergies','medications','alerts','consent')
        if self.user['role']!='admin' and any(values[k]!=(old.get(k) if old else None) for k in protected):
            raise PermissionError('Administrator access required')
        keys=['name','phone']+optional
        data=[values[k] for k in keys]
        with self.action('patient saved',patient_id or values['name']) as db:
            if patient_id:
                db.execute('UPDATE patients SET '+','.join(k+'=?' for k in keys)+' WHERE id=?',data+[patient_id])
            else:
                patient_id=db.execute('INSERT INTO patients('+','.join(keys)+',created) VALUES('+','.join('?' for _ in range(len(keys)+1))+')',data+[now()]).lastrowid
        return patient_id

    def duplicates(self, name, phone, exclude=0):
        return self.s.rows('SELECT id,name,phone FROM patients WHERE id<>? AND (lower(name)=lower(?) OR (phone<>\'\' AND phone=?))', (exclude, name.strip(), phone_normalize(phone)))

    def archive(self, pid, value):
        if not self.s.one('SELECT id FROM patients WHERE id=?',(pid,)):raise ValueError('Choose a patient first')
        with self.action('patient archive status', f'{pid}: {value}', admin=True) as db:
            db.execute('UPDATE patients SET archived=? WHERE id=?', (int(value), pid))

    def visit(self, pid, doctor, notes='', followup='', date=None):
        check_date(followup, True)
        check_date(date or today())
        if not doctor.strip():raise ValueError('Please check your entry')
        self.allowed()
        if self.user['role']!='admin' and (notes.strip() or followup):raise PermissionError('Administrator access required')
        with self.action('visit created', pid) as db:
            return db.execute('INSERT INTO visits(patient_id,date,doctor,notes,followup,created) VALUES(?,?,?,?,?,?)', (pid,date or today(),doctor,notes,followup,event_time())).lastrowid

    def treatment(self, visit_id, procedure, price, tooth='', condition='', status='planned', notes=''):
        minor_units(price)
        if not procedure.strip() or (tooth and tooth not in TEETH) or status not in ('planned','completed'):
            raise ValueError('Invalid treatment or tooth number')
        with self.action('treatment recorded', visit_id, clinical=True) as db:
            return db.execute('INSERT INTO treatments(visit_id,procedure,price,tooth,condition,status,notes) VALUES(?,?,?,?,?,?,?)', (visit_id,procedure,price,tooth,condition,status,notes)).lastrowid

    def complete(self, treatment_id):
        if not self.s.one('SELECT id FROM treatments WHERE id=?',(treatment_id,)):raise ValueError('Choose a treatment first')
        with self.action('treatment completed', treatment_id, clinical=True) as db:
            db.execute("UPDATE treatments SET status='completed' WHERE id=?", (treatment_id,))

    def appointment(self, pid, starts, minutes, status='scheduled', notes='', override=False):
        start = datetime.fromisoformat(starts)
        if type(minutes) is not int or not 5 <= minutes <= 480:
            raise ValueError('Duration must be 5 to 480 minutes')
        end = start+timedelta(minutes=minutes)
        conflicts = self.s.rows("SELECT * FROM appointments WHERE status NOT IN ('cancelled','missed') AND starts<? AND datetime(starts,'+'||minutes||' minutes')>datetime(?)", (end.isoformat(timespec='minutes'),start.isoformat(timespec='minutes')))
        if conflicts and not override:
            raise ValueError('Appointment time conflicts with another appointment')
        with self.action('appointment created', pid) as db:
            return db.execute('INSERT INTO appointments(patient_id,starts,minutes,status,notes) VALUES(?,?,?,?,?)', (pid,start.isoformat(timespec='minutes'),minutes,status,notes)).lastrowid

    def status(self, aid, status):
        if not self.s.one('SELECT id FROM appointments WHERE id=?',(aid,)):raise ValueError('Choose an appointment first')
        with self.action('appointment status', f'{aid}: {status}') as db:
            db.execute('UPDATE appointments SET status=? WHERE id=?', (status,aid))

    def add_record(self, table, values, clinical=False):
        permitted = {'catalogue','materials','suppliers','expenses','labs','prescriptions'}
        if table not in permitted:
            raise ValueError('Unsupported record')
        allowed_cols = {r['name'] for r in self.s.rows('PRAGMA table_info('+table+')')}-{'id'}
        if not set(values)<=allowed_cols:
            raise ValueError('Unsupported field')
        if table=='catalogue':minor_units(values.get('price',0))
        elif table=='expenses':
            minor_units(values.get('amount'),True);check_date(values.get('date'));
            if not values.get('category','').strip():raise ValueError('Please check your entry')
        elif table=='labs':
            minor_units(values.get('cost'));minor_units(values.get('paid'));check_date(values.get('sent'));check_date(values.get('expected'))
            if values.get('treatment_id') and not self.s.one('SELECT t.id FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE t.id=? AND v.patient_id=?',(values['treatment_id'],values['patient_id'])):raise ValueError('Choose a treatment for this patient')
        if table=='prescriptions':clinical=True
        with self.action(table+' added', '', clinical=clinical, admin=table in {'catalogue','materials','suppliers','expenses','labs'}) as db:
            rid = db.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')', list(values.values())).lastrowid
            if table=='labs' and values.get('paid',0)>0:
                db.execute('INSERT INTO lab_payments(lab_id,date,amount) VALUES(?,?,?)', (rid,values['sent'],values['paid']))
            return rid

    def stock_quantity(self, mid):
        return self.s.one('SELECT COALESCE(SUM(quantity),0) n FROM stock WHERE material_id=?', (mid,))['n']

    def stock(self, mid, quantity, kind, reason='', batch='', expiry='', treatment_id=None):
        check_date(expiry, True)
        if type(quantity) is not int:raise ValueError('Quantity must be a whole number')
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
        minor_units(paid)
        for item in items:
            if type(item['quantity']) is not int or item['quantity']<=0:raise ValueError('Quantity must be a positive whole number')
            minor_units(item['unit_cost'])
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
        billed = self.s.one('SELECT COALESCE(SUM(total),0) n FROM invoice_balances WHERE date BETWEEN ? AND ?',(start,end))['n']
        purchases = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM supplier_payments WHERE date BETWEEN ? AND ?', (start,end))['n']
        lab = self.s.one('SELECT COALESCE(SUM(amount),0) n FROM lab_payments WHERE date BETWEEN ? AND ?', (start,end))['n']
        outstanding = self.s.one('SELECT COALESCE(SUM(balance),0) n FROM invoice_balances')['n']
        return dict(billed=billed,collected=collected,expenses=expenses,purchases=purchases,lab=lab,outstanding=outstanding,cash_surplus=collected-expenses-purchases-lab)


    def supplier_payment(self, purchase_id, amount):
        minor_units(amount,True)
        with self.action('supplier payment', purchase_id, admin=True) as db:
            r = self.s.one('SELECT p.paid,COALESCE(SUM(i.quantity*i.unit_cost),0) total FROM purchases p JOIN purchase_items i ON i.purchase_id=p.id WHERE p.id=? GROUP BY p.id',(purchase_id,))
            if not r or amount<=0 or amount>r['total']-r['paid']:
                raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            db.execute('INSERT INTO supplier_payments(purchase_id,date,amount) VALUES(?,?,?)',(purchase_id,today(),amount))
            db.execute('UPDATE purchases SET paid=paid+? WHERE id=?',(amount,purchase_id))

    def update_lab(self, lid, status, returned, paid):
        minor_units(paid)
        check_date(returned,True)
        with self.action('lab updated',lid,admin=True) as db:
            r=self.s.one('SELECT * FROM labs WHERE id=?',(lid,))
            if not r or not r['paid']<=paid<=r['cost']:
                raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            if paid>r['paid']:
                db.execute('INSERT INTO lab_payments(lab_id,date,amount) VALUES(?,?,?)',(lid,today(),paid-r['paid']))
            db.execute('UPDATE labs SET status=?,returned=?,paid=? WHERE id=?',(status,returned,paid,lid))

    def record_attachments(self,records,pid=None):
        with self.action('attachments added',len(records),clinical=pid is not None,admin=pid is None) as db:
            return [db.execute('INSERT INTO attachments(patient_id,scope,name,stored,sha256) VALUES(?,?,?,?,?)',(pid,'patient' if pid else 'profile',r['name'],r['stored'],r['sha256'])).lastrowid for r in records]

    def record_attachment(self, meta, pid=None):
        with self.action('attachment added',meta['name'],clinical=pid is not None,admin=pid is None) as db:
            return db.execute('INSERT INTO attachments(patient_id,scope,name,stored,sha256) VALUES(?,?,?,?,?)', (pid,'patient' if pid else 'profile',meta['name'],meta['stored'],meta['sha256'])).lastrowid


    def dashboard(self, days=30):
        self.allowed()
        if days not in (7,30,90):raise ValueError('Please check your entry')
        from datetime import date
        end=today();start=(date.fromisoformat(end)-timedelta(days=days-1)).isoformat()
        next_week=(date.fromisoformat(end)+timedelta(days=7)).isoformat()
        appointments=self.s.rows('SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE substr(a.starts,1,10)=? ORDER BY a.starts',(end,))
        visits=self.s.rows('SELECT v.*,p.name FROM visits v JOIN patients p ON p.id=v.patient_id WHERE v.date=? ORDER BY v.id DESC',(end,))
        upcoming=self.s.rows("SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE a.starts>=? AND substr(a.starts,1,10)<=? AND a.status IN ('scheduled','arrived','in treatment') ORDER BY a.starts",(now()[:16],next_week))
        ledger=self.s.rows('SELECT pay.*,i.patient_id,p.name FROM payments pay JOIN invoices i ON i.id=pay.invoice_id JOIN patients p ON p.id=i.patient_id WHERE pay.date BETWEEN ? AND ? ORDER BY pay.date,pay.id',(start,end))
        by_date={}
        for row in ledger:by_date[row['date']]=by_date.get(row['date'],0)+row['amount']
        trend=[{'date':(date.fromisoformat(start)+timedelta(days=n)).isoformat(),'amount':by_date.get((date.fromisoformat(start)+timedelta(days=n)).isoformat(),0)} for n in range(days)]
        distribution=self.s.rows("SELECT t.procedure,COUNT(*) count FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE v.date BETWEEN ? AND ? AND t.status='completed' GROUP BY t.procedure ORDER BY count DESC,t.procedure",(start,end))
        statuses=self.s.rows('SELECT status,COUNT(*) count FROM appointments WHERE substr(starts,1,10) BETWEEN ? AND ? GROUP BY status ORDER BY count DESC,status',(start,end))
        balances=self.balances()
        billed_today=self.s.one('SELECT COALESCE(SUM(total),0) n FROM invoice_balances WHERE date=?',(end,))['n']
        billed=self.s.rows('SELECT b.*,p.name FROM invoice_balances b JOIN patients p ON p.id=b.patient_id WHERE b.date BETWEEN ? AND ? AND b.void=0 ORDER BY b.date,b.id',(start,end))
        recent_visits=self.s.rows('SELECT v.id,v.patient_id,v.date,p.name FROM visits v JOIN patients p ON p.id=v.patient_id ORDER BY v.date DESC,v.id DESC LIMIT 6')
        recent_payments=self.s.rows('SELECT pay.*,i.patient_id,p.name FROM payments pay JOIN invoices i ON i.id=pay.invoice_id JOIN patients p ON p.id=i.patient_id ORDER BY pay.date DESC,pay.id DESC LIMIT 6')
        low_stock=self.s.rows('SELECT m.*,COALESCE(SUM(s.quantity),0) quantity FROM materials m LEFT JOIN stock s ON s.material_id=m.id GROUP BY m.id HAVING quantity<=minimum ORDER BY m.name')
        followups=self.s.rows('SELECT v.*,p.name FROM visits v JOIN patients p ON p.id=v.patient_id WHERE v.followup>=? ORDER BY v.followup,v.id LIMIT 8',(end,))
        return dict(start=start,end=end,seen_today=len({r['patient_id'] for r in visits}),billed_today=billed_today,billed=billed,recent_visits=recent_visits,recent_payments=recent_payments,visits=visits,appointments=appointments,upcoming=upcoming,ledger=ledger,trend=trend,distribution=distribution,statuses=statuses,balances=balances,collected_today=sum(r['amount'] for r in ledger if r['date']==end),outstanding=sum(r['balance'] for r in balances),recent_patients=self.s.rows('SELECT * FROM patients WHERE archived=0 ORDER BY created DESC,id DESC LIMIT 6'),low_stock=low_stock,followups=followups)


    def image_permission(self,slot):
        import re
        if slot in ('profile_photo','clinic_logo','clinic_background') or re.fullmatch(r'gallery_[a-f0-9]+',slot):self.allowed(admin=True);return None
        match=re.fullmatch(r'patient_photo_([0-9]+)',slot)
        if not match:raise ValueError('Unsupported image setting')
        self.allowed(clinical=True)
        pid=int(match.group(1))
        if not self.s.one('SELECT id FROM patients WHERE id=?',(pid,)):raise ValueError('Choose a record first')
        return pid

    def replace_image(self,slot,records):
        pid=self.image_permission(slot)
        if not records:raise ValueError('Please check your entry')
        old=self.s.one('SELECT * FROM image_assets WHERE slot=?',(slot,))
        with self.action('image replaced',slot,clinical=pid is not None,admin=pid is None) as db:
            ids=[]
            for meta in records:
                if Path(meta['stored']).name!=meta['stored']:raise ValueError('Invalid attachment path')
                ids.append(db.execute('INSERT INTO attachments(patient_id,scope,name,stored,sha256,image_owned) VALUES(?,?,?,?,?,1)',(pid,'patient' if pid else 'profile',meta['name'],meta['stored'],meta['sha256'])).lastrowid)
            db.execute('INSERT INTO image_assets VALUES(?,?,?) ON CONFLICT(slot) DO UPDATE SET original_id=excluded.original_id,preview_id=excluded.preview_id',(slot,ids[0],ids[-1]))
            db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(slot,records[-1]['stored']))
        if old:self._collect_image_copies({old['original_id'],old['preview_id']})
        return ids

    def remove_image(self,slot):
        pid=self.image_permission(slot)
        old=self.s.one('SELECT * FROM image_assets WHERE slot=?',(slot,))
        with self.action('image removed',slot,clinical=pid is not None,admin=pid is None) as db:
            db.execute('DELETE FROM image_assets WHERE slot=?',(slot,));db.execute('DELETE FROM settings WHERE key=?',(slot,))
        if old:self._collect_image_copies({old['original_id'],old['preview_id']})

    def _collect_image_copies(self,ids):
        for aid in ids:
            row=self.s.one('SELECT * FROM attachments WHERE id=?',(aid,))
            if not row or not row['image_owned']:continue
            if self.s.one('SELECT slot FROM image_assets WHERE original_id=? OR preview_id=?',(aid,aid)):continue
            if self.s.one('SELECT key FROM settings WHERE value=?',(row['stored'],)):continue
            with self.s.db:self.s.db.execute('DELETE FROM attachments WHERE id=?',(aid,))
            if Path(row['stored']).name==row['stored']:
                try:(self.s.root/'attachments'/row['stored']).unlink(missing_ok=True)
                except OSError:
                    import logging
                    logging.warning('An unused managed image could not yet be removed')

    def remove_attachment(self,aid):
        row=self.s.one('SELECT * FROM attachments WHERE id=?',(aid,))
        if not row:raise ValueError('Choose a record first')
        self.allowed(clinical=row['patient_id'] is not None,admin=row['patient_id'] is None)
        if self.s.one('SELECT slot FROM image_assets WHERE original_id=? OR preview_id=?',(aid,aid)) or self.s.one('SELECT key FROM settings WHERE value=?',(row['stored'],)):
            raise ValueError('This image is still in use. Remove its setting first.')
        with self.action('attachment removed',aid,clinical=row['patient_id'] is not None,admin=row['patient_id'] is None) as db:db.execute('DELETE FROM attachments WHERE id=?',(aid,))
        if Path(row['stored']).name==row['stored']:(self.s.root/'attachments'/row['stored']).unlink(missing_ok=True)


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
