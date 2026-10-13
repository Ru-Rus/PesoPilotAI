from hypothesis import given, strategies as st
from app.finance import minor


@given(st.integers(min_value=1, max_value=50_000_000_000), st.integers(min_value=1, max_value=50_000_000_000))
def test_centavo_addition_is_exact(first, second):
    def pesos(value):
        return f'{value // 100}.{value % 100:02d}'
    assert minor(pesos(first)) + minor(pesos(second)) == minor(pesos(first + second))
