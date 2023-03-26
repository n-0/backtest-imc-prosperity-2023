from dontlooseshells_algo import Trader

from datamodel import *
from typing import Any
import numpy as np
import pandas as pd
import statistics
import copy
import uuid
import random

# Timesteps used in training files
TIME_DELTA = 100
# Please put all! the price and log files into
# the same directory or adjust the code accordingly
TRAINING_DATA_PREFIX = "./training"

SYMBOLS = [
    'PEARLS',
    'BANANAS',
    'COCONUTS',
    'PINA_COLADAS',
    'DIVING_GEAR',
    'BERRIES',
    'DOLPHIN_SIGHTINGS'
]

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

        if product not in states[time].position:
            states[time].position[product] = 0
            states[time].own_trades[product] = []
            states[time].market_trades[product] = []

        states[time].listings[product] = Listing(product, product, "1")

        if product == "DOLPHIN_SIGHTINGS":
            states[time].observations["DOLPHIN_SIGHTINGS"] = row['mid_price']
            
        depth = OrderDepth()
        if row["bid_price_1"]> 0:
            depth.buy_orders[row["bid_price_1"]] = int(row["bid_volume_1"])
        if row["bid_price_2"]> 0:
            depth.buy_orders[row["bid_price_2"]] = int(row["bid_volume_2"])
        if row["bid_price_3"]> 0:
            depth.buy_orders[row["bid_price_3"]] = int(row["bid_volume_3"])
        if row["ask_price_1"]> 0:
            depth.sell_orders[row["ask_price_1"]] = -int(row["ask_volume_1"])
        if row["ask_price_2"]> 0:
            depth.sell_orders[row["ask_price_2"]] = -int(row["ask_volume_2"])
        if row["ask_price_3"]> 0:
            depth.sell_orders[row["ask_price_3"]] = -int(row["ask_volume_3"])
        states[time].order_depths[product] = depth

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
    'PINA_COLADAS': 300,
    'DIVING_GEAR': 50,
    'BERRIES': 250,
}

# Setting a high time_limit can be harder to visualize
# print_position prints the position before! every Trader.run
def simulate_alternative(round: int, day: int, trader, print_position=False, time_limit=999900, end_liquidation=True):
    prices_path = f"{TRAINING_DATA_PREFIX}/prices_round_{round}_day_{day}.csv"
    trades_path = f"{TRAINING_DATA_PREFIX}/trades_round_{round}_day_{day}_nn.csv"
    df_prices = pd.read_csv(prices_path, sep=';')
    df_trades = pd.read_csv(trades_path, sep=';')
    states = process_prices(df_prices, time_limit)
    process_trades(df_trades, states, time_limit)
    position = copy.copy(states[0].position)
    ref_symbols = list(states[0].position.keys())
    profits_by_symbol: dict[int, dict[str, float]] = { 0: dict(zip(ref_symbols, [0.0]*len(ref_symbols))) }
    max_time = max(list(states.keys()))
    for time, state in states.items():
        position = copy.deepcopy(state.position)
        orders = trader.run(state)
        trades = clear_order_book(orders, state.order_depths, time)
        if print_position:
            print(position)
        if profits_by_symbol.get(time + TIME_DELTA) == None and time != max_time:
            profits_by_symbol[time + TIME_DELTA] = copy.deepcopy(profits_by_symbol[time])
        if len(trades) > 0:
            grouped_by_symbol = {}
            for trade in trades:
                current_pnl = profits_by_symbol[time][trade.symbol]
                if grouped_by_symbol.get(trade.symbol) == None:
                    grouped_by_symbol[trade.symbol] = []
                n_position = position[trade.symbol] + trade.quantity 
                if abs(n_position) > current_limits[trade.symbol]:
                    print('ILLEGAL TRADE, WOULD EXCEED POSITION LIMIT, KILLING ALL REMAINING ORDERS')
                    trade_vars = vars(trade)
                    trade_str = ', '.join("%s: %s" % item for item in trade_vars.items())
                    print(f'Stopped at the following trade: {trade_str}')
                    print(f"All trades that were sent:")
                    for trade in trades:
                        trade_vars = vars(trade)
                        trades_str = ', '.join("%s: %s" % item for item in trade_vars.items())
                        print(trades_str)
                    break
                position[trade.symbol] = n_position
                current_pnl += -trade.price * trade.quantity
                if states.get(time + TIME_DELTA) != None:
                    profits_by_symbol[time + TIME_DELTA][trade.symbol] = current_pnl
            if states.get(time + TIME_DELTA) != None:
                states[time + TIME_DELTA].own_trades = grouped_by_symbol
        if time == max_time:
            print("End of simulation reached. All positions left are liquidated")
            if end_liquidation: 
                liquidate_leftovers(position, profits_by_symbol, state, time)
        if states.get(time + TIME_DELTA) != None:
            states[time + TIME_DELTA].position = copy.deepcopy(position)
    create_log_file(states, day, profits_by_symbol, trader)

