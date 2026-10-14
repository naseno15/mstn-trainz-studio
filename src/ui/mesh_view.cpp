#include "mesh_view.h"

#include <QColor>
#include <QElapsedTimer>
#include <QFont>
#include <QFontMetrics>
#include <QImage>
#include <QKeyEvent>
#include <QLabel>
#include <QMatrix4x4>
#include <QMouseEvent>
#include <QPainter>
#include <QSurfaceFormat>
#include <QTimer>
#include <QVector3D>
#include <QWheelEvent>
#include <QtMath>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
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
uniform sampler2D u_normal;
uniform sampler2D u_parameter;
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
uniform float u_face;
uniform float u_roughness;
uniform float u_metallic;
uniform float u_has_normal;
uniform float u_has_parameter;
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
uniform sampler2D u_sun_map;
uniform float u_sun_bias;
uniform float u_sun_cast;

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
    float lit = smoothstep(0.0, 0.004, closest - (z - 0.0015));
    return mix(0.08, 1.0, lit);
}

float sunShadow(vec3 world, vec3 N) {
    if (u_sun_cast < 0.5 || u_shadow_count < 1) return 1.0;
    vec4 clip = u_shadow_vp[0] * vec4(world, 1.0);
    vec2 uv = clip.xy * 0.5 + 0.5;
    float z = clip.z * 0.5 + 0.5;
    if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0) return 1.0;
    float ndl = clamp(dot(normalize(N), normalize(u_lights[0])), 0.0, 1.0);
    float bias = u_sun_bias * mix(2.6, 1.0, ndl);
    float fade = u_sun_bias * 4.0;
    vec2 texel = vec2(1.0 / 4096.0) * 1.0;
    float lit = 0.0;
    float wsum = 0.0;
    for (int y = -2; y <= 2; ++y) {
        for (int x = -2; x <= 2; ++x) {
            float w = 3.0 - abs(float(x)) - abs(float(y));
            float closest = texture(u_sun_map, uv + vec2(float(x), float(y)) * texel).r;
            lit += w * (1.0 - smoothstep(bias, bias + fade, z - closest));
            wsum += w;
        }
    }
    return lit / max(wsum, 1e-4);
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
vec3 getNormalFromMap(vec3 N) {
    vec3 tangentNormal = texture(u_normal, v_uv).xyz;
    tangentNormal.y = abs(tangentNormal.y - 1.0);
    tangentNormal = tangentNormal * 2.0 - 1.0;
    vec3 Q1 = dFdx(v_world);
    vec3 Q2 = dFdy(v_world);
    vec2 st1 = dFdx(v_uv);
    vec2 st2 = dFdy(v_uv);
    vec3 N0 = normalize(N);
    vec3 T = normalize(Q1 * st2.t - Q2 * st1.t);
    vec3 B = -normalize(cross(N0, T));
    return normalize(mat3(T, B, N0) * tangentNormal);
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
    if (albedo.a < 0.04) discard;
    float roughness = 0.55;
    float metallic = 0.0;
    float ao = 1.0;
    float emissive = 0.0;
    if (u_has_parameter > 0.5) {
        vec4 p = texture(u_parameter, v_uv);
        emissive = p.r;
        roughness = clamp(p.g, 0.04, 1.0);
        ao = p.b;
        metallic = p.a;
    }
    vec3 N = normalize(v_nrm);
    if (u_has_normal > 0.5) N = getNormalFromMap(N);
    vec3 V = normalize(u_cam_pos - v_world);
    if (u_two_sided > 0.5 && dot(N, V) < 0.0) N = -N;
    if (u_face > 0.5) {
        bool front = gl_FrontFacing || u_two_sided > 0.5;
        FragColor = vec4(front ? vec3(0.16, 0.82, 0.28) : vec3(0.90, 0.16, 0.14), 1.0);
        return;
    }
    if (u_debug_mode == 1) { FragColor = vec4(albedo.rgb, 1.0); return; }
    if (u_debug_mode == 2) { FragColor = vec4(N * 0.5 + 0.5, 1.0); return; }
    if (u_debug_mode == 3) { FragColor = vec4(vec3(roughness), 1.0); return; }
    if (u_debug_mode == 4) { FragColor = vec4(vec3(metallic), 1.0); return; }
    if (u_debug_mode == 5) { FragColor = vec4(vec3(ao), 1.0); return; }
    vec3 col = vec3(0.0);
    float sunSh = sunShadow(v_world, N);
    vec3 key = vec3(0.0);
    vec3 fill = vec3(0.0);
    for (int i = 0; i < 5; i++) {
        if (u_light_on[i] < 0.5) continue;
        vec3 lit = shadeLight(N, V, normalize(u_lights[i]), albedo.rgb, roughness, metallic, u_light_rad[i]);
        if (i == 0) key += lit;
        else fill += lit;
    }
    col += key * mix(0.18, 1.0, sunSh) + fill;
    for (int i = 0; i < 8; i++) {
        if (i >= u_lamp_count) break;
        vec3 toL = u_lamp_pos[i] - v_world;
        float dist = length(toL);
        float r = max(u_lamp_range[i], 0.05);
        if (dist < 1e-4 || dist >= r) continue;
        float fall = 1.0 - dist / r;
        fall = fall * fall;
        float sh = lampShadow(v_world, i + 1);
        vec3 radiance = u_lamp_col[i] * (u_lamp_power[i] * fall * 3.6);
        col += shadeLight(N, V, toL / dist, albedo.rgb, roughness, metallic, radiance) * sh;
    }
    float ndv = max(dot(N, V), 0.0);
    vec3 F0 = mix(vec3(0.04), albedo.rgb, metallic);
    vec3 F = fresnelSchlick(ndv, F0);
    vec3 R = normalize(mix(reflect(-V, N), N, roughness * roughness * 0.55));
    col += sampleEnv(R, roughness) * u_ibl_strength * F * mix(1.15, 0.18, roughness * roughness) * ao;
    float occ = mix(0.74, 1.0, sunSh);
    col += sampleEnv(N, 0.92) * u_ibl_strength * 0.62 * albedo.rgb * (1.0 - metallic) * (1.0 - F) * ao * occ;
    col += vec3(u_ambient) * albedo.rgb * ao * 0.32 * occ;
    col += albedo.rgb * emissive * u_emissive_scale;
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
layout(location = 1) in vec3 in_nrm;
uniform mat4 u_mvp;
uniform vec3 u_light;
uniform float u_thick;
void main() {
    vec3 L = normalize(u_light);
    vec3 n = normalize(in_nrm);
    vec3 side = n - L * dot(n, L);
    float sl = length(side);
    if (sl > 1e-4) side /= sl;
    float grazing = smoothstep(0.55, 0.05, abs(dot(n, L)));
    gl_Position = u_mvp * vec4(in_pos + side * (u_thick * grazing), 1.0);
}
)";

const char* k_depth_frag = R"(#version 330 core
out vec4 FragColor;
uniform float u_esm;
void main() {
    float z = gl_FragCoord.z;
    FragColor = vec4(u_esm > 0.5 ? exp(48.0 * (z - 1.0)) : z);
}
)";

const char* k_label_vert = R"(#version 330 core
layout(location = 0) in vec2 in_pos;
layout(location = 1) in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
)";

const char* k_label_frag = R"(#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 FragColor;
void main() { FragColor = texture(u_tex, v_uv); }
)";

const char* k_line_vert = R"(#version 330 core
layout(location = 0) in vec3 in_pos;
layout(location = 1) in vec3 in_col;
uniform mat4 u_mvp;
out vec3 v_col;
void main() {
    v_col = in_col;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
)";

const char* k_line_frag = R"(#version 330 core
in vec3 v_col;
out vec4 FragColor;
void main() { FragColor = vec4(v_col, 1.0); }
)";

const char* k_glow_vert = R"(#version 330 core
layout(location = 0) in vec3 in_pos;
uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(in_pos, 1.0); }
)";

const char* k_glow_frag = R"(#version 330 core
out vec4 FragColor;
uniform vec4 u_color;
void main() { FragColor = u_color; }
)";

void sun_rgb(float elevation_deg, float rgb[3]) {
    const float u = std::clamp((elevation_deg + 6.f) / 58.f, 0.f, 1.f);
    const float k = u * u * (3.f - 2.f * u);
    rgb[0] = 1.f;
    rgb[1] = 0.38f + (0.96f - 0.38f) * k;
    rgb[2] = 0.10f + (0.88f - 0.10f) * k;
}

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
            const float u = x / float(w);
            const float v = y / float(h);
            float r = 22.f + 18.f * v;
            float g = 24.f + 16.f * v;
            float b = 28.f + 14.f * v;
            auto add = [&](float cx, float cy, float rx, float ry, float ar, float ag, float ab) {
                const float dx = (u - cx) / rx;
                const float dy = (v - cy) / ry;
                const float e = std::exp(-(dx * dx + dy * dy));
                r += ar * e;
                g += ag * e;
                b += ab * e;
            };
            add(0.50f, 0.22f, 0.28f, 0.16f, 210.f, 214.f, 220.f);
            add(0.22f, 0.38f, 0.14f, 0.22f, 230.f, 150.f, 90.f);
            add(0.78f, 0.40f, 0.16f, 0.20f, 70.f, 110.f, 180.f);
            p[0] = static_cast<unsigned char>(std::clamp(r, 0.f, 255.f));
            p[1] = static_cast<unsigned char>(std::clamp(g, 0.f, 255.f));
            p[2] = static_cast<unsigned char>(std::clamp(b, 0.f, 255.f));
            p[3] = 255;
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
    if (!linked) {
        gl->glDeleteProgram(prog);
        return 0;
    }
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
    setFocusPolicy(Qt::StrongFocus);
    clock_.start();
    fps_clock_.start();
    fps_ = new QLabel(this);
    fps_->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    fps_->setStyleSheet(QStringLiteral("color:#48ff78;background:rgba(0,0,0,150);border-radius:4px;padding:5px 8px;font-family:Consolas,monospace;font-size:11px;"));
    fps_->hide();
    coast_ = new QTimer(this);
    coast_->setInterval(16);
    connect(coast_, &QTimer::timeout, this, [this] { coast(); });
}

