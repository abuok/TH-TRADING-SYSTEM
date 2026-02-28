//+------------------------------------------------------------------+
//|                                              LiveBridgeEA.mq5    |
//|                                  Copyright 2026, PHX Trading     |
//|                                             https://phx.ai       |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, PHX Trading"
#property link      "https://phx.ai"
#property version   "1.00"
#property strict

//--- input parameters
input string   InpServerUrl = "http://localhost:8005"; // Bridge Server URL
input string   InpSecret    = "change-me-in-prod";   // Bridge Secret Key
input int      InpInterval  = 5;                    // Sync interval (seconds)

//--- global variables
datetime last_sync = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("PHX Live Bridge EA Started.");
   SyncSymbolSpecs();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("PHX Live Bridge EA Stopped.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(TimeCurrent() - last_sync < InpInterval) return;
   
   SyncQuote();
   last_sync = TimeCurrent();
}

//+------------------------------------------------------------------+
//| Sync Symbol Specifications                                       |
//+------------------------------------------------------------------+
void SyncSymbolSpecs()
{
   string symbol = _Symbol;
   double contract_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double tick_size     = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value    = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double pip_size      = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10; // Simple approx
   double min_lot       = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double lot_step      = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   string json = StringFormat(
      "{\"symbol\":\"%s\", \"contract_size\":%f, \"tick_size\":%f, \"tick_value\":%f, \"pip_size\":%f, \"min_lot\":%f, \"lot_step\":%f}",
      symbol, contract_size, tick_size, tick_value, pip_size, min_lot, lot_step
   );

   SendToBridge("/bridge/spec", json);
}

//+------------------------------------------------------------------+
//| Sync Current Quote                                               |
//+------------------------------------------------------------------+
void SyncQuote()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   
   string json = StringFormat(
      "{\"symbol\":\"%s\", \"bid\":%f, \"ask\":%f, \"ts_utc\":\"%s\"}",
      _Symbol, bid, ask, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );

   SendToBridge("/bridge/quote", json);
}

//+------------------------------------------------------------------+
//| Helper: Send HTTP Request                                        |
//+------------------------------------------------------------------+
void SendToBridge(string endpoint, string json)
{
   char data[];
   char result[];
   string result_headers;
   int res;
   
   StringToCharArray(json, data, 0, StringLen(json));
   
   string headers = "Content-Type: application/json\r\n";
   headers += "X-Bridge-Secret: " + InpSecret + "\r\n";
   
   res = WebRequest("POST", InpServerUrl + endpoint, headers, 500, data, result, result_headers);
   
   if(res == -1)
   {
      Print("Error in WebRequest: ", GetLastError());
   }
   else if(res != 200)
   {
      Print("Bridge error (", res, "): ", CharArrayToString(result));
   }
}
//+------------------------------------------------------------------+
