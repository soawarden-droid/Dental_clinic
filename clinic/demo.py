"""Explicit fictional demonstration profile; never called in the normal profile."""
from .domain import today


def seed(service):
    if service.s.rows('SELECT id FROM users'):
        service.login('demo','Fictional-demo-2026!')
        return
    service.register('demo','Fictional-demo-2026!');service.login('demo','Fictional-demo-2026!')
    names=[('Demo · Maryam Ahmadi','مریم احمدی'),('Demo · Ahmad Rahimi','احمد رحیمی'),('Demo · Sara Noori','سارا نوری'),('Demo · Omar Sediqi','عمر صدیقی')]
    for index,(en,fa) in enumerate(names):
        pid=service.save_patient({'name':en+' / '+fa,'phone':'+93700000000','estimated_age':str(20+index*5),'alerts':'Penicillin allergy — fictional example' if index==0 else ''})
        vid=service.visit(pid,'Dr. Farshad Faramarz','Fictional demonstration visit',today())
        service.treatment(vid,'Filling',250000,'26','Recorded by doctor','completed','Fictional record')
        service.treatment(vid,'Scaling',120000,'','','planned')
        iid=service.invoice(vid);service.payment(iid,100000,'Cash')
        service.appointment(pid,today()+f'T{9+index:02}:00',30,'arrived' if index<2 else 'scheduled',override=True)
    mid=service.add_record('materials',{'name':'Composite · demo','unit':'syringe','minimum':4})
    sid=service.add_record('suppliers',{'name':'Fictional supplier','phone':'+93700000000','address':''})
    service.purchase(sid,[{'material_id':mid,'quantity':3,'unit_cost':80000,'batch':'DEMO','expiry':''}],100000)
    service.add_record('expenses',{'date':today(),'category':'Electricity','amount':150000,'notes':'Fictional demonstration only'})
