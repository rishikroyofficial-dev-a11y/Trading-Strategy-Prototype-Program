
from argparse import Namespace
from types import SimpleNamespace

import pandas as pd

from algodesk import (
    SimulatedBroker,
    fraction_above,
    generate_demo,
    prepare_indicators,
    run_engine,
)


def test_body_threshold():
    candle = SimpleNamespace(open=100, close=110)

    assert fraction_above(candle, 105) == 0.5
    assert fraction_above(candle, 108) == 0.2
    assert fraction_above(candle, 99) == 1.0


def test_gap_through_stop():
    broker = SimulatedBroker(slippage_bps=0)
    candle = SimpleNamespace(open=90, high=103, low=88)

    assert broker.sell_stop(95, candle) == 90


def test_no_indicator_lookahead(tmp_path):
    path = tmp_path / "synthetic.csv"
    generate_demo(path)

    raw = pd.read_csv(path)
    full = prepare_indicators(raw)
    prefix = prepare_indicators(raw.iloc[:120].copy())

    columns = [
        "sma_high", "sma_low",
        "macd", "macd_signal",
        "ema30", "ema50", "ema60", "wma6"
    ]

    pd.testing.assert_frame_equal(
        full[columns].iloc[:120].reset_index(drop=True),
        prefix[columns].reset_index(drop=True)
    )


def test_paper_restart_matches_backtest(tmp_path):
    path = tmp_path / "synthetic.csv"
    generate_demo(path)

    df = prepare_indicators(pd.read_csv(path))

    config = dict(
        strategy="A",
        instrument="SYNTHETIC_TEST",
        output=str(tmp_path / "backtest"),
        mode="backtest",
        capital=100000,
        lot_size=1,
        lots=2,
        tick=0.05,
        slippage=2,
        oversized=2.0,
        macd_window=1,
        cooldown=30,
        max_trades=5,
        max_daily_loss=10000,
        kill=False,
        limit=None,
        reset=False,
    )

    uninterrupted = run_engine(df, Namespace(**config))

    config["mode"] = "paper"
    config["output"] = str(tmp_path / "paper")
    config["limit"] = 300

    run_engine(df, Namespace(**config))

    # Resume from checkpoint, not from the beginning.
    config["limit"] = None
    resumed = run_engine(df, Namespace(**config))

    assert resumed["trades"] == uninterrupted["trades"]
    assert resumed["events"] == uninterrupted["events"]
    assert resumed["equity"] == uninterrupted["equity"]


def test_strategy_b_ema_warmup(tmp_path):
    path = tmp_path / "synthetic.csv"
    generate_demo(path)

    df = prepare_indicators(pd.read_csv(path))

    assert df["ema60"].iloc[:59].isna().all()
    assert pd.notna(df["ema60"].iloc[59])
