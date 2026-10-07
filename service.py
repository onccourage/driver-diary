"""Бизнес-логика: валидация, хранилище, сводка. Без HTTP."""
import hashlib
import json
import threading
from datetime import date, datetime
from pathlib import Path

PAYMENTS = ("cash", "card")


class ValidationError(ValueError):
    pass


class ConflictError(Exception):
    pass


def _parse_dt(value, field):
    if not isinstance(value, str):
        raise ValidationError(f"{field}: ожидается строка ISO 8601")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field}: неверный формат даты '{value}'")
    if dt.tzinfo is None:
        raise ValidationError(f"{field}: нужен часовой пояс, например +05:00")
    return dt


def _num(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field}: ожидается число")
    return value


def validate(raw):
    """Проверяет и нормализует поездку. Бросает ValidationError."""
    if not isinstance(raw, dict):
        raise ValidationError("ожидается JSON-объект")
    start = _parse_dt(raw.get("start"), "start")
    end = _parse_dt(raw.get("end"), "end")
    if end <= start:
        raise ValidationError("end должен быть позже start")
    amount = _num(raw.get("amount"), "amount")
    if amount <= 0:
        raise ValidationError("amount должен быть > 0")
    commission = _num(raw.get("commission", 0), "commission")
    if commission < 0 or commission > amount:
        raise ValidationError("commission должна быть в диапазоне 0..amount")
    payment = raw.get("payment")
    if payment not in PAYMENTS:
        raise ValidationError("payment должен быть 'cash' или 'card'")

    trip = {
        "start": raw["start"], "end": raw["end"], "amount": amount,
        "payment": payment, "commission": commission,
    }
    trip_id = raw.get("id")
    if trip_id is None:
        # без id берём отпечаток содержимого: повтор даст тот же id
        key = f'{trip["start"]}|{trip["end"]}|{amount}|{payment}|{commission}'
        trip_id = hashlib.sha1(key.encode()).hexdigest()[:12]
    elif not isinstance(trip_id, str) or not trip_id.strip():
        raise ValidationError("id должен быть непустой строкой")
    return {"id": trip_id.strip(), **trip}


def _fingerprint(t):
    return (t["start"], t["end"], t["amount"], t["payment"], t["commission"])


def trip_day(trip):
    """День поездки — по дате начала в её собственном часовом поясе."""
    return datetime.fromisoformat(trip["start"]).date()


def summarize(trips):
    summary = {
        "trips": len(trips),
        "revenue": sum(t["amount"] for t in trips),
        "commission": sum(t["commission"] for t in trips),
        "cash": {"trips": 0, "amount": 0},
        "card": {"trips": 0, "amount": 0},
    }
    for t in trips:
        summary[t["payment"]]["trips"] += 1
        summary[t["payment"]]["amount"] += t["amount"]
    # «на руки» = выручка минус комиссия
    summary["on_hand"] = summary["revenue"] - summary["commission"]
    return summary


class TripStore:
    def __init__(self, path=None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._trips = {}
        if self._path and self._path.exists():
            for raw in json.loads(self._path.read_text("utf-8")):
                trip = validate(raw)
                self._trips[trip["id"]] = trip

    def add(self, raw):
        """Возвращает (trip, created). Повтор той же поездки -> (existing, False)."""
        trip = validate(raw)
        with self._lock:
            existing = self._trips.get(trip["id"])
            if existing:
                if existing == trip:
                    return existing, False
                raise ConflictError(f"поездка с id '{trip['id']}' уже есть и отличается")
            for t in self._trips.values():
                if _fingerprint(t) == _fingerprint(trip):
                    return t, False  # тот же рейс, но с другим id
            self._trips[trip["id"]] = trip
            self._save()
            return trip, True

    def for_day(self, day: date):
        with self._lock:
            trips = [t for t in self._trips.values() if trip_day(t) == day]
        return sorted(trips, key=lambda t: datetime.fromisoformat(t["start"]))

    def _save(self):
        if self._path:
            data = list(self._trips.values())
            self._path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
