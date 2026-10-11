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

#include "io/fbx.h"
#include "io/cdp.h"
#include "io/chump.h"
#include "io/im_geom.h"
#include "io/kin.h"
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
    expect_eq(summarize_chump(text_to_chump(chump_to_text(chump))), summarize_chump(chump), "chump text");

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

    auto named = tz;
    const size_t tail = sub.tail_off;
    assert(tail <= named.size());
    auto le = [](const char* text) {
        const std::string body = std::string(text) + '\0';
        std::string out(4 + body.size(), '\0');
        const uint32_t n = static_cast<uint32_t>(body.size());
        std::memcpy(out.data(), &n, 4);
        std::memcpy(out.data() + 4, body.data(), body.size());
        return out;
    };
    const std::string block = le("pbrmetal") + le("body.m.pbrmetal") + std::string("\0\0\0\0\x01", 5) + std::string(16, '\0') + std::string("\0\0\0\x01", 4) + le("txAlbedo") + le("body.texture");
    named.insert(named.begin() + static_cast<std::ptrdiff_t>(tail), block.begin(), block.end());
    const TrainzMesh tagged = parse_trainzmesh(named.data(), named.size());
    assert(tagged.submeshes[0].name == "body.m.pbrmetal");
    assert(tagged.submeshes[0].material_type == "pbrmetal");
    const auto mats = parse_tzmf_materials(named.data(), named.size());
    assert(mats.size() == 1);
    assert(mats[0].name == "body.m.pbrmetal");
    assert(mats[0].textures.size() == 1);
    assert(mats[0].textures[0].key == "txAlbedo");
    const std::string kin_path = std::string(EDITING_DIR) + "/kuid 1190880 100144 MSTN KIHA _ ______40/glass/windowcab_scene.kin";
    const std::string mesh_path = std::string(EDITING_DIR) + "/kuid 1190880 100144 MSTN KIHA _ ______40/glass/windowcab.trainzmesh";
    if (std::ifstream(kin_path, std::ios::binary) && std::ifstream(mesh_path, std::ios::binary)) {
        const auto kin_bin = read_bin(kin_path);
        const auto mesh_bin = read_bin(mesh_path);
        const KinClip clip = parse_kin(kin_bin.data(), kin_bin.size());
        assert(clip.ok);
        assert(clip.frames.size() == 99);
        assert(clip.bones.size() == 1 && clip.bones[0] == "r.fuckyou");
        assert(std::fabs(clip.frames[1][0].pos[2] + 0.0128f) < 1e-4f);
        std::string missing;
        assert(kin_bones_in_mesh(clip, mesh_bin.data(), mesh_bin.size(), &missing));
        KinClip foreign = clip;
        foreign.bones[0] = "r.not-on-this-mesh";
        assert(!kin_bones_in_mesh(foreign, mesh_bin.data(), mesh_bin.size(), &missing));
        assert(missing == "r.not-on-this-mesh");
    }
    std::vector<uint8_t> att_bin;
    const std::string att_name = "a.bog0";
    att_bin.push_back(static_cast<uint8_t>(att_name.size()));
    att_bin.insert(att_bin.end(), att_name.begin(), att_name.end());
    auto push_be = [&](float v) {
        uint32_t bits = 0;
        std::memcpy(&bits, &v, 4);
        for (int s = 24; s >= 0; s -= 8) att_bin.push_back(static_cast<uint8_t>((bits >> s) & 0xFF));
    };
    push_be(1.5f);
    push_be(-2.f);
    push_be(0.25f);
    push_be(0.f);
    push_be(0.f);
    push_be(0.f);
    push_be(1.f);
    const auto atts = parse_trainzmesh_attachments(att_bin.data(), att_bin.size());
    assert(atts.size() == 1);
    assert(atts[0].name == "a.bog0");
    assert(std::fabs(atts[0].pos[0] - 1.5f) < 1e-5f);
    assert(std::fabs(atts[0].orient[0] - 1.f) < 1e-5f && std::fabs(atts[0].orient[4] - 1.f) < 1e-5f);
    const std::string body = std::string(EDITING_DIR) + "/kuid 1125787 100059 MSTN KIHA _ ______40/body/body.trainzmesh";
    if (std::ifstream(body, std::ios::binary)) {
        const auto body_bin = read_bin(body);
        const auto body_atts = parse_trainzmesh_attachments(body_bin.data(), body_bin.size());
        assert(body_atts.size() == 102);
        assert(body_atts[0].name == "a.airdryer");
    }
    const std::string door = "c:/trs22/backups/26-10-03/kuid 1125787 100060 MSTN KIHA _ ______40/door/doorintback.trainzmesh";
    if (std::ifstream(door, std::ios::binary)) {
        const auto door_bin = read_bin(door);
        const auto door_mats = parse_tzmf_materials(door_bin.data(), door_bin.size());
        assert(door_mats.size() == 3);
        assert(door_mats[0].name == "rubber.m.pbrmetal");
        assert(door_mats[0].textures.size() == 6);
    }
}

