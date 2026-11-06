
# Strategy B — EMA Alignment

## Instrument
Individual stocks selected by the client.

## Indicators
Client discussed the 12-EMA indicator with periods:
3, 5, 8, 10, 12, 15, 30, 35, 40, 45, 50, 60.

The longer EMA group is:
30, 35, 40, 45, 50, 60.

The client also uses a WMA-based indicator
with input setting 6.

## Candidate bullish alignment
EMA30 > EMA35 > EMA40 > EMA45 > EMA50 > EMA60

## Entry confirmation
EMA alignment must agree with the confirmation
indicator crossover.

## Exit
Client requires indicator reversal relative
to a black EMA reference line.

## Important ambiguities
- Exact identity of black and blue lines
- Whether violet equals standard WMA(6)
- Exact crossover direction and timing
- Confirmed short/sell rules
- Exact stop and trailing-stop formula

## Prototype assumptions
The current implementation treats:
- Blue = EMA(50)
- Black = EMA(60)
- Violet = WMA(6)
- Bullish trigger = WMA crossing above EMA(50)

These are unverified assumptions.

## Risks
- Incorrect signal mapping due to ambiguity
- Whipsaws in sideways markets
- EMA lag
- False crossover signals
- Overfitting indicator parameters

The current implementation should not be treated
as an exact reproduction of the client's strategy.
