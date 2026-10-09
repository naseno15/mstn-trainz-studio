#undef NDEBUG
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "io/cdp.h"
#include "io/chump.h"
#include "io/im_geom.h"
#include "io/kuid.h"
#include "io/lzss.h"
#include "io/lm_txt.h"
#include "io/mat_name.h"
#include "io/texture_txt.h"
#include "io/trainzmesh.h"
#include "io/tzarc.h"

#ifndef FIXTURE_DIR
#define FIXTURE_DIR "checks/fixtures"
#endif

static std::vector<uint8_t> read_bin(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    assert(in);
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

static std::string read_text(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    assert(in);
    std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    text.erase(std::remove(text.begin(), text.end(), '\r'), text.end());
    return text;
}

static void expect_eq(const std::string& got, const std::string& want, const char* name) {
    if (got != want) {
        std::fprintf(stderr, "%s mismatch\n--- got ---\n%s--- want ---\n%s", name, got.c_str(), want.c_str());
        assert(false);
    }
}

static int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static std::vector<uint8_t> from_hex(const char* text) {
    std::vector<uint8_t> out;
    int hi = -1;
    for (const char* p = text; *p; ++p) {
        int n = hex_nibble(*p);
        if (n < 0) continue;
        if (hi < 0) hi = n;
        else {
            out.push_back(static_cast<uint8_t>((hi << 4) | n));
            hi = -1;
        }
    }
    return out;
}

static std::string fmt_f(float value) {
    float nearest = std::round(value);
    if (std::fabs(value - nearest) < 1e-5f) return std::to_string(static_cast<int>(nearest));
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6f", value);
    std::string text = buf;
    while (!text.empty() && text.back() == '0') text.pop_back();
    if (!text.empty() && text.back() == '.') text.pop_back();
    return text.empty() ? "0" : text;
}

static std::string join_ints(const std::vector<int32_t>& values) {
    std::string out;
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) out += ',';
        out += std::to_string(values[i]);
    }
    return out;
}

static std::string summarize_chump(const ChumpFile& file) {
    std::string out;
    const auto walk = [&](auto&& self, const std::vector<ChumpTag>& tags, const std::string& indent) -> void {
        for (const ChumpTag& tag : tags) {
            if (tag.type == ChumpType::Soup) {
                out += indent + "soup " + tag.name + "\n";
                self(self, tag.children, indent + "  ");
            } else if (tag.type == ChumpType::Text) {
                out += indent + "text " + tag.name + "=" + tag.text + "\n";
            } else if (tag.type == ChumpType::Int) {
                out += indent + "int " + tag.name + "=" + join_ints(tag.ints) + "\n";
            } else if (tag.type == ChumpType::Kuid) {
                out += indent + "kuid " + tag.name + "=" + bytes_to_kuid(tag.raw.data(), tag.raw.size()) + "\n";
            }
        }
    };
    walk(walk, file.root, "");
    return out;
}

static void check_kuid() {
    auto plain = pack_kuid(1, 2, std::nullopt);
    assert(bytes_to_kuid(plain.data(), plain.size()) == "<kuid:1:2>");
    assert(hash_folder(plain.data(), plain.size()) == "hash-03");
    auto parsed = parse_kuid_string("see <kuid2:1190880:100078:1> here");
    assert(parsed);
    assert(bytes_to_kuid(parsed->data(), parsed->size()) == "<kuid2:1190880:100078:1>");
    uint8_t negative[] = {0x00, 0x00, 0x00, 0x01, 0x02, 0x00, 0x00, 0x00};
    assert(bytes_to_kuid(negative, 8) == "<kuid2:-16777216:2:0>");
}

static void check_lzss() {
    std::vector<uint8_t> sample(512);
    for (int i = 0; i < 256; ++i) {
        sample[i] = static_cast<uint8_t>(i);
        sample[256 + i] = static_cast<uint8_t>(i);
    }
    std::vector<uint8_t> stored;
    stored.push_back(0x20);
    stored.insert(stored.end(), sample.begin(), sample.end());
    assert(lzss_decompress(stored.data(), stored.size(), static_cast<uint32_t>(sample.size())) == sample);

    std::vector<uint8_t> blob(4);
    uint32_t n = static_cast<uint32_t>(sample.size());
    std::memcpy(blob.data(), &n, 4);
    blob.push_back(0x00);
    blob.insert(blob.end(), sample.begin(), sample.end());
    assert(decode_binary_blob(blob.data(), blob.size()) == sample);

    auto gs = from_hex(
        "450000000600000000696e636c75646520226b6968615f6d61696e2e677322"
        "0a0a636c617373206d730000ae01746e5f6c696e6b5f736372697074206973"
        "192e207b7d3b0a");
    auto gs_text = decode_binary_blob(gs.data(), gs.size());
    assert(std::string(gs_text.begin(), gs_text.end()) == "include \"kiha_main.gs\"\n\nclass mstn_link_script isclass kiha_main {};\n");

    auto lm = from_hex(
        "b4000000060000000076657273696f6e20312e300d0a6f6666736574203d2030"
        "2e30303b0d0a63616c6080002063506f696e1363656e746572156d756c746970"
        "6c6965720400dc0016311172656e6465724375744f66663c16616e696d6174f1"
        "0c105f5b081931351974746163686d4f093334010080005d6573682822312229"
        "0d0a7b0d0a20206e616d6521226361622e08000000696d22247d0d0a");
    auto lm_text = decode_binary_blob(lm.data(), lm.size());
    std::string lm_want =
        "version 1.0\r\noffset = 0.00;\r\ncalcPoint = center;\r\n"
        "multiplier = 1;\r\nrenderCutOff = 0.01;\r\nanimationCutOff = 0.15;\r\n"
        "attachmentCutOff = 0.001;\r\n\r\nmesh(\"1\")\r\n{\r\n  name = \"cab.im\";\r\n}\r\n";
    assert(std::string(lm_text.begin(), lm_text.end()) == lm_want);

    const uint8_t jp[] = {0x93, 0xFA, 0x96, 0x7B, 0x8C, 0xEA};
    assert(decode_asset_text(jp, sizeof(jp)) == "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E");
}

