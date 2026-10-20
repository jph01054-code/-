from datetime import datetime
from .rules import parse_opening


def split_time(value):
    date = parse_opening(value)
    return dict(year=str(date.year),month=f'{date.month:02}',day=f'{date.day:02}',
                ampm='PM' if date.hour>=12 else 'AM',hour=f'{date.hour%12 or 12:02}',
                minute=f'{date.minute:02}',second=f'{date.second:02}')


def join_time(parts):
    try:
        hour=int(parts['hour'])
        if not 1<=hour<=12 or parts['ampm'] not in {'AM','PM'}:
            raise ValueError()
        hour=hour%12+(12 if parts['ampm']=='PM' else 0)
        date=datetime(int(parts['year']),int(parts['month']),int(parts['day']),hour,
                      int(parts['minute']),int(parts['second']))
    except (KeyError,ValueError,TypeError):
        raise ValueError('년·월·일과 AM/PM·시·분·초를 확인하세요.') from None
    return date.strftime('%Y-%m-%d %H:%M:%S')
