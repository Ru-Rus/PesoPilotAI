import pytest
from app.finance import minor, parse_csv

def test_exact_money():
    assert minor('0.01') + minor('0.02') == minor('0.03')

@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '0', '0.001', '1000000001', 'no'])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        minor(value)

def test_csv_preserves_legitimate_duplicates():
    row = '2026-10-01,Coffee,Food & dining,expense,100.25\n'
    rows = parse_csv(('date,description,category,kind,amount\n' + row * 2).encode())
    assert len(rows) == 2
    assert rows[0]['amount_minor'] == 10025

def test_invalid_csv():
    with pytest.raises(ValueError):
        parse_csv(b'date,amount\n2026-10-01,1')
