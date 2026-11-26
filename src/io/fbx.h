#pragma once

#include "io/im_geom.h"

#include <cstdint>
#include <string>
#include <vector>

// Triangulated parts in Trainz space (metres, +X right, +Z up, +Y forward).
std::vector<MeshPart> parse_fbx_parts(const uint8_t* data, size_t size);
// Parts plus every node named a.* as an attachment (world pose, rows = node axes). Throws only when both are missing.
ImView parse_fbx_view(const uint8_t* data, size_t size);
// ASCII FBX 7.4 from Trainz-space parts + a.* attachments (same axis/unit convention as the fixtures).
std::string write_fbx(const ImView& view);
