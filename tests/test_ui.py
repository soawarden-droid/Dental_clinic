"""Drive real Qt dialogs through the daily clinic workflow."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication,QDialog,QComboBox,QTextEdit,QLineEdit
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtPrintSupport import QPrinter
from clinic.storage import Store
from clinic.service import Service
from clinic.ui import Window,PAGES
from clinic.widgets import Form
from clinic.printing import PrintDialog,invoice_html
from clinic import i18n


@pytest.fixture(scope='module')
def app():
    app=QApplication.instance() or QApplication([])
    for path in Path('assets').glob('*.ttf'):QFontDatabase.addApplicationFont(str(path))
    yield app


def fill_next(app,values):
    def fill():
        d=app.activeModalWidget()
        assert isinstance(d,Form)
        for key,value in values.items():
            w,kind=d.fields[key]
            if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(value))
            elif isinstance(w,QTextEdit):w.setPlainText(str(value))
            elif hasattr(w,'setText'):w.setText(str(value))
            elif hasattr(w,'setValue'):w.setValue(value)
        d.validate()
    QTimer.singleShot(30,fill)


def test_real_dialog_patient_to_receipt(app,tmp_path,monkeypatch):
    svc=Service(Store(tmp_path/'clinic'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    w=Window(svc,Path('assets'));w.show();app.processEvents()
    fill_next(app,dict(name='Fictional · آزمایش مریض',phone='0701234567',estimated_age='8',allergies='Fictional alert'))
    w.new_patient();assert w.pid==1
    fill_next(app,dict(notes='Fictional visit'))
    w.new_visit(1)
    fill_next(app,dict(procedure='Filling',price='2500.29',tooth='55',status='completed',notes='Fictional primary tooth'))
    w.add_treatment('55')
    fill_next(app,dict(discount='0.29'))
    w.issue_invoice()
    assert svc.invoice_totals(1)['total']==250000
    w.invoice_table.setCurrentCell(0,0)
    paths=[]
    def export(dialog):
        path=tmp_path/f'receipt-{len(paths)}.pdf';printer=dialog.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(path));dialog.document.print_(printer);paths.append(path);return QDialog.Accepted
    monkeypatch.setattr(PrintDialog,'exec',export)
    fill_next(app,dict(amount='1000.00'))
    w.pay()
    assert svc.invoice_totals(1)==dict(total=250000,paid=100000,balance=150000)
    assert paths[0].read_bytes().startswith(b'%PDF')
    # Printing is read only.
    before=svc.invoice_totals(1);w.invoice_table.setCurrentCell(0,0);w.print_invoice();assert svc.invoice_totals(1)==before
    # Full navigation renders in both languages and themes without modal errors.
    errors=[];w.error=lambda message:errors.append(message)
    for lang in ('en','fa_AF'):
        for theme in ('light','dark'):
            w.s.set_setting('language',lang);w.s.set_setting('theme',theme);w.current='Overview';w.build()
            for page in PAGES:w.navigate(page);app.processEvents()
            w.patient_detail(1);app.processEvents()
    assert not errors
    # Dari output uses the same record and a bundled font.
    i18n.LANG='fa_AF';export(PrintDialog(invoice_html(svc,1,1),w))
    w.close()


def test_receptionist_clinical_pages_hidden(app,tmp_path):
    svc=Service(Store(tmp_path/'clinic'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    pid=svc.save_patient(dict(name='Fictional patient',phone='0701234567',history='Private clinical notes'))
    svc.register('reception','reception-test-password','receptionist');svc.login('reception','reception-test-password')
    w=Window(svc,Path('assets'));w.patient_detail(pid)
    from PySide6.QtWidgets import QTabWidget
    tabs=w.pages.currentWidget().findChild(QTabWidget)
    assert tabs.count()==2
    assert all('Private clinical notes' not in label.text() for label in tabs.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel))
    w.close()


def test_background_attachment_backup_and_restore(app,tmp_path,monkeypatch):
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog
    from time import monotonic
    import clinic.ui as ui
    svc=Service(Store(tmp_path/'clinic'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password');pid=svc.save_patient(dict(name='Fictional patient',phone='0701234567'))
    w=Window(svc,Path('assets'));errors=[];w.error=errors.append
    photo=tmp_path/'photo.png';image=QImage(2000,1500,QImage.Format_RGB32);image.fill(QColor('#087f80'));assert image.save(str(photo))
    results=[];w.attach_file(photo,pid,results.append,True)
    def wait_jobs():
        deadline=monotonic()+15
        while w.jobs and monotonic()<deadline:QTest.qWait(20)
        assert not w.jobs
        assert not errors,errors
    wait_jobs();assert len(results[0])==2
    assert len(svc.s.rows('SELECT * FROM attachments'))==2
    w.s.set_setting('backup_folder',str(tmp_path/'usb'));w.backup();wait_jobs()
    backup=next((tmp_path/'usb').glob('*.fdbackup'))
    svc.save_patient(dict(name='After backup patient',phone='0701234568'))
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a,**k:(str(backup),''));w.confirm=lambda _:True
    def login_restored(service,parent=None):service.login('doctor','a-long-test-password');return True
    monkeypatch.setattr(ui,'authenticate',login_restored)
    w.restore();wait_jobs()
    assert w.svc.user['username']=='doctor'
    assert len(w.s.rows('SELECT * FROM patients'))==1
    assert len(w.s.rows('SELECT * FROM attachments'))==2
    assert w.current=='Overview'
    w.close()


def test_pdf_export_worker(app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtTest import QTest
    from time import monotonic
    destination=tmp_path/'async.pdf'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(destination),''))
    d=PrintDialog('<html dir="rtl"><body style="font-family:Noto Sans Arabic">مریض آزمایشی — 1,234.50 AFN</body></html>')
    d.pdf();deadline=monotonic()+10
    while d.export_job and monotonic()<deadline:QTest.qWait(20)
    assert d.export_job is None
    assert destination.read_bytes().startswith(b'%PDF')
    d.close()


def test_first_account_in_dari(app,tmp_path):
    from PySide6.QtWidgets import QPushButton
    from clinic.ui import authenticate
    svc=Service(Store(tmp_path/'clinic'));svc.s.set_setting('language','fa_AF');i18n.LANG='fa_AF'
    def submit():
        d=app.activeModalWidget()
        for key,value in [('username','مدیر'),('password','local-dari-password'),('repeat','local-dari-password')]:d.findChild(QLineEdit,key).setText(value)
        d.findChild(QPushButton,'unlock').click()
    QTimer.singleShot(30,submit)
    assert authenticate(svc)
    assert svc.user['role']=='admin'
    svc.s.db.close();i18n.LANG='en'


def test_minimal_registration_form_inline_errors_and_null_printing(app,tmp_path):
    from clinic.ui import PATIENT_FIELDS
    from clinic.printing import document_html
    from clinic import i18n
    svc=Service(Store(tmp_path/'profile'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password');w=Window(svc,'assets')
    d=Form('New patient',PATIENT_FIELDS,w);d.show();app.processEvents()
    assert d.additional.isHidden()
    d.validate();assert d.result_values is None and d.field_errors['name'].text()
    d.fields['name'][0].setText('  Minimal patient  ');d.validate();assert d.result_values is None and d.field_errors['phone'].text()
    d.fields['phone'][0].setText(' 070 123 4567 ');d.validate()
    pid=svc.save_patient(d.result_values);p=svc.s.one('SELECT * FROM patients WHERE id=?',(pid,))
    assert all(p[k] is None for k in ('father','address','dob','estimated_age','gender','email','history','allergies','medications','alerts','emergency','consent'))
    html=document_html(svc,'Patient',p,[('Birth date',p['dob']),('Address',p['address'])])
    assert 'None' not in html and '>null<' not in html and 'Minimal patient' in html
    output=tmp_path/'minimal-patient.pdf';dialog=PrintDialog(html,w);printer=dialog.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output));dialog.document.print_(printer)
    assert output.read_bytes().startswith(b'%PDF')
    d2=Form('Edit patient',PATIENT_FIELDS,w,p);assert d2.fields['dob'][0].text()=='' and d2.fields['gender'][0].currentData() is None
    d2.fields['address'][0].setText('');svc.save_patient(d2.values(),pid);w.patient_detail(pid);w.close()


def test_charts_empty_data_and_reduced_motion(app,tmp_path,monkeypatch):
    from clinic.components import Chart
    from clinic.theme import motion_enabled
    from PySide6.QtTest import QTest
    import clinic.theme as theme
    svc=Service(Store(tmp_path/'profile'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    svc.s.set_setting('reduced_motion',True);assert not motion_enabled(svc.s)
    data=svc.dashboard(7)
    for kind,rows in [('trend',data['trend']),('donut',data['distribution']),('status',data['statuses'])]:
        chart=Chart(kind,rows,motion_enabled(svc.s),has_records=False);chart.resize(400,200);chart.show();app.processEvents();assert chart.animation is None;assert not chart.grab().isNull();chart.close()
    # Real zero/negative collections render without inventing a positive baseline.
    chart=Chart('trend',[{'date':'2026-10-27','amount':100},{'date':'2026-10-28','amount':-50}],False);chart.resize(400,200);chart.show();app.processEvents();assert not chart.grab().isNull();chart.close()
    svc.s.set_setting('reduced_motion',False);monkeypatch.setattr(theme,'system_reduced_motion',lambda:True);assert not motion_enabled(svc.s)
    svc.s.db.close()


def test_real_image_controls_upload_remove_and_restart(app,tmp_path,monkeypatch):
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtWidgets import QFileDialog,QPushButton
    from PySide6.QtTest import QTest
    from time import monotonic
    from clinic.i18n import tr
    svc=Service(Store(tmp_path/'profile'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    original=tmp_path/'original-doctor.png';image=QImage(300,300,QImage.Format_RGB32);image.fill(QColor('#c4afe9'));assert image.save(str(original));original_bytes=original.read_bytes()
    w=Window(svc,'assets');w.show();w.image_settings();w.confirm=lambda _:True;errors=[];w.error=errors.append
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a,**k:(str(original),''))
    def click(text):next(b for b in w.pages.currentWidget().findChildren(QPushButton) if b.text()==tr(text)).click()
    click('Add');deadline=monotonic()+15
    while w.jobs and monotonic()<deadline:QTest.qWait(20)
    assert not errors and svc.s.setting('profile_photo')
    stored=svc.s.setting('profile_photo');assert (svc.s.root/'attachments'/stored).exists()
    click('Remove');assert svc.s.setting('profile_photo')==''
    assert original.read_bytes()==original_bytes
    root=svc.s.root;w.close();reopened=Store(root);reopened.migrate();assert reopened.setting('profile_photo')=='';assert reopened.rows('SELECT * FROM image_assets')==[];reopened.db.close()


def test_real_fee_installments_restart_and_statement(app,tmp_path,monkeypatch):
    from clinic.printing import statement_html
    from PySide6.QtTest import QTest
    svc=Service(Store(tmp_path/'clinic'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    svc.register('desk','reception-password','receptionist');svc.login('desk','reception-password')
    w=Window(svc,'assets');w.show();app.processEvents()
    fill_next(app,dict(name='Minimal reception patient',phone='0701234567'));w.new_patient()
    fill_next(app,{});w.new_visit(1)
    fill_next(app,dict(amount='500'));w.add_charge()
    fill_next(app,dict(kind='procedure',description='Filling',amount='2000'));w.add_charge()
    assert len(svc.drafts(1))==2 and svc.account_totals(1)['balance']==0
    fill_next(app,dict(discount='0'));w.billing_invoice()
    assert svc.account_totals(1)==dict(total=250000,paid=0,balance=250000)
    assert w.invoice_table.records[0]['status']=='unpaid'
    def receipt(d):
        # Re-entrant attempts while printing must not open a second payment form.
        w.pay()
        path=tmp_path/'receipt.pdf';printer=d.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(path));d.document.print_(printer);return QDialog.Accepted
    monkeypatch.setattr(PrintDialog,'exec',receipt)
    def pay_twice():
        d=app.activeModalWidget();d.fields['amount'][0].setText('3000');d.validate()
        assert not d.submitted and d.error.text() and svc.s.rows('SELECT * FROM payments')==[]
        d.fields['amount'][0].setText('1000');QTest.mouseClick(d.save_button,Qt.LeftButton);d.validate()
    QTimer.singleShot(30,pay_twice);w.pay()
    assert len(svc.s.rows('SELECT * FROM payments'))==1
    assert svc.account_totals(1)['balance']==150000 and w.invoice_table.records[0]['status']=='partial'
    assert (tmp_path/'receipt.pdf').read_bytes().startswith(b'%PDF')
    root=svc.s.root;w.close()
    svc=Service(Store(root));svc.login('desk','reception-password');w=Window(svc,'assets');w.patient_detail(1)
    assert svc.account_totals(1)['balance']==150000
    fill_next(app,{});w.new_visit(1)
    fill_next(app,dict(amount='1500'));w.pay()
    assert len(svc.s.rows('SELECT * FROM payments'))==2
    assert svc.account_totals(1)['balance']==0 and w.invoice_table.records[0]['status']=='paid'
    html=statement_html(svc,1);assert 'Doctor consultation fee' in html and 'Filling' in html and '1,000.00 AFN' in html and '1,500.00 AFN' in html
    assert svc.dashboard(7)['billed_today']==svc.dashboard(7)['collected_today']==250000
    w.close()


def test_failed_form_save_stays_open_and_can_be_corrected(app,tmp_path):
    svc=Service(Store(tmp_path/'profile'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password')
    pid=svc.save_patient(dict(name='Test',phone='0701234567'));vid=svc.visit(pid,'Doctor')
    d=Form('Add charge',[('description','Description','line',' '),('amount','Amount','money','500')],submit_callback=lambda v:svc.add_charge(vid,v['description'],__import__('clinic.domain',fromlist=['money']).money(v['amount'])))
    d.show();d.validate();assert not d.submitted and d.error.text() and not svc.s.rows('SELECT * FROM charges')
    d.fields['description'][0].setText('Consultation');d.validate();d.validate()
    assert d.submitted and len(svc.s.rows('SELECT * FROM charges'))==1
    svc.s.db.close()


def test_forgot_password_button_opens_explicit_recovery_and_allows_login(app,tmp_path):
    from clinic.ui import authenticate
    from PySide6.QtWidgets import QPushButton,QCheckBox
    from clinic.i18n import tr
    svc=Service(Store(tmp_path/'profile'));svc.register('doctor','old-local-password');i18n.LANG='en'
    def reset_and_sign_in():
        login=app.activeModalWidget()
        def fill_recovery():
            recovery=app.activeModalWidget();fields=recovery.findChildren(QLineEdit)
            fields[0].setText('new-local-password');fields[1].setText('new-local-password');recovery.findChild(QCheckBox).setChecked(True)
            next(b for b in recovery.findChildren(QPushButton) if b.text()==tr('Reset password')).click()
        QTimer.singleShot(30,fill_recovery)
        next(b for b in login.findChildren(QPushButton) if b.text()==tr('Forgot password?')).click()
        login.findChild(QLineEdit,'username').setText('doctor');login.findChild(QLineEdit,'password').setText('new-local-password');login.findChild(QPushButton,'unlock').click()
    QTimer.singleShot(30,reset_and_sign_in)
    assert authenticate(svc) and svc.user['username']=='doctor'
    assert list((tmp_path/'FaramarzPasswordRecoveryBackups').glob('*.fdbackup'))
    svc.s.db.close()
