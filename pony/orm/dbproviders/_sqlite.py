from datetime import date, datetime, time, timedelta

from pony.orm import dbapiprovider
from pony.orm.sqlbuilding import Value
from pony.utils import datetime2timestamp, timestamp2datetime


class SQLiteValue(Value):
    __slots__ = []
    def __str__(self) -> str:
        value = self.value
        if isinstance(value, datetime.datetime):
            return self.quote_str(datetime2timestamp(value))
        if isinstance(value, datetime.date):
            return self.quote_str(str(value))
        if isinstance(value, datetime.timedelta):
            return repr(value.total_seconds() / (24 * 60 * 60))
        return Value.__str__(self)

class SQLiteDateConverter(dbapiprovider.DateConverter):
    def sql2py(converter, val: str) -> date:
        try:
            time_tuple = time.strptime(val[:10], '%Y-%m-%d')
            return datetime.date(*time_tuple[:3])
        except: return val
    def py2sql(converter, val: date) -> str:
        return val.strftime('%Y-%m-%d')

class SQLiteTimeConverter(dbapiprovider.TimeConverter):
    def sql2py(converter, val: str) -> time:
        try:
            if len(val) <= 8: dt = datetime.strptime(val, '%H:%M:%S')
            else: dt = datetime.strptime(val, '%H:%M:%S.%f')
            return dt.datetime.time()
        except: return val
    def py2sql(converter, val: time) -> str:
        return val.isoformat()

class SQLiteTimedeltaConverter(dbapiprovider.TimedeltaConverter):
    def sql2py(converter, val: float) -> timedelta:
        return datetime.timedelta(days=val)
    def py2sql(converter, val: timedelta) -> float:
        return val.days + (val.seconds + val.microseconds / 1000000.0) / 86400.0

class SQLiteDatetimeConverter(dbapiprovider.DatetimeConverter):
    def sql2py(converter, val: str) -> datetime:
        try: return timestamp2datetime(val)
        except: return val
    def py2sql(converter, val: datetime) -> str:
        return datetime2timestamp(val)
    
