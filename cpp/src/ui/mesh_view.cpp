#include "mesh_view.h"

#include <QMatrix4x4>
#include <QMouseEvent>
#include <QSurfaceFormat>
#include <QVector3D>
#include <QWheelEvent>
#include <QtMath>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace {

const char* k_mesh_vert = R"(#version 330 core
layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec3 in_nrm;
layout(location = 2) in vec2 in_uv;
uniform mat4 u_mvp;
uniform mat4 u_model;
out vec3 v_nrm;
out vec2 v_uv;
out vec3 v_world;
void main() {
    vec4 world = u_model * vec4(in_pos, 1.0);
    v_world = world.xyz;
    v_nrm = mat3(u_model) * in_nrm;
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
)";

const char* k_mesh_frag = R"(#version 330 core
in vec3 v_nrm;
in vec2 v_uv;
in vec3 v_world;
out vec4 FragColor;
uniform sampler2D u_albedo;
uniform sampler2D u_env_map;
uniform sampler2D u_shadow_atlas;
uniform vec3 u_cam_pos;
uniform vec3 u_flat_color;
uniform float u_use_tex;
uniform float u_ambient;
uniform float u_emissive_scale;
uniform float u_self_illum;
uniform vec3 u_lights[5];
uniform float u_light_on[5];
uniform vec3 u_light_rad[5];
uniform int u_debug_mode;
uniform float u_two_sided;
uniform vec3 u_sky_top;
uniform vec3 u_sky_horizon;
uniform float u_ibl_strength;
uniform float u_use_env_map;
uniform int u_lamp_count;
uniform vec3 u_lamp_pos[8];
uniform vec3 u_lamp_col[8];
uniform float u_lamp_power[8];
uniform float u_lamp_range[8];
uniform int u_shadow_count;
uniform mat4 u_shadow_vp[8];

