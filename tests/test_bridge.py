"""Tests for the PipV0 <-> Fairyland bridge."""

import json
import tempfile

from fairyland.bridge import (
    GovernorState,
    PipThermal,
    SessionFrictionSummary,
    extract_session_friction,
    friction_to_pip_events,
    governor_to_reveal_speed,
    load_governor_state,
    load_pip_thermal,
    load_tiered_memory,
    save_tiered_memory,
    seed_kernel_from_pip,
)
from fairyland.engine.state import KernelState
from fairyland.memory.tiered import FurReaction, TieredMemoryState


class TestPipThermalToKernel:
    def test_seed_adjusts_coherence(self):
        kernel = KernelState()
        thermal = PipThermal(coherence=0.3, pressure=0.0, groove=0.5)
        original_coherence = kernel.coherence
        seed_kernel_from_pip(kernel, thermal)
        assert kernel.coherence < original_coherence

    def test_seed_adjusts_groove(self):
        kernel = KernelState()
        thermal = PipThermal(groove=0.9)
        seed_kernel_from_pip(kernel, thermal)
        assert kernel.groove > 0.5

    def test_seed_raises_pressure_from_pip(self):
        kernel = KernelState()
        thermal = PipThermal(pressure=0.8)
        seed_kernel_from_pip(kernel, thermal)
        assert kernel.pressure > 0

    def test_seed_respects_integration_debt(self):
        kernel = KernelState()
        thermal = PipThermal(integration_debt=0.9)
        seed_kernel_from_pip(kernel, thermal)
        assert kernel.debt > 0

    def test_seed_with_tiered_memory(self):
        kernel = KernelState()
        thermal = PipThermal()
        tiered = TieredMemoryState(
            tattoo_history={"a": 5, "b": 5},
            fur_reactions=[FurReaction(key="x", effect="cooled", strength=0.8)],
        )
        seed_kernel_from_pip(kernel, thermal, tiered)
        assert kernel.stress > 0  # high recurrence -> stress offset

    def test_neutral_thermal_minimal_change(self):
        kernel = KernelState()
        original = KernelState()
        thermal = PipThermal()
        seed_kernel_from_pip(kernel, thermal)
        assert abs(kernel.coherence - original.coherence) < 0.2
        assert abs(kernel.groove - original.groove) < 0.2


class TestGovernorRevealSpeed:
    def test_build_mode(self):
        gov = GovernorState(mode="BUILD")
        assert governor_to_reveal_speed(gov) == 0.7

    def test_shed_mode(self):
        gov = GovernorState(mode="SHED")
        assert governor_to_reveal_speed(gov) == 0.1

    def test_budget_remaining(self):
        gov = GovernorState(daily_budget=60000, daily_used=30000)
        assert gov.budget_remaining_ratio == 0.5


class TestFrictionToEvents:
    def test_converts_summary_to_events(self):
        summary = SessionFrictionSummary(
            session_id="abc",
            tick_count=50,
            avg_pressure=0.6,
            max_pressure=0.9,
            dominant_tone="cautious",
            hesitation_count=3,
            tattoo_produced=None,
            breath_overdrive_count=1,
            drift_scores={"parasocial": 0.1},
        )
        events = friction_to_pip_events(summary)
        assert len(events) == 1
        assert events[0]["app_name"] == "fairyland_session"
        assert events[0]["notifications_received"] == 3


class TestTieredMemoryPersistence:
    def test_round_trip(self):
        state = TieredMemoryState(
            tattoo_history={"a": 3, "b": 1},
            skin_weights={"a": 0.5},
            fur_reactions=[FurReaction(key="a", effect="cooled", strength=0.3)],
            cooldowns={"a": 0.4},
            cycle_count=5,
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        save_tiered_memory(state, path)
        loaded = load_tiered_memory(path)
        assert loaded.tattoo_history == {"a": 3, "b": 1}
        assert loaded.skin_weights == {"a": 0.5}
        assert len(loaded.fur_reactions) == 1
        assert loaded.fur_reactions[0].key == "a"
        assert loaded.cooldowns == {"a": 0.4}
        assert loaded.cycle_count == 5

    def test_load_missing_file(self):
        state = load_tiered_memory("/nonexistent/path.json")
        assert state.cycle_count == 0
        assert len(state.tattoo_history) == 0


class TestLoadPipThermal:
    def test_load_from_dream_result(self):
        data = {
            "thermal_state": {
                "coherence": 0.6,
                "pressure": 0.3,
                "drift": 0.1,
                "groove": 0.7,
                "integration_debt": 0.2,
                "scar": 0.15,
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name
        thermal = load_pip_thermal(path)
        assert thermal is not None
        assert thermal.coherence == 0.6
        assert thermal.groove == 0.7

    def test_load_missing_returns_none(self):
        assert load_pip_thermal("/nonexistent.json") is None


class TestLoadGovernor:
    def test_load_and_mode_detection(self):
        data = {"daily_budget_tokens": 60000, "daily_used_tokens": 50000}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name
        gov = load_governor_state(path)
        assert gov.mode == "DWELL"  # 10000/60000 = 16.7% remaining

    def test_load_fresh_is_build(self):
        data = {"daily_budget_tokens": 60000, "daily_used_tokens": 0}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(data, f)
            path = f.name
        gov = load_governor_state(path)
        assert gov.mode == "BUILD"
