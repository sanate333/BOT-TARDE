//+------------------------------------------------------------------+
//|                                                 SanateBot_EA.mq5 |
//|                                         SanateBot Trading System  |
//|                        Expert Advisor para Forex - MetaTrader 5   |
//+------------------------------------------------------------------+
#property copyright "SanateBot"
#property version   "1.00"
#property description "Bot de trading automatizado - Replica SanateStrategy"
#property description "Indicadores: EMA, RSI, MACD, Bollinger, ADX, Stochastic"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//--- Parámetros de entrada
input group "=== CONFIGURACIÓN GENERAL ==="
input double   InpLotSize          = 0.01;    // Tamaño del lote
input int      InpMaxTrades        = 3;       // Máximo de operaciones abiertas
input int      InpMagicNumber      = 234000;  // Número mágico
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5; // Timeframe principal

input group "=== GESTIÓN DE RIESGO ==="
input double   InpStopLossPct      = 4.0;     // Stop Loss (%)
input double   InpTakeProfitPct    = 8.0;     // Take Profit (%)
input bool     InpTrailingStop     = true;     // Activar Trailing Stop
input double   InpTrailingPct      = 1.0;     // Trailing Stop (%)
input double   InpTrailingOffset   = 2.5;     // Trailing Offset activación (%)

input group "=== PARÁMETROS DE ESTRATEGIA ==="
input int      InpRSI_BuyThreshold  = 30;     // RSI Fast - Umbral compra
input int      InpRSI_SellThreshold = 70;     // RSI Fast - Umbral venta
input double   InpBB_BuyTrigger     = 0.99;   // BB - Trigger compra
input double   InpBB_SellTrigger    = 1.01;   // BB - Trigger venta
input int      InpADX_Min           = 20;     // ADX mínimo

//--- Handles de indicadores
int handleEMA9, handleEMA21, handleEMA50;
int handleRSI, handleRSI_Fast;
int handleMACD;
int handleADX;
int handleStoch;
int handleRSI_15m, handleRSI_1h;

//--- Buffers
double ema9[], ema21[], ema50[];
double rsi[], rsi_fast[];
double macd_main[], macd_signal[], macd_hist[];
double adx[], plus_di[], minus_di[];
double stoch_k[], stoch_d[];
double rsi_15m[], rsi_1h[];

//--- Objetos de trading
CTrade trade;
CPositionInfo posInfo;
CSymbolInfo symInfo;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   // Configurar objeto de trading
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // Inicializar indicadores
   handleEMA9   = iMA(_Symbol, InpTimeframe, 9, 0, MODE_EMA, PRICE_CLOSE);
   handleEMA21  = iMA(_Symbol, InpTimeframe, 21, 0, MODE_EMA, PRICE_CLOSE);
   handleEMA50  = iMA(_Symbol, InpTimeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
   handleRSI    = iRSI(_Symbol, InpTimeframe, 14, PRICE_CLOSE);
   handleRSI_Fast = iRSI(_Symbol, InpTimeframe, 7, PRICE_CLOSE);
   handleMACD   = iMACD(_Symbol, InpTimeframe, 12, 26, 9, PRICE_CLOSE);
   handleADX    = iADX(_Symbol, InpTimeframe, 14);
   handleStoch  = iStochastic(_Symbol, InpTimeframe, 5, 3, 3, MODE_SMA, STO_LOWHIGH);

   // Multi-timeframe RSI
   handleRSI_15m = iRSI(_Symbol, PERIOD_M15, 14, PRICE_CLOSE);
   handleRSI_1h  = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);

   // Verificar handles
   if(handleEMA9 == INVALID_HANDLE || handleEMA21 == INVALID_HANDLE ||
      handleEMA50 == INVALID_HANDLE || handleRSI == INVALID_HANDLE ||
      handleRSI_Fast == INVALID_HANDLE || handleMACD == INVALID_HANDLE ||
      handleADX == INVALID_HANDLE || handleStoch == INVALID_HANDLE ||
      handleRSI_15m == INVALID_HANDLE || handleRSI_1h == INVALID_HANDLE)
   {
      Print("Error al crear indicadores: ", GetLastError());
      return INIT_FAILED;
   }

   Print("SanateBot EA inicializado correctamente");
   Print("Símbolo: ", _Symbol, " | Timeframe: ", EnumToString(InpTimeframe));
   Print("Lote: ", InpLotSize, " | Max Trades: ", InpMaxTrades);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(handleEMA9);
   IndicatorRelease(handleEMA21);
   IndicatorRelease(handleEMA50);
   IndicatorRelease(handleRSI);
   IndicatorRelease(handleRSI_Fast);
   IndicatorRelease(handleMACD);
   IndicatorRelease(handleADX);
   IndicatorRelease(handleStoch);
   IndicatorRelease(handleRSI_15m);
   IndicatorRelease(handleRSI_1h);

   Print("SanateBot EA detenido");
}

