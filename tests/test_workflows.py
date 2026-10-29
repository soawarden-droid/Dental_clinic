import sqlite3
from pathlib import Path
import zipfile
import pytest
from clinic.storage import Store
from clinic.service import Service
from clinic.domain import today
from clinic.backup import create_backup,validate_backup,restore_backup


@pytest.fixture
def svc(tmp_path):
    s=Store(tmp_path/'profile');v=Service(s);v.register('doctor','a-long-test-password');v.login('doctor','a-long-test-password');yield v
    v.s.db.close()


def patient(svc):return svc.save_patient({'name':'Fictional Test Child','estimated_age':'0','phone':'0701234567'})

def bill(svc):
    pid=patient(svc);vid=svc.visit(pid,'Test doctor','Record only')
    tid=svc.treatment(vid,'Filling',100029,'11',status='completed')
    svc.treatment(vid,'Planned crown',500000,'21',status='planned')
    return pid,vid,tid,svc.invoice(vid,29)


def test_patient_visit_invoice_partial_refund(svc):
    pid,vid,tid,iid=bill(svc)
    assert svc.invoice_totals(iid)==dict(total=100000,paid=0,balance=100000)
    receipt=svc.payment(iid,40000,'Cash')
    assert svc.invoice_totals(iid)['balance']==60000
    with pytest.raises(ValueError):svc.payment(iid,60001,'Cash')
    with pytest.raises(ValueError):svc.payment(iid,-40001,'Cash','refund')
    with pytest.raises(ValueError):svc.payment(iid,-100,'Cash')
    svc.payment(iid,-10000,'Cash','Correction',receipt)
    with pytest.raises(ValueError):svc.payment(iid,-30001,'Cash','Correction',receipt)
    assert svc.invoice_totals(iid)['paid']==30000
    with pytest.raises(ValueError):svc.invoice(vid)
    assert len(svc.s.rows('SELECT * FROM invoices'))==1
    assert len(svc.s.rows('SELECT * FROM invoice_items'))==1
    with pytest.raises(ValueError):svc.void_invoice(iid,'Wrong invoice')
    svc.payment(iid,-30000,'Cash','Full refund')
    svc.void_invoice(iid,'Wrong invoice')
    assert svc.invoice_totals(iid)==dict(total=0,paid=0,balance=0)
    assert len(svc.s.rows('SELECT * FROM audit'))>=8


def test_stock_purchase_atomicity_duplicate_deduction(svc):
    pid,vid,tid,iid=bill(svc)
    mid=svc.add_record('materials',dict(name='Material',unit='unit',minimum=2))
    sid=svc.add_record('suppliers',dict(name='Supplier'))
    purchase=svc.purchase(sid,[dict(material_id=mid,quantity=10,unit_cost=200,batch='B1',expiry='2030-01-01')],1500)
    assert svc.stock_quantity(mid)==10
    svc.stock(mid,-2,'use','Confirmed use','B1','2030-01-01',tid)
    assert svc.stock_quantity(mid)==8
    with pytest.raises(ValueError):svc.stock(mid,-2,'use','Double click','B1','2030-01-01',tid)
    assert svc.stock_quantity(mid)==8
    with pytest.raises(ValueError):svc.stock(mid,-9,'wastage','Too much')
    assert svc.stock_quantity(mid)==8
    with pytest.raises(sqlite3.IntegrityError):svc.purchase(sid,[dict(material_id=mid,quantity=2,unit_cost=200),dict(material_id=999,quantity=1,unit_cost=200)],0)
    assert len(svc.s.rows('SELECT * FROM purchases'))==1
    assert svc.stock_quantity(mid)==8
    assert svc.report(today(),today())['purchases']==1500


def test_appointment_conflict_and_status(svc):
    pid=patient(svc)
    a=svc.appointment(pid,today()+'T09:00',30)
    with pytest.raises(ValueError):svc.appointment(pid,today()+'T09:29',30)
    svc.appointment(pid,today()+'T09:30',30)
    svc.status(a,'cancelled');svc.appointment(pid,today()+'T09:00',30)
    with pytest.raises(sqlite3.IntegrityError):svc.status(a,'invalid')


def test_permissions_and_archive(svc):
    pid,vid,tid,iid=bill(svc)
    svc.register('reception','reception-password','receptionist');svc.login('reception','reception-password')
    svc.payment(iid,10000,'Cash')
    for fn in [lambda:svc.visit(pid,'doctor'),lambda:svc.stock(1,-1,'use','x'),lambda:svc.archive(pid,True),lambda:svc.payment(iid,-10,'Cash','x'),lambda:svc.report(today(),today()),lambda:svc.add_record('materials',{'name':'bad','unit':'x'})]:
        with pytest.raises(PermissionError):fn()
    svc.login('doctor','a-long-test-password');svc.archive(pid,True)
    assert not svc.search()
    assert svc.search(archived=True)[0]['id']==pid
    svc.archive(pid,False);assert svc.search('P-000001')[0]['id']==pid


