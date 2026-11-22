# MEMBER 2 - uniform-price double auction (BR-05, BR-06).
#
# Solar and non-solar are separate markets (BR-03), so close_session() clears each one
# on its own. clear_market() only does the maths: it takes lists of orders and gives back
# the clearing price and how many units each order got. close_session() then updates the
# registry and the accounts.

from ledger import accounts, config, registry
from ledger.state import ZERO


def sort_buys(buys):
    # highest price first; same price -> the order entered first
    return sorted(buys, key=lambda o: (-o["price"], o["seq"]))


def sort_sells(sells):
    # lowest price first; same price -> the order entered first
    return sorted(sells, key=lambda o: (o["price"], o["seq"]))


def find_clearing(buys, sells):
    """Try every order price p.
         demand(p) = total buy quantity with limit price >= p
         supply(p) = total sell quantity with limit price <= p
         volume(p) = the smaller of the two
    The clearing price is the LOWEST p that gives the biggest volume.
    (Using '>' below means the first = lowest price wins a tie.)"""
    prices = []
    for o in buys + sells:
        if o["price"] not in prices:
            prices.append(o["price"])
    prices.sort()

    best_price = None
    best_volume = 0
    for p in prices:
        demand = 0
        for b in buys:
            if b["price"] >= p:
                demand += b["qty"]
        supply = 0
        for s in sells:
            if s["price"] <= p:
                supply += s["qty"]
        volume = min(demand, supply)
        if volume > best_volume:
            best_price = p
            best_volume = volume
    return best_price, best_volume


def allocate_side(sorted_orders, volume):
    """Give out 'volume' units to a sorted list of orders, one price level at a time.
    A level that fits completely is filled completely.
    The first level that does NOT fit is shared pro-rata by quantity, rounded DOWN (BR-05).
    Units left over after rounding stay unfilled.
    Returns a dict {order_id: filled_quantity}."""
    fills = {}
    for o in sorted_orders:
        fills[o["id"]] = 0

    remaining = volume
    i = 0
    while i < len(sorted_orders) and remaining > 0:
        # find all orders with the same price as order i (one price level)
        level_price = sorted_orders[i]["price"]
        j = i
        while j < len(sorted_orders) and sorted_orders[j]["price"] == level_price:
            j += 1
        level = sorted_orders[i:j]

        level_qty = 0
        for o in level:
            level_qty += o["qty"]

        if level_qty <= remaining:
            for o in level:
                fills[o["id"]] = o["qty"]
            remaining -= level_qty
        else:
            for o in level:
                fills[o["id"]] = remaining * o["qty"] // level_qty
            remaining = 0
        i = j
    return fills


def trim(sorted_orders, fills, excess):
    """Take 'excess' units away from the orders at the end of the list (lowest priority)."""
    for o in reversed(sorted_orders):
        cut = min(fills[o["id"]], excess)
        fills[o["id"]] -= cut
        excess -= cut
        if excess == 0:
            break


def balance(buys, buy_fills, sells, sell_fills):
    """Rounding down can make the total bought different from the total sold.
    We cut the bigger side so both totals are equal."""
    bought = sum(buy_fills.values())
    sold = sum(sell_fills.values())
    if bought > sold:
        trim(buys, buy_fills, bought - sold)
    elif sold > bought:
        trim(sells, sell_fills, sold - bought)


def clear_at_forbearance(buys, sells):
    """BR-06: the clearing price would be above the forbearance price.
    Price = forbearance price. Every sell at or below it clears. Buys are pro-rated."""
    price = config.FORBEARANCE_PRICE

    sells_ok = []
    for s in sells:
        if s["price"] <= price:
            sells_ok.append(s)
    sells_ok = sort_sells(sells_ok)

    buys_ok = []
    for b in buys:
        if b["price"] >= price:
            buys_ok.append(b)
    buys_ok = sort_buys(buys_ok)

    supply = 0
    for s in sells_ok:
        supply += s["qty"]
    demand = 0
    for b in buys_ok:
        demand += b["qty"]

    volume = min(supply, demand)
    if volume == 0:
        return None, {}

    sell_fills = allocate_side(sells_ok, volume)
    buy_fills = {}
    for b in buys_ok:
        buy_fills[b["id"]] = volume * b["qty"] // demand
    balance(buys_ok, buy_fills, sells_ok, sell_fills)

    fills = {}
    fills.update(buy_fills)
    fills.update(sell_fills)
    return price, fills


