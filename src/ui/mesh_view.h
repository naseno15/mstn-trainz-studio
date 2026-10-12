#pragma once

#include <QElapsedTimer>
#include <QHash>
#include <QMatrix4x4>
#include <deque>
#include <QOpenGLFunctions_3_3_Core>
#include <QOpenGLWidget>
#include <QString>
#include <cstdint>
#include <vector>

class QKeyEvent;
class QLabel;
class QMouseEvent;
class QTimer;
class QWheelEvent;

struct ViewAtt {
    float pos[3] = {};
    float orient[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};  // row-major, each row is an axis
    float quat[4] = {0, 0, 0, 1};                   // xyzw, same pose as orient
    int file = 0;
    int off = -1;  // .trainzmesh byte offset of pos+quat, -1 when not writable
    QString name;
};

struct ViewPart {
    QString name;
    std::vector<float> positions;
    std::vector<float> normals;
    std::vector<float> uvs;
    std::vector<uint32_t> indices;
    std::vector<unsigned char> rgba;
    std::vector<unsigned char> nrgba;
    std::vector<unsigned char> prgba;
    int tex_w = 0;
    int tex_h = 0;
    int nrm_w = 0;
    int nrm_h = 0;
    int prm_w = 0;
    int prm_h = 0;
    bool two_sided = false;
    QString material;
};

int studio_softbox_peak();

class MeshView : public QOpenGLWidget, protected QOpenGLFunctions_3_3_Core {
    Q_OBJECT

public:
    explicit MeshView(QWidget* parent = nullptr);

    void setParts(std::vector<ViewPart> parts);
    void setAttachments(std::vector<ViewAtt> atts);
    void updateAttachment(int index, const ViewAtt& att);
    void setAttFileShown(int file, bool on);
    void setAttSelected(int index);
    // Move tool: left-drag an attachment. On an axis line: along that axis. On the origin: in the view plane. Esc cancels.
    void setMoveTool(bool on);
    void setDebugMode(int mode);
    void setShade(int mode);
    void setEnvironment(int index);
    void setSun(bool on);
    void setSunPose(float azimuth_deg, float elevation_deg, float intensity);
    void setArrayLight(int index, bool on);
    void setEmissiveScale(float scale);
    void setMoon(bool on);
    void setSunWarm(float warm);
    void setGround(bool on);
    void setTwoSided(bool on);
    void setPartTwo(int index, bool on);
    void setFaceOrient(bool on);
    void setAttNames(bool on);
    void setAnimMatrix(const QMatrix4x4& model);
    void setShown(int index, bool on);
    void setHighlight(std::vector<uint8_t> on);
    void resetCamera();
    // Sidebar nav gizmo. axis: 0 +X, 1 -X, 2 +Y, 3 -Y, 4 +Z, 5 -Z.
    void orbitDrag(float dx_px, float dy_px);
    void lookAxis(int axis);
    // Screen tips of the world axes: x,y,z triples, y down, z toward the camera.
    void navTips(float out[9]) const;
    // Smoothly fly the orbit target/distance to frame the highlighted parts.
    void flyToHighlight();
    // Panel rects (widget coords, y from top) whose backdrop gets blurred.
    void setBlurRects(const QRect& a, const QRect& b) { blur_rect_[0] = a; blur_rect_[1] = b; update(); }
    void setWalk(int key, bool down);
    void toggleFps();
    int partCount() const { return static_cast<int>(parts_.size()); }

signals:
    void partPicked(int index);  // Shift+click on a part
    void attPicked(int index);
    void attMoved(int index, float x, float y, float z);
    void attDragDone();  // release or Esc after a Move-tool drag
    void pickCleared();  // Shift+click on empty viewport
    void cameraMoved();

protected:
    void initializeGL() override;
    void resizeGL(int w, int h) override;
    void paintGL() override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void keyReleaseEvent(QKeyEvent* event) override;

private:
    struct Lamp {
        float pos[3];
        float range;
    };
    void upload();
    void draw_shadows();
    void draw_sky();
    void draw_disc(const QMatrix4x4& proj, const QMatrix4x4& view, const QVector3D& eye, const QVector3D& dir, float radius, float r, float g, float b, float a, bool additive);
    void draw_guides(const QMatrix4x4& proj, const QMatrix4x4& view);
    void draw_atts(const QMatrix4x4& proj, const QMatrix4x4& view);
    void paint_att_names(const QMatrix4x4& proj, const QMatrix4x4& view);
    void rebuild_guides();
    void rebuild_atts();
    void frame_camera();
    int pick_part(const QPoint& pos) const;
    int pick_att(const QPoint& pos, int* axis = nullptr) const;
    bool mouse_ray(const QPoint& pos, QVector3D* origin, QVector3D* dir, QVector3D* forward) const;
    bool drag_point(const QPoint& pos, QVector3D* out) const;
    bool pick_press_ = false;
    bool move_tool_ = false;
    int drag_att_ = -1;
    int drag_axis_ = -1;   // -1 view plane
    int shift_axis_ = -1;  // world axis locked by Shift during a free drag
    QVector3D drag_from_;
    QVector3D drag_grab_;
    bool fly_on_ = false;
    bool fly_orient_ = false;
    float fly_from_[4] = {};
    float fly_to_[4] = {};
    float fly_yaw0_ = 0.f;
    float fly_yaw1_ = 0.f;
    float fly_pitch0_ = 0.f;
    float fly_pitch1_ = 0.f;
    QElapsedTimer fly_clock_;
    void coast();
    void kick_coast();
    void cam_right(float* x, float* y) const;
    void note_keys(int key, bool down, bool repeat);
    void sync_fps();
    void bind_widget_target();
    void blur_panels();
    QRect blur_rect_[2];
    static constexpr int kBlurLevels = 4;
    unsigned blur_fbo_[kBlurLevels] = {};
    unsigned blur_tex_[kBlurLevels] = {};
    int blur_w_ = 0;
    int blur_h_ = 0;
    void fb_size(int* w, int* h) const;

