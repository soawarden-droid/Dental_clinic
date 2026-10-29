"""Reusable cards, restrained decorative geometry and accessible local charts."""
from PySide6.QtCore import Qt,QRectF,QPointF,QVariantAnimation,QEasingCurve,Signal
from PySide6.QtGui import QPainter,QPainterPath,QColor,QPen,QFont,QLinearGradient,QPixmap
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QWidget,QSizePolicy,QGraphicsDropShadowEffect
from .theme import colors
from .widgets import label
from .i18n import tr
from .domain import afn


class Card(QFrame):
    def __init__(self,title='',subtitle='',parent=None):
        super().__init__(parent);self.setObjectName('card')
        self.content=QVBoxLayout(self);self.content.setContentsMargins(19,17,19,17);self.content.setSpacing(10)
        if title:self.content.addWidget(label(title,'brand'))
        if subtitle:self.content.addWidget(label(subtitle,'subtitle'))


class Hero(Card):
    def __init__(self,title,subtitle):
        super().__init__(title,subtitle);self.setObjectName('hero');self.background_image=None;self.opacity=.15
    def set_background(self,path,opacity):
        self.background_image=QPixmap(str(path));self.opacity=max(0,min(30,opacity))/100;self.update()
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(Qt.NoPen)
        p.setClipPath(self.clip_path())
        if self.background_image and not self.background_image.isNull():
            p.save();p.setOpacity(self.opacity);p.drawPixmap(self.rect(),self.background_image);p.restore()
        right=self.width() if self.layoutDirection()==Qt.LeftToRight else 0
        for radius,offset,color in [(106,0,colors().rose_soft),(65,40,colors().soft)]:
            p.setBrush(QColor(color));p.drawEllipse(QPointF(right-12-offset,7),radius,radius)
        p.end()
    def clip_path(self):
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),18,18);return path


class StatCard(Card):
    clicked=Signal()
    def __init__(self,title,value,caption='',tone='rose'):
        super().__init__();self.setObjectName('stat');self.setFocusPolicy(Qt.StrongFocus);self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(tr(title)+': '+value)
        self.content.setContentsMargins(17,14,17,14)
        self.content.addWidget(label(title,'subtitle'));self.content.addWidget(label(value,'metric'))
        if caption:self.content.addWidget(label(caption,'subtitle'))
        self.tone=tone;self.setMinimumHeight(112)
        shadow=QGraphicsDropShadowEffect(self);shadow.setBlurRadius(14);shadow.setOffset(0,3);shadow.setColor(QColor(80,35,65,12));self.setGraphicsEffect(shadow)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:self.clicked.emit()
        super().mouseReleaseEvent(event)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Space):self.clicked.emit();event.accept()
        else:super().keyPressEvent(event)


