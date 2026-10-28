import csv
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from html import escape
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFrame,QLabel,QLineEdit,QPushButton,QStackedWidget,QTabWidget,QDialog,QMessageBox,QFileDialog,QComboBox,QApplication,QScrollArea,QGridLayout,QProgressDialog,QTextBrowser)
from PySide6.QtCore import Qt,QTimer,QThread,Signal,QUrl
from PySide6.QtGui import QIcon,QShortcut,QKeySequence,QDesktopServices,QPixmap
from .widgets import Form,Table,button,label
from .domain import today,now,money,afn,amount_text,display_date,parse_date,ADULT,CHILD
from .i18n import tr
from . import i18n
from .theme import stylesheet
from .printing import PrintDialog,invoice_html,document_html
from .backup import create_backup,restore_backup,apply_retention

PAGES=['Overview','Patients','Appointments','Materials','Purchases','Expenses','Laboratory','Reports','Clinic profile','Settings']
PATIENT_FIELDS=[('name','Full name','line',''),('father','Father’s name','line',''),('phone','Phone','phone',''),('address','Address','line',''),('dob','Birth date','date_optional',''),('estimated_age','Estimated age at registration','line',''),('history','Medical history','text',''),('allergies','Allergies','text',''),('medications','Medications','text',''),('alerts','Clinical alerts','text',''),('emergency','Emergency contact','line',''),('consent','Consent notes','text','')]


class Job(QThread):
    done=Signal(object); failed=Signal(str)
    def __init__(self,fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))


