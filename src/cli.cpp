#include "cli.h"

#include "io/cdp.h"
#include "io/chump.h"
#include "io/enginespec.h"
#include "io/fbx.h"
#include "io/im_geom.h"
#include "io/kin.h"
#include "io/kuid.h"
#include "io/lm_txt.h"
#include "io/texture_txt.h"
#include "io/trainzmesh.h"
#include "io/tzarc.h"
#include "io/wav.h"
#include "io/zip_read.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <exception>
#include <fstream>
#include <ostream>
#include <sstream>
#include <string>
#include <vector>

#ifndef TRAINZ_STUDIO_VERSION
#define TRAINZ_STUDIO_VERSION "0"
#endif

namespace {

enum class Cmd { None, Help, Version, Kuid, Mesh, Cdp, Tzarc, Chump, Zip, Texture, Wav, Engine, Lm, Kin };

const char* usage_text() {
    return
        "Trainz Studio " TRAINZ_STUDIO_VERSION "\n"
        "trainz_studio_cpp <command> [args]\n"
        "  help\n"
        "  version\n"
        "  kuid <kuid>\n"
        "  mesh <file.trainzmesh|.im|.fbx>\n"
        "  cdp <file.cdp> [kuid]\n"
        "  tzarc <file.tzarc> [name]\n"
        "  chump <file>\n"
        "  zip <file.zip>\n"
        "  texture <file.texture.txt>\n"
        "  wav <file.wav>\n"
        "  engine <enginespec>\n"
        "  lm <file.lm.txt>\n"
        "  kin <file.kin>\n"
        "No command opens the window.\n";
}

std::string lower_copy(std::string text) {
    for (char& c : text)
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    return text;
}

Cmd command_of(const char* text) {
    const std::string name = lower_copy(text ? text : "");
    if (name == "help" || name == "--help" || name == "-h" || name == "/?") return Cmd::Help;
    if (name == "version" || name == "--version" || name == "-v") return Cmd::Version;
    if (name == "kuid") return Cmd::Kuid;
    if (name == "mesh") return Cmd::Mesh;
    if (name == "cdp") return Cmd::Cdp;
    if (name == "tzarc") return Cmd::Tzarc;
    if (name == "chump") return Cmd::Chump;
    if (name == "zip") return Cmd::Zip;
    if (name == "texture") return Cmd::Texture;
    if (name == "wav") return Cmd::Wav;
    if (name == "engine") return Cmd::Engine;
    if (name == "lm") return Cmd::Lm;
    if (name == "kin") return Cmd::Kin;
    return Cmd::None;
}

std::vector<uint8_t> read_bin(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open " + path);
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

std::string read_text(const std::string& path) {
    const std::vector<uint8_t> bytes = read_bin(path);
    std::string text(bytes.begin(), bytes.end());
    text.erase(std::remove(text.begin(), text.end(), '\r'), text.end());
    return text;
}

std::string extension_of(std::string path) {
    for (char& c : path)
        if (c == '\\') c = '/';
    const auto slash = path.rfind('/');
    const auto dot = path.rfind('.');
    if (dot == std::string::npos || (slash != std::string::npos && dot < slash)) return {};
    return lower_copy(path.substr(dot));
}

std::string parent_of(const std::string& path) {
    const auto slash = path.find_last_of("/\\");
    if (slash == std::string::npos) return {};
    return path.substr(0, slash + 1);
}

bool file_ok(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    return static_cast<bool>(in);
}

void write_num(std::ostream& out, double value) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6g", value);
    out << buf;
}

int usage_fail(std::ostream& err, const char* line) {
    err << line << '\n';
    return 2;
}

int cmd_kuid(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "kuid <kuid>");
    const auto raw = parse_kuid_string(argv[2]);
    if (!raw) throw std::runtime_error("not a kuid");
    out << bytes_to_kuid(raw->data(), raw->size()) << '\n';
    out << hash_folder(raw->data(), raw->size()) << '\n';
    return 0;
}

void write_parts(std::ostream& out, const std::vector<MeshPart>& parts) {
    out << "parts " << parts.size() << '\n';
    for (const MeshPart& part : parts) {
        out << "part " << part.name << " verts " << (part.positions.size() / 3) << " tris " << (part.indices.size() / 3);
        if (!part.albedo.empty()) out << " albedo " << part.albedo;
        out << '\n';
    }
}

void write_im_atts(std::ostream& out, const std::vector<ImAttachment>& atts) {
    out << "attachments " << atts.size() << '\n';
    for (const ImAttachment& att : atts) {
        out << "attachment " << att.name << ' ';
        write_num(out, att.pos[0]);
        out << ' ';
        write_num(out, att.pos[1]);
        out << ' ';
        write_num(out, att.pos[2]);
        out << '\n';
    }
}

