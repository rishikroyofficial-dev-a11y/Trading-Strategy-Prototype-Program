
# AlgoDesk Algo Developer Assessment

## Overview

Python-based prototype for implementing and evaluating
two client trading strategies.

### Strategy A
Intraday ATM options strategy based on:
- 2-minute candles
- SMA(High, 20) and SMA(Low, 20)
- MACD(12, 26, 9)
- Candle confirmation and four-candle breakout
- Stop loss, partial 1R exit, and final 2R target

### Strategy B
Multi-EMA alignment strategy with an additional
WMA-based confirmation indicator.

Some Strategy B indicator identities and crossover
rules remain assumptions pending verification.

## Architecture

- `algodesk.py`: Shared strategy and execution engine
- `test_algodesk.py`: Initial unit tests
- `data/`: Synthetic testing data
- `outputs/`: Signal lists and generated reports

The same `run_engine()` function is used for
backtesting and paper replay.

## Installation

```bash
pip install -r requirements.txt
```

## Run demonstration

```bash
python algodesk.py --demo
```

## Run tests

```bash
python -m pytest -v
```

## Paper replay

```bash
python algodesk.py --data data/synthetic_demo.csv --strategy A --instrument SYNTHETIC_TEST_ONLY --mode paper --output outputs/paper_A --limit 400 --reset
```

Resume from the checkpoint using a larger limit
without the `--reset` flag.

## Outputs

- signals.csv
- trades.csv
- trade_legs.csv
- equity.csv
- report.html
- report.json
- events.jsonl

## Limitations

The organizers' historical market data was not
available during implementation.

The included demonstration uses synthetic OHLC data.
Its signals and performance statistics are NOT
historical market results.

Brokerage and statutory costs are illustrative.
The strategy implementations contain documented
assumptions and do not reproduce every client rule.

No live trading or real broker integration is included.