void MeshView::setParts(std::vector<ViewPart> parts) {
    parts_ = std::move(parts);
    highlight_.clear();
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
        const float span = std::sqrt((maxb[0] - minb[0]) * (maxb[0] - minb[0]) + (maxb[1] - minb[1]) * (maxb[1] - minb[1]) + (maxb[2] - minb[2]) * (maxb[2] - minb[2]));
        radius_ = std::max(0.05f, 0.5f * span);
        for (Lamp& lamp : lamps_) lamp.range = std::max(4.f, radius_ * 1.5f);
    }
    shown_.assign(parts_.size(), 1);
    frame_camera();
    rebuild_guides();
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
    spin_yaw_ = spin_pitch_ = zoom_v_ = elev_v_ = 0.f;
    move_v_[0] = move_v_[1] = move_v_[2] = 0.f;
    if (coast_) coast_->stop();
    pitch_ = 25.f;
    emit cameraMoved();
}

void MeshView::setDebugMode(int mode) {
    debug_mode_ = std::clamp(mode, 0, 5);
    update();
}
void MeshView::setShade(int mode) {
    shade_ = std::clamp(mode, 0, 3);
    update();
}
void MeshView::setEnvironment(int index) {
    env_index_ = std::clamp(index, 0, 5);
    update();
}
void MeshView::setSun(bool on) {
    sun_ = on;
    shadow_dirty_ = true;
    update();
}
void MeshView::setSunPose(float azimuth_deg, float elevation_deg, float intensity) {
    sun_az_ = azimuth_deg;
    sun_el_ = elevation_deg;
    sun_int_ = std::max(0.f, intensity);
    shadow_dirty_ = true;
    update();
}
void MeshView::setArrayLight(int index, bool on) {
    if (index < 0 || index > 4) return;
    array_on_[index] = on;
    shadow_dirty_ = true;
    update();
}
void MeshView::setEmissiveScale(float scale) {
    emis_scale_ = std::max(0.f, scale);
    update();
}
void MeshView::setMoon(bool on) {
    moon_ = on;
    update();
}
void MeshView::setSunWarm(float warm) {
    sun_warm_ = std::clamp(warm, 0.f, 1.f);
    update();
}
void MeshView::setGround(bool on) {
    ground_ = on;
    update();
}
void MeshView::setTwoSided(bool on) {
    two_sided_ = on;
    for (ViewPart& part : parts_) part.two_sided = on;
    update();
}
void MeshView::setPartTwo(int index, bool on) {
    if (index < 0 || index >= static_cast<int>(parts_.size())) return;
    parts_[static_cast<size_t>(index)].two_sided = on;
    update();
}
void MeshView::setAttNames(bool on) {
    att_names_ = on;
    update();
}

void MeshView::setAnimMatrix(const QMatrix4x4& model) {
    anim_model_ = model;
    update();
}

void MeshView::paint_att_names(const QMatrix4x4& proj, const QMatrix4x4& view) {
    if (!att_names_ || atts_.empty() || label_prog_ == 0) return;
    int fbw = 1;
    int fbh = 1;
    fb_size(&fbw, &fbh);
    const qreal dpr = devicePixelRatioF();
    const QMatrix4x4 mvp = proj * view * anim_model_;
    auto label_for = [&](const QString& name, bool hot) -> AttLabel {
        const QString key = name + QLatin1Char(hot ? '1' : '0') + QString::number(int(std::lround(dpr * 100)));
        if (att_labels_.contains(key)) return att_labels_.value(key);
        QFont font;
        font.setPixelSize(std::max(12, static_cast<int>(std::lround(13 * dpr))));
        font.setBold(true);
        const QFontMetrics fm(font);
        const int pad_x = std::max(6, fm.horizontalAdvance(QStringLiteral("a")) / 2);
        const int pad_y = std::max(3, int(std::lround(2 * dpr)));
        const int tw = fm.horizontalAdvance(name);
        const int th = fm.height();
        QImage img(tw + pad_x * 2, th + pad_y * 2, QImage::Format_RGBA8888_Premultiplied);
        img.fill(Qt::transparent);
        QPainter painter(&img);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setRenderHint(QPainter::TextAntialiasing);
        painter.setFont(font);
        painter.setPen(Qt::NoPen);
        painter.setBrush(hot ? QColor(255, 244, 230, 235) : QColor(8, 8, 12, 220));
        painter.drawRoundedRect(QRectF(0.5, 0.5, img.width() - 1, img.height() - 1), 5 * dpr, 5 * dpr);
        painter.setPen(hot ? QColor(20, 16, 12) : QColor(255, 255, 255));
        painter.drawText(img.rect(), Qt::AlignCenter, name);
        painter.end();
        // GL reads the first row as the bottom of the texture. Flip so the top of the word stays the top of the quad.
        const QImage rgba = img.mirrored(false, true).convertToFormat(QImage::Format_RGBA8888);
        AttLabel slot;
        slot.w = rgba.width();
        slot.h = rgba.height();
        glGenTextures(1, &slot.tex);
        glBindTexture(GL_TEXTURE_2D, slot.tex);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        glPixelStorei(GL_UNPACK_ROW_LENGTH, rgba.bytesPerLine() / 4);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, rgba.width(), rgba.height(), 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.constBits());
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        att_labels_.insert(key, slot);
        return slot;
    };
    bind_widget_target();
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(label_prog_);
    glUniform1i(glGetUniformLocation(label_prog_, "u_tex"), 0);
    glActiveTexture(GL_TEXTURE0);
    glBindVertexArray(label_vao_);
    const float gap = float(std::lround(4 * dpr));
    for (size_t i = 0; i < atts_.size(); ++i) {
        const ViewAtt& att = atts_[i];
        if (att.name.isEmpty()) continue;
        if (att.file >= 0 && att.file < static_cast<int>(att_on_.size()) && !att_on_[static_cast<size_t>(att.file)]) continue;
        const QVector3D clip = mvp.map(QVector3D(att.pos[0], att.pos[1], att.pos[2]));
        if (clip.z() < -1.f || clip.z() > 1.f) continue;
        const AttLabel slot = label_for(att.name, static_cast<int>(i) == att_sel_);
        if (slot.tex == 0) continue;
        const float sx = (clip.x() * 0.5f + 0.5f) * float(fbw);
        const float sy = (0.5f - clip.y() * 0.5f) * float(fbh);
        const float left = sx - slot.w * 0.5f;
        const float top = sy - slot.h - gap;
        const float right = left + slot.w;
        const float bottom = top + slot.h;
        auto nx = [&](float x) { return x / float(fbw) * 2.f - 1.f; };
        auto ny = [&](float y) { return 1.f - y / float(fbh) * 2.f; };
        const float quad[] = {
            nx(left), ny(top), 0.f, 1.f, nx(left), ny(bottom), 0.f, 0.f, nx(right), ny(top), 1.f, 1.f,
            nx(right), ny(top), 1.f, 1.f, nx(left), ny(bottom), 0.f, 0.f, nx(right), ny(bottom), 1.f, 0.f,
        };
        glBindTexture(GL_TEXTURE_2D, slot.tex);
        glBindBuffer(GL_ARRAY_BUFFER, label_vbo_);
        glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_DYNAMIC_DRAW);
        glDrawArrays(GL_TRIANGLES, 0, 6);
    }
    glBindVertexArray(0);
    glDisable(GL_BLEND);
}

void MeshView::setFaceOrient(bool on) {
    face_orient_ = on;
    update();
}
void MeshView::setHighlight(std::vector<uint8_t> on) {
    highlight_ = std::move(on);
    update();
}

void MeshView::setShown(int index, bool on) {
    if (index < 0 || index >= static_cast<int>(shown_.size())) return;
    shown_[static_cast<size_t>(index)] = on ? 1 : 0;
    update();
}
void MeshView::resetCamera() { fly_on_ = false; fov_ = 40.f; frame_camera(); update(); }

void MeshView::orbitDrag(float dx_px, float dy_px) {
    fly_on_ = false;
    fly_orient_ = false;
    spin_yaw_ = spin_pitch_ = 0.f;
    yaw_ -= dx_px * 0.45f;
    pitch_ = std::clamp(pitch_ + dy_px * 0.45f, -85.f, 85.f);
    update();
    emit cameraMoved();
}

void MeshView::lookAxis(int axis) {
    float yaw = yaw_;
    float pitch = pitch_;
    switch (axis) {
    case 0: yaw = 0.f; pitch = 0.f; break;
    case 1: yaw = 180.f; pitch = 0.f; break;
    case 2: yaw = 90.f; pitch = 0.f; break;
    case 3: yaw = -90.f; pitch = 0.f; break;
    case 4: pitch = 85.f; break;
    case 5: pitch = -85.f; break;
    default: return;
    }
    float turn = yaw - yaw_;
    while (turn > 180.f) turn -= 360.f;
    while (turn < -180.f) turn += 360.f;
    spin_yaw_ = spin_pitch_ = 0.f;
    fly_from_[0] = fly_to_[0] = target_[0];
    fly_from_[1] = fly_to_[1] = target_[1];
    fly_from_[2] = fly_to_[2] = target_[2];
    fly_from_[3] = fly_to_[3] = dist_;
    fly_yaw0_ = yaw_;
    fly_yaw1_ = yaw_ + turn;
    fly_pitch0_ = pitch_;
    fly_pitch1_ = pitch;
    fly_orient_ = true;
    fly_on_ = true;
    fly_clock_.start();
    kick_coast();
}

void MeshView::navTips(float out[9]) const {
    const float yr = qDegreesToRadians(yaw_);
    const float pr = qDegreesToRadians(pitch_);
    const QVector3D eye(std::cos(pr) * std::cos(yr), std::cos(pr) * std::sin(yr), std::sin(pr));
    QMatrix4x4 cam;
    cam.lookAt(eye, QVector3D(0, 0, 0), QVector3D(0, 0, 1));
    const QVector3D axes[3] = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
    for (int i = 0; i < 3; ++i) {
        const QVector3D v = cam.mapVector(axes[i]);
        out[i * 3] = v.x();
        out[i * 3 + 1] = -v.y();
        out[i * 3 + 2] = v.z();
    }
}

