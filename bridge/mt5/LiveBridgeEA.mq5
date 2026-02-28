//+------------------------------------------------------------------+
//|                                              LiveBridgeEA.mq5    |
//|                                  Copyright 2026, PHX Trading     |
//|                                             https://phx.ai       |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, PHX Trading"
#property link      "https://phx.ai"
#property version   "2.00"
#property strict

//--- input parameters
input string   InpServerUrl = "http://localhost:8005"; // Bridge Server URL
input string   InpSecret    = "change-me-in-prod";   // Bridge Secret Key
input int      InpInterval  = 5;                    // Sync interval (seconds)
input string   InpAccountId = "ACC-001";            // Account ID

//--- global variables
datetime last_sync = 0;
datetime last_pos_sync = 0;
ulong last_deal_ticket = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("PHX Live Bridge EA v2.0 Started.");
   SyncSymbolSpecs();
   
   // Init history for OnTrade
   HistorySelect(0, TimeCurrent());
   int total = HistoryDealsTotal();
   if(total > 0)
      last_deal_ticket = HistoryDealGetTicket(total - 1);
      
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
   if(TimeCurrent() - last_sync >= InpInterval) {
       SyncQuote();
       last_sync = TimeCurrent();
   }
   
   if(TimeCurrent() - last_pos_sync >= 30) {
       SyncPositions();
       last_pos_sync = TimeCurrent();
   }
}

//+------------------------------------------------------------------+
//| Trade Event                                                      |
//+------------------------------------------------------------------+
void OnTrade()
{
   HistorySelect(TimeCurrent()-86400, TimeCurrent()+86400);
   int total = HistoryDealsTotal();
   if(total == 0) return;
   
   string json = "{\"fills\":[";
   bool added = false;
   
   for(int i = total - 1; i >= 0; i--) {
       ulong ticket = HistoryDealGetTicket(i);
       if(ticket <= last_deal_ticket) break; // Already processed
       
       long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
       long type = HistoryDealGetInteger(ticket, DEAL_TYPE);
       if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue; // Only trades
       
       string symbol = HistoryDealGetString(ticket, DEAL_SYMBOL);
       double lots = HistoryDealGetDouble(ticket, DEAL_VOLUME);
       double price = HistoryDealGetDouble(ticket, DEAL_PRICE);
       long magic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
       string comment = HistoryDealGetString(ticket, DEAL_COMMENT);
       
       string event_type = "OPEN";
       if(entry == DEAL_ENTRY_OUT) event_type = "CLOSE";
       else if(entry == DEAL_ENTRY_INOUT) event_type = "PARTIAL";
       
       string side = (type == DEAL_TYPE_BUY) ? "BUY" : "SELL";
       string ts = TimeToString(HistoryDealGetInteger(ticket, DEAL_TIME), TIME_DATE|TIME_SECONDS);
       StringReplace(ts, ".", "-"); // to ISO-ish YYYY-MM-DD HH:MI:SS
       
       // Escape JSON comment
       StringReplace(comment, "\"", "\\\"");
       
       if(added) json += ",";
       json += StringFormat("{\"broker_trade_id\":\"%d\",\"symbol\":\"%s\",\"side\":\"%s\",\"lots\":%f,\"price\":%f,\"time_utc\":\"%s\",\"time_eat\":\"%s\",\"event_type\":\"%s\",\"comment\":\"%s\",\"magic\":%d,\"account_id\":\"%s\"}", 
                            ticket, symbol, side, lots, price, ts, ts, event_type, comment, magic, InpAccountId);
       added = true;
   }
   json += "]}";
   
   if(added) {
       SendToBridge("/bridge/trades/fill", json);
       last_deal_ticket = HistoryDealGetTicket(total - 1);
   }
}

//+------------------------------------------------------------------+
//| Sync Positions                                                   |
//+------------------------------------------------------------------+
void SyncPositions()
{
   string json = "{\"snapshots\":[";
   int total = PositionsTotal();
   bool added = false;
   
   for(int i=0; i<total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      
      string pos_symbol = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      double lots = PositionGetDouble(POSITION_VOLUME);
      double price = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double pnl = PositionGetDouble(POSITION_PROFIT);
      
      string ts = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
      StringReplace(ts, ".", "-");
      
      if(added) json += ",";
      json += StringFormat("{\"position_id\":\"%d\",\"symbol\":\"%s\",\"side\":\"%s\",\"lots\":%f,\"avg_price\":%f,\"floating_pnl\":%f,\"sl\":%f,\"tp\":%f,\"updated_at_utc\":\"%s\",\"updated_at_eat\":\"%s\",\"account_id\":\"%s\"}", 
                           ticket, pos_symbol, type==POSITION_TYPE_BUY?"BUY":"SELL", lots, price, pnl, sl, tp, ts, ts, InpAccountId);
      added = true;
   }
   json += "]}";
   
   if(added) SendToBridge("/bridge/trades/positions", json);
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
   
   string ts = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   StringReplace(ts, ".", "-");
   
   string json = StringFormat(
      "{\"symbol\":\"%s\", \"bid\":%f, \"ask\":%f, \"ts_utc\":\"%s\"}",
      _Symbol, bid, ask, ts
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
   
   // Increased timeout to 1000ms as per Changlog
   res = WebRequest("POST", InpServerUrl + endpoint, headers, 1000, data, result, result_headers);
   
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
