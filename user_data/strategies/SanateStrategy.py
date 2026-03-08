import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_pair, DecimalParameter, IntParameter
from freqtrade.persistence import Trade
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
from datetime import datetime, timedelta
from functools import reduce


class SanateStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    startup_candle_count = 200
    can_short = True
    minimal_roi = {"0": 0.08, "30": 0.05, "60": 0.03, "120": 0.015, "240": 0.008, "480": 0.004}
    stoploss = -0.04
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True
    order_types = {'entry': 'limit', 'exit': 'limit', 'stoploss': 'market', 'stoploss_on_exchange': True}
    order_time_in_force = {'entry': 'GTC', 'exit': 'GTC'}
    buy_rsi_fast = IntParameter(10, 40, default=30, space='buy', optimize=True)
    sell_rsi_fast = IntParameter(60, 90, default=70, space='sell', optimize=True)
    bb_buy_trigger = DecimalParameter(0.97, 1.0, default=0.99, space='buy', optimize=True)
    bb_sell_trigger = DecimalParameter(1.0, 1.03, default=1.01, space='sell', optimize=True)
    adx_min = IntParameter(15, 35, default=20, space='buy', optimize=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, tf) for tf in ['15m', '1h'] for pair in pairs]

    def populate_indicators(self, dataframe, metadata):
        dataframe['ema_9'] = ta.EMA(dataframe, timeperiod=9)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        stoch = ta.STOCH(dataframe)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        dataframe['volume_mean_20'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean_20']
        if self.dp:
            inf_15m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='15m')
            if not inf_15m.empty:
                inf_15m['rsi_15m'] = ta.RSI(inf_15m, timeperiod=14)
                dataframe = merge_informative_pair(dataframe, inf_15m, self.timeframe, '15m', ffill=True)
            inf_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='1h')
            if not inf_1h.empty:
                inf_1h['rsi_1h'] = ta.RSI(inf_1h, timeperiod=14)
                dataframe = merge_informative_pair(dataframe, inf_1h, self.timeframe, '1h', ffill=True)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        cl = []
        cl.append((dataframe['ema_9'] > dataframe['ema_21']) & (dataframe['ema_21'] > dataframe['ema_50']) & (dataframe['rsi'] > 40) & (dataframe['rsi'] < 65) & (dataframe['adx'] > self.adx_min.value) & (dataframe['plus_di'] > dataframe['minus_di']) & (dataframe['volume_ratio'] > 1.0) & (dataframe['macd'] > dataframe['macdsignal']))
        cl.append((dataframe['close'] < dataframe['bb_lowerband'] * self.bb_buy_trigger.value) & (dataframe['stoch_k'] < 20) & (dataframe['rsi_fast'] < self.buy_rsi_fast.value) & (dataframe['volume_ratio'] > 0.8))
        cl.append(qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) & (dataframe['close'] > dataframe['ema_50']) & (dataframe['adx'] > 18) & (dataframe['rsi'] > 35) & (dataframe['rsi'] < 60) & (dataframe['volume_ratio'] > 1.2))
        combined = reduce(lambda x, y: x | y, cl)
        mtf = True
        if 'rsi_15m_15m' in dataframe.columns:
            mtf = (dataframe['rsi_15m_15m'] > 35) & (dataframe['rsi_15m_15m'] < 70)
        if 'rsi_1h_1h' in dataframe.columns:
            mtf = mtf & (dataframe['rsi_1h_1h'] > 30) & (dataframe['rsi_1h_1h'] < 75)
        dataframe.loc[combined & mtf, 'enter_long'] = 1
        cs = []
        cs.append((dataframe['ema_9'] < dataframe['ema_21']) & (dataframe['ema_21'] < dataframe['ema_50']) & (dataframe['rsi'] < 60) & (dataframe['rsi'] > 35) & (dataframe['adx'] > self.adx_min.value) & (dataframe['minus_di'] > dataframe['plus_di']) & (dataframe['volume_ratio'] > 1.0) & (dataframe['macd'] < dataframe['macdsignal']))
        cs.append((dataframe['close'] > dataframe['bb_upperband'] * self.bb_sell_trigger.value) & (dataframe['stoch_k'] > 80) & (dataframe['rsi_fast'] > self.sell_rsi_fast.value) & (dataframe['volume_ratio'] > 0.8))
        cs.append(qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal']) & (dataframe['close'] < dataframe['ema_50']) & (dataframe['adx'] > 18) & (dataframe['rsi'] > 40) & (dataframe['rsi'] < 65) & (dataframe['volume_ratio'] > 1.2))
        combined_s = reduce(lambda x, y: x | y, cs)
        mtf_s = True
        if 'rsi_15m_15m' in dataframe.columns:
            mtf_s = (dataframe['rsi_15m_15m'] > 30) & (dataframe['rsi_15m_15m'] < 65)
        if 'rsi_1h_1h' in dataframe.columns:
            mtf_s = mtf_s & (dataframe['rsi_1h_1h'] > 25) & (dataframe['rsi_1h_1h'] < 70)
        dataframe.loc[combined_s & mtf_s, 'enter_short'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[((dataframe['rsi'] > 72) & (dataframe['macd'] < dataframe['macdsignal'])) | (qtpylib.crossed_below(dataframe['ema_9'], dataframe['ema_21']) & (dataframe['adx'] > 20)) | ((dataframe['close'] > dataframe['bb_upperband']) & (dataframe['stoch_k'] > 80)), 'exit_long'] = 1
        dataframe.loc[((dataframe['rsi'] < 28) & (dataframe['macd'] > dataframe['macdsignal'])) | (qtpylib.crossed_above(dataframe['ema_9'], dataframe['ema_21']) & (dataframe['adx'] > 20)) | ((dataframe['close'] < dataframe['bb_lowerband']) & (dataframe['stoch_k'] < 20)), 'exit_short'] = 1
        return dataframe

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return 3.0

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        if current_profit > 0.08:
            return -0.004
        if current_profit > 0.05:
            return -0.008
        if current_profit > 0.03:
            return -0.015
        return self.stoploss