void MeshView::flyToHighlight() {
    QVector3D lo(1e30f, 1e30f, 1e30f), hi(-1e30f, -1e30f, -1e30f);
    bool any = false;
    for (size_t p = 0; p < parts_.size() && p < highlight_.size(); ++p) {
        if (!highlight_[p] || (p < shown_.size() && !shown_[p])) continue;
        const std::vector<float>& v = parts_[p].positions;
        for (size_t i = 0; i + 2 < v.size(); i += 3) {
            const QVector3D q(v[i], v[i + 1], v[i + 2]);
            lo = QVector3D(std::min(lo.x(), q.x()), std::min(lo.y(), q.y()), std::min(lo.z(), q.z()));
            hi = QVector3D(std::max(hi.x(), q.x()), std::max(hi.y(), q.y()), std::max(hi.z(), q.z()));
            any = true;
        }
    }
    if (!any) return;
    const QVector3D c = (lo + hi) * 0.5f;
    const float r = (hi - lo).length() * 0.5f;
    fly_from_[0] = target_[0]; fly_from_[1] = target_[1]; fly_from_[2] = target_[2]; fly_from_[3] = dist_;
    fly_to_[0] = c.x(); fly_to_[1] = c.y(); fly_to_[2] = c.z();
    fly_to_[3] = std::clamp(r * 3.0f, std::max(0.05f, radius_ * 0.2f), std::max(radius_ * 8.f, 1.f));
    spin_yaw_ = spin_pitch_ = zoom_v_ = elev_v_ = 0.f;
    move_v_[0] = move_v_[1] = move_v_[2] = 0.f;
    fly_on_ = true;
    fly_clock_.start();
    kick_coast();
}

int MeshView::pick_part(const QPoint& pos) const {
    if (width() < 2 || height() < 2) return -1;
    const float yr = qDegreesToRadians(yaw_), pr = qDegreesToRadians(pitch_);
    const QVector3D eye(target_[0] + dist_ * std::cos(pr) * std::cos(yr), target_[1] + dist_ * std::cos(pr) * std::sin(yr), target_[2] + dist_ * std::sin(pr));
    const float near_p = std::max(0.001f, radius_ * 0.008f);
    const float far_p = std::max(near_p * 100.f, std::max(dist_ * 40.f, 120.f));
    QMatrix4x4 proj, view;
    proj.perspective(fov_, std::max(0.1f, float(width()) / float(height())), near_p, far_p);
    view.lookAt(eye, QVector3D(target_[0], target_[1], target_[2]), QVector3D(0, 0, 1));
    const QMatrix4x4 inv = (proj * view).inverted();
    const float nx = 2.f * pos.x() / width() - 1.f, ny = 1.f - 2.f * pos.y() / height();
    const QVector3D a = inv.map(QVector3D(nx, ny, -1.f)), b = inv.map(QVector3D(nx, ny, 1.f));
    const QVector3D o = a, d = (b - a).normalized();
    int best = -1;
    float best_t = 1e30f;
    for (size_t p = 0; p < parts_.size(); ++p) {
        if (p < shown_.size() && !shown_[p]) continue;
        const std::vector<float>& v = parts_[p].positions;
        const std::vector<uint32_t>& ix = parts_[p].indices;
        for (size_t k = 0; k + 2 < ix.size(); k += 3) {
            if (size_t(ix[k]) * 3 + 2 >= v.size() || size_t(ix[k + 1]) * 3 + 2 >= v.size() || size_t(ix[k + 2]) * 3 + 2 >= v.size()) continue;
            const QVector3D p0(v[ix[k] * 3], v[ix[k] * 3 + 1], v[ix[k] * 3 + 2]);
            const QVector3D e1 = QVector3D(v[ix[k + 1] * 3], v[ix[k + 1] * 3 + 1], v[ix[k + 1] * 3 + 2]) - p0;
            const QVector3D e2 = QVector3D(v[ix[k + 2] * 3], v[ix[k + 2] * 3 + 1], v[ix[k + 2] * 3 + 2]) - p0;
            const QVector3D h = QVector3D::crossProduct(d, e2);
            const float det = QVector3D::dotProduct(e1, h);
            if (std::abs(det) < 1e-12f) continue;  // two-sided hit test
            const QVector3D s = o - p0;
            const float u = QVector3D::dotProduct(s, h) / det;
            if (u < 0.f || u > 1.f) continue;
            const QVector3D q = QVector3D::crossProduct(s, e1);
            const float w = QVector3D::dotProduct(d, q) / det;
            if (w < 0.f || u + w > 1.f) continue;
            const float t = QVector3D::dotProduct(e2, q) / det;
            if (t > 0.f && t < best_t) { best_t = t; best = int(p); }
        }
    }
    return best;
}

int MeshView::pick_att(const QPoint& pos, int* axis_hit) const {
    if (axis_hit) *axis_hit = -1;
    if (atts_.empty() || width() < 2 || height() < 2) return -1;
    const float yr = qDegreesToRadians(yaw_), pr = qDegreesToRadians(pitch_);
    const QVector3D eye(target_[0] + dist_ * std::cos(pr) * std::cos(yr), target_[1] + dist_ * std::cos(pr) * std::sin(yr), target_[2] + dist_ * std::sin(pr));
    const float near_p = std::max(0.001f, radius_ * 0.008f);
    const float far_p = std::max(near_p * 100.f, std::max(dist_ * 40.f, 120.f));
    QMatrix4x4 proj, view;
    proj.perspective(fov_, std::max(0.1f, float(width()) / float(height())), near_p, far_p);
    view.lookAt(eye, QVector3D(target_[0], target_[1], target_[2]), QVector3D(0, 0, 1));
    const QMatrix4x4 mvp = proj * view * anim_model_;
    const QPointF cursor(pos);
    // Drawn axes are 2px. A few pixels of slop, not a sphere around the point.
    const float slop = move_tool_ ? 6.f : 3.f;
    auto project = [&](const QVector3D& p, QPointF* out) {
        const QVector4D c = mvp * QVector4D(p, 1.f);
        if (c.w() <= 1e-4f) return false;
        const float iw = 1.f / c.w();
        *out = QPointF((c.x() * iw * 0.5f + 0.5f) * width(), (0.5f - c.y() * iw * 0.5f) * height());
        return true;
    };
    auto along = [](const QPointF& a, const QPointF& b, const QPointF& p) {
        const QPointF ab = b - a;
        const float len2 = float(QPointF::dotProduct(ab, ab));
        const float t = len2 < 1e-4f ? 0.f : std::clamp(float(QPointF::dotProduct(p - a, ab) / len2), 0.f, 1.f);
        const QPointF dlt = p - (a + ab * t);
        return float(std::sqrt(QPointF::dotProduct(dlt, dlt)));
    };
    int best = -1;
    float best_px = slop;
    const float length = std::max(0.12f, radius_ * 0.08f);
    for (size_t i = 0; i < atts_.size(); ++i) {
        const ViewAtt& att = atts_[i];
        if (att.file >= 0 && att.file < static_cast<int>(att_on_.size()) && !att_on_[static_cast<size_t>(att.file)]) continue;
        const float len = length * (static_cast<int>(i) == att_sel_ ? 1.6f : 1.f);
        const QVector3D origin(att.pos[0], att.pos[1], att.pos[2]);
        QPointF a;
        if (!project(origin, &a)) continue;
        const QPointF to_origin = cursor - a;
        const float origin_px = float(std::sqrt(QPointF::dotProduct(to_origin, to_origin)));
        if (origin_px <= best_px) {
            best_px = origin_px;
            best = static_cast<int>(i);
            if (axis_hit) *axis_hit = -1;
        }
        for (int axis = 0; axis < 3; ++axis) {
            QVector3D dir(att.orient[axis * 3], att.orient[axis * 3 + 1], att.orient[axis * 3 + 2]);
            if (dir.lengthSquared() < 1e-8f) continue;
            QPointF b;
            if (!project(origin + dir.normalized() * len, &b)) continue;
            const float px = along(a, b, cursor);
            // Near the origin every axis is close; keep the free move there.
            if (px < best_px && origin_px > slop) {
                best_px = px;
                best = static_cast<int>(i);
                if (axis_hit) *axis_hit = axis;
            }
        }
    }
    return best;
}

bool MeshView::mouse_ray(const QPoint& pos, QVector3D* origin, QVector3D* dir, QVector3D* forward) const {
    if (width() < 2 || height() < 2) return false;
    const float yr = qDegreesToRadians(yaw_), pr = qDegreesToRadians(pitch_);
    const QVector3D eye(target_[0] + dist_ * std::cos(pr) * std::cos(yr), target_[1] + dist_ * std::cos(pr) * std::sin(yr), target_[2] + dist_ * std::sin(pr));
    const QVector3D target(target_[0], target_[1], target_[2]);
    const float near_p = std::max(0.001f, radius_ * 0.008f);
    const float far_p = std::max(near_p * 100.f, std::max(dist_ * 40.f, 120.f));
    QMatrix4x4 proj, view;
    proj.perspective(fov_, std::max(0.1f, float(width()) / float(height())), near_p, far_p);
    view.lookAt(eye, target, QVector3D(0, 0, 1));
    bool ok = false;
    const QMatrix4x4 inv = (proj * view * anim_model_).inverted(&ok);
    if (!ok) return false;
    const float nx = 2.f * float(pos.x()) / float(width()) - 1.f;
    const float ny = 1.f - 2.f * float(pos.y()) / float(height());
    const QVector4D a = inv * QVector4D(nx, ny, -1.f, 1.f);
    const QVector4D b = inv * QVector4D(nx, ny, 1.f, 1.f);
    if (std::abs(a.w()) < 1e-9f || std::abs(b.w()) < 1e-9f) return false;
    *origin = a.toVector3D() / a.w();
    *dir = (b.toVector3D() / b.w() - *origin).normalized();
    *forward = (anim_model_.inverted().mapVector(target - eye)).normalized();
    return true;
}

// Where the cursor lands on the drag constraint (axis line or view plane through drag_from_).
bool MeshView::drag_point(const QPoint& pos, QVector3D* out) const {
    QVector3D o, r, fwd;
    if (!mouse_ray(pos, &o, &r, &fwd)) return false;
    if (drag_axis_ < 0) {
        const float den = QVector3D::dotProduct(fwd, r);
        if (std::abs(den) < 1e-6f) return false;
        *out = o + r * (QVector3D::dotProduct(fwd, drag_from_ - o) / den);
        return true;
    }
    const ViewAtt& att = atts_[static_cast<size_t>(drag_att_)];
    const QVector3D d = QVector3D(att.orient[drag_axis_ * 3], att.orient[drag_axis_ * 3 + 1], att.orient[drag_axis_ * 3 + 2]).normalized();
    const QVector3D w0 = drag_from_ - o;
    const float b = QVector3D::dotProduct(d, r), dd = QVector3D::dotProduct(d, w0), e = QVector3D::dotProduct(r, w0);
    const float den = 1.f - b * b;
    if (std::abs(den) < 1e-6f) return false;
    *out = drag_from_ + d * ((b * e - dd) / den);
    return true;
}

