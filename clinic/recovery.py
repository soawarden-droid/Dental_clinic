"""Explicit local OS-owner recovery; no master password or authentication bypass."""
from .domain import password_hash,now
from .backup import create_backup


def reset_local_password(store,username,new_password):
    # The desktop entrypoint holds the normal exclusive profile lock.
    hashed=password_hash(new_password)
    row=store.one('SELECT id FROM users WHERE username=?',(username,))
    if not row:raise ValueError('Choose a local account')
    safety=create_backup(store.root,store.root.parent/'FaramarzPasswordRecoveryBackups')
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        store.db.execute('UPDATE users SET password=? WHERE id=?',(hashed,row['id']))
        store.db.execute('INSERT INTO audit(at,actor,action,details) VALUES(?,?,?,?)',(now(),'local OS owner','local password recovery',username+'; complete safety backup created'))
    return safety


def recovery_dialog(store):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QLineEdit,QCheckBox,QPushButton
    from .i18n import tr
    accounts=store.rows('SELECT username,role FROM users ORDER BY username')
    if not accounts:raise ValueError('No local accounts exist yet')
    d=QDialog();d.setWindowTitle(tr('Local password recovery'));d.setMinimumWidth(510)
    layout=QVBoxLayout(d)
    info=QLabel(tr('Only the owner of this computer should reset a local account. A complete backup will be made. Clinic records will be preserved.'));info.setWordWrap(True);layout.addWidget(info)
    choice=QComboBox()
    for row in accounts:choice.addItem(row['username']+' · '+tr(row['role']),row['username'])
    layout.addWidget(choice)
    layout.addWidget(QLabel(tr('New password')));password=QLineEdit();password.setEchoMode(QLineEdit.Password);layout.addWidget(password)
    layout.addWidget(QLabel(tr('Confirm password')));repeat=QLineEdit();repeat.setEchoMode(QLineEdit.Password);layout.addWidget(repeat)
    consent=QCheckBox(tr('I own this local clinic profile and want to reset this account.'));layout.addWidget(consent)
    error=QLabel();error.setWordWrap(True);layout.addWidget(error)
    save=QPushButton(tr('Reset password'));layout.addWidget(save)
    close=QPushButton(tr('Cancel'));close.clicked.connect(d.reject);layout.addWidget(close)
    def reset():
        save.setEnabled(False)
        try:
            if not consent.isChecked():raise ValueError('Confirm local ownership before resetting')
            if password.text()!=repeat.text():raise ValueError('Passwords do not match')
            reset_local_password(store,choice.currentData(),password.text())
            password.clear();repeat.clear();d.accept()
        except Exception as e:error.setText(tr(str(e)));save.setEnabled(True)
    save.clicked.connect(reset)
    return d.exec()==QDialog.Accepted
