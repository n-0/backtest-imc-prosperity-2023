# Backtest IMC Prosperity 2023

This is repo contains utilities for IMC Prosperity 2023 challenge.
Right now, it has the [backtester.py](./backtester.py), that should mimic log files from
the prosperity challenge [platform](https://prosperity.imc.com/).
The format is good enough to be accepted by jmerle's amazing [project](https://github.com/jmerle/imc-prosperity-visualizer),
for visualizing the order book as well as your trades.

## Order matching
Orders returned by the `Trader.run` method, are matched against the `OrderDepth`
of the state provided to the method call. The trader always gets their trade and
trades from bots are ignored. An order is matched only if the price is exactly the
same as an opposite one from `OrderDepth`. If the new position that would result from
this order exceeds the specified limit of the symbol, all following orders (including the failing one)
are cancelled. You can relax those conditions by answering sth. to `Matching orders halfway (sth. not blank for True):`, during the input dialog
of the backtester. Halfway matches any volume (regardless of order book), such that
sell/buy orders are always matched, if they're below/above the midprice
of the highest bid/lowest ask (regardless of volume)

## Profit and Loss (PnL)
PnL is calculated by adding the previous profit (starting from 0.0) to the value
of all executed trades. The value of an executed trade is:

```python
current_pnl += -trade.price * trade.quantity
```
Meaning that if the trade was selling a symbol (e.g. Shorting) the trade.quantity is negative ,
ending in a positive `current_pnl`. Hence buying a symbol is a positive trade.quantity, ending in a negative `current_pnl`.

In the final round all open positions that the Trader still has (`position != 0`) are liquidated, giving
for large positions a sharp spike in visualizer. They're matched against the last `OrderDepth` and take any price.
This behavior probably deviates from IMC and can be turned off by supplying `False` as the last argument to `simulate_alternative`
E.g.
```python
simulate_alternative(3, 0, trader, False, 30000, True)`
```


## After All
If your trader has a method called `after_last_round`, it will be called after the logs have been written.
This is useful for plotting something with matplotlib for example (but don't forget to remove the import,
when you upload your algorithm).

## General usage
Add the csv's from IMC to the training folder and adjust if necessary the constant `TRAINING_DATA_PREFIX`
to the full path of `training` directory on your system, at the top of `backtester.py`.
Import your Trader at the top of `backtester.py` (in the repo the Trader from `dontlooseshells.py` is used).
Then run
```bash
python backtester.py
```
This executes
```
if __name__ == "__main__":
    trader = Trader()
    simulate_alternative(3, 0, trader, False, 30000)
```
The central method is `simulate_alternative`. There are some default parameters
and the meaning is
```
def simulate_alternative(round: int, day: int, trader, time_limit=999900, end_liquidation=True, halfway=False, print_position=False):
```
where round and day are substituted to the following path `{TRAINING_DATA_PREFIX}/prices_round_{round}_day_{day}.csv` (same for `trades_round...`).
Be careful if you're using windows, where the separator is `\`. Trader is your algorithm trader, `time_limit` can be decreased to only read a part of the full training file. `end_liquidation=False` stops the backtest from liquidating all your open positions in the last round. `halway` enables smarter order matching, `print_position` prints before every call of `Trader.run`
the current position to the stdout

## Logging with jmerle's visualizer
Because the `backtester` doesn't read from the stdout nor stderr, logs produced have an empty `Submission logs:` section (still limit exceeds are printed).
Furthermore the default `Logger` from jmerle's project won't do the trick, the following adjustments make it compatible

```python
class Logger:
    # Set this to true, if u want to create
    # local logs
    local: bool 
    # this is used as a buffer for logs
    # instead of stdout
    local_logs: dict[int, str] = {}

    def __init__(self, local=False) -> None:
        self.logs = ""
        self.local = local

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]]) -> None:
        output = json.dumps({
            "state": state,
            "orders": orders,
            "logs": self.logs,
        }, cls=ProsperityEncoder, separators=(",", ":"), sort_keys=True)
        if self.local:
            self.local_logs[state.timestamp] = output
        print(output)

        self.logs = ""
```

and in your `Trader` class add the attribute like this:
```
class Trader:

    logger = Logger(local=True)
```
Now calls to `self.logger.flush` will be visible in the log files and available to the visualizer.
Thus it can also provide you diagrams about prices, volumes etc.
A working example is given in [dontlooseshells.py](./dontlooseshells.py).

Good luck 🍀
