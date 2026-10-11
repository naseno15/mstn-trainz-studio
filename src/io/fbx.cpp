#include "fbx.h"

#include "ufbx.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string ufbx_text(ufbx_string text) {
    if (!text.data || text.length == 0) return {};
    return std::string(text.data, text.length);
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

}  // namespace

std::vector<MeshPart> parse_fbx_parts(const uint8_t* data, size_t size) {
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

    std::vector<MeshPart> parts;
    for (size_t n = 0; n < scene->nodes.count; ++n) {
        ufbx_node* node = scene->nodes.data[n];
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
    if (parts.empty()) throw std::runtime_error("no mesh in this .fbx");
    return parts;
}
