/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <IOKit/IOMemoryDescriptor.h>
#include "DitingScanoutWire.h"
extern "C" {
void diting_scanout_initialize(uint64_t,size_t,uint32_t,uint32_t,uint32_t);
int diting_scanout_frame(IOMemoryDescriptor *,size_t,uint32_t,uint32_t,uint32_t);
bool diting_scanout_quarantined(void);
void diting_scanout_idle(void);
IOReturn diting_scanout_connect(task_t);
void diting_scanout_disconnect(task_t);
IOReturn diting_scanout_call(task_t,unsigned,const void *,size_t,void *,size_t);
IOMemoryDescriptor *diting_scanout_memory(task_t);
}
