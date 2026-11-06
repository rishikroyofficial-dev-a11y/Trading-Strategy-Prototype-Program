
import argparse
import json
import math
import os
import random
from pathlib import Path
from datetime import time

import pandas as pd


# All rates are illustrative, not verified exchange rates.
# Replace using the broker's actual fee schedule.
COSTS = {
    "brokerage_per_order": 20.0,
    "stt_sell": 0.001,
    "exchange": 0.00035,
    "sebi": 0.000001,
    "gst": 0.18,
    "stamp_buy": 0.00003,
}


def transaction_cost(side, value):
    brokerage = COSTS["brokerage_per_order"]
    exchange = value * COSTS["exchange"]
    sebi = value * COSTS["sebi"]
    gst = COSTS["gst"] * (brokerage + exchange + sebi)
    stt = value * COSTS["stt_sell"] if side == "SELL" else 0
    stamp = value * COSTS["stamp_buy"] if side == "BUY" else 0
    return brokerage + exchange + sebi + gst + stt + stamp


class BrokerAdapter:
    """Execution interface independent of strategy code."""

    def buy_stop(self, trigger, candle):
        raise NotImplementedError

    def sell_stop(self, stop, candle):
        raise NotImplementedError

    def sell_limit(self, target, candle):
        raise NotImplementedError

    def sell_market(self, candle):
        raise NotImplementedError


class SimulatedBroker(BrokerAdapter):
    def __init__(self, slippage_bps=2):
        self.slippage = slippage_bps / 10000

    def buy_stop(self, trigger, candle):
        if candle.high < trigger:
            return None
        return max(float(candle.open), trigger) * (1 + self.slippage)

    def sell_stop(self, stop, candle):
        if candle.low > stop:
            return None
        return min(float(candle.open), stop) * (1 - self.slippage)

    def sell_limit(self, target, candle):
        if candle.high < target:
            return None
        return target * (1 - self.slippage)

    def sell_market(self, candle):
        return float(candle.open) * (1 - self.slippage)


