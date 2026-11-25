from runtime_patch_core import Evidence, GPD0_MASK, GPD0_XDATA, MemoryAdapter, PatchController, PatchState


def ev(t=0.0, *, rdo=0, vbus=5000, net=0, attached=True, valid=True, fault=False, ready=True):
    return Evidence(t, attached, rdo, vbus, valid, fault, ready, net, 0)


def test_zero_rdo_is_allowed_only_with_physical_input():
    adapter = MemoryAdapter(0)
    controller = PatchController(adapter)
    assert controller.arm(ev(net=100)).allow
    assert controller.state == PatchState.ACTIVE
    assert adapter.value & GPD0_MASK

    blocked = PatchController(MemoryAdapter(0)).arm(ev(vbus=None, net=100))
    assert not blocked.allow
    assert "physical VBUS" in blocked.reasons[0]


def test_watchdog_rolls_back_when_no_net_input():
    adapter = MemoryAdapter(0)
    controller = PatchController(adapter)
    assert controller.arm(ev(net=100)).allow
    result = controller.tick(ev(t=9.0, net=0))
    assert not result.allow
    assert controller.state == PatchState.IDLE
    assert adapter.value == 0
    assert adapter.writes[-1] == (GPD0_XDATA, 0)


def test_hard_fault_rolls_back_immediately():
    adapter = MemoryAdapter(0)
    controller = PatchController(adapter)
    assert controller.arm(ev(net=100)).allow
    result = controller.tick(ev(t=1.0, net=100, fault=True))
    assert not result.allow
    assert controller.state == PatchState.IDLE
    assert adapter.value == 0


def test_unverified_adapter_never_writes():
    adapter = MemoryAdapter(0)
    adapter.verified_write = False
    controller = PatchController(adapter)
    result = controller.arm(ev(net=100))
    assert not result.allow
    assert adapter.writes == []
