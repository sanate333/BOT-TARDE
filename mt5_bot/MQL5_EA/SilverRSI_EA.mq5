//+------------------------------------------------------------------+
//|                                                SilverRSI_EA.mq5  |
//|                      Silver RSI + EMA50 Trading Bot              |
//|        Estrategia: RSI oversold/overbought + EMA50 trend filter  |
//+------------------------------------------------------------------+
#property copyright "SanateBot - Silver"
#property version   "1.00"
#property description "Bot automático para Silver (XAGUSD)"
#property description "Compra: RSI < 30 + Precio > EMA50"
#property description "Vende: RSI > 70"
#property description "SL: 50 pips | TP: 100 pips"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//--- Parámetros de entrada
input group "=== CONFIGURACIÓN GENERAL ==="
input double   InpLotSize       = 0.01;       // Tamaño del lote
input int      InpMagicNumber   = 234100;     // Número mágico (identificador)
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5; // Timeframe

input group "=== PARÁMETROS RSI ==="
input int      InpRSI_Period    = 14;         // RSI - Período
input int      InpRSI_BuyLevel  = 30;         // RSI - Nivel de compra (oversold)
input int      InpRSI_SellLevel = 70;         // RSI - Nivel de venta (overbought)

input group "=== PARÁMETROS EMA ==="
input int      InpEMA_Period    = 50;         // EMA - Período (filtro de tendencia)

input group "=== GESTIÓN DE RIESGO ==="
input int      InpStopLoss      = 50;         // Stop Loss (pips)
input int      InpTakeProfit    = 100;        // Take Profit (pips)
input int      InpMaxTrades     = 1;          // Máximo de operaciones abiertas
input bool     InpTrailingStop  = true;       // Activar Trailing Stop
input int      InpTrailingPips  = 30;         // Trailing Stop (pips)
input int      InpTrailingStart = 50;         // Trailing Start (pips de ganancia)

//--- Handles de indicadores
int handleRSI;
int handleEMA;

//--- Buffers
double rsi[];
double ema[];

//--- Objetos de trading
CTrade trade;
CPositionInfo posInfo;
CSymbolInfo symInfo;

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   // Verificar que estamos en Silver
   string symbol = _Symbol;
   if(StringFind(symbol, "XAG") < 0 && StringFind(symbol, "Silver") < 0 &&
      StringFind(symbol, "SILVER") < 0 && StringFind(symbol, "xag") < 0)
   {
      Print("ADVERTENCIA: Este EA está diseñado para Silver (XAGUSD).");
      Print("Símbolo actual: ", symbol, " - El EA funcionará pero está optimizado para Silver.");
   }

   // Configurar objeto de trading
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(30);  // Silver tiene más volatilidad
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // Inicializar indicadores
   handleRSI = iRSI(_Symbol, InpTimeframe, InpRSI_Period, PRICE_CLOSE);
   handleEMA = iMA(_Symbol, InpTimeframe, InpEMA_Period, 0, MODE_EMA, PRICE_CLOSE);

   // Verificar handles
   if(handleRSI == INVALID_HANDLE || handleEMA == INVALID_HANDLE)
   {
      Print("Error al crear indicadores: ", GetLastError());
      return INIT_FAILED;
   }

   // Configurar arrays como series
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(ema, true);

   Print("================================================");
   Print("Silver RSI Bot inicializado correctamente");
   Print("Símbolo: ", _Symbol, " | Timeframe: ", EnumToString(InpTimeframe));
   Print("RSI(", InpRSI_Period, ") | EMA(", InpEMA_Period, ")");
   Print("Compra: RSI < ", InpRSI_BuyLevel, " + Precio > EMA", InpEMA_Period);
   Print("Venta: RSI > ", InpRSI_SellLevel);
   Print("Lote: ", InpLotSize, " | SL: ", InpStopLoss, " pips | TP: ", InpTakeProfit, " pips");
   Print("================================================");

   // Timer para actualizar info en pantalla
   EventSetTimer(1);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(handleRSI);
   IndicatorRelease(handleEMA);
   EventKillTimer();
   Comment("");
   Print("Silver RSI Bot detenido");
}

//+------------------------------------------------------------------+
//| Obtener datos de indicadores                                       |
//+------------------------------------------------------------------+
bool GetIndicatorData()
{
   if(CopyBuffer(handleRSI, 0, 0, 3, rsi) < 3) return false;
   if(CopyBuffer(handleEMA, 0, 0, 3, ema) < 3) return false;
   return true;
}

