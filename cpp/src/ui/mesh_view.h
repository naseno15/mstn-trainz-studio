#pragma once

#include <QOpenGLFunctions_3_3_Core>
#include <QOpenGLWidget>
#include <QString>
#include <cstdint>
#include <vector>

class QMouseEvent;
class QWheelEvent;

struct ViewPart {
    QString name;
    std::vector<float> positions;
    std::vector<float> uvs;
    std::vector<uint32_t> indices;
};

int studio_softbox_peak();

class MeshView : public QOpenGLWidget, protected QOpenGLFunctions_3_3_Core {
    Q_OBJECT

public:
    explicit MeshView(QWidget* parent = nullptr);

    void setParts(std::vector<ViewPart> parts);
    void setDebugMode(int mode);
    void setEnvironment(int index);
    void setSun(bool on);
    void setGround(bool on);
    void resetCamera();
    int partCount() const { return static_cast<int>(parts_.size()); }

protected:
    void initializeGL() override;
    void resizeGL(int w, int h) override;
    void paintGL() override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

private:
    struct Lamp {
        float pos[3];
        float range;
    };
    void upload();
    void draw_shadows();
    void draw_sky();
    void draw_parts(bool depth_only);
    void frame_camera();

    std::vector<ViewPart> parts_;
    std::vector<Lamp> lamps_;
    bool upload_pending_ = false;
    bool shadow_dirty_ = true;
    bool gl_ready_ = false;
    int debug_mode_ = 0;
    int env_index_ = 0;
    bool sun_ = false;
    bool ground_ = false;
    float yaw_ = 35.f;
    float pitch_ = 25.f;
    float dist_ = 8.f;
    float target_[3] = {0, 0, 0};
    float center_[3] = {0, 0, 0};
    float radius_ = 1.f;
    QPoint last_;
    unsigned mesh_prog_ = 0;
    unsigned sky_prog_ = 0;
    unsigned depth_prog_ = 0;
    unsigned white_tex_ = 0;
    unsigned env_tex_ = 0;
    unsigned shadow_tex_ = 0;
    unsigned shadow_fbo_ = 0;
    unsigned shadow_depth_ = 0;
    unsigned vao_ = 0;
    unsigned vbo_ = 0;
    unsigned ibo_ = 0;
    unsigned ground_vao_ = 0;
    unsigned ground_vbo_ = 0;
    unsigned sky_vao_ = 0;
    unsigned sky_vbo_ = 0;
    float shadow_vp_[8][16] = {};
    int shadow_count_ = 0;
    std::vector<unsigned> part_first_;
    std::vector<int> part_count_;
    int index_total_ = 0;
};