//+------------------------------------------------------------------+
//| Obtener datos de indicadores                                       |
//+------------------------------------------------------------------+
bool GetIndicatorData()
{
   // Configurar arrays como series
   ArraySetAsSeries(ema9, true);
   ArraySetAsSeries(ema21, true);
   ArraySetAsSeries(ema50, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(rsi_fast, true);
   ArraySetAsSeries(macd_main, true);
   ArraySetAsSeries(macd_signal, true);
   ArraySetAsSeries(adx, true);
   ArraySetAsSeries(plus_di, true);
   ArraySetAsSeries(minus_di, true);
   ArraySetAsSeries(stoch_k, true);
   ArraySetAsSeries(stoch_d, true);
   ArraySetAsSeries(rsi_15m, true);
   ArraySetAsSeries(rsi_1h, true);

   int bars = 3;

   if(CopyBuffer(handleEMA9, 0, 0, bars, ema9) < bars) return false;
   if(CopyBuffer(handleEMA21, 0, 0, bars, ema21) < bars) return false;
   if(CopyBuffer(handleEMA50, 0, 0, bars, ema50) < bars) return false;
   if(CopyBuffer(handleRSI, 0, 0, bars, rsi) < bars) return false;
   if(CopyBuffer(handleRSI_Fast, 0, 0, bars, rsi_fast) < bars) return false;
   if(CopyBuffer(handleMACD, 0, 0, bars, macd_main) < bars) return false;
   if(CopyBuffer(handleMACD, 1, 0, bars, macd_signal) < bars) return false;
   if(CopyBuffer(handleADX, 0, 0, bars, adx) < bars) return false;
   if(CopyBuffer(handleADX, 1, 0, bars, plus_di) < bars) return false;
   if(CopyBuffer(handleADX, 2, 0, bars, minus_di) < bars) return false;
   if(CopyBuffer(handleStoch, 0, 0, bars, stoch_k) < bars) return false;
   if(CopyBuffer(handleStoch, 1, 0, bars, stoch_d) < bars) return false;
   if(CopyBuffer(handleRSI_15m, 0, 0, 2, rsi_15m) < 2) return false;
   if(CopyBuffer(handleRSI_1h, 0, 0, 2, rsi_1h) < 2) return false;

   return true;
}

//+------------------------------------------------------------------+
//| Obtener volumen ratio                                              |
//+------------------------------------------------------------------+
double GetVolumeRatio()
{
   long volumes[];
   ArraySetAsSeries(volumes, true);

   if(CopyTickVolume(_Symbol, InpTimeframe, 0, 21, volumes) < 21)
      return 1.0;

   double sum = 0;
   for(int i = 1; i <= 20; i++)
      sum += (double)volumes[i];

   double avg = sum / 20.0;
   if(avg == 0) return 1.0;

   return (double)volumes[0] / avg;
}

//+------------------------------------------------------------------+
//| Obtener precio de Bollinger Bands                                  |
//+------------------------------------------------------------------+
void GetBollingerBands(double &upper, double &lower)
{
   double closes[];
   double highs[];
   double lows[];
   ArraySetAsSeries(closes, true);
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows, true);

   if(CopyClose(_Symbol, InpTimeframe, 0, 21, closes) < 21) { upper = 0; lower = 0; return; }
   if(CopyHigh(_Symbol, InpTimeframe, 0, 21, highs) < 21) { upper = 0; lower = 0; return; }
   if(CopyLow(_Symbol, InpTimeframe, 0, 21, lows) < 21) { upper = 0; lower = 0; return; }

   // Typical price y Bollinger (misma lógica que qtpylib)
   double tp_sum = 0;
   double tp_vals[];
   ArrayResize(tp_vals, 20);

   for(int i = 0; i < 20; i++)
   {
      tp_vals[i] = (highs[i] + lows[i] + closes[i]) / 3.0;
      tp_sum += tp_vals[i];
   }

   double tp_mean = tp_sum / 20.0;

   double variance = 0;
   for(int i = 0; i < 20; i++)
      variance += MathPow(tp_vals[i] - tp_mean, 2);

   double std_dev = MathSqrt(variance / 20.0);

   upper = tp_mean + 2.0 * std_dev;
   lower = tp_mean - 2.0 * std_dev;
}

