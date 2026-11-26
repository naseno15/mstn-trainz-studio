#include "fbx.h"

#include "ufbx.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string ufbx_text(ufbx_string text) {
    if (!text.data || text.length == 0) return {};
    return std::string(text.data, text.length);
}

// Trainz (+X right, +Y forward, +Z up) → FBX file space matching the fixtures (Y-up, Front Z).
void to_fbx(float x, float y, float z, float& ox, float& oy, float& oz) {
    ox = x;
    oy = z;
    oz = -y;
}

std::string fmt_num(double value) {
    const double nearest = std::round(value);
    if (std::fabs(value - nearest) < 1e-7) return std::to_string(static_cast<long long>(nearest));
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.9g", value);
    return buf;
}

std::string fbx_name(std::string name) {
    for (char& c : name) {
        if (c == '"' || c == '\n' || c == '\r') c = '_';
    }
    if (name.empty()) name = "mesh";
    return name;
}

// Columns of R are local axes in FBX world. Euler XYZ degrees as R = Rz·Ry·Rx.
void euler_xyz_deg(const float axis[9], float& rx, float& ry, float& rz) {
    const float r00 = axis[0], r10 = axis[1], r20 = axis[2];
    const float r01 = axis[3], r11 = axis[4], r21 = axis[5];
    const float r02 = axis[6], r12 = axis[7], r22 = axis[8];
    const float sy = std::sqrt(r00 * r00 + r10 * r10);
    constexpr float rad = 57.29577951308232f;
    if (sy > 1e-6f) {
        rx = std::atan2(r21, r22) * rad;
        ry = std::atan2(-r20, sy) * rad;
        rz = std::atan2(r10, r00) * rad;
    } else {
        rx = std::atan2(-r12, r11) * rad;
        ry = std::atan2(-r20, sy) * rad;
        rz = 0.f;
        (void)r01;
        (void)r02;
    }
}

void append_floats(std::ostream& out, const std::vector<float>& values) {
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) out << ',';
        out << fmt_num(values[i]);
    }
}

void append_ints(std::ostream& out, const std::vector<int32_t>& values) {
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) out << ',';
        out << values[i];
    }
}

std::string file_name(ufbx_texture* texture) {
    if (!texture) return {};
    const ufbx_string raw = texture->relative_filename.length ? texture->relative_filename : texture->filename;
    std::string path = ufbx_text(raw);
    const size_t slash = path.find_last_of("/\\");
    if (slash != std::string::npos) path.erase(0, slash + 1);
    return path;
}

void push_normal(std::vector<float>& normals, float x, float y, float z) {
    const float len = std::sqrt(x * x + y * y + z * z);
    if (len > 1e-12f) {
        x /= len;
        y /= len;
        z /= len;
    }
    normals.push_back(x);
    normals.push_back(y);
    normals.push_back(z);
}

void append_faces(MeshPart& part, ufbx_node* node, ufbx_mesh* mesh, const uint32_t* face_ids, size_t face_count, std::vector<uint32_t>& tri) {
    for (size_t i = 0; i < face_count; ++i) {
        const uint32_t face_ix = face_ids ? face_ids[i] : static_cast<uint32_t>(i);
        if (face_ix >= mesh->faces.count) continue;
        if (mesh->face_hole.data && face_ix < mesh->face_hole.count && mesh->face_hole.data[face_ix]) continue;
        const uint32_t tris = ufbx_triangulate_face(tri.data(), tri.size(), mesh, mesh->faces.data[face_ix]);
        for (uint32_t corner = 0; corner < tris * 3; ++corner) {
            const uint32_t index = tri[corner];
            ufbx_vec3 position = ufbx_transform_position(&node->geometry_to_world, ufbx_get_vertex_vec3(&mesh->vertex_position, index));
            part.indices.push_back(static_cast<uint32_t>(part.positions.size() / 3));
            part.positions.push_back(static_cast<float>(position.x));
            part.positions.push_back(static_cast<float>(position.y));
            part.positions.push_back(static_cast<float>(position.z));
            if (mesh->vertex_normal.exists) {
                const ufbx_vec3 normal = ufbx_transform_direction(&node->geometry_to_world, ufbx_get_vertex_vec3(&mesh->vertex_normal, index));
                push_normal(part.normals, static_cast<float>(normal.x), static_cast<float>(normal.y), static_cast<float>(normal.z));
            } else {
                part.normals.insert(part.normals.end(), {0.f, 0.f, 1.f});
            }
            if (mesh->vertex_uv.exists) {
                const ufbx_vec2 uv = ufbx_get_vertex_vec2(&mesh->vertex_uv, index);
                part.uvs.push_back(static_cast<float>(uv.x));
                part.uvs.push_back(static_cast<float>(uv.y));
            }
        }
    }
}