int cmd_mesh(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "mesh <file.trainzmesh|.im|.fbx>");
    const std::string path = argv[2];
    const std::vector<uint8_t> bytes = read_bin(path);
    const std::string ext = extension_of(path);
    if (ext == ".trainzmesh") {
        const TrainzMesh mesh = parse_trainzmesh(bytes.data(), bytes.size());
        const auto mats = parse_tzmf_materials(bytes.data(), bytes.size());
        const auto atts = parse_trainzmesh_attachments(bytes.data(), bytes.size());
        out << "kind trainzmesh\nversion " << mesh.version << '\n';
        out << "parts " << mesh.submeshes.size() << '\n';
        for (const SubMesh& part : mesh.submeshes) {
            out << "part " << part.name << " verts " << (part.positions.size() / 3) << " tris " << (part.indices.size() / 3);
            if (!part.material_type.empty()) out << " type " << part.material_type;
            if (!part.albedo.empty()) out << " albedo " << part.albedo;
            out << '\n';
        }
        out << "materials " << mats.size() << '\n';
        for (const TzMaterial& mat : mats) out << "material " << mat.type_name << ' ' << mat.name << '\n';
        out << "attachments " << atts.size() << '\n';
        for (const TzAttachment& att : atts) {
            out << "attachment " << att.name << ' ';
            write_num(out, att.pos[0]);
            out << ' ';
            write_num(out, att.pos[1]);
            out << ' ';
            write_num(out, att.pos[2]);
            out << '\n';
        }
        return 0;
    }
    if (ext == ".im") {
        const ImView view = parse_im_view(bytes.data(), bytes.size());
        out << "kind im\n";
        write_parts(out, view.parts);
        write_im_atts(out, view.atts);
        return 0;
    }
    if (ext == ".fbx") {
        const ImView view = parse_fbx_view(bytes.data(), bytes.size());
        out << "kind fbx\n";
        write_parts(out, view.parts);
        write_im_atts(out, view.atts);
        return 0;
    }
    throw std::runtime_error("want .trainzmesh, .im, or .fbx");
}

int cmd_cdp(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "cdp <file.cdp> [kuid]");
    const std::vector<uint8_t> bytes = read_bin(argv[2]);
    if (argc >= 4) {
        const std::string text = asset_config_text(bytes.data(), bytes.size(), argv[3]);
        out << text;
        if (text.empty() || text.back() != '\n') out << '\n';
        return 0;
    }
    const auto assets = list_cdp_assets(bytes.data(), bytes.size());
    for (const CdpAssetEntry& asset : assets) {
        out << asset.kuid << '\n';
        if (!asset.username.empty()) out << "username " << asset.username << '\n';
        if (!asset.kind.empty()) out << "kind " << asset.kind << '\n';
        for (size_t i = 0; i < asset.files.size(); ++i) {
            out << "file " << asset.files[i];
            if (i < asset.sizes.size()) out << ' ' << asset.sizes[i];
            out << '\n';
        }
    }
    return 0;
}

bool text_bytes(const std::vector<uint8_t>& bytes) {
    const size_t n = std::min(bytes.size(), size_t{4096});
    return std::memchr(bytes.data(), 0, n) == nullptr;
}

int cmd_tzarc(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "tzarc <file.tzarc> [name]");
    const std::vector<uint8_t> bytes = read_bin(argv[2]);
    const auto entries = list_tzarc(bytes.data(), bytes.size());
    if (argc < 4) {
        for (const TzarcEntry& entry : entries) out << entry.size << ' ' << entry.name << '\n';
        return 0;
    }
    const std::vector<uint8_t> member = read_tzarc_named(bytes.data(), bytes.size(), {argv[3]});
    bool listed = false;
    const std::string want = lower_copy(argv[3]);
    for (const TzarcEntry& entry : entries) {
        std::string name = lower_copy(entry.name);
        const auto slash = name.rfind('/');
        const std::string base = slash == std::string::npos ? name : name.substr(slash + 1);
        if (name == want || base == want) listed = true;
    }
    if (!listed && member.empty()) throw std::runtime_error("no such entry");
    if (!text_bytes(member)) {
        err << "binary " << member.size() << " bytes\n";
        return 1;
    }
    out.write(reinterpret_cast<const char*>(member.data()), static_cast<std::streamsize>(member.size()));
    if (member.empty() || member.back() != '\n') out << '\n';
    return 0;
}

int cmd_chump(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "chump <file>");
    const std::vector<uint8_t> bytes = read_bin(argv[2]);
    out << chump_to_text(read_chump(bytes.data(), bytes.size()));
    return 0;
}

int cmd_zip(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "zip <file.zip>");
    const std::vector<uint8_t> bytes = read_bin(argv[2]);
    for (const ZipEntry& entry : list_zip(bytes.data(), bytes.size()))
        out << entry.size << ' ' << entry.name << '\n';
    return 0;
}

