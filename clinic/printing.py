from html import escape
import os
import uuid
from pathlib import Path
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
from PySide6.QtCore import QMarginsF, Qt, QSizeF, QThread, Signal
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QFileDialog, QTextBrowser, QHBoxLayout, QComboBox, QProgressDialog, QMessageBox
from .i18n import tr
from . import i18n
from .domain import afn, display_date
from .theme import LIGHT


def document_html(service, title, patient, rows, totals=None, extra=''):
    s = service.s
    name = s.setting('clinic_name','Faramarz Dental Clinic')
    doctor = s.setting('display_dari' if i18n.LANG=='fa_AF' else 'display_english','داکتر فرشاد فرامرز' if i18n.LANG=='fa_AF' else 'Dr. Farshad Faramarz')
    direction = 'rtl' if i18n.LANG=='fa_AF' else 'ltr'
    def e(v): return escape('—' if v is None or v=='' else str(v)).replace('\n','<br>')
    # Explicit embedding keeps the leading + with Latin phone digits in Qt's RTL paragraphs.
    def phone(v):return '&#8234;'+e(v)+'&#8236;'
    logo = s.setting('clinic_logo')
    logo_path=(s.root/'attachments'/logo) if logo else Path(__file__).resolve().parent.parent/'assets'/'clinic.svg'
    logo_html='<img width=48 height=48 src="'+logo_path.as_uri()+'">'
    def row_html(a,b):
        value_dir='rtl' if any('\u0600'<=ch<='\u06ff' for ch in str(b)) else 'ltr'
        if direction=='rtl':
            return '<tr><td align="left" dir="'+value_dir+'">'+e(b)+'</td><td align="right">'+e(a)+'</td></tr>'
        return '<tr><td>'+e(a)+'</td><td align="right" dir="'+value_dir+'">'+e(b)+'</td></tr>'
    body = ''.join(row_html(a,b) for a,b in rows)
    total = '' if not totals else '<hr>'+''.join('<p>'+e(tr(k))+': <span dir="ltr">'+e(afn(v))+'</span></p>' for k,v in totals)
    return f'''<html dir="{direction}"><head><meta charset="utf-8"><style>body{{font-family:'Noto Sans Arabic';font-size:11pt;color:{LIGHT.ink}}}h1{{font-size:23pt;color:{LIGHT.rose}}}td{{padding:9px;border-bottom:1px solid {LIGHT.border}}}table{{width:100%}}small{{color:{LIGHT.muted}}}</style></head><body>{logo_html}<h1>{e(name)}</h1><p>{e(doctor)}<br>{e(s.setting('clinic_address','Khair Khana, District 11, Kabul, Afghanistan'))}<br>{phone(s.setting('clinic_phone',''))}</p><hr><h2>{e(tr(title))}</h2><p>{e(tr('Patient'))}: {e(patient['name'])} &nbsp; <span dir="ltr">P-{patient['id']:06}</span><br>{e(tr('Phone'))}: <span dir="ltr">{phone(patient.get('phone'))}</span></p><table width="100%" dir="{direction}">{body}</table>{total}<p>{e(extra)}</p></body></html>'''