//+------------------------------------------------------------------+
//| Convertir pips a precio según el símbolo                          |
//+------------------------------------------------------------------+
double PipsToPrice(int pips)
{
   // Silver (XAGUSD) normalmente tiene 2-3 decimales
   // 1 pip en silver = 0.01 (para brokers con 2 decimales)
   // 1 pip en silver = 0.001 (para brokers con 3 decimales)
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // Para Silver: ajustar según decimales del broker
   if(digits == 2)
      return pips * 0.01;      // 50 pips = 0.50
   else if(digits == 3)
      return pips * 0.01;      // 50 pips = 0.50 (pipettes)
   else
      return pips * point * 10; // Genérico
}

//+------------------------------------------------------------------+
//| Verificar señal de compra (LONG)                                  |
//|   - RSI por debajo del nivel de sobreventa (< 30)                 |
//|   - Precio por encima de la EMA 50 (tendencia alcista)            |
//+------------------------------------------------------------------+
bool CheckBuySignal()
{
   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   // RSI en zona de sobreventa Y precio en tendencia alcista
   bool rsi_oversold = (rsi[1] < InpRSI_BuyLevel);  // Usar vela cerrada [1]
   bool price_above_ema = (close_price > ema[0]);

   if(rsi_oversold && price_above_ema)
   {
      Print("SEÑAL DE COMPRA: RSI(", rsi[1], ") < ", InpRSI_BuyLevel,
            " | Precio(", close_price, ") > EMA50(", ema[0], ")");
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Verificar señal de venta (cerrar LONG)                            |
//|   - RSI por encima del nivel de sobrecompra (> 70)                |
//+------------------------------------------------------------------+
bool CheckSellSignal()
{
   // RSI en zona de sobrecompra - señal de salida
   bool rsi_overbought = (rsi[1] > InpRSI_SellLevel);  // Usar vela cerrada [1]

   if(rsi_overbought)
   {
      Print("SEÑAL DE VENTA: RSI(", rsi[1], ") > ", InpRSI_SellLevel);
      return true;
   }

   return false;
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
//| Verificar si hay posición abierta de tipo específico               |
//+------------------------------------------------------------------+
bool HasPosition(ENUM_POSITION_TYPE posType)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol &&
            posInfo.Magic() == InpMagicNumber &&
            posInfo.PositionType() == posType)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Cerrar todas las posiciones propias                                |
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
            Print("Posición cerrada: ", _Symbol,
                  " | Ticket: ", posInfo.Ticket(),
                  " | Profit: ", posInfo.Profit(),
                  " | Razón: ", reason);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Abrir orden de compra                                             |
//+------------------------------------------------------------------+
bool OpenBuy()
{
   symInfo.Name(_Symbol);
   symInfo.RefreshRates();

   double price = symInfo.Ask();
   double pip_value = PipsToPrice(1);
   double sl = NormalizeDouble(price - InpStopLoss * pip_value, _Digits);
   double tp = NormalizeDouble(price + InpTakeProfit * pip_value, _Digits);

   Print("ABRIENDO BUY: ", _Symbol,
         " @ ", price,
         " | SL: ", sl, " (", InpStopLoss, " pips)",
         " | TP: ", tp, " (", InpTakeProfit, " pips)",
         " | Lote: ", InpLotSize);

   bool result = trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, InpLotSize, price, sl, tp,
                                     "SilverRSI_Buy");

   if(!result)
   {
      Print("Error abriendo BUY: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
   }

   return result;
}

//+------------------------------------------------------------------+
//| Abrir orden de venta (short)                                      |
//+------------------------------------------------------------------+
bool OpenSell()
{
   symInfo.Name(_Symbol);
   symInfo.RefreshRates();

   double price = symInfo.Bid();
   double pip_value = PipsToPrice(1);
   double sl = NormalizeDouble(price + InpStopLoss * pip_value, _Digits);
   double tp = NormalizeDouble(price - InpTakeProfit * pip_value, _Digits);

   Print("ABRIENDO SELL: ", _Symbol,
         " @ ", price,
         " | SL: ", sl, " (", InpStopLoss, " pips)",
         " | TP: ", tp, " (", InpTakeProfit, " pips)",
         " | Lote: ", InpLotSize);

   bool result = trade.PositionOpen(_Symbol, ORDER_TYPE_SELL, InpLotSize, price, sl, tp,
                                     "SilverRSI_Sell");

   if(!result)
   {
      Print("Error abriendo SELL: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
   }

   return result;
}

//+------------------------------------------------------------------+
//| Gestionar trailing stop                                            |
//+------------------------------------------------------------------+
void ManageTrailingStop()
{
   if(!InpTrailingStop) return;

   double pip_value = PipsToPrice(1);

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
         double profitPips = (currentPrice - openPrice) / pip_value;

         // Solo activar trailing cuando el profit supera el umbral
         if(profitPips >= InpTrailingStart)
         {
            double newSL = NormalizeDouble(currentPrice - InpTrailingPips * pip_value, _Digits);
            if(newSL > currentSL)
            {
               trade.PositionModify(posInfo.Ticket(), newSL, currentTP);
               Print("Trailing SL BUY actualizado: ", _Symbol,
                     " -> SL=", newSL, " | Profit: ", profitPips, " pips");
            }
         }
      }
      else if(posInfo.PositionType() == POSITION_TYPE_SELL)
      {
         double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double profitPips = (openPrice - currentPrice) / pip_value;

         if(profitPips >= InpTrailingStart)
         {
            double newSL = NormalizeDouble(currentPrice + InpTrailingPips * pip_value, _Digits);
            if(newSL < currentSL || currentSL == 0)
            {
               trade.PositionModify(posInfo.Ticket(), newSL, currentTP);
               Print("Trailing SL SELL actualizado: ", _Symbol,
                     " -> SL=", newSL, " | Profit: ", profitPips, " pips");
            }
         }
      }
   }
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

   // Gestionar trailing stop en cada nueva vela
   ManageTrailingStop();

   int myPositions = CountMyPositions();

   // --- Si hay posiciones abiertas, verificar señal de cierre ---
   if(myPositions > 0)
   {
      // Si tenemos un BUY abierto y RSI > 70, cerrar
      if(HasPosition(POSITION_TYPE_BUY) && CheckSellSignal())
      {
         CloseMyPositions("RSI_overbought_exit");
      }

      // Si tenemos un SELL abierto y RSI < 30, cerrar
      if(HasPosition(POSITION_TYPE_SELL) && CheckBuySignal())
      {
         CloseMyPositions("RSI_oversold_exit");
      }

      return;
   }

   // --- Si no hay posiciones, verificar señales de entrada ---
   if(myPositions >= InpMaxTrades) return;

   // Señal de COMPRA: RSI < 30 + Precio > EMA50
   if(CheckBuySignal())
   {
      OpenBuy();
   }
   // Señal de VENTA (short): RSI > 70 + Precio < EMA50
   else if(rsi[1] > InpRSI_SellLevel && SymbolInfoDouble(_Symbol, SYMBOL_BID) < ema[0])
   {
      OpenSell();
   }
}

//+------------------------------------------------------------------+
//| Información en el gráfico                                          |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!GetIndicatorData()) return;

   double close_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   string trend = (close_price > ema[0]) ? "ALCISTA ▲" : "BAJISTA ▼";
   string rsi_status;
   color rsi_color;

   if(rsi[0] < InpRSI_BuyLevel)
   {
      rsi_status = "SOBREVENTA (COMPRAR)";
   }
   else if(rsi[0] > InpRSI_SellLevel)
   {
      rsi_status = "SOBRECOMPRA (VENDER)";
   }
   else
   {
      rsi_status = "NEUTRAL";
   }

   Comment(StringFormat(
      "╔══════════════════════════════════╗\n"
      "║   Silver RSI Bot v1.0           ║\n"
      "╠══════════════════════════════════╣\n"
      "║ Símbolo: %s\n"
      "║ Timeframe: %s\n"
      "║ Precio: %.5f\n"
      "╠══════════════════════════════════╣\n"
      "║ RSI(%d): %.1f  [%s]\n"
      "║ EMA(%d): %.5f\n"
      "║ Tendencia: %s\n"
      "╠══════════════════════════════════╣\n"
      "║ Posiciones: %d/%d\n"
      "║ SL: %d pips | TP: %d pips\n"
      "║ Lote: %.2f\n"
      "╠══════════════════════════════════╣\n"
      "║ Reglas:\n"
      "║  BUY:  RSI < %d + Precio > EMA%d\n"
      "║  SELL: RSI > %d + Precio < EMA%d\n"
      "║  EXIT: RSI cruza nivel opuesto\n"
      "╚══════════════════════════════════╝",
      _Symbol,
      EnumToString(InpTimeframe),
      close_price,
      InpRSI_Period, rsi[0], rsi_status,
      InpEMA_Period, ema[0],
      trend,
      CountMyPositions(), InpMaxTrades,
      InpStopLoss, InpTakeProfit,
      InpLotSize,
      InpRSI_BuyLevel, InpEMA_Period,
      InpRSI_SellLevel, InpEMA_Period
   ));
}
//+------------------------------------------------------------------+