//+------------------------------------------------------------------+
//| Verificar señal de entrada LONG                                    |
//+------------------------------------------------------------------+
bool CheckEntryLong()
{
   // Filtro multi-timeframe
   if(rsi_15m[0] <= 35 || rsi_15m[0] >= 70) return false;
   if(rsi_1h[0] <= 30 || rsi_1h[0] >= 75) return false;

   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double vol_ratio = GetVolumeRatio();
   double bb_upper, bb_lower;
   GetBollingerBands(bb_upper, bb_lower);

   // Condición 1: Tendencia EMA + RSI + ADX + MACD
   bool cond1 = (ema9[0] > ema21[0] && ema21[0] > ema50[0] &&
                 rsi[0] > 40 && rsi[0] < 65 &&
                 adx[0] > InpADX_Min &&
                 plus_di[0] > minus_di[0] &&
                 vol_ratio > 1.0 &&
                 macd_main[0] > macd_signal[0]);

   // Condición 2: Bollinger bounce + Stoch oversold
   bool cond2 = (close_price < bb_lower * InpBB_BuyTrigger &&
                 stoch_k[0] < 20 &&
                 rsi_fast[0] < InpRSI_BuyThreshold &&
                 vol_ratio > 0.8);

   // Condición 3: MACD crossover
   bool cond3 = (macd_main[1] <= macd_signal[1] && macd_main[0] > macd_signal[0] &&
                 close_price > ema50[0] &&
                 adx[0] > 18 &&
                 rsi[0] > 35 && rsi[0] < 60 &&
                 vol_ratio > 1.2);

   return (cond1 || cond2 || cond3);
}

//+------------------------------------------------------------------+
//| Verificar señal de entrada SHORT                                   |
//+------------------------------------------------------------------+
bool CheckEntryShort()
{
   // Filtro multi-timeframe
   if(rsi_15m[0] <= 30 || rsi_15m[0] >= 65) return false;
   if(rsi_1h[0] <= 25 || rsi_1h[0] >= 70) return false;

   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double vol_ratio = GetVolumeRatio();
   double bb_upper, bb_lower;
   GetBollingerBands(bb_upper, bb_lower);

   // Condición 1: Tendencia bajista
   bool cond1 = (ema9[0] < ema21[0] && ema21[0] < ema50[0] &&
                 rsi[0] > 35 && rsi[0] < 60 &&
                 adx[0] > InpADX_Min &&
                 minus_di[0] > plus_di[0] &&
                 vol_ratio > 1.0 &&
                 macd_main[0] < macd_signal[0]);

   // Condición 2: BB reject + Stoch overbought
   bool cond2 = (close_price > bb_upper * InpBB_SellTrigger &&
                 stoch_k[0] > 80 &&
                 rsi_fast[0] > InpRSI_SellThreshold &&
                 vol_ratio > 0.8);

   // Condición 3: MACD crossover bajista
   bool cond3 = (macd_main[1] >= macd_signal[1] && macd_main[0] < macd_signal[0] &&
                 close_price < ema50[0] &&
                 adx[0] > 18 &&
                 rsi[0] > 40 && rsi[0] < 65 &&
                 vol_ratio > 1.2);

   return (cond1 || cond2 || cond3);
}

