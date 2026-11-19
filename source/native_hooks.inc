// Softkey frame render: intercept only its own virtual render slot.
{0x4a04d058,0,0,false,0x4a0ed188},
// Resource lookup diagnostics: single ARM instructions; replayed by guest interpreter.
{0x4a090df4,0x4a090df4,4,true,0},
{0x4a090e2c,0x4a090e2c,4,true,0},

// Keypad state enter/leave: observe virtual calls without displacing instructions.
{0x4a099ee4,0,0,false,0x4a0f21c8},
{0x4a099c88,0,0,false,0x4a0f21cc},
