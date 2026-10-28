from datetime import date,timedelta
import pytest
import jdatetime
from clinic.domain import money,afn,parse_date,display_date,password_hash,password_verify,phone_normalize,ADULT,CHILD,TEETH


def test_exact_money():
    assert money('0.29')==29
    assert money('1,234.50')==123450
    assert afn(123450)=='1,234.50 AFN'
    for x in ['NaN','Infinity','-1','1.001','oops']:
        with pytest.raises(ValueError):money(x)


def test_passwords():
    a=password_hash('A strong passphrase!');b=password_hash('A strong passphrase!')
    assert a!=b
    assert password_verify('A strong passphrase!',a)
    assert not password_verify('wrong',a)
    with pytest.raises(ValueError):password_hash('short')


def test_fdi():
    assert len(TEETH)==52
    assert ADULT[0]==[18,17,16,15,14,13,12,11,21,22,23,24,25,26,27,28]
    assert CHILD[1]==[85,84,83,82,81,71,72,73,74,75]


def test_calendar_roundtrips():
    d=date(1900,1,1)
    while d<date(2101,1,1):
        j=jdatetime.date.fromgregorian(date=d)
        assert parse_date(f'{j.year}/{j.month}/{j.day}',True)==d.isoformat()
        d+=timedelta(days=1)
    assert parse_date('۱۴۰۳/۰۱/۰۱',True)=='2024-03-20'
    assert display_date('2024-03-20',True,True)=='1 حمل 1403'
    with pytest.raises(ValueError):parse_date('1402/12/30',True)


def test_afghan_and_other_phone():
    assert phone_normalize('۰۷۰ ۱۲۳ ۴۵۶۷')=='+93701234567'
    assert phone_normalize('0044 20 1234 5678')=='+442012345678'
    assert phone_normalize('')==''
    with pytest.raises(ValueError):phone_normalize('abc')


def test_large_money_rendering_stays_exact():
    from clinic.domain import amount_text
    value=9007199254740993
    assert money(amount_text(value))==value
    assert afn(value)=='90,071,992,547,409.93 AFN'
