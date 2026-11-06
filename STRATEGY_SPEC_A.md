
# Strategy A — Intraday Options

## Instrument
Liquid ATM call/put options, primarily NIFTY,
SENSEX, HDFC Bank and Reliance.

## Timeframe
2-minute option-premium candles.

## Indicators
- SMA(High, 20)
- SMA(Low, 20)
- MACD(12, 26, 9)

## Entry window
09:45–14:20 IST.

## Bullish setup
1. MACD confirms bullish crossover.
2. Green candle closes with at least 50% of its
   body above the upper SMA channel.
3. Reject abnormally large candles.
4. Enter on a break above the signal candle high
   within four subsequent candles.

## Bearish setup
The client describes bearish signal detection
and switching to the corresponding put option.
The complete contract-switching implementation
is not included in the current prototype.

## Position management
- Initial stop based on the signal candle and SMA
- Partial exit at 1R
- Breakeven stop on the remaining position
- Final exit at 2R
- No overnight holdings

## Assumptions
- MACD crossover timing is configurable.
- Oversized threshold: 2x preceding 25-candle
  median body size.
- Initial bullish stop: SMA(Low, 20).
- First partial exit: 50%, subject to whole lots.
- Same-candle stop/target ambiguity: stop first.
- Square-off: 15:20 IST.
- No precise trailing algorithm was provided;
  only breakeven protection is implemented.

## Source traceability
Source: Strategy A client video.
Exact video timestamps were not verified and
must be added before claiming full traceability.

## Risks
- Premium decay and poor liquidity
- Slippage on breakout entries
- False MACD crossovers
- Gaps through stop losses
- Parameter overfitting