class Chart(QWidget):
    activated=Signal()
    categoryActivated=Signal(str)
    def __init__(self,kind,rows,animated=False,date_format=None,has_records=True,parent=None):
        super().__init__(parent);self.kind=kind;self.rows=rows;self.progress=1.0;self.date_format=date_format or (lambda v:v)
        self.has_records=has_records;self.setMinimumHeight(max(166,len(rows)*35+12) if kind=='status' else 166);self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus);self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(tr({'trend':'Net collections','donut':'Completed treatments','status':'Appointment status'}[kind]))
        self.setAccessibleDescription('; '.join(str(r) for r in rows) if has_records else tr('No records in this period'))
        self.animation=None
        if animated and has_records and self.total_activity():
            self.progress=0.0;self.animation=QVariantAnimation(self);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.setDuration(260);self.animation.setEasingCurve(QEasingCurve.OutCubic)
            self.animation.valueChanged.connect(self.frame);self.animation.start()
    def total_activity(self):return sum(abs(r.get('amount',r.get('count',0))) for r in self.rows)
    def frame(self,value):self.progress=float(value);self.update()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            if self.kind=='status' and self.rows:
                height=min(35,(self.height()-12)/len(self.rows));idx=int((event.position().y()-6)/height)
                if 0<=idx<len(self.rows):self.categoryActivated.emit(self.rows[idx]['status'])
            else:self.activated.emit()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Space):self.activated.emit()
        else:super().keyPressEvent(event)
    def mouseMoveEvent(self,event):
        if self.kind=='trend' and self.rows:
            idx=max(0,min(len(self.rows)-1,round((event.position().x()-15)/max(1,self.width()-30)*(len(self.rows)-1))))
            row=self.rows[idx];self.setToolTip(self.date_format(row['date'])+' · '+afn(row['amount']))
        else:self.setToolTip(tr('Open underlying records'))
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);p=colors();painter.setPen(QColor(p.muted));font=painter.font();font.setPixelSize(12);painter.setFont(font)
        if not self.has_records or not self.rows:
            painter.drawText(self.rect().adjusted(12,8,-12,-8),Qt.AlignCenter|Qt.TextWordWrap,tr('No records in this period')+'\n'+tr('Saved activity will appear here.'));return
        if self.kind=='trend':self.draw_trend(painter,p)
        elif self.kind=='donut':self.draw_donut(painter,p)
        else:self.draw_status(painter,p)
    def draw_trend(self,painter,p):
        area=QRectF(10,24,self.width()-20,self.height()-53);values=[r['amount'] for r in self.rows];lo=min(0,min(values));hi=max(0,max(values))
        if hi==lo:hi=lo+100
        def point(index,value):return QPointF(area.left()+area.width()*index/max(1,len(values)-1),area.bottom()-area.height()*(value-lo)/(hi-lo)*self.progress)
        painter.setPen(QPen(QColor(p.border),1))
        for step in range(4):y=area.top()+area.height()*step/3;painter.drawLine(QPointF(area.left(),y),QPointF(area.right(),y))
        path=QPainterPath();path.moveTo(point(0,values[0]))
        for i,value in enumerate(values[1:],1):path.lineTo(point(i,value))
        fill=QPainterPath(path);fill.lineTo(point(len(values)-1,lo));fill.lineTo(point(0,lo));fill.closeSubpath()
        gradient=QLinearGradient(0,area.top(),0,area.bottom());a=QColor(p.rose);a.setAlpha(65);b=QColor(p.rose);b.setAlpha(5);gradient.setColorAt(0,a);gradient.setColorAt(1,b)
        painter.fillPath(fill,gradient);painter.setPen(QPen(QColor(p.rose),2.5));painter.drawPath(path)
        painter.setPen(QColor(p.muted));painter.drawText(QRectF(8,0,self.width()-16,20),Qt.AlignLeft,afn(hi));painter.drawText(QRectF(8,self.height()-25,self.width()/2,22),Qt.AlignLeft,self.date_format(self.rows[0]['date']));painter.drawText(QRectF(self.width()/2,self.height()-25,self.width()/2-8,22),Qt.AlignRight,self.date_format(self.rows[-1]['date']))
    def draw_donut(self,painter,p):
        total=sum(r['count'] for r in self.rows)
        if not total:return
        size=min(144,self.height()-14,self.width()-14);rect=QRectF((self.width()-size)/2,(self.height()-size)/2,size,size)
        palette=[p.rose,p.lilac,p.mint,p.amber,p.muted];start=90*16
        painter.setBrush(Qt.NoBrush);painter.setPen(QPen(QColor(p.border),18));painter.drawEllipse(rect.adjusted(10,10,-10,-10))
        for index,row in enumerate(self.rows):
            span=-360*16*row['count']/total*self.progress;painter.setPen(QPen(QColor(palette[index%len(palette)]),18,Qt.SolidLine,Qt.FlatCap));painter.drawArc(rect.adjusted(10,10,-10,-10),round(start),round(span));start+=span
        font=painter.font();font.setPixelSize(29);font.setBold(True);painter.setFont(font);painter.setPen(QColor(p.ink));painter.drawText(rect,Qt.AlignCenter,str(total))
    def draw_status(self,painter,p):
        total=sum(r['count'] for r in self.rows);n=len(self.rows);height=min(35,(self.height()-12)/max(1,n));palette=[p.mint,p.rose,p.lilac,p.amber,p.muted]
        for i,row in enumerate(self.rows):
            y=6+i*height;painter.setPen(QColor(p.muted));painter.drawText(QRectF(4,y,self.width()-8,18),Qt.AlignLeft if self.layoutDirection()==Qt.LeftToRight else Qt.AlignRight,tr(row['status'])+' · '+str(row['count']))
            rect=QRectF(4,y+21,self.width()-8,5);painter.setPen(Qt.NoPen);painter.setBrush(QColor(p.border));painter.drawRoundedRect(rect,2.5,2.5);rect.setWidth(rect.width()*row['count']/max(1,total)*self.progress);painter.setBrush(QColor(palette[i%len(palette)]));painter.drawRoundedRect(rect,2.5,2.5)
