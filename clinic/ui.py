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
from .theme import stylesheet,colors,motion_enabled,apply_app_theme,tooth_style
from .printing import PrintDialog,invoice_html,document_html
from .components import Card,Hero,StatCard,Chart
from .finance_ui import FinanceUI
from .backup import create_backup,restore_backup,apply_retention

PAGES=['Overview','Patients','Appointments','Materials','Purchases','Expenses','Laboratory','Reports','Clinic profile','Settings']
PATIENT_FIELDS=[('name','Full name','line',''),('phone','Phone','phone',''),('father','Father’s name','line',''),('address','Address','line',''),('dob','Birth date','date_optional',''),('estimated_age','Estimated age at registration','line',''),('gender','Gender',[(None,'Not provided'),('female','Female'),('male','Male'),('other','Other')],None),('email','Email','line',''),('history','Medical history','text',''),('allergies','Allergies','text',''),('medications','Medications','text',''),('alerts','Clinical alerts','text',''),('emergency','Emergency contact','line',''),('consent','Consent notes','text','')]


class Job(QThread):
    done=Signal(object); failed=Signal(str)
    def __init__(self,fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))


class Window(FinanceUI,QMainWindow):
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
            text=tr('Please check your entry')+'\n'+message
        QMessageBox.warning(self,tr('Please check your entry'),text)

    def confirm(self,message):
        return QMessageBox.question(self,tr('Confirm'),tr(message),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes

    def form(self,title,fields,initial=None,on_save=None):
        d=Form(title,fields,self,initial,submit_callback=on_save)
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
            b=self.act(name,lambda n=name:self.navigate(n)); b.setObjectName('nav'); b.setIcon(QIcon(str(self.assets/'icons'/(name.lower().replace(' ','-')+'.svg'))));b.setCheckable(True); nav_layout.addWidget(b); self.nav[name]=b
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
        apply_app_theme(self.s)

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
        if title:layout.addWidget(label(title,'title'))
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
        dispatch={'Overview':self.overview,'Patients':self.patient_list,'Appointments':self.appointments,'Materials':self.materials,'Purchases':self.purchases,'Expenses':self.expenses,'Laboratory':self.labs,'Reports':self.reports,'Clinic profile':self.profile,'Settings':self.settings,'images':self.image_settings,'detail':lambda:self.patient_detail(self.pid)}
        self.guard(dispatch[name])

    def refresh(self):
        if self.current=='images':self.image_settings()
        elif self.current=='detail' and self.pid: self.patient_detail(self.pid)
        else: self.navigate(self.current)
        self.statusBar().showMessage(tr('Saved successfully'),4000)

    def overview(self):
        days=getattr(self,'dashboard_days',30);data=self.svc.dashboard(days);self.dashboard_data=data
        layout=self.page('')
        doctor=self.s.setting('display_dari' if i18n.LANG=='fa_AF' else 'display_english','داکتر فرشاد فرامرز' if i18n.LANG=='fa_AF' else 'Dr. Farshad Faramarz')
        hero=Hero(doctor,self.date(today())+'   ·   '+tr('A little care, every day.'))
        self.actions(hero.content,[('New patient',self.new_patient,True),('New visit',self.quick_visit),('Record payment',self.quick_payment)])
        background=self.s.setting('clinic_background')
        if background:hero.set_background(self.s.root/'attachments'/background,int(self.s.setting('background_opacity','15')))
        layout.addWidget(hero)
        cards=QGridLayout();cards.setSpacing(12)
        stats=[('Patients seen today',str(data['seen_today']),'Distinct patients with visits',lambda:self.dashboard_records('visits')),
               ('Billed today',afn(data['billed_today']),'Issued invoices less discounts',lambda:self.dashboard_records('today_billed')),
               ('Collected today',afn(data['collected_today']),'Payments less refunds',lambda:self.dashboard_records('today_payments')),
               ('Outstanding balances',afn(data['outstanding']),'All issued invoices less payments',lambda:self.dashboard_records('balances')),
               ('Upcoming appointments',str(len(data['upcoming'])),'Next seven days',lambda:self.dashboard_records('upcoming'))]
        for i,(title,value,caption,callback) in enumerate(stats):
            card=StatCard(title,value,caption);card.clicked.connect(lambda fn=callback:self.guard(fn));cards.addWidget(card,i//3,i%3)
        layout.addLayout(cards)
        heading=QHBoxLayout();heading.addWidget(label('The rhythm of your clinic','brand'),1);period=QComboBox()
        for n in (7,30,90):period.addItem(tr('Last {days} days').format(days=n),n)
        period.setCurrentIndex((7,30,90).index(days))
        def change_period():self.dashboard_days=period.currentData();self.overview()
        period.currentIndexChanged.connect(change_period);heading.addWidget(period);layout.addLayout(heading);layout.addWidget(label(self.date(data['start'])+' — '+self.date(data['end']),'subtitle'))
        charts=QHBoxLayout();charts.setSpacing(12);animated=motion_enabled(self.s)
        trend=Card('Net collections','Payments less refunds');trend_chart=Chart('trend',data['trend'],animated,self.date,bool(data['ledger']));trend.content.addWidget(trend_chart);trend_chart.activated.connect(lambda:self.guard(lambda:self.dashboard_records('payments')));charts.addWidget(trend,2)
        distribution=Card('Treatment mix','Completed treatments');donut=Chart('donut',data['distribution'],animated);distribution.content.addWidget(donut);donut.activated.connect(lambda:self.guard(lambda:self.dashboard_records('treatments')))
        for row in data['distribution'][:3]:
            b=self.act(tr(row['procedure'])+'  ·  '+str(row['count']),lambda proc=row['procedure']:self.dashboard_records('treatments',proc));b.setObjectName('badge');distribution.content.addWidget(b)
        charts.addWidget(distribution,1)
        status=Card('Appointment status','Saved appointments in this period');status_chart=Chart('status',data['statuses'],animated);status.content.addWidget(status_chart);status_chart.categoryActivated.connect(lambda state:self.guard(lambda:self.dashboard_records('statuses',state)));status_chart.activated.connect(lambda:self.guard(lambda:self.dashboard_records('statuses')));charts.addWidget(status,1)
        layout.addLayout(charts)
        lower=QHBoxLayout();lower.setSpacing(12)
        agenda=Card('Today’s agenda');t=self.table(agenda.content,['Time','Patient','Status'],data['appointments'],[lambda r:r['starts'][11:16],'name','status'],lambda r:self.patient_detail(r['patient_id']));t.setMinimumHeight(190);lower.addWidget(agenda,2)
        recent=Card('Recent patients')
        for row in data['recent_patients']:
            recent.content.addWidget(self.act(row['name']+'  ·  '+f"P-{row['id']:06}",lambda pid=row['id']:self.patient_detail(pid)))
        if not data['recent_patients']:recent.content.addWidget(label('Register your first patient to begin.','subtitle'))
        recent.content.addStretch();lower.addWidget(recent,1);layout.addLayout(lower)
        activity=QHBoxLayout();recent_v=Card('Recent visits');recent_p=Card('Recent payments')
        for rows,card,tab in [(data['recent_visits'],recent_v,0),(data['recent_payments'],recent_p,3)]:
            for row in rows:card.content.addWidget(self.act(row['name']+' · '+self.date(row['date'])+(' · '+afn(row['amount']) if 'amount' in row else ''),lambda pid=row['patient_id'],tab=tab:self.patient_detail(pid,tab)))
            if not rows:card.content.addWidget(label('No records yet','subtitle'))
            activity.addWidget(card,1)
        layout.addLayout(activity)
        alerts=QHBoxLayout();stock=Card('Low stock');follow=Card('Upcoming follow-ups')
        for row in data['low_stock'][:5]:stock.content.addWidget(self.act(row['name']+'  ·  '+str(row['quantity'])+' '+row['unit'],lambda:self.navigate('Materials')))
        if not data['low_stock']:stock.content.addWidget(label('No low-stock alerts.','subtitle'))
        for row in data['followups']:follow.content.addWidget(self.act(row['name']+'  ·  '+self.date(row['followup']),lambda pid=row['patient_id']:self.patient_detail(pid)))
        if not data['followups']:follow.content.addWidget(label('No upcoming follow-ups.','subtitle'))
        alerts.addWidget(stock,1);alerts.addWidget(follow,1);layout.addLayout(alerts);layout.addStretch()

    def dashboard_records(self,kind,procedure=None):
        data=self.dashboard_data;start,end=data['start'],data['end']
        if kind=='visits':rows=data['visits'];headers=['Patient','Date','Doctor'];keys=['name',lambda r:self.date(r['date']),'doctor']
        elif kind in ('payments','today_payments'):
            rows=[r for r in data['ledger'] if kind=='payments' or r['date']==today()];headers=['Patient','Date','Amount','Method'];keys=['name',lambda r:self.date(r['date']),lambda r:afn(r['amount']),'method']
        elif kind in ('billed','today_billed'):rows=[r for r in data['billed'] if kind=='billed' or r['date']==today()];headers=['Patient','Invoice number','Total'];keys=['name',lambda r:f"INV-{r['id']:06}",lambda r:afn(r['total'])]
        elif kind=='balances':rows=[r for r in data['balances'] if r['balance']!=0];headers=['Patient','Invoice number','Remaining'];keys=['name',lambda r:f"INV-{r['id']:06}",lambda r:afn(r['balance'])]
        elif kind=='upcoming':rows=data['upcoming'];headers=['Patient','Date','Time','Status'];keys=['name',lambda r:self.date(r['starts'][:10]),lambda r:r['starts'][11:16],'status']
        elif kind=='treatments':
            rows=self.s.rows("SELECT t.*,v.patient_id,v.date,p.name FROM treatments t JOIN visits v ON v.id=t.visit_id JOIN patients p ON p.id=v.patient_id WHERE v.date BETWEEN ? AND ? AND t.status='completed'"+(' AND t.procedure=?' if procedure else '')+' ORDER BY t.id DESC',(start,end,procedure) if procedure else (start,end));headers=['Patient','Date','Procedure','Tooth'];keys=['name',lambda r:self.date(r['date']),'procedure','tooth']
        else:
            rows=self.s.rows('SELECT a.*,p.name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE substr(a.starts,1,10) BETWEEN ? AND ?'+(' AND a.status=?' if procedure else '')+' ORDER BY a.starts',(start,end,procedure) if procedure else (start,end));headers=['Patient','Date','Status'];keys=['name',lambda r:self.date(r['starts'][:10]),'status']
        d=QDialog(self);d.setWindowTitle(tr('Underlying records'));d.resize(850,550);l=QVBoxLayout(d);l.addWidget(label('Underlying records','title'));l.addWidget(label(self.date(start)+' — '+self.date(end),'subtitle'));table=self.table(l,headers,rows,keys)
        def open_patient():
            r=table.selected();d.accept();self.patient_detail(r['patient_id'],3 if kind in ('payments','today_payments','balances','billed','today_billed') else 0)
        self.actions(l,[('Patient',open_patient,True),('Close',d.accept)]);d.exec()

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
        if pid:self.patient_detail(pid,3);self.pay()

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
        balance=sum(r['balance'] for r in self.svc.balances(pid))
        layout=self.page(p['name'],f"P-{pid:06}   ·   {p['phone'] or '—'}"+'   ·   '+tr('Balance')+': '+afn(balance))
        if self.svc.user['role']=='admin' and (p['alerts'] or p['allergies']): layout.addWidget(label(tr('Clinical alerts')+': '+(p['alerts'] or '—')+'   '+tr('Allergies')+': '+(p['allergies'] or '—'),'alert'))
        photo=self.s.setting(f'patient_photo_{pid}')
        if photo:
            image=QLabel();image.setPixmap(QPixmap(str(self.s.root/'attachments'/photo)).scaled(80,80,Qt.KeepAspectRatio,Qt.SmoothTransformation));layout.addWidget(image)
        account=Card();account_row=QHBoxLayout();balance_box=QVBoxLayout();balance_box.addWidget(label('Balance','subtitle'));balance_box.addWidget(label(afn(balance),'metric'));account_row.addLayout(balance_box);account_row.addStretch()
        for title,fn in [('Add charge',self.add_charge),('Record payment',self.pay)]:account_row.addWidget(self.act(title,fn,title in ('Add charge','Record payment')))
        account.content.addLayout(account_row)
        drafts=self.svc.drafts(pid)
        if drafts:account.content.addWidget(label(tr('Saved draft charges (not yet billed)')+': '+afn(sum(r['amount'] for r in drafts)),'subtitle'))
        layout.addWidget(account)
        self.actions(layout,[('New visit',lambda:self.new_visit(pid)),('Statement',self.print_statement),('Edit patient',lambda:self.edit_patient(pid)),('Patient photograph',lambda:self.patient_photo(pid)),('Restore patient' if p['archived'] else 'Archive',lambda:self.archive_patient(p))])
        tabs=QTabWidget(); layout.addWidget(tabs,1)
        sections=[('Overview',self.patient_overview),('Visits & treatments',lambda l,p:self.clinical_tab(l,p,False,True)),('Dental chart',lambda l,p:self.clinical_tab(l,p,True,False)),('Invoices & payments',self.billing_tab),('Photos & documents',self.patient_documents),('Prescriptions',self.prescriptions_tab)]
        for title,fn in sections:
            if self.svc.user['role']!='admin' and title not in ('Overview','Invoices & payments'):continue
            w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(0,16,0,0);l.setSpacing(14);fn(l,p);tabs.addTab(w,tr(title).replace('&','&&'))
        self.patient_tabs=tabs
        tabs.setCurrentIndex(tab if self.svc.user['role']=='admin' else (1 if tab==3 else 0))

    def patient_overview(self,l,p):
        l.addWidget(label('Account timeline','brand'));self.account_activity(l,p['id'])
        row=QHBoxLayout();demographics=Card('Patient information');clinical=Card('Medical history')
        for key,title in [('father','Father’s name'),('dob','Birth date'),('estimated_age','Estimated age at registration'),('gender','Gender'),('address','Address'),('email','Email'),('emergency','Emergency contact')]:
            value=self.date(p[key]) if key=='dob' and p[key] else p[key]
            demographics.content.addWidget(label(tr(title)+'  ·  '+(str(value) if value is not None and value!='' else tr('Not provided')),'subtitle'))
        demographics.content.addWidget(self.act('Edit details',lambda:self.edit_section(p,'Patient information',{'father','dob','estimated_age','gender','address','email','emergency'})))
        row.addWidget(demographics,1)
        if self.svc.user['role']=='admin':
            for key,title in [('history','Medical history'),('allergies','Allergies'),('medications','Medications'),('alerts','Clinical alerts'),('consent','Consent notes')]:clinical.content.addWidget(label(tr(title)+'  ·  '+(p[key] or tr('Not provided')),'subtitle'))
            clinical.content.addWidget(self.act('Edit medical notes',lambda:self.edit_section(p,'Medical history',{'history','allergies','medications','alerts','consent'})));row.addWidget(clinical,1)
        l.addLayout(row)

    def edit_section(self,p,title,keys):
        v=self.form(title,[field for field in PATIENT_FIELDS if field[0] in keys],p)
        if v:self.svc.save_patient(v,p['id']);self.patient_detail(p['id'])

    def patient_documents(self,l,p):
        self.image_card(l,'patient_photo_'+str(p['id']),'Patient photograph')
        self.documents_tab(l,p)

    def patient_photo(self,pid):
        self.svc.allowed(clinical=True);self.patient_detail(pid,4)

    def archive_patient(self,p):
        if self.confirm('Archive this patient? Their records will be preserved.'):
            self.svc.archive(p['id'],not p['archived']); self.patient_detail(p['id'])

    def history_tab(self,l,p):
        for key,title,_,_ in PATIENT_FIELDS[2:]:
            l.addWidget(label(title,'brand')); l.addWidget(label((self.date(p[key]) if key=='dob' and p[key] else p[key]) or 'Not supplied'))
        l.addStretch()

    def clinical_tab(self,l,p,show_chart=True,show_history=True):
        visits=self.s.rows('SELECT * FROM visits WHERE patient_id=? ORDER BY id DESC',(p['id'],))
        treatments=self.s.rows('SELECT t.*,v.date,v.doctor FROM treatments t JOIN visits v ON v.id=t.visit_id WHERE v.patient_id=? ORDER BY t.id DESC',(p['id'],))
        bar=QHBoxLayout(); self.visit_choice=QComboBox();choice=self.visit_choice;self.visit_choice.setLayoutDirection(Qt.LeftToRight)
        for v in visits: self.visit_choice.addItem(f"V-{v['id']} · {self.date(v['date'])} · {v['doctor']}",v['id'])
        bar.addWidget(self.visit_choice,1); bar.addWidget(self.act('Add treatment',lambda:self.add_treatment(visit_id=choice.currentData()),True)); bar.addWidget(self.act('Issue invoice',lambda:self.issue_invoice(choice.currentData()))); l.addLayout(bar)
        if show_chart:
            dentition=QComboBox(); dentition.addItem(tr('Permanent teeth'),False); dentition.addItem(tr('Primary teeth'),True); l.addWidget(dentition)
            chart=QWidget(); chart.setFixedHeight(100); grid=QGridLayout(chart); grid.setSpacing(5)
            def draw():
                while grid.count():
                    item=grid.takeAt(0)
                    if item.widget(): item.widget().deleteLater()
                rows=CHILD if dentition.currentData() else ADULT
                for row,teeth in enumerate(rows):
                    for col,tooth in enumerate(teeth):
                        b=self.act(str(tooth),lambda t=tooth:self.add_treatment(str(t),choice.currentData()))
                        b.setMinimumWidth(34); b.setMinimumHeight(44); b.setStyleSheet(tooth_style())
                        relevant=[r for r in treatments if r['tooth']==str(tooth)]
                        if relevant:
                            state='planned' if any(r['status']=='planned' for r in relevant) else 'completed'
                            b.setStyleSheet(tooth_style(state))
                            b.setToolTip('\n'.join(tr(r['procedure'])+' · '+tr(r['status']) for r in relevant))
                        grid.addWidget(b,row,col)
                chart.setLayoutDirection(Qt.LeftToRight)
            dentition.currentIndexChanged.connect(draw); draw()
            l.addWidget(label('Patient right → left','subtitle')); l.addWidget(label('Upper jaw','subtitle')); l.addWidget(chart); l.addWidget(label('Lower jaw','subtitle')); l.addWidget(label('Select a tooth to record work. Teal: completed · Amber: planned.','subtitle'))
        if show_history:
            l.addWidget(label('Planned treatments are not billed. Complete treatment, then issue an invoice.','subtitle'))
            self.treatment_table=self.table(l,['Treatment number','Date','Tooth','Procedure','Price','Status'],treatments,['id',lambda r:self.date(r['date']),'tooth','procedure',lambda r:afn(r['price']),'status'],self.treatment_details)
            self.actions(l,[('Edit treatment',self.edit_treatment),('Complete treatment',self.complete_treatment)])
            vt=Table(['Date','Notes','Follow-up'],visits,[lambda r:self.date(r['date']),'notes',lambda r:self.date(r['followup'])]); l.addWidget(vt)

    def new_visit(self,pid):
        self.svc.allowed()
        v=self.form('New visit',[('doctor','Doctor','line',self.s.setting('display_dari' if i18n.LANG=='fa_AF' else 'display_english','داکتر فرشاد فرامرز' if i18n.LANG=='fa_AF' else 'Dr. Farshad Faramarz')),('date','Date','date',today()),*([('notes','Notes','text',''),('followup','Follow-up','date_optional','')] if self.svc.user['role']=='admin' else [])])
        if v:
            self.svc.visit(pid,**v); self.patient_detail(pid,1)

    def add_treatment(self,tooth='',visit_id=None):
        self.svc.allowed(clinical=True)
        vid=visit_id or self.visit_choice.currentData()
        if not vid: raise ValueError('Choose a record first')
        catalogue=self.s.rows('SELECT * FROM catalogue ORDER BY name')
        v=self.form('Add treatment',[('procedure','Procedure',[(r['name'],r['name']) for r in catalogue],catalogue[0]['name']),('price','Price','money','0.00'),('tooth','Tooth',['']+[str(n) for row in ADULT+CHILD for n in row],tooth),('condition','Condition','line',''),('status','Status',['planned','completed'],'planned'),('notes','Notes','text','')])
        if v:
            self.svc.treatment(vid,price=money(v.pop('price')),**v); self.patient_detail(self.pid,1)

    def complete_treatment(self):
        t=self.treatment_table.selected(); self.svc.complete(t['id']); self.patient_detail(self.pid,1)

    def issue_invoice(self,visit_id=None):
        vid=visit_id or self.visit_choice.currentData()
        if not vid: raise ValueError('Choose a record first')
        v=self.form('Issue invoice',[('discount','Discount','money','0.00')],on_save=lambda v:self.svc.invoice(vid,money(v['discount'])))
        if v:
            self.patient_detail(self.pid,3)

    def treatment_details(self,r):
        self.svc.allowed(clinical=True)
        d=QDialog(self);d.resize(550,450);d.setWindowTitle(tr('Procedure'));l=QVBoxLayout(d)
        for key,title in [('procedure','Procedure'),('tooth','Tooth'),('condition','Condition'),('status','Status'),('doctor','Doctor'),('notes','Notes')]:
            l.addWidget(label(title,'brand'));l.addWidget(label(r[key] or 'Not supplied'))
        l.addWidget(button('Close',d.accept));d.exec()

    def void(self):
        inv=self.invoice_table.selected(); v=self.form('Void invoice',[('reason','Reason','text','')])
        if v: self.svc.void_invoice(inv['id'],v['reason']); self.patient_detail(self.pid,3)

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
            if path:self.attach_file(path,pid,lambda _:self.patient_detail(pid,4) if pid else self.profile())
        def open_doc():
            self.svc.allowed(clinical=bool(pid),admin=not pid)
            r=table.selected(); QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.s.root/'attachments'/r['stored'])))
        self.actions(l,[('Add document',add,True),('Open document',open_doc),('Remove',lambda:self.remove_saved_document(table,lambda:self.patient_detail(pid,4) if pid else self.profile()))])

    def prescriptions_tab(self,l,p):
        rows=self.s.rows('SELECT * FROM prescriptions WHERE patient_id=? ORDER BY id DESC',(p['id'],))
        table=self.table(l,['Date','Prescription','Aftercare instructions'],rows,[lambda r:self.date(r['date']),'content','aftercare'])
        def add():
            self.svc.allowed(clinical=True)
            v=self.form('Write prescription',[('content','Prescription','text',''),('aftercare','Aftercare instructions','text','')])
            if v:
                self.svc.add_record('prescriptions',dict(patient_id=p['id'],date=today(),**v),clinical=True); self.patient_detail(p['id'],5)
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
        self.actions(layout,[('Change status',change),('New visit',visit),('Record payment',lambda:self.patient_detail(table.selected()['patient_id'],3))]); layout.addStretch()

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

    def image_card(self,layout,slot,title):
        card=Card(title);stored=self.s.setting(slot);row=QHBoxLayout();preview=QLabel();preview.setFixedSize(94,94);preview.setAlignment(Qt.AlignCenter)
        if stored:
            pix=QPixmap(str(self.s.root/'attachments'/stored));preview.setPixmap(pix.scaled(88,88,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        elif slot=='clinic_logo':preview.setPixmap(QIcon(str(self.assets/'clinic.svg')).pixmap(70,70))
        else:
            preview.setText('FF' if slot=='profile_photo' else '◇');preview.setObjectName('avatar')
        row.addWidget(preview);description=label('Custom image' if stored else ('Default avatar' if slot=='profile_photo' else 'Plain background' if slot=='clinic_background' else 'Default clinic mark' if slot=='clinic_logo' else 'No photograph'),'subtitle');row.addWidget(description,1);card.content.addLayout(row)
        buttons=QGridLayout()
        def refresh():self.patient_detail(int(slot.removeprefix('patient_photo_')),4) if slot.startswith('patient_photo_') else self.image_settings()
        def upload():
            self.svc.image_permission(slot);path,_=QFileDialog.getOpenFileName(self,tr('Choose image'),'','Images (*.png *.jpg *.jpeg *.webp)')
            if path:
                from .service import prepare_attachment
                def saved(records):self.svc.replace_image(slot,records);refresh()
                self.background(lambda:prepare_attachment(self.s.root,path,True),saved)
        def remove():
            if self.confirm('Remove this custom image? Your original file will be kept.'):
                self.svc.remove_image(slot);refresh()
        def show():
            if stored:self.preview_image(stored,title)
            else:
                d=QDialog(self);d.setWindowTitle(tr('Preview'));l=QVBoxLayout(d);l.addWidget(label(description.text()));l.addWidget(button('Close',d.accept));d.exec()
        for index,(text,fn) in enumerate([('Replace' if stored else 'Add',upload),('Remove',remove),('Preview',show),('Restore default',remove)]):
            b=self.act(text,fn,index==0);b.setEnabled(bool(stored) or text in ('Add','Preview'));buttons.addWidget(b,index//2,index%2)
        card.content.addLayout(buttons)
        if layout is not None:layout.addWidget(card)
        return card

    def preview_image(self,stored,title='Preview'):
        d=QDialog(self);d.setWindowTitle(tr(title));d.resize(720,530);l=QVBoxLayout(d);image=QLabel();image.setAlignment(Qt.AlignCenter);image.setPixmap(QPixmap(str(self.s.root/'attachments'/stored)).scaled(650,430,Qt.KeepAspectRatio,Qt.SmoothTransformation));l.addWidget(image,1);l.addWidget(button('Close',d.accept));d.exec()

    def image_settings(self):
        self.svc.allowed(admin=True);self.current='images';layout=self.page('Images & appearance','Make the clinic feel like yours.')
        self.actions(layout,[('Clinic profile',self.profile),('Add gallery image',self.add_gallery_image,True)])
        grid=QGridLayout();grid.setSpacing(16)
        for i,(slot,title) in enumerate([('profile_photo','Profile photograph'),('clinic_logo','Clinic logo'),('clinic_background','Clinic background')]):grid.addWidget(self.image_card(None,slot,title),i//2,i%2)
        overlay=Card('Background opacity','A soft overlay keeps text readable.');overlay.content.addWidget(label(str(self.s.setting('background_opacity','15'))+'%','metric'))
        def opacity():
            v=self.form('Background opacity',[('opacity','Opacity (0–30%)','int',int(self.s.setting('background_opacity','15')))])
            if v:
                if not 0<=v['opacity']<=30:raise ValueError('Choose an opacity between 0 and 30')
                with self.svc.action('background opacity changed','',admin=True):self.s.set_setting('background_opacity',v['opacity'])
                self.image_settings()
        overlay.content.addWidget(self.act('Adjust overlay',opacity));grid.addWidget(overlay,1,1);layout.addLayout(grid)
        gallery=self.s.rows("SELECT ia.slot,a.stored,a.name FROM image_assets ia JOIN attachments a ON a.id=ia.preview_id WHERE ia.slot LIKE 'gallery_%' ORDER BY ia.slot")
        layout.addWidget(label('Profile gallery','brand'));gallery_grid=QGridLayout()
        for index,row in enumerate(gallery):gallery_grid.addWidget(self.image_card(None,row['slot'],row['name'].replace(' (preview)','')),index//2,index%2)
        if not gallery:layout.addWidget(label('No gallery images yet. Add your own clinic photographs.','subtitle'))
        layout.addLayout(gallery_grid)
        # Previous uploads remain documents until deliberately removed, never guessed away.
        legacy=self.s.rows("SELECT * FROM attachments WHERE scope='profile' AND image_owned=0 AND (lower(stored) LIKE '%.png' OR lower(stored) LIKE '%.jpg' OR lower(stored) LIKE '%.jpeg' OR lower(stored) LIKE '%.webp')")
        if legacy:
            layout.addWidget(label('Other saved images','brand'));table=self.table(layout,['Name'],legacy,['name'])
            self.actions(layout,[('Preview',lambda:self.preview_image(table.selected()['stored'])),('Remove',lambda:self.remove_saved_document(table,self.image_settings))])
        layout.addStretch()

    def add_gallery_image(self):
        import uuid
        slot='gallery_'+uuid.uuid4().hex
        path,_=QFileDialog.getOpenFileName(self,tr('Choose image'),'','Images (*.png *.jpg *.jpeg *.webp)')
        if path:
            from .service import prepare_attachment
            def saved(records):self.svc.replace_image(slot,records);self.image_settings()
            self.background(lambda:prepare_attachment(self.s.root,path,True),saved)

    def remove_saved_document(self,table,refresh):
        row=table.selected()
        if self.confirm('Remove this managed document? Your original file will be kept.'):
            self.svc.remove_attachment(row['id']);refresh()

    def profile(self):
        layout=self.page('Clinic profile');self.svc.allowed(admin=True)
        fields=[('display_english','Display name (English)','line','Dr. Farshad Faramarz'),('display_dari','Display name (Dari)','line','داکتر فرشاد فرامرز'),('clinic_name','Clinic name','line','Faramarz Dental Clinic'),('clinic_address','Clinic address','line','Khair Khana, District 11, Kabul, Afghanistan'),('clinic_phone','Phone','phone',''),('biography','Biography','text',''),('education','Education & qualifications','text',''),('experience','Experience','text',''),('specialties','Specialties','text',''),('hours','Working hours','text','')]
        def edit():
            v=self.form('Clinic profile',fields,{k:self.s.setting(k,default) for k,_,_,default in fields})
            if v:
                with self.svc.action('clinic profile edited','',admin=True) as db:
                    db.executemany('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',list(v.items()))
                self.profile()
        self.actions(layout,[('Edit profile',edit,True),('Images & appearance',self.image_settings)])
        for key,title,_,default in fields:
            layout.addWidget(label(title,'brand'));layout.addWidget(label(self.s.setting(key,default) or 'No information supplied'))
        layout.addWidget(label('Profile documents & images','brand'));self.documents_tab(layout)

    def settings(self):
        self.svc.allowed(admin=True);layout=self.page('Settings')
        layout.addWidget(label('Dari wording is provisional; please review with the clinic.','subtitle'))
        def display():
            v=self.form('Settings',[('theme','Theme',[('light','Light'),('dark','Dark'),('system','System')],self.s.setting('theme','system')),('calendar','Calendar',[('gregorian','Gregorian'),('solar','Solar Hijri')],self.s.setting('calendar','gregorian')),('reduced_motion','Reduce motion','bool',self.s.setting('reduced_motion')=='True')])
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
                self.svc.record_attachments(records,pid)
                callback(records)
            except Exception as e:
                for r in records:
                    if not self.s.one('SELECT id FROM attachments WHERE stored=?',(r['stored'],)):(self.s.root/'attachments'/r['stored']).unlink(missing_ok=True)
                self.error(str(e))
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
    if not first:
        def recover():
            from .recovery import recovery_dialog
            try:
                if recovery_dialog(service.s):password.clear();error.setText(tr('Password reset. Sign in using your new password.'))
            except Exception as e:error.setText(tr(str(e)))
        outer.addWidget(button('Forgot password?',recover))
    def change_lang():
        service.s.set_setting('language',language.currentData());i18n.LANG=language.currentData();apply_app_theme(service.s);d.done(2)
    language.currentIndexChanged.connect(change_lang)
    d.setLayoutDirection(Qt.RightToLeft if i18n.LANG=='fa_AF' else Qt.LeftToRight)
    result=d.exec()
    if result==2:return authenticate(service,parent)
    return result==QDialog.Accepted