void MeshView::setMoveTool(bool on) {
    move_tool_ = on;
    if (!on) drag_att_ = -1;
    atts_dirty_ = true;
    update();
}

void MeshView::initializeGL() {
    if (!initializeOpenGLFunctions()) {
        std::fprintf(stderr, "mesh GL 3.3 functions missing\n");
        return;
    }
    gl_ready_ = true;
    mesh_prog_ = link_program(this, k_mesh_vert, k_mesh_frag);
    sky_prog_ = link_program(this, k_sky_vert, k_sky_frag);
    depth_prog_ = link_program(this, k_depth_vert, k_depth_frag);
    line_prog_ = link_program(this, k_line_vert, k_line_frag);
    glow_prog_ = link_program(this, k_glow_vert, k_glow_frag);
    label_prog_ = link_program(this, k_label_vert, k_label_frag);
    glGenVertexArrays(1, &label_vao_);
    glGenBuffers(1, &label_vbo_);
    glBindVertexArray(label_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, label_vbo_);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), reinterpret_cast<void*>(2 * sizeof(float)));
    glBindVertexArray(0);
    std::vector<float> disc;
    disc.insert(disc.end(), {0.f, 0.f, 0.f});
    for (int i = 0; i <= 28; ++i) {
        const float a = float(i) / 28.f * 6.2831853f;
        disc.push_back(std::cos(a));
        disc.push_back(std::sin(a));
        disc.push_back(0.f);
    }
    glGenVertexArrays(1, &glow_vao_);
    glGenBuffers(1, &glow_vbo_);
    glBindVertexArray(glow_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, glow_vbo_);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(disc.size() * sizeof(float)), disc.data(), GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, nullptr);
    glBindVertexArray(0);
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
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, 2048, 1024, 0, GL_RED, GL_FLOAT, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &shadow_fbo_);
    glBindFramebuffer(GL_FRAMEBUFFER, shadow_fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, shadow_tex_, 0);
    glGenRenderbuffers(1, &shadow_depth_);
    glBindRenderbuffer(GL_RENDERBUFFER, shadow_depth_);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, 2048, 1024);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, shadow_depth_);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        std::fprintf(stderr, "mesh shadow FBO incomplete\n");
        glDeleteFramebuffers(1, &shadow_fbo_);
        shadow_fbo_ = 0;
    }
    glGenTextures(1, &sun_tex_);
    glBindTexture(GL_TEXTURE_2D, sun_tex_);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R32F, 4096, 4096, 0, GL_RED, GL_FLOAT, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glGenFramebuffers(1, &sun_fbo_);
    glBindFramebuffer(GL_FRAMEBUFFER, sun_fbo_);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, sun_tex_, 0);
    glGenRenderbuffers(1, &sun_depth_);
    glBindRenderbuffer(GL_RENDERBUFFER, sun_depth_);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, 4096, 4096);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, sun_depth_);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        std::fprintf(stderr, "mesh sun shadow FBO incomplete\n");
        glDeleteFramebuffers(1, &sun_fbo_);
        sun_fbo_ = 0;
    }
    bind_widget_target();
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
    const float gizmo[] = {
        0, 0, 0, 0.95f, 0.22f, 0.18f, 1, 0, 0, 0.95f, 0.22f, 0.18f, 0, 0, 0, 0.22f, 0.82f, 0.28f, 0, 1, 0, 0.22f, 0.82f, 0.28f,
        0, 0, 0, 0.28f, 0.48f, 0.95f, 0, 0, 1, 0.28f, 0.48f, 0.95f,
    };
    glGenVertexArrays(1, &gizmo_vao_);
    glGenBuffers(1, &gizmo_vbo_);
    glBindVertexArray(gizmo_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, gizmo_vbo_);
    glBufferData(GL_ARRAY_BUFFER, sizeof(gizmo), gizmo, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), reinterpret_cast<void*>(3 * sizeof(float)));
    glGenVertexArrays(1, &line_vao_);
    glGenBuffers(1, &line_vbo_);
    glGenVertexArrays(1, &att_vao_);
    glGenBuffers(1, &att_vbo_);
    glBindVertexArray(att_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, att_vbo_);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), reinterpret_cast<void*>(3 * sizeof(float)));
    glBindVertexArray(0);
    rebuild_guides();
    if (upload_pending_) upload();
}

void MeshView::fb_size(int* w, int* h) const {
    const qreal dpr = devicePixelRatioF();
    *w = std::max(1, static_cast<int>(std::lround(width() * dpr)));
    *h = std::max(1, static_cast<int>(std::lround(height() * dpr)));
}

void MeshView::bind_widget_target() {
    // QOpenGLWidget's FBO stays GL_NONE after a user FBO bind. Clears and draws
    // then miss the color attachment and the viewport stays black.
    glBindFramebuffer(GL_FRAMEBUFFER, defaultFramebufferObject());
    glDrawBuffer(GL_COLOR_ATTACHMENT0);
    glReadBuffer(GL_COLOR_ATTACHMENT0);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDepthMask(GL_TRUE);
    glDisable(GL_SCISSOR_TEST);
    int w = 1;
    int h = 1;
    fb_size(&w, &h);
    glViewport(0, 0, w, h);
}

void MeshView::resizeGL(int, int) { bind_widget_target(); }

void MeshView::upload() {
    for (const PartMaps& maps : part_maps_) {
        unsigned ids[3] = {maps.albedo, maps.normal, maps.parameter};
        for (unsigned tex : ids)
            if (tex) glDeleteTextures(1, &tex);
    }
    part_maps_.clear();
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
            if (part.normals.size() >= (v + 1) * 3) {
                const float sx = part.normals[v * 3];
                const float sy = part.normals[v * 3 + 1];
                const float sz = part.normals[v * 3 + 2];
                const float nlen = std::sqrt(sx * sx + sy * sy + sz * sz);
                if (nlen > 1e-8f) {
                    nx = sx / nlen;
                    ny = sy / nlen;
                    nz = sz / nlen;
                }
            }
            const float u = v < part.uvs.size() / 2 ? part.uvs[v * 2] : 0.f;
            const float vv = v < part.uvs.size() / 2 ? part.uvs[v * 2 + 1] : 0.f;
            verts.insert(verts.end(), {p[0], p[1], p[2], nx, ny, nz, u, vv});
        }
        base += static_cast<unsigned>(n);
        auto make_tex = [&](int w, int h, const std::vector<unsigned char>& rgba) {
            unsigned tex = 0;
            if (w <= 0 || h <= 0 || rgba.size() < static_cast<size_t>(w) * h * 4) return tex;
            glGenTextures(1, &tex);
            glBindTexture(GL_TEXTURE_2D, tex);
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
            glGenerateMipmap(GL_TEXTURE_2D);
            return tex;
        };
        part_maps_.push_back({make_tex(part.tex_w, part.tex_h, part.rgba), make_tex(part.nrm_w, part.nrm_h, part.nrgba), make_tex(part.prm_w, part.prm_h, part.prgba)});
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
    if (index_total_ == 0 || shadow_fbo_ == 0 || depth_prog_ == 0) return;
    glBindFramebuffer(GL_FRAMEBUFFER, shadow_fbo_);
    glViewport(0, 0, 2048, 1024);
    glClearColor(1, 1, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glEnable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(1.5f, 2.f);
    glUseProgram(depth_prog_);
    const int loc = glGetUniformLocation(depth_prog_, "u_mvp");
    glBindVertexArray(vao_);
    auto draw_casters = [&] {
        for (size_t p = 0; p < part_count_.size(); ++p) {
            if (p < shown_.size() && !shown_[p]) continue;
            if (p < parts_.size() && is_lamp_name(parts_[p].name)) continue;
            glDrawElements(GL_TRIANGLES, part_count_[p], GL_UNSIGNED_INT, reinterpret_cast<void*>(static_cast<uintptr_t>(part_first_[p] * sizeof(unsigned))));
        }
    };
    const float az = qDegreesToRadians(sun_az_);
    const float el = qDegreesToRadians(sun_el_);
    float dx = 0.f;
    float dy = 0.f;
    float dz = 1.f;
    bool cast = false;
    if (sun_) {
        dx = std::cos(el) * std::sin(az);
        dy = std::cos(el) * std::cos(az);
        dz = std::sin(el);
        cast = true;
    } else if (moon_) {
        dx = 0.25f;
        dy = 0.18f;
        dz = 0.92f;
        cast = true;
    } else {
        const float array_d[5][3] = {{-1.f, 0.f, 0.4f}, {1.f, 0.f, 0.4f}, {0.f, -1.f, 0.3f}, {0.f, 1.f, 0.3f}, {0.f, 0.f, 1.f}};
        for (int i = 0; i < 5; ++i) {
            if (!array_on_[i]) continue;
            dx = array_d[i][0];
            dy = array_d[i][1];
            dz = array_d[i][2];
            cast = true;
            break;
        }
    }
    const float dlen = std::sqrt(dx * dx + dy * dy + dz * dz);
    dx /= dlen;
    dy /= dlen;
    dz /= dlen;
    const float span = std::max(radius_ * 1.2f, 0.5f);
    QMatrix4x4 sun_proj;
    sun_proj.ortho(-span, span, -span, span, span * 0.35f, span * 3.1f);
    QMatrix4x4 sun_view;
    const QVector3D at(center_[0], center_[1], center_[2]);
    const QVector3D from = at + QVector3D(dx, dy, dz) * span * 1.7f;
    const QVector3D up = std::abs(dz) > 0.9f ? QVector3D(0.f, 1.f, 0.f) : QVector3D(0.f, 0.f, 1.f);
    sun_view.lookAt(from, at, up);
    const QMatrix4x4 sun_mvp = sun_proj * sun_view;
    for (int k = 0; k < 16; ++k) shadow_vp_[0][k] = sun_mvp.constData()[k];
    key_shadow_ = false;
    if (cast && sun_fbo_ != 0) {
        glBindFramebuffer(GL_FRAMEBUFFER, sun_fbo_);
        glViewport(0, 0, 4096, 4096);
        glClearColor(1, 1, 1, 1);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        glDisable(GL_CULL_FACE);
        glEnable(GL_POLYGON_OFFSET_FILL);
        glPolygonOffset(0.5f, 1.0f);
        glUniform1f(glGetUniformLocation(depth_prog_, "u_esm"), 0.f);
        glUniform3f(glGetUniformLocation(depth_prog_, "u_light"), dx, dy, dz);
        glUniform1f(glGetUniformLocation(depth_prog_, "u_thick"), std::max(0.08f, radius_ * 0.012f));
        glUniformMatrix4fv(loc, 1, GL_FALSE, sun_mvp.constData());
        draw_casters();
        key_shadow_ = true;
        glBindFramebuffer(GL_FRAMEBUFFER, shadow_fbo_);
        glEnable(GL_POLYGON_OFFSET_FILL);
    }
    glUniform1f(glGetUniformLocation(depth_prog_, "u_esm"), 0.f);
    glUniform1f(glGetUniformLocation(depth_prog_, "u_thick"), 0.f);
    shadow_count_ = 1;
    for (int i = 0; i < static_cast<int>(lamps_.size()) && i < 7; ++i) {
        const int slot = i + 1;
        const int col = slot % 4;
        const int row = slot / 4;
        glViewport(col * 512, row * 512, 512, 512);
        QMatrix4x4 proj;
        proj.perspective(70.f, 1.f, 0.05f, lamps_[static_cast<size_t>(i)].range);
        QMatrix4x4 view;
        const QVector3D eye(lamps_[static_cast<size_t>(i)].pos[0], lamps_[static_cast<size_t>(i)].pos[1], lamps_[static_cast<size_t>(i)].pos[2]);
        view.lookAt(eye, eye + QVector3D(0, 0, -1), QVector3D(0, 1, 0));
        const QMatrix4x4 mvp = proj * view;
        for (int k = 0; k < 16; ++k) shadow_vp_[slot][k] = mvp.constData()[k];
        glUniformMatrix4fv(loc, 1, GL_FALSE, mvp.constData());
        draw_casters();
        shadow_count_ = slot + 1;
    }
    glDisable(GL_POLYGON_OFFSET_FILL);
    bind_widget_target();
    shadow_dirty_ = false;
}