class Window(QMainWindow):
    def __init__(self,service,assets):
        super().__init__(); self.svc=service; self.s=service.s; self.assets=Path(assets)
        self.pid=None; self.current='Overview'; self.archived=False; self.jobs=[]; self.report_rows=[]
        self.setWindowTitle('Faramarz Dental Clinic'); self.setWindowIcon(QIcon(str(self.assets/'clinic.svg')))
        available=QApplication.primaryScreen().availableGeometry()
        self.resize(min(1366,available.width()-24),min(768,available.height()-36)); self.setMinimumSize(1000,560)
        self.build()
        for seq,fn in [('Ctrl+N',self.new_patient),('Ctrl+F',lambda:self.search.setFocus()),('Ctrl+L',self.lock),('Ctrl+B',self.backup)]:
            QShortcut(QKeySequence(seq),self,activated=lambda f=fn:self.guard(f))
        self.schedule=QTimer(self); self.schedule.timeout.connect(self.scheduled_backup); self.schedule.start(60000)
        QApplication.instance().styleHints().colorSchemeChanged.connect(lambda *_: self.apply_theme())

    def guard(self,fn):
        try: return fn()
        except (ValueError,PermissionError,FileNotFoundError) as e: self.error(str(e))
        except Exception as e:
            import logging
            logging.exception('Action failed')
            self.error(str(e))

    def error(self,message):
        text=tr(message)
        if i18n.LANG=='fa_AF' and text==message and message not in i18n.DARI:
            text=tr('Please check your entry')
        QMessageBox.warning(self,tr('Please check your entry'),text)

    def confirm(self,message):
        return QMessageBox.question(self,tr('Confirm'),tr(message),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes

    def form(self,title,fields,initial=None):
        d=Form(title,fields,self,initial)
        if title=='Add treatment':
            choice=d.fields['procedure'][0];price=d.fields['price'][0]
            def update_price():
                row=self.s.one('SELECT price FROM catalogue WHERE name=?',(choice.currentData(),))
                if row:price.setText(f"{row['price']//100}.{row['price']%100:02}")
            choice.currentIndexChanged.connect(update_price);update_price();d.dirty=False
        return d.result_values if d.exec()==QDialog.Accepted else None

    def act(self,text,fn,primary=False): return button(text,lambda:self.guard(fn),primary)

    def date(self,value): return display_date(value,self.s.setting('calendar')=='solar',i18n.LANG=='fa_AF')

    def build(self):
        i18n.LANG=self.s.setting('language','en')
        self.setLayoutDirection(Qt.RightToLeft if i18n.LANG=='fa_AF' else Qt.LeftToRight)
        base=QWidget(); outer=QHBoxLayout(base); outer.setContentsMargins(14,14,14,14); outer.setSpacing(24)
        self.setCentralWidget(base)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(224)
        sl=QVBoxLayout(side); sl.setContentsMargins(16,23,16,18); sl.setSpacing(6)
        brand=QLabel(); brand.setPixmap(QIcon(str(self.assets/'clinic.svg')).pixmap(44,44)); sl.addWidget(brand)
        sl.addWidget(label('FARAMARZ','brand')); sl.addWidget(label('کلینیک دندان فرامرز','subtitle')); sl.addSpacing(20)
        nav_body=QWidget();nav_layout=QVBoxLayout(nav_body);nav_layout.setContentsMargins(0,0,0,0);nav_layout.setSpacing(2)
        self.nav={}
        for name in PAGES:
            if name in ('Overview','Materials','Reports'):nav_layout.addWidget(label({'Overview':'Care','Materials':'Operations','Reports':'Clinic'}[name],'subtitle'))
            b=self.act(name,lambda n=name:self.navigate(n)); b.setObjectName('nav'); b.setCheckable(True); nav_layout.addWidget(b); self.nav[name]=b
            if self.svc.user and self.svc.user['role']!='admin' and name in ('Reports','Clinic profile','Settings'):b.setEnabled(False)
        nav_layout.addStretch()
        self.nav_scroll=QScrollArea();self.nav_scroll.setWidgetResizable(True);self.nav_scroll.setFrameShape(QFrame.NoFrame);self.nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.nav_scroll.setWidget(nav_body);sl.addWidget(self.nav_scroll,1)
        sl.addWidget(self.act('Backup now',self.backup)); sl.addWidget(self.act('Lock',self.lock)); sl.addWidget(label('Offline · Local SQLite','subtitle'))
        outer.addWidget(side)
        right=QVBoxLayout(); right.setSpacing(16); outer.addLayout(right,1)
        top=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText(tr('Search patients')+' · Ctrl+F'); self.search.setMinimumWidth(240)
        self.search_timer=QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.setInterval(180)
        self.search.textChanged.connect(lambda *_:self.search_timer.start()); self.search_timer.timeout.connect(self.global_search)
        top.addWidget(self.search,1)
        self.lang=QComboBox(); self.lang.addItem('English','en'); self.lang.addItem('دری','fa_AF'); self.lang.setCurrentIndex(1 if i18n.LANG=='fa_AF' else 0)
        self.lang.currentIndexChanged.connect(self.switch_language); top.addWidget(self.lang)
        top.addWidget(self.act('New patient',self.new_patient,True)); right.addLayout(top)
        self.pages=QStackedWidget(); right.addWidget(self.pages,1)
        menu=self.menuBar();menu.clear();help_menu=menu.addMenu(tr('Help'))
        help_menu.addAction(tr('User guide'),lambda:self.show_help('User guide',self.assets.parent/'docs'/('USER_GUIDE.fa_AF.md' if i18n.LANG=='fa_AF' else 'USER_GUIDE.md')))
        help_menu.addAction(tr('Licenses'),lambda:self.show_help('Licenses',self.assets/'THIRD-PARTY-NOTICES.md'))
        self.apply_theme(); self.navigate(self.current)

    def show_help(self,title,path):
        d=QDialog(self);d.setWindowTitle(tr(title));d.resize(820,660);l=QVBoxLayout(d);browser=QTextBrowser();browser.setOpenExternalLinks(True)
        browser.setMarkdown(Path(path).read_text(encoding='utf-8'));l.addWidget(browser);l.addWidget(button('Close',d.accept));d.exec()

    def apply_theme(self):
        mode=self.s.setting('theme','system')
        dark=mode=='dark' or (mode=='system' and QApplication.instance().styleHints().colorScheme()==Qt.ColorScheme.Dark)
        QApplication.instance().setStyleSheet(stylesheet(dark)+("\nQWidget {font-family:'Noto Sans Arabic';} QPushButton#nav {text-align:right;}" if i18n.LANG=='fa_AF' else ''))

    def switch_language(self):
        self.s.set_setting('language',self.lang.currentData()); self.build()

    def global_search(self):
        if self.svc.user:
            self.current='Patients'; self.patient_list(self.search.text())
            for name,b in self.nav.items(): b.setChecked(name=='Patients')

    def page(self,title,subtitle=''):
        while self.pages.count():
            old=self.pages.widget(0); self.pages.removeWidget(old); old.deleteLater()
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        body=QWidget(); layout=QVBoxLayout(body); layout.setContentsMargins(0,4,12,12); layout.setSpacing(17)
        layout.addWidget(label(title,'title'))
        if subtitle: layout.addWidget(label(subtitle,'subtitle'))
        scroll.setWidget(body); self.pages.addWidget(scroll)
        return layout

    def actions(self,layout,items):
        row=QHBoxLayout()
        for item in items:
            text,fn,*primary=item; row.addWidget(self.act(text,fn,bool(primary and primary[0])))
        row.addStretch(); layout.addLayout(row)

    def table(self,layout,headers,rows,keys,callback=None):
        if not rows:
            layout.addWidget(label('No records yet','subtitle')); layout.addWidget(label('Start with the action above. Your saved records will appear here.','subtitle'))
        t=Table(headers,rows,keys); layout.addWidget(t)
        if callback: t.cellDoubleClicked.connect(lambda *_:self.guard(lambda:callback(t.selected())))
        return t

    def navigate(self,name):
        self.current=name
        if name in self.nav:self.nav_scroll.ensureWidgetVisible(self.nav[name])
        for n,b in self.nav.items(): b.setChecked(n==name)
        if not self.svc.user: return
        dispatch={'Overview':self.overview,'Patients':self.patient_list,'Appointments':self.appointments,'Materials':self.materials,'Purchases':self.purchases,'Expenses':self.expenses,'Laboratory':self.labs,'Reports':self.reports,'Clinic profile':self.profile,'Settings':self.settings}
        self.guard(dispatch[name])

    def refresh(self):
        if self.current=='detail' and self.pid: self.patient_detail(self.pid)
        else: self.navigate(self.current)
        self.statusBar().showMessage(tr('Saved successfully'),4000)

    def overview(self):
        layout=self.page('Today at the clinic','A calm place to manage your day.')
        self.actions(layout,[('New patient',self.new_patient,True),('New visit',self.quick_visit),('Record payment',self.quick_payment)])
        day=today()
        apps=self.s.rows('SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE substr(starts,1,10)=? ORDER BY starts',(day,))
        collected=self.s.one('SELECT COALESCE(SUM(amount),0) n FROM payments WHERE date=?',(day,))['n']
        outstanding=sum(self.svc.invoice_totals(r['id'])['balance'] for r in self.s.rows('SELECT id FROM invoices'))
        cards=QHBoxLayout()
        for title,value in [('Today’s appointments',str(len(apps))),('Waiting patients',str(sum(r['status']=='arrived' for r in apps))),('Collected today',afn(collected)),('Outstanding balances',afn(outstanding))]:
            card=QFrame(); card.setObjectName('card'); cv=QVBoxLayout(card); cv.setContentsMargins(18,18,18,18); cv.addWidget(label(title,'subtitle')); cv.addWidget(label(value,'metric')); cards.addWidget(card)
        layout.addLayout(cards)
        layout.addWidget(label('Today’s appointments','brand'))
        self.table(layout,['Time','Patient','Status'],apps,[lambda r:r['starts'][11:16],'name',lambda r:tr(r['status'])],lambda r:self.patient_detail(r['patient_id']))
        tabs=QTabWidget(); layout.addWidget(tabs)
        datasets=[('Recent visits',self.s.rows('SELECT v.*,p.name FROM visits v JOIN patients p ON p.id=v.patient_id ORDER BY v.id DESC LIMIT 8'),['Patient','Date','Doctor'],['name',lambda r:self.date(r['date']),'doctor']),('Upcoming follow-ups',self.s.rows("SELECT v.*,p.name FROM visits v JOIN patients p ON p.id=v.patient_id WHERE followup>=? ORDER BY followup LIMIT 12",(day,)),['Patient','Follow-up'],['name',lambda r:self.date(r['followup'])]),('Low stock',self.s.rows('SELECT m.*,COALESCE(SUM(s.quantity),0) quantity FROM materials m LEFT JOIN stock s ON s.material_id=m.id GROUP BY m.id HAVING quantity<=minimum'),['Name','In stock','Minimum stock'],['name','quantity','minimum'])]
        for title,rows,heads,keys in datasets:
            t=Table(heads,rows,keys); tabs.addTab(t,tr(title))
        layout.addStretch()

    def choose_patient(self,title='Patient'):
        d=QDialog(self); d.setWindowTitle(tr(title)); d.resize(680,500); l=QVBoxLayout(d); search=QLineEdit(); search.setPlaceholderText(tr('Search patients')); l.addWidget(search)
        table=Table(['Patient number','Full name','Phone'],self.svc.search(),[lambda r:f"P-{r['id']:06}",'name','phone']); l.addWidget(table)
        def update():
            nonlocal table
            l.removeWidget(table); table.deleteLater(); table=Table(['Patient number','Full name','Phone'],self.svc.search(search.text()),[lambda r:f"P-{r['id']:06}",'name','phone']); l.insertWidget(1,table); table.cellDoubleClicked.connect(d.accept)
        search.textChanged.connect(update); table.cellDoubleClicked.connect(d.accept)
        l.addWidget(self.act('Continue',d.accept)); l.addWidget(button('Cancel',d.reject))
        if d.exec()==QDialog.Accepted: return table.selected()['id']
        return None

    def quick_visit(self):
        pid=self.choose_patient('New visit')
        if pid: self.new_visit(pid)

    def quick_payment(self):
        pid=self.choose_patient('Record payment')
        if pid: self.patient_detail(pid,1)

    def patient_list(self,term=''):
        layout=self.page('Patients')
        self.actions(layout,[('New patient',self.new_patient,True),('Active patients' if self.archived else 'Archived patients',self.toggle_archived)])
        self.patient_offset=getattr(self,'patient_offset',0) if term==getattr(self,'last_term',None) else 0; self.last_term=term
        rows=self.svc.search(term,self.archived,100,self.patient_offset)
        self.table(layout,['Patient number','Full name','Phone','Clinical alerts'],rows,[lambda r:f"P-{r['id']:06}",'name','phone','alerts'],lambda r:self.patient_detail(r['id']))
        self.actions(layout,[('Previous period',lambda:self.patient_page(-100,term)),('Continue',lambda:self.patient_page(100,term))])
        layout.addStretch()

    def patient_page(self,delta,term): self.patient_offset=max(0,self.patient_offset+delta); self.patient_list(term)
    def toggle_archived(self): self.archived=not self.archived; self.patient_offset=0; self.patient_list(self.search.text())

    def new_patient(self): self.edit_patient()

    def edit_patient(self,pid=None):
        self.svc.allowed()
        initial=self.s.one('SELECT * FROM patients WHERE id=?',(pid,)) if pid else None
        fields=PATIENT_FIELDS if self.svc.user['role']=='admin' else [f for f in PATIENT_FIELDS if f[0] not in ('history','allergies','medications','alerts','consent')]
        v=self.form('Edit patient' if pid else 'New patient',fields,initial)
        if v and initial and self.svc.user['role']!='admin':
            for key in ('history','allergies','medications','alerts','consent'):v[key]=initial[key]
        if not v: return
        dup=self.svc.duplicates(v['name'],v['phone'],pid or 0)
        if dup and not self.confirm('A similar record exists. Save another record?'): return
        pid=self.svc.save_patient(v,pid); self.patient_detail(pid); self.statusBar().showMessage(tr('Saved successfully'),4000)

    def patient_detail(self,pid,tab=0):
        self.svc.allowed(); self.current='detail'; self.pid=pid
        for name,b in self.nav.items():b.setChecked(name=='Patients')
        p=self.s.one('SELECT * FROM patients WHERE id=?',(pid,))
        layout=self.page(p['name'],f"P-{pid:06}   ·   {p['phone']}   ·   {p['address']}")
        if p['alerts'] or p['allergies']: layout.addWidget(label(tr('Clinical alerts')+': '+p['alerts']+'   '+tr('Allergies')+': '+p['allergies'],'alert'))
        photo=self.s.setting(f'patient_photo_{pid}')
        if photo:
            image=QLabel();image.setPixmap(QPixmap(str(self.s.root/'attachments'/photo)).scaled(80,80,Qt.KeepAspectRatio,Qt.SmoothTransformation));layout.addWidget(image)
        self.actions(layout,[('New visit',lambda:self.new_visit(pid),True),('Edit patient',lambda:self.edit_patient(pid)),('Patient photograph',lambda:self.patient_photo(pid)),('Restore patient' if p['archived'] else 'Archive',lambda:self.archive_patient(p))])
        tabs=QTabWidget(); layout.addWidget(tabs,1)
        for title,fn in [('Visits & dental chart',self.clinical_tab),('Billing',self.billing_tab),('Medical history',self.history_tab),('Documents',self.documents_tab),('Prescriptions',self.prescriptions_tab)]:
            w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,16,0,0); l.setSpacing(14);
            if self.svc.user['role']!='admin' and title!='Billing':continue
            fn(l,p); tabs.addTab(w,tr(title))
        tabs.setCurrentIndex(tab if self.svc.user['role']=='admin' else 0)

    def patient_photo(self,pid):
        self.svc.allowed(clinical=True)
        path,_=QFileDialog.getOpenFileName(self,tr('Choose image'),'','Images (*.png *.jpg *.jpeg)')
        if path:
            self.attach_file(path,pid,lambda meta:(self.s.set_setting(f'patient_photo_{pid}',meta[-1]['stored']),self.patient_detail(pid)),True)

    def archive_patient(self,p):
        if self.confirm('Archive this patient? Their records will be preserved.'):
            self.svc.archive(p['id'],not p['archived']); self.patient_detail(p['id'])

    def history_tab(self,l,p):
        for key,title,_,_ in PATIENT_FIELDS[4:]:
            l.addWidget(label(title,'brand')); l.addWidget(label((self.date(p[key]) if key=='dob' and p[key] else p[key]) or 'Not supplied'))
        l.addStretch()

    def clinical_tab(self,l,p):
        visits=self.s.rows('SELECT * FROM visits WHERE patient_id=? ORDER BY id DESC',(p['id'],))
        treatments=self.s.rows('SELECT t.*,v.date,v.doctor FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE v.patient_id=? ORDER BY t.id DESC',(p['id'],))
        bar=QHBoxLayout(); self.visit_choice=QComboBox(); self.visit_choice.setLayoutDirection(Qt.LeftToRight)
        for v in visits: self.visit_choice.addItem(f"V-{v['id']} · {self.date(v['date'])} · {v['doctor']}",v['id'])
        bar.addWidget(self.visit_choice,1); bar.addWidget(self.act('Add treatment',self.add_treatment,True)); bar.addWidget(self.act('Issue invoice',self.issue_invoice)); l.addLayout(bar)
        dentition=QComboBox(); dentition.addItem(tr('Permanent teeth'),False); dentition.addItem(tr('Primary teeth'),True); l.addWidget(dentition)
        chart=QWidget(); chart.setFixedHeight(100); grid=QGridLayout(chart); grid.setSpacing(5)
        def draw():
            while grid.count():
                item=grid.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            rows=CHILD if dentition.currentData() else ADULT
            for row,teeth in enumerate(rows):
                for col,tooth in enumerate(teeth):
                    b=self.act(str(tooth),lambda t=tooth:self.add_treatment(str(t)))
                    b.setMinimumWidth(34); b.setMinimumHeight(44); b.setStyleSheet('padding:5px;border-radius:12px 12px 8px 8px;')
                    relevant=[r for r in treatments if r['tooth']==str(tooth)]
                    if relevant:
                        color='#dfb25a' if any(r['status']=='planned' for r in relevant) else '#149a96'
                        b.setStyleSheet(f'padding:5px;border:2px solid {color};border-radius:12px 12px 8px 8px;')
                        b.setToolTip('\n'.join(tr(r['procedure'])+' · '+tr(r['status']) for r in relevant))
                    grid.addWidget(b,row,col)
            chart.setLayoutDirection(Qt.LeftToRight)
        dentition.currentIndexChanged.connect(draw); draw()
        l.addWidget(label('Patient right → left','subtitle')); l.addWidget(label('Upper jaw','subtitle')); l.addWidget(chart); l.addWidget(label('Lower jaw','subtitle')); l.addWidget(label('Select a tooth to record work. Teal: completed · Amber: planned.','subtitle'))
        self.treatment_table=self.table(l,['Treatment number','Date','Tooth','Procedure','Price','Status'],treatments,['id',lambda r:self.date(r['date']),'tooth','procedure',lambda r:afn(r['price']),'status'],self.treatment_details)
        self.actions(l,[('Complete treatment',self.complete_treatment)])
        vt=Table(['Date','Notes','Follow-up'],visits,[lambda r:self.date(r['date']),'notes',lambda r:self.date(r['followup'])]); l.addWidget(vt)

    def new_visit(self,pid):
        self.svc.allowed(clinical=True)
        v=self.form('New visit',[('doctor','Doctor','line',self.s.setting('display_dari' if i18n.LANG=='fa_AF' else 'display_english','داکتر فرشاد فرامرز' if i18n.LANG=='fa_AF' else 'Dr. Farshad Faramarz')),('date','Date','date',today()),('notes','Notes','text',''),('followup','Follow-up','date_optional','')])
        if v:
            self.svc.visit(pid,**v); self.patient_detail(pid)

    def add_treatment(self,tooth=''):
        self.svc.allowed(clinical=True)
        vid=self.visit_choice.currentData()
        if not vid: raise ValueError('Choose a record first')
        catalogue=self.s.rows('SELECT * FROM catalogue ORDER BY name')
        v=self.form('Add treatment',[('procedure','Procedure',[(r['name'],r['name']) for r in catalogue],catalogue[0]['name']),('price','Price','money','0.00'),('tooth','Tooth',['']+[str(n) for row in ADULT+CHILD for n in row],tooth),('condition','Condition','line',''),('status','Status',['planned','completed'],'planned'),('notes','Notes','text','')])
        if v:
            self.svc.treatment(vid,price=money(v.pop('price')),**v); self.patient_detail(self.pid)

    def complete_treatment(self):
        t=self.treatment_table.selected(); self.svc.complete(t['id']); self.patient_detail(self.pid)

    def issue_invoice(self):
        vid=self.visit_choice.currentData()
        if not vid: raise ValueError('Choose a record first')
        v=self.form('Issue invoice',[('discount','Discount','money','0.00')])
        if v:
            self.svc.invoice(vid,money(v['discount'])); self.patient_detail(self.pid,1)

    def billing_tab(self,l,p):
        invoices=self.s.rows('SELECT * FROM invoices WHERE patient_id=? ORDER BY id DESC',(p['id'],))
        for inv in invoices: inv.update(self.svc.invoice_totals(inv['id']))
        self.invoice_table=self.table(l,['Invoice number','Date','Total','Paid','Remaining','Status'],invoices,[lambda r:f"INV-{r['id']:06}",lambda r:self.date(r['date']),lambda r:afn(r['total']),lambda r:afn(r['paid']),lambda r:afn(r['balance']),lambda r:tr('cancelled') if r['void'] else '—'])
        self.actions(l,[('Record payment',self.pay,True),('Issue invoice',self.billing_invoice),('Refund',lambda:self.pay(True)),('Print / PDF',self.print_invoice),('Void invoice',self.void)])
        payments=self.s.rows('SELECT pay.* FROM payments pay JOIN invoices i ON i.id=pay.invoice_id WHERE i.patient_id=? ORDER BY pay.id DESC',(p['id'],))
        l.addWidget(label('Payment history','brand'))
        self.payment_table=self.table(l,['Receipt number','Invoice number','Date','Amount','Method','Reason'],payments,[lambda r:f"R-{r['id']:06}",lambda r:f"INV-{r['invoice_id']:06}",lambda r:self.date(r['date']),lambda r:afn(r['amount']),'method','reason'],lambda r:PrintDialog(invoice_html(self.svc,r['invoice_id'],r['id']),self).exec())
        self.actions(l,[('Receipt',self.print_receipt)])

    def billing_invoice(self):
        visits=self.s.rows("SELECT * FROM visits WHERE patient_id=? ORDER BY id DESC",(self.pid,))
        v=self.form('Issue invoice',[('visit','New visit',[(r['id'],f"V-{r['id']} · {self.date(r['date'])}") for r in visits],visits[0]['id'] if visits else None),('discount','Discount','money','0.00')])
        if v and v['visit']:self.svc.invoice(v['visit'],money(v['discount']));self.patient_detail(self.pid,1)

    def treatment_details(self,r):
        self.svc.allowed(clinical=True)
        d=QDialog(self);d.resize(550,450);d.setWindowTitle(tr('Procedure'));l=QVBoxLayout(d)
        for key,title in [('procedure','Procedure'),('tooth','Tooth'),('condition','Condition'),('status','Status'),('doctor','Doctor'),('notes','Notes')]:
            l.addWidget(label(title,'brand'));l.addWidget(label(r[key] or 'Not supplied'))
        l.addWidget(button('Close',d.accept));d.exec()

    def pay(self,refund=False):
        inv=self.invoice_table.selected()
        v=self.form('Refund' if refund else 'Record payment',[('amount','Amount','money',amount_text((inv['paid'] if refund else inv['balance']))),('method','Method',['Cash','Other'],'Cash'),('reason','Reason','line','')])
        if v:
            amount=money(v.pop('amount')); receipt=self.svc.payment(inv['id'],-amount if refund else amount,**v)
            self.patient_detail(self.pid,1); PrintDialog(invoice_html(self.svc,inv['id'],receipt),self).exec()

    def void(self):
        inv=self.invoice_table.selected(); v=self.form('Void invoice',[('reason','Reason','text','')])
        if v: self.svc.void_invoice(inv['id'],v['reason']); self.patient_detail(self.pid,1)

    def print_invoice(self): PrintDialog(invoice_html(self.svc,self.invoice_table.selected()['id']),self).exec()
    def print_receipt(self):
        r=self.payment_table.selected(); PrintDialog(invoice_html(self.svc,r['invoice_id'],r['id']),self).exec()

    def documents_tab(self,l,p=None):
        pid=p['id'] if p else None
        rows=self.s.rows('SELECT * FROM attachments WHERE patient_id=?' if pid else "SELECT * FROM attachments WHERE scope='profile'",(pid,) if pid else ())
        table=self.table(l,['Name','Type'],rows,['name','scope'])
        def add():
            self.svc.allowed(clinical=bool(pid),admin=not pid)
            path,_=QFileDialog.getOpenFileName(self,tr('Add document'))
            if path:self.attach_file(path,pid,lambda _:self.patient_detail(pid,3) if pid else self.profile())
        def open_doc():
            self.svc.allowed(clinical=bool(pid),admin=not pid)
            r=table.selected(); QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.s.root/'attachments'/r['stored'])))
        self.actions(l,[('Add document',add,True),('Open document',open_doc)])

    def prescriptions_tab(self,l,p):
        rows=self.s.rows('SELECT * FROM prescriptions WHERE patient_id=? ORDER BY id DESC',(p['id'],))
        table=self.table(l,['Date','Prescription','Aftercare instructions'],rows,[lambda r:self.date(r['date']),'content','aftercare'])
        def add():
            self.svc.allowed(clinical=True)
            v=self.form('Write prescription',[('content','Prescription','text',''),('aftercare','Aftercare instructions','text','')])
            if v:
                self.svc.add_record('prescriptions',dict(patient_id=p['id'],date=today(),**v),clinical=True); self.patient_detail(p['id'],4)
        def print_rx():
            self.svc.allowed(clinical=True); r=table.selected()
            PrintDialog(document_html(self.svc,'Prescription',p,[(tr('Date'),self.date(r['date'])),(tr('Prescription'),r['content']),(tr('Aftercare instructions'),r['aftercare'])]),self).exec()
        l.addWidget(label('Doctor-written instructions only.','subtitle')); self.actions(l,[('Write prescription',add,True),('Print / PDF',print_rx)])

    def appointments(self):
        layout=self.page('Appointments')
        controls=QHBoxLayout(); agenda_value=getattr(self,'agenda_date',today())
        if self.s.setting('calendar')=='solar':
            import jdatetime
            j=jdatetime.date.fromgregorian(date=date.fromisoformat(agenda_value));agenda_value=f'{j.year:04}/{j.month:02}/{j.day:02}'
        self.app_day=QLineEdit(agenda_value); self.app_day.setLayoutDirection(Qt.LeftToRight)
        controls.addWidget(self.app_day); view=QComboBox(); view.addItems([tr('Agenda'),tr('Day'),tr('Week')]); view.setCurrentIndex(getattr(self,'agenda_mode',0)); controls.addWidget(view)
        def apply():
            self.agenda_date=parse_date(self.app_day.text(),self.s.setting('calendar')=='solar'); self.agenda_mode=view.currentIndex(); self.appointments()
        controls.addWidget(self.act('Apply',apply)); controls.addWidget(self.act('Add appointment',self.add_appointment,True)); controls.addWidget(self.act('Walk-in',lambda:self.add_appointment(True))); layout.addLayout(controls)
        start=getattr(self,'agenda_date',today()); mode=getattr(self,'agenda_mode',0)
        end=(date.fromisoformat(start)+timedelta(days=6 if mode==2 else 0)).isoformat()
        rows=self.s.rows('SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE substr(starts,1,10) BETWEEN ? AND ? ORDER BY starts',(start,end))
        if mode==2:
            week=QHBoxLayout()
            for offset in range(7):
                day=(date.fromisoformat(start)+timedelta(days=offset)).isoformat(); card=QFrame(); card.setObjectName('card'); col=QVBoxLayout(card); col.addWidget(label(self.date(day),'subtitle'))
                for r in rows:
                    if r['starts'][:10]==day:
                        col.addWidget(self.act(r['starts'][11:16]+'\n'+r['name'],lambda pid=r['patient_id']:self.patient_detail(pid)))
                col.addStretch(); week.addWidget(card)
            layout.addLayout(week)
        elif mode==1:
            for r in rows:
                layout.addWidget(self.act(r['starts'][11:16]+'  ·  '+r['name']+'  ·  '+tr(r['status']),lambda pid=r['patient_id']:self.patient_detail(pid)))
        table=self.table(layout,['Date','Time','Patient','Duration (minutes)','Status'],rows,[lambda r:self.date(r['starts'][:10]),lambda r:r['starts'][11:16],'name','minutes','status'],lambda r:self.patient_detail(r['patient_id']))
        def change():
            r=table.selected(); v=self.form('Change status',[('status','Status',['scheduled','arrived','in treatment','completed','cancelled','missed'],r['status'])])
            if v: self.svc.status(r['id'],v['status']); self.appointments()
        def visit(): self.new_visit(table.selected()['patient_id'])
        self.actions(layout,[('Change status',change),('New visit',visit),('Record payment',lambda:self.patient_detail(table.selected()['patient_id'],1))]); layout.addStretch()

    def add_appointment(self,walkin=False):
        pid=self.choose_patient('Walk-in' if walkin else 'Add appointment')
        if not pid:return
        v=self.form('Add appointment',[('date','Date','date',today()),('time','Time','line',datetime.fromisoformat(now()).strftime('%H:%M')),('minutes','Duration (minutes)','int',30),('notes','Notes','text','')])
        if v:
            starts=v.pop('date')+'T'+v.pop('time'); kwargs=dict(pid=pid,starts=starts,status='arrived' if walkin else 'scheduled',**v)
            try:self.svc.appointment(**kwargs)
            except ValueError as e:
                if 'conflicts' in str(e) and self.confirm('Allow this overlap?'): self.svc.appointment(**kwargs,override=True)
                else:raise
            self.appointments()

    def materials(self):
        layout=self.page('Materials'); self.actions(layout,[('Add material',self.add_material,True),('Stock movement',self.move_stock)])
        rows=self.s.rows('SELECT m.*,COALESCE(SUM(s.quantity),0) quantity FROM materials m LEFT JOIN stock s ON m.id=s.material_id GROUP BY m.id ORDER BY m.name')
        self.material_table=self.table(layout,['Name','Unit','In stock','Minimum stock'],rows,['name','unit','quantity','minimum'])
        layout.addWidget(label('Near-expiry batches','brand'))
        expiry=(date.fromisoformat(today())+timedelta(days=60)).isoformat()
        self.table(layout,['Name','Batch','Expiry','Quantity'],self.s.rows("SELECT m.name,s.batch,s.expiry,SUM(s.quantity) quantity FROM stock s JOIN materials m ON m.id=s.material_id WHERE s.expiry<>'' AND s.expiry<=? GROUP BY m.id,s.batch,s.expiry HAVING quantity>0 ORDER BY s.expiry",(expiry,)),['name','batch',lambda r:self.date(r['expiry']),'quantity'])
        layout.addStretch()

    def add_material(self):
        v=self.form('Add material',[('name','Name','line',''),('unit','Unit','line',''),('minimum','Minimum stock','int',0)])
        if v:
            if not v['name'] or not v['unit']:raise ValueError('Please check your entry')
            self.svc.add_record('materials',v);self.materials()

    def move_stock(self):
        self.svc.allowed(admin=True); material=self.material_table.selected()
        batches=self.s.rows('SELECT batch,expiry,SUM(quantity) quantity FROM stock WHERE material_id=? GROUP BY batch,expiry HAVING quantity>0',(material['id'],))
        choices=[('', 'Not supplied')]+[(json.dumps([r['batch'],r['expiry']]),(r['batch'] or '—')+' · '+self.date(r['expiry'])+' · '+str(r['quantity'])) for r in batches]
        v=self.form('Stock movement',[('quantity','Quantity','int',-1),('kind','Type',['use','wastage','return','adjustment'],'use'),('existing_batch','Batch',choices,choices[1][0] if len(choices)>1 else ''),('batch','Batch','line',''),('expiry','Expiry','date_optional',''),('reason','Reason','line',''),('treatment_id','Treatment number (optional)','line','')])
        if v:
            selected_batch=v.pop('existing_batch')
            if selected_batch:v['batch'],v['expiry']=json.loads(selected_batch)
            v['treatment_id']=int(v['treatment_id']) if v['treatment_id'] else None
            if v['quantity']<0 and not self.confirm('Confirm stock deduction? This can only be applied once per treatment and material.'):return
            self.svc.stock(material['id'],**v);self.materials()

    def purchases(self):
        layout=self.page('Purchases');self.actions(layout,[('Record purchase',self.add_purchase,True),('Add supplier',self.add_supplier)])
        rows=self.s.rows('SELECT p.*,s.name,COALESCE(SUM(i.quantity*i.unit_cost),0) total FROM purchases p JOIN suppliers s ON s.id=p.supplier_id LEFT JOIN purchase_items i ON i.purchase_id=p.id GROUP BY p.id ORDER BY p.id DESC')
        self.purchase_table=self.table(layout,['Purchase number','Date','Supplier','Total','Paid','Supplier balance'],rows,['id',lambda r:self.date(r['date']),'name',lambda r:afn(r['total']),lambda r:afn(r['paid']),lambda r:afn(r['total']-r['paid'])],self.purchase_detail)
        self.actions(layout,[('Record payment',self.pay_supplier)])
        layout.addWidget(label('Supplier','brand'))
        self.table(layout,['Name','Phone','Address'],self.s.rows('SELECT * FROM suppliers ORDER BY name'),['name','phone','address']);layout.addStretch()

    def add_supplier(self):
        v=self.form('Add supplier',[('name','Name','line',''),('phone','Phone','phone',''),('address','Address','line','')])
        if v:
            if not v['name']:raise ValueError('Please check your entry')
            self.svc.add_record('suppliers',v);self.purchases()

    def add_purchase(self):
        self.svc.allowed(admin=True)
        suppliers=self.s.rows('SELECT * FROM suppliers ORDER BY name'); materials=self.s.rows('SELECT * FROM materials ORDER BY name')
        if not suppliers or not materials:raise ValueError('Choose a record first')
        d=QDialog(self);d.setWindowTitle(tr('Record purchase'));d.resize(800,580);layout=QVBoxLayout(d)
        supplier=QComboBox()
        for r in suppliers:supplier.addItem(r['name'],r['id'])
        layout.addWidget(label('Supplier'));layout.addWidget(supplier);items=[]
        table=Table(['Name','Quantity','Unit cost','Batch','Expiry'],[],['name','quantity',lambda r:afn(r['unit_cost']),'batch','expiry']);layout.addWidget(table)
        def redraw():
            nonlocal table
            layout.removeWidget(table);table.deleteLater();table=Table(['Name','Quantity','Unit cost','Batch','Expiry'],items,['name','quantity',lambda r:afn(r['unit_cost']),'batch',lambda r:self.date(r['expiry'])]);layout.insertWidget(2,table)
        def add():
            v=self.form('Add item',[('material_id','Materials',[(r['id'],r['name']) for r in materials],materials[0]['id']),('quantity','Quantity','int',1),('unit_cost','Unit cost','money','0.00'),('batch','Batch','line',''),('expiry','Expiry','date_optional','')])
            if v:
                if v['quantity']<=0:raise ValueError('Please check your entry')
                v['unit_cost']=money(v['unit_cost']);v['name']=next(r['name'] for r in materials if r['id']==v['material_id']);items.append(v);redraw()
        def remove():
            table.selected();items.pop(table.currentRow());redraw()
        self.actions(layout,[('Add item',add),('Remove item',remove)])
        paid=QLineEdit('0.00');paid.setLayoutDirection(Qt.LeftToRight);layout.addWidget(label('Paid amount'));layout.addWidget(paid)
        def save():self.svc.purchase(supplier.currentData(),items,money(paid.text()));d.accept();self.purchases()
        self.actions(layout,[('Save',save,True),('Cancel',d.reject)]);d.exec()

    def pay_supplier(self):
        r=self.purchase_table.selected()
        v=self.form('Record payment',[('amount','Amount','money',amount_text((r['total']-r['paid'])))])
        if v:self.svc.supplier_payment(r['id'],money(v['amount']));self.purchases()

    def purchase_detail(self,p):
        rows=self.s.rows('SELECT i.*,m.name FROM purchase_items i JOIN materials m ON m.id=i.material_id WHERE purchase_id=?',(p['id'],))
        d=QDialog(self);d.resize(800,450);d.setWindowTitle(tr('Purchase items'));l=QVBoxLayout(d);self.table(l,['Name','Quantity','Unit cost','Batch','Expiry'],rows,['name','quantity',lambda r:afn(r['unit_cost']),'batch',lambda r:self.date(r['expiry'])]);l.addWidget(button('Close',d.accept));d.exec()

    def expenses(self):
        layout=self.page('Expenses');self.actions(layout,[('Add expense',self.add_expense,True)])
        rows=self.s.rows('SELECT * FROM expenses ORDER BY date DESC,id DESC LIMIT 500')
        self.table(layout,['Date','Category','Amount','Notes'],rows,[lambda r:self.date(r['date']),'category',lambda r:afn(r['amount']),'notes']);layout.addStretch()

    def add_expense(self):
        v=self.form('Add expense',[('date','Date','date',today()),('category','Category',['Rent','Electricity','Salaries','Maintenance','Laboratory costs','Other'],'Other'),('amount','Amount','money','0.00'),('notes','Notes','text','')])
        if v:v['amount']=money(v['amount']);self.svc.add_record('expenses',v);self.expenses()

    def labs(self):
        layout=self.page('Laboratory');self.actions(layout,[('Add lab case',self.add_lab,True)])
        rows=self.s.rows('SELECT l.*,p.name FROM labs l JOIN patients p ON p.id=l.patient_id ORDER BY l.id DESC LIMIT 500')
        table=self.table(layout,['Patient','Laboratory','Description','Expected return','Status','Cost','Paid'],rows,['name','laboratory','description',lambda r:self.date(r['expected']),'status',lambda r:afn(r['cost']),lambda r:afn(r['paid'])])
        def update():
            self.svc.allowed(admin=True);r=table.selected();v=self.form('Update case',[('status','Status',['sent','returned','delayed','cancelled'],r['status']),('returned','Actual return','date_optional',r['returned']),('paid','Paid amount','money',amount_text(r['paid']))])
            if v:
                v['paid']=money(v['paid'])
                self.svc.update_lab(r['id'],v['status'],v['returned'],v['paid'])
                self.labs()
        self.actions(layout,[('Update case',update)]);layout.addStretch()

    def add_lab(self):
        self.svc.allowed(admin=True);pid=self.choose_patient('Add lab case')
        if not pid:return
        treatments=self.s.rows('SELECT t.* FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE v.patient_id=?',(pid,))
        v=self.form('Add lab case',[('treatment_id','Procedure',[(None,'Not supplied')]+[(r['id'],str(r['id'])+' · '+r['procedure']) for r in treatments],None),('laboratory','Laboratory','line',''),('description','Description','text',''),('sent','Sent date','date',today()),('expected','Expected return','date',today()),('cost','Cost','money','0.00'),('paid','Paid amount','money','0.00')])
        if v:
            v['cost']=money(v['cost']);v['paid']=money(v['paid']);self.svc.add_record('labs',dict(patient_id=pid,status='sent',**v));self.labs()

    def reports(self):
        self.svc.allowed(admin=True)
        layout=self.page('Reports');start=getattr(self,'report_start',today()[:8]+'01');end=getattr(self,'report_end',today())
        def filter_dates():
            v=self.form('Reports',[('start','Start date','date',start),('end','End date','date',end)])
            if v:self.report_start=v['start'];self.report_end=v['end'];self.reports()
        self.actions(layout,[('Apply',filter_dates),('Export CSV',self.report_csv),('Print / PDF',self.print_report)])
        layout.addWidget(label(self.date(start)+' → '+self.date(end),'subtitle'))
        report=self.svc.report(start,end);days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
        previous_end=(date.fromisoformat(start)-timedelta(days=1)).isoformat();previous_start=(date.fromisoformat(start)-timedelta(days=days)).isoformat();previous=self.svc.report(previous_start,previous_end)
        names={'billed':'Billed','collected':'Collected','expenses':'Expenses','purchases':'Purchase payments','lab':'Lab payments','outstanding':'Outstanding balances','cash_surplus':'Cash surplus estimate'}
        self.report_rows=[{'metric':tr(names[k]),'amount':v,'previous':None if k=='outstanding' else previous[k]} for k,v in report.items()]
        self.table(layout,['Description','Current period','Previous period'],self.report_rows,['metric',lambda r:afn(r['amount']),lambda r:afn(r['previous']) if r['previous'] is not None else '—'])
        layout.addWidget(label('Cash surplus excludes unpaid liabilities and is not accounting profit.','subtitle'));layout.addStretch()

    def report_csv(self):
        self.svc.allowed(admin=True);path,_=QFileDialog.getSaveFileName(self,tr('Export CSV'),'report.csv','CSV (*.csv)')
        if path:
            with open(path,'w',newline='',encoding='utf-8-sig') as f:
                writer=csv.writer(f);writer.writerow([tr('Description'),tr('Current period'),tr('Previous period')]);writer.writerows([[r['metric'],amount_text(r['amount']),'' if r['previous'] is None else amount_text(r['previous'])] for r in self.report_rows])
            with self.svc.action('report exported',path,admin=True):pass

    def print_report(self):
        self.svc.allowed(admin=True)
        html='<html dir="'+('rtl' if i18n.LANG=='fa_AF' else 'ltr')+'"><body style="font-family:Noto Sans Arabic"><h1>'+escape(self.s.setting('clinic_name','Faramarz Dental Clinic'))+'</h1><h2>'+tr('Reports')+'</h2><p>'+self.date(getattr(self,'report_start',today()[:8]+'01'))+' — '+self.date(getattr(self,'report_end',today()))+'</p><table>'+''.join('<tr><td>'+escape(r['metric'])+'</td><td>'+afn(r['amount'])+'</td></tr>' for r in self.report_rows)+'</table><p>'+tr('Cash surplus excludes unpaid liabilities and is not accounting profit.')+'</p></body></html>'
        PrintDialog(html,self).exec()

    def profile(self):
        layout=self.page('Clinic profile');self.svc.allowed(admin=True)
        photo=self.s.setting('profile_photo')
        if photo and (self.s.root/'attachments'/photo).exists():
            image=QLabel();image.setPixmap(QPixmap(str(self.s.root/'attachments'/photo)).scaled(140,140,Qt.KeepAspectRatio,Qt.SmoothTransformation));layout.addWidget(image)
        background=self.s.setting('clinic_background')
        if background and (self.s.root/'attachments'/background).exists():
            image=QLabel();image.setPixmap(QPixmap(str(self.s.root/'attachments'/background)).scaled(360,120,Qt.KeepAspectRatio,Qt.SmoothTransformation));layout.addWidget(image)
        fields=[('display_english','Display name (English)','line','Dr. Farshad Faramarz'),('display_dari','Display name (Dari)','line','داکتر فرشاد فرامرز'),('clinic_name','Clinic name','line','Faramarz Dental Clinic'),('clinic_address','Clinic address','line','Khair Khana, District 11, Kabul, Afghanistan'),('clinic_phone','Phone','phone',''),('biography','Biography','text',''),('education','Education & qualifications','text',''),('experience','Experience','text',''),('specialties','Specialties','text',''),('hours','Working hours','text','')]
        def edit():
            v=self.form('Clinic profile',fields,{k:self.s.setting(k,default) for k,_,_,default in fields})
            if v:
                with self.svc.action('clinic profile edited','',admin=True) as db:
                    db.executemany('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',list(v.items()))
                self.profile()
        def image(key):
            path,_=QFileDialog.getOpenFileName(self,tr('Choose image'),'','Images (*.png *.jpg *.jpeg)')
            if path:
                self.attach_file(path,None,lambda meta:(self.s.set_setting(key,meta[-1]['stored']),self.profile()),True)
        self.actions(layout,[('Clinic profile',edit,True),('Profile photograph',lambda:image('profile_photo')),('Clinic logo',lambda:image('clinic_logo')),('Clinic background',lambda:image('clinic_background'))])
        for key,title,_,default in fields:
            layout.addWidget(label(title,'brand'));layout.addWidget(label(self.s.setting(key,default) or 'No information supplied'))
        layout.addWidget(label('Profile documents & images','brand'));self.documents_tab(layout)

    def settings(self):
        self.svc.allowed(admin=True);layout=self.page('Settings')
        layout.addWidget(label('Dari wording is provisional; please review with the clinic.','subtitle'))
        def display():
            v=self.form('Settings',[('theme','Theme',[('light','Light'),('dark','Dark'),('system','System')],self.s.setting('theme','system')),('calendar','Calendar',[('gregorian','Gregorian'),('solar','Solar Hijri')],self.s.setting('calendar','gregorian'))])
            if v:
                for k,value in v.items():self.s.set_setting(k,value)
                self.apply_theme();self.settings()
        def folder():
            path=QFileDialog.getExistingDirectory(self,tr('Choose folder'),self.s.setting('backup_folder',str(Path.home())))
            if path:self.s.set_setting('backup_folder',path);self.settings()
        def schedule():
            v=self.form('Backup now',[('scheduled','Daily backup while app is open','bool',self.s.setting('scheduled')=='True'),('retention','Retention (backups)','int',int(self.s.setting('retention','14')))])
            if v:
                if not 1<=v['retention']<=365:raise ValueError('Please check your entry')
                for k,value in v.items():self.s.set_setting(k,value)
                self.settings()
        self.actions(layout,[('Theme',display),('Choose folder',folder),('Daily backup while app is open',schedule)])
        layout.addWidget(label(tr('Backup folder')+': '+self.s.setting('backup_folder','Not supplied'),'subtitle'))
        self.actions(layout,[('Backup now',self.backup,True),('Restore backup',self.restore),('Add account',self.add_account),('Change password',self.change_password)])
        layout.addWidget(label('Local accounts restrict access in this app. The database and backups are not encrypted. Use operating-system disk encryption and protect backup drives.','subtitle'))
        catalogue=self.s.rows('SELECT * FROM catalogue ORDER BY name');layout.addWidget(label('Treatment catalogue','brand'));ct=self.table(layout,['Procedure','Price'],catalogue,['name',lambda r:afn(r['price'])])
        def add():
            v=self.form('Add procedure',[('name','Procedure','line',''),('price','Price','money','0.00')])
            if v:
                if not v['name']:raise ValueError('Please check your entry')
                v['price']=money(v['price']);self.svc.add_record('catalogue',v);self.settings()
        def price():
            r=ct.selected();v=self.form('Edit price',[('name','Procedure','line',r['name']),('price','Price','money',amount_text(r['price']))])
            if v:
                with self.svc.action('catalogue edited',r['id'],admin=True) as db:db.execute('UPDATE catalogue SET name=?,price=? WHERE id=?',(v['name'],money(v['price']),r['id']))
                self.settings()
        self.actions(layout,[('Add procedure',add),('Edit price',price)])
        layout.addWidget(label('Audit history','brand'))
        self.table(layout,['Date','Actor','Action','Details'],self.s.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 200'),['at','actor','action','details'])

    def add_account(self):
        v=self.form('Add account',[('username','Username','line',''),('password','Password','password',''),('role','Role',['receptionist','admin'],'receptionist')])
        if v:self.svc.register(**v);self.statusBar().showMessage(tr('Saved successfully'),4000)

    def change_password(self):
        from .domain import password_hash,password_verify
        v=self.form('Change password',[('current','Current password','password',''),('new','New password','password',''),('confirm','Confirm password','password','')])
        if v:
            user=self.s.one('SELECT * FROM users WHERE id=?',(self.svc.user['id'],))
            if not password_verify(v['current'],user['password']):raise ValueError('Incorrect username or password')
            if v['new']!=v['confirm']:raise ValueError('Passwords do not match')
            hashed=password_hash(v['new'])
            with self.svc.action('password changed','',admin=True) as db:db.execute('UPDATE users SET password=? WHERE id=?',(hashed,user['id']))
            self.statusBar().showMessage(tr('Saved successfully'),4000)

    def attach_file(self,path,pid,callback,thumbnail=False):
        self.svc.allowed(clinical=pid is not None,admin=pid is None)
        from .service import prepare_attachment
        def done(records):
            try:
                for record in records:self.svc.record_attachment(record,pid)
                callback(records)
            except Exception as e:self.error(str(e))
        self.background(lambda:prepare_attachment(self.s.root,path,thumbnail),done)

    def background(self,fn,callback):
        progress=QProgressDialog(tr('Working…'),'',0,0,self);progress.setCancelButton(None);progress.setWindowModality(Qt.ApplicationModal);progress.setMinimumDuration(0);progress.show()
        job=Job(fn);self.jobs.append(job)
        state={}
        job.done.connect(lambda value:state.update(result=value))
        job.failed.connect(lambda message:state.update(error=message))
        def finish():
            self.jobs.remove(job);progress.close()
            if 'error' in state:self.error(state['error'])
            else:self.guard(lambda:callback(state.get('result')))
            job.deleteLater()
        job.finished.connect(finish);job.start()

    def backup(self,scheduled=False):
        self.svc.allowed(admin=True)
        if self.jobs:return
        destination=self.s.setting('backup_folder')
        if not destination:
            destination=QFileDialog.getExistingDirectory(self,tr('Choose folder'))
            if not destination:return
            self.s.set_setting('backup_folder',destination)
        with self.svc.action('backup requested',destination,admin=True):pass
        root=self.s.root;keep=int(self.s.setting('retention','14'))
        def work():
            path=create_backup(root,destination);apply_retention(destination,keep);return path
        def finished(path):
            self.s.set_setting('last_backup',today());self.statusBar().showMessage(tr('Backup completed')+': '+str(path),15000)
        self.background(work,finished)

    def scheduled_backup(self):
        if self.svc.user and self.svc.user['role']=='admin' and self.s.setting('scheduled')=='True' and self.s.setting('backup_folder') and self.s.setting('last_backup')!=today() and not self.jobs:
            self.guard(lambda:self.backup(True))

    def restore(self):
        self.svc.allowed(admin=True)
        if self.jobs:return
        path,_=QFileDialog.getOpenFileName(self,tr('Restore backup'),'','Faramarz backup (*.fdbackup)')
        if not path or not self.confirm('Restore replaces all records, files, settings and accounts. A safety backup is made first. Continue?'):return
        # UI is blocked during replacement; validation and archive I/O run in worker.
        from .storage import Store
        root=self.s.root
        self.s.db.close()
        def work():
            worker_store=Store(root)
            try:return restore_backup(worker_store,path)
            finally:
                try:worker_store.db.close()
                except Exception:pass
        def finished(safety):
            self.s=Store(root);self.svc.s=self.s;self.s.migrate();self.svc.user=None
            self.build();self.lock()
        def recover():
            if self.s.db:
                try:self.s.db.execute('SELECT 1')
                except Exception:self.s=Store(root);self.svc.s=self.s
        # Failed restores reconnect the current profile before editing resumes.
        self.background(work,finished)
        self.jobs[-1].failed.connect(lambda *_:recover())

    def lock(self):
        if self.jobs:return
        self.svc.user=None;self.centralWidget().hide()
        if authenticate(self.svc,self):
            self.current='Overview';self.pid=None;self.build()
        else:self.close()

    def closeEvent(self,event):
        if self.jobs:event.ignore();return
        self.s.db.close();event.accept()


def authenticate(service,parent=None):
    first=not service.s.rows('SELECT id FROM users')
    d=QDialog(parent);d.setWindowTitle('Faramarz Dental Clinic');d.setMinimumWidth(440)
    d.resize(500,min(690,QApplication.primaryScreen().availableGeometry().height()-60))
    outer=QVBoxLayout(d);body=QWidget();l=QVBoxLayout(body);l.setContentsMargins(23,18,23,18);l.setSpacing(10)
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);outer.addWidget(scroll,1)
    l.addWidget(label('Welcome to your clinic','title'));l.addWidget(label('Create your private local account. Use at least 10 characters.' if first else 'Your records stay on this computer.','subtitle'))
    language=QComboBox();language.addItem('English','en');language.addItem('دری','fa_AF');language.setCurrentIndex(1 if i18n.LANG=='fa_AF' else 0);l.addWidget(language)
    l.addWidget(label('Username'));username=QLineEdit();username.setObjectName('username');l.addWidget(username)
    l.addWidget(label('Password'));password=QLineEdit();password.setObjectName('password');password.setEchoMode(QLineEdit.Password);l.addWidget(password)
    repeat=None
    if first:
        l.addWidget(label('Confirm password'));repeat=QLineEdit();repeat.setObjectName('repeat');repeat.setEchoMode(QLineEdit.Password);l.addWidget(repeat)
    error=label('');error.setObjectName('error');l.addWidget(error);attempts=[0]
    def submit():
        try:
            if first:
                if password.text()!=repeat.text():raise ValueError('Passwords do not match')
                service.register(username.text(),password.text())
            service.login(username.text(),password.text());d.accept()
        except Exception as e:
            error.setText(tr(str(e)) if str(e) in i18n.DARI or i18n.LANG=='en' else tr('Please check your entry'))
            attempts[0]+=1;submit_button.setEnabled(False);QTimer.singleShot(min(30000,attempts[0]*1000),lambda:submit_button.setEnabled(True))
    submit_button=button('Create administrator' if first else 'Unlock',submit,True);submit_button.setObjectName('unlock');outer.addWidget(submit_button);password.returnPressed.connect(submit_button.click)
    def change_lang():
        service.s.set_setting('language',language.currentData());i18n.LANG=language.currentData();d.done(2)
    language.currentIndexChanged.connect(change_lang)
    d.setLayoutDirection(Qt.RightToLeft if i18n.LANG=='fa_AF' else Qt.LeftToRight)
    result=d.exec()
    if result==2:return authenticate(service,parent)
    return result==QDialog.Accepted
