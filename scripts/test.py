from datetime import datetime, timezone, timedelta


def beijing_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)

print(beijing_now())