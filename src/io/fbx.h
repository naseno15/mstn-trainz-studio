#pragma once

#include "io/im_geom.h"

#include <cstdint>
#include <vector>

// Triangulated parts in Trainz space (metres, +X right, +Z up, +Y forward).
std::vector<MeshPart> parse_fbx_parts(const uint8_t* data, size_t size);