float lampShadow(vec3 world, int li) {
    if (li < 0 || li >= u_shadow_count || li >= 8) return 1.0;
    vec4 clip = u_shadow_vp[li] * vec4(world, 1.0);
    if (clip.w <= 1e-5) return 1.0;
    float iw = 1.0 / clip.w;
    vec2 uv = clip.xy * iw * 0.5 + 0.5;
    float z = clip.z * iw * 0.5 + 0.5;
    if (uv.x <= 0.001 || uv.x >= 0.999 || uv.y <= 0.001 || uv.y >= 0.999) return 1.0;
    if (z <= 0.001 || z >= 0.999) return 1.0;
    float col = mod(float(li), 4.0);
    float row = floor(float(li) / 4.0);
    vec2 tuv = vec2((col + uv.x) * 0.25, (row + uv.y) * 0.5);
    float closest = texture(u_shadow_atlas, tuv).r;
    float lit = (z - 0.0015 > closest) ? 0.0 : 1.0;
    return mix(0.08, 1.0, lit);
}

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float denom = (NdotH * NdotH * (a2 - 1.0) + 1.0);
    denom = 3.14159265 * denom * denom;
    return a2 / max(denom, 1e-6);
}
float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    return NdotV / max(NdotV * (1.0 - k) + k, 1e-6);
}
float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    return GeometrySchlickGGX(max(dot(N, V), 0.0), roughness) * GeometrySchlickGGX(max(dot(N, L), 0.0), roughness);
}
vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);
}
vec3 shadeLight(vec3 N, vec3 V, vec3 L, vec3 albedo, float roughness, float metallic, vec3 radiance) {
    vec3 H = normalize(V + L);
    float NDF = DistributionGGX(N, H, roughness);
    float G = GeometrySmith(N, V, L, roughness);
    vec3 F0 = mix(vec3(0.04), albedo, metallic);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);
    vec3 spec = (NDF * G * F) / (4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 1e-5);
    vec3 kD = (vec3(1.0) - F) * (1.0 - metallic);
    return (kD * albedo / 3.14159265 + spec) * radiance * max(dot(N, L), 0.0);
}
vec3 worldToYup(vec3 d) { return vec3(d.x, d.z, -d.y); }
vec2 dirToEquirect(vec3 d) {
    vec3 y = worldToYup(normalize(d));
    float u = atan(y.z, y.x) * 0.15915494309 + 0.5;
    float v = asin(clamp(y.y, -1.0, 1.0)) * 0.31830988618 + 0.5;
    return vec2(u, 1.0 - v);
}
vec3 sampleEnvRaw(vec3 d) {
    vec3 n = normalize(d);
    if (u_use_env_map > 0.5) return texture(u_env_map, dirToEquirect(n)).rgb;
    float skyT = clamp(n.z * 0.5 + 0.5, 0.0, 1.0);
    return mix(u_sky_horizon, u_sky_top, skyT);
}
vec3 sampleEnv(vec3 d, float roughness) {
    vec3 n = normalize(d);
    float blur = roughness * roughness * 0.07;
    vec3 c = sampleEnvRaw(n);
    if (blur < 0.0015 || u_use_env_map < 0.5) return c;
    vec3 up = abs(n.z) < 0.99 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 t = normalize(cross(up, n));
    vec3 b = cross(n, t);
    c *= 0.36;
    c += sampleEnvRaw(normalize(n + t * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n - t * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n + b * blur)) * 0.16;
    c += sampleEnvRaw(normalize(n - b * blur)) * 0.16;
    return c;
}
void main() {
    vec4 albedo = (u_use_tex > 0.5) ? texture(u_albedo, v_uv) : vec4(u_flat_color, 1.0);
    float roughness = 0.45;
    float metallic = 0.08;
    float ao = 1.0;
    vec3 N = normalize(v_nrm);
    vec3 V = normalize(u_cam_pos - v_world);
    if (u_two_sided > 0.5 && dot(N, V) < 0.0) N = -N;
    if (u_debug_mode == 1) { FragColor = vec4(albedo.rgb, 1.0); return; }
    if (u_debug_mode == 2) { FragColor = vec4(N * 0.5 + 0.5, 1.0); return; }
    if (u_debug_mode == 3) { FragColor = vec4(vec3(roughness), 1.0); return; }
    if (u_debug_mode == 4) { FragColor = vec4(vec3(metallic), 1.0); return; }
    if (u_debug_mode == 5) { FragColor = vec4(vec3(ao), 1.0); return; }
    vec3 col = vec3(0.0);
    for (int i = 0; i < 5; i++) {
        if (u_light_on[i] > 0.5)
            col += shadeLight(N, V, normalize(u_lights[i]), albedo.rgb, roughness, metallic, u_light_rad[i]);
    }
    for (int i = 0; i < 8; i++) {
        if (i >= u_lamp_count) break;
        vec3 toL = u_lamp_pos[i] - v_world;
        float dist = length(toL);
        float r = max(u_lamp_range[i], 0.05);
        if (dist < 1e-4 || dist >= r) continue;
        float fall = 1.0 - dist / r;
        fall = fall * fall;
        float sh = lampShadow(v_world, i);
        vec3 radiance = u_lamp_col[i] * (u_lamp_power[i] * fall * 3.6);
        col += shadeLight(N, V, toL / dist, albedo.rgb, roughness, metallic, radiance) * sh;
    }
    float ndv = max(dot(N, V), 0.0);
    vec3 F0 = mix(vec3(0.04), albedo.rgb, metallic);
    vec3 F = fresnelSchlick(ndv, F0);
    vec3 R = normalize(mix(reflect(-V, N), N, roughness * roughness * 0.55));
    col += sampleEnv(R, roughness) * u_ibl_strength * F * mix(1.15, 0.18, roughness * roughness) * ao;
    col += sampleEnv(N, 0.92) * u_ibl_strength * 0.62 * albedo.rgb * (1.0 - metallic) * (1.0 - F) * ao;
    col += vec3(u_ambient) * albedo.rgb * ao * 0.32;
    col += albedo.rgb * u_self_illum * (0.82 + 0.45 * pow(1.0 - ndv, 2.5));
    col = clamp((col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14), 0.0, 1.0);
    col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
    FragColor = vec4(col, 1.0);
}
)";

const char* k_sky_vert = R"(#version 330 core
layout(location = 0) in vec3 in_pos;
uniform mat4 u_mvp;
out vec3 v_dir;
void main() {
    v_dir = in_pos;
    vec4 clip = u_mvp * vec4(in_pos, 1.0);
    gl_Position = clip.xyww;
}
)";

