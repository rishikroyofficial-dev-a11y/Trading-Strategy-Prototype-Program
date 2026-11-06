
# Indian Market Edge Cases

## 1. Repainting
Indicators are calculated from current and
previous completed candles. Signals are recorded
after candle-close confirmation.

## 2. Lookahead
No future candles are used in indicator calculations.
An initial prefix-consistency unit test is included.

## 3. Market hours
Entry window: 09:45–14:20 IST.
Square-off threshold: 15:20 IST.

## 4. Expiry
Expiry/rollover contract mapping is not yet implemented.

## 5. Strike selection
ATM strike mapping requires an option instrument master.

## 6. Lot size
Lot size is supplied through a command-line parameter.
It must be verified for each real option contract.

## 7. Gaps
Stops execute at a less favorable opening price
when a candle opens beyond the stop.
Entry stops account for upward price gaps.

## 8. Freeze quantity
Exchange freeze-quantity splitting is not implemented.

## 9. Reconnect and restart
Paper mode persists state after each candle.
Previously processed timestamps are skipped
when replay resumes.

## 10. Order rejection
Insufficient simulated cash results in rejection.
Broker-specific rejection handling is incomplete.

## 11. Clock drift
Historical timestamps are used for replay.
Live exchange clock synchronization is not implemented.

## Additional limitations
- Synthetic candles are used for demonstration.
- Market costs are illustrative.
- Same-bar execution uses a conservative stop-first
  assumption but is not tick-accurate.
- Full contract lifecycle handling is incomplete.
