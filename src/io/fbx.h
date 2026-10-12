#pragma once

#include "io/im_geom.h"

#include <cstdint>
#include <vector>

// Triangulated parts in Trainz space (metres, +X right, +Z up, +Y forward).
std::vector<MeshPart> parse_fbx_parts(const uint8_t* data, size_t size);
// Parts plus every node named a.* as an attachment (world pose, rows = node axes). Throws only when both are missing.
ImView parse_fbx_view(const uint8_t* data, size_t size);