const char* k_sky_frag = R"(#version 330 core
in vec3 v_dir;
out vec4 FragColor;
uniform sampler2D u_env_map;
uniform float u_use_env_map;
uniform vec3 u_sky_top;
uniform vec3 u_sky_horizon;
uniform vec3 u_sky_ground;
uniform float u_exposure;
vec3 worldToYup(vec3 d) { return vec3(d.x, d.z, -d.y); }
vec2 dirToEquirect(vec3 d) {
    vec3 y = worldToYup(normalize(d));
    float u = atan(y.z, y.x) * 0.15915494309 + 0.5;
    float v = asin(clamp(y.y, -1.0, 1.0)) * 0.31830988618 + 0.5;
    return vec2(u, 1.0 - v);
}
vec3 tonemapAces(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}
void main() {
    vec3 d = normalize(v_dir);
    vec3 c;
    if (u_use_env_map > 0.5) {
        c = texture(u_env_map, dirToEquirect(d)).rgb;
        c = pow(max(c, vec3(0.0)), vec3(0.96));
    } else {
        float h = d.z;
        vec3 sky = mix(u_sky_horizon, u_sky_top, smoothstep(-0.02, 0.72, h));
        c = mix(u_sky_ground, sky, smoothstep(-0.45, 0.08, h));
        c = tonemapAces(c * u_exposure);
        c = pow(c, vec3(1.0 / 2.2));
    }
    FragColor = vec4(c, 1.0);
}
)";

const char* k_depth_vert = R"(#version 330 core
layout(location = 0) in vec3 in_pos;
uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(in_pos, 1.0); }
)";

const char* k_depth_frag = R"(#version 330 core
out vec4 FragColor;
void main() { FragColor = vec4(gl_FragCoord.z); }
)";

struct Env {
    const char* key;
    float top[3];
    float horizon[3];
    float ground[3];
    float clear[3];
    float ambient;
    float ibl;
    bool map;
};

const Env k_envs[] = {
    {"none", {0.07f, 0.08f, 0.10f}, {0.38f, 0.40f, 0.46f}, {0.07f, 0.08f, 0.10f}, {0.07f, 0.08f, 0.10f}, 0.12f, 0.85f, true},
    {"studio", {0.12f, 0.13f, 0.15f}, {0.22f, 0.24f, 0.27f}, {0.16f, 0.17f, 0.19f}, {0.10f, 0.11f, 0.13f}, 0.18f, 1.25f, true},
    {"station", {0.35f, 0.48f, 0.62f}, {0.72f, 0.78f, 0.82f}, {0.32f, 0.31f, 0.30f}, {0.55f, 0.62f, 0.70f}, 0.22f, 0.55f, false},
    {"harbor", {0.18f, 0.38f, 0.58f}, {0.55f, 0.72f, 0.82f}, {0.12f, 0.28f, 0.38f}, {0.40f, 0.58f, 0.70f}, 0.20f, 0.55f, false},
    {"lake", {0.28f, 0.52f, 0.72f}, {0.78f, 0.88f, 0.92f}, {0.10f, 0.32f, 0.36f}, {0.62f, 0.78f, 0.86f}, 0.22f, 0.55f, false},
    {"mountains", {0.22f, 0.36f, 0.58f}, {0.85f, 0.78f, 0.70f}, {0.22f, 0.28f, 0.20f}, {0.55f, 0.58f, 0.62f}, 0.20f, 0.55f, false},
};

std::vector<unsigned char> softbox_rgba() {
    const int w = 128;
    const int h = 64;
    std::vector<unsigned char> px(static_cast<size_t>(w * h * 4), 18);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            unsigned char* p = px.data() + (y * w + x) * 4;
            p[0] = p[1] = p[2] = 28;
            p[3] = 255;
            const bool panel = y > 8 && y < 28 && ((x > 18 && x < 46) || (x > 82 && x < 110));
            if (panel) p[0] = p[1] = p[2] = 245;
        }
    }
    return px;
}

