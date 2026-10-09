#pragma once

#include <cstdint>
#include <string>
#include <vector>

std::vector<uint8_t> read_tzarc_config(const uint8_t* data, size_t size);
