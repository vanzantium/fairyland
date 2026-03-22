"""Tests for micro-healing interventions."""

from fairyland.engine.healing import select_intervention
from fairyland.engine.state import KernelState, Mode


class TestInterventionSelection:
    def test_calm_system_no_intervention(self):
        k = KernelState(pressure=0.1, coherence=0.9)
        assert select_intervention(k, Mode.BUILD) is None

    def test_high_stress_gets_grounding(self):
        k = KernelState(stress=0.8, reserve=0.2, pressure=0.5, coherence=0.4)
        i = select_intervention(k, Mode.BUILD)
        assert i is not None
        assert i.name == "Grandfather's Whisper"
        assert i.domain == "grounding"

    def test_high_pressure_temp_gets_tension_release(self):
        k = KernelState(pressure=0.7, temperature=0.7, stress=0.2, reserve=0.5)
        i = select_intervention(k, Mode.BUILD)
        assert i is not None
        assert i.name == "Rat Root Decoction"

    def test_high_loss_gets_letting_go(self):
        k = KernelState(loss=0.6, pressure=0.2, coherence=0.6, stress=0.1, reserve=0.5)
        i = select_intervention(k, Mode.BUILD)
        assert i is not None
        assert i.name == "Nigredo Dust"

    def test_low_coherence_gets_focus(self):
        k = KernelState(coherence=0.3, temperature=0.6, pressure=0.2,
                        stress=0.1, reserve=0.5, loss=0.1, debt=0.1)
        i = select_intervention(k, Mode.BUILD)
        assert i is not None
        assert i.name == "Salt of Focus"

    def test_moderate_pressure_gets_redirect(self):
        k = KernelState(pressure=0.5, coherence=0.6, stress=0.1,
                        reserve=0.5, temperature=0.3, loss=0.1, debt=0.1)
        i = select_intervention(k, Mode.BUILD)
        assert i is not None
        assert i.name == "Sweetgrass Trail"

    def test_intervention_is_aesthetic_not_prescription(self):
        k = KernelState(stress=0.8, reserve=0.2, pressure=0.5, coherence=0.4)
        i = select_intervention(k, Mode.BUILD)
        # should never contain instructional language
        assert "you should" not in i.artifact.lower()
        assert "try to" not in i.artifact.lower()
