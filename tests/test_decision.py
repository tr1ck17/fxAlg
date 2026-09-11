"""
unit tests for decision function
tests decision logic with manually-made candle seqs.
no calls or db
"""

import unittest
from datetime import datetime, date
from decimal import Decimal

from src.fxalg.types import Candle, Range, Direction, TriggerType
from src.fxalg.decision import (
    decide,
    detect_fvg,
    detect_excursion,
    classify_candle_position,
    check_breakout,
    check_rejection,
)

def make_candle(
        timestamp: str,
        o: str,
        h: str,
        l: str,
        c: str,
) -> Candle:
    # helper to create candles with less boilerplate
    return Candle(
        timestamp=datetime.fromisoformat(timestamp),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
    )

def make_range(high: str, low: str) -> Range:
    # helper to create range
    return Range(
        high=Decimal(high),
        low=Decimal(low),
        session_date=date(2024, 1, 15),
    )

class TestDetectFVG(unittest.TestCase):
    # tests for fvg detection
    def test_bullish_fvg(self):
        # bullish fvg: c3.low > c1.high (gap above)
        c1 = make_candle("2024-01-15T20:00:00", "95.00", "95.50", "94.80", "95.30")
        c2 = make_candle("2024-01-15T20:05:00", "95.30", "96.50", "95.20", "96.40")
        c3 = make_candle("2024-01-15T20:10:00", "96.40", "96.80", "95.60", "96.70")
        # c3.low (95.60) > c1.high (95.50) -> bullish fvg

        fvg = detect_fvg(c1, c2, c3)

        self.assertIsNotNone(fvg)
        self.assertTrue(fvg.is_bullish)

    def test_bearish_fvg(self):
        # bearish fvg: c3.high < c1.low (gap below)
        c1 = make_candle("2024-01-15T20:00:00", "95.00", "95.50", "94.80", "94.90")
        c2 = make_candle("2024-01-15T20:05:00", "94.90", "95.00", "93.50", "93.60")
        c3 = make_candle("2024-01-15T20:10:00", "93.60", "94.70", "93.40", "94.50")
        # c3.high < c1.low (94.70 < 94.80) -> bearish fvg

        fvg = detect_fvg(c1, c2, c3)

        self.assertIsNotNone(fvg)
        self.assertFalse(fvg.is_bullish)

    def test_no_fvg_touching(self):
        # no fvg when c1 and c3 exactly touch (no gap)
        c1 = make_candle("2024-01-15T20:00:00", "95.00", "95.50", "94.80", "95.30")
        c2 = make_candle("2024-01-15T20:05:00", "95.30", "96.00", "95.20", "95.90")
        c3 = make_candle("2024-01-15T20:10:00", "95.90", "96.20", "95.50", "96.10")
        # c3.low == c1.high -> NOT a gap

        fvg = detect_fvg(c1, c2, c3)

        self.assertIsNone(fvg)

    def test_no_fvg_overlapping(self): #QUESTIONABLE/NEED TO DOUBLE CHECK THIS ONE
        # no fvg when c1 and c3 overlap
        c1 = make_candle("2024-01-15T20:00:00", "95.00", "95.50", "94.80", "95.30")
        c2 = make_candle("2024-01-15T20:05:00", "95.30", "95.80", "95.10", "95.70")
        c3 = make_candle("2024-01-15T20:10:00", "95.70", "96.00", "95.40", "95.90")
        # c3.low < c1.high -> overlap

        fvg = detect_fvg(c1, c2, c3)

        self.assertIsNone(fvg)

class TestClassifyPosition(unittest.TestCase):
    # test for candle position classification
    def test_above_range(self):
        # candle entirely above range
        range_ = make_range("96.00", "95.00")
        candle = make_candle("2024-01-15T20:00:00", "96.50", "97.00", "96.20", "96.80")
        # low > range_ high

        self.assertEqual(classify_candle_position(candle, range_), "above")

    def test_below_range(self):
        # candle entirely below range
        range_ = make_range("96.00", "95.00")
        candle = make_candle("2024-01-15T20:00:00", "94.50", "94.90", "94.20", "94.80")
        # high < range_low

        self.assertEqual(classify_candle_position(candle, range_), "below")

    def test_inside_range(self):
        # candle entirely isnide range
        range_ = make_range("96.00", "95.00")
        candle = make_candle("2024-01-15T20:00:00", "95.20", "95.80", "95.10", "95.70")
        # low >= range_low AND high <= range_high

        self.assertEqual(classify_candle_position(candle, range_), "inside")

    def test_spanning_range(self):
        # candle spans across range boundary
        range_ = make_range("96.00", "95.00")
        candle = make_candle("2024-01-15T20:00:00", "95.50", "96.50", "95.20", "96.30")
        # low (95.20) inside, high (96.50) above → spanning

        self.assertEqual(classify_candle_position(candle, range_), "spanning")

