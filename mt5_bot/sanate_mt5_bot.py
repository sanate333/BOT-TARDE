"""
SanateBot MT5 - Bot de Trading Automatizado para MetaTrader 5
Replica la SanateStrategy de Freqtrade para operar Forex en MT5.

Uso:
    python sanate_mt5_bot.py --config mt5_config.json

Requisitos:
    pip install MetaTrader5 pandas numpy ta-lib
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import talib
import json
import time
import logging
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sanate_mt5_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SanateBot_MT5')


class SanateMT5Bot:
    """
    Bot de trading para MT5 que implementa la misma lógica de SanateStrategy.
    Indicadores: EMA(9,21,50), RSI(14,7), MACD, Bollinger Bands, ADX, Stochastic.
    """

    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.symbols = self.config.get('symbols', [
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF',
            'AUDUSD', 'USDCAD', 'NZDUSD', 'EURGBP'
        ])
        self.timeframe_map = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5,
            '15m': mt5.TIMEFRAME_M15, '30m': mt5.TIMEFRAME_M30,
            '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1
        }
        self.timeframe = self.config.get('timeframe', '5m')
        self.mt5_timeframe = self.timeframe_map[self.timeframe]

        # Parámetros de la estrategia (mismos que SanateStrategy)
        self.rsi_buy_threshold = self.config.get('rsi_buy_threshold', 30)
        self.rsi_sell_threshold = self.config.get('rsi_sell_threshold', 70)
        self.bb_buy_trigger = self.config.get('bb_buy_trigger', 0.99)
        self.bb_sell_trigger = self.config.get('bb_sell_trigger', 1.01)
        self.adx_min = self.config.get('adx_min', 20)

        # Risk management
        self.lot_size = self.config.get('lot_size', 0.01)
        self.max_open_trades = self.config.get('max_open_trades', 3)
        self.stoploss_pct = self.config.get('stoploss_pct', 0.04)
        self.take_profit_pct = self.config.get('take_profit_pct', 0.08)
        self.leverage = self.config.get('leverage', 3)

        # Trailing stop
        self.trailing_stop = self.config.get('trailing_stop', True)
        self.trailing_stop_positive = self.config.get('trailing_stop_positive', 0.01)
        self.trailing_stop_positive_offset = self.config.get('trailing_stop_positive_offset', 0.025)

        # Dry run
        self.dry_run = self.config.get('dry_run', True)

        # Estado
        self.active_trades = {}
        self.running = False

    def connect(self) -> bool:
        """Conectar a MetaTrader 5."""
        mt5_path = self.config.get('mt5_path', None)

        if mt5_path:
            if not mt5.initialize(mt5_path):
                logger.error(f"Error al inicializar MT5: {mt5.last_error()}")
                return False
        else:
            if not mt5.initialize():
                logger.error(f"Error al inicializar MT5: {mt5.last_error()}")
                return False

        account = self.config.get('account', None)
        password = self.config.get('password', None)
        server = self.config.get('server', None)

        if account and password and server:
            if not mt5.login(account, password=password, server=server):
                logger.error(f"Error al iniciar sesión: {mt5.last_error()}")
                return False

        account_info = mt5.account_info()
        if account_info:
            logger.info(f"Conectado a cuenta: {account_info.login}")
            logger.info(f"Servidor: {account_info.server}")
            logger.info(f"Balance: {account_info.balance} {account_info.currency}")
            logger.info(f"Leverage: 1:{account_info.leverage}")
        return True

    def get_candles(self, symbol: str, timeframe: int, count: int = 250) -> pd.DataFrame:
        """Obtener velas históricas de MT5."""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No se pudieron obtener datos para {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcular todos los indicadores técnicos (replica SanateStrategy)."""
        if df.empty or len(df) < 200:
            return df

        # EMAs
        df['ema_9'] = talib.EMA(df['close'], timeperiod=9)
        df['ema_21'] = talib.EMA(df['close'], timeperiod=21)
        df['ema_50'] = talib.EMA(df['close'], timeperiod=50)

        # RSI
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)
        df['rsi_fast'] = talib.RSI(df['close'], timeperiod=7)

        # MACD
        df['macd'], df['macdsignal'], df['macdhist'] = talib.MACD(df['close'])

        # Bollinger Bands
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['bb_middle'] = typical_price.rolling(window=20).mean()
        bb_std = typical_price.rolling(window=20).std()
        df['bb_upperband'] = df['bb_middle'] + 2 * bb_std
        df['bb_lowerband'] = df['bb_middle'] - 2 * bb_std

        # ADX y Directional Indicators
        df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
        df['plus_di'] = talib.PLUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
        df['minus_di'] = talib.MINUS_DI(df['high'], df['low'], df['close'], timeperiod=14)

        # Stochastic
        df['stoch_k'], df['stoch_d'] = talib.STOCH(df['high'], df['low'], df['close'])

        # Volumen
        df['volume_mean_20'] = df['tick_volume'].rolling(20).mean()
        df['volume_ratio'] = df['tick_volume'] / df['volume_mean_20']

        return df

    def get_mtf_data(self, symbol: str) -> dict:
        """Obtener datos multi-timeframe (15m y 1h) para filtros adicionales."""
        mtf = {}

        df_15m = self.get_candles(symbol, mt5.TIMEFRAME_M15, 100)
        if not df_15m.empty and len(df_15m) > 14:
            mtf['rsi_15m'] = talib.RSI(df_15m['close'], timeperiod=14).iloc[-1]

        df_1h = self.get_candles(symbol, mt5.TIMEFRAME_H1, 100)
        if not df_1h.empty and len(df_1h) > 14:
            mtf['rsi_1h'] = talib.RSI(df_1h['close'], timeperiod=14).iloc[-1]

        return mtf

    def check_entry_long(self, df: pd.DataFrame, mtf: dict) -> bool:
        """Verificar señales de entrada LONG (compra)."""
        if len(df) < 2:
            return False

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Filtro multi-timeframe
        if 'rsi_15m' in mtf:
            if not (35 < mtf['rsi_15m'] < 70):
                return False
        if 'rsi_1h' in mtf:
            if not (30 < mtf['rsi_1h'] < 75):
                return False

        # Condición 1: Tendencia EMA + RSI + ADX + MACD
        cond1 = (
            last['ema_9'] > last['ema_21'] and
            last['ema_21'] > last['ema_50'] and
            40 < last['rsi'] < 65 and
            last['adx'] > self.adx_min and
            last['plus_di'] > last['minus_di'] and
            last['volume_ratio'] > 1.0 and
            last['macd'] > last['macdsignal']
        )

        # Condición 2: Bollinger Band bounce + Stochastic oversold
        cond2 = (
            last['close'] < last['bb_lowerband'] * self.bb_buy_trigger and
            last['stoch_k'] < 20 and
            last['rsi_fast'] < self.rsi_buy_threshold and
            last['volume_ratio'] > 0.8
        )

        # Condición 3: MACD crossover
        cond3 = (
            prev['macd'] <= prev['macdsignal'] and
            last['macd'] > last['macdsignal'] and
            last['close'] > last['ema_50'] and
            last['adx'] > 18 and
            35 < last['rsi'] < 60 and
            last['volume_ratio'] > 1.2
        )

        return cond1 or cond2 or cond3

    def check_entry_short(self, df: pd.DataFrame, mtf: dict) -> bool:
        """Verificar señales de entrada SHORT (venta)."""
        if len(df) < 2:
            return False

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Filtro multi-timeframe
        if 'rsi_15m' in mtf:
            if not (30 < mtf['rsi_15m'] < 65):
                return False
        if 'rsi_1h' in mtf:
            if not (25 < mtf['rsi_1h'] < 70):
                return False

        # Condición 1: Tendencia bajista EMA
        cond1 = (
            last['ema_9'] < last['ema_21'] and
            last['ema_21'] < last['ema_50'] and
            35 < last['rsi'] < 60 and
            last['adx'] > self.adx_min and
            last['minus_di'] > last['plus_di'] and
            last['volume_ratio'] > 1.0 and
            last['macd'] < last['macdsignal']
        )

        # Condición 2: Bollinger Band reject + Stochastic overbought
        cond2 = (
            last['close'] > last['bb_upperband'] * self.bb_sell_trigger and
            last['stoch_k'] > 80 and
            last['rsi_fast'] > self.rsi_sell_threshold and
            last['volume_ratio'] > 0.8
        )

        # Condición 3: MACD crossover bajista
        cond3 = (
            prev['macd'] >= prev['macdsignal'] and
            last['macd'] < last['macdsignal'] and
            last['close'] < last['ema_50'] and
            last['adx'] > 18 and
            40 < last['rsi'] < 65 and
            last['volume_ratio'] > 1.2
        )

        return cond1 or cond2 or cond3

    def check_exit_long(self, df: pd.DataFrame) -> bool:
        """Verificar señales de salida LONG."""
        last = df.iloc[-1]
        prev = df.iloc[-2]

        cond1 = last['rsi'] > 72 and last['macd'] < last['macdsignal']
        cond2 = (
            prev['ema_9'] >= prev['ema_21'] and
            last['ema_9'] < last['ema_21'] and
            last['adx'] > 20
        )
        cond3 = last['close'] > last['bb_upperband'] and last['stoch_k'] > 80

        return cond1 or cond2 or cond3

    def check_exit_short(self, df: pd.DataFrame) -> bool:
        """Verificar señales de salida SHORT."""
        last = df.iloc[-1]
        prev = df.iloc[-2]

        cond1 = last['rsi'] < 28 and last['macd'] > last['macdsignal']
        cond2 = (
            prev['ema_9'] <= prev['ema_21'] and
            last['ema_9'] > last['ema_21'] and
            last['adx'] > 20
        )
        cond3 = last['close'] < last['bb_lowerband'] and last['stoch_k'] < 20

        return cond1 or cond2 or cond3

    def get_symbol_info(self, symbol: str) -> dict:
        """Obtener información del símbolo para calcular SL/TP."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            'point': info.point,
            'digits': info.digits,
            'spread': info.spread,
            'bid': info.bid,
            'ask': info.ask,
            'volume_min': info.volume_min,
            'volume_max': info.volume_max,
            'volume_step': info.volume_step,
        }

    def calculate_sl_tp(self, symbol: str, order_type: str, price: float) -> tuple:
        """Calcular Stop Loss y Take Profit."""
        info = self.get_symbol_info(symbol)
        if info is None:
            return 0, 0

        sl_distance = price * self.stoploss_pct
        tp_distance = price * self.take_profit_pct

        if order_type == 'buy':
            sl = round(price - sl_distance, info['digits'])
            tp = round(price + tp_distance, info['digits'])
        else:
            sl = round(price + sl_distance, info['digits'])
            tp = round(price - tp_distance, info['digits'])

        return sl, tp

    def place_order(self, symbol: str, order_type: str, reason: str) -> bool:
        """Ejecutar orden en MT5."""
        info = self.get_symbol_info(symbol)
        if info is None:
            logger.error(f"No se pudo obtener info de {symbol}")
            return False

        price = info['ask'] if order_type == 'buy' else info['bid']
        sl, tp = self.calculate_sl_tp(symbol, order_type, price)

        lot = max(info['volume_min'], self.lot_size)
        lot = min(lot, info['volume_max'])

        if self.dry_run:
            logger.info(f"[DRY RUN] {order_type.upper()} {symbol} @ {price} | SL: {sl} | TP: {tp} | Lot: {lot} | Razón: {reason}")
            self.active_trades[symbol] = {
                'type': order_type, 'price': price,
                'sl': sl, 'tp': tp, 'time': datetime.now(),
                'reason': reason
            }
            return True

        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == 'buy' else mt5.ORDER_TYPE_SELL

        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': lot,
            'type': mt5_order_type,
            'price': price,
            'sl': sl,
            'tp': tp,
            'deviation': 20,
            'magic': 234000,
            'comment': f'SanateBot_{reason}',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"order_send falló para {symbol}: {mt5.last_error()}")
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Orden rechazada para {symbol}: retcode={result.retcode}, comment={result.comment}")
            return False

        logger.info(f"ORDEN EJECUTADA: {order_type.upper()} {symbol} @ {price} | SL: {sl} | TP: {tp} | Ticket: {result.order}")
        self.active_trades[symbol] = {
            'type': order_type, 'price': price,
            'sl': sl, 'tp': tp, 'ticket': result.order,
            'time': datetime.now(), 'reason': reason
        }
        return True

    def close_position(self, symbol: str, reason: str) -> bool:
        """Cerrar posición abierta."""
        if self.dry_run:
            if symbol in self.active_trades:
                trade = self.active_trades.pop(symbol)
                logger.info(f"[DRY RUN] CERRADA posición {trade['type'].upper()} {symbol} | Razón: {reason}")
                return True
            return False

        positions = mt5.positions_get(symbol=symbol)
        if positions is None or len(positions) == 0:
            return False

        for pos in positions:
            if pos.magic != 234000:
                continue

            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask

            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': pos.volume,
                'type': close_type,
                'position': pos.ticket,
                'price': price,
                'deviation': 20,
                'magic': 234000,
                'comment': f'SanateBot_close_{reason}',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"POSICIÓN CERRADA: {symbol} ticket={pos.ticket} | Razón: {reason}")
                self.active_trades.pop(symbol, None)
                return True
            else:
                logger.error(f"Error cerrando {symbol}: {result}")

        return False

    def get_open_positions_count(self) -> int:
        """Contar posiciones abiertas del bot."""
        if self.dry_run:
            return len(self.active_trades)

        positions = mt5.positions_get()
        if positions is None:
            return 0
        return sum(1 for p in positions if p.magic == 234000)

    def has_position(self, symbol: str) -> bool:
        """Verificar si ya hay posición abierta en un símbolo."""
        if self.dry_run:
            return symbol in self.active_trades

        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return False
        return any(p.magic == 234000 for p in positions)

    def manage_trailing_stop(self):
        """Gestionar trailing stop para posiciones abiertas."""
        if not self.trailing_stop:
            return

        if self.dry_run:
            return  # En dry run no se puede mover SL

        positions = mt5.positions_get()
        if positions is None:
            return

        for pos in positions:
            if pos.magic != 234000:
                continue

            current_price = mt5.symbol_info_tick(pos.symbol)
            if current_price is None:
                continue

            if pos.type == mt5.ORDER_TYPE_BUY:
                profit_pct = (current_price.bid - pos.price_open) / pos.price_open
                if profit_pct >= self.trailing_stop_positive_offset:
                    new_sl = current_price.bid * (1 - self.trailing_stop_positive)
                    if new_sl > pos.sl:
                        self._modify_sl(pos, new_sl)

            elif pos.type == mt5.ORDER_TYPE_SELL:
                profit_pct = (pos.price_open - current_price.ask) / pos.price_open
                if profit_pct >= self.trailing_stop_positive_offset:
                    new_sl = current_price.ask * (1 + self.trailing_stop_positive)
                    if new_sl < pos.sl or pos.sl == 0:
                        self._modify_sl(pos, new_sl)

    def _modify_sl(self, position, new_sl: float):
        """Modificar stop loss de una posición."""
        info = mt5.symbol_info(position.symbol)
        new_sl = round(new_sl, info.digits)

        request = {
            'action': mt5.TRADE_ACTION_SLTP,
            'symbol': position.symbol,
            'position': position.ticket,
            'sl': new_sl,
            'tp': position.tp,
            'magic': 234000,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Trailing SL actualizado: {position.symbol} -> SL={new_sl}")
        else:
            logger.warning(f"Error actualizando trailing SL: {position.symbol}: {result}")

    def custom_stoploss_check(self, symbol: str, current_profit: float) -> float:
        """Stoploss dinámico basado en ganancias (replica custom_stoploss)."""
        if current_profit > 0.08:
            return -0.004
        if current_profit > 0.05:
            return -0.008
        if current_profit > 0.03:
            return -0.015
        return -self.stoploss_pct

    def process_symbol(self, symbol: str):
        """Procesar un símbolo: verificar señales y ejecutar trades."""
        # Verificar que el símbolo existe en MT5
        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Símbolo {symbol} no disponible en MT5")
            return

        # Obtener datos
        df = self.get_candles(symbol, self.mt5_timeframe, 250)
        if df.empty:
            return

        df = self.calculate_indicators(df)
        if df.empty or df.iloc[-1].isna().any():
            return

        mtf = self.get_mtf_data(symbol)

        # Si ya hay posición, verificar salida
        if self.has_position(symbol):
            trade_info = self.active_trades.get(symbol, {})
            trade_type = trade_info.get('type', 'buy')

            if trade_type == 'buy' and self.check_exit_long(df):
                self.close_position(symbol, 'exit_signal_long')
            elif trade_type == 'sell' and self.check_exit_short(df):
                self.close_position(symbol, 'exit_signal_short')
            return

        # Si no hay posición, verificar entrada
        if self.get_open_positions_count() >= self.max_open_trades:
            return

        if self.check_entry_long(df, mtf):
            self.place_order(symbol, 'buy', 'entry_long')
        elif self.check_entry_short(df, mtf):
            self.place_order(symbol, 'sell', 'entry_short')

    def run(self):
        """Loop principal del bot."""
        if not self.connect():
            logger.error("No se pudo conectar a MT5. Verifica que MetaTrader 5 esté abierto.")
            return

        self.running = True
        interval = self.config.get('check_interval_seconds', 30)

        mode = "DRY RUN (simulación)" if self.dry_run else "LIVE TRADING"
        logger.info(f"{'='*60}")
        logger.info(f"SanateBot MT5 iniciado en modo: {mode}")
        logger.info(f"Símbolos: {self.symbols}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Max trades: {self.max_open_trades}")
        logger.info(f"Lot size: {self.lot_size}")
        logger.info(f"SL: {self.stoploss_pct*100}% | TP: {self.take_profit_pct*100}%")
        logger.info(f"Intervalo de chequeo: {interval}s")
        logger.info(f"{'='*60}")

        try:
            while self.running:
                try:
                    for symbol in self.symbols:
                        self.process_symbol(symbol)

                    self.manage_trailing_stop()

                    open_count = self.get_open_positions_count()
                    if open_count > 0:
                        logger.info(f"Posiciones abiertas: {open_count}/{self.max_open_trades}")

                    time.sleep(interval)

                except Exception as e:
                    logger.error(f"Error en el loop: {e}", exc_info=True)
                    time.sleep(10)

        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario (Ctrl+C)")
        finally:
            self.shutdown()

    def shutdown(self):
        """Cerrar conexión con MT5."""
        self.running = False
        mt5.shutdown()
        logger.info("Conexión MT5 cerrada. Bot detenido.")


def main():
    parser = argparse.ArgumentParser(description='SanateBot MT5 - Trading Bot para Forex')
    parser.add_argument('--config', type=str, default='mt5_config.json',
                        help='Ruta al archivo de configuración JSON')
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Archivo de configuración no encontrado: {config_path}")
        logger.info("Crea mt5_config.json basándote en mt5_config.example.json")
        sys.exit(1)

    bot = SanateMT5Bot(str(config_path))
    bot.run()


if __name__ == '__main__':
    main()
