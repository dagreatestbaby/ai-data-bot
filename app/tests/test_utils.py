import pytest
import pandas as pd
from app.utils import get_columns, aggregate_column

def test_get_columns():
    df = pd.DataFrame({'A': [1,2,3], 'B': [4,5,6]})
    cols = get_columns(df)
    assert 'A' in cols
    assert 'B' in cols

def test_aggregate_column_mean():
    df = pd.DataFrame({'numbers': [1,2,3,4,5]})
    result = aggregate_column(df, 'numbers', 'mean')
    assert "Mean of numbers:" in result
    assert str(df['numbers'].mean()) in result

def test_aggregate_column_unsupported():
    df = pd.DataFrame({'numbers': [1,2,3]})
    result = aggregate_column(df, 'numbers', 'median')
    assert "Unsupported operation." in result

def test_aggregate_column_missing_column():
    df = pd.DataFrame({'numbers': [1,2,3]})
    result = aggregate_column(df, 'not_here', 'mean')
    assert "Column not_here not found." in result

