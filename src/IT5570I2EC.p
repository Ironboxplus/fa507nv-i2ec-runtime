// IT5570 dedicated I2EC transport for PawnIO.
//
// The stock FA507NV EC firmware enables I2EC at base 0x0680:
//   0x681 = XRAM address high byte
//   0x682 = XRAM address low byte
//   0x683 = XRAM data
//
// This module deliberately does not guess a Super-I/O BAR.  The dedicated
// window is the only transport used by the runtime adapter.
#include <pawnio.inc>

const I2EC_ADDR_H = 0x681;
const I2EC_ADDR_L = 0x682;
const I2EC_DATA   = 0x683;
const SPCTRL1     = 0x200D;

bool:valid_address(address) {
    return address >= 0 && address <= 0xFFFF;
}

bool:valid_byte(value) {
    return value >= 0 && value <= 0xFF;
}

set_address(address) {
    io_out_byte(I2EC_ADDR_H, (address >> 8) & 0xFF);
    io_out_byte(I2EC_ADDR_L, address & 0xFF);
}

DEFINE_IOCTL_SIZED(ioctl_it5570_i2ec_read, 1, 1) {
    new address = in[0];
    if (!valid_address(address))
        return STATUS_INVALID_PARAMETER;
    set_address(address);
    out[0] = io_in_byte(I2EC_DATA);
    return STATUS_SUCCESS;
}

// Write is intentionally a separate IOCTL.  The caller must first read
// SPCTRL1 and verify I2ECCTRL[1:0] == 3, then verify the post-write value.
DEFINE_IOCTL_SIZED(ioctl_it5570_i2ec_write, 2, 0) {
    new address = in[0];
    new value = in[1];
    if (!valid_address(address) || !valid_byte(value))
        return STATUS_INVALID_PARAMETER;
    set_address(SPCTRL1);
    if ((io_in_byte(I2EC_DATA) & 0x03) != 0x03)
        return STATUS_ACCESS_DENIED;
    set_address(address);
    io_out_byte(I2EC_DATA, value);
    return STATUS_SUCCESS;
}

NTSTATUS:main() {
    new CPUArch:arch = get_arch();
    debug_print(''IT5570 I2EC module loaded, arch=%d'', _:arch);
    return STATUS_SUCCESS;
}

public NTSTATUS:unload() {
    debug_print(''IT5570 I2EC module unloaded'');
    return STATUS_SUCCESS;
}
