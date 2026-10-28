from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QTextEdit,QComboBox,QSpinBox,QCheckBox,QDialogButtonBox,QScrollArea,QWidget,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QMessageBox,QApplication)
from PySide6.QtCore import Qt, QTimer
from .i18n import tr
from .domain import parse_date,display_date,today,money,phone_normalize


def button(text, callback, primary=False):
    b = QPushButton(tr(text))
    if primary: b.setObjectName('primary')
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(lambda checked=False: callback())
    return b


def label(text, kind=''):
    w = QLabel(tr(text)); w.setWordWrap(True)
    if kind: w.setObjectName(kind)
    return w


class Form(QDialog):
    """Reusable accessible forms; dates accept the chosen calendar, stored as ISO."""
    def __init__(self, title, fields, parent=None, initial=None):
        super().__init__(parent)
        self.setWindowTitle(tr(title)); self.resize(570, min(680,190+len(fields)*56,QApplication.primaryScreen().availableGeometry().height()-70))
        self.fields = {}; self.dirty = False
        self.solar = bool(parent and getattr(parent,'s',None) and parent.s.setting('calendar')=='solar')
        layout = QVBoxLayout(self)
        layout.addWidget(label(title,'title'))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); form = QFormLayout(body); form.setSpacing(12)
        initial = initial or {}
        for key, title, kind, default in fields:
            value = initial.get(key, default)
            if isinstance(kind,list):
                w = QComboBox()
                for item in kind:
                    data, text = item if isinstance(item,tuple) else (item,item)
                    w.addItem(tr(str(text)),data)
                idx = w.findData(value)
                if idx>=0: w.setCurrentIndex(idx)
                w.currentIndexChanged.connect(self.changed)
            elif kind=='text':
                w = QTextEdit(); w.setPlainText(str(value)); w.setMaximumHeight(90); w.textChanged.connect(self.changed)
            elif kind=='int':
                w = QSpinBox(); w.setRange(-100000000,100000000); w.setValue(int(value or 0)); w.valueChanged.connect(self.changed)
            elif kind=='bool':
                w = QCheckBox(); w.setChecked(bool(value)); w.toggled.connect(self.changed)
            else:
                w = QLineEdit(str(value))
                if kind=='password': w.setEchoMode(QLineEdit.Password)
                if kind in ('date','date_optional'):
                    if value and self.solar:
                        from jdatetime import date
                        d=date.fromgregorian(date=__import__('datetime').date.fromisoformat(str(value)[:10]))
                        w.setText(f'{d.year:04}/{d.month:02}/{d.day:02}')
                    w.setPlaceholderText(tr('Solar format: YYYY/MM/DD' if self.solar else 'Date format: YYYY-MM-DD'))
                    w.setLayoutDirection(Qt.LeftToRight)
                if kind in ('money','phone','password'): w.setLayoutDirection(Qt.LeftToRight)
                w.textChanged.connect(self.changed)
            w.setAccessibleName(tr(title)); form.addRow(tr(title),w); self.fields[key]=(w,kind)
        scroll.setWidget(body); layout.addWidget(scroll)
        self.error = label(''); self.error.setObjectName('error'); layout.addWidget(self.error)
        bb = QDialogButtonBox(); bb.addButton(tr('Save'),QDialogButtonBox.AcceptRole); bb.addButton(tr('Cancel'),QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.validate); bb.rejected.connect(self.reject); layout.addWidget(bb)
        self.result_values = None

    def changed(self,*args): self.dirty = True

    def values(self):
        result = {}
        for key,(w,kind) in self.fields.items():
            if isinstance(w,QComboBox): value = w.currentData()
            elif isinstance(w,QTextEdit): value = w.toPlainText().strip()
            elif isinstance(w,QSpinBox): value = w.value()
            elif isinstance(w,QCheckBox): value = w.isChecked()
            else: value = w.text().strip()
            if kind in ('date','date_optional') and value: value = parse_date(value,self.solar)
            elif kind=='date' and not value: raise ValueError('Date')
            if kind=='money': money(value)
            if kind=='phone': phone_normalize(value)
            if key in ('name','username','doctor','procedure','laboratory') and not value:
                raise ValueError('Full name is required')
            result[key]=value
        return result

    def validate(self):
        try:
            self.result_values=self.values(); self.accept()
        except (ValueError,TypeError) as e:
            self.error.setText(tr(str(e)) if str(e) in __import__('clinic.i18n',fromlist=['DARI']).DARI else tr('Please check your entry'))

    def reject(self):
        if self.dirty and QMessageBox.question(self,tr('Confirm'),tr('Unsaved changes will be lost. Continue?'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
            return
        super().reject()


class Table(QTableWidget):
    def __init__(self, headers, rows, keys, parent=None):
        super().__init__(len(rows),len(headers),parent)
        self.records=rows
        self.setHorizontalHeaderLabels([tr(x) for x in headers])
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True); self.setShowGrid(False)
        self.verticalHeader().hide(); self.verticalHeader().setDefaultSectionSize(47)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setMinimumHeight(150)
        for r,row in enumerate(rows):
            for c,key in enumerate(keys):
                value = key(row) if callable(key) else row.get(key,'')
                item = QTableWidgetItem(tr(str(value)))
                item.setToolTip(str(value))
                self.setItem(r,c,item)
        self.setSortingEnabled(False)

    def selected(self):
        r=self.currentRow()
        if r<0: raise ValueError('Choose a record first')
        return self.records[r]
