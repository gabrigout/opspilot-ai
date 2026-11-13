"""API tests: auth, validation, orders, couriers, incidents, dashboard, reports, simulation."""
from sqlalchemy import func, select

from app.models import Courier, Incident, Order, Restaurant
from app.models.enums import CourierStatus, OrderStatus

API = "/api/v1"


# ------------------------------------------------------------------ auth
def test_login_ok_and_me(client):
    r = client.post(f"{API}/auth/login", json={"email": "admin@opspilot.local", "password": "opspilot-demo"})
    assert r.status_code == 200 and r.json()["expires_in"] > 0
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["role"] == "ADMIN"


def test_login_wrong_password_is_generic(client):
    r = client.post(f"{API}/auth/login", json={"email": "admin@opspilot.local", "password": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r2 = client.post(f"{API}/auth/login", json={"email": "ghost@opspilot.local", "password": "nope"})
    assert r.json()["error"]["message"] == r2.json()["error"]["message"]


def test_routes_require_token(client):
    for path in ("/orders", "/dashboard/overview", "/ai/status", "/couriers"):
        assert client.get(API + path).status_code == 401
    assert client.get(f"{API}/orders", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_logout_revokes_token(client, auth):
    assert client.post(f"{API}/auth/logout", headers=auth).status_code == 204
    assert client.get(f"{API}/auth/me", headers=auth).status_code == 401


def test_password_is_hashed(db):
    from app.models import User
    u = db.scalars(select(User)).first()
    assert u.hashed_password.startswith("$2") and "opspilot-demo" not in u.hashed_password


def test_viewer_cannot_write(client, viewer_auth, db):
    code = db.scalars(select(Order.code).where(Order.status == OrderStatus.RECEIVED)).first()
    r = client.patch(f"{API}/orders/{code}/status", json={"status": "CONFIRMED"}, headers=viewer_auth)
    assert r.status_code == 403
    r = client.post(f"{API}/incidents", json={"type": "CUSTOMER_COMPLAINT", "description": "teste de permissão"}, headers=viewer_auth)
    assert r.status_code == 403
    assert client.get(f"{API}/orders", headers=viewer_auth).status_code == 200


def test_errors_do_not_leak_internals(client, auth):
    r = client.get(f"{API}/orders/ORD-999999", headers=auth)
    assert r.status_code == 404 and set(r.json()["error"]) == {"code", "message", "details"}


# ------------------------------------------------------------------ orders
def test_list_filter_search_and_pagination(client, auth, db):
    total = db.scalar(select(func.count()).select_from(Order))
    assert total >= 100
    r = client.get(f"{API}/orders?page_size=10", headers=auth).json()
    assert r["total"] == total and len(r["items"]) == 10
    delivered = client.get(f"{API}/orders?status=DELIVERED&page_size=100", headers=auth).json()
    assert delivered["total"] > 0 and all(o["status"] == "DELIVERED" for o in delivered["items"])
    first = r["items"][0]["code"]
    found = client.get(f"{API}/orders?q={first[-4:]}", headers=auth).json()
    assert any(o["code"] == first for o in found["items"])
    rest = db.scalars(select(Restaurant)).first()
    by_rest = client.get(f"{API}/orders?restaurant={rest.code}&page_size=100", headers=auth).json()
    assert by_rest["items"] and all(o["restaurant"]["code"] == rest.code for o in by_rest["items"])


def test_delayed_filter_matches_rule(client, auth):
    d = client.get(f"{API}/orders?situation=delayed&page_size=100", headers=auth).json()
    assert d["total"] >= 5
    for o in d["items"]:
        assert o["is_delayed"] and o["delay_minutes"] > 0 and o["remaining_minutes"] < 0
        assert o["status"] not in ("DELIVERED", "CANCELLED")


def test_at_risk_filter_has_reasons(client, auth):
    d = client.get(f"{API}/orders?situation=at_risk&page_size=100", headers=auth).json()
    assert d["total"] >= 3 and all(o["risk_reasons"] and not o["is_delayed"] for o in d["items"])


def test_order_detail_and_history(client, auth):
    code = client.get(f"{API}/orders?status=DELIVERED", headers=auth).json()["items"][0]["code"]
    d = client.get(f"{API}/orders/{code}", headers=auth).json()
    assert d["items"] and d["history"][0]["event_type"] == "CREATED" and d["allowed_transitions"] == []
    h = client.get(f"{API}/orders/{code}/history", headers=auth).json()
    assert h["events"][-1]["to_status"] == "DELIVERED"
    assert client.get(f"{API}/orders/{d['id']}", headers=auth).json()["code"] == code  # by UUID too


def test_status_update_valid_and_invalid(client, auth, db):
    code = db.scalars(select(Order.code).where(Order.status == OrderStatus.RECEIVED)).first()
    bad = client.patch(f"{API}/orders/{code}/status", json={"status": "DELIVERED"}, headers=auth)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_transition"
    ok = client.patch(f"{API}/orders/{code}/status", json={"status": "CONFIRMED"}, headers=auth)
    assert ok.status_code == 200 and ok.json()["status"] == "CONFIRMED"
    assert ok.json()["history"][-1]["to_status"] == "CONFIRMED"
    assert client.patch(f"{API}/orders/{code}/status", json={"status": "NOPE"}, headers=auth).status_code == 422


def test_cannot_start_delivery_without_courier(client, auth, db):
    code = db.scalars(select(Order.code).where(Order.status == OrderStatus.WAITING_COURIER)).first()
    r = client.patch(f"{API}/orders/{code}/status", json={"status": "IN_DELIVERY"}, headers=auth)
    assert r.status_code == 422 and "courier" in r.json()["error"]["message"]


def test_assignment_flow_updates_courier(client, auth, db):
    code = db.scalars(select(Order.code).where(Order.status == OrderStatus.WAITING_COURIER)).first()
    rec = client.get(f"{API}/orders/{code}/courier-recommendations", headers=auth).json()
    assert rec["auto_assigned"] is False and rec["candidates"]
    scores = [c["score"] for c in rec["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert client.get(f"{API}/orders/{code}", headers=auth).json()["courier"] is None  # nothing auto-assigned
    best = rec["candidates"][0]["courier"]["code"]
    r = client.post(f"{API}/orders/{code}/assign", json={"courier_id": best}, headers=auth)
    assert r.status_code == 200 and r.json()["courier"]["code"] == best
    db.expire_all()
    assert db.scalars(select(Courier).where(Courier.code == best)).first().status == CourierStatus.ASSIGNED
    again = client.post(f"{API}/orders/{code}/assign", json={"courier_id": best}, headers=auth)
    assert again.status_code == 409  # courier no longer available


# ------------------------------------------------------------------ couriers / restaurants
def test_couriers(client, auth):
    allc = client.get(f"{API}/couriers", headers=auth).json()
    assert allc["total"] >= 30 and sum(allc["summary"].values()) == allc["total"]
    av = client.get(f"{API}/couriers/available", headers=auth).json()
    assert av["total"] > 0 and all(c["status"] == "AVAILABLE" for c in av["items"])
    d = client.get(f"{API}/couriers/{av['items'][0]['code']}", headers=auth).json()
    assert "recent_orders" in d


def test_courier_status_guard(client, auth):
    busy = next(c for c in client.get(f"{API}/couriers?status=DELIVERING", headers=auth).json()["items"])
    r = client.patch(f"{API}/couriers/{busy['code']}/status", json={"status": "OFFLINE"}, headers=auth)
    assert r.status_code == 409
    free = client.get(f"{API}/couriers/available", headers=auth).json()["items"][0]
    assert client.patch(f"{API}/couriers/{free['code']}/status", json={"status": "OFFLINE"}, headers=auth).status_code == 200


def test_restaurants_and_slow_prep_detection(client, auth):
    d = client.get(f"{API}/restaurants?period_hours=72", headers=auth).json()
    assert d["total"] >= 15
    slow = [r["name"] for r in d["items"] if r["prep_alert"]]
    assert "Sabor Urbano" in slow
    one = client.get(f"{API}/restaurants/{d['items'][0]['code']}", headers=auth).json()
    assert "recent_orders" in one


# ------------------------------------------------------------------ incidents
def test_incident_lifecycle_with_history(client, auth):
    code = client.get(f"{API}/orders?status=PREPARING", headers=auth).json()["items"][0]["code"]
    c = client.post(f"{API}/incidents", headers=auth, json={
        "type": "SLOW_PREPARATION", "priority": "HIGH", "description": "Cozinha demorando", "order_ref": code})
    assert c.status_code == 201
    inc = c.json()
    assert inc["status"] == "OPEN" and inc["order"]["code"] == code
    u = client.patch(f"{API}/incidents/{inc['code']}", headers=auth, json={"status": "INVESTIGATING", "assignee": "Ana"})
    assert u.status_code == 200 and u.json()["status"] == "INVESTIGATING"
    # resolving needs a resolution
    assert client.patch(f"{API}/incidents/{inc['code']}", headers=auth, json={"status": "RESOLVED"}).status_code == 409
    r = client.patch(f"{API}/incidents/{inc['code']}", headers=auth, json={"status": "RESOLVED", "resolution": "Restaurante acelerou."})
    assert r.json()["resolved_at"]
    assert client.patch(f"{API}/incidents/{inc['code']}", headers=auth, json={"status": "CLOSED"}).status_code == 200
    assert client.patch(f"{API}/incidents/{inc['code']}", headers=auth, json={"priority": "LOW"}).status_code == 409
    hist = client.get(f"{API}/incidents/{inc['code']}", headers=auth).json()["history"]
    assert [h["event_type"] for h in hist][0] == "INCIDENT_CREATED" and len(hist) >= 4


def test_incident_validation(client, auth):
    bad = [
        {"type": "NOPE", "description": "descrição válida"},
        {"type": "CUSTOMER_COMPLAINT", "description": "x"},
        {"type": "CUSTOMER_COMPLAINT", "description": "descrição válida", "priority": "URGENT"},
    ]
    for body in bad:
        assert client.post(f"{API}/incidents", json=body, headers=auth).status_code == 422
    r = client.post(f"{API}/incidents", json={"type": "CUSTOMER_COMPLAINT", "description": "descrição válida", "order_ref": "ORD-0"}, headers=auth)
    assert r.status_code == 404


def test_open_incidents_filter(client, auth):
    d = client.get(f"{API}/incidents?open_only=true", headers=auth).json()
    assert d["total"] > 0 and all(i["status"] in ("OPEN", "INVESTIGATING", "WAITING_ACTION") for i in d["items"])
    ranks = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    r = [ranks[i["priority"]] for i in d["items"]]
    assert r == sorted(r, reverse=True)


# ------------------------------------------------------------------ dashboard / metrics
def test_kpis_match_database(client, auth, db):
    k = client.get(f"{API}/dashboard/metrics?hours=24", headers=auth).json()
    from app.models.enums import ACTIVE_STATUSES
    assert k["in_progress"] == db.scalar(select(func.count()).select_from(Order).where(Order.status.in_(ACTIVE_STATUSES)))
    assert k["available_couriers"] == db.scalar(select(func.count()).select_from(Courier).where(Courier.status == CourierStatus.AVAILABLE))
    assert k["open_incidents"] == len(client.get(f"{API}/incidents?open_only=true", headers=auth).json()["items"])
    delayed = client.get(f"{API}/orders?situation=delayed", headers=auth).json()["total"]
    assert k["delayed"] == delayed
    assert db.scalar(select(func.count()).select_from(Incident)) >= 20


def test_overview_contains_charts_alerts_activity(client, auth):
    d = client.get(f"{API}/dashboard/overview?hours=24", headers=auth).json()
    assert d["simulated_data"] is True
    for key in ("order_volume", "orders_by_status", "avg_delivery_time", "incident_distribution",
                "restaurant_performance", "cancellations"):
        assert key in d["charts"]
    assert len(d["charts"]["order_volume"]) >= 24
    assert {a["level"] for a in d["alerts"]} <= {"INFO", "WARNING", "CRITICAL"}
    assert any(a["rule"] == "ORDERS_DELAYED" for a in d["alerts"])
    assert d["activity"]
    assert client.get(f"{API}/dashboard/overview?hours=0", headers=auth).status_code == 422


# ------------------------------------------------------------------ reports
def test_reports_all_kinds_and_exports(client, auth):
    kinds = [k["kind"] for k in client.get(f"{API}/reports", headers=auth).json()["items"]]
    assert set(kinds) == {"general", "delays", "restaurants", "couriers", "incidents"}
    for k in kinds:
        r = client.get(f"{API}/reports/{k}?hours=24", headers=auth).json()
        assert r["summary"] and r["indicators"] and r["recommendations"] and r["period"]["hours"] == 24
    assert client.get(f"{API}/reports/operational", headers=auth).json()["kind"] == "general"
    csv = client.get(f"{API}/reports/delays/export?format=csv", headers=auth)
    assert csv.headers["content-type"].startswith("text/csv") and b"Pedido" in csv.content
    pdf = client.get(f"{API}/reports/general/export?format=pdf", headers=auth)
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"{API}/reports/nope", headers=auth).status_code == 404


# ------------------------------------------------------------------ simulation
def test_advance_changes_dashboard(client, auth):
    before = client.get(f"{API}/dashboard/metrics", headers=auth).json()
    r = client.post(f"{API}/simulation/advance", json={"minutes": 45}, headers=auth)
    assert r.status_code == 200 and r.json()["status_changes"] > 0
    after = client.get(f"{API}/dashboard/metrics", headers=auth).json()
    assert after["delivered"] > before["delivered"]
    assert client.post(f"{API}/simulation/advance", json={"minutes": 0}, headers=auth).status_code == 422
    assert client.get(f"{API}/simulation/status", headers=auth).json()["offset_minutes"] == 45


def test_scenario_actions(client, auth):
    m0 = client.get(f"{API}/dashboard/metrics", headers=auth).json()
    client.post(f"{API}/simulation/actions", json={"action": "demand_spike", "count": 12}, headers=auth)
    client.post(f"{API}/simulation/actions", json={"action": "reduce_couriers", "count": 5}, headers=auth)
    m1 = client.get(f"{API}/dashboard/metrics", headers=auth).json()
    assert m1["total_orders"] >= m0["total_orders"] + 12 and m1["available_couriers"] == m0["available_couriers"] - 5
    r = client.post(f"{API}/simulation/actions", json={"action": "generate_incidents"}, headers=auth).json()
    assert r["created_incidents"] is not None
    r = client.post(f"{API}/simulation/actions", json={"action": "restaurant_delay", "restaurant": "Sushi Aurora", "factor": 2}, headers=auth)
    assert r.status_code == 200 and r.json()["delay_factor"] == 2
    assert client.post(f"{API}/simulation/actions", json={"action": "restaurant_delay"}, headers=auth).status_code == 400


def test_advance_keeps_couriers_and_orders_consistent(client, auth, db):
    """Regression: an order must never be assigned twice in one pass (couriers stuck as ASSIGNED)."""
    from app.models.enums import ACTIVE_STATUSES
    for _ in range(3):
        assert client.post(f"{API}/simulation/advance", json={"minutes": 20}, headers=auth).status_code == 200
    db.expire_all()
    busy = (CourierStatus.ASSIGNED, CourierStatus.PICKING_UP, CourierStatus.DELIVERING)
    for c in db.scalars(select(Courier)):
        active = db.scalar(select(func.count()).select_from(Order).where(Order.courier_id == c.id, Order.status.in_(ACTIVE_STATUSES)))
        assert (c.status in busy) == (active > 0), f"{c.code}: {c.status.value} with {active} active orders"
        assert active <= 1


def test_reset_restores_demo(client, auth):
    client.post(f"{API}/simulation/actions", json={"action": "cancel_orders", "count": 8}, headers=auth)
    base = client.post(f"{API}/simulation/reset", headers=auth)
    assert base.status_code == 200 and base.json()["orders"] >= 100
    assert client.get(f"{API}/simulation/status", headers=auth).json()["offset_minutes"] == 0


def test_reset_requires_admin(client, db):
    from tests.conftest import login
    assert client.post(f"{API}/simulation/reset", headers=login(client, "operador@opspilot.local")).status_code == 403


def test_seed_dataset_size(db):
    assert db.scalar(select(func.count()).select_from(Restaurant)) >= 15
    assert db.scalar(select(func.count()).select_from(Courier)) >= 30
    assert db.scalar(select(func.count()).select_from(Incident)) >= 20
    assert db.scalar(select(func.count()).select_from(Order)) >= 100
