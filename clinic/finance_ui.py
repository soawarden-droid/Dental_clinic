"""Daily reception workflow: draft fees → issued bills → dated receipts."""
from uuid import uuid4
from PySide6.QtWidgets import QDialog,QComboBox,QLabel,QVBoxLayout
from .widgets import Form
from .components import Card
from .domain import today,money,afn,amount_text
from .i18n import tr
from .printing import PrintDialog,invoice_html,statement_html


class FinanceUI:
    def account_activity(self,layout,patient_id):
        statement=self.svc.statement(patient_id)
        self.timeline_table=self.table(layout,['Date','Type','Description','Charge','Payment','Balance','Status'],statement['events'],[lambda r:self.date(r['date']),'kind','description',lambda r:afn(r['charge']) if r['charge'] else '—',lambda r:afn(r['payment']) if r['payment'] else '—',lambda r:afn(r['balance']),'status'])

    def add_charge(self):
        self.svc.allowed()
        visits=self.s.rows('SELECT * FROM visits WHERE patient_id=? ORDER BY date DESC,id DESC',(self.pid,))
        if not visits:
            self.new_visit(self.pid)
            visits=self.s.rows('SELECT * FROM visits WHERE patient_id=? ORDER BY date DESC,id DESC',(self.pid,))
            if not visits:return
        fields=[('visit_id','Visit',[(r['id'],f"V-{r['id']} · {self.date(r['date'])}") for r in visits],visits[0]['id']),('kind','Charge type',[('consultation','Doctor consultation fee'),('procedure','Treatment charge'),('other','Other')],'consultation'),('description','Description','line',tr('Doctor consultation fee')),('amount','Amount','money','')]
        def save(v):return self.svc.add_charge(v['visit_id'],v['description'],money(v['amount']),v['kind'])
        v=self.form('Add charge',fields,on_save=save)
        if v:self.patient_detail(self.pid,3);self.statusBar().showMessage(tr('Draft charge saved. Issue an invoice to finalize it.'),7000)

    def edit_draft(self):
        row=self.draft_table.selected()
        if row['source']=='treatment':
            self.edit_treatment(row['id']);return
        original=self.s.one('SELECT * FROM charges WHERE id=?',(row['id'],))
        def save(v):self.svc.update_charge(original['id'],v['description'],money(v['amount']),v['kind'])
        v=self.form('Edit draft charge',[('kind','Charge type',[('consultation','Doctor consultation fee'),('procedure','Treatment charge'),('other','Other')],original['kind']),('description','Description','line',original['description']),('amount','Amount','money',amount_text(original['amount']))],on_save=save)
        if v:self.patient_detail(self.pid,3)

    def edit_treatment(self,treatment_id=None):
        self.svc.allowed(clinical=True)
        tid=treatment_id or self.treatment_table.selected()['id'];t=self.s.one('SELECT * FROM treatments WHERE id=?',(tid,))
        def save(v):self.svc.update_treatment(tid,price=money(v.pop('price')),**v)
        v=self.form('Edit treatment',[('procedure','Procedure','line',t['procedure']),('price','Price','money',amount_text(t['price'])),('tooth','Tooth','line',t['tooth']),('condition','Condition','line',t['condition']),('status','Status',['planned','completed'],t['status']),('notes','Notes','text',t['notes'])],on_save=save)
        if v:self.patient_detail(self.pid,1)

    def billing_tab(self,l,p):
        summary=self.svc.account_totals(p['id']);card=Card('Patient account',tr('Billed')+': '+afn(summary['total'])+'   ·   '+tr('Paid')+': '+afn(summary['paid'])+'   ·   '+tr('Remaining')+': '+afn(summary['balance']))
        self.actions(card.content,[('Add charge',self.add_charge,True),('Record payment',self.pay,True),('Statement',self.print_statement)]);l.addWidget(card)
        drafts=self.svc.drafts(p['id'])
        if drafts:
            l.addWidget(QLabel(tr('Draft charges are saved but are not debt until you issue an invoice.')+' '+afn(sum(r['amount'] for r in drafts))))
            self.draft_table=self.table(l,['Visit','Date','Description','Type','Amount'],drafts,['visit_id',lambda r:self.date(r['date']),'description','kind',lambda r:afn(r['amount'])])
            self.actions(l,[('Edit draft charge',self.edit_draft),('Issue invoice',self.billing_invoice,True)])
        invoices=self.svc.balances(p['id'])
        self.invoice_table=self.table(l,['Invoice number','Date','Total','Paid','Remaining','Status'],invoices,[lambda r:f"INV-{r['id']:06}",lambda r:self.date(r['date']),lambda r:afn(r['total']),lambda r:afn(r['paid']),lambda r:afn(r['balance']),'status'])
        if invoices:self.invoice_table.setCurrentCell(next((i for i,r in enumerate(invoices) if r['balance']>0),0),0)
        self.actions(l,[('Print / PDF',self.print_invoice),('Refund',lambda:self.pay(True)),('Void invoice',self.void)])
        payments=self.s.rows('SELECT pay.* FROM payments pay JOIN invoices i ON i.id=pay.invoice_id WHERE i.patient_id=? ORDER BY pay.date,pay.id',(p['id'],))
        self.payment_table=self.table(l,['Receipt number','Invoice number','Date','Amount','Method','Reason'],payments,[lambda r:f"R-{r['id']:06}",lambda r:f"INV-{r['invoice_id']:06}",lambda r:self.date(r['date']),lambda r:afn(r['amount']),'method','reason'],lambda r:PrintDialog(invoice_html(self.svc,r['invoice_id'],r['id']),self).exec())
        if payments:self.payment_table.setCurrentCell(len(payments)-1,0)
        self.actions(l,[('Receipt',self.print_receipt)])

    def billing_invoice(self):
        draft_visits={r['visit_id'] for r in self.svc.drafts(self.pid)}
        visits=self.s.rows('SELECT * FROM visits WHERE patient_id=? ORDER BY date DESC,id DESC',(self.pid,))
        visits=[r for r in visits if r['id'] in draft_visits]
        if not visits:raise ValueError('No completed unbilled treatments or draft fees for this visit')
        def save(v):return self.svc.invoice(v['visit'],money(v['discount']))
        v=self.form('Issue invoice',[('visit','Visit',[(r['id'],f"V-{r['id']} · {self.date(r['date'])}") for r in visits],visits[0]['id']),('discount','Discount','money','0.00')],on_save=save)
        if v:self.patient_detail(self.pid,3);self.statusBar().showMessage(tr('Invoice issued. No payment has been recorded.'),6000)

    def pay(self,refund=False):
        if getattr(self,'_payment_busy',False):return
        self._payment_busy=True
        try:
            invoices=[r for r in self.svc.balances(self.pid) if not r['void'] and (r['paid']>0 if refund else r['balance']>0)]
            if not invoices:raise ValueError('No refundable payments' if refund else 'No outstanding invoice. Finalize any draft charges first.')
            selected=self.invoice_table.selected() if hasattr(self,'invoice_table') and self.invoice_table.currentRow()>=0 else None
            default=next((r for r in invoices if selected and r['id']==selected['id']),invoices[-1])
            key=uuid4().hex
            def available(row):return row['paid'] if refund else row['balance']
            def save(v):return self.svc.payment(v['invoice_id'],-money(v['amount']) if refund else money(v['amount']),v['method'],v['reason'],request_key=key,date=v['date'])
            d=Form('Refund' if refund else 'Record payment',[('invoice_id','Invoice number',[(r['id'],f"INV-{r['id']:06} · {afn(available(r))}") for r in invoices],default['id']),('date','Date','date',today()),('amount','Amount','money',amount_text(available(default))),('method','Method',['Cash','Other'],'Cash'),('reason','Reason','line','')],self,submit_callback=save)
            def invoice_changed():
                r=next(r for r in invoices if r['id']==d.fields['invoice_id'][0].currentData());d.fields['amount'][0].setText(amount_text(available(r)))
            d.fields['invoice_id'][0].currentIndexChanged.connect(invoice_changed)
            if d.exec()!=QDialog.Accepted:return
            iid=d.result_values['invoice_id'];receipt=d.result_record;self.patient_detail(self.pid,3)
            self.statusBar().showMessage(tr('Payment saved. Printing does not record another payment.'),6000)
            PrintDialog(invoice_html(self.svc,iid,receipt),self).exec()
        finally:self._payment_busy=False

    def print_statement(self):PrintDialog(statement_html(self.svc,self.pid),self).exec()