static void check_files() {
    const std::string dir = FIXTURE_DIR;
    auto chump_bin = read_bin(dir + "/chump.bin");
    ChumpFile chump = read_chump(chump_bin.data(), chump_bin.size());
    expect_eq(summarize_chump(chump), read_text(dir + "/chump.txt"), "chump");
    assert(encode_chump(chump) == chump_bin);

    auto cdp_bin = read_bin(dir + "/demo.cdp");
    auto kuids = list_cdp_kuids(cdp_bin.data(), cdp_bin.size());
    assert(kuids.size() == 1);
    auto note = read_cdp_file(cdp_bin.data(), cdp_bin.size(), kuids[0], "note.txt");
    expect_eq("kuid " + kuids[0] + "\nfile note.txt " + std::string(note.begin(), note.end()) + "\n", read_text(dir + "/cdp.txt"), "cdp");

    auto v1 = read_bin(dir + "/sample.tzarc");
    auto v2 = read_bin(dir + "/sample2.tzarc");
    auto c1 = read_tzarc_config(v1.data(), v1.size());
    auto c2 = read_tzarc_config(v2.data(), v2.size());
    expect_eq("v1 config.txt " + std::string(c1.begin(), c1.end()) + "\nv2 config.txt " + std::string(c2.begin(), c2.end()) + "\n",
              read_text(dir + "/tzarc.txt"), "tzarc");

    auto im = read_bin(dir + "/tri.im");
    auto parts = parse_im_parts(im.data(), im.size());
    std::ostringstream im_got;
    im_got << "parts " << parts.size() << "\nname " << parts[0].name << "\nverts " << (parts[0].positions.size() / 3) << "\nidx ";
    for (size_t i = 0; i < parts[0].indices.size(); ++i) {
        if (i) im_got << ',';
        im_got << parts[0].indices[i];
    }
    im_got << '\n';
    for (size_t v = 0; v < parts[0].positions.size() / 3; ++v) {
        im_got << "pos" << v << ' ' << fmt_f(parts[0].positions[v * 3]) << ',' << fmt_f(parts[0].positions[v * 3 + 1]) << ','
               << fmt_f(parts[0].positions[v * 3 + 2]) << '\n';
    }
    expect_eq(im_got.str(), read_text(dir + "/im.txt"), "im");

    auto tz = read_bin(dir + "/tri.trainzmesh");
    TrainzMesh mesh = parse_trainzmesh(tz.data(), tz.size());
    const SubMesh& sub = mesh.submeshes[0];
    std::ostringstream tz_got;
    tz_got << "version " << mesh.version << "\ncount " << mesh.submeshes.size() << "\nname " << sub.name << "\nverts "
           << (sub.positions.size() / 3) << "\nidx ";
    for (size_t i = 0; i < sub.indices.size(); ++i) {
        if (i) tz_got << ',';
        tz_got << sub.indices[i];
    }
    tz_got << '\n';
    for (size_t v = 0; v < sub.positions.size() / 3; ++v) {
        tz_got << "pos" << v << ' ' << fmt_f(sub.positions[v * 3]) << ',' << fmt_f(sub.positions[v * 3 + 1]) << ','
               << fmt_f(sub.positions[v * 3 + 2]) << '\n';
    }
    for (size_t v = 0; v < sub.uvs.size() / 2; ++v) {
        tz_got << "uv" << v << ' ' << fmt_f(sub.uvs[v * 2]) << ',' << fmt_f(sub.uvs[v * 2 + 1]) << '\n';
    }
    tz_got << "albedo " << sub.albedo << "\nmat " << sub.material_type << "\n";
    expect_eq(tz_got.str(), read_text(dir + "/tzmf.txt"), "tzmf");
}

int main() {
    check_kuid();
    check_lzss();
    check_files();
    check_texture_txt_logic();
    check_lm_txt_logic();
    check_mat_name_logic();
    std::printf("check_formats: ok\n");
    return 0;
}