def liquidate_leftovers(position: dict[Product, Position], profits_by_symbol: dict[int, dict[str, float]], state: TradingState, time: int):
        liquidated_position = copy.deepcopy(position)
        for symbol in position.keys():
            if liquidated_position[symbol] != 0:
                if liquidated_position[symbol] > 0:
                    sorted_sell_prices = list(state.order_depths[symbol].sell_orders.keys())
                    sorted_sell_prices.sort(reverse=True)
                    for ask_order_price in sorted_sell_prices:
                        if abs(liquidated_position[symbol]) <= abs(state.order_depths[symbol].sell_orders[ask_order_price]):
                            profits_by_symbol[time][symbol] += ask_order_price*liquidated_position[symbol]
                            liquidated_position[symbol] = 0
                            break
                        else:
                            profits_by_symbol[time][symbol] += ask_order_price*state.order_depths[symbol].sell_orders[ask_order_price]
                            liquidated_position[symbol] -= state.order_depths[symbol].sell_orders[ask_order_price]
                    if liquidated_position[symbol] > 0:
                        print(f'Unable to liquidate all LONG positions for {symbol}, left with {liquidated_position[symbol]}')
                else:
                    sorted_buy_prices = list(state.order_depths[symbol].buy_orders.keys())
                    sorted_buy_prices.sort(reverse=True)
                    for buy_order_price in sorted_buy_prices:
                        if abs(liquidated_position[symbol]) <= abs(state.order_depths[symbol].buy_orders[buy_order_price]):
                            profits_by_symbol[time][symbol] -= buy_order_price*liquidated_position[symbol]
                            liquidated_position[symbol] = 0
                            break
                        else:
                            profits_by_symbol[time][symbol] -= buy_order_price*state.order_depths[symbol].buy_orders[buy_order_price]
                            liquidated_position[symbol] += state.order_depths[symbol].buy_orders[buy_order_price]
                    if liquidated_position[symbol] < 0:
                        print(f'Unable to liquidate all SHORT positions for {symbol}, left with {liquidated_position[symbol]}')
            position = liquidated_position
        print(f'\n')

def cleanup_order_volumes(org_orders: List[Order]) -> List[Order]:
    orders = [] #copy.deepcopy(org_orders)
    for order_1 in org_orders:
        final_order = copy.copy(order_1)
        for order_2 in org_orders:
            if order_1.price == order_2.price and order_1.quantity == order_2.quantity:
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
                            #Match[1] will be negative so needs to be changed to work here
                            if abs(match[1]) > order.quantity:
                                final_volume = order.quantity
                            else:
                                final_volume = abs(match[1])
                            trades.append(Trade(symbol, order.price, final_volume, "YOU", "BOT", time))
        return trades
                            
csv_header = "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss"
log_header = [
    'Sandbox logs:\n',
    '0 OpenBLAS WARNING - could not determine the L2 cache size on this system, assuming 256k\n',
    'START RequestId: 8ab36ff8-b4e6-42d4-b012-e6ad69c42085 Version: $LATEST\n',
    'END RequestId: 8ab36ff8-b4e6-42d4-b012-e6ad69c42085\n',
    'REPORT RequestId: 8ab36ff8-b4e6-42d4-b012-e6ad69c42085	Duration: 18.73 ms	Billed Duration: 19 ms	Memory Size: 128 MB	Max Memory Used: 94 MB	Init Duration: 1574.09 ms\n',
]

def create_log_file(states: dict[int, TradingState], day, profits: dict[int, dict[str, float]], trader: Trader):
    file_name = uuid.uuid4()
    with open(f'./logs/{file_name}.log', 'w', encoding="utf-8", newline='\n') as f:
        f.writelines(log_header)
        csv_rows = []
        f.write('\n')
        for time, state in states.items():
            if hasattr(trader, 'logger'):
                if hasattr(trader.logger, 'local_logs') != None:
                    if trader.logger.local_logs.get(time) != None:
                        f.write(f'{time} {trader.logger.local_logs[time]}\n')
                        continue
            if time != 0:
                f.write(f'{time}\n')

        f.write(f'\n\n')
        f.write('Submission logs:\n\n\n\n')
        f.write('Activities log:\n')
        f.write(csv_header)
        for time, state in states.items():
            for symbol in SYMBOLS:
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
                if len(asks_prices) == 0 or max(bids_prices) == 0:
                    if symbol == 'DOLPHIN_SIGHTINGS':
                        dolphin_sightings = state.observations['DOLPHIN_SIGHTINGS']
                        f.write(f'{dolphin_sightings};{profits[time][symbol]}\n')
                    else:
                        f.write(f'{0};{profits[time][symbol]}\n')
                else:
                    min_ask = min(asks_prices)
                    max_bid = max(bids_prices)
                    median_price = statistics.median([min_ask, max_bid])
                    f.write(f'{median_price};{profits[time][symbol]}\n')
                if time == inp:
                    print(f'Final profit for {symbol} = {profits[time][symbol]}')
        print(f"\nSimulation on round {rnd} day {day} for time {inp} complete")


# Adjust accordingly the round and day to your needs
if __name__ == "__main__":
    trader = Trader()
    inp = int(input("Input a timestamp to end (blank for 999000): ") or 999000)
    rnd = int(input("Input a round (blank for 3): ") or 3)
    day = int(input("Input a day (blank for random): ") or random.randint(0, 2))
    print(f"Running simulation on round {rnd} day {day} for time {inp}")
    print("Remember to change the trader import")
    simulate_alternative(rnd, day, trader, False, inp)
