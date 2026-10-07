"""Консольный клиент. Команды: n (след. день), p (пред.), d ГГГГ-ММ-ДД, a (добавить), q."""
import json
import sys
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, method=method,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        return e.code, json.load(e)


def show(day):
    status, res = call("GET", f"/api/trips?date={day.isoformat()}")
    s = res["summary"]
    print(f"\n=== {res['date']} ===")
    print(f"Поездок: {s['trips']} | Выручка: {s['revenue']} | Комиссия: {s['commission']} | На руки: {s['on_hand']}")
    print(f"Наличные: {s['cash']['trips']} шт. / {s['cash']['amount']}  |  Карта: {s['card']['trips']} шт. / {s['card']['amount']}")
    for t in res["trips"]:
        print(f"  {t['start'][11:16]}–{t['end'][11:16]}  {t['amount']:>7}  {t['payment']:<4} ком. {t['commission']}")
    if not res["trips"]:
        print("  (нет поездок)")


def add(day):
    try:
        print(f"Время вводите как ЧЧ:ММ, часовой пояс +05:00, дата {day}")
        trip = {
            "start": f"{day}T{input('Начало: ')}:00+05:00",
            "end": f"{day}T{input('Конец: ')}:00+05:00",
            "amount": float(input("Сумма: ")),
            "payment": input("Оплата (cash/card): ").strip(),
            "commission": float(input("Комиссия: ") or 0),
        }
    except ValueError:
        return print("Ошибка: число введено неверно")
    status, res = call("POST", "/api/trips", trip)
    print({201: "Добавлено", 200: "Такая поездка уже есть (дубль не создан)"}.get(status) or f"Ошибка {status}: {res['error']}")


def main():
    day = date.today()
    while True:
        show(day)
        cmd = input("\n[n]ext [p]rev [d]ate [a]dd [q]uit > ").strip().lower()
        if cmd == "n":
            day += timedelta(days=1)
        elif cmd == "p":
            day -= timedelta(days=1)
        elif cmd.startswith("d"):
            try:
                day = date.fromisoformat(cmd[1:].strip() or input("Дата: "))
            except ValueError:
                print("Формат: ГГГГ-ММ-ДД")
        elif cmd == "a":
            add(day)
        elif cmd == "q":
            break


if __name__ == "__main__":
    main()
