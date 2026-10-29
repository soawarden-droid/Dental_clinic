"""Exact, transactional patient charges and an append-only payment ledger.

Drafts never masquerade as debt. Issuing an invoice finalizes its line snapshots.
All financial balances are read from the same SQLite view, invoice_balances.
"""
from datetime import datetime
from .domain import today,now,check_date,KABUL


def event_time():return datetime.now(KABUL).isoformat(timespec='microseconds')


def minor_units(value,positive=False):
    if type(value) is not int or value<0 or value>9223372036854775807 or (positive and value==0):
        raise ValueError('Enter a valid amount in whole minor units')
    return value


class Finance:
    def add_charge(self,visit_id,description,amount,kind='consultation'):
        minor_units(amount)
        if kind not in ('consultation','procedure','other') or not description.strip():
            raise ValueError('Enter a charge description and a valid type')
        with self.action('draft charge added',visit_id) as db:
            if not self.s.one('SELECT id FROM visits WHERE id=?',(visit_id,)):
                raise ValueError('Choose a visit first')
            return db.execute('INSERT INTO charges(visit_id,kind,description,amount,created) VALUES(?,?,?,?,?)',(visit_id,kind,description.strip(),amount,now())).lastrowid

    def update_charge(self,charge_id,description,amount,kind='consultation'):
        minor_units(amount)
        if not description.strip() or kind not in ('consultation','procedure','other'):
            raise ValueError('Enter a charge description and a valid type')
        with self.action('draft charge edited',charge_id) as db:
            if not self.s.one('SELECT id FROM charges WHERE id=?',(charge_id,)):raise ValueError('Choose a record first')
            if self.s.one('SELECT ii.id FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.charge_id=? AND i.void=0',(charge_id,)):
                raise ValueError('Finalized charges cannot be edited; void and reissue')
            db.execute('UPDATE charges SET description=?,amount=?,kind=? WHERE id=?',(description.strip(),amount,kind,charge_id))

    def update_treatment(self,treatment_id,procedure,price,tooth='',condition='',status='planned',notes=''):
        from .domain import TEETH
        minor_units(price)
        if not procedure.strip() or (tooth and tooth not in TEETH) or status not in ('planned','completed'):raise ValueError('Invalid treatment or tooth number')
        with self.action('treatment edited',treatment_id,clinical=True) as db:
            if not self.s.one('SELECT id FROM treatments WHERE id=?',(treatment_id,)):raise ValueError('Choose a record first')
            if self.s.one('SELECT ii.id FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.treatment_id=? AND i.void=0',(treatment_id,)):
                raise ValueError('Finalized treatments cannot be repriced; void and reissue')
            db.execute('UPDATE treatments SET procedure=?,price=?,tooth=?,condition=?,status=?,notes=? WHERE id=?',(procedure.strip(),price,tooth,condition,status,notes,treatment_id))

    def drafts(self,patient_id):
        self.allowed()
        return self.s.rows("""SELECT c.id,c.visit_id,v.date,c.description,c.amount,c.kind,'charge' source FROM charges c JOIN visits v ON v.id=c.visit_id
          WHERE v.patient_id=? AND NOT EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.charge_id=c.id AND i.void=0)
          UNION ALL SELECT t.id,t.visit_id,v.date,t.procedure || CASE WHEN t.tooth='' THEN '' ELSE ' · '||t.tooth END,t.price,'procedure','treatment' FROM treatments t JOIN visits v ON v.id=t.visit_id
          WHERE v.patient_id=? AND t.status='completed' AND NOT EXISTS(SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE ii.treatment_id=t.id AND i.void=0)
          ORDER BY 3,2,1""",(patient_id,patient_id))

    def invoice(self,visit_id,discount=0):
        minor_units(discount)
        with self.action('invoice issued',visit_id) as db:
            visit=self.s.one('SELECT * FROM visits WHERE id=?',(visit_id,))
            if not visit:raise ValueError('Choose a visit first')
            items=[r for r in self.drafts(visit['patient_id']) if r['visit_id']==visit_id]
            if not items:raise ValueError('No completed unbilled treatments or draft fees for this visit')
            if discount>sum(r['amount'] for r in items):raise ValueError('Discount exceeds invoice subtotal')
            iid=db.execute('INSERT INTO invoices(patient_id,visit_id,date,discount,created,finalized) VALUES(?,?,?,?,?,0)',(visit['patient_id'],visit_id,today(),discount,event_time())).lastrowid
            db.executemany('INSERT INTO invoice_items(invoice_id,treatment_id,charge_id,description,amount) VALUES(?,?,?,?,?)',[(iid,r['id'] if r['source']=='treatment' else None,r['id'] if r['source']=='charge' else None,r['description'],r['amount']) for r in items])
            db.execute('UPDATE invoices SET finalized=1 WHERE id=?',(iid,))
            return iid

    def balances(self,patient_id=None):
        self.allowed()
        return self.s.rows('SELECT b.*,p.name,p.phone FROM invoice_balances b JOIN patients p ON p.id=b.patient_id'+(' WHERE b.patient_id=?' if patient_id is not None else '')+' ORDER BY b.date DESC,b.id DESC',(patient_id,) if patient_id is not None else ())

    def invoice_totals(self,iid):
        self.allowed()
        row=self.s.one('SELECT total,paid,balance FROM invoice_balances WHERE id=?',(iid,))
        if not row:raise ValueError('Choose an invoice first')
        return row

    def account_totals(self,patient_id):
        self.allowed()
        rows=self.balances(patient_id)
        return {key:sum(r[key] for r in rows) for key in ('total','paid','balance')}

    def payment(self,iid,amount,method,reason='',reversal_of=None,request_key=None,date=None):
        if type(amount) is not int or amount==0 or abs(amount)>9223372036854775807:raise ValueError('Enter a valid amount in whole minor units')
        if not method.strip():raise ValueError('Choose a payment method')
        stamp=check_date(date or today())
        if stamp>today():raise ValueError('Payment date cannot be in the future')
        if request_key is not None and (not isinstance(request_key,str) or not request_key.strip()):raise ValueError('Invalid payment request key')
        with self.action('payment recorded' if amount>0 else 'payment refunded',iid,admin=amount<0) as db:
            if request_key:
                old=self.s.one('SELECT * FROM payments WHERE request_key=?',(request_key,))
                if old:
                    if (old['invoice_id'],old['amount'],old['method'],old['reason'],old['reversal_of'],old['date'])!=(iid,amount,method.strip(),reason.strip(),reversal_of,stamp):
                        raise ValueError('This payment request was already used with different details')
                    return old['id']
            totals=self.invoice_totals(iid);inv=self.s.one('SELECT * FROM invoices WHERE id=?',(iid,))
            if stamp<inv['date']:raise ValueError('Payment date cannot precede the invoice')
            if inv['void'] or (amount>0 and amount>totals['balance']) or (amount<0 and -amount>totals['paid']):raise ValueError('Payment exceeds balance or refund exceeds paid amount')
            if amount<0 and not reason.strip():raise ValueError('A refund reason is required')
            if reversal_of is not None:
                original=self.s.one('SELECT * FROM payments WHERE id=? AND invoice_id=?',(reversal_of,iid))
                refunded=self.s.one('SELECT COALESCE(SUM(amount),0) n FROM payments WHERE reversal_of=?',(reversal_of,))['n']
                if not original or original['amount']<=0 or amount>=0 or -amount>original['amount']+refunded:raise ValueError('Refund exceeds original payment')
            return db.execute('INSERT INTO payments(invoice_id,date,amount,method,reason,reversal_of,request_key,created) VALUES(?,?,?,?,?,?,?,?)',(iid,stamp,amount,method.strip(),reason.strip(),reversal_of,request_key,event_time())).lastrowid

    def void_invoice(self,iid,reason):
        if not reason.strip():raise ValueError('A correction reason is required')
        with self.action('invoice voided',f'{iid}: {reason}',admin=True) as db:
            row=self.s.one('SELECT * FROM invoice_balances WHERE id=?',(iid,))
            if not row:raise ValueError('Choose an invoice first')
            if row['void']:raise ValueError('This invoice is already void')
            if row['paid']:raise ValueError('Refund payments before voiding this invoice')
            db.execute('UPDATE invoices SET void=1,reason=?,voided_at=? WHERE id=?',(reason.strip(),event_time(),iid))

    def statement(self,patient_id,start=None,end=None):
        self.allowed()
        if not self.s.one('SELECT id FROM patients WHERE id=?',(patient_id,)):raise ValueError('Choose a patient first')
        if start:check_date(start)
        if end:check_date(end)
        if start and end and start>end:raise ValueError('Start date must be before end date')
        events=self.s.rows("""SELECT date,0 rank,id,'visit' kind,'Visit' description,0 charge,0 payment,NULL invoice_id,id visit_id,'' status,created at FROM visits WHERE patient_id=?
        UNION ALL SELECT i.date,1,ii.id,'charge',ii.description,ii.amount,0,i.id,i.visit_id,CASE WHEN i.void THEN 'void' ELSE '' END,i.created FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE i.patient_id=?
        UNION ALL SELECT i.date,2,i.id,'discount','Discount',-i.discount,0,i.id,i.visit_id,CASE WHEN i.void THEN 'void' ELSE '' END,i.created FROM invoices i WHERE i.patient_id=? AND i.discount<>0
        UNION ALL SELECT p.date,3,p.id,CASE WHEN p.amount<0 THEN 'refund' ELSE 'payment' END,p.method||CASE WHEN p.reason='' THEN '' ELSE ' · '||p.reason END,0,p.amount,p.invoice_id,i.visit_id,'',p.created FROM payments p JOIN invoices i ON i.id=p.invoice_id WHERE i.patient_id=?
        UNION ALL SELECT substr(COALESCE(i.voided_at,(SELECT MAX(date) FROM payments WHERE invoice_id=i.id)||'T23:59:59',i.date||'T23:59:59'),1,10),4,i.id,'void',i.reason,-(COALESCE((SELECT SUM(amount) FROM invoice_items WHERE invoice_id=i.id),0)-i.discount),0,i.id,i.visit_id,'void',COALESCE(i.voided_at,(SELECT MAX(date) FROM payments WHERE invoice_id=i.id)||'T23:59:59',i.date||'T23:59:59') FROM invoices i WHERE i.patient_id=? AND i.void=1
        ORDER BY 1,11,2,3""",(patient_id,)*5)
        running=opening=0;visible=[]
        for row in events:
            running+=row['charge']-row['payment'];row['balance']=running
            if start and row['date']<start:opening=running;continue
            if end and row['date']>end:continue
            visible.append(row)
        return dict(opening=opening,events=visible,totals=self.account_totals(patient_id),start=start,end=end)
