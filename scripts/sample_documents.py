import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtPrintSupport import QPrinter
from clinic.storage import Store
from clinic.service import Service
from clinic.printing import PrintDialog,invoice_html
from clinic import i18n
from clinic.domain import today
app=QApplication([])
for f in Path('assets').glob('*.ttf'):QFontDatabase.addApplicationFont(str(f))
output=Path('docs/examples');output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    service=Service(Store(tmp));service.register('sample','Sample-documents-only');service.login('sample','Sample-documents-only')
    pid=service.save_patient({'name':'نمونه خیالی — مریم احمدی','phone':'','estimated_age':'25'})
    vid=service.visit(pid,'Dr. Farshad Faramarz');service.treatment(vid,'Filling',250000,'26',status='completed');iid=service.invoice(vid);rid=service.payment(iid,100000,'Cash')
    for lang in ('en','fa_AF'):
        i18n.LANG=lang
        service.s.set_setting('clinic_address','خیرخانه، ناحیه ۱۱، کابل، افغانستان' if lang=='fa_AF' else 'Khair Khana, District 11, Kabul, Afghanistan')
        for paper in ('a4','receipt'):
            d=PrintDialog(invoice_html(service,iid,rid));d.paper.setCurrentIndex(0 if paper=='a4' else 1)
            printer=d.printer();printer.setOutputFormat(QPrinter.PdfFormat);printer.setOutputFileName(str(output/f'receipt-{lang}-{paper}.pdf'));d.document.print_(printer)
    service.s.db.close()
