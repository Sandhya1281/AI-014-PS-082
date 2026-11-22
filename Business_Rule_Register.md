# Business Rule Register

Status key: Implemented = code written; Tested = automated test passes in this repository.
"Tested" means our own tests. The official and hidden sessions have not been run.

| ID | Rule (summary) | Code | Owner | Tests | Notes |
|---|---|---|---|---|---|
| BR-01 | 1 REC per MWh, round down, apply within 6 months, audit flag if accredited < 1 year | registry.issue_rec | M1 | test_registry BR01 x6, EC3 | A-01, A-16 |
| BR-02 | 1 credit per tonne, 5% buffer, release after 3 consecutive clean issuances | carbon.issue_carbon, release_buffers | M1 | test_carbon BR02 x5 | A-02, A-03 |
| BR-03 | Solar/non-solar separate markets and targets; solar surplus may cover non-solar only after solar target met; non-solar never covers solar | compliance.retire; auction.close_session (separate markets) | M1 / M2 | test_compliance BR03 x3, EC4 | retirement uses `against=` |
| BR-04 | Expiry 36 months after end of issuance month; expired not tradable or retirable; expiry day valid; FIFO by vintage | registry.expiry_date, is_expired, take_fifo, transfer_fifo, expire_lots | M1 | test_registry BR04 x5, EC8 | A-01, D-20 |
| BR-05 | Uniform-price double auction, sort, price where cumulative buy meets sell, marginal pro-rata rounded down, residual unfilled | auction.find_clearing, allocate_side, balance | M2 | test_auction BR05 x5, EC1, EC2 | A-09, A-10 |
| BR-06 | Floor 1000, forbearance 3000, out-of-band rejected at entry, forbearance clearing | orders.place_order, auction.clear_at_forbearance | M2 | test_orders BR06 x4, test_auction BR06 | A-11 |
| BR-07 | Exchange fee 0.5% both sides, Rs 2 per certificate seller, GST 18% on fees, T+1, fees before proceeds | accounts.calculate_fees, settle_due | M2 | test_accounts BR07 x7, EC7 | A-13, A-14 |
| BR-08 | 100% margin at entry, released on rejection or non-fill, converted on fill | accounts.block_margin, release_margin, convert_margin | M2 | test_orders BR08 x4, EC7 | A-15 |
| BR-09 | Target = consumption x RPO (solar 10%, non-solar 15%), retirements up to 31 March count, penalty = shortfall x 3000, 90% carry-forward once | compliance.targets, retire, close_year | M1 | test_compliance BR09 x6, EC5 | A-05, A-06, A-07 |
| BR-10 | Reversal: untraded first, buffer next, remainder in rupees at last clearing price, no clawback of retired | carbon.reverse_issuance | M1 | test_carbon BR10 x5, EC6 | A-08 |
| BR-11 | Sell <= unencumbered same-category holdings, partial sells, no modify, cancel before close only | orders.place_order, cancel_order, modify_order | M2 | test_orders BR11 x7, test_registry BR11 x1 | A-17 |
