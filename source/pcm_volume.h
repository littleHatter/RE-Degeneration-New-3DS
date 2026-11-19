#pragma once
#include <cstdint>
// Keep negative PCM signed when applying the unsigned S3E 0..256 volume.
inline int32_t ScalePcmVolume(int32_t sample,uint32_t volume){return int32_t(int64_t(sample)*volume/256);}