unsigned link_program(QOpenGLFunctions_3_3_Core* gl, const char* vert, const char* frag) {
    const auto log_shader = [&](unsigned shader, const char* stage) {
        int ok = 0;
        gl->glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
        if (ok) return;
        int len = 0;
        gl->glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &len);
        std::string text(static_cast<size_t>(std::max(len, 1)), '\0');
        gl->glGetShaderInfoLog(shader, len, nullptr, text.data());
        std::fprintf(stderr, "mesh %s shader: %s\n", stage, text.c_str());
    };
    const unsigned vs = gl->glCreateShader(GL_VERTEX_SHADER);
    const unsigned fs = gl->glCreateShader(GL_FRAGMENT_SHADER);
    gl->glShaderSource(vs, 1, &vert, nullptr);
    gl->glShaderSource(fs, 1, &frag, nullptr);
    gl->glCompileShader(vs);
    gl->glCompileShader(fs);
    log_shader(vs, "vert");
    log_shader(fs, "frag");
    const unsigned prog = gl->glCreateProgram();
    gl->glAttachShader(prog, vs);
    gl->glAttachShader(prog, fs);
    gl->glLinkProgram(prog);
    int linked = 0;
    gl->glGetProgramiv(prog, GL_LINK_STATUS, &linked);
    if (!linked) {
        int len = 0;
        gl->glGetProgramiv(prog, GL_INFO_LOG_LENGTH, &len);
        std::string text(static_cast<size_t>(std::max(len, 1)), '\0');
        gl->glGetProgramInfoLog(prog, len, nullptr, text.data());
        std::fprintf(stderr, "mesh link: %s\n", text.c_str());
    }
    gl->glDeleteShader(vs);
    gl->glDeleteShader(fs);
    return prog;
}

bool is_lamp_name(const QString& name) {
    const QString lower = name.toLower();
    return lower.contains(QLatin1String("light")) || lower.contains(QLatin1String("kuay")) || lower.contains(QLatin1String("lamp"));
}

}  // namespace

int studio_softbox_peak() {
    int peak = 0;
    for (unsigned char b : softbox_rgba()) peak = std::max(peak, static_cast<int>(b));
    return peak;
}

MeshView::MeshView(QWidget* parent) : QOpenGLWidget(parent) {
    QSurfaceFormat fmt;
    fmt.setDepthBufferSize(24);
    fmt.setVersion(3, 3);
    fmt.setProfile(QSurfaceFormat::CoreProfile);
    setFormat(fmt);
    setUpdateBehavior(QOpenGLWidget::NoPartialUpdate);
}

void MeshView::setParts(std::vector<ViewPart> parts) {
    parts_ = std::move(parts);
    lamps_.clear();
    float minb[3] = {1e9f, 1e9f, 1e9f};
    float maxb[3] = {-1e9f, -1e9f, -1e9f};
    int count = 0;
    for (const ViewPart& part : parts_) {
        float pmin[3] = {1e9f, 1e9f, 1e9f};
        float pmax[3] = {-1e9f, -1e9f, -1e9f};
        for (size_t i = 0; i + 2 < part.positions.size(); i += 3) {
            for (int a = 0; a < 3; ++a) {
                minb[a] = std::min(minb[a], part.positions[i + a]);
                maxb[a] = std::max(maxb[a], part.positions[i + a]);
                pmin[a] = std::min(pmin[a], part.positions[i + a]);
                pmax[a] = std::max(pmax[a], part.positions[i + a]);
            }
            ++count;
        }
        if (is_lamp_name(part.name) && lamps_.size() < 8 && count > 0) {
            Lamp lamp;
            lamp.pos[0] = (pmin[0] + pmax[0]) * 0.5f;
            lamp.pos[1] = (pmin[1] + pmax[1]) * 0.5f;
            lamp.pos[2] = pmin[2] - 0.03f;
            lamp.range = 8.f;
            lamps_.push_back(lamp);
        }
    }
    if (count == 0) {
        center_[0] = center_[1] = center_[2] = 0;
        radius_ = 1.f;
    } else {
        for (int a = 0; a < 3; ++a) center_[a] = (minb[a] + maxb[a]) * 0.5f;
        radius_ = std::max(0.5f, 0.5f * std::sqrt((maxb[0] - minb[0]) * (maxb[0] - minb[0]) + (maxb[1] - minb[1]) * (maxb[1] - minb[1]) + (maxb[2] - minb[2]) * (maxb[2] - minb[2])));
        for (Lamp& lamp : lamps_) lamp.range = std::max(4.f, radius_ * 1.5f);
    }
    frame_camera();
    upload_pending_ = true;
    shadow_dirty_ = true;
    update();
}

