import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import ryubot_system
import trade_logger

def test_cek_trailing_stop():
    # Test Fixed Stop Loss
    grid = {
        "positions": [
            {"buy_price": 3000, "amount": 0.01}
        ]
    }
    
    price_sl = 3000 * (1 + config.STOP_LOSS_PCT / 100) - 1 # Drop below SL
    is_stop, pct, type_sl = ryubot_system.cek_trailing_stop(grid, price_sl)
    assert is_stop is True
    assert type_sl == "STOP LOSS"
    
    # Test Trailing Stop
    grid["positions"][0]["highest_pnl"] = 0.6 # Reached +0.6%
    price_trailing = 3000 * 1.001 # Dropped to +0.1%
    is_stop, pct, type_sl = ryubot_system.cek_trailing_stop(grid, price_trailing)
    assert is_stop is True
    assert type_sl == "TRAILING STOP"

    # Test Break Even
    grid["positions"][0]["highest_pnl"] = 0.4 # Reached +0.4%
    price_be = 3000 * 0.999 # Dropped to -0.1%
    is_stop, pct, type_sl = ryubot_system.cek_trailing_stop(grid, price_be)
    assert is_stop is True
    assert type_sl == "BREAK-EVEN"

def test_is_daily_limit_hit(mocker):
    # Mock trade_logger.get_daily_pnl
    mocker.patch("trade_logger.get_daily_pnl", return_value=-0.6)
    assert trade_logger.is_daily_limit_hit() is True
    
    mocker.patch("trade_logger.get_daily_pnl", return_value=-0.4)
    assert trade_logger.is_daily_limit_hit() is False
