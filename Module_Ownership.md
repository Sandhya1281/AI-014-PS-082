# Module Ownership

| Module | File | Member | Responsibilities | Depends on | Tests |
|---|---|---|---|---|---|
| Registry | ledger/registry.py | 1 | Register generators and entities, REC issuance (BR-01), lots, expiry (BR-04), holdings, FIFO transfer | config, state | test_registry.py |
| Carbon | ledger/carbon.py | 1 | Carbon issuance, 5% buffer pool, buffer release (BR-02), reversal (BR-10) | registry, accounts (debt record only) | test_carbon.py |
| Compliance | ledger/compliance.py | 1 | Retirement, fungibility (BR-03), RPO targets, penalty, carry-forward (BR-09) | registry | test_compliance.py |
| Orders | ledger/orders.py | 2 | Sessions, order validation, band check (BR-06), margin at entry (BR-08), cancel and no-modify (BR-11) | registry (free holdings), accounts | test_orders.py |
| Auction | ledger/auction.py | 2 | Sorting, uniform-price clearing, pro-rata, forbearance (BR-05, BR-06), applying results | registry (transfer), accounts | test_auction.py |
| Accounts | ledger/accounts.py | 2 | Member funds, margin block/release/convert (BR-08), fees and GST, T+1 settlement (BR-07) | config, state | test_accounts.py |
| Config, State | ledger/config.py, state.py | Both | Constants, state dictionary, date helpers | none | used everywhere |
| Parser, Main, Reports | parser.py, main.py, reports.py | Both | Command dispatch (M1 handlers / M2 handlers in separate sections), report printing | all | test_integration.py |
| Edge cases | tests/test_edge_cases.py | Both | The eight mandatory edge cases | all | itself |

Size: Member 1 owns about 390 lines of logic, Member 2 about 380 lines.

## Interfaces between the two members

Member 2 calls Member 1:
- `registry.free_holdings(state, owner, category, on_date)` - order validation (BR-11)
- `registry.transfer_fifo(state, seller, buyer, category, qty, trade_date)` - applying auction fills

Member 1 calls Member 2:
- `accounts.record_reversal_debt(state, member, amount, deficit_units)` - after a reversal (BR-10)

Shared data contract (state dict): lot = `{id, owner, category, vintage, qty}`; order status `open`
means the sell quantity is encumbered. `state["last_clearing_price"]` is written by Member 2
(auction) and read by Member 1 (reversal).