bool att_node(const std::string& name) {
    return name.size() > 2 && (name[0] == 'a' || name[0] == 'A') && name[1] == '.';
}

}  // namespace

std::vector<MeshPart> parse_fbx_parts(const uint8_t* data, size_t size) {
    ImView view = parse_fbx_view(data, size);
    if (view.parts.empty()) throw std::runtime_error("no mesh in this .fbx");
    return std::move(view.parts);
}

ImView parse_fbx_view(const uint8_t* data, size_t size) {
    // ponytail: bind-pose triangles only. Skinning and animation stay in the FBX until a deform path is needed.
    ufbx_load_opts opts = {};
    opts.generate_missing_normals = true;
    opts.target_axes = ufbx_axes_right_handed_z_up;
    opts.target_unit_meters = 1.0;
    ufbx_error error;
    ufbx_scene* scene = ufbx_load_memory(data, size, &opts, &error);
    if (!scene) throw std::runtime_error(error.description.length ? ufbx_text(error.description) : "not an FBX file");
    struct Release {
        ufbx_scene* scene;
        ~Release() { ufbx_free_scene(scene); }
    } release{scene};

    ImView view;
    std::vector<MeshPart>& parts = view.parts;
    for (size_t n = 0; n < scene->nodes.count; ++n) {
        ufbx_node* node = scene->nodes.data[n];
        if (att_node(ufbx_text(node->name))) {
            ImAttachment att;
            att.name = ufbx_text(node->name);
            const ufbx_matrix& m = node->node_to_world;
            for (int k = 0; k < 3; ++k) att.pos[k] = static_cast<float>(m.cols[3].v[k]);
            for (int axis = 0; axis < 3; ++axis) {
                const ufbx_vec3 c = m.cols[axis];
                const double len = std::sqrt(c.x * c.x + c.y * c.y + c.z * c.z);
                const double s = len > 1e-12 ? 1.0 / len : 0.0;
                att.orient[axis * 3] = static_cast<float>(c.x * s);
                att.orient[axis * 3 + 1] = static_cast<float>(c.y * s);
                att.orient[axis * 3 + 2] = static_cast<float>(c.z * s);
            }
            view.atts.push_back(std::move(att));
            continue;
        }
        ufbx_mesh* mesh = node->mesh;
        if (!mesh || mesh->num_faces == 0 || mesh->num_triangles == 0) continue;
        std::vector<uint32_t> tri(std::max<size_t>(mesh->max_face_triangles, 1) * 3);
        const size_t splits = mesh->material_parts.count > 0 ? mesh->material_parts.count : 1;
        for (size_t s = 0; s < splits; ++s) {
            MeshPart part;
            std::string node_name = ufbx_text(node->name);
            if (node_name.empty()) node_name = "mesh";
            const uint32_t mat_i = mesh->material_parts.count > 0 ? mesh->material_parts.data[s].index : 0;
            ufbx_material* material = nullptr;
            if (mat_i < node->materials.count) material = node->materials.data[mat_i];
            else if (mat_i < mesh->materials.count) material = mesh->materials.data[mat_i];
            if (material) {
                part.name = splits > 1 && material->name.length ? node_name + " / " + ufbx_text(material->name) : node_name;
                ufbx_texture* albedo = material->pbr.base_color.texture ? material->pbr.base_color.texture : material->fbx.diffuse_color.texture;
                part.albedo = file_name(albedo);
                part.normal_map = file_name(material->fbx.normal_map.texture);
            } else {
                part.name = node_name;
            }
            if (mesh->material_parts.count > 0) {
                const ufbx_mesh_part& slice = mesh->material_parts.data[s];
                append_faces(part, node, mesh, slice.face_indices.data, slice.face_indices.count, tri);
            } else {
                append_faces(part, node, mesh, nullptr, mesh->faces.count, tri);
            }
            if (!part.indices.empty()) parts.push_back(std::move(part));
        }
    }
    if (parts.empty() && view.atts.empty()) throw std::runtime_error("no mesh or a.* node in this .fbx");
    return view;
}