void MeshView::draw_disc(const QMatrix4x4& proj, const QMatrix4x4& view, const QVector3D& eye, const QVector3D& dir, float radius, float r, float g, float b, float a, bool additive) {
    if (glow_prog_ == 0 || radius <= 0.f) return;
    QVector3D n = dir;
    if (n.lengthSquared() < 1e-8f) return;
    n.normalize();
    const QVector3D up = std::abs(n.z()) > 0.92f ? QVector3D(0.f, 1.f, 0.f) : QVector3D(0.f, 0.f, 1.f);
    QMatrix4x4 cam;
    cam.lookAt(eye + n * 40.f, eye, up);
    bool ok = false;
    QMatrix4x4 model = cam.inverted(&ok);
    if (!ok) return;
    model.scale(radius);
    glUseProgram(glow_prog_);
    const QMatrix4x4 mvp = proj * view * model;
    glUniformMatrix4fv(glGetUniformLocation(glow_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
    glUniform4f(glGetUniformLocation(glow_prog_, "u_color"), r, g, b, a);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, additive ? GL_ONE : GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(GL_FALSE);
    glBindVertexArray(glow_vao_);
    glDrawArrays(GL_TRIANGLE_FAN, 0, 30);
    glBindVertexArray(0);
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
}

void MeshView::draw_sky() {
    const Env& env = k_envs[env_index_];
    if (sky_prog_ == 0 || std::strcmp(env.key, "none") == 0) return;
    glDisable(GL_DEPTH_TEST);
    glDepthMask(GL_FALSE);
    glUseProgram(sky_prog_);
    int fbw = 1;
    int fbh = 1;
    fb_size(&fbw, &fbh);
    QMatrix4x4 proj;
    proj.perspective(40.f, std::max(0.1f, float(fbw) / float(fbh)), 0.05f, 200.f);
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
    glDepthMask(GL_TRUE);
}

void MeshView::rebuild_guides() {
    std::vector<float> verts;
    auto line = [&](float x0, float y0, float z0, float x1, float y1, float z1, float r, float g, float b) {
        verts.insert(verts.end(), {x0, y0, z0, r, g, b, x1, y1, z1, r, g, b});
    };
    const float span = std::max(2.f, radius_ * 3.f);
    float step = std::pow(10.f, std::floor(std::log10(std::max(span / 8.f, 1e-4f))));
    if (span / step > 24.f) step *= 2.f;
    if (span / step < 6.f) step *= 0.5f;
    const int n = std::clamp(static_cast<int>(span / step), 2, 40);
    const float lim = n * step;
    for (int i = -n; i <= n; ++i) {
        const float a = i * step;
        const int band = ((i % 5) + 5) % 5;
        const float gray = band == 0 ? 0.42f : 0.20f;
        line(-lim, a, 0, lim, a, 0, gray, gray, gray);
        line(a, -lim, 0, a, lim, 0, gray, gray, gray);
    }
    const float ax = lim * 0.45f;
    line(0, 0, 0, ax, 0, 0, 0.95f, 0.22f, 0.18f);
    line(0, 0, 0, 0, ax, 0, 0.22f, 0.82f, 0.28f);
    line(0, 0, 0, 0, 0, ax, 0.28f, 0.48f, 0.95f);
    guide_count_ = static_cast<int>(verts.size() / 6);
    if (!gl_ready_ || line_vbo_ == 0) {
        guides_dirty_ = true;
        return;
    }
    glBindVertexArray(line_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, line_vbo_);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(verts.size() * sizeof(float)), verts.data(), GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 6 * sizeof(float), reinterpret_cast<void*>(3 * sizeof(float)));
    glBindVertexArray(0);
    guides_dirty_ = false;
}

void MeshView::setAttachments(std::vector<ViewAtt> atts) {
    att_sel_ = -1;
    atts_ = std::move(atts);
    int files = 1;
    for (const ViewAtt& att : atts_) files = std::max(files, att.file + 1);
    att_on_.assign(static_cast<size_t>(files), 1);
    atts_dirty_ = true;
    if (parts_.empty() && !atts_.empty()) {
        float mn[3] = {atts_[0].pos[0], atts_[0].pos[1], atts_[0].pos[2]};
        float mx[3] = {mn[0], mn[1], mn[2]};
        for (const ViewAtt& att : atts_) {
            for (int a = 0; a < 3; ++a) {
                mn[a] = std::min(mn[a], att.pos[a]);
                mx[a] = std::max(mx[a], att.pos[a]);
            }
        }
        for (int a = 0; a < 3; ++a) center_[a] = (mn[a] + mx[a]) * 0.5f;
        const float dx = mx[0] - mn[0], dy = mx[1] - mn[1], dz = mx[2] - mn[2];
        radius_ = std::max(0.2f, 0.5f * std::sqrt(dx * dx + dy * dy + dz * dz));
        frame_camera();
        rebuild_guides();
    }
    update();
}

void MeshView::updateAttachment(int index, const ViewAtt& att) {
    if (index < 0 || index >= static_cast<int>(atts_.size())) return;
    atts_[static_cast<size_t>(index)] = att;
    atts_dirty_ = true;
    update();
}

void MeshView::setAttSelected(int index) {
    att_sel_ = index >= 0 && index < static_cast<int>(atts_.size()) ? index : -1;
    atts_dirty_ = true;
    if (att_sel_ >= 0) {
        const ViewAtt& att = atts_[static_cast<size_t>(att_sel_)];
        const float length = std::max(0.12f, radius_ * 0.08f);
        fly_from_[0] = target_[0];
        fly_from_[1] = target_[1];
        fly_from_[2] = target_[2];
        fly_from_[3] = dist_;
        fly_to_[0] = att.pos[0];
        fly_to_[1] = att.pos[1];
        fly_to_[2] = att.pos[2];
        fly_to_[3] = std::clamp(length * 5.f, 0.55f, std::max(radius_, 0.55f));
        spin_yaw_ = spin_pitch_ = zoom_v_ = elev_v_ = 0.f;
        move_v_[0] = move_v_[1] = move_v_[2] = 0.f;
        fly_on_ = true;
        fly_clock_.start();
        kick_coast();
    }
    update();
}

void MeshView::setAttFileShown(int file, bool on) {
    if (file < 0) return;
    if (file >= static_cast<int>(att_on_.size())) att_on_.resize(static_cast<size_t>(file) + 1, 1);
    att_on_[static_cast<size_t>(file)] = on ? 1 : 0;
    atts_dirty_ = true;
    update();
}

void MeshView::rebuild_atts() {
    // Same RGB line triad as the corner gizmo, placed on each attachment and spun by its matrix.
    std::vector<float> verts;
    auto line = [&](float x0, float y0, float z0, float x1, float y1, float z1, float r, float g, float b) {
        verts.insert(verts.end(), {x0, y0, z0, r, g, b, x1, y1, z1, r, g, b});
    };
    const float length = std::max(0.12f, radius_ * 0.08f);
    const float rgb[3][3] = {{0.95f, 0.22f, 0.18f}, {0.22f, 0.82f, 0.28f}, {0.28f, 0.48f, 0.95f}};
    for (size_t i = 0; i < atts_.size(); ++i) {
        const ViewAtt& att = atts_[i];
        if (att.file >= 0 && att.file < static_cast<int>(att_on_.size()) && !att_on_[static_cast<size_t>(att.file)]) continue;
        const bool hot = static_cast<int>(i) == att_sel_;
        const float len = length * (hot ? 1.6f : 1.f);
        for (int axis = 0; axis < 3; ++axis) {
            float ax = att.orient[axis * 3], ay = att.orient[axis * 3 + 1], az = att.orient[axis * 3 + 2];
            const float n = std::sqrt(ax * ax + ay * ay + az * az);
            if (n < 1e-8f) continue;
            ax /= n;
            ay /= n;
            az /= n;
            float r = rgb[axis][0], g = rgb[axis][1], b = rgb[axis][2];
            if (hot) {
                r = std::min(1.f, r + (1.f - r) * 0.75f);
                g = std::min(1.f, g + (1.f - g) * 0.75f);
                b = std::min(1.f, b + (1.f - b) * 0.75f);
            }
            line(att.pos[0], att.pos[1], att.pos[2], att.pos[0] + ax * len, att.pos[1] + ay * len, att.pos[2] + az * len, r, g, b);
            if (hot && move_tool_) {
                // Arrowhead: four short barbs back from the tip, around the axis.
                const QVector3D dir(ax, ay, az);
                const QVector3D side = QVector3D::crossProduct(dir, std::abs(az) < 0.9f ? QVector3D(0, 0, 1) : QVector3D(1, 0, 0)).normalized();
                const QVector3D up = QVector3D::crossProduct(dir, side);
                const QVector3D tip = QVector3D(att.pos[0], att.pos[1], att.pos[2]) + dir * len;
                for (const QVector3D& off : {side, -side, up, -up}) {
                    const QVector3D barb = tip - dir * (len * 0.16f) + off * (len * 0.06f);
                    line(tip.x(), tip.y(), tip.z(), barb.x(), barb.y(), barb.z(), r, g, b);
                }
            }
        }
        if (hot && move_tool_) {
            // Free-move handle: small white box on the origin.
            const float h = length * 0.09f;
            const float* p = att.pos;
            for (int e = 0; e < 12; ++e) {
                static const int edges[12][2] = {{0, 1}, {1, 3}, {3, 2}, {2, 0}, {4, 5}, {5, 7}, {7, 6}, {6, 4}, {0, 4}, {1, 5}, {2, 6}, {3, 7}};
                auto corner = [&](int c, float* o) {
                    o[0] = p[0] + ((c & 1) ? h : -h);
                    o[1] = p[1] + ((c & 2) ? h : -h);
                    o[2] = p[2] + ((c & 4) ? h : -h);
                };
                float a[3], b[3];
                corner(edges[e][0], a);
                corner(edges[e][1], b);
                line(a[0], a[1], a[2], b[0], b[1], b[2], 1.f, 1.f, 1.f);
            }
        }
    }
    att_verts_ = static_cast<int>(verts.size() / 6);
    if (!gl_ready_ || att_vbo_ == 0) return;
    glBindVertexArray(att_vao_);
    glBindBuffer(GL_ARRAY_BUFFER, att_vbo_);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(verts.size() * sizeof(float)), verts.empty() ? nullptr : verts.data(), GL_DYNAMIC_DRAW);
    glBindVertexArray(0);
    atts_dirty_ = false;
}