class TestDetectExcursion(unittest.TestCase):
    # tests for excursion detection
    def test_excursion_above(self):
        # detects excursion above range_high
        range_ = make_range("96.00", "95.00")
        candles = [
            make_candle("2024-01-15T20:00:00", "95.50", "95.80", "95.40", "95.70"),
            make_candle("2024-01-15T20:05:00", "96.10", "96.50", "96.05", "96.40"),  # Both O and C > 96
            make_candle("2024-01-15T20:10:00", "96.30", "96.60", "96.20", "96.50"),
        ]

        excursion = detect_excursion(candles, range_)

        self.assertTrue(excursion.above_range_high)
        self.assertFalse(excursion.below_range_low)

    def test_excursion_below(self):
        # detects excursion below range_low
        range_ = make_range("96.00", "95.00")
        candles = [
            make_candle("2024-01-15T20:00:00", "95.50", "95.80", "95.40", "95.60"),
            make_candle("2024-01-15T20:05:00", "94.80", "94.95", "94.50", "94.70"),  # Both O and C < 95
        ]

        excursion = detect_excursion(candles, range_)

        self.assertFalse(excursion.above_range_high)
        self.assertTrue(excursion.below_range_low)

    def test_wick_only_not_excursion(self):
        # wick beyond level doesn't count as excursion
        range_ = make_range("96.00", "95.00")
        candles = [
            # High wick above range, but open and close inside
            make_candle("2024-01-15T20:00:00", "95.50", "96.50", "95.40", "95.80"),      
        ]

        excursion = detect_excursion(candles, range_)

        self.assertFalse(excursion.above_range_high)
        self.assertFalse(excursion.below_range_low)

    def test_no_excursion(self):
        # no excursion when all candles stay in range
        range_ = make_range("96.00", "95.00")
        candles = [
            make_candle("2024-01-15T20:00:00", "95.50", "95.80", "95.40", "95.70"),
            make_candle("2024-01-15T20:05:00", "95.70", "95.90", "95.50", "95.60"),
        ]

        excursion = detect_excursion(candles, range_)

        self.assertFalse(excursion.above_range_high)
        self.assertFalse(excursion.below_range_low)

class TestBreakoutLong(unittest.TestCase):
    # tests for bullish breakout trigger
    def test_valid_breakout_long(self):
        # valid bullish breakout: mid opens at/below range_high, closes above
        range_ = make_range("96.00", "95.00")
        # R = 1.00
        
        # fvg candles for bullish breakout
        c1 = make_candle("2024-01-15T20:00:00", "95.80", "96.00", "95.70", "95.90")
        c2 = make_candle("2024-01-15T20:05:00", "96.00", "96.80", "95.90", "96.70")
        c3 = make_candle("2024-01-15T20:10:00", "96.70", "97.00", "96.10", "96.90")
        # c3.low > c1.high -> bullish fvg
        # mid.open <= range_high
        # mid.close > range_high

        fvg = detect_fvg(c1, c2, c3)
        signal = check_breakout(fvg, range_)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, Direction.LONG)
        self.assertEqual(signal.trigger_type, TriggerType.BREAKOUT)
        self.assertEqual(signal.notional_entry, Decimal("96.00"))
        # stop = range_low - 0.1R = 95.00 - 0.10 = 94.90
        self.assertEqual(signal.stop, Decimal("94.90"))
        # notional risk = 1.1R = 1.10
        self.assertEqual(signal.notional_risk_distance, Decimal("1.10"))
        # target = entry + 2 * 1.1R = 96.00 + 2.20 = 98.20
        self.assertEqual(signal.target, Decimal("98.20"))

    def test_breakout_rejected_when_open_above_level(self):
        # no breakout if mid.open > range_high
        range_ = make_range("96.00", "95.00")

        c1 = make_candle("2024-01-15T20:00:00", "96.20", "96.50", "96.10", "96.40")
        c2 = make_candle("2024-01-15T20:05:00", "96.50", "97.20", "96.40", "97.10")  # open=96.50 > 96
        c3 = make_candle("2024-01-15T20:10:00", "97.10", "97.40", "96.60", "97.30")

        fvg = detect_fvg(c1, c2, c3)
        self.assertIsNotNone(fvg)   # fvg exists

        signal = check_breakout(fvg, range_)
        self.assertIsNone(signal)   # but no breakout trigger