def invoice_html(service, iid, payment_id=None):
    s = service.s
    inv = s.one('SELECT * FROM invoices WHERE id=?',(iid,))
    patient = s.one('SELECT * FROM patients WHERE id=?',(inv['patient_id'],))
    totals = service.invoice_totals(iid)
    rows = [(tr('Invoice number'),f'INV-{iid:06}'),(tr('Date'),display_date(inv['date'],s.setting('calendar')=='solar',i18n.LANG=='fa_AF'))]
    rows += [(tr(r['description'].split(' · ')[0])+(' · '+r['description'].split(' · ')[1] if ' · ' in r['description'] else ''),afn(r['amount'])) for r in s.rows('SELECT * FROM invoice_items WHERE invoice_id=?',(iid,))]
    if payment_id:
        payment = s.one('SELECT * FROM payments WHERE id=? AND invoice_id=?',(payment_id,iid))
        rows[1]=(tr('Date'),display_date(payment['date'],s.setting('calendar')=='solar',i18n.LANG=='fa_AF'))
        rows += [(tr('Receipt number'),f'R-{payment_id:06}'),(tr('Amount'),afn(payment['amount'])),(tr('Method'),tr(payment['method']))]
        if payment['reason']:rows.append((tr('Reason'),payment['reason']))
    if inv['void']:rows += [(tr('Status'),tr('cancelled')),(tr('Reason'),inv['reason'])]
    return document_html(service,'Receipt' if payment_id else 'Invoice',patient,rows,[(tr('Discount'),inv['discount']),('Total',totals['total']),('Paid',totals['paid']),('Remaining',totals['balance'])])


def make_printer(paper):
    printer = QPrinter(QPrinter.HighResolution)
    if paper=='receipt':
        printer.setPageSize(QPageSize(QSizeF(80,200),QPageSize.Millimeter,'80 mm receipt'))
        printer.setPageMargins(QMarginsF(5,5,5,5),QPageLayout.Millimeter)
    else:
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(14,14,14,14),QPageLayout.Millimeter)
    return printer


class PDFJob(QThread):
    failed=Signal(str)

    def __init__(self, html, paper, destination):
        super().__init__()
        self.html,self.paper,self.destination=html,paper,Path(destination)

    def run(self):
        temporary=self.destination.with_name(uuid.uuid4().hex+'.partial.pdf')
        try:
            document=QTextDocument()
            document.setHtml(self.html)
            printer=make_printer(self.paper)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(str(temporary))
            document.print_(printer)
            if not temporary.exists() or temporary.stat().st_size<100:
                raise ValueError('Unable to save PDF')
            os.replace(temporary,self.destination)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            temporary.unlink(missing_ok=True)


class PrintDialog(QDialog):
    def __init__(self, html, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Print / PDF'))
        self.resize(850,680)
        self.export_job=None
        self.document = QTextDocument(self)
        self.document.setHtml(html)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setDocument(self.document)
        layout.addWidget(browser)
        controls = QHBoxLayout()
        self.paper=QComboBox();self.paper.addItem('A4','a4');self.paper.addItem(tr('Receipt')+' · 80 mm','receipt');controls.addWidget(self.paper)
        for name, fn in [('Print preview',self.preview),('Export PDF',self.pdf),('Close',self.accept)]:
            b = QPushButton(tr(name)); b.clicked.connect(fn); controls.addWidget(b)
        layout.addLayout(controls)

    def printer(self):
        return make_printer(self.paper.currentData())

    def preview(self):
        printer = self.printer()
        preview = QPrintPreviewDialog(printer,self)
        preview.paintRequested.connect(self.document.print_)
        preview.exec()

    def pdf(self):
        if self.export_job:return
        path,_ = QFileDialog.getSaveFileName(self,tr('Export PDF'),'','PDF (*.pdf)')
        if path:
            if not path.lower().endswith('.pdf'): path += '.pdf'
            progress=QProgressDialog(tr('Working…'),'',0,0,self)
            progress.setCancelButton(None)
            progress.setWindowModality(Qt.ApplicationModal)
            progress.setMinimumDuration(0)
            progress.show()
            job=PDFJob(self.document.toHtml(),self.paper.currentData(),path)
            self.export_job=job
            errors=[]
            job.failed.connect(errors.append)
            def finish():
                progress.close()
                self.export_job=None
                if errors:QMessageBox.warning(self,tr('Please check your entry'),tr('Unable to save PDF'))
                job.deleteLater()
            job.finished.connect(finish)
            job.start()

    def reject(self):
        if not self.export_job:super().reject()

    def closeEvent(self,event):
        if self.export_job:event.ignore()
        else:super().closeEvent(event)
