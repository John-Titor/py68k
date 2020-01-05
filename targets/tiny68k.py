
def configure(args):
	import emulator
	emu = emulator.Emulator(args, memory_size=(16 * 1024 - 32))

	import device
	emu.add_device(args, device.root_device, 0xff8000)

	import deviceDUART
	emu.add_device(args,
	               deviceDUART.DUART,
	               address=0xfff000,
	               interrupt=emulator.M68K_IRQ_2)

	import deviceCF
	emu.add_device(args,
	               deviceCF.CompactFlash,
	               address=0xffe000)

	return emu