void MeshView::draw_atts(const QMatrix4x4& proj, const QMatrix4x4& view) {
    if (line_prog_ == 0) return;
    if (atts_dirty_) rebuild_atts();
    if (att_verts_ <= 0) return;
    // Drawn after the body. Depth-tested axes sit under the shell and never show; an attachment-only .im has no triangles so it looked fine.
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    glUseProgram(line_prog_);
    const QMatrix4x4 mvp = proj * view * anim_model_;
    glUniformMatrix4fv(glGetUniformLocation(line_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
    glBindVertexArray(att_vao_);
    glLineWidth(2.f);
    glDrawArrays(GL_LINES, 0, att_verts_);
}

void MeshView::draw_guides(const QMatrix4x4& proj, const QMatrix4x4& view) {
    if (line_prog_ == 0) return;
    if (guides_dirty_) rebuild_guides();
    if (guide_count_ > 0) {
        glEnable(GL_DEPTH_TEST);
        glUseProgram(line_prog_);
        const QMatrix4x4 mvp = proj * view;
        glUniformMatrix4fv(glGetUniformLocation(line_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
        glBindVertexArray(line_vao_);
        glDrawArrays(GL_LINES, 0, guide_count_);
    }
}

void MeshView::paintGL() {
    if (!gl_ready_ || mesh_prog_ == 0) return;
    if (upload_pending_) upload();
    if (shadow_dirty_) draw_shadows();
    bind_widget_target();
    const Env& env = k_envs[env_index_];
    float tint[3] = {1.f, 0.96f, 0.9f};
    sun_rgb(sun_el_, tint);
    tint[1] = tint[1] * (1.f - sun_warm_) + 0.26f * sun_warm_;
    tint[2] = tint[2] * (1.f - sun_warm_) + 0.05f * sun_warm_;
    float clear_r = env.clear[0];
    float clear_g = env.clear[1];
    float clear_b = env.clear[2];
    if (std::strcmp(env.key, "none") == 0) {
        if (sun_) {
            const float k = std::clamp((sun_el_ + 4.f) / 36.f, 0.2f, 1.f);
            clear_r = 0.04f + tint[0] * 0.28f * k;
            clear_g = 0.045f + tint[1] * 0.26f * k;
            clear_b = 0.06f + tint[2] * 0.30f * k;
        } else if (moon_) {
            clear_r = 0.025f;
            clear_g = 0.032f;
            clear_b = 0.055f;
        }
    }
    glClearColor(clear_r, clear_g, clear_b, 1.f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    draw_sky();
    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    const float yr = qDegreesToRadians(yaw_);
    const float pr = qDegreesToRadians(pitch_);
    const QVector3D eye(target_[0] + dist_ * std::cos(pr) * std::cos(yr), target_[1] + dist_ * std::cos(pr) * std::sin(yr), target_[2] + dist_ * std::sin(pr));
    int fbw = 1;
    int fbh = 1;
    fb_size(&fbw, &fbh);
    const float near_p = std::max(0.001f, radius_ * 0.008f);
    const float far_p = std::max(near_p * 100.f, std::max(dist_ * 40.f, 120.f));
    QMatrix4x4 proj;
    proj.perspective(fov_, std::max(0.1f, float(fbw) / float(fbh)), near_p, far_p);
    QMatrix4x4 view;
    view.lookAt(eye, QVector3D(target_[0], target_[1], target_[2]), QVector3D(0, 0, 1));
    glEnable(GL_DEPTH_TEST);
    if (sun_) {
        const float azr = qDegreesToRadians(sun_az_);
        const float elr = qDegreesToRadians(sun_el_);
        const QVector3D sun_dir(std::cos(elr) * std::sin(azr), std::cos(elr) * std::cos(azr), std::sin(elr));
        draw_disc(proj, view, eye, sun_dir, 3.6f, tint[0], tint[1] * 0.72f, tint[2] * 0.45f, 0.55f, true);
        draw_disc(proj, view, eye, sun_dir, 1.35f, 1.f, 0.55f + tint[1] * 0.45f, 0.25f + tint[2] * 0.5f, 1.f, false);
    }
    if (moon_ || !sun_) {
        const QVector3D moon_dir(0.25f, 0.18f, 0.92f);
        const float moon_a = (moon_ && !sun_) ? 1.f : 0.42f;
        draw_disc(proj, view, eye, moon_dir, 2.2f, 0.45f, 0.52f, 0.7f, moon_a * 0.35f, true);
        draw_disc(proj, view, eye, moon_dir, 1.05f, 0.78f, 0.82f, 0.9f, moon_a, false);
    }
    draw_guides(proj, view);
    if (index_total_ <= 0 || mesh_prog_ == 0) {
        draw_atts(proj, view);
        paint_att_names(proj, view);
        sync_fps();
        return;
    }
    glEnable(GL_DEPTH_TEST);
    const bool wire = shade_ == 0;
    const bool clay = shade_ <= 1;
    const bool use_maps = shade_ >= 3;
    if (wire) glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);
    glUseProgram(mesh_prog_);
    QMatrix4x4 model = anim_model_;
    const QMatrix4x4 mvp = proj * view * model;
    glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
    glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, "u_model"), 1, GL_FALSE, model.constData());
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_cam_pos"), eye.x(), eye.y(), eye.z());
    const float amb = (moon_ && !sun_) ? 0.045f : sun_ ? 0.16f : env.ambient;
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_ambient"), amb);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_emissive_scale"), emis_scale_);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_self_illum"), 0.f);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_debug_mode"), debug_mode_);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_sky_top"), env.top[0], env.top[1], env.top[2]);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_sky_horizon"), env.horizon[0], env.horizon[1], env.horizon[2]);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_ibl_strength"), (moon_ && !sun_) ? env.ibl * 0.28f : env.ibl);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_env_map"), env.map ? 1.f : 0.f);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_albedo"), 0);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_normal"), 1);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_parameter"), 2);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_env_map"), 3);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_shadow_atlas"), 4);
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_sun_map"), 5);
    const float depth_range = std::max(radius_ * 1.2f, 0.5f) * 2.75f;
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_sun_bias"), std::clamp(0.02f / depth_range, 0.00028f, 0.0016f));
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_sun_cast"), key_shadow_ ? 1.f : 0.f);
    const float azr = qDegreesToRadians(sun_az_);
    const float elr = qDegreesToRadians(sun_el_);
    const float sun_d[3] = {std::cos(elr) * std::sin(azr), std::cos(elr) * std::cos(azr), std::sin(elr)};
    const float array_d[5][3] = {{-1.f, 0.f, 0.4f}, {1.f, 0.f, 0.4f}, {0.f, -1.f, 0.3f}, {0.f, 1.f, 0.3f}, {0.f, 0.f, 1.f}};
    const float array_r[5] = {0.95f, 0.75f, 0.85f, 0.35f, 0.40f};
    for (int i = 0; i < 5; ++i) {
        float d[3] = {0.f, 0.f, 1.f};
        float rad = 0.f;
        bool on = false;
        if (sun_) {
            if (i == 0) {
                d[0] = sun_d[0];
                d[1] = sun_d[1];
                d[2] = sun_d[2];
                rad = sun_int_;
                on = true;
            } else if (i == 4) {
                rad = 0.22f;
                on = true;
            }
        } else if (moon_ && i == 0) {
            d[0] = 0.25f;
            d[1] = 0.18f;
            d[2] = 0.92f;
            rad = 0.55f;
            on = true;
        } else if (!moon_) {
            d[0] = array_d[i][0];
            d[1] = array_d[i][1];
            d[2] = array_d[i][2];
            rad = array_r[i];
            on = array_on_[i];
        }
        float cr = rad;
        float cg = rad;
        float cb = rad;
        if (sun_ && i == 0) {
            cr = rad * tint[0];
            cg = rad * tint[1];
            cb = rad * tint[2];
        } else if (moon_ && !sun_ && i == 0) {
            cr = 0.32f;
            cg = 0.40f;
            cb = 0.62f;
        }
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lights[" + std::to_string(i) + "]").c_str()), d[0], d[1], d[2]);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_light_on[" + std::to_string(i) + "]").c_str()), on ? 1.f : 0.f);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_light_rad[" + std::to_string(i) + "]").c_str()), cr, cg, cb);
    }
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_lamp_count"), static_cast<int>(lamps_.size()));
    glUniform1i(glGetUniformLocation(mesh_prog_, "u_shadow_count"), shadow_count_);
    for (int i = 0; i < shadow_count_ && i < 8; ++i) {
        const auto n = std::to_string(i);
        glUniformMatrix4fv(glGetUniformLocation(mesh_prog_, ("u_shadow_vp[" + n + "]").c_str()), 1, GL_FALSE, shadow_vp_[i]);
    }
    for (int i = 0; i < static_cast<int>(lamps_.size()) && i < 8; ++i) {
        const auto n = std::to_string(i);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lamp_pos[" + n + "]").c_str()), lamps_[i].pos[0], lamps_[i].pos[1], lamps_[i].pos[2]);
        glUniform3f(glGetUniformLocation(mesh_prog_, ("u_lamp_col[" + n + "]").c_str()), 1.f, 0.62f, 0.22f);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_lamp_power[" + n + "]").c_str()), 1.6f);
        glUniform1f(glGetUniformLocation(mesh_prog_, ("u_lamp_range[" + n + "]").c_str()), lamps_[i].range);
    }
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, white_tex_);
    glActiveTexture(GL_TEXTURE3);
    glBindTexture(GL_TEXTURE_2D, env_tex_);
    glActiveTexture(GL_TEXTURE4);
    glBindTexture(GL_TEXTURE_2D, shadow_tex_);
    glActiveTexture(GL_TEXTURE5);
    glBindTexture(GL_TEXTURE_2D, sun_tex_);
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_tex"), 1.f);
    glUniform3f(glGetUniformLocation(mesh_prog_, "u_flat_color"), 0.72f, 0.74f, 0.78f);
    const int two_loc = glGetUniformLocation(mesh_prog_, "u_two_sided");
    glUniform1f(glGetUniformLocation(mesh_prog_, "u_face"), face_orient_ ? 1.f : 0.f);
    const int has_n = glGetUniformLocation(mesh_prog_, "u_has_normal");
    const int has_p = glGetUniformLocation(mesh_prog_, "u_has_parameter");
    glBindVertexArray(vao_);
    for (size_t p = 0; p < part_count_.size(); ++p) {
        if (p < shown_.size() && !shown_[p]) continue;
        const bool two = p < parts_.size() && parts_[p].two_sided;
        glUniform1f(two_loc, two ? 1.f : 0.f);
        if (two || face_orient_) glDisable(GL_CULL_FACE);
        else {
            glEnable(GL_CULL_FACE);
            glCullFace(GL_BACK);
        }
        const PartMaps maps = p < part_maps_.size() ? part_maps_[p] : PartMaps{};
        glUniform1f(has_n, use_maps && maps.normal ? 1.f : 0.f);
        glUniform1f(has_p, use_maps && maps.parameter ? 1.f : 0.f);
        glUniform1f(glGetUniformLocation(mesh_prog_, "u_use_tex"), !clay && maps.albedo ? 1.f : 0.f);
        glActiveTexture(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D, use_maps && maps.normal ? maps.normal : white_tex_);
        glActiveTexture(GL_TEXTURE2);
        glBindTexture(GL_TEXTURE_2D, use_maps && maps.parameter ? maps.parameter : white_tex_);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, !clay && maps.albedo ? maps.albedo : white_tex_);
        glDrawElements(GL_TRIANGLES, part_count_[p], GL_UNSIGNED_INT, reinterpret_cast<void*>(static_cast<uintptr_t>(part_first_[p] * sizeof(unsigned))));
    }
    if (glow_prog_ != 0 && std::find(highlight_.begin(), highlight_.end(), 1) != highlight_.end()) {
        glUseProgram(glow_prog_);
        glUniformMatrix4fv(glGetUniformLocation(glow_prog_, "u_mvp"), 1, GL_FALSE, mvp.constData());
        glUniform4f(glGetUniformLocation(glow_prog_, "u_color"), 1.f, 0.35f, 0.12f, 0.55f);
        glDisable(GL_CULL_FACE);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE);
        glDepthFunc(GL_LEQUAL);
        glDepthMask(GL_FALSE);
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);
        for (size_t p = 0; p < part_count_.size() && p < highlight_.size(); ++p) {
            if (!highlight_[p] || (p < shown_.size() && !shown_[p])) continue;
            glDrawElements(GL_TRIANGLES, part_count_[p], GL_UNSIGNED_INT, reinterpret_cast<void*>(static_cast<uintptr_t>(part_first_[p] * sizeof(unsigned))));
        }
        glPolygonMode(GL_FRONT_AND_BACK, wire ? GL_LINE : GL_FILL);
        glDepthMask(GL_TRUE);
        glDepthFunc(GL_LESS);
        glDisable(GL_BLEND);
        glUseProgram(mesh_prog_);
    }
    if (wire) glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    glDisable(GL_CULL_FACE);
    if (ground_) {
        glDisable(GL_CULL_FACE);
        glUniform1f(two_loc, 0.f);
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
    draw_atts(proj, view);
    blur_panels();
    paint_att_names(proj, view);
    sync_fps();
}