class TestBreakoutShort(unittest.TestCase):
    # tests for bearish breakout trigger
    def test_valid_breakout_short(self):
        # valid bearish breakout: mid opens at/above range_low, closes below
        range_ = make_range("96.00", "95.00")
        # R = 1.00

        c1 = make_candle("2024-01-15T20:00:00", "95.20", "95.30", "95.00", "95.10")
        c2 = make_candle("2024-01-15T20:05:00", "95.00", "95.10", "94.30", "94.40")  # open=95, close=94.40
        c3 = make_candle("2024-01-15T20:10:00", "94.40", "94.90", "94.20", "94.50")
        # c3.high < c1.low -> bearish FVG
        # mid.open >= range_low
        # mid.close < range_low

        fvg = detect_fvg(c1, c2, c3)
        signal = check_breakout(fvg, range_)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, Direction.SHORT)
        self.assertEqual(signal.trigger_type, TriggerType.BREAKOUT)
        self.assertEqual(signal.notional_entry, Decimal("95.00"))
        # stop = range_high + 0.1R = 96.00 + 0.10 = 96.10
        self.assertEqual(signal.stop, Decimal("96.10"))
        # target = entry - 2 * 1.1R = 95.00 - 2.20 = 92.80
        self.assertEqual(signal.target, Decimal("92.80"))

class TestRejectionShort(unittest.TestCase):
    # tests for bearish rejection trigger
    def test_valid_rejection_short(self):
        # valid bearish rejection after excursion above range_high
        range_ = make_range("96.00", "95.00")
        # R = 1.00

        # prior excursion above
        prior = [
            make_candle("2024-01-15T20:00:00", "96.20", "96.50", "96.10", "96.40"), # 0 and C > 96
        ]

        # fvg candles for rejection back into range
        c1 = make_candle("2024-01-15T20:05:00", "96.30", "96.40", "96.00", "96.10")
        c2 = make_candle("2024-01-15T20:10:00", "96.00", "96.10", "95.40", "95.50")  # open=96, close=95.50
        c3 = make_candle("2024-01-15T20:15:00", "95.50", "95.90", "95.30", "95.70")
        # c3.high < c1.low -> bearish FVG
        # mid.open >= range_high
        # mid.close < range_high

        fvg = detect_fvg(c1, c2, c3)
        excursion = detect_excursion(prior, range_)
        signal = check_rejection(fvg, range_, excursion)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, Direction.SHORT)
        self.assertEqual(signal.trigger_type, TriggerType.REJECTION)
        self.assertEqual(signal.notional_entry, Decimal("96.00"))
        # stop = range_high + 1.0R = 96.00 + 1.00 = 97.00
        self.assertEqual(signal.stop, Decimal("97.00"))
        # notional risk = 1.0R = 1.00
        self.assertEqual(signal.notional_risk_distance, Decimal("1.00"))
        # target = entry - 2 * 1.0R = 96.00 - 2.00 = 94.00
        self.assertEqual(signal.target, Decimal("94.00"))

    def test_rejection_requires_excursion(self):
        # no rejection signal without prior excursion
        range_ = make_range("96.00", "95.00")

        prior = []  # no prior candles, no excursion

        c1 = make_candle("2024-01-15T20:05:00", "96.30", "96.40", "96.00", "96.10")
        c2 = make_candle("2024-01-15T20:10:00", "96.00", "96.10", "95.40", "95.50")
        c3 = make_candle("2024-01-15T20:15:00", "95.50", "95.90", "95.30", "95.70")

        fvg = detect_fvg(c1, c2, c3)
        excursion = detect_excursion(prior, range_)
        signal = check_rejection(fvg, range_, excursion)

        self.assertIsNone(signal)

