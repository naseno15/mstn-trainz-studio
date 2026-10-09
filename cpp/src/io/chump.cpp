#include "chump.h"

#include "bin.h"

static std::string utf8_lossy(const uint8_t* data, size_t size) {
    std::string out;
    out.reserve(size);
    for (size_t i = 0; i < size;) {
        uint8_t c = data[i];
        size_t need = 1;
        if ((c & 0x80) == 0) need = 1;
        else if ((c & 0xE0) == 0xC0) need = 2;
        else if ((c & 0xF0) == 0xE0) need = 3;
        else if ((c & 0xF8) == 0xF0) need = 4;
        else {
            out.append("\xEF\xBF\xBD");
            ++i;
            continue;
        }
        if (i + need > size) {
            out.append("\xEF\xBF\xBD");
            break;
        }
        bool ok = true;
        for (size_t k = 1; k < need; ++k) {
            if ((data[i + k] & 0xC0) != 0x80) ok = false;
        }
        if (!ok) {
            out.append("\xEF\xBF\xBD");
            ++i;
            continue;
        }
        out.append(reinterpret_cast<const char*>(data + i), need);
        i += need;
    }
    return out;
}

static ChumpTag read_tag(const uint8_t* data, size_t limit, size_t& pos) {
    if (pos + 5 > limit) throw std::runtime_error("truncated chump tag");
    uint32_t pair_len = rd_u32(data + pos);
    pos += 4;
    size_t pair_end = pos + pair_len;
    if (pair_end > limit) pair_end = limit;
    uint8_t name_size = data[pos++];
    if (name_size < 1 || pos + name_size > pair_end) throw std::runtime_error("bad chump tag name");
    std::string name = utf8_lossy(data + pos, name_size - 1);
    pos += name_size;
    if (pos >= pair_end) {
        ChumpTag tag;
        tag.name = name;
        tag.type = ChumpType::Null;
        pos = pair_end;
        return tag;
    }
    auto type = static_cast<ChumpType>(data[pos++]);
    const uint8_t* payload = data + pos;
    size_t payload_len = pair_end - pos;
    ChumpTag tag;
    tag.name = name;
    tag.type = type;
    if (type == ChumpType::Soup) {
        size_t cpos = 0;
        while (cpos < payload_len) tag.children.push_back(read_tag(payload, payload_len, cpos));
    } else if (type == ChumpType::Int) {
        for (size_t i = 0; i + 4 <= payload_len; i += 4) tag.ints.push_back(rd_i32(payload + i));
    } else if (type == ChumpType::Float) {
        for (size_t i = 0; i + 4 <= payload_len; i += 4) tag.floats.push_back(rd_f32(payload + i));
    } else if (type == ChumpType::Text) {
        size_t n = 0;
        while (n < payload_len && payload[n] != 0) ++n;
        tag.text = utf8_lossy(payload, n);
    } else if (type == ChumpType::Null) {
        tag.type = ChumpType::Null;
    } else if (type == ChumpType::Kuid) {
        if (payload_len < 8) throw std::runtime_error("kuid tag too short");
        tag.raw.assign(payload, payload + 8);
    } else {
        tag.raw.assign(payload, payload + payload_len);
    }
    pos = pair_end;
    return tag;
}

ChumpFile read_chump(const uint8_t* data, size_t size) {
    need(size, 16, "not a chump (missing ACS$)");
    if (std::memcmp(data, "ACS$", 4) != 0) throw std::runtime_error("not a chump (missing ACS$)");
    ChumpFile file;
    file.version = rd_u32(data + 4);
    file.reserved = rd_u32(data + 8);
    uint32_t length = rd_u32(data + 12);
    size_t end = 16 + length;
    if (end > size) end = size;
    size_t pos = 16;
    while (pos < end) file.root.push_back(read_tag(data, end, pos));
    return file;
}

static void encode_tag(const ChumpTag& tag, std::vector<uint8_t>& out) {
    std::string name_b = tag.name;
    name_b.push_back('\0');
    if (name_b.size() > 255) throw std::runtime_error("tag name too long");
    std::vector<uint8_t> payload;
    if (tag.type == ChumpType::Soup) {
        for (const ChumpTag& child : tag.children) encode_tag(child, payload);
    } else if (tag.type == ChumpType::Int) {
        for (int32_t value : tag.ints) wr_i32(payload, value);
    } else if (tag.type == ChumpType::Float) {
        for (float value : tag.floats) wr_f32(payload, value);
    } else if (tag.type == ChumpType::Text) {
        payload.insert(payload.end(), tag.text.begin(), tag.text.end());
        payload.push_back(0);
    } else if (tag.type == ChumpType::Null) {
    } else if (tag.type == ChumpType::Kuid) {
        if (tag.raw.size() < 8) throw std::runtime_error("kuid tag too short");
        payload.insert(payload.end(), tag.raw.begin(), tag.raw.begin() + 8);
    } else {
        payload.insert(payload.end(), tag.raw.begin(), tag.raw.end());
    }
    uint32_t pair_len = static_cast<uint32_t>(name_b.size() + 2 + payload.size());
    wr_u32(out, pair_len);
    out.push_back(static_cast<uint8_t>(name_b.size()));
    out.insert(out.end(), name_b.begin(), name_b.end());
    out.push_back(static_cast<uint8_t>(tag.type));
    out.insert(out.end(), payload.begin(), payload.end());
}

std::vector<uint8_t> encode_chump(const ChumpFile& file) {
    std::vector<uint8_t> body;
    for (const ChumpTag& tag : file.root) encode_tag(tag, body);
    std::vector<uint8_t> out;
    out.insert(out.end(), {'A', 'C', 'S', '$'});
    wr_u32(out, file.version);
    wr_u32(out, file.reserved);
    wr_u32(out, static_cast<uint32_t>(body.size()));
    out.insert(out.end(), body.begin(), body.end());
    return out;
}

const ChumpTag* find_tag(const std::vector<ChumpTag>& tags, const std::string& name) {
    for (const ChumpTag& tag : tags) {
        if (tag.name == name) return &tag;
    }
    return nullptr;
}
