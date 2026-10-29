import sqlite3
from pathlib import Path
import pytest
from clinic.storage import Store
from clinic.service import Service
from clinic.schema import MIGRATIONS

OPTIONAL='father address dob estimated_age gender email history allergies medications alerts emergency consent'.split()


def account(folder):
    svc=Service(Store(folder));svc.register('doctor','local-test-password');svc.login('doctor','local-test-password');return svc


def test_minimal_patient_nullable_reopen_and_partial_edit(tmp_path):
    svc=account(tmp_path/'profile')
    pid=svc.save_patient({'name':'  Test Patient  ','phone':' 070 123 4567 '})
    row=svc.s.one('SELECT * FROM patients WHERE id=?',(pid,))
    assert row['name']=='Test Patient' and row['phone']=='+93701234567'
    assert all(row[k] is None for k in OPTIONAL)
    svc.save_patient({'address':'   ','allergies':None},pid)
    svc.s.db.close();svc.s=Store(tmp_path/'profile');svc.s.migrate()
    row=svc.s.one('SELECT * FROM patients WHERE id=?',(pid,))
    assert all(row[k] is None for k in OPTIONAL)
    svc.save_patient({'name':'Edited Patient'},pid)
    assert svc.s.one('SELECT phone FROM patients WHERE id=?',(pid,))['phone']=='+93701234567'
    svc.s.db.close()


def test_required_essentials_and_shared_phone_warning(tmp_path):
    svc=account(tmp_path/'profile')
    for values in ({'name':'  ','phone':'0701234567'},{'name':'A','phone':'  '},{'name':'A'}):
        with pytest.raises(ValueError):svc.save_patient(values)
    svc.save_patient({'name':'Family One','phone':'0701234567'})
    assert svc.duplicates('Family Two','+93 (0)70 123 4567')
    second=svc.save_patient({'name':'Family Two','phone':'+93701234567'})
    assert second==2
    svc.s.db.close()


def test_v2_upgrade_preserves_ids_finances_files_and_legacy_missing_phone(tmp_path):
    store=Store(tmp_path/'old')
    for index,sql in enumerate(MIGRATIONS[:2],1):
        store.db.executescript('BEGIN;'+sql+f'PRAGMA user_version={index};COMMIT;')
    with store.db:
        store.db.execute("INSERT INTO patients(id,name,phone,created,estimated_age) VALUES(41,'Existing child','','2020-01-01','0')")
        store.db.execute("INSERT INTO visits(id,patient_id,date,doctor) VALUES(12,41,'2020-01-01','Doctor')")
        store.db.execute("INSERT INTO invoices(id,patient_id,visit_id,date) VALUES(7,41,12,'2020-01-01')")
        store.db.execute("INSERT INTO invoice_items(invoice_id,description,amount) VALUES(7,'Work',250000)")
        store.db.execute("INSERT INTO payments(invoice_id,date,amount,method) VALUES(7,'2020-01-01',100000,'Cash')")
        store.db.execute("INSERT INTO attachments(patient_id,scope,name,stored,sha256) VALUES(41,'patient','Original','original.txt','d59c2a5f721ce135ce54628b1ad8ad8b8eb26c8bbe2e2abe1cdca97e2d6ab446')")
    folder=store.root/'attachments';folder.mkdir();(folder/'original.txt').write_text('untouched')
    store.db.close();svc=account(tmp_path/'old')
    p=svc.s.one('SELECT * FROM patients WHERE id=41')
    assert p['father'] is None and p['dob'] is None and p['estimated_age']=='0'
    assert svc.invoice_totals(7)==dict(total=250000,paid=100000,balance=150000)
    assert (folder/'original.txt').read_text()=='untouched'
    assert svc.s.rows('PRAGMA foreign_key_check')==[]
    svc.save_patient({'history':'Updated clinical notes without inventing demographics'},41)
    assert svc.s.one('SELECT phone FROM patients WHERE id=41')['phone']==''
    assert svc.save_patient({'name':'Next','phone':'0701234567'})>41
    svc.s.db.close()
