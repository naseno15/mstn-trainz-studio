cmake_minimum_required(VERSION 3.21)
project(trainz_studio_cpp VERSION 4.2.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Widgets OpenGLWidgets Quick QuickWidgets)

if(TRAINZ_QT_PREFIX)
    set(trainz_qt_define QT_PREFIX="${TRAINZ_QT_PREFIX}")
endif()
set(trainz_qml_define QML_DIR="${CMAKE_SOURCE_DIR}/ui/qml" I18N_DIR="${CMAKE_SOURCE_DIR}/assets/i18n")

# ponytail: one OBJECT lib so the UI .cpp files compile once. Checks link the
# same objects. A per-check compile define cannot live in these TUs — put it
# on the check .cpp only. Upgrade path: split a page out if it needs its own flags.
set(trainz_ui_sources
    src/ui/icons.cpp
    src/ui/crash_report.cpp
    src/ui/shell_window.cpp
    src/ui/status_hub.cpp
    src/ui/i18n.cpp
    src/ui/ve_rules.cpp
    src/ui/install_queue.cpp
    src/ui/trainz_meta.cpp
    src/ui/asset_preview.cpp
    src/ui/trainzutil_page.cpp
    src/ui/engine_page.cpp
    src/ui/assets_page.cpp
    src/ui/texmesh.cpp
    src/ui/sounds_page.cpp
    src/ui/wave_player.cpp
    src/ui/mesh_page.cpp
    src/ui/mesh_view.cpp
)

add_library(trainz_io STATIC
    src/io/kuid.cpp
    src/io/chump.cpp
    src/io/lzss.cpp
    src/io/cdp.cpp
    src/io/tzarc.cpp
    src/io/zip_read.cpp
    src/io/im_geom.cpp
    src/io/fbx.cpp
    src/io/trainzmesh.cpp
    third_party/ufbx/ufbx.c
    src/io/config_id.cpp
    src/io/enginespec.cpp
    src/io/wav.cpp
    src/io/texture_txt.cpp
    src/io/lm_txt.cpp
    src/io/mat_name.cpp
    third_party/puff/puff.c
)
target_include_directories(trainz_io PUBLIC src third_party/puff third_party/ufbx)
set_source_files_properties(third_party/ufbx/ufbx.c PROPERTIES SKIP_PRECOMPILE_HEADERS ON)

add_library(trainz_ui OBJECT ${trainz_ui_sources})
target_link_libraries(trainz_ui PUBLIC trainz_io Qt6::Core Qt6::Widgets Qt6::Quick Qt6::OpenGLWidgets Qt6::QuickWidgets)
if(WIN32)
    target_link_libraries(trainz_ui PUBLIC winmm)
endif()
target_include_directories(trainz_ui PUBLIC src)
target_compile_definitions(trainz_ui PUBLIC ${trainz_qml_define} ${trainz_qt_define})
target_precompile_headers(trainz_ui PRIVATE src/ui/qt_pch.h)

qt_add_executable(trainz_studio_cpp src/main.cpp)
target_link_libraries(trainz_studio_cpp PRIVATE trainz_ui)
set_target_properties(trainz_studio_cpp PROPERTIES WIN32_EXECUTABLE TRUE)

# Embed QML, i18n catalogs and the icon font so the exe is self-contained (res_path.h prefers :/studio).
file(GLOB studio_qml CONFIGURE_DEPENDS ui/qml/*.qml)
file(GLOB studio_i18n CONFIGURE_DEPENDS assets/i18n/*.json)
set(studio_font assets/fonts/MaterialIcons-Regular.ttf)
foreach(f ${studio_qml})
    get_filename_component(n ${f} NAME)
    set_source_files_properties(${f} PROPERTIES QT_RESOURCE_ALIAS qml/${n})
endforeach()
foreach(f ${studio_i18n})
    get_filename_component(n ${f} NAME)
    set_source_files_properties(${f} PROPERTIES QT_RESOURCE_ALIAS i18n/${n})
endforeach()
set_source_files_properties(${studio_font} PROPERTIES QT_RESOURCE_ALIAS fonts/MaterialIcons-Regular.ttf)
qt_add_resources(trainz_studio_cpp studio PREFIX /studio FILES ${studio_qml} ${studio_i18n} ${studio_font})

# Static Qt (tools/build_qt_static.ps1): one exe, no DLLs.
if(TRAINZ_STATIC)
    qt_import_qml_plugins(trainz_studio_cpp)
    target_link_options(trainz_studio_cpp PRIVATE -static -static-libgcc -static-libstdc++)
endif()

function(trainz_ui_check name)
    add_executable(${name} checks/${name}.cpp)
    target_link_libraries(${name} PRIVATE trainz_ui)
endfunction()

add_executable(check_boot checks/check_boot.cpp)
target_link_libraries(check_boot PRIVATE Qt6::Core Qt6::Widgets)

add_executable(check_formats checks/check_formats.cpp)
target_link_libraries(check_formats PRIVATE trainz_io)
target_compile_definitions(check_formats PRIVATE FIXTURE_DIR="${CMAKE_SOURCE_DIR}/checks/fixtures" EDITING_DIR="${CMAKE_SOURCE_DIR}/../editing")

trainz_ui_check(check_shell)
trainz_ui_check(check_ve)
trainz_ui_check(check_trainzutil)
trainz_ui_check(check_engine)
trainz_ui_check(check_sounds)
trainz_ui_check(check_mesh)
trainz_ui_check(check_assets)
target_compile_definitions(check_assets PRIVATE FIXTURE_DIR="${CMAKE_SOURCE_DIR}/checks/fixtures")