//+------------------------------------------------------------------+
//| Verificar señal de salida LONG                                     |
//+------------------------------------------------------------------+
bool CheckExitLong()
{
   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double bb_upper, bb_lower;
   GetBollingerBands(bb_upper, bb_lower);

   bool cond1 = (rsi[0] > 72 && macd_main[0] < macd_signal[0]);
   bool cond2 = (ema9[1] >= ema21[1] && ema9[0] < ema21[0] && adx[0] > 20);
   bool cond3 = (close_price > bb_upper && stoch_k[0] > 80);

   return (cond1 || cond2 || cond3);
}

//+------------------------------------------------------------------+
//| Verificar señal de salida SHORT                                    |
//+------------------------------------------------------------------+
bool CheckExitShort()
{
   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double bb_upper, bb_lower;
   GetBollingerBands(bb_upper, bb_lower);

   bool cond1 = (rsi[0] < 28 && macd_main[0] > macd_signal[0]);
   bool cond2 = (ema9[1] <= ema21[1] && ema9[0] > ema21[0] && adx[0] > 20);
   bool cond3 = (close_price < bb_lower && stoch_k[0] < 20);

   return (cond1 || cond2 || cond3);
}

//+------------------------------------------------------------------+
//| Contar posiciones propias                                          |
//+------------------------------------------------------------------+
int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
            count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Obtener tipo de posición existente                                 |
//+------------------------------------------------------------------+
ENUM_POSITION_TYPE GetMyPositionType()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
            return posInfo.PositionType();
      }
   }
   return (ENUM_POSITION_TYPE)-1;
}

