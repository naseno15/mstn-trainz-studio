#pragma once

#include <QImage>
#include <QObject>
#include <QString>

#include <vector>

class ParamCanvas;
class MapEditor;

class QLabel;
class QListWidget;
class QPlainTextEdit;
class QTableWidget;
class QWidget;

int magic_pick_count(const unsigned char* rgba, int width, int height, int x, int y, int tol, bool contiguous);

class Texmesh : public QObject {
    Q_OBJECT

public:
    explicit Texmesh(QWidget* host);

    void set_active(bool on);
    void set_page(const QString& page);
    QStringList ve_paths() const;
    bool form_on() const;
    QString form_title() const;
    QString form_tabs() const;
    int form_tab() const;
    bool form_tool() const;
    QString form_blocks() const;
    QString center_tip() const;
    QString center_list() const;
    QString center_prev() const;
    QString brand() const;
    QString blurb() const;
    QString actions_json() const;
    QString table_json() const;
    QString queue_json() const;
    QString well_left() const;
    QString well_right() const;
    void drop_paths(const QStringList& paths);
    void pick_row(int row);
    QString footer_cap() const;
    QString foot_note() const;
    bool show_queue() const;
    int dock_width() const;
    QString status_line() const;

    void place_well(const QString& key, int x, int y, int w, int h);
    void place_queue(int x, int y, int w, int h);
    void place_form_tool(int x, int y, int w, int h);
    void hide_all();
    void set_form_tab(int tab);
    void set_field(const QString& key, const QString& raw);
    void run_dock(const QString& action);
    void run_action(const QString& action);
    void queue_remove();
    void queue_clear();

signals:
    void changed();

private:
    void refresh_texture();
    void refresh_mesh();
    void rebuild_texture_table();
    void add_images(const QStringList& paths);
    void add_meshes(const QStringList& paths);
    void select_texture_row(int row);
    QString texture_text() const;
    void apply_role_hints(const QString& file_name);
    void log_texture(const QString& text);
    void log_mesh(const QString& text);
    void scan_texture_rules(bool fix);
    void scan_ve39(bool fix);
    void scan_mesh_rules();
    void scan_materials(bool fix);
    void save_texture_one();
    void save_texture_all();
    void resize_prep();
    void check_texture_file();
    void scan_texture_folder();
    void save_meshes();
    void load_lm();
    void open_parameter_path(const QString& path);
    void show_parameter();
    void push_undo();
    void param_op(const QString& op);
    void save_parameter();
    void export_channel(const QString& key);
    void open_denoise_path(const QString& path);
    void run_denoise();
    void show_denoise(bool original);
    void save_denoise();
    QImage param_view() const;
    void pick_magic(int x, int y);
    void clear_magic();
    bool magic_allows(int x, int y) const;
    QString path_for_role(const QString& family, const QString& role) const;
    friend class ParamCanvas;
    friend class MapEditor;

    QWidget* host_ = nullptr;
    bool active_ = false;
    QString page_ = QStringLiteral("meshops");
    int form_tab_ = 0;
    QString status_;

    QTableWidget* tex_table_ = nullptr;
    QPlainTextEdit* tex_preview_ = nullptr;
    QPlainTextEdit* tex_log_ = nullptr;
    MapEditor* map_view_ = nullptr;
    QTableWidget* lm_table_ = nullptr;
    QPlainTextEdit* lm_preview_ = nullptr;
    QPlainTextEdit* lm_log_ = nullptr;
    QWidget* param_canvas_ = nullptr;
    QListWidget* param_queue_ = nullptr;
    QLabel* denoise_view_ = nullptr;
    QRect canvas_rect_;
    void sync_canvas();

    QString primary_;
    QString alpha_;
    bool alpha_on_ = false;
    QString tile_ = QStringLiteral("st");
    QString usage_;
    QString normal_;
    QString compress_;
    bool prep_on_ = true;
    QString prep_map_ = QStringLiteral("auto");
    QString prep_resize_ = QStringLiteral("PoT");
    QString prep_fmt_ = QStringLiteral("SAME");
    int prep_pct_ = 50;
    int prep_w_ = 1024;
    int prep_h_ = 1024;
    int prep_max_ = 2048;
    bool prep_flip_ = false;
    bool prep_pot_ = true;

    double lm_offset_ = 0.01;
    QString lm_calc_ = QStringLiteral("center");
    double lm_mult_ = 1;
    double lm_anim_ = 0;
    double lm_render_ = 0;
    double lm_att_ = 0.06;

    QImage param_image_;
    QImage param_original_;
    QString param_path_;
    bool ch_r_ = true;
    bool ch_g_ = true;
    bool ch_b_ = true;
    bool ch_a_ = true;
    bool param_gray_ = false;
    int p_offset_ = 0;
    double p_scale_ = 1;
    int p_fill_ = 0;
    int p_bright_ = 0;
    double p_contrast_ = 1;
    int p_mean_ = 128;
    QString paint_tool_ = QStringLiteral("Brush");
    int brush_ = 24;
    int paint_val_ = 255;
    int hard_ = 80;
    int tol_ = 12;
    bool contig_ = true;
    QString ov_mode_ = QStringLiteral("multiply");
    QString ov_src_ = QStringLiteral("gray");
    int ov_opacity_ = 100;
    QString export_tone_ = QStringLiteral("Color");
    QString stamp_note_ = QStringLiteral("Drop a gray image on a channel, then Apply stamp.");
    QImage stamp_;
    std::vector<QImage> undo_;
    std::vector<QImage> redo_;
    std::vector<unsigned char> magic_;

    QImage denoise_orig_;
    QImage denoise_work_;
    QString denoise_path_;
    QString strength_ = QStringLiteral("heavy");
    bool prefer_oidn_ = true;
    bool lock_black_ = true;
    int black_ = 8;
    bool show_work_ = false;
    QString denoise_prog_ = QStringLiteral("Open a bake.");
};
