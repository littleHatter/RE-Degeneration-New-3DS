#pragma once
#include <cstdint>
#ifdef __3DS__
#include <3ds.h>
inline uint64_t NfsClockMs(){return svcGetSystemTick()/CPU_TICKS_PER_MSEC;}
#else
#include <chrono>
inline uint64_t NfsClockMs(){return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
#endif
