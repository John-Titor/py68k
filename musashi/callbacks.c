/*
 * Callbacks for Musashi 4.x
 * 
 * Conditional, latency-sensitive callbacks.
 */

#include "m68k.h"

void    (*cb_pc_changed)(unsigned int new_pc);
void    (*cb_instr)(unsigned int pc);

void
set_pc_changed_callback(void (*cb)(unsigned int))
{
    cb_pc_changed = cb;
}

void
pc_changed_callback(unsigned int new_pc)
{
    if (cb_pc_changed) {
        cb_pc_changed(new_pc);
    }
}

void
set_instr_hook_callback(void (*cb)(unsigned int))
{
    cb_instr = cb;
}

void
instr_hook_callback(unsigned int pc)
{
    if (cb_instr) {
        cb_instr(pc);
    }
}