// Multi-chunk v2 archive built from stored (uncompressed) deflate blocks, 16-byte chunks.
// Files straddle chunk edges; selective and whole reads must agree.
static void check_tzarc_chunks() {
    const std::vector<std::pair<std::string, std::string>> files = {
        {"config.txt", "username \"x\"\nkind \"traincar\"\n"}, {"mesh/b.bin", std::string(70, 'B') + "end"}, {"c.png", std::string(40, 'C')}};
    std::vector<uint8_t> inner = {0, 0, 0, static_cast<uint8_t>(files.size())};
    for (const auto& f : files) {
        inner.push_back(static_cast<uint8_t>(f.first.size()));
        inner.insert(inner.end(), f.first.begin(), f.first.end());
        for (int s = 56; s >= 0; s -= 8) inner.push_back(static_cast<uint8_t>((uint64_t(f.second.size()) >> s) & 0xFF));
    }
    inner.insert(inner.end(), {0, 0, 0, 0});
    for (const auto& f : files) inner.insert(inner.end(), f.second.begin(), f.second.end());
    const size_t chunk = 16, n = (inner.size() + chunk - 1) / chunk;
    std::vector<uint8_t> out = {'T', 'Z', 'a', 'c', 0, 0, 0, 2};
    auto le = [&](uint64_t v, int bytes) {
        for (int i = 0; i < bytes; ++i) out.push_back(static_cast<uint8_t>((v >> (8 * i)) & 0xFF));
    };
    le(inner.size(), 8);
    le(n, 4);
    std::vector<size_t> sizes;
    for (size_t i = 0; i < n; ++i) sizes.push_back(std::min(chunk, inner.size() - i * chunk));
    for (size_t s : sizes) le(s + 10, 2);  // zlib hdr 2 + stored hdr 5 + data + adler 4, minus 1
    for (size_t i = 0; i < n; ++i) {
        out.insert(out.end(), {0x78, 0x01, 0x01});
        le(sizes[i], 2);
        le(~sizes[i] & 0xFFFF, 2);
        out.insert(out.end(), inner.begin() + i * chunk, inner.begin() + i * chunk + sizes[i]);
        out.insert(out.end(), {0, 0, 0, 0});
    }
    const auto config = read_tzarc_config(out.data(), out.size());
    assert(std::string(config.begin(), config.end()) == files[0].second);
    const auto one = read_tzarc_select(out.data(), out.size(), [](const std::string& name) { return name == "mesh/b.bin"; });
    assert(one.size() == 1 && std::string(one[0].second.begin(), one[0].second.end()) == files[1].second);
    const auto all = read_tzarc_all(out.data(), out.size());
    assert(all.size() == 3 && std::string(all[2].second.begin(), all[2].second.end()) == files[2].second);
}

static void check_real_meshes() {
    const std::string editing = EDITING_DIR;
    const std::string cab = editing + "/kuid 1190880 100078 MSTN KIHA _ ______40/cab.im";
    const std::string door = editing + "/kuid 1125787 100060 MSTN KIHA _ ______40/door/doorback.fbx";
    if (!std::ifstream(cab, std::ios::binary)) return;
    auto cab_bytes = read_bin(cab);
    ImView cab_view = parse_im_view(cab_bytes.data(), cab_bytes.size());
    assert(cab_view.parts.empty());
    assert(cab_view.atts.size() > 10);
    assert(cab_view.atts[0].name.rfind("a.", 0) == 0);
    bool turned = false;
    for (const ImAttachment& att : cab_view.atts)
        if (std::fabs(att.orient[1]) > 0.15f || std::fabs(att.orient[2]) > 0.15f || std::fabs(att.orient[3]) > 0.15f || std::fabs(att.orient[6]) > 0.15f) turned = true;
    assert(turned);
    auto door_bytes = read_bin(door);
    auto door_parts = parse_fbx_parts(door_bytes.data(), door_bytes.size());
    assert(!door_parts.empty());
    float zmin = 1e30f, zmax = -1e30f;
    size_t tris = 0;
    for (const MeshPart& part : door_parts) {
        tris += part.indices.size() / 3;
        for (size_t i = 2; i < part.positions.size(); i += 3) {
            zmin = std::min(zmin, part.positions[i]);
            zmax = std::max(zmax, part.positions[i]);
        }
    }
    assert(tris > 100);
    assert(zmax - zmin > 1.f);
}

static void check_fbx() {
    auto fbx = read_bin(std::string(FIXTURE_DIR) + "/tri.fbx");
    auto parts = parse_fbx_parts(fbx.data(), fbx.size());
    assert(parts.size() == 1);
    assert(parts[0].name == "tri");
    assert(parts[0].indices.size() == 3);
    assert(parts[0].positions.size() == 9);
    bool origin = false, right = false, up = false;
    for (size_t v = 0; v < 3; ++v) {
        const float x = parts[0].positions[v * 3];
        const float y = parts[0].positions[v * 3 + 1];
        const float z = parts[0].positions[v * 3 + 2];
        if (std::fabs(x) < 1e-3f && std::fabs(y) < 1e-3f && std::fabs(z) < 1e-3f) origin = true;
        if (x > 0.5f) right = true;
        if (z > 0.5f) up = true;
    }
    assert(origin && right && up);
}

int main() {
    check_tzarc_chunks();
    check_fbx();
    check_real_meshes();
    check_kuid();
    check_lzss();
    check_files();
    check_texture_txt_logic();
    check_lm_txt_logic();
    check_mat_name_logic();
    std::printf("check_formats: ok\n");
    return 0;
}
