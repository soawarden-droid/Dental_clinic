def stylesheet(dark=False):
    bg, surface, ink, muted, line, alt = ('#111f2b','#192c3a','#ebf3f4','#a5b9c3','#304654','#1d303e') if dark else ('#f3f6f4','#ffffff','#17383f','#637a7d','#dae5e1','#f6f9f7')
    return f'''
QWidget {{font-family:'DejaVu Sans';font-size:14px;color:{ink};}}
QMainWindow,QDialog {{background:{bg};}}
QMenuBar {{background:{bg};padding:3px;}}
QMenuBar::item:selected {{background:{alt};}}
QMenu {{background:{surface};border:1px solid {line};}}
QFrame#sidebar {{background:{surface};border:1px solid {line};border-radius:18px;}}
QLabel#title {{font-size:27px;font-weight:700;}}
QLabel#subtitle {{color:{muted};font-size:13px;}}
QLabel#brand {{font-size:19px;font-weight:700;color:#149a96;}}
QLabel#metric {{font-size:26px;font-weight:700;}}
QLabel#error {{color:#c15a45;}}
QLabel#alert {{background:#fff0d2;color:#744b0b;border-radius:9px;padding:12px;}}
QFrame#card {{background:{surface};border:1px solid {line};border-radius:14px;}}
QPushButton {{background:{surface};border:1px solid {line};border-radius:8px;padding:10px 15px;min-height:19px;}}
QPushButton:hover {{border-color:#149a96;background:{alt};}}
QPushButton:pressed {{background:#167f7c;color:white;}}
QPushButton:focus,QLineEdit:focus,QTextEdit:focus,QComboBox:focus {{border:2px solid #169d96;}}
QPushButton:disabled {{color:{muted};background:{alt};}}
QPushButton#primary {{background:#087f80;color:white;border:1px solid #087f80;font-weight:600;}}
QPushButton#primary:hover {{background:#086b6d;}}
QPushButton#nav {{border:0;text-align:left;padding:8px 15px;background:transparent;}}
QPushButton#nav:checked {{background:#d8eeea;color:#075b5a;font-weight:700;}}
QLineEdit,QTextEdit,QComboBox,QSpinBox {{background:{surface};border:1px solid {line};border-radius:7px;padding:9px;selection-background-color:#087f80;}}
QTableWidget {{background:{surface};alternate-background-color:{alt};border:1px solid {line};border-radius:10px;selection-background-color:#d8eeea;selection-color:#17383f;}}
QTableWidget::item {{padding:7px;border-bottom:1px solid {line};}}
QHeaderView::section {{background:{alt};color:{muted};padding:12px 5px;border:0;font-weight:600;}}
QTabWidget::pane {{border:0;background:{bg};}}
QTabBar::tab {{padding:12px 14px;border-bottom:3px solid transparent;}}
QTabBar::tab:selected {{color:#149a96;border-bottom:3px solid #149a96;}}
QScrollArea {{border:0;background:transparent;}}
QScrollArea>QWidget>QWidget {{background:{bg};}}
QComboBox QAbstractItemView {{background:{surface};color:{ink};selection-background-color:#087f80;}}
QToolTip {{background:{surface};color:{ink};border:1px solid {line};padding:6px;}}
QStatusBar {{color:{muted};}}
'''