void MeshView::frame_camera() {
    target_[0] = center_[0];
    target_[1] = center_[1];
    target_[2] = center_[2];
    dist_ = radius_ * 2.4f;
    yaw_ = 35.f;
    pitch_ = 25.f;
}

void MeshView::setDebugMode(int mode) {
    debug_mode_ = std::clamp(mode, 0, 5);
    update();
}
void MeshView::setEnvironment(int index) {
    env_index_ = std::clamp(index, 0, 5);
    update();
}
void MeshView::setSun(bool on) {
    sun_ = on;
    update();
}
void MeshView::setGround(bool on) {
    ground_ = on;
    update();
}
void MeshView::resetCamera() { frame_camera(); update(); }

void MeshView::initializeGL() {
    initializeOpenGLFunctions();
    gl_ready_ = true;
    mesh_prog_ = link_program(this, k_mesh_vert, k_mesh_frag);
    sky_prog_ = link_program(this, k_sky_vert, k_sky_frag);
    depth_prog_ = link_program(this, k_depth_vert, k_depth_frag);
    glGenVertexArrays(1, &vao_);
    glGenBuffers(1, &vbo_);
    glGenBuffers(1, &ibo_);
    glGenTextures(1, &white_tex_);
    glBindTexture(GL_TEXTURE_2D, white_tex_);
    const unsigned char white[4] = {210, 214, 220, 255};
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, white);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    const auto box = softbox_rgba();
    glGenTextures(1, &env_tex_);
    glBindTexture(GL_TEXTURE_2D, env_tex_);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 128, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, box.data());
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glGenTextures(1, &shadow_tex_);
    glBindTexture(GL_TEXTURE_2D, shadow_tex_);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 512, 256, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &shadow_fbo_);
    glBindFramebuffer(GL_FRAMEBUFFER, shadow_fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, shadow_tex_, 0);
    glGenRenderbuffers(1, &shadow_depth_);
    glBindRenderbuffer(GL_RENDERBUFFER, shadow_depth_);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, 512, 256);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, shadow_depth_);
    glBindFramebuffer(GL_FRAMEBUFFER, defaultFramebufferObject());
    const float sky[18] = {-1, -1, -1, 1, -1, -1, 1, 1, -1, -1, -1, -1, 1, 1, -1, -1, 1, -1};
    glGenVertexArrays(1, &sky_vao_);
    glGenBuffers(1, &sky_vbo_);
    glBindVertexArray(sky_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, sky_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(sky), sky, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
    glGenVertexArrays(1, &ground_vao_);
    glBindVertexArray(ground_vao_);
    const float ground[] = {
        -20, -20, 0, 0, 0, 1, 0, 0, 20, -20, 0, 0, 0, 1, 1, 0, 20, 20, 0, 0, 0, 1, 1, 1,
        -20, -20, 0, 0, 0, 1, 0, 0, 20, 20, 0, 0, 0, 1, 1, 1, -20, 20, 0, 0, 0, 1, 0, 1,
    };
    glGenBuffers(1, &ground_vbo_);
    glBindBuffer(GL_ARRAY_BUFFER, ground_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(ground), ground, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 8 * sizeof(float), reinterpret_cast<void*>(3 * sizeof(float)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, 8 * sizeof(float), reinterpret_cast<void*>(6 * sizeof(float)));
    glBindVertexArray(0);
    if (upload_pending_) upload();
}

void MeshView::resizeGL(int w, int h) { glViewport(0, 0, std::max(1, w), std::max(1, h)); }

void MeshView::upload() {
    std::vector<float> verts;
    std::vector<unsigned> idx;
    part_first_.clear();
    part_count_.clear();
    unsigned base = 0;
    for (const ViewPart& part : parts_) {
        const size_t n = part.positions.size() / 3;
        std::vector<float> nrm(n * 3, 0.f);
        std::vector<unsigned> local = part.indices;
        if (local.empty()) {
            local.resize(n);
            for (unsigned i = 0; i < n; ++i) local[i] = i;
        }
        for (size_t t = 0; t + 2 < local.size(); t += 3) {
            const unsigned ia = local[t];
            const unsigned ib = local[t + 1];
            const unsigned ic = local[t + 2];
            if (ia >= n || ib >= n || ic >= n) continue;
            const float* a = part.positions.data() + ia * 3;
            const float* b = part.positions.data() + ib * 3;
            const float* c = part.positions.data() + ic * 3;
            const float e1[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]};
            const float e2[3] = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
            const float fn[3] = {e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]};
            for (unsigned id : {ia, ib, ic}) {
                nrm[id * 3] += fn[0];
                nrm[id * 3 + 1] += fn[1];
                nrm[id * 3 + 2] += fn[2];
            }
        }
        part_first_.push_back(static_cast<unsigned>(idx.size()));
        for (unsigned id : local) idx.push_back(base + id);
        part_count_.push_back(static_cast<int>(local.size()));
        for (size_t v = 0; v < n; ++v) {
            const float* p = part.positions.data() + v * 3;
            float nx = nrm[v * 3];
            float ny = nrm[v * 3 + 1];
            float nz = nrm[v * 3 + 2];
            const float len = std::sqrt(nx * nx + ny * ny + nz * nz);
            if (len > 1e-8f) {
                nx /= len;
                ny /= len;
                nz /= len;
            } else {
                nx = 0;
                ny = 0;
                nz = 1;
            }
            const float u = v < part.uvs.size() / 2 ? part.uvs[v * 2] : 0.f;
            const float vv = v < part.uvs.size() / 2 ? part.uvs[v * 2 + 1] : 0.f;
            verts.insert(verts.end(), {p[0], p[1], p[2], nx, ny, nz, u, vv});
        }
        base += static_cast<unsigned>(n);
    }
    index_total_ = static_cast<int>(idx.size());
    glBindVertexArray(vao_);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(verts.size() * sizeof(float)), verts.data(), GL_STATIC_DRAW);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo_);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, static_cast<GLsizeiptr>(idx.size() * sizeof(unsigned)), idx.data(), GL_STATIC_DRAW);
    const int stride = 8 * static_cast<int>(sizeof(float));
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<void*>(3 * sizeof(float)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, stride, reinterpret_cast<void*>(6 * sizeof(float)));
    glBindVertexArray(0);
    upload_pending_ = false;
}

