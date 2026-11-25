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

The EC firmware configures dedicated I2EC through `SPCTRL2.PI2ECEN` and
`PI2ECH/PI2ECL`, yielding ports `0x681` (address high), `0x682` (address low),
and `0x683` (data). `SPCTRL1.I2ECCTRL[1:0]` controls permissions. The runtime
module therefore uses I2EC directly and never guesses a Super-I/O BAR.

The remaining hardware proof is deliberately small: read `0x200D`, read
`0x1604`, perform one guarded write with readback, hold only for the requested
test interval, and restore the original byte. If the permission bits, transport,
readback, or physical safety predicates fail, the adapter does nothing.
