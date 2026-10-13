import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

CATEGORIES = ['Food & dining', 'Transport', 'Shopping', 'Bills', 'Health', 'Entertainment', 'Income', 'Other']

def minor(value: str) -> int:
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000000') or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError('Amount must be positive, at most one billion pesos, with at most two decimal places')
        return int(amount * 100)
    except InvalidOperation as exc:
        raise ValueError('Invalid peso amount') from exc

def parse_csv(content: bytes) -> list[dict]:
    if len(content) > 1_000_000:
        raise ValueError('CSV exceeds 1 MB')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')), strict=True)
        if reader.fieldnames != ['date', 'description', 'category', 'kind', 'amount']:
            raise ValueError('Expected headers: date,description,category,kind,amount')
        rows = []
        for number, row in enumerate(reader, 2):
            if number > 5001:
                raise ValueError('CSV exceeds 5,000 rows')
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'Invalid columns at row {number}')
            if row['category'] not in CATEGORIES or row['kind'] not in ('income', 'expense'):
                raise ValueError(f'Invalid category or kind at row {number}')
            if not 1 <= len(row['description'].strip()) <= 160:
                raise ValueError(f'Invalid description at row {number}')
            rows.append(dict(occurred_at=date.fromisoformat(row['date']), description=row['description'].strip(), category=row['category'], kind=row['kind'], amount_minor=minor(row['amount'])))
        if not rows:
            raise ValueError('CSV has no transactions')
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('CSV must be valid UTF-8 text') from exc
