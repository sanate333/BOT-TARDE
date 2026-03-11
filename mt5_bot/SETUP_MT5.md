# SanateBot MT5 - Guía de Instalación

## Opción A: Bot Python (Recomendado para empezar)

### Requisitos
- Windows 10/11
- MetaTrader 5 instalado y abierto
- Python 3.10+ (Windows)

### Pasos

1. **Instalar dependencias Python** (en PowerShell):
```powershell
pip install MetaTrader5 pandas numpy
```

Para TA-Lib en Windows:
```powershell
# Descargar el wheel de: https://github.com/cgohlke/talib-build/releases
pip install TA_Lib-0.4.32-cp312-cp312-win_amd64.whl
```

2. **Configurar**:
```powershell
cd BOT-TARDE\mt5_bot
copy mt5_config.example.json mt5_config.json
```

Editar `mt5_config.json` con tus datos:
- `mt5_path`: ruta a tu terminal64.exe
- `account`: número de cuenta (ej: 104125263)
- `server`: servidor (ej: "MetaQuotes-Demo")
- `symbols`: pares de forex que quieres operar

3. **Ejecutar en modo simulación** (dry_run):
```powershell
python sanate_mt5_bot.py --config mt5_config.json
```

4. **Para trading real**, cambiar en config:
```json
"dry_run": false
```

---

## Opción B: Expert Advisor MQL5 (Corre dentro de MT5)

### Pasos

1. Copiar `MQL5_EA/SanateBot_EA.mq5` a:
```
C:\Users\TU_USUARIO\AppData\Roaming\MetaQuotes\Terminal\{ID}\MQL5\Experts\
```

O desde MT5: **File > Open Data Folder > MQL5 > Experts**

2. En MT5, compilar el EA:
   - Abrir **MetaEditor** (F4)
   - Abrir `SanateBot_EA.mq5`
   - Compilar (F7)

3. Arrastrar el EA al gráfico del par que quieras operar

4. Asegurarse de que **Algo Trading** está activado (botón en la barra de herramientas)

5. Configurar parámetros en la ventana de inputs del EA

---

## Pares de Forex Recomendados

Los pares del config son los principales con mejor liquidez:
- EURUSD, GBPUSD, USDJPY, USDCHF
- AUDUSD, USDCAD, NZDUSD, EURGBP

---

## Silver RSI Bot (XAGUSD) - NUEVO

Bot especializado para operar **Silver (Plata/XAGUSD)** con estrategia simple de RSI + EMA50.

### Estrategia
- **COMPRA**: RSI(14) < 30 + Precio > EMA(50)
- **VENTA**: RSI(14) > 70
- **Stop Loss**: 50 pips | **Take Profit**: 100 pips
- **Trailing Stop**: 30 pips (se activa a 50 pips de ganancia)

### Opción A: Bot Python para Silver

```powershell
cd BOT-TARDE\mt5_bot
# Editar silver_config.json con tus datos de cuenta
python silver_mt5_bot.py --config silver_config.json
```

### Opción B: EA MQL5 para Silver

1. Copiar `MQL5_EA/SilverRSI_EA.mq5` a la carpeta de Experts de MT5
2. Abrir MetaEditor (F4), abrir el archivo y compilar (F7)
3. Abrir gráfico de **XAGUSD**
4. Arrastrar `SilverRSI_EA` al gráfico
5. Activar **Algo Trading** (botón verde en barra de herramientas)
6. Ajustar parámetros: lote, niveles RSI, SL/TP

### Backtesting del Silver Bot

1. Presionar **Ctrl+R** para abrir el Strategy Tester
2. Seleccionar `SilverRSI_EA` como Expert
3. Seleccionar `XAGUSD` como símbolo
4. Rango de datos: mínimo 6 meses
5. Activar **Visual mode** para ver los trades en el gráfico

---

## Notas Importantes

- **Empieza SIEMPRE en cuenta demo** antes de operar con dinero real
- El bot usa la misma lógica que SanateStrategy de Freqtrade
- Los parámetros se pueden ajustar en el config/inputs del EA
- El trailing stop protege ganancias automáticamente
- Stoploss dinámico se ajusta según el nivel de profit
