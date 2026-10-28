"""Native desktop entrypoint. There is no HTTP server or network client."""
import sys
import os
import argparse
import logging
from pathlib import Path
from time import perf_counter
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QTimer,QLockFile
from PySide6.QtGui import QFontDatabase,QFont
from clinic.storage import Store,data_path
from clinic.service import Service
from clinic import i18n
from clinic.ui import Window,authenticate


def main():
    started=perf_counter()
    os.umask(0o077)
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',help='Run packaged acceptance checks in a NEW isolated output folder')
    parser.add_argument('--demo',action='store_true',help='Open a separate fictional demonstration profile')
    parser.add_argument('--smoke',action='store_true',help='Automated packaged startup and SQLite check')
    parser.add_argument('--capture',help='Save demonstration screenshots to this directory')
    args=parser.parse_args()
    if args.verify:
        output=Path(args.verify).resolve()
        if output.exists() and any(output.iterdir()):parser.error('Verification output folder must be new or empty')
        if args.demo or args.smoke:parser.error('Verification is isolated from other profiles')
        os.environ['FARAMARZ_PROFILE']=str(output/'profile')
    if args.capture and not args.demo:parser.error('--capture requires --demo')
    if args.demo:
        os.environ['FARAMARZ_PROFILE']=str(data_path().parent/'FaramarzDental-Demo')
    root=data_path()
    recovery=root.with_name(root.name+'-restore-old')
    if recovery.exists() and not root.exists():os.replace(recovery,root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    logging.basicConfig(filename=root.parent/(root.name+'-application.log'),level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    app=QApplication(sys.argv);app.setApplicationName('Faramarz Dental Clinic');app.setOrganizationName('FaramarzDental')
    assets=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
    for path in assets.glob('*.ttf'):QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('DejaVu Sans',10));app.setStyle('Fusion')
    lock=QLockFile(str(root.parent/(root.name+'.lock')))
    if not lock.tryLock(0):
        QMessageBox.information(None,'Faramarz Dental Clinic','This clinic profile is already open.');return 1
    store=Store(root)
    try:service=Service(store)
    except Exception as e:QMessageBox.critical(None,'Faramarz Dental Clinic',str(e));return 1
    i18n.LANG=store.setting('language','en')
    if args.verify:
        from clinic.verification import run
        return run(app,service,assets,args.verify,started)
    if args.demo:
        from clinic.demo import seed
        seed(service)
    elif args.smoke:
        # Does not bypass authentication or seed patient data in the real profile.
        count=int(store.setting('smoke_launches','0'))+1;store.set_setting('smoke_launches',count)
        print(f'SQLite persistence: launch {count}',flush=True)
        from PySide6.QtWidgets import QLabel
        w=QLabel('Faramarz Dental Clinic · SQLite verified');w.resize(500,220);w.show()
        QTimer.singleShot(500,app.quit)
        return app.exec()
    else:
        QTimer.singleShot(0,lambda:print(f'Account screen: {perf_counter()-started:.3f}s',flush=True))
        if not authenticate(service):return 0
    window=Window(service,assets);window.show()
    if args.demo:window.setWindowTitle('Faramarz Dental Clinic — FICTIONAL DEMO')
    def ready():print(f'Usable window: {perf_counter()-started:.3f}s',flush=True)
    QTimer.singleShot(0,ready)
    if args.capture:
        window.resize(1366,768)
        target=Path(args.capture);target.mkdir(parents=True,exist_ok=True)
        states=[('en','light','overview-en-light.png',False),('en','dark','patient-en-dark.png',True),('fa_AF','light','patient-dari-light.png',True),('fa_AF','dark','overview-dari-dark.png',False)]
        def capture(index=0):
            if index==len(states):app.quit();return
            lang,theme,name,patient=states[index];store.set_setting('language',lang);store.set_setting('theme',theme);window.current='Overview';window.build()
            if patient:window.patient_detail(1)
            def save():window.grab().save(str(target/name));capture(index+1)
            QTimer.singleShot(500,save)
        QTimer.singleShot(500,capture)
    return app.exec()


if __name__=='__main__':sys.exit(main())
