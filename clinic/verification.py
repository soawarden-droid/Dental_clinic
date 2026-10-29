"""Packaged, isolated acceptance runner. Never opens the normal clinic profile."""
import json
import secrets
from pathlib import Path
from time import perf_counter
from PySide6.QtWidgets import QDialog,QComboBox,QTextEdit,QLineEdit,QApplication
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtPrintSupport import QPrinter
from .widgets import Form
from .ui import Window,authenticate,PAGES
from .printing import PrintDialog,invoice_html,statement_html
from .backup import create_backup,restore_backup
from .storage import Store
from .service import Service


def run(app,service,assets,destination,started):
    output=Path(destination);output.mkdir(parents=True,exist_ok=True)
    password=secrets.token_urlsafe(24)
    def first_account():
        d=app.activeModalWidget()
        for key,value in [('username','acceptance'),('password',password),('repeat',password)]:
            d.findChild(QLineEdit,key).setText(value)
        d.findChild(__import__('PySide6.QtWidgets',fromlist=['QPushButton']).QPushButton,'unlock').click()
    QTimer.singleShot(50,first_account)
    assert authenticate(service)
    w=Window(service,assets);w.resize(1366,768);w.show();app.processEvents()
    result={'usable_seconds_in_process':round(perf_counter()-started,3),'checks':[]}
    print('Acceptance window ready',flush=True)
    errors=[];w.error=errors.append
    def fill(values):
        def submit():
            d=app.activeModalWidget()
            if not isinstance(d,Form):raise RuntimeError('Expected the real clinic form')
            for key,value in values.items():
                widget,kind=d.fields[key]
                if isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(value))
                elif isinstance(widget,QTextEdit):widget.setPlainText(str(value))
                elif hasattr(widget,'setText'):widget.setText(str(value))
                else:widget.setValue(value)
            d.validate()
        QTimer.singleShot(30,submit)
    fill(dict(name='Fictional Acceptance / مریض آزمایشی',phone='0701234567'))
    w.new_patient();assert w.pid==1
    row=service.s.one('SELECT * FROM patients WHERE id=1')
    assert all(row[key] is None for key in ('father','dob','estimated_age','gender','address','email','allergies','history','emergency'))
    result['checks'].append('Name-and-phone-only registration: omitted optional fields are SQL NULL')
    fill(dict(notes='Acceptance test visit'));w.new_visit(1)
    fill(dict(amount='500'));w.add_charge()
    fill(dict(procedure='Filling',price='2000',tooth='55',status='completed'));w.add_treatment('55')
    fill(dict(discount='0'));w.issue_invoice();w.invoice_table.setCurrentCell(0,0)
    original=PrintDialog.exec
    def capture_pdf(d):
        printer=d.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output/'acceptance-receipt.pdf'));d.document.print_(printer);return QDialog.Accepted
    PrintDialog.exec=capture_pdf
    try:fill(dict(amount='1000'));w.pay()
    finally:PrintDialog.exec=original
    assert service.invoice_totals(1)==dict(total=250000,paid=100000,balance=150000)
    result['checks'].append('Real account and patient → visit → treatment → invoice → partial payment → PDF dialogs')
    def settle():
        loop=QEventLoop();QTimer.singleShot(400,loop.quit);loop.exec()
    for lang,theme,filename,patient in [('en','light','overview-en-light.png',False),('en','dark','patient-en-dark.png',True),('fa_AF','light','patient-dari-light.png',True),('fa_AF','dark','overview-dari-dark.png',False)]:
        service.s.set_setting('language',lang);service.s.set_setting('theme',theme);w.current='Overview';w.build()
        for page in PAGES:w.navigate(page);app.processEvents()
        w.patient_detail(1) if patient else w.overview();settle();w.grab().save(str(output/filename))
    w.image_settings();settle();w.grab().save(str(output/'image-settings-dari-dark.png'))
    assert not errors,errors
    result['checks'].append('All pages render in English/Dari and light/dark at 1366×768')
    from . import i18n
    i18n.LANG='fa_AF';d=PrintDialog(invoice_html(service,1,1));printer=d.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output/'acceptance-dari-receipt.pdf'));d.document.print_(printer)
    before=service.invoice_totals(1);assert before==dict(total=250000,paid=100000,balance=150000)
    root=service.s.root;w.close();service=Service(Store(root));service.login('acceptance',password);w=Window(service,assets);w.resize(1366,768);w.show();w.patient_detail(1,3);settle()
    w.grab().save(str(output/'billing-partial-dari-dark.png'))
    assert service.invoice_totals(1)==before
    fill(dict(notes='Later visit'));w.new_visit(1)
    PrintDialog.exec=capture_pdf
    try:fill(dict(amount='1500'));w.pay()
    finally:PrintDialog.exec=original
    before=service.invoice_totals(1);assert before==dict(total=250000,paid=250000,balance=0)
    assert service.balances(1)[0]['status']=='paid'
    assert len(service.s.rows('SELECT * FROM payments'))==2
    data=service.dashboard(7);assert data['billed_today']==data['collected_today']==250000 and data['outstanding']==0
    result['checks'].append('500 AFN consultation + 2000 AFN treatment; 1000 payment, restart, later visit and 1500 payment; paid status and dashboard reconcile')
    statement=PrintDialog(statement_html(service,1));printer=statement.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output/'acceptance-statement.pdf'));statement.document.print_(printer)
    w.patient_detail(1,3);settle();w.grab().save(str(output/'billing-paid-dari-dark.png'))
    result['checks'].append('Dari PDF generated; printing leaves balance unchanged')
    attachment=output/'fictional-attachment.txt';attachment.write_text('Fictional acceptance attachment')
    service.attach(attachment,1);service.attach(attachment)
    archive=create_backup(service.s.root,output/'backups')
    fresh=Store(output/'restored-profile');Service(fresh);safety=restore_backup(fresh,archive)
    restored=Service(Store(output/'restored-profile'));restored.login('acceptance',password)
    assert restored.invoice_totals(1)==before
    assert restored.s.setting('language')=='fa_AF'
    assert len(restored.s.rows('SELECT * FROM patients'))==1
    for row in restored.s.rows('SELECT * FROM attachments'):
        assert (restored.s.root/'attachments'/row['stored']).read_text()=='Fictional acceptance attachment'
    restored.s.db.close();result['checks'].append('Consistent backup restored into a fresh profile: patient, invoices, payments, attachments, settings and account verified')
    (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True);w.close();return 0
