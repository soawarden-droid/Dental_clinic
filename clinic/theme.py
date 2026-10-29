"""Shared boutique-clinic design tokens. Widgets and charts use one palette."""
from dataclasses import dataclass
import os
import subprocess
from functools import lru_cache
from PySide6.QtWidgets import QApplication,QStyle


@dataclass(frozen=True)
class Palette:
    background:str; surface:str; ink:str; muted:str; border:str; soft:str
    rose:str; rose_soft:str; mint:str; lilac:str; amber:str; danger:str

LIGHT=Palette('#fbf7f3','#fffdfc','#433744','#847482','#e9dfe5','#f7f0f4','#9e4668','#f5e2ea','#497e76','#8971b0','#a87836','#ac384e')
DARK=Palette('#201c26','#2c2634','#f4edf3','#c1b2c6','#4a3f52','#352d3f','#f0abc6','#493145','#9dd3c4','#c4afe9','#e8c58d','#ffb1bf')


def colors():
    app=QApplication.instance()
    return DARK if app and app.property('clinicDark') else LIGHT


@lru_cache(maxsize=1)
def system_reduced_motion():
    if os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Control Panel\Desktop\WindowMetrics') as key:
                return winreg.QueryValueEx(key,'MinAnimate')[0]=='0'
        except OSError:return False
    try:
        result=subprocess.run(['gsettings','get','org.gnome.desktop.interface','enable-animations'],capture_output=True,text=True,timeout=.4)
        if result.returncode==0:return result.stdout.strip()=='false'
    except (OSError,subprocess.TimeoutExpired):pass
    app=QApplication.instance()
    return bool(app and not app.style().styleHint(QStyle.SH_Widget_Animate))


def motion_enabled(store):
    return store.setting('reduced_motion','False')!='True' and not system_reduced_motion()


def stylesheet(dark=False):
    p=DARK if dark else LIGHT
    return f'''
QWidget {{font-family:'Noto Sans';font-size:14px;color:{p.ink};}}
QMainWindow,QDialog {{background:{p.background};}}
QMenuBar {{background:{p.background};padding:3px;color:{p.muted};}}
QMenuBar::item:selected {{background:{p.rose_soft};}}
QMenu {{background:{p.surface};border:1px solid {p.border};padding:6px;}}
QFrame#sidebar {{background:{p.surface};border:1px solid {p.border};border-radius:22px;}}
QLabel#title {{font-size:26px;font-weight:700;}}
QLabel#subtitle {{color:{p.muted};font-size:13px;}}
QLabel#brand {{font-size:17px;font-weight:700;color:{p.rose};}}
QLabel#metric {{font-size:25px;font-weight:700;}}
QLabel#avatar {{background:{p.rose_soft};color:{p.rose};border-radius:40px;font-size:28px;font-weight:700;}}
QLabel#error {{color:{p.danger};font-size:13px;}}
QLabel#alert {{background:{p.rose_soft};color:{p.ink};border:1px solid {p.border};border-radius:12px;padding:12px;}}
QFrame#card,QFrame#hero {{background:{p.surface};border:1px solid {p.border};border-radius:18px;}}
QFrame#stat:hover {{border:1px solid {p.rose};}}
QFrame#stat {{background:{p.surface};border:1px solid {p.border};border-radius:16px;}}
QFrame#stat:focus {{border:2px solid {p.rose};}}
QPushButton,QToolButton {{background:{p.surface};border:1px solid {p.border};border-radius:11px;padding:9px 14px;min-height:20px;}}
QPushButton:hover,QToolButton:hover {{border-color:{p.rose};background:{p.soft};}}
QPushButton:pressed,QToolButton:pressed {{background:{p.rose_soft};}}
QPushButton:focus,QToolButton:focus,QLineEdit:focus,QTextEdit:focus,QComboBox:focus {{border:2px solid {p.rose};}}
QPushButton:disabled {{color:{p.muted};background:{p.soft};}}
QPushButton#primary {{background:{p.rose};color:{'#251925' if dark else '#fffdfc'};border:1px solid {p.rose};font-weight:600;}}
QPushButton#primary:hover {{background:{p.lilac};border-color:{p.lilac};}}
QPushButton#nav {{border:0;text-align:left;padding:8px;background:transparent;}}
QPushButton#nav:checked {{background:{p.rose_soft};color:{p.rose};font-weight:700;}}
QPushButton#badge {{border-radius:13px;padding:3px 9px;background:{p.soft};min-height:18px;color:{p.muted};}}
QLineEdit,QTextEdit,QComboBox,QSpinBox {{background:{p.surface};border:1px solid {p.border};border-radius:9px;padding:9px;selection-background-color:{p.rose};}}
QTableWidget {{background:{p.surface};alternate-background-color:{p.soft};border:1px solid {p.border};border-radius:13px;selection-background-color:{p.rose_soft};selection-color:{p.ink};}}
QTableWidget::item {{padding:8px;border-bottom:1px solid {p.border};}}
QHeaderView::section {{background:{p.soft};color:{p.muted};padding:11px 5px;border:0;font-weight:600;}}
QTabWidget::pane {{border:0;background:{p.background};}}
QTabBar::tab {{padding:10px 12px;border-bottom:3px solid transparent;color:{p.muted};}}
QTabBar::tab:selected {{color:{p.rose};border-bottom:3px solid {p.rose};}}
QScrollArea {{border:0;background:transparent;}}
QScrollArea>QWidget>QWidget {{background:{p.background};}}
QComboBox::drop-down {{border:0;width:24px;background:transparent;}}
QComboBox QAbstractItemView {{background:{p.surface};color:{p.ink};selection-background-color:{p.rose_soft};}}
QToolTip {{background:{p.surface};color:{p.ink};border:1px solid {p.border};padding:8px;}}
QStatusBar {{color:{p.muted};}}
QScrollBar:vertical {{background:transparent;width:9px;margin:2px;}}
QScrollBar::handle:vertical {{background:{p.border};border-radius:4px;min-height:28px;}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
'''


def apply_app_theme(store):
    from PySide6.QtCore import Qt
    from . import i18n
    app=QApplication.instance();mode=store.setting('theme','system')
    dark=mode=='dark' or (mode=='system' and app.styleHints().colorScheme()==Qt.ColorScheme.Dark)
    app.setProperty('clinicDark',dark)
    app.setStyleSheet(stylesheet(dark)+("\nQWidget {font-family:'Noto Sans Arabic UI';} QPushButton#nav {text-align:right;}" if i18n.LANG=='fa_AF' else ''))


def tooth_style(status=None):
    p=colors();color=p.amber if status=='planned' else p.mint if status=='completed' else p.border
    return 'padding:5px;border:2px solid '+color+';border-radius:13px 13px 8px 8px;'
