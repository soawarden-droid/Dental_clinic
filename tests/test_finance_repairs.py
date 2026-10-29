"""Regressions from reception's fee → unpaid bill → installments workflow."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from clinic.service import Service
from clinic.storage import Store
from clinic.domain import today,password_verify
from clinic.schema import MIGRATIONS
from clinic.backup import create_backup,restore_backup


def account(root):
    svc=Service(Store(root));svc.register('doctor','long-test-password');svc.login('doctor','long-test-password');return svc


def fixture_bill(root):
    svc=account(root);pid=svc.save_patient(dict(name='Fictional patient',phone='070 123 4567'));vid=svc.visit(pid,'Doctor')
    fee=svc.add_charge(vid,'Doctor consultation fee',50000)
    treatment=svc.treatment(vid,'Filling',200000,'26',status='completed')
    assert svc.account_totals(pid)==dict(total=0,paid=0,balance=0)  # draft, never fake debt
    iid=svc.invoice(vid)
    return svc,pid,vid,fee,treatment,iid


def test_full_two_visit_installments_restart_statement_dashboard_and_backup(tmp_path):
    svc,pid,vid,fee,treatment,iid=fixture_bill(tmp_path/'profile')
    assert svc.invoice_totals(iid)==dict(total=250000,paid=0,balance=250000)
    assert svc.balances(pid)[0]['status']=='unpaid'
    first=svc.payment(iid,100000,'Cash',request_key='first')
    assert svc.balances(pid)[0]['status']=='partial'
    assert svc.account_totals(pid)['balance']==150000
    root=svc.s.root;svc.s.db.close();svc=Service(Store(root));svc.login('doctor','long-test-password')
    assert svc.invoice_totals(iid)==dict(total=250000,paid=100000,balance=150000)
    svc.visit(pid,'Doctor','Later visit');second=svc.payment(iid,150000,'Cash',request_key='later')
    assert second!=first and svc.balances(pid)[0]['status']=='paid'
    assert svc.account_totals(pid)==dict(total=250000,paid=250000,balance=0)
    events=svc.statement(pid)['events'];assert len([r for r in events if r['kind']=='charge'])==2
    assert [r['payment'] for r in events if r['kind']=='payment']==[100000,150000]
    assert events[-1]['balance']==0
    d=svc.dashboard(7);assert d['billed_today']==d['collected_today']==250000 and d['outstanding']==0 and d['seen_today']==1
    assert svc.report(today(),today())['billed']==svc.report(today(),today())['collected']==250000
    archive=create_backup(root,tmp_path/'backups');target=Store(tmp_path/'restored');Service(target);restore_backup(target,archive)
    restored=Service(Store(tmp_path/'restored'));restored.login('doctor','long-test-password')
    assert restored.account_totals(pid)==dict(total=250000,paid=250000,balance=0)
    assert len(restored.statement(pid)['events'])==len(events)
    restored.s.db.close();svc.s.db.close()


def test_retry_same_payment_key_is_idempotent_even_after_restart(tmp_path):
    svc,pid,_,_,_,iid=fixture_bill(tmp_path/'profile')
    receipt=svc.payment(iid,100000,'Cash',request_key='same-intent')
    assert svc.payment(iid,100000,'Cash',request_key='same-intent')==receipt
    root=svc.s.root;svc.s.db.close();svc=Service(Store(root));svc.login('doctor','long-test-password')
    assert svc.payment(iid,100000,'Cash',request_key='same-intent')==receipt
    assert len(svc.s.rows('SELECT * FROM payments'))==1
    with pytest.raises(ValueError):svc.payment(iid,1,'Cash',request_key='same-intent')
    assert svc.invoice_totals(iid)['paid']==100000
    svc.s.db.close()


def test_concurrent_payment_requests_cannot_overpay(tmp_path):
    svc,_,_,_,_,iid=fixture_bill(tmp_path/'profile');root=svc.s.root;svc.s.db.close()
    def pay(key):
        s=Service(Store(root));s.login('doctor','long-test-password')
        try:return s.payment(iid,150000,'Cash',request_key=key)
        except ValueError:return 'rejected'
        finally:s.s.db.close()
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(pay,['a','b']))
    assert results.count('rejected')==1
    s=Service(Store(root));s.login('doctor','long-test-password');assert s.invoice_totals(iid)['paid']==150000;s.s.db.close()


def test_invalid_writes_roll_back_no_partial_invoices_or_payments(tmp_path):
    svc,pid,vid,_,_,iid=fixture_bill(tmp_path/'profile')
    for amount in (0,True,1.5,300000,-1):
        with pytest.raises(ValueError):svc.payment(iid,amount,'Cash')
    with pytest.raises(ValueError):svc.add_charge(vid,'Bad',2.5)
    with pytest.raises(ValueError):svc.add_charge(vid,' ',50000)
    with pytest.raises(ValueError):svc.treatment(vid,'Bad',12.5)
    new=svc.add_charge(vid,'Second bill',10000)
    with pytest.raises(ValueError):svc.invoice(vid,10001)
    assert len(svc.s.rows('SELECT * FROM invoices'))==1
    assert len(svc.s.rows('SELECT * FROM invoice_items'))==2
    assert svc.s.rows('SELECT * FROM payments')==[]
    assert svc.drafts(pid)[0]['id']==new
    with pytest.raises(sqlite3.IntegrityError):
        with svc.s.db:svc.s.db.execute('INSERT INTO payments(invoice_id,date,amount,method) VALUES(?,?,?,?)',(iid,today(),1.5,'Cash'))
    svc.s.db.close()


def test_edit_drafts_then_traceable_refund_void_reissue(tmp_path):
    svc,pid,vid,fee,tid,iid=fixture_bill(tmp_path/'profile')
    with pytest.raises(ValueError):svc.update_charge(fee,'Wrong',70000)
    with pytest.raises(ValueError):svc.update_treatment(tid,'Filling',1)
    receipt=svc.payment(iid,100000,'Cash')
    with pytest.raises(ValueError):svc.void_invoice(iid,'Correction')
    svc.payment(iid,-100000,'Cash','Original wrong',reversal_of=receipt)
    svc.void_invoice(iid,'Correct fee')
    svc.update_charge(fee,'Doctor consultation fee',40000)
    svc.update_treatment(tid,'Filling',190000,'26',status='completed')
    new=svc.invoice(vid,10000)
    assert svc.invoice_totals(new)==dict(total=220000,paid=0,balance=220000)
    assert svc.balances(pid)[1]['status']=='void'
    statement=svc.statement(pid);assert statement['totals']['balance']==220000 and statement['events'][-1]['balance']==220000
    assert any(r['kind']=='void' for r in statement['events'])
    assert all(r['balance']>=0 for r in statement['events'])
    assert svc.dashboard(7)['billed_today']==220000 and svc.dashboard(7)['collected_today']==0
    for sql,args in [('DELETE FROM patients WHERE id=?',(pid,)),('DELETE FROM payments WHERE id=?',(receipt,)),('UPDATE invoice_items SET amount=0 WHERE invoice_id=?',(new,)),('INSERT INTO invoice_items(invoice_id,description,amount) VALUES(?,\'Unapproved extra\',100)',(new,))]:
        with pytest.raises(sqlite3.IntegrityError):
            with svc.s.db:svc.s.db.execute(sql,args)
    svc.s.db.close()


def test_reception_can_create_visits_charge_and_collect_without_clinical_access(tmp_path):
    svc=account(tmp_path/'profile');svc.register('reception','long-reception-password','receptionist');svc.login('reception','long-reception-password')
    pid=svc.save_patient(dict(name='Reception patient',phone='0701234567'));vid=svc.visit(pid,'Doctor')
    svc.add_charge(vid,'Consultation',50000);svc.add_charge(vid,'Recorded treatment charge',200000,'procedure');iid=svc.invoice(vid)
    svc.payment(iid,100000,'Cash');assert svc.account_totals(pid)['balance']==150000
    with pytest.raises(PermissionError):svc.visit(pid,'Doctor','Private note')
    with pytest.raises(PermissionError):svc.treatment(vid,'Filling',100)
    with pytest.raises(PermissionError):svc.void_invoice(iid,'x')
    svc.s.db.close()


def test_upgrade_v4_finances_and_attachments_backup_before_migration(tmp_path):
    root=tmp_path/'legacy';store=Store(root)
    for i,sql in enumerate(MIGRATIONS[:4],1):store.db.executescript('BEGIN;'+sql+f'PRAGMA user_version={i};COMMIT;')
    with store.db:
        store.db.execute("INSERT INTO patients(id,name,phone,created) VALUES(41,'Legacy','0701234567','2020-01-01')")
        store.db.execute("INSERT INTO visits(id,patient_id,date,doctor) VALUES(12,41,'2020-01-01','Doctor')")
        store.db.execute("INSERT INTO invoices(id,patient_id,visit_id,date) VALUES(7,41,12,'2020-01-01')")
        store.db.execute("INSERT INTO invoice_items(invoice_id,description,amount) VALUES(7,'Legacy filling',250000)")
        store.db.execute("INSERT INTO payments(invoice_id,date,amount,method) VALUES(7,'2020-01-01',100000,'Cash')")
    store.db.close();svc=account(root)
    assert svc.account_totals(41)==dict(total=250000,paid=100000,balance=150000)
    assert len(list((tmp_path/'FaramarzUpgradeBackups').glob('*.fdbackup')))==1
    assert svc.s.db.execute('PRAGMA foreign_key_check').fetchall()==[]
    svc.s.db.close()


def test_statement_date_filters_keep_opening_balance_and_current_totals(tmp_path):
    from datetime import date,timedelta
    svc,pid,_,_,_,iid=fixture_bill(tmp_path/'profile');svc.payment(iid,100000,'Cash')
    tomorrow=(date.fromisoformat(today())+timedelta(days=1)).isoformat()
    account=svc.statement(pid,tomorrow,tomorrow)
    assert account['opening']==150000 and account['events']==[]
    with pytest.raises(ValueError):svc.statement(pid,tomorrow,today())
    assert svc.dashboard(7)['billed_today']==250000
    svc.s.db.close()


def test_local_password_recovery_preserves_records_and_audits(tmp_path):
    from clinic.recovery import reset_local_password
    svc,pid,_,_,_,iid=fixture_bill(tmp_path/'profile');before=svc.invoice_totals(iid)
    backup=reset_local_password(svc.s,'doctor','a-new-private-password');assert backup.exists()
    assert svc.invoice_totals(iid)==before
    svc.login('doctor','a-new-private-password')
    with pytest.raises(ValueError):svc.login('doctor','long-test-password')
    assert svc.s.one("SELECT id FROM audit WHERE action='local password recovery'")
    svc.s.db.close()


def test_billing_and_collection_dates_have_distinct_period_scope(tmp_path,monkeypatch):
    from datetime import date,timedelta
    import clinic.finance as finance
    real=today();old=(date.fromisoformat(real)-timedelta(days=40)).isoformat()
    svc=account(tmp_path/'profile');pid=svc.save_patient(dict(name='Old invoice',phone='0701234567'));vid=svc.visit(pid,'Doctor',date=old)
    svc.add_charge(vid,'Consultation',250000);monkeypatch.setattr(finance,'today',lambda:old);iid=svc.invoice(vid)
    svc.payment(iid,100000,'Cash',date=old)
    monkeypatch.setattr(finance,'today',lambda:real);svc.payment(iid,150000,'Cash',date=real)
    d=svc.dashboard(7)
    assert d['billed_today']==0 and d['collected_today']==150000 and d['outstanding']==0
    assert len(d['ledger'])==1 and d['billed']==[]
    assert svc.report(real,real)['billed']==0 and svc.report(real,real)['collected']==150000
    period=svc.statement(pid,real,real);assert period['opening']==150000 and period['events'][-1]['balance']==0
    svc.s.db.close()


def test_related_attachment_records_commit_atomically(tmp_path):
    svc=account(tmp_path/'profile')
    records=[dict(name='A',stored='same-file',sha256='one'),dict(name='B',stored='same-file',sha256='two')]
    with pytest.raises(sqlite3.IntegrityError):svc.record_attachments(records)
    assert svc.s.rows('SELECT * FROM attachments')==[]
    svc.s.db.close()


def test_migration_failure_rolls_back_schema_and_keeps_backup(tmp_path,monkeypatch):
    store=Store(tmp_path/'legacy')
    for i,sql in enumerate(MIGRATIONS[:4],1):store.db.executescript('BEGIN;'+sql+f'PRAGMA user_version={i};COMMIT;')
    with store.db:store.db.execute("INSERT INTO patients(name,phone,created) VALUES('Preserve me','0701234567','2020-01-01')")
    monkeypatch.setattr('clinic.schema.MIGRATIONS',MIGRATIONS[:4]+["CREATE TABLE interrupted(id); INSERT INTO does_not_exist VALUES(1);"])
    with pytest.raises(sqlite3.OperationalError):store.migrate()
    assert store.db.execute('PRAGMA user_version').fetchone()[0]==4
    assert store.one("SELECT name FROM sqlite_master WHERE name='interrupted'") is None
    assert store.one('SELECT name FROM patients')['name']=='Preserve me'
    assert len(list((tmp_path/'FaramarzUpgradeBackups').glob('*.fdbackup')))==1
    store.db.close()