std::string trainz_mat_name(const MeshPart& part) {
    std::string name = fbx_name(part.name);
    if (name.find(".m.") != std::string::npos) return name;
    std::string stem = name;
    if (!part.albedo.empty()) {
        stem = fbx_name(part.albedo);
        const auto dot = stem.find('.');
        if (dot != std::string::npos) stem.resize(dot);
    }
    if (stem.empty()) stem = "mesh";
    return stem + ".m.onetex";
}

std::string albedo_file(const MeshPart& part) {
    if (!part.albedo.empty()) {
        std::string file = part.albedo;
        for (char& c : file)
            if (c == '\\') c = '/';
        const auto slash = file.find_last_of('/');
        if (slash != std::string::npos) file.erase(0, slash + 1);
        return fbx_name(file);
    }
    // Trainz looks up <stem>.texture beside the FBX when the material is <stem>.m.*.
    const std::string mat = trainz_mat_name(part);
    const auto m = mat.rfind(".m.");
    if (m != std::string::npos && m > 0) return mat.substr(0, m) + ".texture";
    return mat + ".texture";
}

std::string write_fbx(const ImView& view) {
    if (view.parts.empty() && view.atts.empty()) throw std::runtime_error("nothing to write to .fbx");

    struct MeshOut {
        int64_t geo_id = 0;
        int64_t model_id = 0;
        int64_t mat_id = 0;
        int64_t tex_id = 0;
        int64_t video_id = 0;
        std::string name;
        std::string mat_name;
        std::string albedo;
        std::vector<float> verts;
        std::vector<int32_t> polys;
        std::vector<int32_t> mat_ids;
        std::vector<float> normals;
        std::vector<float> uvs;
    };
    struct AttOut {
        int64_t model_id = 0;
        std::string name;
        float tx = 0, ty = 0, tz = 0;
        float rx = 0, ry = 0, rz = 0;
    };

    std::vector<MeshOut> meshes;
    meshes.reserve(view.parts.size());
    int64_t next_id = 1000;
    for (const MeshPart& part : view.parts) {
        const size_t vert_n = part.positions.size() / 3;
        if (vert_n == 0 || part.indices.size() < 3) continue;
        MeshOut mesh;
        mesh.verts.reserve(vert_n * 3);
        for (size_t v = 0; v < vert_n; ++v) {
            float x, y, z;
            to_fbx(part.positions[v * 3], part.positions[v * 3 + 1], part.positions[v * 3 + 2], x, y, z);
            mesh.verts.push_back(x);
            mesh.verts.push_back(y);
            mesh.verts.push_back(z);
        }
        mesh.polys.reserve(part.indices.size());
        std::vector<uint32_t> used;
        used.reserve(part.indices.size());
        for (size_t i = 0; i + 2 < part.indices.size(); i += 3) {
            const uint32_t a = part.indices[i];
            const uint32_t b = part.indices[i + 1];
            const uint32_t c = part.indices[i + 2];
            if (a >= vert_n || b >= vert_n || c >= vert_n) continue;
            mesh.polys.push_back(static_cast<int32_t>(a));
            mesh.polys.push_back(static_cast<int32_t>(b));
            mesh.polys.push_back(-static_cast<int32_t>(c) - 1);
            mesh.mat_ids.push_back(0);
            used.push_back(a);
            used.push_back(b);
            used.push_back(c);
        }
        if (mesh.polys.empty()) continue;
        if (part.normals.size() >= vert_n * 3) {
            mesh.normals.reserve(used.size() * 3);
            for (uint32_t idx : used) {
                float x, y, z;
                to_fbx(part.normals[idx * 3], part.normals[idx * 3 + 1], part.normals[idx * 3 + 2], x, y, z);
                const float len = std::sqrt(x * x + y * y + z * z);
                if (len > 1e-12f) {
                    x /= len;
                    y /= len;
                    z /= len;
                }
                mesh.normals.push_back(x);
                mesh.normals.push_back(y);
                mesh.normals.push_back(z);
            }
        }
        // Trainz T5956 needs UV channel0 to build tangents — emit real UVs, or zeros if the source had none.
        mesh.uvs.reserve(used.size() * 2);
        for (uint32_t idx : used) {
            if (part.uvs.size() >= vert_n * 2) {
                mesh.uvs.push_back(part.uvs[idx * 2]);
                mesh.uvs.push_back(part.uvs[idx * 2 + 1]);
            } else {
                mesh.uvs.push_back(0.f);
                mesh.uvs.push_back(0.f);
            }
        }
        mesh.geo_id = next_id++;
        mesh.model_id = next_id++;
        mesh.mat_id = next_id++;
        mesh.tex_id = next_id++;
        mesh.video_id = next_id++;
        mesh.mat_name = trainz_mat_name(part);
        mesh.name = fbx_name(part.name.empty() ? mesh.mat_name : part.name);
        mesh.albedo = albedo_file(part);
        meshes.push_back(std::move(mesh));
    }

    std::vector<AttOut> atts;
    atts.reserve(view.atts.size());
    for (const ImAttachment& att : view.atts) {
        AttOut row;
        row.model_id = next_id++;
        row.name = fbx_name(att.name);
        to_fbx(att.pos[0], att.pos[1], att.pos[2], row.tx, row.ty, row.tz);
        float axis[9];
        for (int a = 0; a < 3; ++a) {
            float x, y, z;
            to_fbx(att.orient[a * 3], att.orient[a * 3 + 1], att.orient[a * 3 + 2], x, y, z);
            const float len = std::sqrt(x * x + y * y + z * z);
            const float s = len > 1e-12f ? 1.f / len : 0.f;
            axis[a * 3] = x * s;
            axis[a * 3 + 1] = y * s;
            axis[a * 3 + 2] = z * s;
        }
        euler_xyz_deg(axis, row.rx, row.ry, row.rz);
        atts.push_back(std::move(row));
    }
    if (meshes.empty() && atts.empty()) throw std::runtime_error("nothing to write to .fbx");

    const size_t mesh_n = meshes.size();
    const size_t model_n = mesh_n + atts.size();
    const size_t mat_n = mesh_n;
    const size_t tex_n = mesh_n;
    const size_t video_n = mesh_n;
    size_t def_count = (mesh_n > 0 ? 1u : 0u) + (model_n > 0 ? 1u : 0u);
    if (mat_n) def_count += 1;
    if (tex_n) def_count += 1;
    if (video_n) def_count += 1;

    std::ostringstream out;
    out << "; FBX 7.4.0 project file\n"
           "FBXHeaderExtension:  {\n"
           "\tFBXHeaderVersion: 1003\n"
           "\tFBXVersion: 7400\n"
           "}\n"
           "GlobalSettings:  {\n"
           "\tVersion: 1000\n"
           "\tProperties70:  {\n"
           "\t\tP: \"UpAxis\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"UpAxisSign\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"FrontAxis\", \"int\", \"Integer\", \"\",2\n"
           "\t\tP: \"FrontAxisSign\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"CoordAxis\", \"int\", \"Integer\", \"\",0\n"
           "\t\tP: \"CoordAxisSign\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"OriginalUpAxis\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"OriginalUpAxisSign\", \"int\", \"Integer\", \"\",1\n"
           "\t\tP: \"UnitScaleFactor\", \"double\", \"Number\", \"\",100\n"
           "\t}\n"
           "}\n"
           "Definitions:  {\n"
           "\tVersion: 100\n"
           "\tCount: "
        << def_count << '\n';
    if (mesh_n) out << "\tObjectType: \"Geometry\" {\n\t\tCount: " << mesh_n << "\n\t}\n";
    if (model_n) out << "\tObjectType: \"Model\" {\n\t\tCount: " << model_n << "\n\t}\n";
    if (mat_n) out << "\tObjectType: \"Material\" {\n\t\tCount: " << mat_n << "\n\t}\n";
    if (tex_n) out << "\tObjectType: \"Texture\" {\n\t\tCount: " << tex_n << "\n\t}\n";
    if (video_n) out << "\tObjectType: \"Video\" {\n\t\tCount: " << video_n << "\n\t}\n";
    out << "}\nObjects:  {\n";

    for (const MeshOut& mesh : meshes) {
        out << "\tGeometry: " << mesh.geo_id << ", \"Geometry::\", \"Mesh\" {\n"
            << "\t\tVertices: *" << mesh.verts.size() << " {\n\t\t\ta: ";
        append_floats(out, mesh.verts);
        out << "\n\t\t}\n"
            << "\t\tPolygonVertexIndex: *" << mesh.polys.size() << " {\n\t\t\ta: ";
        append_ints(out, mesh.polys);
        out << "\n\t\t}\n\t\tGeometryVersion: 124\n";
        if (!mesh.normals.empty()) {
            out << "\t\tLayerElementNormal: 0 {\n"
                   "\t\t\tVersion: 101\n"
                   "\t\t\tName: \"\"\n"
                   "\t\t\tMappingInformationType: \"ByPolygonVertex\"\n"
                   "\t\t\tReferenceInformationType: \"Direct\"\n"
                   "\t\t\tNormals: *"
                << mesh.normals.size() << " {\n\t\t\t\ta: ";
            append_floats(out, mesh.normals);
            out << "\n\t\t\t}\n\t\t}\n";
        }
        out << "\t\tLayerElementUV: 0 {\n"
               "\t\t\tVersion: 101\n"
               "\t\t\tName: \"UVChannel_1\"\n"
               "\t\t\tMappingInformationType: \"ByPolygonVertex\"\n"
               "\t\t\tReferenceInformationType: \"Direct\"\n"
               "\t\t\tUV: *"
            << mesh.uvs.size() << " {\n\t\t\t\ta: ";
        append_floats(out, mesh.uvs);
        out << "\n\t\t\t}\n\t\t}\n";
        out << "\t\tLayerElementMaterial: 0 {\n"
               "\t\t\tVersion: 101\n"
               "\t\t\tName: \"\"\n"
               "\t\t\tMappingInformationType: \"ByPolygon\"\n"
               "\t\t\tReferenceInformationType: \"IndexToDirect\"\n"
               "\t\t\tMaterials: *"
            << mesh.mat_ids.size() << " {\n\t\t\t\ta: ";
        append_ints(out, mesh.mat_ids);
        out << "\n\t\t\t}\n\t\t}\n";
        out << "\t\tLayer: 0 {\n\t\t\tVersion: 100\n";
        if (!mesh.normals.empty()) {
            out << "\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementNormal\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n";
        }
        out << "\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementUV\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n"
               "\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementMaterial\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n"
               "\t\t}\n";
        out << "\t}\n";
        out << "\tModel: " << mesh.model_id << ", \"Model::" << mesh.name << "\", \"Mesh\" {\n"
               "\t\tVersion: 232\n"
               "\t\tProperties70:  {\n"
               "\t\t\tP: \"Lcl Scaling\", \"Lcl Scaling\", \"\", \"A\",1,1,1\n"
               "\t\t}\n"
               "\t\tShading: Y\n"
               "\t\tCulling: \"CullingOff\"\n"
               "\t}\n";
        out << "\tMaterial: " << mesh.mat_id << ", \"Material::" << mesh.mat_name << "\", \"\" {\n"
               "\t\tVersion: 102\n"
               "\t\tShadingModel: \"phong\"\n"
               "\t\tMultiLayer: 0\n"
               "\t\tProperties70:  {\n"
               "\t\t\tP: \"DiffuseColor\", \"Color\", \"\", \"A\",1,1,1\n"
               "\t\t\tP: \"Diffuse\", \"Number\", \"\", \"A\",1\n"
               "\t\t}\n"
               "\t}\n";
        out << "\tVideo: " << mesh.video_id << ", \"Video::" << mesh.albedo << "\", \"Clip\" {\n"
               "\t\tType: \"Clip\"\n"
               "\t\tProperties70:  {\n"
               "\t\t\tP: \"Path\", \"KString\", \"XRefUrl\", \"\", \""
            << mesh.albedo << "\"\n"
               "\t\t}\n"
               "\t\tUseMipMap: 0\n"
               "\t\tFilename: \""
            << mesh.albedo << "\"\n"
               "\t\tRelativeFilename: \""
            << mesh.albedo << "\"\n"
               "\t}\n";
        out << "\tTexture: " << mesh.tex_id << ", \"Texture::" << mesh.albedo << "\", \"\" {\n"
               "\t\tType: \"TextureVideoClip\"\n"
               "\t\tVersion: 202\n"
               "\t\tTextureName: \"Texture::"
            << mesh.albedo << "\"\n"
               "\t\tProperties70:  {\n"
               "\t\t\tP: \"UVSet\", \"KString\", \"\", \"\", \"UVChannel_1\"\n"
               "\t\t}\n"
               "\t\tMedia: \"Video::"
            << mesh.albedo << "\"\n"
               "\t\tFilename: \""
            << mesh.albedo << "\"\n"
               "\t\tRelativeFilename: \""
            << mesh.albedo << "\"\n"
               "\t}\n";
    }
    for (const AttOut& att : atts) {
        out << "\tModel: " << att.model_id << ", \"Model::" << att.name << "\", \"Null\" {\n"
               "\t\tVersion: 232\n"
               "\t\tProperties70:  {\n"
               "\t\t\tP: \"Lcl Translation\", \"Lcl Translation\", \"\", \"A\","
            << fmt_num(att.tx) << ',' << fmt_num(att.ty) << ',' << fmt_num(att.tz) << "\n";
        if (std::fabs(att.rx) > 1e-4f || std::fabs(att.ry) > 1e-4f || std::fabs(att.rz) > 1e-4f) {
            out << "\t\t\tP: \"Lcl Rotation\", \"Lcl Rotation\", \"\", \"A\","
                << fmt_num(att.rx) << ',' << fmt_num(att.ry) << ',' << fmt_num(att.rz) << '\n';
        }
        out << "\t\t}\n\t}\n";
    }
    out << "}\nConnections:  {\n";
    for (const MeshOut& mesh : meshes) {
        out << "\tC: \"OO\"," << mesh.geo_id << ',' << mesh.model_id << '\n';
        out << "\tC: \"OO\"," << mesh.model_id << ",0\n";
        out << "\tC: \"OO\"," << mesh.mat_id << ',' << mesh.model_id << '\n';
        out << "\tC: \"OP\"," << mesh.tex_id << ',' << mesh.mat_id << ", \"DiffuseColor\"\n";
        out << "\tC: \"OO\"," << mesh.video_id << ',' << mesh.tex_id << '\n';
    }
    for (const AttOut& att : atts) {
        out << "\tC: \"OO\"," << att.model_id << ",0\n";
    }
    out << "}\n";
    return out.str();
}
