# MEMBER 2 - member accounts: funds, margin, fees, GST, T+1 settlement (BR-07, BR-08).
#
# An account looks like:
#   {"cash", "blocked", "fee_due", "reversal_owed", "unpriced_units"}
# Available money = cash - blocked.
# Cash never goes below zero. If a fee cannot be paid in full, the unpaid part is
# kept in "fee_due" and collected the next time money is available.

from datetime import timedelta
from decimal import Decimal

from ledger import config
from ledger.state import ZERO, round_money, to_decimal


def get_account(state, member):
    if member not in state["accounts"]:
        state["accounts"][member] = {"cash": ZERO, "blocked": ZERO, "fee_due": ZERO,
                                     "reversal_owed": ZERO, "unpriced_units": 0}
    return state["accounts"][member]


def available(acc):
    return acc["cash"] - acc["blocked"]


def collect_dues(acc):
    """Pay unpaid fees from available cash."""
    money_free = available(acc)
    if money_free < 0:
        money_free = ZERO
    pay = min(money_free, acc["fee_due"])
    acc["cash"] -= pay
    acc["fee_due"] -= pay


def fund(state, member, amount):
    amount = to_decimal(amount, "amount")
    if amount <= 0:
        raise ValueError("Funding amount must be positive")
    acc = get_account(state, member)
    acc["cash"] += amount
    collect_dues(acc)
    return acc


# ---------- margin (BR-08) ----------

def block_margin(state, member, amount):
    """A buy order blocks 100% of its value when it is entered."""
    acc = get_account(state, member)
    if amount > available(acc):
        raise ValueError(f"BR-08: margin {amount} exceeds available funds {available(acc)}")
    acc["blocked"] += amount


def release_margin(state, member, amount):
    acc = get_account(state, member)
    acc["blocked"] -= amount


def convert_margin(state, member, margin, value):
    """After the auction: unblock the whole margin, move the trade value
    (clearing price x filled quantity) to escrow. The rest of the margin stays as free cash."""
    acc = get_account(state, member)
    acc["blocked"] -= margin
    acc["cash"] -= value
    state["escrow"] += value


# ---------- fees (BR-07) ----------

def calculate_fees(side, qty, trade_value):
    """Exchange fee 0.5% for buyer and seller.
    Registry fee Rs 2 per certificate for the seller only.
    GST 18% on the fees. Each amount is rounded to paise."""
    exchange = round_money(trade_value * config.EXCHANGE_FEE_RATE)
    if side == "sell":
        registry_fee = round_money(Decimal(qty) * config.REGISTRY_FEE_PER_CERT)
    else:
        registry_fee = ZERO
    gst = round_money((exchange + registry_fee) * config.GST_RATE)
    total = exchange + registry_fee + gst
    return {"exchange": exchange, "registry": registry_fee, "gst": gst, "total": total}


def add_settlement(state, session_id, order, qty, price, trade_date):
    """Remember a fill. Money for it is settled one day later (T+1)."""
    rec = {"id": len(state["settlements"]) + 1, "session": session_id, "order": order["id"],
           "member": order["member"], "side": order["side"], "category": order["category"],
           "qty": qty, "price": price, "value": price * qty,
           "settle_date": trade_date + timedelta(days=1), "settled": False,
           "fees": None, "fee_paid": ZERO}
    state["settlements"].append(rec)
    return rec


def settle_due(state, on_date):
    """Settle every fill that is due on or before on_date.
    For each fill: first take the fees, then pay the seller (BR-07)."""
    done = []
    for rec in state["settlements"]:
        if rec["settled"] or rec["settle_date"] > on_date:
            continue

        fees = calculate_fees(rec["side"], rec["qty"], rec["value"])
        acc = get_account(state, rec["member"])

        # 1. take the fees (only as much as the account can pay)
        money_free = available(acc)
        if money_free < 0:
            money_free = ZERO
        pay = min(money_free, fees["total"])
        acc["cash"] -= pay
        acc["fee_due"] += fees["total"] - pay
        state["revenue"]["exchange"] += fees["exchange"]
        state["revenue"]["registry"] += fees["registry"]
        state["revenue"]["gst"] += fees["gst"]

        # 2. then pay the seller from escrow
        if rec["side"] == "sell":
            acc["cash"] += rec["value"]
            state["escrow"] -= rec["value"]
            collect_dues(acc)

        rec["settled"] = True
        rec["fees"] = fees
        rec["fee_paid"] = pay
        done.append(rec)
    return done


def record_reversal_debt(state, member, amount, deficit_units):
    """Used after a reversal (BR-10). amount is None when there was no clearing price."""
    acc = get_account(state, member)
    if amount is None:
        acc["unpriced_units"] += deficit_units
    else:
        acc["reversal_owed"] += amount