// Frosted backdrop: downsample the finished frame through a mip-like chain,
// then upsample it back over each panel rect only (scissored blit).
void MeshView::blur_panels() {
    if (blur_rect_[0].isEmpty() && blur_rect_[1].isEmpty()) return;
    int w = 1;
    int h = 1;
    fb_size(&w, &h);
    if (blur_w_ != w || blur_h_ != h) {
        glDeleteFramebuffers(kBlurLevels, blur_fbo_);
        glDeleteTextures(kBlurLevels, blur_tex_);
        glGenFramebuffers(kBlurLevels, blur_fbo_);
        glGenTextures(kBlurLevels, blur_tex_);
        for (int i = 0; i < kBlurLevels; ++i) {
            const int lw = std::max(1, w >> (i + 1));
            const int lh = std::max(1, h >> (i + 1));
            glBindTexture(GL_TEXTURE_2D, blur_tex_[i]);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, lw, lh, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            glBindFramebuffer(GL_FRAMEBUFFER, blur_fbo_[i]);
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, blur_tex_[i], 0);
        }
        blur_w_ = w;
        blur_h_ = h;
    }
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_BLEND);
    auto lvl = [&](int i, int* lw, int* lh) {
        *lw = std::max(1, w >> (i + 1));
        *lh = std::max(1, h >> (i + 1));
    };
    const unsigned screen = defaultFramebufferObject();
    int sw = w;
    int sh = h;
    unsigned src = screen;
    for (int i = 0; i < kBlurLevels; ++i) {
        int lw, lh;
        lvl(i, &lw, &lh);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, src);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, blur_fbo_[i]);
        glBlitFramebuffer(0, 0, sw, sh, 0, 0, lw, lh, GL_COLOR_BUFFER_BIT, GL_LINEAR);
        src = blur_fbo_[i];
        sw = lw;
        sh = lh;
    }
    for (int i = kBlurLevels - 2; i >= 0; --i) {
        int lw, lh;
        lvl(i, &lw, &lh);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, blur_fbo_[i + 1]);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, blur_fbo_[i]);
        int pw, ph;
        lvl(i + 1, &pw, &ph);
        glBlitFramebuffer(0, 0, pw, ph, 0, 0, lw, lh, GL_COLOR_BUFFER_BIT, GL_LINEAR);
    }
    const qreal dpr = devicePixelRatioF();
    glBindFramebuffer(GL_READ_FRAMEBUFFER, blur_fbo_[0]);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, screen);
    glEnable(GL_SCISSOR_TEST);
    int hw, hh;
    lvl(0, &hw, &hh);
    for (const QRect& r : blur_rect_) {
        if (r.isEmpty()) continue;
        const int x = static_cast<int>(r.x() * dpr);
        const int wpx = static_cast<int>(r.width() * dpr);
        const int hpx = static_cast<int>(r.height() * dpr);
        const int y = h - static_cast<int>(r.y() * dpr) - hpx;
        glScissor(x, y, wpx, hpx);
        glBlitFramebuffer(0, 0, hw, hh, 0, 0, w, h, GL_COLOR_BUFFER_BIT, GL_LINEAR);
    }
    glDisable(GL_SCISSOR_TEST);
    bind_widget_target();
}

void MeshView::kick_coast() {
    if (coast_ && !coast_->isActive()) coast_->start();
}

void MeshView::cam_right(float* x, float* y) const {
    const float yr = qDegreesToRadians(yaw_);
    *x = -std::sin(yr);
    *y = std::cos(yr);
}

