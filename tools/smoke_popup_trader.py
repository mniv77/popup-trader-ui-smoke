from __future__ import annotations
import argparse
from typing import Any, Dict, Optional
import requests

class Smoke:
    def __init__(self, base_url: str, tenant: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 8.0):
        self.base = base_url.rstrip("/")
        if not self.base.startswith(("http://","https://")):
            self.base = "https://" + self.base
        self.s = requests.Session()
        self.s.headers.update({"User-Agent":"popup-smoke/2.0"})
        if tenant: self.s.headers["X-Tenant"] = tenant
        if api_key: self.s.headers["X-API-Key"] = api_key
        self.timeout = timeout
    def g(self, p: str, **kw): return self.s.get(self.base+p, timeout=self.timeout, **kw)
    def p(self, p: str, **kw): return self.s.post(self.base+p, timeout=self.timeout, **kw)

def run() -> int:
    ap = argparse.ArgumentParser(description="Popup Trader UI smoke (E2E)")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--tenant", default="public")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--exchange", default="NASDAQ")
    ap.add_argument("--side", default="BUY", choices=["BUY","SELL"])
    ap.add_argument("--qty", type=int, default=10)
    ap.add_argument("--entry", type=float, default=None)
    args = ap.parse_args()

    s = Smoke(args.base_url, args.tenant, args.api_key)

    def step(name, fn):
        try:
            fn(); print(f"[PASS] {name}")
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            raise

    step("/healthz", lambda: (lambda r:(r.raise_for_status(), None if r.json().get("ok") else (_ for _ in ()).throw(Exception("ok!=true"))))(s.g("/healthz")))
    def _db():
        r=s.g("/healthz/db"); r.raise_for_status(); j=r.json()
        counts = j.get("counts") or j.get("tables")
        assert j.get("ok") is True and isinstance(counts, dict)
    step("/healthz/db", _db)
    def _js():
        r=s.g("/static/app.js"); r.raise_for_status(); assert "openTradeModal(" in r.text
    step("/static/app.js", _js)

    created={"id":None,"entry":None}
    def _create():
        payload: Dict[str, Any] = {"symbol":args.symbol,"exchange":args.exchange,"side":args.side,"qty":args.qty}
        if args.entry is not None: payload["entry_price"]=float(args.entry); created["entry"]=float(args.entry)
        r=s.p("/api/trade_sessions", json=payload); r.raise_for_status(); j=r.json()
        assert j.get("ok") is True and "id" in j; created["id"]=int(j["id"])
    step("create session", _create)

    def _price():
        r=s.g(f"/price/{args.symbol}/poll"); r.raise_for_status(); j=r.json()
        price=float(j.get("price")); assert price>0
        if created["entry"] is None: created["entry"]=price
    step("price poll", _price)

    def _close():
        sid=created["id"]; assert sid is not None
        entry=float(created["entry"]) if created["entry"] else 200.0
        exit_price=round(entry*(1.003 if args.side=="BUY" else 0.997), 2)
        r=s.p(f"/api/trade_sessions/{sid}/close", json={"reason":"M","exit_price":exit_price}); r.raise_for_status()
        assert r.json().get("ok") is True
    step("close session", _close)

    def _orders():
        r=s.g("/orders"); r.raise_for_status(); html=r.text
        assert args.symbol in html and ">M<" in html
    step("orders page", _orders)

    print("\nAll checks passed.")
    return 0

if __name__=="__main__": raise SystemExit(run())
