import time
import argparse
from session_manager import SessionManager
from signal_generator import SignalGenerator
from signal_scorer import SignalScorer
from risk_engine import RiskEngine
from journal_service import JournalingService
from replay_engine import ReplayEngine

def run_trading_desk(iterations: int = 5, delay: int = 2):
    print("=== Trading Desk System V1 (Safety + Scope Rules) ===")
    print("Timezone: Africa/Nairobi (EAT)")
    print(f"Current Time: {SessionManager.get_current_time_eat()}")
    print("-" * 50)

    for i in range(iterations):
        if not SessionManager.is_in_session():
            print("Outside trading sessions. Sleeping...")
            break

        symbol = "XAUUSD" if i % 2 == 0 else "GBPJPY"
        
        try:
            # 1. Generate Signal
            signal = SignalGenerator.generate_signal(symbol)
            
            # 2. Score Signal
            score = SignalScorer.score_signal(signal)
            
            # 3. Evaluate Risk
            risk = RiskEngine.evaluate_risk(signal, score)
            
            # 4. Journal Decision
            JournalingService.log_entry(signal, score, risk)
            
        except Exception as e:
            print(f"Error processing signal: {e}")

        time.sleep(delay)

    print("-" * 50)
    print("Forensic log written to trading_journal.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trading Desk CLI V1")
    parser.add_argument("--iter", type=int, default=5, help="Number of iterations")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between signals")
    parser.add_argument("--replay-file", type=str, help="Path to historical signals JSON for replay")
    args = parser.parse_args()
    
    if args.replay_file:
        ReplayEngine.run_replay(args.replay_file, args.delay)
    else:
        run_trading_desk(args.iter, args.delay)
