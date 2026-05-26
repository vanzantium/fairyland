"""Tests for the Memory Engine."""

import tempfile

from fairyland.memory.engine import MemoryEngine


class TestFrictionLogging:
    def test_below_threshold_not_logged(self):
        mem = MemoryEngine()
        mem.log(pressure=0.3, hesitation="NONE", summary="quiet moment")
        assert len(mem.state.daily_artifacts) == 0

    def test_high_pressure_logged(self):
        mem = MemoryEngine()
        mem.log(pressure=0.7, hesitation="NONE", summary="spike")
        assert len(mem.state.daily_artifacts) == 1

    def test_hesitation_logged_even_low_pressure(self):
        mem = MemoryEngine()
        mem.log(pressure=0.3, hesitation="MILD", summary="pause")
        assert len(mem.state.daily_artifacts) == 1


class TestDwellCycle:
    def test_dwell_produces_tattoo(self):
        mem = MemoryEngine()
        mem.log(pressure=0.8, hesitation="STRONG", summary="intense moment")
        mem.log(pressure=0.7, hesitation="MILD", summary="follow up")
        tattoo = mem.dwell()
        assert tattoo is not None
        assert "scar=" in tattoo

    def test_dwell_clears_artifacts(self):
        mem = MemoryEngine()
        mem.log(pressure=0.9, hesitation="STRONG", summary="boom")
        mem.dwell()
        assert len(mem.state.daily_artifacts) == 0

    def test_dwell_increases_scar(self):
        mem = MemoryEngine()
        mem.log(pressure=0.8, hesitation="NONE", summary="load")
        mem.dwell()
        assert mem.state.scar_signature > 0

    def test_dwell_empty_returns_none(self):
        mem = MemoryEngine()
        assert mem.dwell() is None

    def test_tattoo_persisted_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = MemoryEngine(tattoo_dir=tmpdir)
            mem.log(pressure=0.8, hesitation="STRONG", summary="mark")
            mem.dwell()
            from pathlib import Path
            tattoos = list(Path(tmpdir).glob("*.tattoo"))
            assert len(tattoos) == 1


class TestBurnSession:
    def test_burn_clears_artifacts(self):
        mem = MemoryEngine()
        mem.log(pressure=0.9, hesitation="STRONG", summary="data")
        mem.burn_session()
        assert len(mem.state.daily_artifacts) == 0
