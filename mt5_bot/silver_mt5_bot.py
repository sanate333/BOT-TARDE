"""
Silver RSI Bot MT5 - Bot de Trading Automatizado para Silver (XAGUSD)
Estrategia basada en RSI + EMA50 (del video de YouTube).

Estrategia:
    - COMPRA: RSI(14) < 30 AND Precio > EMA(50)
    - VENTA/CIERRE: RSI(14) > 70
    - Stop Loss: 50 pips
    - Take Profit: 100 pips
    - Trailing Stop: 30 pips (se activa a 50 pips de ganancia)

Uso:
    python silver_mt5_bot.py --config silver_config.json

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
from datetime import datetime
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('silver_rsi_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SilverRSI_Bot')


class SilverRSIBot:
    """
    Bot de trading para Silver (XAGUSD) en MT5.
    Estrategia simple: RSI oversold/overbought + EMA50 como filtro de tendencia.
    """

    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Símbolo - Silver puede tener diferentes nombres según el broker
        self.symbol = self.config.get('symbol', 'XAGUSD')
        self.symbol_alternatives = self.config.get('symbol_alternatives', [
            'XAGUSD', 'XAGUSD.', 'SILVER', 'Silver', 'XAGUSD.pro'
        ])

        # Timeframe
        self.timeframe_map = {
            '1m': mt5.TIMEFRAME_M1, '5m': mt5.TIMEFRAME_M5,
            '15m': mt5.TIMEFRAME_M15, '30m': mt5.TIMEFRAME_M30,
            '1h': mt5.TIMEFRAME_H1, '4h': mt5.TIMEFRAME_H4,
            '1d': mt5.TIMEFRAME_D1
        }
        self.timeframe = self.config.get('timeframe', '5m')
        self.mt5_timeframe = self.timeframe_map[self.timeframe]

        # Parámetros RSI
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_buy_level = self.config.get('rsi_buy_level', 30)
        self.rsi_sell_level = self.config.get('rsi_sell_level', 70)

        # Parámetros EMA
        self.ema_period = self.config.get('ema_period', 50)

        # Risk management
        self.lot_size = self.config.get('lot_size', 0.01)
        self.stop_loss_pips = self.config.get('stop_loss_pips', 50)
        self.take_profit_pips = self.config.get('take_profit_pips', 100)
        self.max_trades = self.config.get('max_trades', 1)

        # Trailing stop
        self.trailing_stop = self.config.get('trailing_stop', True)
        self.trailing_pips = self.config.get('trailing_pips', 30)
        self.trailing_start_pips = self.config.get('trailing_start_pips', 50)

        # Dry run
        self.dry_run = self.config.get('dry_run', True)

        # Magic number para identificar trades del bot
        self.magic_number = self.config.get('magic_number', 234100)

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

        # Login si hay credenciales
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

        # Buscar el símbolo correcto de Silver
        self._resolve_symbol()

        return True

    def _resolve_symbol(self):
        """Buscar el nombre correcto del símbolo Silver en el broker."""
        # Intentar seleccionar el símbolo configurado
        if mt5.symbol_select(self.symbol, True):
            info = mt5.symbol_info(self.symbol)
            if info is not None:
                logger.info(f"Símbolo Silver encontrado: {self.symbol}")
                return

        # Si no funciona, buscar alternativas
        logger.warning(f"Símbolo {self.symbol} no encontrado, buscando alternativas...")
        for alt in self.symbol_alternatives:
            if mt5.symbol_select(alt, True):
                info = mt5.symbol_info(alt)
                if info is not None:
                    self.symbol = alt
                    logger.info(f"Símbolo Silver encontrado como: {alt}")
                    return

        logger.warning(f"No se encontró símbolo Silver automáticamente. Usando: {self.symbol}")

    def pips_to_price(self, pips: int) -> float:
        """Convertir pips a distancia de precio para Silver."""
        info = mt5.symbol_info(self.symbol)
        if info is None:
            # Default para Silver: 1 pip = 0.01
            return pips * 0.01

        digits = info.digits
        if digits == 2:
            return pips * 0.01    # 50 pips = 0.50
        elif digits == 3:
            return pips * 0.01    # 50 pips = 0.50
        else:
            return pips * info.point * 10

    def get_candles(self, count: int = 250) -> pd.DataFrame:
        """Obtener velas históricas de Silver."""
        rates = mt5.copy_rates_from_pos(self.symbol, self.mt5_timeframe, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No se pudieron obtener datos para {self.symbol}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcular RSI y EMA50."""
        if df.empty or len(df) < self.ema_period + 10:
            return df

        # RSI
        df['rsi'] = talib.RSI(df['close'], timeperiod=self.rsi_period)

        # EMA 50
        df['ema_50'] = talib.EMA(df['close'], timeperiod=self.ema_period)

        return df

    def check_buy_signal(self, df: pd.DataFrame) -> bool:
        """
        Señal de COMPRA:
        - RSI < 30 (sobreventa)
        - Precio > EMA50 (tendencia alcista)
        """
        if len(df) < 2:
            return False

        last = df.iloc[-2]  # Usar vela cerrada

        rsi_oversold = last['rsi'] < self.rsi_buy_level
        price_above_ema = last['close'] > last['ema_50']

        if rsi_oversold and price_above_ema:
            logger.info(f"SEÑAL DE COMPRA: RSI({last['rsi']:.1f}) < {self.rsi_buy_level} | "
                       f"Precio({last['close']:.5f}) > EMA50({last['ema_50']:.5f})")
            return True

        return False

    def check_sell_signal(self, df: pd.DataFrame) -> bool:
        """
        Señal de VENTA/CIERRE:
        - RSI > 70 (sobrecompra)
        """
        if len(df) < 2:
            return False

        last = df.iloc[-2]  # Usar vela cerrada

        rsi_overbought = last['rsi'] > self.rsi_sell_level

        if rsi_overbought:
            logger.info(f"SEÑAL DE VENTA: RSI({last['rsi']:.1f}) > {self.rsi_sell_level}")
            return True

        return False

    def check_short_signal(self, df: pd.DataFrame) -> bool:
        """
        Señal de SHORT:
        - RSI > 70 (sobrecompra)
        - Precio < EMA50 (tendencia bajista)
        """
        if len(df) < 2:
            return False

        last = df.iloc[-2]

        rsi_overbought = last['rsi'] > self.rsi_sell_level
        price_below_ema = last['close'] < last['ema_50']

        if rsi_overbought and price_below_ema:
            logger.info(f"SEÑAL SHORT: RSI({last['rsi']:.1f}) > {self.rsi_sell_level} | "
                       f"Precio({last['close']:.5f}) < EMA50({last['ema_50']:.5f})")
            return True

        return False

    def get_symbol_info(self) -> dict:
        """Obtener información del símbolo."""
        info = mt5.symbol_info(self.symbol)
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

    def place_order(self, order_type: str, reason: str) -> bool:
        """Ejecutar orden en MT5."""
        info = self.get_symbol_info()
        if info is None:
            logger.error(f"No se pudo obtener info de {self.symbol}")
            return False

        price = info['ask'] if order_type == 'buy' else info['bid']
        pip_value = self.pips_to_price(1)

        if order_type == 'buy':
            sl = round(price - self.stop_loss_pips * pip_value, info['digits'])
            tp = round(price + self.take_profit_pips * pip_value, info['digits'])
        else:
            sl = round(price + self.stop_loss_pips * pip_value, info['digits'])
            tp = round(price - self.take_profit_pips * pip_value, info['digits'])

        lot = max(info['volume_min'], self.lot_size)
        lot = min(lot, info['volume_max'])

        if self.dry_run:
            logger.info(f"[DRY RUN] {order_type.upper()} {self.symbol} @ {price} | "
                       f"SL: {sl} ({self.stop_loss_pips} pips) | "
                       f"TP: {tp} ({self.take_profit_pips} pips) | "
                       f"Lot: {lot} | Razón: {reason}")
            self.active_trades[self.symbol] = {
                'type': order_type, 'price': price,
                'sl': sl, 'tp': tp, 'time': datetime.now(),
                'reason': reason
            }
            return True

        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == 'buy' else mt5.ORDER_TYPE_SELL

        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': self.symbol,
            'volume': lot,
            'type': mt5_order_type,
            'price': price,
            'sl': sl,
            'tp': tp,
            'deviation': 30,  # Mayor desviación para Silver (volátil)
            'magic': self.magic_number,
            'comment': f'SilverRSI_{reason}',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"order_send falló: {mt5.last_error()}")
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Orden rechazada: retcode={result.retcode}, comment={result.comment}")
            return False

        logger.info(f"ORDEN EJECUTADA: {order_type.upper()} {self.symbol} @ {price} | "
                   f"SL: {sl} | TP: {tp} | Ticket: {result.order}")
        self.active_trades[self.symbol] = {
            'type': order_type, 'price': price,
            'sl': sl, 'tp': tp, 'ticket': result.order,
            'time': datetime.now(), 'reason': reason
        }
        return True

    def close_position(self, reason: str) -> bool:
        """Cerrar posición abierta de Silver."""
        if self.dry_run:
            if self.symbol in self.active_trades:
                trade_info = self.active_trades.pop(self.symbol)
                logger.info(f"[DRY RUN] CERRADA posición {trade_info['type'].upper()} {self.symbol} | Razón: {reason}")
                return True
            return False

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return False

        for pos in positions:
            if pos.magic != self.magic_number:
                continue

            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(self.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).ask

            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': self.symbol,
                'volume': pos.volume,
                'type': close_type,
                'position': pos.ticket,
                'price': price,
                'deviation': 30,
                'magic': self.magic_number,
                'comment': f'SilverRSI_close_{reason}',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"POSICIÓN CERRADA: {self.symbol} ticket={pos.ticket} | "
                           f"Profit: {pos.profit} | Razón: {reason}")
                self.active_trades.pop(self.symbol, None)
                return True
            else:
                logger.error(f"Error cerrando posición: {result}")

        return False

    def has_position(self) -> bool:
        """Verificar si hay posición abierta."""
        if self.dry_run:
            return self.symbol in self.active_trades

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return False
        return any(p.magic == self.magic_number for p in positions)

    def get_position_type(self) -> str:
        """Obtener tipo de posición abierta."""
        if self.dry_run:
            if self.symbol in self.active_trades:
                return self.active_trades[self.symbol]['type']
            return None

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return None
        for p in positions:
            if p.magic == self.magic_number:
                return 'buy' if p.type == mt5.ORDER_TYPE_BUY else 'sell'
        return None

    def manage_trailing_stop(self):
        """Gestionar trailing stop."""
        if not self.trailing_stop or self.dry_run:
            return

        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return

        pip_value = self.pips_to_price(1)

        for pos in positions:
            if pos.magic != self.magic_number:
                continue

            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                continue

            if pos.type == mt5.ORDER_TYPE_BUY:
                profit_pips = (tick.bid - pos.price_open) / pip_value
                if profit_pips >= self.trailing_start_pips:
                    new_sl = tick.bid - self.trailing_pips * pip_value
                    info = mt5.symbol_info(self.symbol)
                    new_sl = round(new_sl, info.digits)
                    if new_sl > pos.sl:
                        request = {
                            'action': mt5.TRADE_ACTION_SLTP,
                            'symbol': self.symbol,
                            'position': pos.ticket,
                            'sl': new_sl,
                            'tp': pos.tp,
                            'magic': self.magic_number,
                        }
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"Trailing SL BUY: {self.symbol} -> SL={new_sl} | Profit: {profit_pips:.0f} pips")

            elif pos.type == mt5.ORDER_TYPE_SELL:
                profit_pips = (pos.price_open - tick.ask) / pip_value
                if profit_pips >= self.trailing_start_pips:
                    new_sl = tick.ask + self.trailing_pips * pip_value
                    info = mt5.symbol_info(self.symbol)
                    new_sl = round(new_sl, info.digits)
                    if new_sl < pos.sl or pos.sl == 0:
                        request = {
                            'action': mt5.TRADE_ACTION_SLTP,
                            'symbol': self.symbol,
                            'position': pos.ticket,
                            'sl': new_sl,
                            'tp': pos.tp,
                            'magic': self.magic_number,
                        }
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"Trailing SL SELL: {self.symbol} -> SL={new_sl} | Profit: {profit_pips:.0f} pips")

    def process(self):
        """Procesar Silver: verificar señales y ejecutar trades."""
        # Verificar que el símbolo está disponible
        if not mt5.symbol_select(self.symbol, True):
            logger.warning(f"Símbolo {self.symbol} no disponible")
            return

        # Obtener datos
        df = self.get_candles(250)
        if df.empty:
            return

        df = self.calculate_indicators(df)
        if df.empty:
            return

        last = df.iloc[-2]  # Última vela cerrada
        if pd.isna(last['rsi']) or pd.isna(last['ema_50']):
            return

        # Log estado actual
        current_price = mt5.symbol_info_tick(self.symbol)
        if current_price:
            logger.debug(f"Silver: Precio={current_price.bid:.5f} | "
                        f"RSI={last['rsi']:.1f} | EMA50={last['ema_50']:.5f}")

        # Gestionar trailing stop
        self.manage_trailing_stop()

        # Si hay posición, verificar señal de cierre
        if self.has_position():
            pos_type = self.get_position_type()

            if pos_type == 'buy' and self.check_sell_signal(df):
                self.close_position('RSI_overbought_exit')
            elif pos_type == 'sell' and self.check_buy_signal(df):
                self.close_position('RSI_oversold_exit')
            return

        # Si no hay posición, verificar señales de entrada
        if self.check_buy_signal(df):
            self.place_order('buy', 'RSI_oversold_buy')
        elif self.check_short_signal(df):
            self.place_order('sell', 'RSI_overbought_sell')

    def run(self):
        """Loop principal del bot."""
        if not self.connect():
            logger.error("No se pudo conectar a MT5. Verifica que MetaTrader 5 esté abierto.")
            return

        self.running = True
        interval = self.config.get('check_interval_seconds', 30)

        mode = "DRY RUN (simulación)" if self.dry_run else "LIVE TRADING"
        logger.info("=" * 60)
        logger.info(f"Silver RSI Bot iniciado en modo: {mode}")
        logger.info(f"Símbolo: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Estrategia: RSI({self.rsi_period}) + EMA({self.ema_period})")
        logger.info(f"  COMPRA: RSI < {self.rsi_buy_level} + Precio > EMA{self.ema_period}")
        logger.info(f"  VENTA:  RSI > {self.rsi_sell_level}")
        logger.info(f"Lote: {self.lot_size} | SL: {self.stop_loss_pips} pips | TP: {self.take_profit_pips} pips")
        logger.info(f"Trailing: {'ON' if self.trailing_stop else 'OFF'} ({self.trailing_pips} pips @ {self.trailing_start_pips} pips)")
        logger.info(f"Max trades: {self.max_trades}")
        logger.info(f"Intervalo: {interval}s")
        logger.info("=" * 60)

        try:
            while self.running:
                try:
                    self.process()

                    if self.has_position():
                        trade_info = self.active_trades.get(self.symbol, {})
                        logger.info(f"Posición abierta: {trade_info.get('type', '?').upper()} "
                                   f"@ {trade_info.get('price', 0)}")

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
        logger.info("Conexión MT5 cerrada. Silver RSI Bot detenido.")


def main():
    parser = argparse.ArgumentParser(description='Silver RSI Bot - Trading automático de Silver en MT5')
    parser.add_argument('--config', type=str, default='silver_config.json',
                        help='Ruta al archivo de configuración JSON')
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        # Si no existe, crear uno por defecto
        default_config = {
            "symbol": "XAGUSD",
            "timeframe": "5m",
            "rsi_period": 14,
            "rsi_buy_level": 30,
            "rsi_sell_level": 70,
            "ema_period": 50,
            "lot_size": 0.01,
            "stop_loss_pips": 50,
            "take_profit_pips": 100,
            "max_trades": 1,
            "trailing_stop": True,
            "trailing_pips": 30,
            "trailing_start_pips": 50,
            "dry_run": True,
            "check_interval_seconds": 30,
            "magic_number": 234100
        }
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info(f"Configuración por defecto creada: {config_path}")
        logger.info("Edita el archivo y vuelve a ejecutar.")
        sys.exit(0)

    bot = SilverRSIBot(str(config_path))
    bot.run()


if __name__ == '__main__':
    main()
