#undef NDEBUG
#include "cli.h"

#include "io/kuid.h"
#include "io/wav.h"

#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#ifndef FIXTURE_DIR
#define FIXTURE_DIR "checks/fixtures"
#endif

static int run(std::ostream& out, std::ostream& err, const std::vector<std::string>& args) {
    std::vector<std::string> owned = args;
    std::vector<char*> argv;
    for (std::string& arg : owned) argv.push_back(arg.data());
    return studio_cli(static_cast<int>(argv.size()), argv.data(), out, err);
}

int main() {
    std::ostringstream out;
    std::ostringstream err;
    char self[] = "trainz_studio_cpp";
    char* bare[] = {self};
    assert(!studio_cli_command(1, bare));
    assert(run(out, err, {"trainz_studio_cpp"}) == -1);

    out.str("");
    err.str("");
    char extra[] = "not-a-command";
    char* unknown[] = {self, extra};
    assert(!studio_cli_command(2, unknown));
    assert(run(out, err, {"trainz_studio_cpp", "not-a-command"}) == -1);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "help"}) == 0);
    assert(out.str().find("mesh") != std::string::npos);
    assert(out.str().find(TRAINZ_STUDIO_VERSION) != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "version"}) == 0);
    assert(out.str().find(TRAINZ_STUDIO_VERSION) != std::string::npos);

    out.str("");
    err.str("");
    const std::string kuid = "<kuid:123:456>";
    assert(run(out, err, {"trainz_studio_cpp", "kuid", kuid}) == 0);
    const auto raw = parse_kuid_string(kuid);
    assert(raw);
    assert(out.str().find(bytes_to_kuid(raw->data(), raw->size())) != std::string::npos);
    assert(out.str().find(hash_folder(raw->data(), raw->size())) != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "kuid", "nope"}) == 1);
    assert(!err.str().empty());

    const std::string dir = FIXTURE_DIR;
    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "mesh", dir + "/tri.trainzmesh"}) == 0);
    assert(out.str().find("kind trainzmesh") != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "mesh", dir + "/tri.im"}) == 0);
    assert(out.str().find("kind im") != std::string::npos);
    assert(out.str().find("part body") != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "cdp", dir + "/demo.cdp"}) == 0);
    assert(out.str().find("<kuid:1:2>") != std::string::npos);
    assert(out.str().find("note.txt") != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "tzarc", dir + "/sample.tzarc"}) == 0);
    assert(out.str().find("config.txt") != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "tzarc", dir + "/sample.tzarc", "config.txt"}) == 0);
    assert(out.str().find("hello-v1") != std::string::npos);

    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "mesh", dir + "/missing.trainzmesh"}) == 1);

    const auto wav = write_wav_pcm16(std::vector<int16_t>(8000, 1000), 8000);
    const auto wav_path = std::filesystem::temp_directory_path() / "trainz_studio_check.wav";
    {
        std::ofstream file(wav_path, std::ios::binary);
        assert(file);
        file.write(reinterpret_cast<const char*>(wav.data()), static_cast<std::streamsize>(wav.size()));
    }
    out.str("");
    err.str("");
    assert(run(out, err, {"trainz_studio_cpp", "wav", wav_path.string()}) == 0);
    assert(out.str().find("rate 8000") != std::string::npos);
    std::filesystem::remove(wav_path);

    std::printf("check_cli: ok\n");
    return 0;
}