class TestRejectionLong(unittest.TestCase):
    # tests for bullish rejection trigger
    def test_valid_rejection_long(self):
        # valid bullish rejection after excursion below range_low
        range_ = make_range("96.00", "95.00")

        prior = [
            make_candle("2024-01-15T20:00:00", "94.80", "94.95", "94.50", "94.60"),     # O and C < 95
        ]

        c1 = make_candle("2024-01-15T20:05:00", "94.70", "95.00", "94.60", "94.90")
        c2 = make_candle("2024-01-15T20:10:00", "95.00", "95.60", "94.90", "95.50")  # open=95, close=95.50
        c3 = make_candle("2024-01-15T20:15:00", "95.50", "95.80", "95.10", "95.70")
        # c3.low > c1.high -> bullish FVG
        # mid.open <= range_low
        # mid.close > range_low

        fvg = detect_fvg(c1, c2, c3)
        excursion = detect_excursion(prior, range_)
        signal = check_rejection(fvg, range_, excursion)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, Direction.LONG)
        self.assertEqual(signal.trigger_type, TriggerType.REJECTION)
        self.assertEqual(signal.notional_entry, Decimal("95.00"))
        # stop = range_low - 1.0R = 95.00 - 1.00 = 94.00
        self.assertEqual(signal.stop, Decimal("94.00"))
        # target = entry + 2 * 1.0R = 95.00 + 2.00 = 97.00
        self.assertEqual(signal.target, Decimal("97.00"))

class TestDecideIntegration(unittest.TestCase):
    # integration test for the main decide() function
    def test_returns_none_witj_fewer_than_3_candles(self):
        # need at least 3 candles for fvg detection
        range_ = make_range("96.00", "95.00")
        candles = [
            make_candle("2024-01-15T20:00:00", "95.50", "95.80", "95.40", "95.70"),
            make_candle("2024-01-15T20:05:00", "95.70", "96.00", "95.60", "95.90"),
        ]

        signal = decide(candles, range_)

        self.assertIsNone(signal)

    def test_breakout_signal_from_decide(self):
        # decide() returns breakout signal correctly
        range_ = make_range("96.00", "95.00")

        candles = [
            make_candle("2024-01-15T20:00:00", "95.80", "96.00", "95.70", "95.90"),
            make_candle("2024-01-15T20:05:00", "96.00", "96.80", "95.90", "96.70"),
            make_candle("2024-01-15T20:10:00", "96.70", "97.00", "96.10", "96.90"),
        ]

        signal = decide(candles, range_)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, Direction.LONG)
        self.assertEqual(signal.trigger_type, TriggerType.BREAKOUT)

    def test_no_signal_without_fvg(self):
        # decide() returns None when no fvg forms
        range_ = make_range("96.00", "95.00")

        candles = [
            make_candle("2024-01-15T20:00:00", "95.50", "95.80", "95.40", "95.70"),
            make_candle("2024-01-15T20:05:00", "95.70", "95.90", "95.60", "95.80"),
            make_candle("2024-01-15T20:10:00", "95.80", "96.00", "95.70", "95.90"),
        ]

        signal = decide(candles, range_)

        self.assertIsNone(signal)

    def test_candle_1_position_included(self):
        # every signal includes candle_1_position
        range_ = make_range("96.00", "95.00")

        candles = [
            make_candle("2024-01-15T20:00:00", "95.80", "96.00", "95.70", "95.90"),  # inside range
            make_candle("2024-01-15T20:05:00", "96.00", "96.80", "95.90", "96.70"),
            make_candle("2024-01-15T20:10:00", "96.70", "97.00", "96.10", "96.90"),
        ]

        signal = decide(candles, range_)

        self.assertIsNotNone(signal)
        self.assertIn(signal.candle_1_position, ["above", "below", "inside", "spanning"])

    def test_pure_function_same_inputs_same_output(self):
        # same inputs always produce same output
        range_ = make_range("96.00", "95.00")

        candles = [
            make_candle("2024-01-15T20:00:00", "95.80", "96.00", "95.70", "95.90"),
            make_candle("2024-01-15T20:05:00", "96.00", "96.80", "95.90", "96.70"),
            make_candle("2024-01-15T20:10:00", "96.70", "97.00", "96.10", "96.90"),
        ]

        signal1 = decide(candles, range_)
        signal2 = decide(candles, range_)

        self.assertEqual(signal1, signal2)

if __name__ == "__main__":
    unittest.main()