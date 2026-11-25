# Root cause and backend decision

The firmware state machine writes IT5570 XDATA `0x1604` bit 0 at the two
identified code sites: the source-on path sets it and `source_off()` clears it.
The boardview maps that bit to KU1 `N1 = RI1#/GPD0`, the `SNK_PD_EN_EC_R` input
power gate. That makes the bit a valid control target, but not every host EC
window is a valid way to reach it.

The initial PawnIO `LpcIO` path used SIO LDN `0x0F` SMFI address registers
`0x10/0x11/0x12`. It recognized IT5570 and returned stable `0x1604 = 0x00`,
but `old | 1` read back as `0x00`. This is evidence that the SMFI host SRAM
window is not a live GPIO write path; repeating that write is discarded.

The EC firmware family can configure dedicated I2EC through `SPCTRL2.PI2ECEN`
and `PI2ECH/PI2ECL`, yielding ports `0x681` (address high), `0x682` (address
low), and `0x683` (data). `SPCTRL1.I2ECCTRL[1:0]` controls permissions. The
Windows bridge uses the signed LpcIO module's PIO whitelist and temporarily
anchors it through inactive writable LDN `0x14`, restoring `0x30/0x60/0x61` before
exit. It never assumes that a zero permission byte means the transport is live.

The remaining hardware proof is deliberately small: read `0x200D`, read
`0x1604`, perform one guarded write with readback, hold only for the requested
test interval, and restore the original byte. If the permission bits, transport,
readback, or physical safety predicates fail, the adapter does nothing.

On FA507NV.318, the signed-LpcIO read-only bridge was exercised without
changing the EC data port. The temporary BAR anchor was restored. Direct
dedicated-port reads returned `0xFF` (not decoded), while the SIO depth-2 I2EC
sequence returned `0x00` for `0x200D`, `0x2012`, `0x2014`, `0x2015`, `0x1604`,
and known telemetry addresses. This is a transport-availability failure on
this firmware instance, so the runtime writer remains disabled; it is not
evidence that GPD0 is safe to force.

The 318 image contains one direct `XRAM[0x2012]` update at EC image offset
`0x1461c`: `MOV DPTR,#0x2012; MOVX A,@DPTR; ORL A,#0x20; MOVX @DPTR,A`.
The local register map used for this board identifies the I2EC decode enable as
bit 0, so the existing `#0x20` must not be assumed to enable I2EC. This is a
firmware-side initialization defect candidate, not a runtime write recipe. The
bit definition and the banked caller must be confirmed before any image edit.
