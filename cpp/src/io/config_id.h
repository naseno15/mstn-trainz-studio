#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

struct ConfigIdentity {
    std::string author;
    std::string build;
    std::string username;
    std::string kuid;
};

struct LibraryRow {
    std::string name;
    std::string kuid;
    std::string author;
    std::string build;
};

ConfigIdentity config_identity(const uint8_t* data, size_t size);
std::string author_label(const std::string& author, const std::string& build);
LibraryRow library_row_from_config(const uint8_t* data, size_t size);
