import pytest
from pathlib import Path
from datetime import date,timedelta
from clinic.service import Service,prepare_attachment
from clinic.storage import Store
from clinic.domain import today


def service(path):
    svc=Service(Store(path));svc.register('doctor','local-test-password');svc.login('doctor','local-test-password');return svc


def test_dashboard_reconciles_actual_saved_transactions(tmp_path):
    svc=service(tmp_path/'profile');pid=svc.save_patient(dict(name='Test',phone='0701234567'))
    vid=svc.visit(pid,'Doctor');svc.treatment(vid,'Filling',250029,'11',status='completed');svc.treatment(vid,'Crown',900000,'12',status='planned');iid=svc.invoice(vid,29)
    svc.payment(iid,120000,'Cash');svc.payment(iid,-20000,'Cash','Correction')
    tomorrow=(date.fromisoformat(today())+timedelta(days=1)).isoformat();svc.appointment(pid,tomorrow+'T10:00',30)
    svc.appointment(pid,today()+'T09:00',30,'arrived')
    data=svc.dashboard(7)
    assert len(data['visits'])==1
    assert data['collected_today']==100000==sum(r['amount'] for r in data['trend'])
    assert data['outstanding']==150000==sum(r['balance'] for r in data['balances'])
    assert data['distribution']==[{'procedure':'Filling','count':1}]
    assert sum(r['count'] for r in data['statuses'])==1
    assert any(r['starts']==tomorrow+'T10:00' for r in data['upcoming'])
    assert data['trend'][0]['date']==(date.fromisoformat(today())-timedelta(days=6)).isoformat()
    svc.s.db.close()


def test_empty_dashboard_contains_no_invented_activity(tmp_path):
    svc=service(tmp_path/'profile');d=svc.dashboard(30)
    assert d['collected_today']==d['outstanding']==0
    assert not any(d[k] for k in ('ledger','distribution','statuses','visits','recent_patients','upcoming'))
    assert len(d['trend'])==30 and sum(x['amount'] for x in d['trend'])==0
    svc.s.db.close()


def test_image_replace_remove_restart_and_shared_references(tmp_path):
    # A complete valid tiny PNG; prepare_attachment thumbnails are tested through Qt below.
    import base64
    original=tmp_path/'original.png';original.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    svc=service(tmp_path/'profile');doc=tmp_path/'certificate.txt';doc.write_text('Unrelated qualification document');document_id=svc.attach(doc)
    records=prepare_attachment(svc.s.root,original)
    first=svc.replace_image('profile_photo',records)
    # Another image slot references this asset; removing the first must retain it.
    with svc.s.db:
        svc.s.db.execute('INSERT INTO image_assets VALUES(?,?,?)',('gallery_a',first[0],first[-1]))
        svc.s.db.execute('INSERT INTO settings VALUES(?,?)',('gallery_a',records[-1]['stored']))
    svc.remove_image('profile_photo')
    assert (svc.s.root/'attachments'/records[0]['stored']).exists()
    svc.remove_image('gallery_a')
    assert not (svc.s.root/'attachments'/records[0]['stored']).exists()
    before=original.read_bytes()
    new=prepare_attachment(svc.s.root,original);svc.replace_image('clinic_background',new)
    old_path=svc.s.root/'attachments'/new[0]['stored']
    next_image=prepare_attachment(svc.s.root,original);svc.replace_image('clinic_background',next_image)
    assert not old_path.exists()
    assert original.read_bytes()==before
    svc.remove_image('clinic_background');root=svc.s.root;svc.s.db.close();store=Store(root);store.migrate()
    assert store.setting('clinic_background')=='' and store.setting('profile_photo')==''
    row=store.one('SELECT * FROM attachments WHERE id=?',(document_id,));assert (root/'attachments'/row['stored']).read_text()=='Unrelated qualification document'
    store.db.close()