def prepare_indicators(df):
    """Only historical/current closed candles are used."""
    df = df.copy()

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="raise")

    df["datetime"] = pd.to_datetime(df["datetime"])

    if df["datetime"].dt.tz is not None:
        df["datetime"] = (
            df["datetime"].dt.tz_convert("Asia/Kolkata")
            .dt.tz_localize(None)
        )

    df = df.sort_values("datetime").reset_index(drop=True)

    if df.datetime.duplicated().any():
        raise ValueError("Duplicate candle timestamps found")

    if (
        (df.high < df[["open", "close", "low"]].max(axis=1)) |
        (df.low > df[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("Invalid OHLC values")

    # Strategy A
    df["sma_high"] = df.high.rolling(20, min_periods=20).mean()
    df["sma_low"] = df.low.rolling(20, min_periods=20).mean()

    ema12 = df.close.ewm(
        span=12, adjust=False, min_periods=12
    ).mean()

    ema26 = df.close.ewm(
        span=26, adjust=False, min_periods=26
    ).mean()

    df["macd"] = ema12 - ema26
    df["macd_signal"] = df.macd.ewm(
        span=9, adjust=False, min_periods=9
    ).mean()

    df["macd_cross_up"] = (
        (df.macd > df.macd_signal) &
        (df.macd.shift(1) <= df.macd_signal.shift(1))
    )

    df["body"] = (df.close - df.open).abs()

    df["prior_body"] = (
        df.body.shift(1)
        .rolling(25, min_periods=25)
        .median()
    )

    # Strategy B: confirmed EMA periods.
    for period in [30, 35, 40, 45, 50, 60]:
        df[f"ema{period}"] = df.close.ewm(
            span=period, adjust=False, min_periods=period
        ).mean()

    # Provisional interpretation of WMA(6).
    df["wma6"] = df.close.rolling(6).apply(
        lambda a: sum(
            (j + 1) * a[j] for j in range(6)
        ) / 21,
        raw=True
    )

    return df


def fraction_above(row, boundary):
    bottom = min(row.open, row.close)
    top = max(row.open, row.close)
    size = top - bottom

    if size <= 0:
        return 0

    return max(
        0, top - max(bottom, boundary)
    ) / size


def strategy_a_signal(df, i, cfg):
    row = df.iloc[i]

    needed = [
        row.sma_high, row.sma_low,
        row.macd, row.macd_signal, row.prior_body
    ]

    if any(pd.isna(x) for x in needed):
        return None

    if row.close <= row.open:
        return None

    if row.prior_body <= 0:
        return None

    if row.body > cfg.oversized * row.prior_body:
        return None

    if fraction_above(row, row.sma_high) < 0.50:
        return None

    # Explicit channel-touch interpretation.
    if not (row.low <= row.sma_high <= row.high):
        return None

    # Cross on the current or recent closed candles.
    recent = df.iloc[
        max(0, i - cfg.macd_window + 1):i + 1
    ]

    if not (
        row.macd > row.macd_signal
        and recent.macd_cross_up.any()
    ):
        return None

    stop = float(row.sma_low)
    trigger = float(row.high) + cfg.tick

    if stop >= trigger:
        return None

    return {
        "trigger": trigger,
        "stop": stop,
        "bar_index": i,
        "date": str(row.datetime.date()),
        "strategy": "A"
    }


def strategy_b_signal(df, i, cfg):
    """Provisional: exact blue/black line identities unconfirmed."""
    if i < 1:
        return None

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    periods = [30, 35, 40, 45, 50, 60]

    if any(pd.isna(row[f"ema{p}"]) for p in periods):
        return None

    if pd.isna(prev.wma6) or pd.isna(prev.ema50):
        return None

    aligned = all(
        row[f"ema{a}"] > row[f"ema{b}"]
        for a, b in zip(periods, periods[1:])
    )

    # ASSUMPTIONS:
    # blue = EMA(50), black = EMA(60), violet = WMA(6)
    crossed = (
        prev.wma6 <= prev.ema50
        and row.wma6 > row.ema50
    )

    if not aligned or not crossed:
        return None

    if row.wma6 <= row.ema60:
        return None

    trigger = float(row.high) + cfg.tick
    stop = min(float(row.low), float(row.ema60)) - cfg.tick

    return {
        "trigger": trigger,
        "stop": stop,
        "bar_index": i,
        "date": str(row.datetime.date()),
        "strategy": "B"
    }


def fresh_state(capital):
    return {
        "cash": float(capital),
        "pending": None,
        "position": None,
        "last_time": None,
        "last_exit": None,
        "killed": False,
        "trades": [],
        "legs": [],
        "events": [],
        "equity": []
    }


def event(state, timestamp, kind, **details):
    state["events"].append({
        "datetime": timestamp,
        "event": kind,
        **details
    })


def save_checkpoint(path, state):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temp, path)


def exit_part(state, qty, price, timestamp, reason):
    p = state["position"]

    qty = min(qty, p["remaining"])
    value = qty * price
    sell_fee = transaction_cost("SELL", value)
    entry_fee_part = p["entry_fee"] * qty / p["quantity"]

    net = (
        (price - p["entry"]) * qty
        - sell_fee - entry_fee_part
    )

    state["cash"] += value - sell_fee

    state["legs"].append({
        "entry_time": p["entry_time"],
        "exit_time": timestamp,
        "instrument": p["instrument"],
        "direction": p["direction"],
        "quantity": qty,
        "entry_price": p["entry"],
        "exit_price": price,
        "net_pnl": net,
        "exit_reason": reason
    })

    p["remaining"] -= qty
    p["exit_value"] += value
    p["net_pnl"] += net
    p["reasons"].append(reason)

    event(
        state, timestamp, "SELL_FILL",
        quantity=qty, price=price, reason=reason
    )

    if p["remaining"] == 0:
        state["trades"].append({
            "datetime": p["entry_time"],
            "direction": p["direction"],
            "instrument_or_strike": p["instrument"],
            "entry_price": p["entry"],
            "stop_loss": p["initial_stop"],
            "target": p["target2"],
            "exit_time": timestamp,
            "exit_price": p["exit_value"] / p["quantity"],
            "exit_reason": "+".join(p["reasons"]),
            "quantity": p["quantity"],
            "net_pnl": p["net_pnl"],
            "r_multiple": (
                p["net_pnl"] /
                (p["risk"] * p["quantity"])
            )
        })

        state["position"] = None
        state["last_exit"] = timestamp


def run_engine(df, cfg):
    output = Path(cfg.output)
    output.mkdir(parents=True, exist_ok=True)

    checkpoint = output / "checkpoint.json"

    if cfg.mode == "paper" and checkpoint.exists() and not cfg.reset:
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
    else:
        state = fresh_state(cfg.capital)

    broker = SimulatedBroker(cfg.slippage)

    quantity = cfg.lot_size * cfg.lots
    first_qty = cfg.lot_size * (cfg.lots // 2)

    if cfg.lots < 2:
        raise ValueError("At least 2 lots needed for partial exits")

    if cfg.kill:
        state["killed"] = True

    for i, row in df.iterrows():
        if cfg.limit and i >= cfg.limit:
            break

        timestamp = row.datetime.isoformat()

        if state["last_time"] and timestamp <= state["last_time"]:
            continue

        now = row.datetime.time()
        date = str(row.datetime.date())

        valid_time = time(9, 45) <= now <= time(14, 20)

        closing_time = now >= time(15, 20)
        entered = False
        exited = False

        # Count entries and realized P&L for this trading day.
        daily_entries = sum(
            e["event"] == "BUY_FILL"
            and e["datetime"][:10] == date
            for e in state["events"]
        )

        daily_pnl = sum(
            leg["net_pnl"]
            for leg in state["legs"]
            if leg["exit_time"][:10] == date
        )

        p = state["position"]

        # 1. Manage existing open position.
        if p is not None:
            if state["killed"] or closing_time or p.get("exit_next"):
                price = broker.sell_market(row)

                if state["killed"]:
                    reason = "KILL_SWITCH"
                elif closing_time:
                    reason = "SQUARE_OFF"
                else:
                    reason = "INDICATOR_EXIT"

                exit_part(
                    state, p["remaining"],
                    price, timestamp, reason
                )
                exited = True

            else:
                # Conservative priority: stop before target.
                stopped = broker.sell_stop(p["stop"], row)

                if stopped is not None:
                    exit_part(
                        state, p["remaining"],
                        stopped, timestamp, "STOP_LOSS"
                    )
                    exited = True

                elif not p["partial"]:
                    target_hit = broker.sell_limit(p["target1"], row)

                    if target_hit is not None:
                        exit_part(
                            state, first_qty, target_hit,
                            timestamp, "PARTIAL_1R"
                        )
                        p["partial"] = True
                        p["stop"] = p["entry"]

                else:
                    target_hit = broker.sell_limit(p["target2"], row)

                    if target_hit is not None:
                        exit_part(
                            state, p["remaining"],
                            target_hit, timestamp, "TARGET_2R"
                        )
                        exited = True

                # Strategy B indicator exit is confirmed at close.
                # The actual exit occurs at the next candle's open.
                p = state["position"]

                if p is not None and cfg.strategy == "B":
                    if (
                        pd.notna(row.wma6)
                        and pd.notna(row.ema50)
                        and pd.notna(row.ema60)
                        and row.wma6 < row.ema60
                        and row.ema50 < row.ema60
                    ):
                        p["exit_next"] = True

        # 2. Execute pending entry order.
        pending = state["pending"]

        if (
            state["position"] is None
            and not exited
            and pending is not None
            and not state["killed"]
        ):
            age = i - pending["bar_index"]

            if (
                age > 4
                or pending["date"] != date
                or not valid_time
            ):
                event(state, timestamp, "SETUP_EXPIRED")
                state["pending"] = None

            elif age >= 1:
                price = broker.buy_stop(pending["trigger"], row)

                if price is not None and price > pending["stop"]:
                    buy_fee = transaction_cost(
                        "BUY", price * quantity
                    )
                    required = price * quantity + buy_fee

                    if state["cash"] < required:
                        event(state, timestamp, "ORDER_REJECTED",
                              reason="INSUFFICIENT_CASH")
                        state["pending"] = None
                    else:
                        risk = price - pending["stop"]

                        state["cash"] -= required

                        state["position"] = {
                            "entry_time": timestamp,
                            "instrument": cfg.instrument,
                            "direction": (
                                "BUY_OPTION" if cfg.strategy == "A"
                                else "BUY_STOCK"
                            ),
                            "entry": price,
                            "initial_stop": pending["stop"],
                            "stop": pending["stop"],
                            "risk": risk,
                            "target1": price + risk,
                            "target2": price + 2 * risk,
                            "quantity": quantity,
                            "remaining": quantity,
                            "entry_fee": buy_fee,
                            "partial": False,
                            "exit_next": False,
                            "exit_value": 0.0,
                            "net_pnl": 0.0,
                            "reasons": []
                        }

                        state["pending"] = None
                        entered = True
                        daily_entries += 1

                        event(
                            state, timestamp, "BUY_FILL",
                            price=price, quantity=quantity
                        )

                        # Conservative entry-candle stop handling.
                        p = state["position"]
                        stopped = broker.sell_stop(p["stop"], row)

                        if stopped is not None:
                            exit_part(
                                state, p["remaining"], stopped,
                                timestamp, "ENTRY_BAR_STOP"
                            )
                            exited = True

        # 3. New signal only after candle closes.
        cooldown_ok = (
            state["last_exit"] is None
            or (
                row.datetime -
                pd.Timestamp(state["last_exit"])
            ).total_seconds() >= cfg.cooldown * 60
        )

        if (
            valid_time
            and not entered
            and not exited
            and state["position"] is None
            and state["pending"] is None
            and not state["killed"]
            and daily_entries < cfg.max_trades
            and daily_pnl > -cfg.max_daily_loss
            and cooldown_ok
        ):
            if cfg.strategy == "A":
                setup = strategy_a_signal(df, i, cfg)
            else:
                setup = strategy_b_signal(df, i, cfg)

            if setup is not None:
                state["pending"] = setup
                event(
                    state, timestamp, "SIGNAL",
                    trigger=setup["trigger"],
                    stop=setup["stop"]
                )

        # 4. Mark-to-market equity.
        p = state["position"]

        market_value = (
            p["remaining"] * float(row.close)
            if p is not None else 0.0
        )

        state["equity"].append({
            "datetime": timestamp,
            "equity": state["cash"] + market_value
        })

        state["last_time"] = timestamp

        # Durable state after each completed candle.
        if cfg.mode == "paper":
            save_checkpoint(checkpoint, state)

    return state


def export_results(state, cfg):
    output = Path(cfg.output)
    output.mkdir(parents=True, exist_ok=True)

    signals = [
        "datetime", "direction", "instrument_or_strike",
        "entry_price", "stop_loss", "target",
        "exit_time", "exit_price", "exit_reason"
    ]

    pd.DataFrame(
        state["trades"], columns=signals
    ).to_csv(output / "signals.csv", index=False)

    pd.DataFrame(state["trades"]).to_csv(
        output / "trades.csv", index=False
    )

    pd.DataFrame(state["legs"]).to_csv(
        output / "trade_legs.csv", index=False
    )

    equity = pd.DataFrame(state["equity"])

    if not equity.empty:
        equity["peak"] = equity.equity.cummax()
        equity["drawdown"] = equity.equity - equity.peak

    equity.to_csv(output / "equity.csv", index=False)

    with (output / "events.jsonl").open(
        "w", encoding="utf-8"
    ) as f:
        for record in state["events"]:
            f.write(json.dumps(record) + "\n")

    trades = state["trades"]
    pnl = [t["net_pnl"] for t in trades]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]

    streak = longest = 0
    for x in pnl:
        streak = streak + 1 if x < 0 else 0
        longest = max(longest, streak)

    max_drawdown = (
        float(-equity.drawdown.min())
        if not equity.empty else 0.0
    )

    if equity.empty:
        monthly = {}
        sharpe = None
    else:
        dated = equity.copy()
        dated["date"] = pd.to_datetime(dated.datetime).dt.date
        dated["month"] = pd.to_datetime(
            dated.datetime
        ).dt.to_period("M").astype(str)

        day_end = dated.groupby("date").equity.last()
        day_ret = day_end.pct_change().dropna()

        sharpe = (
            float(day_ret.mean() / day_ret.std() * math.sqrt(252))
            if len(day_ret) >= 2 and day_ret.std() > 0
            else None
        )

        month_end = dated.groupby("month").equity.last()
        previous = cfg.capital
        monthly = {}

        for month, value in month_end.items():
            monthly[month] = (
                float(value) / previous - 1
            ) * 100
            previous = float(value)

    report = {
        "strategy": cfg.strategy,
        "data_type": (
            "SYNTHETIC_DEMO" if cfg.demo else
            "USER_SUPPLIED_DATA_UNVERIFIED"
        ),
        "cost_rates": "ILLUSTRATIVE_ONLY",
        "completed_trades": len(trades),
        "net_pnl": round(sum(pnl), 2),
        "max_drawdown": round(max_drawdown, 2),
        "win_rate_percent": (
            round(100 * len(wins) / len(pnl), 2)
            if pnl else 0
        ),
        "profit_factor": (
            sum(wins) / abs(sum(losses))
            if losses else None
        ),
        "expectancy": (
            sum(pnl) / len(pnl) if pnl else 0
        ),
        "average_r_multiple": (
            sum(t["r_multiple"] for t in trades) / len(trades)
            if trades else 0
        ),
        "longest_losing_streak": longest,
        "annualized_daily_sharpe": sharpe,
        "monthly_returns_percent": monthly,
        "open_position_remaining": (
            state["position"] is not None
        )
    }

    (output / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    html = [
        "<html><head><meta charset='utf-8'>",
        "<title>AlgoDesk Assessment Report</title></head><body>",
        f"<h1>Strategy {cfg.strategy} - Backtest Report</h1>",
        "<p>Unverified costs and strategy assumptions. "
        "Synthetic data is not historical market performance.</p>",
        "<table border='1' cellpadding='8'>"
    ]

    for key, value in report.items():
        html.append(f"<tr><td>{key}</td><td>{value}</td></tr>")

    html.extend(["</table></body></html>"])

    (output / "report.html").write_text(
        "\n".join(html), encoding="utf-8"
    )

    print(json.dumps(report, indent=2))


def generate_demo(path):
    """Deterministic fictional candles, never real market data."""
    random.seed(42)
    rows = []
    price = 100.0

    for day in pd.bdate_range("2026-10-05", periods=10):
        for k in range(187):
            timestamp = (
                day + pd.Timedelta(hours=9, minutes=17)
                + pd.Timedelta(minutes=2 * k)
            )

            phase = k % 75

            if phase < 25:
                drift = -0.28
            elif phase < 55:
                drift = 0.48
            else:
                drift = -0.10

            opening = price
            closing = max(
                5, opening + drift + random.uniform(-0.25, 0.25)
            )

            high = max(opening, closing) + random.uniform(0.05, 0.22)
            low = min(opening, closing) - random.uniform(0.05, 0.22)

            rows.append({
                "datetime": timestamp.isoformat(),
                "open": round(opening, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(closing, 2)
            })

            price = closing

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Created synthetic demonstration data: {path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--data")
    parser.add_argument("--strategy", choices=["A", "B"], default="A")
    parser.add_argument("--instrument", default="DEMO")
    parser.add_argument("--mode", choices=["backtest", "paper"],
                        default="backtest")
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--kill", action="store_true")
    parser.add_argument("--limit", type=int)

    parser.add_argument("--lot-size", type=int, default=1)
    parser.add_argument("--lots", type=int, default=2)
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--tick", type=float, default=0.05)
    parser.add_argument("--slippage", type=float, default=2)
    parser.add_argument("--oversized", type=float, default=2.0)
    parser.add_argument("--macd-window", type=int, default=1)
    parser.add_argument("--cooldown", type=int, default=30)
    parser.add_argument("--max-trades", type=int, default=5)
    parser.add_argument("--max-daily-loss", type=float, default=10000)

    cfg = parser.parse_args()

    if cfg.demo:
        cfg.data = "data/synthetic_demo.csv"
        generate_demo(Path(cfg.data))

    if not cfg.data:
        parser.error("Provide --data path or use --demo")

    if (
        cfg.lot_size <= 0 or cfg.lots < 2
        or cfg.capital <= 0 or cfg.macd_window < 1
    ):
        parser.error("Invalid quantity, capital or MACD window")

    data = pd.read_csv(cfg.data)
    df = prepare_indicators(data)

    if cfg.demo:
        # Backtest both strategies using fictional test candles.
        for strategy in ["A", "B"]:
            cfg.strategy = strategy
            cfg.mode = "backtest"
            cfg.output = f"outputs/demo_{strategy}"
            cfg.instrument = "SYNTHETIC_TEST_ONLY"

            result = run_engine(df, cfg)
            export_results(result, cfg)
    else:
        result = run_engine(df, cfg)
        export_results(result, cfg)


if __name__ == "__main__":
    main()
