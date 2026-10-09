#include "kuid.h"

#include "bin.h"

#include <cctype>
#include <cstdio>

std::vector<uint8_t> pack_kuid(int32_t creator, int32_t content, std::optional<int> version) {
    std::vector<uint8_t> out(8);
    uint32_t user = static_cast<uint32_t>(creator);
    uint32_t cont = static_cast<uint32_t>(content);
    std::memcpy(out.data(), &user, 4);
    std::memcpy(out.data() + 4, &cont, 4);
    if (version && *version > 0 && *version < 128 && creator >= 0) {
        out[3] = static_cast<uint8_t>((out[3] & 1) | ((*version & 0x7F) << 1));
    }
    return out;
}

void unpack_kuid(const uint8_t* raw, size_t size, int32_t& creator, int32_t& content, int& version) {
    need(size, 8, "kuid needs 8 bytes");
    uint8_t ub[4] = {raw[0], raw[1], raw[2], raw[3]};
    version = ub[3] >> 1;
    uint8_t sign = ub[3] & 1;
    ub[3] = sign ? 0xFF : 0;
    creator = static_cast<int32_t>(rd_u32(ub));
    content = rd_i32(raw + 4);
}

std::string bytes_to_kuid(const uint8_t* raw, size_t size) {
    int32_t creator = 0;
    int32_t content = 0;
    int version = 0;
    unpack_kuid(raw, size, creator, content, version);
    if ((version > 0 && creator > 0) || (version == 0 && creator < 0)) {
        return "<kuid2:" + std::to_string(creator) + ":" + std::to_string(content) + ":" +
               std::to_string(version) + ">";
    }
    return "<kuid:" + std::to_string(creator) + ":" + std::to_string(content) + ">";
}

std::optional<std::vector<uint8_t>> parse_kuid_string(const std::string& text) {
    auto lower_at = [](unsigned char c) { return static_cast<char>(std::tolower(c)); };
    size_t pos = text.find('<');
    if (pos == std::string::npos) return std::nullopt;
    size_t end = text.find('>', pos);
    if (end == std::string::npos) return std::nullopt;
    std::string body = text.substr(pos + 1, end - pos - 1);
    size_t i = 0;
    while (i < body.size() && std::isspace(static_cast<unsigned char>(body[i]))) ++i;
    std::string kind;
    while (i < body.size() && std::isalpha(static_cast<unsigned char>(body[i]))) {
        kind.push_back(lower_at(static_cast<unsigned char>(body[i])));
        ++i;
    }
    if (kind == "kuid" && i < body.size() && body[i] == '2') {
        kind.push_back('2');
        ++i;
    }
    if (kind != "kuid" && kind != "kuid2") return std::nullopt;
    while (i < body.size() && (std::isspace(static_cast<unsigned char>(body[i])) || body[i] == ':')) ++i;
    std::vector<std::string> parts;
    std::string cur;
    for (; i <= body.size(); ++i) {
        if (i == body.size() || body[i] == ':') {
            size_t a = 0;
            while (a < cur.size() && std::isspace(static_cast<unsigned char>(cur[a]))) ++a;
            size_t b = cur.size();
            while (b > a && std::isspace(static_cast<unsigned char>(cur[b - 1]))) --b;
            if (a < b) parts.push_back(cur.substr(a, b - a));
            cur.clear();
        } else {
            cur.push_back(body[i]);
        }
    }
    if (parts.size() < 2) return std::nullopt;
    int32_t creator = std::stoi(parts[0]);
    int32_t content = std::stoi(parts[1]);
    if (kind == "kuid2") {
        int version = parts.size() >= 3 ? std::stoi(parts[2]) : 127;
        return pack_kuid(creator, content, version);
    }
    return pack_kuid(creator, content, std::nullopt);
}

int kuid_hash(const uint8_t* raw, size_t size) {
    need(size, 8, "kuid needs 8 bytes");
    int hash = 0;
    for (int i = 0; i < 8; ++i) hash ^= raw[i];
    if ((raw[3] & 1) == 0) hash ^= raw[3];
    return hash & 0xFF;
}

std::string hash_folder(const uint8_t* raw, size_t size) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "hash-%02X", kuid_hash(raw, size));
    return buf;
}
