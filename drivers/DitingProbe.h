// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef DITING_PROBE_H
#define DITING_PROBE_H

// Optional probes report a result and return. A FAIL must never publish a
// successful hardware resource or touch later MMIO stages that need it.
enum DitingProbeState : unsigned {
  DitingProbePass = 1, DitingProbeFail = 2, DitingProbeSkip = 3, DitingProbeRunning = 4
};

static inline void DitingProbeRecord(unsigned slot, const char *name,
                                   DitingProbeState state, const char *reason,
                                   uint64_t detail = 0)
{
  (void)slot;
  (void)name;
  (void)state;
  (void)reason;
  (void)detail;
}
#endif
