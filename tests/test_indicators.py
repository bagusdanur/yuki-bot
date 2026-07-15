import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import indicators

def test_calculate_rsi():
    prices = [10, 11, 12, 11, 13, 14, 15, 14, 16, 17, 18, 17, 16, 15]
    rsi = indicators.calculate_rsi(prices, period=7)
    assert rsi is not None
    assert 0 <= rsi <= 100

def test_calculate_macd():
    prices = [10, 11, 12, 11, 13, 14, 15, 14, 16, 17, 18, 17, 16, 15]
    macd, signal, hist = indicators.calculate_macd(prices, fast=5, slow=13, signal=4)
    assert macd is not None
    assert signal is not None
    assert hist is not None

def test_calculate_bollinger_bands():
    prices = [10, 11, 12, 11, 13, 14, 15, 14, 16, 17, 18, 17, 16, 15, 10, 11, 12, 11, 13, 14, 15]
    upper, middle, lower = indicators.calculate_bollinger_bands(prices, period=20)
    assert upper is not None
    assert middle is not None
    assert lower is not None
    assert upper > middle > lower

def test_calculate_volume_spike():
    volumes = [100, 120, 110, 105, 115, 90, 100, 110, 120, 100, 500]
    spike = indicators.calculate_volume_spike(volumes, period=10)
    assert spike is True

    volumes_normal = [100, 120, 110, 105, 115, 90, 100, 110, 120, 100, 100]
    spike_normal = indicators.calculate_volume_spike(volumes_normal, period=10)
    assert spike_normal is True