void MeshView::coast() {
    const float yaw0 = yaw_;
    const float pitch0 = pitch_;
    if (fly_on_) {
        const float t = std::min(1.f, fly_clock_.elapsed() / 650.f);
        const float s = t * t * t * (t * (t * 6.f - 15.f) + 10.f);  // smootherstep
        for (int i = 0; i < 3; ++i) target_[i] = fly_from_[i] + (fly_to_[i] - fly_from_[i]) * s;
        dist_ = fly_from_[3] + (fly_to_[3] - fly_from_[3]) * s;
        if (fly_orient_) {
            yaw_ = fly_yaw0_ + (fly_yaw1_ - fly_yaw0_) * s;
            pitch_ = std::clamp(fly_pitch0_ + (fly_pitch1_ - fly_pitch0_) * s, -85.f, 85.f);
        }
        if (t >= 1.f) {
            fly_on_ = false;
            fly_orient_ = false;
        }
    }
    const bool walking = key_up_ || key_down_ || key_left_ || key_right_ || key_pgup_ || key_pgdn_;
    if (std::abs(spin_yaw_) > 1e-4f || std::abs(spin_pitch_) > 1e-4f) {
        yaw_ += spin_yaw_;
        pitch_ = std::clamp(pitch_ + spin_pitch_, -85.f, 85.f);
        spin_yaw_ *= 0.82f;
        spin_pitch_ *= 0.82f;
        if (std::abs(spin_yaw_) < 1e-3f) spin_yaw_ = 0.f;
        if (std::abs(spin_pitch_) < 1e-3f) spin_pitch_ = 0.f;
    }
    if (yaw_ != yaw0 || pitch_ != pitch0) emit cameraMoved();
    if (std::abs(zoom_v_) > 1e-5f) {
        dist_ = std::clamp(dist_ * (1.f + zoom_v_), std::max(0.05f, radius_ * 0.2f), std::max(radius_ * 40.f, 1.f));
        zoom_v_ *= 0.82f;
        if (std::abs(zoom_v_) < 1e-4f) zoom_v_ = 0.f;
    }
    if (walking) {
        const float pr = qDegreesToRadians(pitch_);
        const float yr = qDegreesToRadians(yaw_);
        float fx = -std::cos(pr) * std::cos(yr);
        float fy = -std::cos(pr) * std::sin(yr);
        const float fl = std::sqrt(fx * fx + fy * fy);
        if (fl < 1e-6f) {
            fx = -1.f;
            fy = 0.f;
        } else {
            fx /= fl;
            fy /= fl;
        }
        float rx = 0.f;
        float ry = 0.f;
        cam_right(&rx, &ry);
        const float step = dist_ * 0.0032f;
        if (key_up_) {
            move_v_[0] += fx * step;
            move_v_[1] += fy * step;
        }
        if (key_down_) {
            move_v_[0] -= fx * step;
            move_v_[1] -= fy * step;
        }
        if (key_left_) {
            move_v_[0] -= rx * step;
            move_v_[1] -= ry * step;
        }
        if (key_right_) {
            move_v_[0] += rx * step;
            move_v_[1] += ry * step;
        }
        const float elev = dist_ * 0.0028f;
        if (key_pgup_) elev_v_ += elev;
        if (key_pgdn_) elev_v_ -= elev;
    }
    const float move = std::sqrt(move_v_[0] * move_v_[0] + move_v_[1] * move_v_[1] + move_v_[2] * move_v_[2]);
    if (move > 1e-6f) {
        target_[0] += move_v_[0];
        target_[1] += move_v_[1];
        target_[2] += move_v_[2];
        move_v_[0] *= 0.80f;
        move_v_[1] *= 0.80f;
        move_v_[2] *= 0.80f;
    }
    if (std::abs(elev_v_) > 1e-6f) {
        target_[2] += elev_v_;
        elev_v_ *= 0.78f;
        if (std::abs(elev_v_) < 1e-5f) elev_v_ = 0.f;
    }
    const bool alive = fly_on_ || walking || show_fps_ || std::abs(spin_yaw_) > 0.f || std::abs(spin_pitch_) > 0.f || std::abs(zoom_v_) > 0.f || std::abs(elev_v_) > 0.f || move > 1e-6f;
    if (!alive) {
        if (coast_) coast_->stop();
        return;
    }
    update();
}

void MeshView::mousePressEvent(QMouseEvent* event) {
    last_ = event->pos();
    setFocus(Qt::MouseFocusReason);
    fly_on_ = false;
    fly_orient_ = false;
    if (move_tool_ && event->button() == Qt::LeftButton && !(event->modifiers() & Qt::ShiftModifier)) {
        int axis = -1;
        const int att = pick_att(event->pos(), &axis);
        if (att >= 0) {
            const ViewAtt& hit = atts_[static_cast<size_t>(att)];
            drag_att_ = att;
            drag_axis_ = axis;
            shift_axis_ = -1;
            drag_from_ = QVector3D(hit.pos[0], hit.pos[1], hit.pos[2]);
            if (!drag_point(event->pos(), &drag_grab_)) drag_grab_ = drag_from_;
            att_sel_ = att;
            atts_dirty_ = true;
            update();
            emit attPicked(att);
            return;
        }
    }
    pick_press_ = event->button() == Qt::LeftButton && (event->modifiers() & Qt::ShiftModifier);
    if (!pick_press_) return;
    const int att = pick_att(event->pos());
    if (att >= 0) {
        att_sel_ = att;
        atts_dirty_ = true;
        update();
        emit attPicked(att);
        return;
    }
    const int hit = pick_part(event->pos());
    if (hit >= 0) {
        if (att_sel_ != -1) {
            att_sel_ = -1;
            atts_dirty_ = true;
            update();
        }
        emit partPicked(hit);
        return;
    }
    if (att_sel_ != -1) {
        att_sel_ = -1;
        atts_dirty_ = true;
        update();
    }
    emit pickCleared();
}

void MeshView::mouseMoveEvent(QMouseEvent* event) {
    const QPoint d = event->pos() - last_;
    last_ = event->pos();
    if (drag_att_ >= 0 && drag_att_ < static_cast<int>(atts_.size())) {
        QVector3D now;
        if (!drag_point(event->pos(), &now)) return;
        QVector3D delta = now - drag_grab_;
        // Blender-style: Shift during a free drag locks to the world axis it has moved along most.
        if (drag_axis_ < 0 && (event->modifiers() & Qt::ShiftModifier)) {
            if (shift_axis_ < 0 && delta.lengthSquared() > 1e-12f) {
                shift_axis_ = 0;
                for (int k = 1; k < 3; ++k)
                    if (std::abs(delta[k]) > std::abs(delta[shift_axis_])) shift_axis_ = k;
            }
            if (shift_axis_ >= 0) {
                const float keep = delta[shift_axis_];
                delta = QVector3D();
                delta[shift_axis_] = keep;
            }
        } else {
            shift_axis_ = -1;
        }
        const QVector3D p = drag_from_ + delta;
        ViewAtt& att = atts_[static_cast<size_t>(drag_att_)];
        att.pos[0] = p.x();
        att.pos[1] = p.y();
        att.pos[2] = p.z();
        atts_dirty_ = true;
        update();
        emit attMoved(drag_att_, p.x(), p.y(), p.z());
        return;
    }
    if (pick_press_) return;
    if (event->buttons() & Qt::LeftButton) {
        spin_yaw_ = std::clamp(spin_yaw_ - d.x() * 0.045f, -8.f, 8.f);
        spin_pitch_ = std::clamp(spin_pitch_ + d.y() * 0.045f, -8.f, 8.f);
        kick_coast();
    } else if (event->buttons() & (Qt::RightButton | Qt::MiddleButton)) {
        float rx = 0.f;
        float ry = 0.f;
        cam_right(&rx, &ry);
        const float scale = dist_ * 0.00035f;
        move_v_[0] += rx * d.x() * scale;
        move_v_[1] += ry * d.x() * scale;
        elev_v_ = std::clamp(elev_v_ + d.y() * scale, -dist_ * 0.04f, dist_ * 0.04f);
        kick_coast();
    }
}

void MeshView::mouseReleaseEvent(QMouseEvent* event) {
    Q_UNUSED(event);
    if (drag_att_ >= 0) emit attDragDone();
    drag_att_ = -1;
    pick_press_ = false;
    kick_coast();
}

void MeshView::wheelEvent(QWheelEvent* event) {
    fly_on_ = false;
    const float steps = event->angleDelta().y() / 120.f;
    if (event->modifiers() & Qt::ControlModifier) {
        fov_ = std::clamp(fov_ * std::pow(0.9f, steps), 5.f, 110.f);
        update();
        event->accept();
        return;
    }
    zoom_v_ = std::clamp(zoom_v_ - steps * 0.085f, -0.28f, 0.28f);
    kick_coast();
    event->accept();
}

void MeshView::note_keys(int key, bool down, bool repeat) {
    if (repeat && !down) return;
    bool* slot = nullptr;
    if (key == Qt::Key_Up) slot = &key_up_;
    else if (key == Qt::Key_Down) slot = &key_down_;
    else if (key == Qt::Key_Left) slot = &key_left_;
    else if (key == Qt::Key_Right) slot = &key_right_;
    else if (key == Qt::Key_PageUp) slot = &key_pgup_;
    else if (key == Qt::Key_PageDown) slot = &key_pgdn_;
    else if (key == Qt::Key_F3 && down && !repeat) {
        toggleFps();
        return;
    } else if (key == Qt::Key_R && down && !repeat) {
        resetCamera();
        return;
    } else return;
    *slot = down;
    if (down) kick_coast();
}

void MeshView::setWalk(int key, bool down) { note_keys(key, down, false); }

void MeshView::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_Escape && drag_att_ >= 0 && drag_att_ < static_cast<int>(atts_.size())) {
        ViewAtt& att = atts_[static_cast<size_t>(drag_att_)];
        att.pos[0] = drag_from_.x();
        att.pos[1] = drag_from_.y();
        att.pos[2] = drag_from_.z();
        atts_dirty_ = true;
        update();
        emit attMoved(drag_att_, drag_from_.x(), drag_from_.y(), drag_from_.z());
        drag_att_ = -1;
        emit attDragDone();
        return;
    }
    note_keys(event->key(), true, event->isAutoRepeat());
}
void MeshView::keyReleaseEvent(QKeyEvent* event) { note_keys(event->key(), false, event->isAutoRepeat()); }

void MeshView::toggleFps() {
    show_fps_ = !show_fps_;
    if (!show_fps_ && fps_) fps_->hide();
    else kick_coast();
    update();
}

void MeshView::sync_fps() {
    if (!fps_) return;
    const qint64 now = fps_clock_.nsecsElapsed();
    if (fps_last_ns_ > 0) {
        fps_wall_.push_back(static_cast<float>(now - fps_last_ns_) / 1.e6f);
        if (fps_wall_.size() > 90) fps_wall_.pop_front();
    }
    fps_last_ns_ = now;
    ++frame_id_;
    if (!show_fps_) {
        fps_->hide();
        return;
    }
    if (fps_wall_.empty()) return;
    const float wall = fps_wall_.back();
    float sum = 0.f;
    float lo = wall;
    float hi = wall;
    for (float sample : fps_wall_) {
        sum += sample;
        lo = std::min(lo, sample);
        hi = std::max(hi, sample);
    }
    const float avg = sum / static_cast<float>(fps_wall_.size());
    const float fps = 1000.f / std::max(wall, 0.001f);
    const float fps_avg = 1000.f / std::max(avg, 0.001f);
    fps_->setText(QStringLiteral("%1 fps  %2 ms\navg %3  %4 ms  (%5–%6)\n#%7")
                      .arg(fps, 0, 'f', 1)
                      .arg(wall, 0, 'f', 1)
                      .arg(fps_avg, 0, 'f', 1)
                      .arg(avg, 0, 'f', 1)
                      .arg(lo, 0, 'f', 0)
                      .arg(hi, 0, 'f', 0)
                      .arg(frame_id_));
    fps_->adjustSize();
    fps_->move(std::max(8, width() / 2 - fps_->width() / 2), 14);
    fps_->show();
    fps_->raise();
}