void MeshView::draw_shadows() {
    shadow_count_ = 0;
    if (lamps_.empty() || index_total_ == 0) return;
    glBindFramebuffer(GL_FRAMEBUFFER, shadow_fbo_);
    glViewport(0, 0, 512, 256);
    glClearColor(1, 1, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_DEPTH_TEST);
    glUseProgram(depth_prog_);
    const int loc = glGetUniformLocation(depth_prog_, "u_mvp");
    glBindVertexArray(vao_);
    for (int i = 0; i < static_cast<int>(lamps_.size()) && i < 8; ++i) {
        const int col = i % 4;
        const int row = i / 4;
        glViewport(col * 128, row * 128, 128, 128);
        QMatrix4x4 proj;
        proj.perspective(70.f, 1.f, 0.05f, lamps_[static_cast<size_t>(i)].range);
        QMatrix4x4 view;
        const QVector3D eye(lamps_[static_cast<size_t>(i)].pos[0], lamps_[static_cast<size_t>(i)].pos[1], lamps_[static_cast<size_t>(i)].pos[2]);
        view.lookAt(eye, eye + QVector3D(0, 0, -1), QVector3D(0, 1, 0));
        const QMatrix4x4 mvp = proj * view;
        for (int k = 0; k < 16; ++k) shadow_vp_[i][k] = mvp.constData()[k];
        glUniformMatrix4fv(loc, 1, GL_FALSE, mvp.constData());
        for (size_t p = 0; p < part_count_.size(); ++p) {
            if (p < parts_.size() && is_lamp_name(parts_[p].name)) continue;
            glDrawElements(GL_TRIANGLES, part_count_[p], GL_UNSIGNED_INT, reinterpret_cast<void*>(static_cast<uintptr_t>(part_first_[p] * sizeof(unsigned))));
        }
        shadow_count_ = i + 1;
    }
    glBindFramebuffer(GL_FRAMEBUFFER, defaultFramebufferObject());
    shadow_dirty_ = false;
}