def clear_market(buys, sells):
    """Returns (clearing price, {order_id: filled quantity}).
    Returns (None, {}) when nothing can trade."""
    buys = sort_buys(buys)
    sells = sort_sells(sells)
    price, volume = find_clearing(buys, sells)
    if price is None:
        return None, {}
    if price > config.FORBEARANCE_PRICE:
        return clear_at_forbearance(buys, sells)

    buy_fills = allocate_side(buys, volume)
    sell_fills = allocate_side(sells, volume)
    balance(buys, buy_fills, sells, sell_fills)

    fills = {}
    fills.update(buy_fills)
    fills.update(sell_fills)
    return price, fills


def pair_up(buy_list, sell_list):
    """Match filled buy orders with filled sell orders (in priority order).
    Each item of buy_list / sell_list is (order, filled_qty).
    Returns a list of (sell_order, buy_order, qty) - who delivers how much to whom."""
    buys = []
    for order, qty in buy_list:
        buys.append([order, qty])
    sells = []
    for order, qty in sell_list:
        sells.append([order, qty])

    pairs = []
    b = 0
    s = 0
    while b < len(buys) and s < len(sells):
        qty = min(buys[b][1], sells[s][1])
        pairs.append((sells[s][0], buys[b][0], qty))
        buys[b][1] -= qty
        sells[s][1] -= qty
        if buys[b][1] == 0:
            b += 1
        if sells[s][1] == 0:
            s += 1
    return pairs


def apply_market(state, session, category, buys, sells, price, fills):
    """Use the auction result: move certificates, settle margin, record fills."""
    trade_date = session["date"]

    if price is not None:
        buy_list = []
        for o in sort_buys(buys):
            if fills.get(o["id"], 0) > 0:
                buy_list.append((o, fills[o["id"]]))
        sell_list = []
        for o in sort_sells(sells):
            if fills.get(o["id"], 0) > 0:
                sell_list.append((o, fills[o["id"]]))

        for seller, buyer, qty in pair_up(buy_list, sell_list):
            registry.transfer_fifo(state, seller["member"], buyer["member"], category, qty, trade_date)

        state["last_clearing_price"][category] = price
        state["last_clearing_price"]["any"] = price

    for order in buys + sells:
        filled = fills.get(order["id"], 0)
        order["filled"] = filled
        if filled == order["qty"]:
            order["status"] = "filled"
        elif filled > 0:
            order["status"] = "partial"
        else:
            order["status"] = "unfilled"

        # BR-08: margin is converted on fill, released if not filled
        if order["side"] == "buy":
            value = ZERO
            if price is not None:
                value = price * filled
            accounts.convert_margin(state, order["member"], order["margin"], value)

        if filled > 0:
            accounts.add_settlement(state, session["id"], order, filled, price, trade_date)


def close_session(state, session_id):
    """Close the session (no more cancels) and clear the solar and non-solar markets."""
    if session_id not in state["sessions"]:
        raise ValueError(f"Unknown session {session_id}")
    session = state["sessions"][session_id]
    if session["status"] == "closed":
        raise ValueError(f"Session {session_id} already closed")
    session["status"] = "closed"

    for category in config.REC_CATEGORIES:
        buys = []
        sells = []
        for o in state["orders"].values():
            if o["session"] == session_id and o["category"] == category and o["status"] == "open":
                if o["side"] == "buy":
                    buys.append(o)
                else:
                    sells.append(o)

        price, fills = clear_market(buys, sells)
        apply_market(state, session, category, buys, sells, price, fills)

        volume = 0
        for o in buys:
            volume += o["filled"]
        session["results"][category] = {"price": price, "volume": volume}
    return session
