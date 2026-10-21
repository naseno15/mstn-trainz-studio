#pragma once

#include <iosfwd>

// True when argv asks for a headless command. No command opens the window.
bool studio_cli_command(int argc, char** argv);

// -1 when there is no command. Otherwise the process exit code.
int studio_cli(int argc, char** argv, std::ostream& out, std::ostream& err);
