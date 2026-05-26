"""Tests for the tiered memory system (fur/skin/tattoo)."""

from fairyland.memory.tiered import (
    FurReaction,
    TieredMemoryState,
    compute_kernel_adjustments,
    decay_tiered_memory,
    get_fur_penalty,
    record_feedback,
    update_tattoos,
)


class TestDecay:
    def test_skin_decays_at_092(self):
        state = TieredMemoryState(skin_weights={"a": 1.0})
        decay_tiered_memory(state)
        assert abs(state.skin_weights["a"] - 0.92) < 0.001

    def test_skin_below_threshold_removed(self):
        state = TieredMemoryState(skin_weights={"a": 0.01})
        decay_tiered_memory(state)
        assert "a" not in state.skin_weights

    def test_fur_decays_at_07(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key="a", effect="cooled", strength=1.0)
        ])
        decay_tiered_memory(state)
        assert abs(state.fur_reactions[0].strength - 0.7) < 0.001

    def test_fur_below_threshold_removed(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key="a", effect="cooled", strength=0.04)
        ])
        decay_tiered_memory(state)
        assert len(state.fur_reactions) == 0

    def test_cooldown_decays_at_082(self):
        state = TieredMemoryState(cooldowns={"a": 1.0})
        decay_tiered_memory(state)
        assert abs(state.cooldowns["a"] - 0.82) < 0.001

    def test_cooldown_below_threshold_removed(self):
        state = TieredMemoryState(cooldowns={"a": 0.04})
        decay_tiered_memory(state)
        assert "a" not in state.cooldowns

    def test_fur_capped_at_12(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key=f"k{i}", effect="cooled", strength=0.5)
            for i in range(15)
        ])
        decay_tiered_memory(state)
        assert len(state.fur_reactions) <= 12


class TestFeedback:
    def test_accepted_lowers_skin(self):
        state = TieredMemoryState(skin_weights={"a": 0.5})
        record_feedback(state, "a", "accepted")
        assert state.skin_weights["a"] == 0.25

    def test_accepted_raises_cooldown(self):
        state = TieredMemoryState()
        record_feedback(state, "a", "accepted")
        assert state.cooldowns["a"] == 0.45

    def test_rejected_raises_skin(self):
        state = TieredMemoryState(skin_weights={"a": 0.0})
        record_feedback(state, "a", "rejected")
        assert state.skin_weights["a"] == 0.35

    def test_deferred_small_raise(self):
        state = TieredMemoryState(skin_weights={"a": 0.0})
        record_feedback(state, "a", "deferred")
        assert state.skin_weights["a"] == 0.12

    def test_resolved_composts(self):
        state = TieredMemoryState()
        record_feedback(state, "a", "resolved")
        assert len(state.compost_log) == 1
        assert state.compost_log[0]["reason"] == "user_resolved"

    def test_feedback_creates_fur(self):
        state = TieredMemoryState()
        record_feedback(state, "a", "accepted")
        assert len(state.fur_reactions) == 1
        assert state.fur_reactions[0].effect == "cooled"


class TestTattooUpdate:
    def test_active_key_increments(self):
        state = TieredMemoryState()
        update_tattoos(state, {"a", "b"}, cycle=1)
        assert state.tattoo_history["a"] == 1
        assert state.tattoo_history["b"] == 1

    def test_inactive_key_decrements(self):
        state = TieredMemoryState(tattoo_history={"a": 3, "b": 1})
        update_tattoos(state, {"a"}, cycle=1)
        assert state.tattoo_history["a"] == 4
        assert state.tattoo_history.get("b") is None  # was 1, -1 = 0 -> deleted

    def test_stale_key_composted(self):
        state = TieredMemoryState(
            tattoo_history={"stale": 1},
            skin_weights={"stale": 0.5},
            cooldowns={"stale": 0.3},
        )
        update_tattoos(state, set(), cycle=5)
        assert "stale" not in state.tattoo_history
        assert "stale" not in state.skin_weights
        assert "stale" not in state.cooldowns
        assert any(c["reason"] == "signal_faded" for c in state.compost_log)


class TestKernelAdjustments:
    def test_high_recurrence_raises_stress(self):
        state = TieredMemoryState(tattoo_history={"a": 5, "b": 4})
        adj = compute_kernel_adjustments(state)
        assert adj.get("stress_offset", 0) > 0

    def test_low_recurrence_lowers_stress(self):
        state = TieredMemoryState(tattoo_history={"a": 1})
        adj = compute_kernel_adjustments(state)
        assert adj.get("stress_offset", 0) < 0

    def test_fur_reactions_set_pressure_baseline(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key="a", effect="cooled", strength=0.5)
        ])
        adj = compute_kernel_adjustments(state)
        assert adj.get("pressure_baseline", 0) > 0

    def test_empty_state_minimal_adjustments(self):
        state = TieredMemoryState()
        adj = compute_kernel_adjustments(state)
        assert adj.get("stress_offset") is None
        assert adj.get("pressure_baseline") is None


class TestFurPenalty:
    def test_avoid_repeat_penalty(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key="a", effect="avoid_repeat", strength=0.5)
        ])
        assert get_fur_penalty(state, "a") > 0

    def test_no_matching_key_zero_penalty(self):
        state = TieredMemoryState(fur_reactions=[
            FurReaction(key="a", effect="avoid_repeat", strength=0.5)
        ])
        assert get_fur_penalty(state, "b") == 0.0