int cmd_texture(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "texture <file.texture.txt>");
    const std::string path = argv[2];
    const std::string text = read_text(path);
    const auto keys = parse_texture_txt(text);
    std::string primary;
    for (const auto& row : keys)
        if (row.first == "Primary") primary = row.second;
    int width = 0;
    int height = 0;
    bool found = false;
    if (!primary.empty()) {
        const bool abs = (primary.size() > 1 && primary[1] == ':') || primary[0] == '/' || primary[0] == '\\';
        const std::string image = abs ? primary : parent_of(path) + primary;
        found = file_ok(image);
        if (found) {
            const std::vector<uint8_t> image_bytes = read_bin(image);
            const auto size = image_size_header(image_bytes.data(), image_bytes.size(), primary);
            width = size.first;
            height = size.second;
        }
    }
    const TextureReport report = check_texture_txt(path, text, width, height, found);
    out << format_texture_report(report);
    return report.ok() ? 0 : 1;
}

int cmd_wav(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "wav <file.wav>");
    const std::string path = argv[2];
    const std::vector<uint8_t> bytes = read_bin(path);
    const PcmClip clip = read_wav_pcm16(bytes.data(), bytes.size());
    const int channels = std::max(1, clip.channels);
    const int frames = static_cast<int>(clip.samples.size() / static_cast<size_t>(channels));
    out << "rate " << clip.rate << '\n';
    out << "channels " << clip.channels << '\n';
    out << "frames " << frames << '\n';
    out << "seconds ";
    write_num(out, clip.rate > 0 ? static_cast<double>(frames) / clip.rate : 0);
    out << '\n';
    for (const QcFinding& finding : analyze_pcm(clip.samples, clip.rate, path))
        out << finding.severity << ' ' << finding.kind << ' ' << finding.message << '\n';
    return 0;
}

int cmd_engine(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "engine <enginespec>");
    const std::string text = read_text(argv[2]);
    if (!looks_like_enginespec(text)) throw std::runtime_error("not an enginespec");
    const EngineSpec spec = parse_enginespec(text);
    for (const auto& row : spec.header) out << row.first << '=' << row.second << '\n';
    for (const auto& block : spec.blocks) out << "block " << block.first << ' ' << block.second.size() << '\n';
    for (const auto& notch : spec.throttle) out << "notch " << notch.first << " points " << notch.second.size() << '\n';
    return 0;
}

int cmd_lm(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "lm <file.lm.txt>");
    const LmFile lm = parse_lm_txt(read_text(argv[2]));
    out << "version " << lm.version << '\n';
    out << "offset ";
    write_num(out, lm.offset);
    out << "\ncalcPoint " << lm.calc_point << '\n';
    out << "meshes " << lm.meshes.size() << '\n';
    for (const LmMesh& mesh : lm.meshes) {
        out << "mesh ";
        write_num(out, mesh.width);
        out << ' ' << mesh.name << '\n';
    }
    return 0;
}

int cmd_kin(int argc, char** argv, std::ostream& out, std::ostream& err) {
    if (argc < 3) return usage_fail(err, "kin <file.kin>");
    const std::vector<uint8_t> bytes = read_bin(argv[2]);
    const KinClip clip = parse_kin(bytes.data(), bytes.size());
    if (!clip.ok) throw std::runtime_error(clip.error.empty() ? "not a .kin" : clip.error);
    out << "tick " << clip.tick << '\n';
    out << "bones " << clip.bones.size() << '\n';
    for (const std::string& bone : clip.bones) out << "bone " << bone << '\n';
    out << "frames " << clip.frames.size() << '\n';
    return 0;
}

int dispatch(int argc, char** argv, std::ostream& out, std::ostream& err) {
    switch (command_of(argc >= 2 ? argv[1] : "")) {
    case Cmd::None: return -1;
    case Cmd::Help: out << usage_text(); return 0;
    case Cmd::Version: out << TRAINZ_STUDIO_VERSION << '\n'; return 0;
    case Cmd::Kuid: return cmd_kuid(argc, argv, out, err);
    case Cmd::Mesh: return cmd_mesh(argc, argv, out, err);
    case Cmd::Cdp: return cmd_cdp(argc, argv, out, err);
    case Cmd::Tzarc: return cmd_tzarc(argc, argv, out, err);
    case Cmd::Chump: return cmd_chump(argc, argv, out, err);
    case Cmd::Zip: return cmd_zip(argc, argv, out, err);
    case Cmd::Texture: return cmd_texture(argc, argv, out, err);
    case Cmd::Wav: return cmd_wav(argc, argv, out, err);
    case Cmd::Engine: return cmd_engine(argc, argv, out, err);
    case Cmd::Lm: return cmd_lm(argc, argv, out, err);
    case Cmd::Kin: return cmd_kin(argc, argv, out, err);
    }
    return -1;
}

}  // namespace

bool studio_cli_command(int argc, char** argv) {
    if (argc < 2 || argv == nullptr || argv[1] == nullptr) return false;
    return command_of(argv[1]) != Cmd::None;
}

int studio_cli(int argc, char** argv, std::ostream& out, std::ostream& err) {
    try {
        const int code = dispatch(argc, argv, out, err);
        out.flush();
        err.flush();
        return code;
    } catch (const std::exception& error) {
        err << error.what() << '\n';
        err.flush();
        return 1;
    }
}
