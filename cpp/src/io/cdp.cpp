#include "cdp.h"

#include "bin.h"
#include "chump.h"
#include "kuid.h"
#include "lzss.h"

#include <cstring>

namespace {

struct Draft {
    std::string kuid;
    std::vector<uint8_t> kuid_bytes;
};

std::string lossy_text(const uint8_t* data, size_t size) {
    if (size > 0 && data[size - 1] == 0) --size;
    return std::string(reinterpret_cast<const char*>(data), size);
}

size_t parse_tag(const uint8_t* data, size_t pos, size_t limit, const std::string& parent, std::vector<std::string>& assets, Draft* draft) {
    if (pos + 5 > limit) return limit;
    uint32_t tag_length = rd_u32(data + pos);
    pos += 4;
    size_t tag_end = pos + tag_length;
    if (tag_end > limit) tag_end = limit;
    if (pos >= tag_end) return tag_end;
    uint8_t name_size = data[pos++];
    if (name_size < 1 || pos + name_size > tag_end) return tag_end;
    std::string name(reinterpret_cast<const char*>(data + pos), name_size - 1);
    pos += name_size;
    if (pos >= tag_end) return tag_end;
    int tag_type = data[pos++];
    if (tag_type == 0) {
        if (parent != "" && parent != "assets") return tag_end;
        Draft child;
        Draft* next = parent == "assets" ? &child : draft;
        while (pos < tag_end) pos = parse_tag(data, pos, tag_end, name, assets, next);
        if (parent == "assets" && !child.kuid.empty()) assets.push_back(child.kuid);
        else if (parent == "assets" && !child.kuid_bytes.empty()) {
            assets.push_back(bytes_to_kuid(child.kuid_bytes.data(), child.kuid_bytes.size()));
        }
        return tag_end;
    }
    if (draft == nullptr) return tag_end;
    const uint8_t* value = data + pos;
    size_t value_len = tag_end - pos;
    if (tag_type == 1 && name == "kuid" && value_len >= 4) {
        int32_t content = rd_i32(value);
        auto packed = pack_kuid(-1, content, std::nullopt);
        draft->kuid_bytes = packed;
        draft->kuid = bytes_to_kuid(packed.data(), packed.size());
    } else if (tag_type == 3 && name == "kuid") {
        std::string text = lossy_text(value, value_len);
        draft->kuid = text.find('<') != std::string::npos ? text : "<" + text + ">";
    } else if (tag_type == 0x0D && name == "kuid" && value_len >= 8) {
        draft->kuid_bytes.assign(value, value + 8);
        draft->kuid = bytes_to_kuid(value, 8);
    }
    return tag_end;
}

const ChumpTag* file_parent(const ChumpTag& asset, const std::string& rel, std::string& leaf) {
    const ChumpTag* files = find_tag(asset.children, "files");
    if (files == nullptr || files->type != ChumpType::Soup) return nullptr;
    std::vector<std::string> parts;
    std::string cur;
    for (char c : rel) {
        if (c == '\\' || c == '/') {
            if (!cur.empty()) parts.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    if (!cur.empty()) parts.push_back(cur);
    if (parts.empty()) return nullptr;
    const ChumpTag* node = files;
    for (size_t i = 0; i + 1 < parts.size(); ++i) {
        const ChumpTag* child = find_tag(node->children, parts[i]);
        if (child == nullptr || child->type != ChumpType::Soup) return nullptr;
        node = child;
    }
    leaf = parts.back();
    return node;
}

}  // namespace

namespace {

std::string text_child(const std::vector<ChumpTag>& tags, const std::string& name) {
    const ChumpTag* tag = find_tag(tags, name);
    if (tag == nullptr || tag->type != ChumpType::Text) return {};
    return tag->text;
}

void collect_files(const std::vector<ChumpTag>& tags, const std::string& prefix, std::vector<std::string>& out) {
    for (const ChumpTag& tag : tags) {
        if (tag.type == ChumpType::Soup) collect_files(tag.children, prefix + tag.name + "/", out);
        else if (tag.type == ChumpType::Raw) out.push_back(prefix + tag.name);
    }
}

}  // namespace

std::vector<CdpAssetEntry> list_cdp_assets(const uint8_t* data, size_t size) {
    ChumpFile file = read_chump(data, size);
    const ChumpTag* assets = find_tag(file.root, "assets");
    std::vector<CdpAssetEntry> rows;
    if (assets == nullptr || assets->type != ChumpType::Soup) return rows;
    for (const ChumpTag& asset : assets->children) {
        if (asset.type != ChumpType::Soup || asset.name.empty()) continue;
        CdpAssetEntry row;
        row.kuid = asset.name;
        row.username = text_child(asset.children, "username");
        row.kind = text_child(asset.children, "kind");
        const ChumpTag* files = find_tag(asset.children, "files");
        if (files != nullptr && files->type == ChumpType::Soup) collect_files(files->children, "", row.files);
        rows.push_back(std::move(row));
    }
    return rows;
}

std::vector<std::string> list_cdp_kuids(const uint8_t* data, size_t size) {
    need(size, 16, "not a CDP/chump");
    if (std::memcmp(data, "ACS$", 4) != 0) throw std::runtime_error("not a CDP/chump");
    uint32_t length = rd_u32(data + 12);
    size_t end = 16 + length;
    if (end > size) end = size;
    std::vector<std::string> assets;
    size_t pos = 16;
    while (pos < end) pos = parse_tag(data, pos, end, "", assets, nullptr);
    return assets;
}

std::vector<uint8_t> read_cdp_file(
    const uint8_t* data, size_t size, const std::string& asset_kuid, const std::string& rel_path) {
    ChumpFile file = read_chump(data, size);
    const ChumpTag* assets = find_tag(file.root, "assets");
    if (assets == nullptr) throw std::runtime_error("missing asset");
    const ChumpTag* asset = find_tag(assets->children, asset_kuid);
    if (asset == nullptr) throw std::runtime_error("missing asset");
    std::string leaf;
    const ChumpTag* parent = file_parent(*asset, rel_path, leaf);
    if (parent == nullptr) throw std::runtime_error("missing file");
    const ChumpTag* tag = find_tag(parent->children, leaf);
    if (tag == nullptr) throw std::runtime_error("missing file");
    return decode_binary_blob(tag->raw.data(), tag->raw.size());
}
