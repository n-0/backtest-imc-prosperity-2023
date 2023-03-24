from dontlooseshells_algo import Trader

from datamodel import *
from typing import Any
import pandas as pd
import statistics
import copy
import uuid

# Timesteps used in training files
TIME_DELTA = 100
# Please put all! the price and log files into
# the same directory or adjust the code accordingly
TRAINING_DATA_PREFIX = "./training"

def process_prices(df_prices, time_limit) -> dict[int, TradingState]:
    states = {}
    for _, row in df_prices.iterrows():
        time: int = int(row["timestamp"])
        if time > time_limit:
            break
        product: str = row["product"]
        if states.get(time) == None:
            position: Dict[Product, Position] = {}
            own_trades: Dict[Symbol, List[Trade]] = {}
            market_trades: Dict[Symbol, List[Trade]] = {}
            observations: Dict[Product, Observation] = {}
            listings = {}
            depths = {}
            states[time] = TradingState(time, listings, depths, own_trades, market_trades, position, observations)

        states[time].listings[product] = Listing(product, product, product)
        depth = OrderDepth()
        if row["bid_price_1"]> 0:
            depth.buy_orders[row["bid_price_1"]] = int(row["bid_volume_1"])
        if row["bid_price_2"]> 0:
            depth.buy_orders[row["bid_price_2"]] = int(row["bid_volume_2"])
        if row["bid_price_3"]> 0:
            depth.buy_orders[row["bid_price_3"]] = int(row["bid_volume_3"])
        if row["ask_price_1"]> 0:
            depth.sell_orders[row["ask_price_1"]] = int(row["ask_volume_1"])
        if row["ask_price_2"]> 0:
            depth.sell_orders[row["ask_price_2"]] = int(row["ask_volume_2"])
        if row["ask_price_3"]> 0:
            depth.sell_orders[row["ask_price_3"]] = int(row["ask_volume_3"])
        states[time].order_depths[product] = depth

        if product not in states[time].position:
            states[time].position[product] = 0
            states[time].own_trades[product] = []
            states[time].market_trades[product] = []
    return states

def process_trades(df_trades, states: dict[int, TradingState], time_limit):
    for _, trade in df_trades.iterrows():
        time: int = trade['timestamp']
        if time > time_limit:
            break
        symbol = trade['symbol']
        if symbol not in states[time].market_trades:
            states[time].market_trades[symbol] = []
        t = Trade(
                symbol, 
                trade['price'], 
                trade['quantity'], 
                '', #trade['buyer'], 
                '', #trade['seller'], 
                time)
        states[time].market_trades[symbol].append(t)
       
current_limits = {
    'PEARLS': 20,
    'BANANAS': 20,
    'COCONUTS': 600,
    'PINA_COLADAS': 300
}

# Setting a high time_limit can be harder to visualize
def simulate_alternative(round: int, day: int, trader, time_limit=999900):
    prices_path = f"{TRAINING_DATA_PREFIX}/prices_round_{round}_day_{day}.csv"
    trades_path = f"{TRAINING_DATA_PREFIX}/trades_round_{round}_day_{day}_nn.csv"
    df_prices = pd.read_csv(prices_path, sep=';')
    df_trades = pd.read_csv(trades_path, sep=';')
    states = process_prices(df_prices, time_limit)
    process_trades(df_trades, states, time_limit)
    position = copy.copy(states[0].position)
    for time, state in states.items():
        position = copy.copy(state.position)
        orders = trader.run(state)
        trades = clear_order_book(orders, state.order_depths, time)
        if len(trades) > 0:
            grouped_by_symbol = {}
            for trade in trades:
                if grouped_by_symbol.get(trade.symbol) == None:
                    grouped_by_symbol[trade.symbol] = []
                n_position = position[trade.symbol] + trade.quantity 
                if abs(n_position) > current_limits[trade.symbol]:
                    print("ILLEGAL TRADE, WOULD EXCEED POSITION LIMIT, KILLING ALL REMAINING ORDERS")
                    break
                position[trade.symbol] = n_position
                grouped_by_symbol[trade.symbol].append(trade)
            if states.get(time + TIME_DELTA) != None:
                states[time + TIME_DELTA].own_trades = grouped_by_symbol
        if states.get(time + TIME_DELTA) != None:
            states[time + TIME_DELTA].position = position
    create_log_file(states, day, trader) 

def cleanup_order_volumes(org_orders: List[Order]) -> List[Order]:
    orders = copy.deepcopy(org_orders)
    for order_1 in org_orders:
        final_order = copy.copy(order_1)
        for order_2 in org_orders:
            if order_1 == order_2:
               continue 
            if order_1.price == order_2.price:
                final_order.quantity += order_2.quantity
        orders.append(final_order)
    return orders

