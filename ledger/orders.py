# MEMBER 2 - sessions and orders: validation, margin at entry, cancel (BR-06, BR-08, BR-11).
#
# An order looks like:
#   {"id", "session", "member", "side" (buy/sell), "category", "qty", "price", "seq",
#    "status" (open/rejected/cancelled/filled/partial/unfilled), "margin", "filled", "reason"}

from ledger import accounts, config, registry
from ledger.state import ZERO, to_decimal


def open_session(state, session_id, trade_date):
    if session_id in state["sessions"]:
        raise ValueError(f"Session {session_id} already exists")
    session = {"id": session_id, "date": trade_date, "status": "open", "results": {}}
    state["sessions"][session_id] = session
    return session


def reject_order(state, order, reason):
    order["status"] = "rejected"
    order["reason"] = reason
    state["orders"][order["id"]] = order
    return order


def place_order(state, order_id, session_id, member, side, category, qty, price):
    """Check the order and store it.
    Broken input (unknown session, bad number...) raises ValueError.
    A rule violation gives back the order with status "rejected" and a reason."""
    if session_id not in state["sessions"]:
        raise ValueError(f"Unknown session {session_id}")
    session = state["sessions"][session_id]
    if session["status"] != "open":
        raise ValueError(f"Session {session_id} is closed")
    if order_id in state["orders"]:
        raise ValueError(f"Order {order_id} already exists")

    side = side.lower()
    category = category.lower()
    if side != "buy" and side != "sell":
        raise ValueError(f"Invalid side '{side}'")
    if category not in config.REC_CATEGORIES:
        raise ValueError(f"Invalid category '{category}' (use solar or nonsolar)")
    qty = int(qty)
    if qty <= 0:
        raise ValueError("Order quantity must be positive")
    price = to_decimal(price, "price")

    state["order_seq"] += 1
    order = {"id": order_id, "session": session_id, "member": member, "side": side,
             "category": category, "qty": qty, "price": price, "seq": state["order_seq"],
             "status": "open", "margin": ZERO, "filled": 0, "reason": ""}

    # BR-06: price must be inside the band
    if price < config.FLOOR_PRICE or price > config.FORBEARANCE_PRICE:
        return reject_order(state, order, f"BR-06: price {price} outside band "
                                          f"{config.FLOOR_PRICE}-{config.FORBEARANCE_PRICE}")

    if side == "sell":
        # BR-11: cannot sell more than the free holdings of the same category
        free = registry.free_holdings(state, member, category, session["date"])
        if qty > free:
            return reject_order(state, order, f"BR-11: sell qty {qty} exceeds "
                                              f"unencumbered {category} holdings {free}")
    else:
        # BR-08: block 100% of the order value
        margin = price * qty
        try:
            accounts.block_margin(state, member, margin)
        except ValueError as err:
            return reject_order(state, order, str(err))
        order["margin"] = margin

    state["orders"][order_id] = order
    return order


def cancel_order(state, order_id):
    """BR-11: an order can be cancelled only while its session is open."""
    if order_id not in state["orders"]:
        raise ValueError(f"Unknown order {order_id}")
    order = state["orders"][order_id]
    session = state["sessions"][order["session"]]
    if session["status"] != "open":
        raise ValueError("BR-11: cancellation after session close is rejected")
    if order["status"] != "open":
        raise ValueError(f"Order {order_id} is {order['status']}, cannot cancel")

    order["status"] = "cancelled"
    if order["side"] == "buy":
        accounts.release_margin(state, order["member"], order["margin"])
        order["margin"] = ZERO
    return order


def modify_order(state, order_id, **changes):
    """BR-11: orders cannot be modified. Cancel it and enter a new one."""
    raise ValueError("BR-11: orders cannot be modified; cancel and re-enter")