def test_migration_restart_and_foreign_keys(svc):
    pid,vid,tid,iid=bill(svc)
    root=svc.s.root;svc.s.db.close();svc.s=Store(root);svc.s.migrate();svc.s.migrate()
    assert svc.s.one('SELECT name FROM patients WHERE id=?',(pid,))['name']=='Fictional Test Child'
    assert svc.s.db.execute('PRAGMA foreign_keys').fetchone()[0]==1
    assert svc.s.db.execute('PRAGMA user_version').fetchone()[0]==4
    with pytest.raises(sqlite3.IntegrityError):
        with svc.s.db:svc.s.db.execute('DELETE FROM patients WHERE id=?',(pid,))


def test_backup_restore_fresh_profile(svc,tmp_path):
    pid,vid,tid,iid=bill(svc);svc.payment(iid,40000,'Cash');svc.s.set_setting('language','fa_AF')
    source=tmp_path/'test.txt';source.write_text('Fictional patient attachment');svc.attach(source,pid)
    svc.attach(source)
    backup=create_backup(svc.s.root,tmp_path/'usb')
    fresh=Store(tmp_path/'fresh');Service(fresh)
    safety=restore_backup(fresh,backup)
    assert safety.exists()
    restored=Store(tmp_path/'fresh');restored_service=Service(restored);restored_service.login('doctor','a-long-test-password')
    assert restored_service.invoice_totals(iid)==dict(total=100000,paid=40000,balance=60000)
    assert restored.setting('language')=='fa_AF'
    for r in restored.rows('SELECT * FROM attachments'):
        assert (restored.root/'attachments'/r['stored']).read_text()=='Fictional patient attachment'
    restored.db.close()
    broken=tmp_path/'broken.fdbackup'
    with zipfile.ZipFile(backup) as z,zipfile.ZipFile(broken,'w') as b:
        for n in z.namelist():b.writestr(n,b'broken' if n=='clinic.sqlite' else z.read(n))
    with pytest.raises(ValueError):validate_backup(broken,tmp_path/'bad')
    assert svc.invoice_totals(iid)['paid']==40000


def test_report_reconciles(svc):
    _,_,_,iid=bill(svc);svc.payment(iid,80000,'Cash');svc.payment(iid,-10000,'Cash','Correction')
    svc.add_record('expenses',dict(date=today(),category='Rent',amount=20000,notes='Test'))
    r=svc.report(today(),today())
    assert r['billed']==100000 and r['collected']==70000 and r['outstanding']==30000
    assert r['expenses']==20000 and r['cash_surplus']==50000


def test_later_supplier_and_lab_payments(svc):
    pid=patient(svc)
    mid=svc.add_record('materials',dict(name='Material',unit='unit',minimum=0));sid=svc.add_record('suppliers',dict(name='Supplier'))
    purchase=svc.purchase(sid,[dict(material_id=mid,quantity=3,unit_cost=1000)],500)
    svc.supplier_payment(purchase,1000)
    with pytest.raises(ValueError):svc.supplier_payment(purchase,1501)
    lid=svc.add_record('labs',dict(patient_id=pid,laboratory='Test lab',description='Test',sent=today(),expected=today(),status='sent',cost=5000,paid=500))
    svc.update_lab(lid,'returned',today(),1500)
    with pytest.raises(ValueError):svc.update_lab(lid,'returned',today(),1499)
    assert svc.report(today(),today())['lab']==1500
    assert svc.report(today(),today())['purchases']==1500


def test_void_can_be_corrected_without_duplicate_active_billing(svc):
    _,vid,_,iid=bill(svc);svc.void_invoice(iid,'Discount entered incorrectly')
    corrected=svc.invoice(vid,100)
    assert svc.invoice_totals(corrected)['total']==99929
    with pytest.raises(ValueError):svc.invoice(vid)


def test_backup_path_traversal(svc,tmp_path):
    archive=tmp_path/'unsafe.fdbackup'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','x')
    with pytest.raises(ValueError):validate_backup(archive,tmp_path/'stage')
    assert not (tmp_path/'outside').exists()


def test_interrupted_restore_recovers_original_profile(svc):
    pid=patient(svc);root=svc.s.root;svc.s.db.close()
    root.rename(root.with_name(root.name+'-restore-old'))
    svc.s=Store(root)
    assert svc.s.one('SELECT name FROM patients WHERE id=?',(pid,))['name']=='Fictional Test Child'


def test_one_treatment_can_consume_multiple_materials_once(svc):
    _,_,tid,_=bill(svc)
    mids=[svc.add_record('materials',dict(name=name,unit='unit',minimum=0)) for name in ('A','B')]
    for mid in mids:
        svc.stock(mid,10,'adjustment','Opening inventory')
        svc.stock(mid,-1,'use','Confirmed treatment use',treatment_id=tid)
        assert svc.stock_quantity(mid)==9
    with pytest.raises(ValueError):svc.stock(mids[0],-1,'use','Duplicate',treatment_id=tid)
