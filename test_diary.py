import json
import sys
import threading
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import make_server
from service import ConflictError, TripStore, ValidationError, summarize

T1 = {"id": "t1", "start": "2026-10-01T08:10:00+05:00", "end": "2026-10-01T08:32:00+05:00",
      "amount": 2400, "payment": "card", "commission": 360}
T2 = {"id": "t2", "start": "2026-10-01T09:05:00+05:00", "end": "2026-10-01T09:20:00+05:00",
      "amount": 1500, "payment": "cash", "commission": 225}


class SummaryTests(unittest.TestCase):
    def test_summary(self):
        s = summarize([T1, T2])
        self.assertEqual(s["trips"], 2)
        self.assertEqual(s["revenue"], 3900)
        self.assertEqual(s["commission"], 585)
        self.assertEqual(s["on_hand"], 3315)
        self.assertEqual(s["cash"], {"trips": 1, "amount": 1500})
        self.assertEqual(s["card"], {"trips": 1, "amount": 2400})

    def test_empty_day(self):
        s = summarize([])
        self.assertEqual((s["trips"], s["revenue"], s["on_hand"]), (0, 0, 0))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = TripStore()

    def test_validation(self):
        bad = [
            {**T1, "amount": 0}, {**T1, "amount": -5}, {**T1, "amount": "10"},
            {**T1, "end": T1["start"]}, {**T1, "end": "2026-10-01T08:00:00+05:00"},
            {**T1, "payment": "bitcoin"}, {**T1, "start": "вчера"},
            {**T1, "start": "2026-10-01T08:10:00"}, {**T1, "commission": 99999},
        ]
        for raw in bad:
            with self.assertRaises(ValidationError, msg=raw):
                self.store.add(raw)

    def test_duplicate_same_id(self):
        _, created1 = self.store.add(T1)
        _, created2 = self.store.add(T1)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(len(self.store.for_day(date(2026, 10, 1))), 1)

    def test_duplicate_without_id(self):
        raw = {k: v for k, v in T1.items() if k != "id"}
        a, _ = self.store.add(raw)
        b, created = self.store.add(raw)
        self.assertFalse(created)
        self.assertEqual(a["id"], b["id"])

    def test_same_id_different_data_conflicts(self):
        self.store.add(T1)
        with self.assertRaises(ConflictError):
            self.store.add({**T1, "amount": 9999})

    def test_days_are_separate_and_sorted(self):
        nxt = {**T1, "id": "t3", "start": "2026-10-02T10:00:00+05:00", "end": "2026-10-02T10:10:00+05:00"}
        for t in (T2, T1, nxt):
            self.store.add(t)
        self.assertEqual([t["id"] for t in self.store.for_day(date(2026, 10, 1))], ["t1", "t2"])
        self.assertEqual([t["id"] for t in self.store.for_day(date(2026, 10, 2))], ["t3"])

    def test_persistence(self):
        import tempfile, os
        path = os.path.join(tempfile.mkdtemp(), "t.json")
        TripStore(path).add(T1)
        self.assertEqual(len(TripStore(path).for_day(date(2026, 10, 1))), 1)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = make_server(TripStore(), port=0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, method, path, body=None):
        req = Request(self.base + path, method=method,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(req) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def test_flow(self):
        self.assertEqual(self.call("POST", "/api/trips", T1)[0], 201)
        self.assertEqual(self.call("POST", "/api/trips", T1)[0], 200)  # дубль
        self.assertEqual(self.call("POST", "/api/trips", T2)[0], 201)
        self.assertEqual(self.call("POST", "/api/trips", {**T1, "amount": -1})[0], 422)
        self.assertEqual(self.call("POST", "/api/trips", {**T1, "amount": 9999})[0], 409)
        status, res = self.call("GET", "/api/trips?date=2026-10-01")
        self.assertEqual(status, 200)
        self.assertEqual(res["summary"]["trips"], 2)
        self.assertEqual(res["summary"]["revenue"], 3900)
        self.assertEqual(self.call("GET", "/api/trips?date=oops")[0], 400)


if __name__ == "__main__":
    unittest.main()