def clear_order_book(trader_orders: dict[str, List[Order]], order_depth: dict[str, OrderDepth], time: int) -> list[Trade]:
        trades = []
        for symbol in trader_orders.keys():
            if order_depth.get(symbol) != None:
                symbol_order_depth = copy.deepcopy(order_depth[symbol])
                t_orders = cleanup_order_volumes(trader_orders[symbol])
                for order in t_orders:
                    if order.quantity < 0:
                        potential_matches = list(filter(lambda o: o[0] == order.price, symbol_order_depth.buy_orders.items()))
                        if len(potential_matches) > 0:
                            match = potential_matches[0]
                            final_volume = 0
                            if match[1] > order.quantity:
                                final_volume = order.quantity
                            else:
                                final_volume = match[1]
                            trades.append(Trade(symbol, order.price, final_volume, "YOU", "BOT", time))
                    if order.quantity > 0:
                        potential_matches = list(filter(lambda o: o[0] == order.price, symbol_order_depth.sell_orders.items()))
                        if len(potential_matches) > 0:
                            match = potential_matches[0]
                            final_volume = 0
                            if match[1] > order.quantity:
                                final_volume = order.quantity
                            else:
                                final_volume = match[1]
                            trades.append(Trade(symbol, order.price, final_volume, "YOU", "BOT", time))
        return trades
                            
csv_header = "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss"
log_header = ['Sandbox logs:\n', 
              '0 OpenBLAS WARNING - could not determine the L2 cache size on this system, assuming 256k\n', 
              'START RequestId: fcc44f9f-1aef-4542-ac1f-f2d79914f659 Version: $LATEST\n',
              'END RequestId: fcc44f9f-1aef-4542-ac1f-f2d79914f659\n',
              'REPORT RequestId: fcc44f9f-1aef-4542-ac1f-f2d79914f659	Duration: 21.16 ms	Billed Duration: 22 ms	Memory Size: 128 MB	Max Memory Used: 66 MB	Init Duration: 601.84 ms\n'
]

def create_log_file(states: dict[int, TradingState], day, trader: Trader):
    file_name = uuid.uuid4()
    with open(f'{file_name}.log', 'w', encoding="utf-8") as f:
        f.writelines(log_header)
        csv_rows = []
        f.write('\n\n')
        for time, state in states.items():
            if trader.__getattribute__('logger') != None:
                if trader.logger.__getattribute__('local_logs') != None:
                    if trader.logger.local_logs.get(time) != None:
                        f.write(f'{time} {trader.logger.local_logs[time]}\n')
                        continue
            if time != 0:
                f.write(f'{time}\n')

        f.write(f'\n\n')
        f.write('Submission logs:\n\n\n')
        f.write('Activities log:\n')
        f.write(csv_header)
        for time, state in states.items():
            for symbol in state.order_depths.keys():
                f.write(f'{day};{time};{symbol};')
                bids_length = len(state.order_depths[symbol].buy_orders)
                bids = list(state.order_depths[symbol].buy_orders.items())
                bids_prices = list(state.order_depths[symbol].buy_orders.keys())
                bids_prices.sort()
                asks_length = len(state.order_depths[symbol].sell_orders)
                asks_prices = list(state.order_depths[symbol].sell_orders.keys())
                asks_prices.sort()
                asks = list(state.order_depths[symbol].sell_orders.items())
                if bids_length >= 3:
                    f.write(f'{bids[0][0]};{bids[0][1]};{bids[1][0]};{bids[1][1]};{bids[2][0]};{bids[2][1]};')
                elif bids_length == 2:
                    f.write(f'{bids[0][0]};{bids[0][1]};{bids[1][0]};{bids[1][1]};;;')
                elif bids_length == 1:
                    f.write(f'{bids[0][0]};{bids[0][1]};;;;;')
                else:
                    f.write(f';;;;;;')
                if asks_length >= 3:
                    f.write(f'{asks[0][0]};{asks[0][1]};{asks[1][0]};{asks[1][1]};{asks[2][0]};{asks[2][1]};')
                elif asks_length == 2:
                    f.write(f'{asks[0][0]};{asks[0][1]};{asks[1][0]};{asks[1][1]};;;')
                elif asks_length == 1:
                    f.write(f'{asks[0][0]};{asks[0][1]};;;;;')
                else:
                    f.write(f';;;;;;')
                f.write(f'{statistics.median(asks_prices + bids_prices)};0.0\n')


# Adjust accordingly the round and day to your needs
if __name__ == "__main__":
    trader = Trader()
    simulate_alternative(2, 0, trader, 20100)
