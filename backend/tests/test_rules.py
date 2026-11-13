"""Pure unit tests for the business-rule layer (no DB, no HTTP)."""
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.models.enums import OrderStatus, Priority
from app.rules.engine import (
    OrderSnapshot,
    RuleConfig,
    assess_order,
    capacity_alert,
    incident_is_stale_critical,
    is_valid_transition,
    restaurant_prep_alert,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CFG = RuleConfig()


def snap(status=OrderStatus.PREPARING, created_ago=10, due_in=30, prep=20, courier=False, ready_ago=None):
    return OrderSnapshot(
        status=status, created_at=NOW - timedelta(minutes=created_ago), promised_at=NOW + timedelta(minutes=due_in),
        est_prep_minutes=prep, has_courier=courier, ready_at=NOW - timedelta(minutes=ready_ago) if ready_ago is not None else None,
    )


def test_order_past_deadline_is_delayed_with_priority():
    a = assess_order(snap(due_in=-3), NOW, CFG)
    assert a.is_delayed and a.delay_minutes == 3 and a.priority == Priority.LOW and not a.at_risk
    assert assess_order(snap(due_in=-6), NOW, CFG).priority == Priority.MEDIUM
    assert assess_order(snap(due_in=-16), NOW, CFG).priority == Priority.HIGH
    assert assess_order(snap(due_in=-31), NOW, CFG).priority == Priority.CRITICAL


@pytest.mark.parametrize("status", [OrderStatus.DELIVERED, OrderStatus.CANCELLED])
def test_terminal_orders_are_never_delayed(status):
    a = assess_order(snap(status=status, due_in=-100), NOW, CFG)
    assert not a.is_delayed and not a.at_risk


def test_healthy_order_is_not_flagged():
    a = assess_order(snap(created_ago=5, due_in=40, courier=True), NOW, CFG)
    assert not a.is_delayed and not a.at_risk and a.risk_reasons == ()


def test_close_to_deadline_before_delivery_is_at_risk():
    a = assess_order(snap(due_in=8, courier=True), NOW, CFG)
    assert a.at_risk and "8 min" in a.risk_reasons[0]


def test_no_courier_near_deadline_is_at_risk():
    a = assess_order(snap(status=OrderStatus.READY_FOR_PICKUP, due_in=14, ready_ago=1), NOW, CFG)
    assert a.at_risk and any("Sem entregador" in r for r in a.risk_reasons)


def test_no_courier_but_plenty_of_time_is_fine():
    assert not assess_order(snap(status=OrderStatus.CONFIRMED, due_in=30), NOW, CFG).at_risk


def test_waiting_for_courier_too_long_is_at_risk():
    a = assess_order(snap(status=OrderStatus.WAITING_COURIER, due_in=25, ready_ago=9, courier=False), NOW, CFG)
    assert a.at_risk and any("aguardando entregador" in r for r in a.risk_reasons)


def test_preparation_overrun_is_at_risk():
    a = assess_order(snap(status=OrderStatus.PREPARING, created_ago=30, prep=20, due_in=20, courier=True), NOW, CFG)
    assert a.at_risk and any("Preparo excedeu" in r for r in a.risk_reasons)


def test_in_delivery_only_risky_when_almost_due():
    assert not assess_order(snap(status=OrderStatus.IN_DELIVERY, due_in=8, courier=True), NOW, CFG).at_risk
    assert assess_order(snap(status=OrderStatus.IN_DELIVERY, due_in=2, courier=True), NOW, CFG).at_risk


def test_rules_are_configurable():
    strict = RuleConfig.from_overrides({"risk_remaining_minutes": 20})
    assert assess_order(snap(due_in=18, courier=True), NOW, strict).at_risk
    assert not assess_order(snap(due_in=18, courier=True), NOW, CFG).at_risk
    with pytest.raises(ValueError):
        RuleConfig.from_overrides({"nope": 1})


def test_rules_overrides_from_env(monkeypatch):
    monkeypatch.setenv("RULES_OVERRIDES", '{"risk_remaining_minutes": 12}')
    assert Settings().rules_overrides == {"risk_remaining_minutes": 12}


@pytest.mark.parametrize("cur,tgt,ok", [
    (OrderStatus.RECEIVED, OrderStatus.CONFIRMED, True),
    (OrderStatus.RECEIVED, OrderStatus.DELIVERED, False),
    (OrderStatus.PREPARING, OrderStatus.IN_DELIVERY, False),
    (OrderStatus.IN_DELIVERY, OrderStatus.DELIVERED, True),
    (OrderStatus.DELIVERED, OrderStatus.CANCELLED, False),
    (OrderStatus.CANCELLED, OrderStatus.RECEIVED, False),
])
def test_status_transitions(cur, tgt, ok):
    assert is_valid_transition(cur, tgt) is ok


def test_restaurant_prep_alert_threshold():
    assert restaurant_prep_alert(40, 30, 5, CFG) == 33.3
    assert restaurant_prep_alert(38, 30, 5, CFG) is None  # 26.7% < 30%
    assert restaurant_prep_alert(60, 30, 2, CFG) is None  # too few orders
    assert restaurant_prep_alert(None, 30, 5, CFG) is None


def test_capacity_alert():
    assert capacity_alert(0, 0) == "NO_COURIERS"
    assert capacity_alert(2, 5) == "INSUFFICIENT_COURIERS"
    assert capacity_alert(5, 2) is None


def test_stale_critical_incident():
    assert incident_is_stale_critical(Priority.CRITICAL, 31, CFG)
    assert not incident_is_stale_critical(Priority.CRITICAL, 10, CFG)
    assert not incident_is_stale_critical(Priority.HIGH, 300, CFG)