    std::vector<ViewPart> parts_;
    std::vector<uint8_t> highlight_;
    std::vector<Lamp> lamps_;
    bool upload_pending_ = false;
    bool shadow_dirty_ = true;
    bool gl_ready_ = false;
    int debug_mode_ = 0;
    int shade_ = 3;
    int env_index_ = 0;
    bool sun_ = true;
    float sun_az_ = 135.f;
    float sun_el_ = 45.f;
    float sun_int_ = 1.4f;
    bool array_on_[5] = {true, true, true, true, true};
    float emis_scale_ = 0.15f;
    bool moon_ = false;
    bool key_shadow_ = false;
    float sun_warm_ = 0.f;
    unsigned glow_prog_ = 0;
    unsigned glow_vao_ = 0;
    unsigned glow_vbo_ = 0;
    bool ground_ = false;
    bool two_sided_ = false;
    bool face_orient_ = false;
    bool att_names_ = false;
    QMatrix4x4 anim_model_;
    bool guides_dirty_ = true;
    float yaw_ = 35.f;
    float pitch_ = 25.f;
    float dist_ = 8.f;
    float target_[3] = {0, 0, 0};
    float center_[3] = {0, 0, 0};
    float radius_ = 1.f;
    QPoint last_;
    QTimer* coast_ = nullptr;
    QElapsedTimer clock_;
    float spin_yaw_ = 0.f;
    float spin_pitch_ = 0.f;
    float move_v_[3] = {0, 0, 0};
    float elev_v_ = 0.f;
    float zoom_v_ = 0.f;
    float fov_ = 40.f;  // Ctrl+wheel = optical zoom
    bool key_up_ = false;
    bool key_down_ = false;
    bool key_left_ = false;
    bool key_right_ = false;
    bool key_pgup_ = false;
    bool key_pgdn_ = false;
    bool show_fps_ = false;
    QLabel* fps_ = nullptr;
    QElapsedTimer fps_clock_;
    qint64 fps_last_ns_ = 0;
    int frame_id_ = 0;
    std::deque<float> fps_paint_;
    std::deque<float> fps_wall_;
    unsigned mesh_prog_ = 0;
    unsigned sky_prog_ = 0;
    unsigned depth_prog_ = 0;
    unsigned white_tex_ = 0;
    unsigned env_tex_ = 0;
    unsigned shadow_tex_ = 0;
    unsigned shadow_fbo_ = 0;
    unsigned shadow_depth_ = 0;
    unsigned sun_tex_ = 0;
    unsigned sun_fbo_ = 0;
    unsigned sun_depth_ = 0;
    unsigned vao_ = 0;
    unsigned vbo_ = 0;
    unsigned ibo_ = 0;
    unsigned ground_vao_ = 0;
    unsigned ground_vbo_ = 0;
    unsigned sky_vao_ = 0;
    unsigned sky_vbo_ = 0;
    unsigned line_prog_ = 0;
    unsigned line_vao_ = 0;
    unsigned line_vbo_ = 0;
    unsigned gizmo_vao_ = 0;
    unsigned gizmo_vbo_ = 0;
    int guide_count_ = 0;
    unsigned att_vao_ = 0;
    unsigned att_vbo_ = 0;
    int att_verts_ = 0;
    bool atts_dirty_ = false;
    unsigned label_prog_ = 0;
    unsigned label_vao_ = 0;
    unsigned label_vbo_ = 0;
    struct AttLabel {
        unsigned tex = 0;
        int w = 0;
        int h = 0;
    };
    QHash<QString, AttLabel> att_labels_;
    std::vector<ViewAtt> atts_;
    std::vector<char> att_on_;
    int att_sel_ = -1;
    std::vector<uint8_t> shown_;
    struct PartMaps {
        unsigned albedo = 0;
        unsigned normal = 0;
        unsigned parameter = 0;
    };
    std::vector<PartMaps> part_maps_;
    float shadow_vp_[8][16] = {};
    int shadow_count_ = 0;
    std::vector<unsigned> part_first_;
    std::vector<int> part_count_;
    int index_total_ = 0;
};
