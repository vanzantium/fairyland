"""Tests for the Beacon & Handshake mesh."""

from fairyland.beacon.mesh import (
    BeaconState,
    HandshakeDecision,
    broadcast,
    handshake,
)
from fairyland.engine.state import KernelState


class TestBroadcast:
    def test_broadcast_from_kernel(self):
        k = KernelState(stress=0.3, coherence=0.8, reserve=0.9, pressure=0.6, temperature=0.5, debt=0.1)
        b = broadcast(k, scar=0.15)
        assert b.skin_tightness == 0.3
        assert abs(b.skin_noise - 0.2) < 0.01
        assert b.reserve_surface == 0.9
        assert b.scar_signature == 0.15


class TestHandshake:
    def test_noise_shield(self):
        a = BeaconState(skin_noise=0.8, scar_signature=0.5, reserve_surface=0.5)
        b = BeaconState(skin_noise=0.9, scar_signature=0.5, reserve_surface=0.5)
        assert handshake(a, b) == HandshakeDecision.IGNORE

    def test_priority_handshake(self):
        a = BeaconState(skin_noise=0.2, scar_signature=0.5, reserve_surface=0.6)
        b = BeaconState(skin_noise=0.2, scar_signature=0.6, reserve_surface=0.7)
        assert handshake(a, b) == HandshakeDecision.PRIORITY_HANDSHAKE

    def test_mismatch_ignored(self):
        a = BeaconState(skin_noise=0.2, scar_signature=0.0, reserve_surface=0.5)
        b = BeaconState(skin_noise=0.2, scar_signature=0.9, reserve_surface=0.5)
        assert handshake(a, b) == HandshakeDecision.IGNORE

    def test_standard_handshake_default(self):
        a = BeaconState(skin_noise=0.2, scar_signature=0.3, reserve_surface=0.5)
        b = BeaconState(skin_noise=0.2, scar_signature=0.6, reserve_surface=0.8)
        assert handshake(a, b) == HandshakeDecision.STANDARD_HANDSHAKE