//+------------------------------------------------------------------+
//| Cerrar posiciones propias                                          |
//+------------------------------------------------------------------+
void CloseMyPositions(string reason)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
         {
            trade.PositionClose(posInfo.Ticket());
            Print("Posición cerrada: ", _Symbol, " | Razón: ", reason);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Abrir orden                                                        |
//+------------------------------------------------------------------+
bool OpenOrder(ENUM_ORDER_TYPE orderType, string comment)
{
   symInfo.Name(_Symbol);
   symInfo.RefreshRates();

   double price = (orderType == ORDER_TYPE_BUY) ? symInfo.Ask() : symInfo.Bid();
   double sl_distance = price * InpStopLossPct / 100.0;
   double tp_distance = price * InpTakeProfitPct / 100.0;
   double sl, tp;

   if(orderType == ORDER_TYPE_BUY)
   {
      sl = NormalizeDouble(price - sl_distance, _Digits);
      tp = NormalizeDouble(price + tp_distance, _Digits);
   }
   else
   {
      sl = NormalizeDouble(price + sl_distance, _Digits);
      tp = NormalizeDouble(price - tp_distance, _Digits);
   }

   string typeStr = (orderType == ORDER_TYPE_BUY) ? "BUY" : "SELL";
   Print(typeStr, " ", _Symbol, " @ ", price, " | SL: ", sl, " | TP: ", tp, " | ", comment);

   return trade.PositionOpen(_Symbol, orderType, InpLotSize, price, sl, tp, comment);
}

//+------------------------------------------------------------------+
//| Gestionar trailing stop                                            |
//+------------------------------------------------------------------+
void ManageTrailingStop()
{
   if(!InpTrailingStop) return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol || posInfo.Magic() != InpMagicNumber) continue;

      double openPrice = posInfo.PriceOpen();
      double currentSL = posInfo.StopLoss();
      double currentTP = posInfo.TakeProfit();

      if(posInfo.PositionType() == POSITION_TYPE_BUY)
      {
         double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double profitPct = (currentPrice - openPrice) / openPrice;

         if(profitPct >= InpTrailingOffset / 100.0)
         {
            double newSL = NormalizeDouble(currentPrice * (1.0 - InpTrailingPct / 100.0), _Digits);
            if(newSL > currentSL)
            {
               trade.PositionModify(posInfo.Ticket(), newSL, currentTP);
               Print("Trailing SL actualizado BUY: ", _Symbol, " -> SL=", newSL);
            }
         }

         // Custom stoploss dinámico
         double dynSL = GetDynamicStoploss(profitPct, openPrice, true);
         if(dynSL > currentSL && dynSL > 0)
         {
            trade.PositionModify(posInfo.Ticket(), NormalizeDouble(dynSL, _Digits), currentTP);
         }
      }
      else if(posInfo.PositionType() == POSITION_TYPE_SELL)
      {
         double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double profitPct = (openPrice - currentPrice) / openPrice;

         if(profitPct >= InpTrailingOffset / 100.0)
         {
            double newSL = NormalizeDouble(currentPrice * (1.0 + InpTrailingPct / 100.0), _Digits);
            if(newSL < currentSL || currentSL == 0)
            {
               trade.PositionModify(posInfo.Ticket(), newSL, currentTP);
               Print("Trailing SL actualizado SELL: ", _Symbol, " -> SL=", newSL);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Stoploss dinámico basado en profit (replica custom_stoploss)       |
//+------------------------------------------------------------------+
double GetDynamicStoploss(double profitPct, double openPrice, bool isBuy)
{
   double sl_pct;

   if(profitPct > 0.08)
      sl_pct = 0.004;
   else if(profitPct > 0.05)
      sl_pct = 0.008;
   else if(profitPct > 0.03)
      sl_pct = 0.015;
   else
      return 0; // Usar SL original

   if(isBuy)
      return openPrice * (1.0 + profitPct - sl_pct);
   else
      return openPrice * (1.0 - profitPct + sl_pct);
}

//+------------------------------------------------------------------+
//| Expert tick function                                                |
//+------------------------------------------------------------------+
void OnTick()
{
   // Solo procesar en nueva vela
   static datetime lastBarTime = 0;
   datetime currentBarTime = iTime(_Symbol, InpTimeframe, 0);
   if(currentBarTime == lastBarTime) return;
   lastBarTime = currentBarTime;

   // Obtener datos de indicadores
   if(!GetIndicatorData())
   {
      Print("Error obteniendo datos de indicadores");
      return;
   }

   int myPositions = CountMyPositions();

   // Gestionar trailing stop
   ManageTrailingStop();

   // Si hay posición, verificar señales de salida
   if(myPositions > 0)
   {
      ENUM_POSITION_TYPE posType = GetMyPositionType();

      if(posType == POSITION_TYPE_BUY && CheckExitLong())
         CloseMyPositions("exit_signal_long");
      else if(posType == POSITION_TYPE_SELL && CheckExitShort())
         CloseMyPositions("exit_signal_short");

      return;
   }

   // Si no hay posición, verificar señales de entrada
   if(myPositions >= InpMaxTrades) return;

   if(CheckEntryLong())
      OpenOrder(ORDER_TYPE_BUY, "SanateBot_entry_long");
   else if(CheckEntryShort())
      OpenOrder(ORDER_TYPE_SELL, "SanateBot_entry_short");
}

//+------------------------------------------------------------------+
//| Información en el gráfico                                          |
//+------------------------------------------------------------------+
void OnTimer()
{
   Comment(StringFormat(
      "SanateBot EA v1.0\n"
      "Símbolo: %s | TF: %s\n"
      "Posiciones: %d/%d\n"
      "RSI: %.1f | ADX: %.1f\n"
      "MACD: %.5f | Signal: %.5f\n"
      "EMA9: %.5f | EMA21: %.5f | EMA50: %.5f",
      _Symbol, EnumToString(InpTimeframe),
      CountMyPositions(), InpMaxTrades,
      rsi[0], adx[0],
      macd_main[0], macd_signal[0],
      ema9[0], ema21[0], ema50[0]
   ));
}
//+------------------------------------------------------------------+