void MeshView::draw_sky() {
    const Env& env = k_envs[env_index_];
    glDisable(GL_DEPTH_TEST);
    glUseProgram(sky_prog_);
    QMatrix4x4 proj;
    proj.perspective(40.f, std::max(0.1f, float(width()) / std::max(1, height())), 0.05f, 200.f);
    const float yr = qDegreesToRadians(yaw_);
    const float pr = qDegreesToRadians(pitch_);
    const QVector3D eye(center_[0] + dist_ * std::cos(pr) * std::cos(yr), center_[1] + dist_ * std::cos(pr) * std::sin(yr), center_[2] + dist_ * std::sin(pr));
    QMatrix4x4 view;
    view.lookAt(QVector3D(0, 0, 0), QVector3D(std::cos(pr) * std::cos(yr), std::cos(pr) * std::sin(yr), std::sin(pr)) * -1.f, QVector3D(0, 0, 1));
    Q_UNUSED(eye);
    const QMatrix4x4 mvp = proj * view;
    glUniformMatrix4fv(glGetUniformLocation(sky_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
    glUniform1f(glGetUniformLocation(sky_prog_, "u_use_env_map"), env.map ? 1.f : 0.f);
    glUniform3f(glGetUniformLocation(sky_prog_, "u_sky_top"), env.top[0], env.top[1], env.top[2]);
    glUniform3f(glGetUniformLocation(sky_prog_, "u_sky_horizon"), env.horizon[0], env.horizon[1], env.horizon[2]);
    glUniform3f(glGetUniformLocation(sky_prog_, "u_sky_ground"), env.ground[0], env.ground[1], env.ground[2]);
    glUniform1f(glGetUniformLocation(sky_prog_, "u_exposure"), 1.1f);
    glUniform1i(glGetUniformLocation(sky_prog_, "u_env_map"), 3);
    glActiveTexture(GL_TEXTURE3);
    glBindTexture(GL_TEXTURE_2D, env_tex_);
    glBindVertexArray(sky_vao_);
    glDrawArrays(GL_TRIANGLES, 0, 6);
}

void MeshView::paintGL() {
    if (!gl_ready_) return;
    if (upload_pending_) upload();
    if (shadow_dirty_) draw_shadows();
    glViewport(0, 0, width(), height());
    const Env& env = k_envs[env_index_];
    glClearColor(env.clear[0], env.clear[1], env.clear[2], 1.f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    draw_sky();
    if (index_total_ <= 0) return;
    glEnable(GL_DEPTH_TEST);
    glUseProgram(mesh_prog_);
    const float yr = qDegreesToRadians(yaw_);
    const float pr = qDegreesToRadians(pitch_);
    const QVector3D eye(target_[0] + dist_ * std::cos(pr) * std::cos(yr), target_[1] + dist_ * std::cos(pr) * std::sin(yr), target_[2] + dist_ * std::sin(pr));
    QMatrix4x4 proj;
    proj.perspective(40.f, std::max(0.1f, float(width()) / std::max(1, height())), 0.05f, std::max(200.f, dist_ * 20.f));
    QMatrix4x4 view;
    view.lookAt(eye, QVector3D(target_[0], target_[1], target_[2]), QVector3D(0, 0, 1));
    QMatrix4x4 model;
    const QMatrix4x4 mvp = proj * view * model;
    glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
    glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_model"), 1, GL_FALSE, model.constData());
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_cam_pos"), eye.x(), eye.y(), eye.z());
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_ambient"), sun_ ? 0.18f : env.ambient);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_emissive_scale"), 0.15f);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_self_illum"), 0.f);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_debug_mode"), debug_mode_);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_sky_top"), env.top[0], env.top[1], env.top[2]);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_sky_horizon"), env.horizon[0], env.horizon[1], env.horizon[2]);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_ibl_strength"), env.ibl);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_env_map"), env.map ? 1.f : 0.f);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_albedo"), 0);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_env_map"), 3);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_shadow_atlas"), 4);
    const float dirs[5][3] = {{-1, 0, 0.4f}, {1, 0, 0.4f}, {0, -1, 0.3f}, {0, 1, 0.3f}, {0, 0, 1}};
    const float rads[5] = {0.95f, 0.75f, 0.85f, 0.35f, 0.40f};
    const float sun_dir[3] = {-0.6f, 0.45f, 0.66f};
    for (int i = 0; i < 5; ++i) {
        const bool on = sun_ ? (i == 0 || i == 4) : true;
        const float rad = sun_ ? (i == 0 ? 1.4f : i == 4 ? 0.28f : 0.f) : rads[i];
        const float* d = (sun_ && i == 0) ? sun_dir : dirs[i];
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lights[" + std::to_string(i) + "]").c_str()), d[0], d[1], d[2]);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_light_on[" + std::to_string(i) + "]").c_str()), on ? 1.f : 0.f);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_light_rad[" + std::to_string(i) + "]").c_str()), rad, rad, rad);
    }
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_lamp_count"), static_cast<int>(lamps_.size()));
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_shadow_count"), shadow_count_);
    for (int i = 0; i < static_cast<int>(lamps_.size()) && i < 8; ++i) {
        const auto n = std::to_string(i);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lamp_pos[" + n + "]").c_str()), lamps_[i].pos[0], lamps_[i].pos[1], lamps_[i].pos[2]);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lamp_col[" + n + "]").c_str()), 1.f, 0.62f, 0.22f);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_lamp_power[" + n + "]").c_str()), 1.6f);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_lamp_range[" + n + "]").c_str()), lamps_[i].range);
        glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, ("u_shadow_vp[" + n + "]").c_str()), 1, GL_FALSE, shadow_vp_[i]);
    }
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, white_tex_);
    glActiveTexture(GL_TEXTURE3);
    glBindTexture(GL_TEXTURE_2D, env_tex_);
    glActiveTexture(GL_TEXTURE4);
    glBindTexture(GL_TEXTURE_2D, shadow_tex_);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_tex"), 1.f);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_flat_color"), 0.72f, 0.74f, 0.78f);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_two_sided"), 0.f);
    glBindVertexArray(vao_);
    for (size_t p = 0; p < part_count_.size(); ++p)
        glDrawElements(GL_TRIANGLES, part_count_[p], GL_UNSIGNED_INT, reinterpret_cast<void*>(static_cast<uintptr_t>(part_first_[p] * sizeof(unsigned))));
    if (ground_) {
        glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_tex"), 0.f);
        glUniform3f(glGetUniformLocation(mesh_prog_, "u_flat_color"), env.ground[0], env.ground[1], env.ground[2]);
        QMatrix4x4 gmodel;
        gmodel.translate(center_[0], center_[1], center_[2] - radius_);
        gmodel.scale(std::max(1.f, radius_ * 0.15f));
        const QMatrix4x4 gmvp = proj * view * gmodel;
        glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_mvp"), 1, GL_FALSE, gmvp.constData());
        glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_model"), 1, GL_FALSE, gmodel.constData());
        glBindVertexArray(ground_vao_);
        glDrawArrays(GL_TRIANGLES, 0, 6);
    }
}

void MeshView::mousePressEvent(QMouseEvent* event) { last_ = event->pos(); }
void MeshView::mouseMoveEvent(QMouseEvent* event) {
    const QPoint d = event->pos() - last_;
    last_ = event->pos();
    if (event->buttons() & Qt::LeftButton) {
        yaw_ += d.x() * 0.4f;
        pitch_ = std::clamp(pitch_ + d.y() * 0.3f, -85.f, 85.f);
        update();
    } else if (event->buttons() & (Qt::RightButton | Qt::MiddleButton)) {
        const float s = dist_ * 0.002f;
        target_[0] -= d.x() * s;
        target_[2] += d.y() * s;
        update();
    }
}
void MeshView::wheelEvent(QWheelEvent* event) {
    const float steps = event->angleDelta().y() / 120.f;
    dist_ = std::clamp(dist_ * std::pow(0.9f, steps), radius_ * 0.2f, radius_ * 40.f);
    update();
}
