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
    fill_next(app,dict(name='Fictional · آزمایش مریض',estimated_age='8',allergies='Fictional alert'))
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
    pid=svc.save_patient(dict(name='Fictional patient',history='Private clinical notes'))
    svc.register('reception','reception-test-password','receptionist');svc.login('reception','reception-test-password')
    w=Window(svc,Path('assets'));w.patient_detail(pid)
    from PySide6.QtWidgets import QTabWidget
    tabs=w.pages.currentWidget().findChild(QTabWidget)
    assert tabs.count()==1
    w.close()


def test_background_attachment_backup_and_restore(app,tmp_path,monkeypatch):
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog
    from time import monotonic
    import clinic.ui as ui
    svc=Service(Store(tmp_path/'clinic'));svc.register('doctor','a-long-test-password');svc.login('doctor','a-long-test-password');pid=svc.save_patient(dict(name='Fictional patient'))
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
    svc.save_patient(dict(name='After backup patient'))
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
