from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import secrets
import re
import jdatetime

KABUL = timezone(timedelta(hours=4, minutes=30), "Asia/Kabul")
MONTHS = 'حمل ثور جوزا سرطان اسد سنبله میزان عقرب قوس جدی دلو حوت'.split()
ADULT = [list(range(18,10,-1))+list(range(21,29)), list(range(48,40,-1))+list(range(31,39))]
CHILD = [list(range(55,50,-1))+list(range(61,66)), list(range(85,80,-1))+list(range(71,76))]
TEETH = {str(n) for row in ADULT+CHILD for n in row}


def today():
    return datetime.now(KABUL).date().isoformat()


def now():
    return datetime.now(KABUL).isoformat(timespec='seconds')


def money(value):
    try:
        d = Decimal(str(value).replace(',', ''))
        if not d.is_finite() or d < 0 or d != d.quantize(Decimal('.01')):
            raise ValueError('Enter a positive amount with at most two decimal places')
        return int(d * 100)
    except (InvalidOperation, OverflowError):
        raise ValueError('Invalid amount') from None


def amount_text(minor):
    return f'{Decimal(minor) / Decimal(100):.2f}'


def afn(minor):
    return f'{Decimal(minor) / Decimal(100):,.2f} AFN'


def password_hash(password):
    if len(password) < 10:
        raise ValueError('Use at least 10 characters for the password')
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f'scrypt$16384$8$1${salt.hex()}${value.hex()}'


def password_verify(password, encoded):
    try:
        _, n, r, p, salt, expected = encoded.split('$')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def check_date(value, optional=False):
    if optional and not value:
        return ''
    return date.fromisoformat(value).isoformat()


def display_date(value, solar=False, dari=False):
    if not value:
        return '—'
    d = date.fromisoformat(value[:10])
    if solar:
        j = jdatetime.date.fromgregorian(date=d)
        return f'{j.day} {MONTHS[j.month-1]} {j.year}' if dari else f'{j.year:04}/{j.month:02}/{j.day:02} SH'
    return d.isoformat()


def parse_date(value, solar=False):
    value = value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    if solar:
        y,m,d = map(int, value.replace('/', '-').split('-'))
        return jdatetime.date(y,m,d).togregorian().isoformat()
    return check_date(value)


def phone_normalize(value):
    value = (value or '').strip().translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    n = re.sub(r'[\s()\-]', '', value)
    if n.startswith('00'):
        n = '+' + n[2:]
    if re.fullmatch(r'0\d{9}', n):
        n = '+93' + n[1:]
    if re.fullmatch(r'93\d{9}',n):n='+'+n
    if re.fullmatch(r'\+930\d{9}',n):n='+93'+n[4:]
    if n and not re.fullmatch(r'\+?\d{7,15}', n):
        raise ValueError('Enter a valid phone number')
    return n
