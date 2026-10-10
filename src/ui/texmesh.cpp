#include "ui/texmesh.h"
#include "ui/feedback.h"

#include "io/lm_txt.h"
#include "io/mat_name.h"
#include "io/texture_txt.h"
#include "io/trainzmesh.h"

#include <QCoreApplication>
#include <QDir>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QListWidget>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QPixmap>
#include <QPlainTextEdit>
#include <QProcess>
#include <QPushButton>
#include <QSlider>
#include <QTemporaryDir>
#include <QProcess>
#include <QTableWidget>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>
#include <atomic>
#include <thread>
#include <QEasingCurve>
#include <QPointer>
#include <QThread>
#include <QVariantAnimation>
#include <array>
#include <cmath>
#include <optional>
#include <cstring>
#include <functional>
#include <map>
#include <queue>

namespace {

const QString k_omit = QStringLiteral("—");
const char* k_style = "QTableWidget,QPlainTextEdit,QListWidget,QLabel{background:#1a1e26;color:#f2f4f8;border:none;font:12px 'Segoe UI';} QHeaderView::section{background:#1a1e26;color:#8b93a1;border:none;padding:4px;}";

QJsonObject jnote(const QString& text) { return {{QStringLiteral("type"), QStringLiteral("note")}, {QStringLiteral("text"), text}}; }
QJsonObject jsection(const QString& label) { return {{QStringLiteral("type"), QStringLiteral("section")}, {QStringLiteral("label"), label}}; }
QJsonObject jfield(const QString& id, const QString& label, const QString& value) {
    return {{QStringLiteral("type"), QStringLiteral("field")}, {QStringLiteral("id"), id}, {QStringLiteral("label"), label}, {QStringLiteral("value"), value}, {QStringLiteral("placeholder"), QString()}};
}
QJsonObject jpills(const QString& id, const QString& label, const QStringList& options, const QString& value) {
    return {{QStringLiteral("type"), QStringLiteral("pills")}, {QStringLiteral("id"), id}, {QStringLiteral("label"), label}, {QStringLiteral("options"), QJsonArray::fromStringList(options)}, {QStringLiteral("value"), value}, {QStringLiteral("enabled"), true}};
}
QJsonObject jcheck(const QString& id, const QString& label, bool on) {
    return {{QStringLiteral("type"), QStringLiteral("check")}, {QStringLiteral("id"), id}, {QStringLiteral("label"), label}, {QStringLiteral("on"), on}, {QStringLiteral("enabled"), true}};
}
QJsonObject jbuttons(const QList<QPair<QString, QString>>& items, bool accent_first) {
    QJsonArray rows;
    for (int i = 0; i < items.size(); ++i) {
        QJsonObject row{{QStringLiteral("id"), items[i].first}, {QStringLiteral("label"), items[i].second}, {QStringLiteral("accent"), accent_first && i == 0}};
        rows.append(row);
    }
    return {{QStringLiteral("type"), QStringLiteral("buttons")}, {QStringLiteral("items"), rows}};
}
QJsonObject jfile(const QString& id, const QString& label, const QString& value, const QString& pick, const QString& placeholder, bool enabled, const QString& check, bool on) {
    QJsonObject row{{QStringLiteral("type"), QStringLiteral("file")}, {QStringLiteral("id"), id}, {QStringLiteral("label"), label}, {QStringLiteral("value"), value}, {QStringLiteral("placeholder"), placeholder}, {QStringLiteral("pick"), pick}, {QStringLiteral("glyph"), QString()}, {QStringLiteral("enabled"), enabled}};
    if (!check.isEmpty()) {
        row.insert(QStringLiteral("check"), check);
        row.insert(QStringLiteral("on"), on);
    }
    return row;
}
QString dump(const QJsonArray& rows) { return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact)); }

QString omit(const QString& value) { return value == k_omit ? QString() : value; }
QString shown(const QString& value) { return value.isEmpty() ? k_omit : value; }

bool is_image(const QString& path) {
    const QString low = path.toLower();
    return low.endsWith(".png") || low.endsWith(".tga") || low.endsWith(".jpg") || low.endsWith(".jpeg") || low.endsWith(".bmp") || low.endsWith(".dds") || low.endsWith(".hdr") || low.endsWith(".tif") || low.endsWith(".tiff") || low.endsWith(".webp");
}
bool is_mesh(const QString& path) {
    const QString low = path.toLower();
    return low.endsWith(".trainzmesh") || low.endsWith(".im") || low.endsWith(".fbx") || low.endsWith(".lm.txt") || low.endsWith(".lm");
}

QStringList dropped_paths(const QMimeData* mime) {
    QStringList paths;
    if (mime == nullptr) return paths;
    for (const QUrl& url : mime->urls()) {
        const QString path = url.toLocalFile();
        if (!path.isEmpty()) paths << path;
    }
    return paths;
}

void style_table(QTableWidget* table) {
    apply_themed_qss(table, QString::fromLatin1(k_style));
    table->setShowGrid(false);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setSelectionMode(QAbstractItemView::ExtendedSelection);
    table->verticalHeader()->setVisible(false);
    table->setAcceptDrops(true);
    table->setWordWrap(false);
    table->setTextElideMode(Qt::ElideRight);
}

int pot_down(int n) {
    if (n <= 1) return 1;
    int v = 1;
    while (v * 2 > 0 && v * 2 <= n) v *= 2;
    return v;
}
int pot_up(int n) {
    int v = 1;
    while (v < n && v < 65536) v *= 2;
    return v;
}

QImage load_image(const QString& path) {
    QImageReader reader(path);
    reader.setAutoTransform(true);
    return reader.read();
}

QString bytes_label(qint64 n) {
    if (n < 1024) return QString::number(n) + QStringLiteral(" B");
    if (n < 1024 * 1024) return QString::number(n / 1024) + QStringLiteral(" KB");
    return QString::number(n / 1024.0 / 1024.0, 'f', 1) + QStringLiteral(" MB");
}

int channel_index(const QString& key) {
    if (key == QLatin1String("G")) return 1;
    if (key == QLatin1String("B")) return 2;
    if (key == QLatin1String("A")) return 3;
    return 0;
}

void mutate_channels(QImage& image, bool r, bool g, bool b, bool a, const std::function<int(int)>& fn) {
    image = image.convertToFormat(QImage::Format_RGBA8888);
    const bool use[4] = {r, g, b, a};
    for (int y = 0; y < image.height(); ++y) {
        uchar* row = image.scanLine(y);
        for (int x = 0; x < image.width(); ++x) {
            for (int c = 0; c < 4; ++c)
                if (use[c]) row[c] = static_cast<uchar>(std::clamp(fn(row[c]), 0, 255));
            row += 4;
        }
    }
}

// Runs fn(row) for every row on all cores; rows are independent in the filters below.
void parallel_rows(int rows, const std::function<void(int)>& fn) {
    std::atomic<int> next{0};
    auto work = [&] {
        for (int y = next.fetch_add(1); y < rows; y = next.fetch_add(1)) fn(y);
    };
    const int count = std::max(1u, std::min(std::thread::hardware_concurrency(), 16u));
    std::vector<std::thread> pool;
    for (int i = 1; i < count; ++i) pool.emplace_back(work);
    work();
    for (std::thread& t : pool) t.join();
}

QImage box_blur(const QImage& src, int radius) {
    if (radius < 1) return src;
    QImage image = src.convertToFormat(QImage::Format_RGBA8888);
    QImage out = image;
    out.detach();  // before the threads touch scanLine()
    const int w = image.width();
    const int h = image.height();
    parallel_rows(h, [&](int y) {
        uchar* dst = out.scanLine(y);
        for (int x = 0; x < w; ++x) {
            int sum[4] = {};
            int count = 0;
            for (int ky = -radius; ky <= radius; ++ky) {
                const int yy = std::clamp(y + ky, 0, h - 1);
                const uchar* row = image.constScanLine(yy);
                for (int kx = -radius; kx <= radius; ++kx) {
                    const int xx = std::clamp(x + kx, 0, w - 1);
                    const uchar* p = row + xx * 4;
                    for (int c = 0; c < 4; ++c) sum[c] += p[c];
                    ++count;
                }
            }
            for (int c = 0; c < 4; ++c) dst[c] = static_cast<uchar>(sum[c] / std::max(1, count));
            dst += 4;
        }
    });
    return out;
}

bool nearly_black(const uchar* p, int threshold) { return p[0] <= threshold && p[1] <= threshold && p[2] <= threshold; }

class DropTable : public QTableWidget {
public:
    std::function<void(const QStringList&)> on_drop;
    explicit DropTable(QWidget* parent) : QTableWidget(parent) {
        setAcceptDrops(true);
        viewport()->setAcceptDrops(true);
    }
protected:
    void dragEnterEvent(QDragEnterEvent* event) override {
        if (event->mimeData()->hasUrls()) event->acceptProposedAction();
    }
    void dragMoveEvent(QDragMoveEvent* event) override {
        if (event->mimeData()->hasUrls()) event->acceptProposedAction();
    }
    void dropEvent(QDropEvent* event) override {
        if (on_drop) on_drop(dropped_paths(event->mimeData()));
        event->acceptProposedAction();
    }
};

QString oidn_exe() {
    const QString name = QStringLiteral("oidnDenoise.exe");
    const QStringList candidates = {
        QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("vendor/oidn/bin/") + name),
#ifdef QML_DIR
        QDir(QStringLiteral(QML_DIR)).filePath(QStringLiteral("../../vendor/oidn/bin/") + name),
#endif
        QDir(QStringLiteral("vendor/oidn/bin")).filePath(name),
    };
    for (const QString& path : candidates)
        if (QFileInfo::exists(path)) return QFileInfo(path).absoluteFilePath();
    return {};
}

std::vector<unsigned char> magic_mask_of(const unsigned char* rgba, int width, int height, int x, int y, int tol, bool contiguous) {
    std::vector<unsigned char> near(static_cast<size_t>(width * height));
    if (rgba == nullptr || width < 1 || height < 1) return near;
    x = std::clamp(x, 0, width - 1);
    y = std::clamp(y, 0, height - 1);
    const unsigned char* seed = rgba + (y * width + x) * 4;
    for (int yy = 0; yy < height; ++yy) {
        for (int xx = 0; xx < width; ++xx) {
            const unsigned char* p = rgba + (yy * width + xx) * 4;
            int delta = 0;
            for (int c = 0; c < 4; ++c) delta = std::max(delta, std::abs(int(p[c]) - int(seed[c])));
            near[static_cast<size_t>(yy * width + xx)] = delta <= tol ? 1 : 0;
        }
    }
    if (!contiguous) return near;
    std::vector<unsigned char> island(near.size());
    std::queue<int> wait;
    auto push = [&](int xx, int yy) {
        const size_t index = static_cast<size_t>(yy * width + xx);
        if (!near[index] || island[index]) return;
        island[index] = 1;
        wait.push(static_cast<int>(index));
    };
    push(x, y);
    while (!wait.empty()) {
        const int index = wait.front();
        wait.pop();
        const int xx = index % width;
        const int yy = index / width;
        if (xx > 0) push(xx - 1, yy);
        if (xx + 1 < width) push(xx + 1, yy);
        if (yy > 0) push(xx, yy - 1);
        if (yy + 1 < height) push(xx, yy + 1);
    }
    return island;
}

bool write_pfm(const QString& path, const QImage& image) {
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
    const QImage rgb = image.convertToFormat(QImage::Format_RGB888);
    file.write("PF\n");
    file.write(QStringLiteral("%1 %2\n-1.0\n").arg(rgb.width()).arg(rgb.height()).toLatin1());
    std::vector<float> row(static_cast<size_t>(rgb.width() * 3));
    for (int y = rgb.height() - 1; y >= 0; --y) {
        const uchar* src = rgb.constScanLine(y);
        for (int x = 0; x < rgb.width(); ++x) {
            row[static_cast<size_t>(x * 3)] = src[x * 3] / 255.f;
            row[static_cast<size_t>(x * 3 + 1)] = src[x * 3 + 1] / 255.f;
            row[static_cast<size_t>(x * 3 + 2)] = src[x * 3 + 2] / 255.f;
        }
        file.write(reinterpret_cast<const char*>(row.data()), static_cast<qint64>(row.size() * sizeof(float)));
    }
    return true;
}

QImage read_pfm(const QString& path, const QImage& alpha_source) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    const QByteArray magic = file.readLine().trimmed();
    const QByteArray dims = file.readLine().trimmed();
    file.readLine();
    const QList<QByteArray> parts = dims.split(' ');
    if (parts.size() < 2) return {};
    const int w = parts[0].toInt();
    const int h = parts[1].toInt();
    const int channels = magic == "PF" ? 3 : 1;
    const QByteArray data = file.readAll();
    if (w < 1 || h < 1 || data.size() < w * h * channels * 4) return {};
    QImage out(w, h, QImage::Format_RGBA8888);
    const float* samples = reinterpret_cast<const float*>(data.constData());
    const QImage src = alpha_source.convertToFormat(QImage::Format_RGBA8888);
    for (int y = 0; y < h; ++y) {
        const int src_y = h - 1 - y;
        uchar* dst = out.scanLine(src_y);
        const uchar* ain = (src_y < src.height() && w == src.width()) ? src.constScanLine(src_y) : nullptr;
        for (int x = 0; x < w; ++x) {
            const float* p = samples + (static_cast<size_t>(y) * w + x) * channels;
            const int r = std::clamp(int(std::lround(p[0] * 255.f)), 0, 255);
            const int g = std::clamp(int(std::lround((channels > 1 ? p[1] : p[0]) * 255.f)), 0, 255);
            const int b = std::clamp(int(std::lround((channels > 2 ? p[2] : p[0]) * 255.f)), 0, 255);
            dst[x * 4] = static_cast<uchar>(r);
            dst[x * 4 + 1] = static_cast<uchar>(g);
            dst[x * 4 + 2] = static_cast<uchar>(b);
            dst[x * 4 + 3] = ain ? ain[x * 4 + 3] : 255;
        }
    }
    return out;
}

QImage bilateral_rgb(const QImage& src, int radius, int sigma, const std::function<void(int)>& report = {}) {
    const QImage image = src.convertToFormat(QImage::Format_RGBA8888);
    QImage out = image;
    out.detach();  // before the threads touch scanLine()
    radius = std::clamp(radius, 1, 6);
    sigma = std::max(8, sigma);
    parallel_rows(image.height(), [&](int y) {
        if (report && y % 16 == 0) report(y * 100 / image.height());
        uchar* dst = out.scanLine(y);
        for (int x = 0; x < image.width(); ++x) {
            const uchar* center = image.constScanLine(y) + x * 4;
            double sum[3] = {};
            double weight = 0;
            for (int ky = -radius; ky <= radius; ++ky) {
                const int yy = std::clamp(y + ky, 0, image.height() - 1);
                const uchar* row = image.constScanLine(yy);
                for (int kx = -radius; kx <= radius; ++kx) {
                    const int xx = std::clamp(x + kx, 0, image.width() - 1);
                    const uchar* p = row + xx * 4;
                    int dist = 0;
                    for (int c = 0; c < 3; ++c) dist = std::max(dist, std::abs(int(p[c]) - int(center[c])));
                    if (dist > sigma) continue;
                    const double wgt = 1.0 / (1.0 + dist);
                    for (int c = 0; c < 3; ++c) sum[c] += p[c] * wgt;
                    weight += wgt;
                }
            }
            for (int c = 0; c < 3; ++c) dst[c] = static_cast<uchar>(sum[c] / std::max(weight, 1e-6));
            dst[3] = center[3];
            dst += 4;
        }
    });
    return out;
}

}  // namespace

int magic_pick_count(const unsigned char* rgba, int width, int height, int x, int y, int tol, bool contiguous) {
    const auto mask = magic_mask_of(rgba, width, height, x, y, tol, contiguous);
    return int(std::count(mask.begin(), mask.end(), 1));
}

class MapEditor : public QWidget {
public:
    explicit MapEditor(Texmesh* owner, QWidget* parent) : QWidget(parent), owner_(owner) {
        apply_themed_qss(this, QStringLiteral("QWidget{background:#1a1e26;color:#f2f4f8;} QPushButton{background:#2a3140;color:#f2f4f8;border:none;border-radius:8px;padding:4px 8px;} QPushButton:checked{background:#ff5a1f;} QLabel{background:#12161c;}"));
        auto* lay = new QVBoxLayout(this);
        lay->setContentsMargins(8, 8, 8, 8);
        lay->setSpacing(8);
        auto* roles = new QHBoxLayout();
        const char* role_names[] = {"albedo", "normal", "parameter"};
        const char* role_labels[] = {"Albedo", "Normal", "Parameter"};
        for (int i = 0; i < 3; ++i) {
            auto* button = new QPushButton(QString::fromLatin1(role_labels[i]), this);
            button->setCheckable(true);
            const QString role = QString::fromLatin1(role_names[i]);
            connect(button, &QPushButton::clicked, this, [this, role] { pick_role(role); });
            roles->addWidget(button);
            role_btns_[i] = button;
        }
        lay->addLayout(roles);
        preview_ = new QLabel(this);
        preview_->setAlignment(Qt::AlignCenter);
        preview_->setMinimumHeight(180);
        preview_->setText(QStringLiteral("Select a map in the table."));
        lay->addWidget(preview_, 1);
        auto* channels = new QHBoxLayout();
        const char* ch_names[] = {"R", "G", "B", "A"};
        for (int i = 0; i < 4; ++i) {
            auto* button = new QPushButton(QString::fromLatin1(ch_names[i]), this);
            button->setCheckable(true);
            button->setChecked(true);
            connect(button, &QPushButton::toggled, this, [this, i](bool on) {
                ch_[i] = on;
                show_image();
            });
            channels->addWidget(button);
        }
        lay->addLayout(channels);
        bright_ = new QSlider(Qt::Horizontal, this);
        bright_->setRange(-100, 100);
        contrast_ = new QSlider(Qt::Horizontal, this);
        contrast_->setRange(-100, 100);
        denoise_ = new QSlider(Qt::Horizontal, this);
        denoise_->setRange(0, 100);
        denoise_->setValue(40);
        lay->addWidget(bright_);
        lay->addWidget(contrast_);
        lay->addWidget(denoise_);
        auto* tools = new QHBoxLayout();
        auto add = [&](const QString& label, auto slot) {
            auto* button = new QPushButton(label, this);
            connect(button, &QPushButton::clicked, this, slot);
            tools->addWidget(button);
        };
        add(QStringLiteral("B/C"), [this] { apply_bc(); });
        add(QStringLiteral("Denoise"), [this] { apply_denoise(); });
        add(QStringLiteral("Invert"), [this] { invert_channels(); });
        add(QStringLiteral("Flip G"), [this] { flip_green(); });
        lay->addLayout(tools);
        auto* hist = new QHBoxLayout();
        add_row(hist, QStringLiteral("Undo"), [this] { undo(); });
        add_row(hist, QStringLiteral("Redo"), [this] { redo(); });
        add_row(hist, QStringLiteral("Save map"), [this] { save(); });
        lay->addLayout(hist);
    }

    void clear() {
        image_ = QImage();
        path_.clear();
        undo_.clear();
        redo_.clear();
        preview_->setPixmap(QPixmap());
        preview_->setText(QStringLiteral("Select a map in the table."));
    }

    void open_path(const QString& path) {
        const QImage image = load_image(path);
        if (image.isNull()) return;
        path_ = path;
        const auto fam = material_family(QFileInfo(path).fileName().toStdString());
        family_ = QString::fromStdString(fam.first);
        role_ = QString::fromStdString(fam.second.empty() ? "albedo" : fam.second);
        image_ = image.convertToFormat(QImage::Format_RGBA8888);
        undo_.clear();
        redo_.clear();
        for (int i = 0; i < 3; ++i) {
            const char* roles[] = {"albedo", "normal", "parameter"};
            const bool has = !owner_->path_for_role(family_, QString::fromLatin1(roles[i])).isEmpty();
            role_btns_[i]->setEnabled(has || role_ == QLatin1String(roles[i]));
            role_btns_[i]->setChecked(role_ == QLatin1String(roles[i]));
        }
        show_image();
    }

private:
    template <typename Fn>
    void add_row(QHBoxLayout* row, const QString& label, Fn slot) {
        auto* button = new QPushButton(label, this);
        connect(button, &QPushButton::clicked, this, slot);
        row->addWidget(button);
    }
    void pick_role(const QString& role) {
        const QString path = owner_->path_for_role(family_, role);
        if (!path.isEmpty()) open_path(path);
    }
    void show_image() {
        if (image_.isNull()) return;
        QImage view = image_;
        for (int y = 0; y < view.height(); ++y) {
            uchar* row = view.scanLine(y);
            for (int x = 0; x < view.width(); ++x) {
                for (int c = 0; c < 4; ++c)
                    if (!ch_[c]) row[c] = 0;
                if (!ch_[3]) row[3] = 255;
                row += 4;
            }
        }
        preview_->setPixmap(QPixmap::fromImage(view).scaled(preview_->size().expandedTo(QSize(280, 180)), Qt::KeepAspectRatio, Qt::SmoothTransformation));
    }
    void push() {
        undo_.push_back(image_);
        if (undo_.size() > 16) undo_.erase(undo_.begin());
        redo_.clear();
    }
    void apply_bc() {
        if (image_.isNull() || (bright_->value() == 0 && contrast_->value() == 0)) return;
        push();
        const double c = contrast_->value();
        const double factor = c == 0 ? 1.0 : (259.0 * (c + 255.0)) / (255.0 * (259.0 - c));
        const double bright = bright_->value() * 255.0 / 100.0;
        mutate_channels(image_, ch_[0], ch_[1], ch_[2], ch_[3] && !(ch_[0] || ch_[1] || ch_[2]), [&](int v) {
            double n = factor * (v - 128.0) + 128.0 + bright;
            return int(std::lround(n));
        });
        bright_->setValue(0);
        contrast_->setValue(0);
        show_image();
    }
    void apply_denoise() {
        if (image_.isNull() || denoise_->value() < 1) return;
        push();
        const int radius = denoise_->value() < 55 ? 1 : 2;
        QImage filtered = box_blur(image_, radius);
        image_ = image_.convertToFormat(QImage::Format_RGBA8888);
        filtered = filtered.convertToFormat(QImage::Format_RGBA8888);
        for (int y = 0; y < image_.height(); ++y) {
            uchar* dst = image_.scanLine(y);
            const uchar* src = filtered.constScanLine(y);
            for (int x = 0; x < image_.width(); ++x) {
                for (int c = 0; c < 4; ++c)
                    if (ch_[c]) dst[c] = src[c];
                dst += 4;
                src += 4;
            }
        }
        if (role_ == QLatin1String("normal")) {
            for (int y = 0; y < image_.height(); ++y) {
                uchar* row = image_.scanLine(y);
                for (int x = 0; x < image_.width(); ++x) {
                    float r = row[0] / 255.f * 2.f - 1.f;
                    float g = row[1] / 255.f * 2.f - 1.f;
                    float b = row[2] / 255.f * 2.f - 1.f;
                    const float len = std::max(1e-5f, std::sqrt(r * r + g * g + b * b));
                    row[0] = static_cast<uchar>(std::clamp((r / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    row[1] = static_cast<uchar>(std::clamp((g / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    row[2] = static_cast<uchar>(std::clamp((b / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    row += 4;
                }
            }
        }
        show_image();
    }
    void invert_channels() {
        if (image_.isNull()) return;
        push();
        mutate_channels(image_, ch_[0], ch_[1], ch_[2], ch_[3], [](int v) { return 255 - v; });
        show_image();
    }
    void flip_green() {
        if (image_.isNull()) return;
        push();
        mutate_channels(image_, false, true, false, false, [](int v) { return 255 - v; });
        show_image();
    }
    void undo() {
        if (undo_.empty()) return;
        redo_.push_back(image_);
        image_ = undo_.back();
        undo_.pop_back();
        show_image();
    }
    void redo() {
        if (redo_.empty()) return;
        undo_.push_back(image_);
        image_ = redo_.back();
        redo_.pop_back();
        show_image();
    }
    void save() {
        if (path_.isEmpty() || image_.isNull()) return;
        const QString bak = path_ + QStringLiteral(".bak");
        if (!QFileInfo::exists(bak)) QFile::copy(path_, bak);
        image_.save(path_);
    }
    Texmesh* owner_ = nullptr;
    QImage image_;
    QString path_;
    QString family_;
    QString role_;
    bool ch_[4] = {true, true, true, true};
    std::vector<QImage> undo_;
    std::vector<QImage> redo_;
    QPushButton* role_btns_[3] = {};
    QLabel* preview_ = nullptr;
    QSlider* bright_ = nullptr;
    QSlider* contrast_ = nullptr;
    QSlider* denoise_ = nullptr;
};

// Denoise preview: wheel zoom at the cursor, drag to pan, double-click to fit. Falls back to QLabel text when empty.
class ZoomLabel : public QLabel {
public:
    using QLabel::QLabel;
    void set_image(const QImage& image) {
        const bool fresh = image_.size() != image.size();
        image_ = image;
        if (fresh) reset();
        update();
    }

protected:
    QRectF target() const {
        const double fit = std::min(double(width()) / image_.width(), double(height()) / image_.height());
        const QSizeF s = image_.size() * fit * zoom_;
        return QRectF(QPointF((width() - s.width()) / 2 + pan_.x(), (height() - s.height()) / 2 + pan_.y()), s);
    }
    void reset() { zoom_ = 1; pan_ = {}; }
    void paintEvent(QPaintEvent* event) override {
        if (image_.isNull()) return QLabel::paintEvent(event);
        QPainter painter(this);
        painter.setRenderHint(QPainter::SmoothPixmapTransform, zoom_ <= 1.01);
        painter.drawImage(target(), image_);
    }
    void wheelEvent(QWheelEvent* event) override {
        if (image_.isNull()) return;
        const QRectF before = target();
        const QPointF at = event->position();
        const double factor = event->angleDelta().y() > 0 ? 1.25 : 0.8;
        const double next = std::clamp(zoom_ * factor, 1.0, 32.0);
        const double k = next / zoom_;
        zoom_ = next;
        // keep the point under the cursor fixed
        const QPointF centre = before.center();
        const QPointF moved = at + (centre - at) * k;
        pan_ += moved - centre;
        if (zoom_ <= 1.0) pan_ = {};
        update();
    }
    void mousePressEvent(QMouseEvent* event) override { from_ = event->position(); }
    void mouseMoveEvent(QMouseEvent* event) override {
        if (!(event->buttons() & Qt::LeftButton) || zoom_ <= 1.0) return;
        pan_ += event->position() - from_;
        from_ = event->position();
        update();
    }
    void mouseDoubleClickEvent(QMouseEvent*) override { reset(); update(); }

private:
    QImage image_;
    double zoom_ = 1;
    QPointF pan_, from_;
};

class ParamCanvas : public QWidget {
public:
    explicit ParamCanvas(Texmesh* owner) : QWidget(nullptr), owner_(owner) {
        setAcceptDrops(true);
        setMouseTracking(true);
    }

protected:
    void paintEvent(QPaintEvent*) override {
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.fillRect(rect(), QColor(ui_dark() ? QStringLiteral("#12161c") : QStringLiteral("#e9edf2")));
        const bool dark = ui_dark();
        // Orange-pill segmented bar, same look as the right dock tabs.
        auto strip = [&](const QRect& r, const QStringList& labels, int sel, int slot) {
            const double pos = glide(slot, sel);
            painter.setPen(QColor(255, 255, 255, dark ? 20 : 100));
            painter.setBrush(QColor(0, 0, 0, dark ? 82 : 15));
            painter.drawRoundedRect(r, r.height() / 3.0, r.height() / 3.0);
            const int sw = (r.width() - 6) / labels.size();
            const QRect pill(r.left() + 3 + int(std::lround(pos * sw)), r.top() + 3, sw, r.height() - 6);
            QLinearGradient grad(pill.topLeft(), pill.bottomLeft());
            grad.setColorAt(0, QColor("#ff7a45"));
            grad.setColorAt(0.42, QColor("#ff5a1f"));
            grad.setColorAt(1, QColor("#c43a10"));
            painter.setPen(Qt::NoPen);
            painter.setBrush(grad);
            painter.drawRoundedRect(pill, pill.height() / 3.0, pill.height() / 3.0);
            for (int i = 0; i < labels.size(); ++i) {
                painter.setPen(i == sel ? QColor(Qt::white) : QColor(dark ? "#f2f4f8" : "#1d1d1f"));
                painter.drawText(QRect(r.left() + 3 + i * sw, r.top(), sw, r.height()), Qt::AlignCenter, labels[i]);
            }
        };
        strip(tab_rect(), {QStringLiteral("Color"), QStringLiteral("Grey")}, param_gray_cached() ? 1 : 0, 4);
        const QRect top = top_rect();
        if (!owner_->param_image_.isNull()) {
            const QImage& view = cached_view();
            const QRectF target = image_rect();
            painter.save();
            painter.setClipRect(top);
            painter.setRenderHint(QPainter::SmoothPixmapTransform, zoom_ <= 1.01 && !stroke_);
            painter.drawImage(target, view);
            painter.setClipping(false);
            painter.restore();
            if (owner_->paint_tool_ == QLatin1String("Brush") && hover_.has_value() && top.contains(*hover_) && target.contains(QPointF(*hover_))) {
                const double r = std::max(1, owner_->brush_) * target.width() / std::max(1, owner_->param_image_.width());
                painter.setClipRect(top);
                painter.setBrush(Qt::NoBrush);
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1));
                painter.drawEllipse(QPointF(*hover_), r, r);
                painter.setPen(QPen(QColor(0, 0, 0, 160), 1));
                painter.drawEllipse(QPointF(*hover_), r + 1, r + 1);
                painter.setClipping(false);
            }
        } else {
            painter.setPen(QColor(QStringLiteral("#8b93a1")));
            painter.drawText(top, Qt::AlignCenter, QStringLiteral("Open a parameter map, or drop one on the queue."));
        }
        const char* keys[] = {"R", "G", "B", "A"};
        const char* names[] = {"Emissive", "Roughness", "AO", "Metallic"};
        for (int i = 0; i < 4; ++i) {
            const QRect cell = cell_rect(i);
            // Paint-target checkbox: the brush only draws into ticked channels.
            const bool on = *channel_flag(i);
            const QRect cb = check_rect(i);
            painter.setPen(QColor(on ? QStringLiteral("#ff5a1f") : QStringLiteral("#8b93a1")));
            painter.setBrush(on ? QColor("#ff5a1f") : Qt::NoBrush);
            painter.drawRoundedRect(cb, 3, 3);
            if (on) {
                painter.setPen(QPen(Qt::white, 2));
                painter.drawLine(cb.left() + 3, cb.center().y(), cb.center().x() - 1, cb.bottom() - 3);
                painter.drawLine(cb.center().x() - 1, cb.bottom() - 3, cb.right() - 3, cb.top() + 3);
            }
            painter.setPen(QColor(QStringLiteral("#8b93a1")));
            painter.drawText(cell.adjusted(26, 0, -4, 0).intersected(QRect(cell.left(), cell.top(), cell.width() - 70, 22)), Qt::AlignLeft | Qt::AlignVCenter, QString::fromLatin1(keys[i]) + QStringLiteral(" ") + QString::fromLatin1(names[i]));
            painter.setPen(QColor(255, 255, 255, dark ? 30 : 120));
            painter.setBrush(QColor(0, 0, 0, dark ? 82 : 15));
            painter.drawRoundedRect(denoise_rect(i), 7, 7);
            painter.setPen(QColor(dark ? "#f2f4f8" : "#1d1d1f"));
            painter.drawText(denoise_rect(i), Qt::AlignCenter, QStringLiteral("Denoise"));
            strip(orig_rect(i), {QStringLiteral("Original"), QStringLiteral("Edited")}, owner_->ch_orig_[i] ? 0 : 1, i);
            if (!owner_->param_image_.isNull()) {
                const QRect box = cell.adjusted(4, 52, -4, -4);
                const bool use_orig = owner_->ch_orig_[i] && owner_->param_original_.size() == owner_->param_image_.size();
                const QImage& source = use_orig ? owner_->param_original_ : owner_->param_image_;
                const std::array<qint64, 4> key = {source.cacheKey(), qint64(owner_->param_gray_) | (qint64(box.width()) << 8) | (qint64(box.height()) << 32), qint64(i), 0};
                // While a stroke is live the small channel previews keep their last frame; they refresh on release.
                if (plane_key_[i] != key && (!stroke_ || plane_[i].isNull())) {
                    plane_key_[i] = key;
                    // Extract the channel from a cell-sized copy, not the full-resolution image.
                    // Nearest-neighbour sampling of the raw bytes: QImage::scaled() would premultiply by alpha,
                    // and a map whose alpha is 0 (common for parameter maps) would come out black.
                    const QImage full = source.format() == QImage::Format_RGBA8888 ? source : source.convertToFormat(QImage::Format_RGBA8888);
                    const double fit = std::min(double(std::max(1, box.width())) / full.width(), double(std::max(1, box.height())) / full.height());
                    const QSize target(std::max(1, int(full.width() * fit)), std::max(1, int(full.height() * fit)));
                    QImage plane(target, QImage::Format_RGBA8888);
                    plane.fill(Qt::black);
                    const int ch = channel_index(QString::fromLatin1(keys[i]));
                    for (int y = 0; y < target.height(); ++y) {
                    const uchar* in = full.constScanLine(std::min(full.height() - 1, int((y + 0.5) * full.height() / target.height())));
                    uchar* out = plane.scanLine(y);
                    for (int x = 0; x < target.width(); ++x) {
                        const int v = in[std::min(full.width() - 1, int((x + 0.5) * full.width() / target.width())) * 4 + ch];
                        const bool gray = owner_->param_gray_ || keys[i][0] == 'A';
                        out[x * 4 + 0] = gray || ch == 0 ? static_cast<uchar>(v) : 0;
                        out[x * 4 + 1] = gray || ch == 1 ? static_cast<uchar>(v) : 0;
                        out[x * 4 + 2] = gray || ch == 2 ? static_cast<uchar>(v) : 0;
                        out[x * 4 + 3] = 255;
                    }
                    }
                    plane_[i] = plane;
                }
                const QSize ps = plane_[i].size();
                painter.drawImage(QPoint(box.left() + (box.width() - ps.width()) / 2, box.top() + (box.height() - ps.height()) / 2), plane_[i]);
            }
        }
    }
    void mousePressEvent(QMouseEvent* event) override {
        const QPoint pos = event->position().toPoint();
        const QRect tabs = tab_rect();
        if (tabs.contains(pos)) {
            owner_->param_gray_ = pos.x() > tabs.center().x();
            owner_->show_parameter();
            update();
            return;
        }
        for (int i = 0; i < 4; ++i) {
            if (check_rect(i).adjusted(-2, -2, 60, 2).contains(pos)) {
                bool* flag = channel_flag(i);
                *flag = !*flag;
                emit owner_->changed();  // keeps the side-panel checkbox in sync
                update();
                return;
            }
            if (denoise_rect(i).contains(pos)) {
                owner_->denoise_channel(i);
                update();
                return;
            }
            const QRect bar = orig_rect(i);
            if (bar.contains(pos)) {
                owner_->ch_orig_[i] = pos.x() < bar.center().x();
                update();
                return;
            }
        }
        if (event->button() == Qt::MiddleButton || event->button() == Qt::RightButton) {
            pan_from_ = event->position();
            return;
        }
        paint_at(pos, true);
    }
    void mouseMoveEvent(QMouseEvent* event) override {
        hover_ = event->position().toPoint();
        if (event->buttons() & (Qt::MiddleButton | Qt::RightButton)) {
            pan_ += event->position() - pan_from_;
            pan_from_ = event->position();
            update();
            return;
        }
        if (event->buttons() & Qt::LeftButton) paint_at(event->position().toPoint(), false);
        else if (owner_->paint_tool_ == QLatin1String("Brush")) update();
    }
    void mouseReleaseEvent(QMouseEvent*) override {
        stroke_ = false;
        update();  // full repaint once: smooth scaling and the channel previews catch up
    }
    void leaveEvent(QEvent*) override {
        hover_.reset();
        update();
    }
    // Wheel zooms around the cursor; middle/right drag pans; double-click resets.
    void wheelEvent(QWheelEvent* event) override {
        const QRect top = top_rect();
        const QPointF at = event->position();
        if (owner_->param_image_.isNull() || !top.contains(at.toPoint())) return;
        const QRectF before = image_rect();
        const double next = std::clamp(zoom_ * std::pow(1.25, event->angleDelta().y() / 120.0), 1.0, 32.0);
        const QPointF unit((at.x() - before.left()) / before.width(), (at.y() - before.top()) / before.height());
        zoom_ = next;
        pan_ = QPointF();
        const QRectF base = image_rect();
        // Keep the pixel under the cursor fixed.
        const QSizeF size = base.size();
        pan_ = (at - QPointF(size.width() * unit.x(), size.height() * unit.y())) - base.topLeft();
        if (zoom_ <= 1.0) pan_ = QPointF();
        update();
    }
    void mouseDoubleClickEvent(QMouseEvent* event) override {
        if (top_rect().contains(event->position().toPoint())) {
            zoom_ = 1;
            pan_ = QPointF();
            update();
        }
    }
    void dragEnterEvent(QDragEnterEvent* event) override {
        if (event->mimeData()->hasUrls()) event->acceptProposedAction();
    }
    void dropEvent(QDropEvent* event) override {
        const QStringList paths = dropped_paths(event->mimeData());
        if (paths.isEmpty()) return;
        const QRect top = top_rect();
        if (owner_->param_image_.isNull() || event->position().toPoint().y() <= top.bottom()) {
            owner_->drop_paths(paths);
            return;
        }
        const QImage dropped = load_image(paths.first());
        if (dropped.isNull()) return;
        const int index = std::clamp((event->position().toPoint().x() - 12) / cell_w(), 0, 3);
        owner_->ch_orig_[index] = false;
        const char* keys[] = {"R", "G", "B", "A"};
        owner_->push_undo();
        QImage src = dropped.convertToFormat(QImage::Format_RGBA8888).scaled(owner_->param_image_.isNull() ? dropped.size() : owner_->param_image_.size(), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
        if (owner_->param_image_.isNull()) owner_->param_image_ = QImage(src.size(), QImage::Format_RGBA8888);
        owner_->param_image_ = owner_->param_image_.convertToFormat(QImage::Format_RGBA8888);
        const int ch = channel_index(QString::fromLatin1(keys[index]));
        for (int y = 0; y < owner_->param_image_.height() && y < src.height(); ++y) {
            const uchar* in = src.constScanLine(y);
            uchar* out = owner_->param_image_.scanLine(y);
            for (int x = 0; x < owner_->param_image_.width() && x < src.width(); ++x)
                out[x * 4 + ch] = static_cast<uchar>(0.299 * in[x * 4] + 0.587 * in[x * 4 + 1] + 0.114 * in[x * 4 + 2]);
        }
        owner_->stamp_ = src;
        owner_->stamp_note_ = QStringLiteral("Channel ") + QString::fromLatin1(keys[index]) + QStringLiteral(" replaced. Stamp image is stored.");
        owner_->show_parameter();
        update();
    }

private:
    bool param_gray_cached() const { return owner_->param_gray_; }
    int cell_w() const { return std::max(40, (width() - 24) / 4); }
    QRect tab_rect() const { return QRect((width() - 200) / 2, 6, 200, 30); }
    QRect top_rect() const { return QRect(12, 44, width() - 24, std::max(40, (height() - 64) / 2)); }
    QRect cell_rect(int i) const { return QRect(12 + i * cell_w(), top_rect().bottom() + 8, cell_w() - 6, height() - top_rect().bottom() - 16); }
    QRect denoise_rect(int i) const { const QRect c = cell_rect(i); return QRect(c.right() - 64, c.top(), 64, 22); }
    QRect orig_rect(int i) const { const QRect c = cell_rect(i); return QRect(c.left() + 4, c.top() + 24, c.width() - 8, 24); }
    void paint_at(const QPoint& pos, bool begin) {
        if (owner_->param_image_.isNull()) return;
        const QRect top = top_rect();
        const QRectF target = image_rect();
        if (!top.contains(pos) || !target.contains(QPointF(pos))) {
            stroke_ = false;
            return;
        }
        QImage& image = owner_->param_image_;
        if (image.format() != QImage::Format_RGBA8888) image = image.convertToFormat(QImage::Format_RGBA8888);
        const QPointF at((pos.x() - target.left()) * image.width() / target.width(), (pos.y() - target.top()) * image.height() / target.height());
        if (owner_->paint_tool_ == QLatin1String("Magic")) {
            if (!begin) return;
            owner_->pick_magic(int(at.x()), int(at.y()));
            update();
            return;
        }
        if (owner_->paint_tool_ != QLatin1String("Brush")) return;
        if (begin) owner_->push_undo();
        cached_view();  // make sure the colour view matches the pixels before we patch it
        // Stamp along the segment from the last point so fast strokes stay continuous.
        const int radius = std::max(1, owner_->brush_);
        const double step = std::max(1.0, radius / 3.0);
        QRect dirty;
        if (!begin && stroke_) {
            const QPointF delta = at - last_;
            const double len = std::hypot(delta.x(), delta.y());
            for (double d = step; d < len; d += step) dirty |= stamp(image, last_ + delta * (d / len), radius);
        }
        dirty |= stamp(image, at, radius);
        last_ = at;
        stroke_ = true;
        // Patch only the touched pixels of the cached view, then repaint just the canvas area.
        if (!view_.isNull() && view_.size() == image.size()) {
            owner_->param_view_rect(view_, dirty);
            view_key_ = view_key();
        }
        update(top_rect());
    }
    std::array<qint64, 4> view_key() const {
        return {owner_->param_image_.cacheKey(), qint64(owner_->ch_r_) | (qint64(owner_->ch_g_) << 1) | (qint64(owner_->ch_b_) << 2) | (qint64(owner_->ch_a_) << 3) | (qint64(owner_->param_gray_) << 4), qint64(owner_->view_rev_), 1};
    }
    bool* channel_flag(int i) { return i == 0 ? &owner_->ch_r_ : i == 1 ? &owner_->ch_g_ : i == 2 ? &owner_->ch_b_ : &owner_->ch_a_; }
    QRect check_rect(int i) const { const QRect c = cell_rect(i); return QRect(c.left() + 4, c.top() + 3, 16, 16); }
    QRect stamp(QImage& image, const QPointF& at, int radius) {
        const int x = int(at.x());
        const int y = int(at.y());
        const bool use[4] = {owner_->ch_r_, owner_->ch_g_, owner_->ch_b_, owner_->ch_a_};
        for (int ky = -radius; ky <= radius; ++ky) {
            const int yy = y + ky;
            if (yy < 0 || yy >= image.height()) continue;
            uchar* row = image.scanLine(yy);
            for (int kx = -radius; kx <= radius; ++kx) {
                const int xx = x + kx;
                if (xx < 0 || xx >= image.width()) continue;
                if (kx * kx + ky * ky > radius * radius) continue;
                if (!owner_->magic_allows(xx, yy)) continue;
                uchar* p = row + xx * 4;
                const double fall = 1.0 - std::sqrt(double(kx * kx + ky * ky)) / radius * (1.0 - owner_->hard_ / 100.0);
                for (int c = 0; c < 4; ++c)
                    if (use[c]) p[c] = static_cast<uchar>(std::clamp(int(p[c] * (1.0 - fall) + owner_->paint_val_ * fall), 0, 255));
            }
        }
        return QRect(x - radius, y - radius, radius * 2 + 1, radius * 2 + 1);
    }
    // Pill position (in slots) for segmented strip `slot`; slides to `sel` over 160 ms like the dock tabs.
    double glide(int slot, int sel) {
        if (!glide_init_[slot]) {
            glide_init_[slot] = true;
            glide_pos_[slot] = glide_to_[slot] = sel;
        } else if (glide_to_[slot] != sel) {
            glide_to_[slot] = sel;
            if (!glide_anim_[slot]) {
                glide_anim_[slot] = new QVariantAnimation(this);
                glide_anim_[slot]->setDuration(160);
                glide_anim_[slot]->setEasingCurve(QEasingCurve::OutCubic);
                connect(glide_anim_[slot], &QVariantAnimation::valueChanged, this, [this, slot](const QVariant& v) {
                    glide_pos_[slot] = v.toDouble();
                    update();
                });
            }
            glide_anim_[slot]->stop();
            glide_anim_[slot]->setStartValue(glide_pos_[slot]);
            glide_anim_[slot]->setEndValue(double(sel));
            glide_anim_[slot]->start();
        }
        return glide_pos_[slot];
    }
    bool glide_init_[5] = {};
    double glide_pos_[5] = {};
    int glide_to_[5] = {};
    QVariantAnimation* glide_anim_[5] = {};

    // Image rect on screen: fitted (aspect kept) inside top_rect, then zoomed/panned.
    QRectF image_rect() {
        const QImage& img = owner_->param_image_;
        const QRect top = top_rect();
        if (img.isNull()) return top;
        if (owner_->param_path_ != seen_path_ || img.size() != seen_size_) {
            seen_path_ = owner_->param_path_;
            seen_size_ = img.size();
            zoom_ = 1;
            pan_ = QPointF();
        }
        const double fit = std::min(double(top.width()) / img.width(), double(top.height()) / img.height());
        const QSizeF size(img.width() * fit * zoom_, img.height() * fit * zoom_);
        return QRectF(QPointF(top.center()) - QPointF(size.width() / 2, size.height() / 2) + pan_, size);
    }
    // Colour view of the image; rebuilt only when the pixels or channel switches change.
    const QImage& cached_view() {
        const std::array<qint64, 4> key = view_key();
        if (view_key_ != key) {
            view_key_ = key;
            view_ = owner_->param_view();
        }
        return view_;
    }
    std::array<qint64, 4> view_key_ = {-1, -1, -1, -1};
    QImage view_;
    std::array<qint64, 4> plane_key_[4] = {{-1, -1, -1, -1}, {-1, -1, -1, -1}, {-1, -1, -1, -1}, {-1, -1, -1, -1}};
    QImage plane_[4];
    double zoom_ = 1;
    QPointF pan_;
    QPointF pan_from_;
    QPointF last_;
    bool stroke_ = false;
    std::optional<QPoint> hover_;
    QString seen_path_;
    QSize seen_size_;
    Texmesh* owner_ = nullptr;
};

Texmesh::Texmesh(QWidget* host) : QObject(host), host_(host) {
    auto make_log = [&]() {
        auto* edit = new QPlainTextEdit(host_);
        edit->setReadOnly(true);
        apply_themed_qss(edit, QString::fromLatin1(k_style));
        edit->hide();
        return edit;
    };
    tex_table_ = new DropTable(host_);
    tex_table_->setColumnCount(5);
    tex_table_->setHorizontalHeaderLabels({QStringLiteral("Name"), QStringLiteral("Dims"), QStringLiteral("Ch"), QStringLiteral("Size"), QStringLiteral("Status")});
    style_table(tex_table_);
    tex_table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    tex_table_->hide();
    static_cast<DropTable*>(tex_table_)->on_drop = [this](const QStringList& paths) { add_images(paths); };
    tex_preview_ = make_log();
    tex_log_ = make_log();
    map_view_ = new MapEditor(this, host_);
    map_view_->hide();
    lm_table_ = new DropTable(host_);
    lm_table_->setColumnCount(3);
    lm_table_->setHorizontalHeaderLabels({QStringLiteral("LOD"), QStringLiteral("Width"), QStringLiteral("Mesh")});
    style_table(lm_table_);
    lm_table_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    lm_table_->hide();
    static_cast<DropTable*>(lm_table_)->on_drop = [this](const QStringList& paths) { add_meshes(paths); };
    lm_preview_ = make_log();
    lm_log_ = make_log();
    param_canvas_ = new ParamCanvas(this);
    param_canvas_->setParent(host_);
    param_canvas_->hide();
    param_queue_ = new QListWidget(host_);
    apply_themed_qss(param_queue_, QString::fromLatin1(k_style));
    param_queue_->setAcceptDrops(true);
    param_queue_->hide();
    denoise_view_ = new ZoomLabel(host_);
    denoise_view_->setAlignment(Qt::AlignCenter);
    apply_themed_qss(denoise_view_, QString::fromLatin1(k_style));
    denoise_view_->hide();
    QObject::connect(tex_table_, &QTableWidget::itemSelectionChanged, this, [this] {
        const auto rows = tex_table_->selectionModel()->selectedRows();
        if (!rows.isEmpty()) select_texture_row(rows.first().row());
    });
    QObject::connect(tex_table_, &QTableWidget::cellDoubleClicked, this, [this](int row, int) {
        const QString family = tex_table_->item(row, 0) ? tex_table_->item(row, 0)->data(Qt::UserRole + 1).toString() : QString();
        tex_table_->clearSelection();
        for (int i = 0; i < tex_table_->rowCount(); ++i) {
            auto* item = tex_table_->item(i, 0);
            if (item && item->data(Qt::UserRole + 1).toString() == family) tex_table_->selectRow(i);
        }
    });
    QObject::connect(lm_table_, &QTableWidget::itemChanged, this, [this] { refresh_mesh(); });
    QObject::connect(param_queue_, &QListWidget::currentRowChanged, this, [this](int row) {
        if (row < 0) return;
        auto* item = param_queue_->item(row);
        if (item) open_parameter_path(item->data(Qt::UserRole).toString());
    });
    refresh_mesh();
    refresh_texture();
}

QStringList Texmesh::ve_paths() const {
    QStringList out;
    for (const QTableWidget* table : {tex_table_, lm_table_})
        for (int row = 0; row < table->rowCount(); ++row)
            for (int col = 0; col < table->columnCount(); ++col)
                if (const auto* item = table->item(row, col)) {
                    const QString path = item->data(Qt::UserRole).toString();
                    if (!path.isEmpty() && !out.contains(path)) out << path;
                }
    return out;
}

void Texmesh::set_active(bool on) {
    active_ = on;
    if (!on) hide_all();
    else sync_canvas();
    emit changed();
}

void Texmesh::set_page(const QString& page) {
    page_ = page;
    form_tab_ = 0;
    if (page == QLatin1String("texture")) refresh_texture();
    if (page == QLatin1String("meshops")) refresh_mesh();
    if (page == QLatin1String("denoise") && denoise_view_) show_denoise(!show_work_);
    sync_canvas();
    emit changed();
}

bool Texmesh::form_on() const { return active_; }
QString Texmesh::form_title() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("Texture Params");
    if (page_ == QLatin1String("parameter")) return QStringLiteral("Texture Editor");
    if (page_ == QLatin1String("denoise")) return QStringLiteral("Texture Denoiser");
    return QStringLiteral("Mesh Lods");
}
QString Texmesh::form_tabs() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("[\"Params\",\"Maps\",\"Resize\"]");
    if (page_ == QLatin1String("parameter")) return QStringLiteral("[\"Adjust\",\"Overlay\",\"Paint\",\"Export\"]");
    return QStringLiteral("[]");
}
int Texmesh::form_tab() const { return form_tab_; }
bool Texmesh::form_tool() const { return active_ && page_ == QLatin1String("texture") && form_tab_ == 1; }
QString Texmesh::center_tip() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("Drop PBR maps onto the table. Dims, channels, and power-of-two rules fill the status column.");
    if (page_ == QLatin1String("parameter")) return QStringLiteral("Top: ticked channels overlaid. Bottom: drop a gray image on a channel to replace it.");
    if (page_ == QLatin1String("denoise")) return QStringLiteral("AO / lightmap grain. ") + (oidn_exe().isEmpty() ? QStringLiteral("OIDN missing, bilateral fallback") : QStringLiteral("OIDN ready")) + QStringLiteral(". Denoise previews in memory — Save overwrites.");
    return QStringLiteral("Drop meshes onto the table. Tick LOD to combine those rows into one .lm.txt.");
}
QString Texmesh::center_list() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("Images · PBR sets");
    if (page_ == QLatin1String("meshops")) return QStringLiteral("Mesh files");
    return {};
}
QString Texmesh::center_prev() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("texture.txt preview");
    if (page_ == QLatin1String("meshops")) return QStringLiteral("lm.txt preview · material check");
    return {};
}
QString Texmesh::brand() const { return QStringLiteral("Texture & Mesh Lods"); }
QString Texmesh::blurb() const {
    if (page_ == QLatin1String("texture")) return QStringLiteral("Texture Params · VE37/39 · .texture.txt · Resize → _prep/.");
    if (page_ == QLatin1String("parameter")) return QStringLiteral("Drop maps on the queue · click a row to edit.");
    if (page_ == QLatin1String("denoise")) return QStringLiteral("Texture Denoiser · preview then Save overwrite.");
    return QStringLiteral("Mesh Lods · material rules · .lm.txt · .m.pbrmetal / .m.onetex.");
}
QString Texmesh::footer_cap() const { return page_ == QLatin1String("parameter") ? QStringLiteral("Parameter maps") : QStringLiteral("Texture & Mesh"); }
QString Texmesh::foot_note() const { return status_.isEmpty() ? blurb() : status_; }
bool Texmesh::show_queue() const { return page_ == QLatin1String("parameter"); }
int Texmesh::dock_width() const {
    // Mesh Lods, Texture Params, Texture Editor, Texture Denoiser share one dock width.
    return 440;
}
QString Texmesh::status_line() const { return status_; }

QString Texmesh::actions_json() const {
    QJsonArray rows;
    auto add = [&](const QString& label, const QString& id, bool accent) {
        rows.append(QJsonObject{{QStringLiteral("id"), id}, {QStringLiteral("label"), label}, {QStringLiteral("accent"), accent}, {QStringLiteral("enabled"), true}});
    };
    if (page_ == QLatin1String("texture")) {
        add(QStringLiteral("New from image…"), QStringLiteral("tex_from_image"), false);
        add(QStringLiteral("Save .texture.txt…"), QStringLiteral("tex_save"), false);
        add(QStringLiteral("Save all…"), QStringLiteral("tex_save_all"), true);
        add(QStringLiteral("Resize → _prep…"), QStringLiteral("tex_resize"), true);
        add(QStringLiteral("Rules scan"), QStringLiteral("tex_rules_scan"), true);
        add(QStringLiteral("Rules fix…"), QStringLiteral("tex_rules_fix"), true);
        add(QStringLiteral("VE39 scan"), QStringLiteral("tex_ve39_scan"), false);
        add(QStringLiteral("VE39 fix…"), QStringLiteral("tex_ve39_fix"), false);
        add(QStringLiteral("Check file…"), QStringLiteral("open_texture"), false);
        add(QStringLiteral("Scan folder…"), QStringLiteral("scan_folder"), false);
    } else if (page_ == QLatin1String("parameter")) {
        add(QStringLiteral("Open parameter…"), QStringLiteral("param_open"), true);
        add(QStringLiteral("Save (overwrite)"), QStringLiteral("param_save"), true);
        add(QStringLiteral("Undo"), QStringLiteral("param_undo"), false);
        add(QStringLiteral("Redo"), QStringLiteral("param_redo"), false);
        add(QStringLiteral("Revert"), QStringLiteral("param_revert"), false);
    } else if (page_ == QLatin1String("denoise")) {
        add(QStringLiteral("Open bake…"), QStringLiteral("denoise_open"), true);
        add(QStringLiteral("Denoise"), QStringLiteral("denoise_run"), true);
        add(QStringLiteral("Save (overwrite)"), QStringLiteral("denoise_save"), true);
        add(QStringLiteral("Revert"), QStringLiteral("denoise_revert"), false);
    } else {
        add(QStringLiteral("Add mesh row"), QStringLiteral("lm_add"), false);
        add(QStringLiteral("Remove selected"), QStringLiteral("lm_remove"), false);
        add(QStringLiteral("Rules scan"), QStringLiteral("lm_rules_scan"), true);
        add(QStringLiteral("Scan materials"), QStringLiteral("lm_mat_scan"), false);
        add(QStringLiteral("Fix material names…"), QStringLiteral("lm_mat_fix"), true);
        add(QStringLiteral("Load .lm.txt…"), QStringLiteral("lm_load"), false);
        add(QStringLiteral("Save all…"), QStringLiteral("lm_save"), true);
    }
    return dump(rows);
}

static QString table_dump(QTableWidget* table) {
    QJsonArray rows;
    if (table == nullptr) return QStringLiteral("[]");
    for (int row = 0; row < table->rowCount(); ++row) {
        QStringList cells;
        for (int column = 0; column < table->columnCount(); ++column) {
            QTableWidgetItem* item = table->item(row, column);
            if (item != nullptr && !item->text().isEmpty()) cells << item->text();
        }
        rows.append(QJsonObject{{QStringLiteral("row"), row}, {QStringLiteral("text"), cells.join(QStringLiteral("   "))}, {QStringLiteral("on"), row == table->currentRow()}});
    }
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString Texmesh::table_json() const {
    if (page_ == QLatin1String("texture")) return table_dump(tex_table_);
    if (page_ == QLatin1String("meshops")) return table_dump(lm_table_);
    return QStringLiteral("[]");
}

QString Texmesh::queue_json() const {
    QJsonArray rows;
    if (param_queue_ == nullptr) return QStringLiteral("[]");
    for (int row = 0; row < param_queue_->count(); ++row) {
        QListWidgetItem* item = param_queue_->item(row);
        rows.append(QJsonObject{{QStringLiteral("row"), row}, {QStringLiteral("kind"), QStringLiteral("Image")}, {QStringLiteral("name"), item == nullptr ? QString() : item->text()}, {QStringLiteral("size"), QString()}, {QStringLiteral("info"), QString()}, {QStringLiteral("on"), row == param_queue_->currentRow()}});
    }
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString Texmesh::well_left() const {
    if (page_ == QLatin1String("texture") && tex_preview_ != nullptr) return tex_preview_->toPlainText();
    if (page_ == QLatin1String("meshops") && lm_preview_ != nullptr) return lm_preview_->toPlainText();
    return {};
}

QString Texmesh::well_right() const {
    if (page_ == QLatin1String("texture") && tex_log_ != nullptr) return tex_log_->toPlainText();
    if (page_ == QLatin1String("meshops") && lm_log_ != nullptr) return lm_log_->toPlainText();
    return {};
}

void Texmesh::drop_paths(const QStringList& paths) {
    const StatusWatch watch(status_);
    QStringList local;
    for (const QString& path : paths) {
        const QUrl url(path);
        local << (url.isLocalFile() ? url.toLocalFile() : path);
    }
    if (page_ == QLatin1String("meshops")) add_meshes(local);
    else if (page_ == QLatin1String("parameter")) {
        for (const QString& path : local) {
            if (!is_image(path)) continue;
            param_queue_->addItem(QFileInfo(path).fileName());
            param_queue_->item(param_queue_->count() - 1)->setData(Qt::UserRole, path);
        }
        if (param_queue_->count() > 0) param_queue_->setCurrentRow(param_queue_->count() - 1);
        emit changed();
    } else add_images(local);
}

void Texmesh::pick_row(int row) {
    QTableWidget* table = page_ == QLatin1String("meshops") ? lm_table_ : tex_table_;
    if (table == nullptr || row < 0 || row >= table->rowCount()) return;
    table->selectRow(row);
    emit changed();
}

QString Texmesh::form_blocks() const {
    QJsonArray rows;
    if (page_ == QLatin1String("meshops")) {
        rows = {jfield(QStringLiteral("lmOffset"), QStringLiteral("offset"), QString::number(lm_offset_, 'f', 3)), jpills(QStringLiteral("lmCalc"), QStringLiteral("calcPoint"), {QStringLiteral("center"), QStringLiteral("near"), QStringLiteral("far")}, lm_calc_), jfield(QStringLiteral("lmMult"), QStringLiteral("multiplier"), QString::number(lm_mult_, 'f', 3)), jfield(QStringLiteral("lmAnim"), QStringLiteral("animCutOff"), QString::number(lm_anim_, 'f', 3)), jfield(QStringLiteral("lmRender"), QStringLiteral("renderCutOff"), QString::number(lm_render_, 'f', 3)), jfield(QStringLiteral("lmAtt"), QStringLiteral("attachCutOff"), QString::number(lm_att_, 'f', 3))};
    } else if (page_ == QLatin1String("denoise")) {
        rows = {jbuttons({{QStringLiteral("denoiseOpen"), QStringLiteral("Open bake…")}}, true), jnote(denoise_path_.isEmpty() ? QStringLiteral("No bake open") : denoise_path_), jpills(QStringLiteral("strength"), QStringLiteral("Strength"), {QStringLiteral("light"), QStringLiteral("balanced"), QStringLiteral("heavy"), QStringLiteral("nuclear")}, strength_), jcheck(QStringLiteral("oidn"), QStringLiteral("Prefer Intel OIDN"), prefer_oidn_), jcheck(QStringLiteral("lockBlack"), QStringLiteral("Lock black UV padding"), lock_black_), jfield(QStringLiteral("black"), QStringLiteral("Black ≤"), QString::number(black_)), jnote(denoise_prog_), jbuttons({{QStringLiteral("denoiseRun"), QStringLiteral("Denoise")}}, true), jbuttons({{QStringLiteral("showOrig"), QStringLiteral("Show original")}, {QStringLiteral("showWork"), QStringLiteral("Show result")}}, false), jbuttons({{QStringLiteral("denoiseRevert"), QStringLiteral("Revert")}}, false), jbuttons({{QStringLiteral("denoiseSave"), QStringLiteral("Save (overwrite)")}}, true)};
    } else if (page_ == QLatin1String("parameter")) {
        QJsonArray tail{jbuttons({{QStringLiteral("paramUndo"), QStringLiteral("Undo")}, {QStringLiteral("paramRedo"), QStringLiteral("Redo")}, {QStringLiteral("paramRevert"), QStringLiteral("Revert")}}, false), jnote(param_path_.isEmpty() ? QStringLiteral("No map") : QFileInfo(param_path_).fileName() + QStringLiteral("  ") + QString::number(param_image_.width()) + QLatin1Char('x') + QString::number(param_image_.height())), jbuttons({{QStringLiteral("paramSave"), QStringLiteral("Save (overwrite)")}}, true)};
        if (form_tab_ == 1) {
            rows = {jnote(param_path_), jsection(QStringLiteral("OVERLAY")), jpills(QStringLiteral("ovMode"), QStringLiteral("Mode"), {QStringLiteral("multiply"), QStringLiteral("add"), QStringLiteral("replace")}, ov_mode_), jpills(QStringLiteral("ovSrc"), QStringLiteral("Source"), {QStringLiteral("gray"), QStringLiteral("R"), QStringLiteral("G"), QStringLiteral("B"), QStringLiteral("A")}, ov_src_), jfield(QStringLiteral("ovOpacity"), QStringLiteral("Opacity"), QString::number(ov_opacity_)), jbuttons({{QStringLiteral("paramOverlay"), QStringLiteral("Overlay image…")}}, false), jnote(QStringLiteral("Paint → Stamp uses this mode, source, and opacity."))};
        } else if (form_tab_ == 2) {
            rows = {jnote(param_path_), jpills(QStringLiteral("paintTool"), QStringLiteral("Tool"), {QStringLiteral("Brush"), QStringLiteral("Stamp"), QStringLiteral("Magic")}, paint_tool_), jsection(QStringLiteral("BRUSH")), jfield(QStringLiteral("brush"), QStringLiteral("Radius"), QString::number(brush_)), jfield(QStringLiteral("paintVal"), QStringLiteral("Value"), QString::number(paint_val_)), jfield(QStringLiteral("hard"), QStringLiteral("Hardness"), QString::number(hard_)), jsection(QStringLiteral("MAGIC")), jfield(QStringLiteral("tol"), QStringLiteral("Tolerance"), QString::number(tol_)), jcheck(QStringLiteral("contig"), QStringLiteral("Contiguous"), contig_), jsection(QStringLiteral("STAMP")), jnote(stamp_note_), jbuttons({{QStringLiteral("paramStamp"), QStringLiteral("Apply stamp")}, {QStringLiteral("paramStampCancel"), QStringLiteral("Cancel")}}, true), jbuttons({{QStringLiteral("paramClearSel"), QStringLiteral("Clear select")}}, false)};
        } else if (form_tab_ == 3) {
            rows = {jnote(param_path_), jsection(QStringLiteral("EXPORT")), jnote(QStringLiteral("Color writes the channel tint. Grey writes black and white.")), jpills(QStringLiteral("exportTone"), QStringLiteral("Look"), {QStringLiteral("Color"), QStringLiteral("Grey")}, export_tone_), jbuttons({{QStringLiteral("exportR"), QStringLiteral("R Emissive")}, {QStringLiteral("exportG"), QStringLiteral("G Roughness")}}, false), jbuttons({{QStringLiteral("exportB"), QStringLiteral("B AO")}, {QStringLiteral("exportA"), QStringLiteral("A Metallic")}}, false)};
        } else {
            rows = {jnote(param_path_), jbuttons({{QStringLiteral("paramOpen"), QStringLiteral("Open…")}}, true), jsection(QStringLiteral("CHANNELS")), jcheck(QStringLiteral("chR"), QStringLiteral("R — Emissive"), ch_r_), jcheck(QStringLiteral("chG"), QStringLiteral("G — Roughness"), ch_g_), jcheck(QStringLiteral("chB"), QStringLiteral("B — AO"), ch_b_), jcheck(QStringLiteral("chA"), QStringLiteral("A — Metallic"), ch_a_), jsection(QStringLiteral("ADJUST")), jfield(QStringLiteral("pOffset"), QStringLiteral("Offset"), QString::number(p_offset_)), jfield(QStringLiteral("pScale"), QStringLiteral("Scale"), QString::number(p_scale_, 'f', 2)), jfield(QStringLiteral("pFill"), QStringLiteral("Fill"), QString::number(p_fill_)), jfield(QStringLiteral("pBright"), QStringLiteral("Bright"), QString::number(p_bright_)), jfield(QStringLiteral("pContrast"), QStringLiteral("Contrast"), QString::number(p_contrast_, 'f', 2)), jfield(QStringLiteral("pMean"), QStringLiteral("→ Mean"), QString::number(p_mean_)), jbuttons({{QStringLiteral("doOffset"), QStringLiteral("Offset")}, {QStringLiteral("doScale"), QStringLiteral("Scale")}, {QStringLiteral("doFill"), QStringLiteral("Fill")}}, false), jbuttons({{QStringLiteral("doBc"), QStringLiteral("B/C")}, {QStringLiteral("doMean"), QStringLiteral("Mean")}, {QStringLiteral("doInvert"), QStringLiteral("Invert")}}, false)};
        }
        for (const QJsonValue& item : tail) rows.append(item);
    } else if (form_tab_ == 2) {
        rows = {jnote(QStringLiteral("Scales images from the list into a sibling _prep/ folder.")), jcheck(QStringLiteral("prepOn"), QStringLiteral("Use these settings for Resize → _prep…"), prep_on_), jpills(QStringLiteral("prepMap"), QStringLiteral("Map"), {QStringLiteral("auto"), QStringLiteral("albedo"), QStringLiteral("normal"), QStringLiteral("parameter")}, prep_map_), jpills(QStringLiteral("prepResize"), QStringLiteral("Resize"), {QStringLiteral("%"), QStringLiteral("exact"), QStringLiteral("max"), QStringLiteral("PoT")}, prep_resize_), jpills(QStringLiteral("prepFmt"), QStringLiteral("Format"), {QStringLiteral("SAME"), QStringLiteral("PNG"), QStringLiteral("TGA"), QStringLiteral("JPG")}, prep_fmt_)};
        if (prep_resize_ == QLatin1String("%")) rows.append(jfield(QStringLiteral("prepPct"), QStringLiteral("Percent"), QString::number(prep_pct_)));
        else if (prep_resize_ == QLatin1String("exact")) {
            rows.append(jfield(QStringLiteral("prepW"), QStringLiteral("Width"), QString::number(prep_w_)));
            rows.append(jfield(QStringLiteral("prepH"), QStringLiteral("Height"), QString::number(prep_h_)));
        } else if (prep_resize_ == QLatin1String("max")) rows.append(jfield(QStringLiteral("prepMax"), QStringLiteral("Max dim"), QString::number(prep_max_)));
        rows.append(jcheck(QStringLiteral("prepFlip"), QStringLiteral("Flip green (DX ↔ GL)"), prep_flip_));
        if (prep_resize_ == QLatin1String("PoT")) rows.append(jcheck(QStringLiteral("prepPot"), QStringLiteral("PoT round down"), prep_pot_));
    } else if (form_tab_ == 1) {
        rows = {jnote(QStringLiteral("Albedo / Normal / Parameter. Channels, brightness, denoise, invert, flip green, then Save map."))};
    } else {
        rows = {jfile(QStringLiteral("primary"), QStringLiteral("Primary"), primary_, QStringLiteral("primaryPick"), QStringLiteral("body_albedo.tga"), true, {}, false), jfile(QStringLiteral("alpha"), QStringLiteral("Alpha"), alpha_, QStringLiteral("alphaPick"), QStringLiteral("optional alpha map…"), alpha_on_, QStringLiteral("alphaOn"), alpha_on_), jpills(QStringLiteral("tile"), QStringLiteral("Tile"), {QStringLiteral("st"), QStringLiteral("s"), QStringLiteral("t"), QStringLiteral("none"), k_omit}, shown(tile_)), jpills(QStringLiteral("usage"), QStringLiteral("UsageHint"), {k_omit, QStringLiteral("albedo"), QStringLiteral("normal"), QStringLiteral("parameter")}, shown(usage_)), jpills(QStringLiteral("normal"), QStringLiteral("NormalMapHint"), {k_omit, QStringLiteral("none"), QStringLiteral("normalmap")}, shown(normal_)), jpills(QStringLiteral("compress"), QStringLiteral("Compression"), {k_omit, QStringLiteral("none"), QStringLiteral("dxt1"), QStringLiteral("dxt3"), QStringLiteral("dxt5")}, shown(compress_))};
    }
    return dump(rows);
}

void Texmesh::place_well(const QString& key, int x, int y, int w, int h) {
    if (key != QLatin1String("canvas")) return;
    canvas_rect_ = QRect(x, y, w, h);
    sync_canvas();
}

void Texmesh::sync_canvas() {
    QWidget* surface = page_ == QLatin1String("parameter") ? param_canvas_ : page_ == QLatin1String("denoise") ? static_cast<QWidget*>(denoise_view_) : nullptr;
    for (QWidget* widget : {param_canvas_, static_cast<QWidget*>(denoise_view_)})
        if (widget && widget != surface) widget->hide();
    if (surface == nullptr) return;
    if (!active_ || canvas_rect_.width() < 8 || canvas_rect_.height() < 8) {
        surface->hide();
        return;
    }
    surface->setAttribute(Qt::WA_NativeWindow, true);
    surface->setGeometry(canvas_rect_);
    surface->show();
    surface->raise();
}

void Texmesh::place_queue(int, int, int, int) {
    if (param_queue_ != nullptr) param_queue_->hide();
}

void Texmesh::place_form_tool(int, int, int, int) {
    if (map_view_ != nullptr) map_view_->hide();
}

void Texmesh::hide_all() {
    QWidget* widgets[] = {tex_table_, tex_preview_, tex_log_, map_view_, lm_table_, lm_preview_, lm_log_, param_canvas_, param_queue_, denoise_view_};
    for (QWidget* widget : widgets)
        if (widget) widget->hide();
}

void Texmesh::set_form_tab(int tab) {
    form_tab_ = std::max(0, tab);
    emit changed();
}

void Texmesh::set_field(const QString& key, const QString& raw) {
    auto num = [&](double fallback) {
        bool ok = false;
        const double v = raw.toDouble(&ok);
        return ok ? v : fallback;
    };
    if (key == QLatin1String("primary")) primary_ = raw;
    else if (key == QLatin1String("alpha")) {
        alpha_ = raw;
        if (!raw.trimmed().isEmpty()) alpha_on_ = true;
    } else if (key == QLatin1String("alphaOn")) {
        alpha_on_ = raw == QLatin1String("1");
        if (!alpha_on_) alpha_.clear();
    } else if (key == QLatin1String("tile")) tile_ = omit(raw);
    else if (key == QLatin1String("usage")) {
        usage_ = omit(raw);
        if (usage_ == QLatin1String("normal")) normal_ = QStringLiteral("normalmap");
        else if ((usage_ == QLatin1String("albedo") || usage_ == QLatin1String("parameter")) && normal_ == QLatin1String("normalmap")) normal_.clear();
    } else if (key == QLatin1String("normal")) normal_ = omit(raw);
    else if (key == QLatin1String("compress")) compress_ = omit(raw);
    else if (key == QLatin1String("prepOn")) prep_on_ = raw == QLatin1String("1");
    else if (key == QLatin1String("prepMap")) prep_map_ = raw;
    else if (key == QLatin1String("prepResize")) prep_resize_ = raw;
    else if (key == QLatin1String("prepFmt")) prep_fmt_ = raw;
    else if (key == QLatin1String("prepPct")) prep_pct_ = int(num(prep_pct_));
    else if (key == QLatin1String("prepW")) prep_w_ = int(num(prep_w_));
    else if (key == QLatin1String("prepH")) prep_h_ = int(num(prep_h_));
    else if (key == QLatin1String("prepMax")) prep_max_ = int(num(prep_max_));
    else if (key == QLatin1String("prepFlip")) prep_flip_ = raw == QLatin1String("1");
    else if (key == QLatin1String("prepPot")) prep_pot_ = raw == QLatin1String("1");
    else if (key == QLatin1String("lmOffset")) lm_offset_ = num(lm_offset_);
    else if (key == QLatin1String("lmCalc")) lm_calc_ = raw;
    else if (key == QLatin1String("lmMult")) lm_mult_ = num(lm_mult_);
    else if (key == QLatin1String("lmAnim")) lm_anim_ = num(lm_anim_);
    else if (key == QLatin1String("lmRender")) lm_render_ = num(lm_render_);
    else if (key == QLatin1String("lmAtt")) lm_att_ = num(lm_att_);
    else if (key == QLatin1String("chR")) ch_r_ = raw == QLatin1String("1");
    else if (key == QLatin1String("chG")) ch_g_ = raw == QLatin1String("1");
    else if (key == QLatin1String("chB")) ch_b_ = raw == QLatin1String("1");
    else if (key == QLatin1String("chA")) ch_a_ = raw == QLatin1String("1");
    else if (key == QLatin1String("pOffset")) p_offset_ = int(num(p_offset_));
    else if (key == QLatin1String("pScale")) p_scale_ = num(p_scale_);
    else if (key == QLatin1String("pFill")) p_fill_ = int(num(p_fill_));
    else if (key == QLatin1String("pBright")) p_bright_ = int(num(p_bright_));
    else if (key == QLatin1String("pContrast")) p_contrast_ = num(p_contrast_);
    else if (key == QLatin1String("pMean")) p_mean_ = int(num(p_mean_));
    else if (key == QLatin1String("paintTool")) paint_tool_ = raw;
    else if (key == QLatin1String("brush")) brush_ = int(num(brush_));
    else if (key == QLatin1String("paintVal")) paint_val_ = int(num(paint_val_));
    else if (key == QLatin1String("hard")) hard_ = int(num(hard_));
    else if (key == QLatin1String("tol")) tol_ = int(num(tol_));
    else if (key == QLatin1String("contig")) contig_ = raw == QLatin1String("1");
    else if (key == QLatin1String("ovMode")) ov_mode_ = raw;
    else if (key == QLatin1String("ovSrc")) ov_src_ = raw;
    else if (key == QLatin1String("ovOpacity")) ov_opacity_ = int(num(ov_opacity_));
    else if (key == QLatin1String("exportTone")) export_tone_ = raw;
    else if (key == QLatin1String("strength")) strength_ = raw;
    else if (key == QLatin1String("oidn")) prefer_oidn_ = raw == QLatin1String("1");
    else if (key == QLatin1String("lockBlack")) lock_black_ = raw == QLatin1String("1");
    else if (key == QLatin1String("black")) black_ = int(num(black_));
    if (page_ == QLatin1String("denoise") && !denoise_orig_.isNull() && (key == QLatin1String("strength") || key == QLatin1String("oidn") || key == QLatin1String("lockBlack") || key == QLatin1String("black"))) {
        // Live preview: re-run with the new setting (queued once if a run is in flight).
        if (denoise_busy_) setProperty("dn_again", true);
        else start_denoise(-1);
    }
    refresh_texture();
    refresh_mesh();
    if (param_canvas_) param_canvas_->update();
    emit changed();
}

void Texmesh::run_dock(const QString& action) { run_action(action); }

void Texmesh::run_action(const QString& action) {
    const StatusWatch watch(status_);
    if (action == QLatin1String("tex_from_image") || action == QLatin1String("primaryPick")) {
        const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("Image"), {}, QStringLiteral("Images (*.png *.tga *.jpg *.jpeg *.bmp)"));
        if (!path.isEmpty()) add_images({path});
    } else if (action == QLatin1String("alphaPick")) {
        const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("Alpha"), {}, QStringLiteral("Images (*.png *.tga *.jpg *.jpeg *.bmp)"));
        if (!path.isEmpty()) {
            alpha_ = QFileInfo(path).fileName();
            alpha_on_ = true;
            refresh_texture();
        }
    } else if (action == QLatin1String("tex_save")) save_texture_one();
    else if (action == QLatin1String("tex_save_all")) save_texture_all();
    else if (action == QLatin1String("tex_resize")) resize_prep();
    else if (action == QLatin1String("tex_rules_scan")) scan_texture_rules(false);
    else if (action == QLatin1String("tex_rules_fix")) scan_texture_rules(true);
    else if (action == QLatin1String("tex_ve39_scan")) scan_ve39(false);
    else if (action == QLatin1String("tex_ve39_fix")) scan_ve39(true);
    else if (action == QLatin1String("open_texture")) check_texture_file();
    else if (action == QLatin1String("scan_folder")) scan_texture_folder();
    else if (action == QLatin1String("lm_add")) add_meshes({});
    else if (action == QLatin1String("lm_remove")) {
        const auto rows = lm_table_->selectionModel()->selectedRows();
        for (int i = rows.size() - 1; i >= 0; --i) lm_table_->removeRow(rows[i].row());
        refresh_mesh();
    } else if (action == QLatin1String("lm_rules_scan") || action == QLatin1String("lm_rules_fix")) scan_mesh_rules();
    else if (action == QLatin1String("lm_mat_scan")) scan_materials(false);
    else if (action == QLatin1String("lm_mat_fix")) scan_materials(true);
    else if (action == QLatin1String("lm_load")) load_lm();
    else if (action == QLatin1String("lm_save")) save_meshes();
    else if (action == QLatin1String("param_open") || action == QLatin1String("paramOpen")) {
        const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("Parameter"), {}, QStringLiteral("Images (*.png *.tga *.jpg *.jpeg *.bmp)"));
        if (!path.isEmpty()) {
            param_queue_->addItem(QFileInfo(path).fileName());
            param_queue_->item(param_queue_->count() - 1)->setData(Qt::UserRole, path);
            open_parameter_path(path);
        }
    } else if (action == QLatin1String("param_save") || action == QLatin1String("paramSave")) save_parameter();
    else if (action == QLatin1String("param_undo") || action == QLatin1String("paramUndo")) {
        if (!undo_.empty()) {
            redo_.push_back(param_image_);
            param_image_ = undo_.back();
            undo_.pop_back();
            show_parameter();
        }
    } else if (action == QLatin1String("param_redo") || action == QLatin1String("paramRedo")) {
        if (!redo_.empty()) {
            undo_.push_back(param_image_);
            param_image_ = redo_.back();
            redo_.pop_back();
            show_parameter();
        }
    } else if (action == QLatin1String("param_revert") || action == QLatin1String("paramRevert")) {
        if (!param_original_.isNull()) {
            push_undo();
            param_image_ = param_original_;
            std::fill(std::begin(ch_orig_), std::end(ch_orig_), true);
            show_parameter();
        }
    } else if (action == QLatin1String("doOffset") || action == QLatin1String("doScale") || action == QLatin1String("doFill") || action == QLatin1String("doBc") || action == QLatin1String("doMean") || action == QLatin1String("doInvert")) param_op(action);
    else if (action == QLatin1String("paramOverlay") || action == QLatin1String("paramStamp")) {
        QString path;
        if (action == QLatin1String("paramOverlay") || stamp_.isNull()) path = QFileDialog::getOpenFileName(host_, QStringLiteral("Overlay"), {}, QStringLiteral("Images (*.png *.tga *.jpg *.jpeg *.bmp)"));
        if (!path.isEmpty()) stamp_ = load_image(path);
        if (!stamp_.isNull() && !param_image_.isNull()) {
            push_undo();
            QImage src = stamp_.convertToFormat(QImage::Format_RGBA8888).scaled(param_image_.size(), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
            const int src_ch = channel_index(ov_src_);
            const bool use[4] = {ch_r_, ch_g_, ch_b_, ch_a_};
            param_image_ = param_image_.convertToFormat(QImage::Format_RGBA8888);
            for (int y = 0; y < param_image_.height(); ++y) {
                const uchar* in = src.constScanLine(y);
                uchar* out = param_image_.scanLine(y);
                for (int x = 0; x < param_image_.width(); ++x) {
                    const int sample = ov_src_ == QLatin1String("gray") ? int(0.299 * in[x * 4] + 0.587 * in[x * 4 + 1] + 0.114 * in[x * 4 + 2]) : in[x * 4 + src_ch];
                    const double t = ov_opacity_ / 100.0;
                    for (int c = 0; c < 4; ++c) {
                        if (!use[c] || !magic_allows(x, y)) continue;
                        int next = sample;
                        if (ov_mode_ == QLatin1String("multiply")) next = out[x * 4 + c] * sample / 255;
                        else if (ov_mode_ == QLatin1String("add")) next = std::min(255, out[x * 4 + c] + sample);
                        out[x * 4 + c] = static_cast<uchar>(out[x * 4 + c] * (1.0 - t) + next * t);
                    }
                }
            }
            show_parameter();
        }
    } else if (action == QLatin1String("paramStampCancel")) {
        stamp_ = {};
        stamp_note_ = QStringLiteral("Stamp cleared.");
    } else if (action == QLatin1String("paramClearSel")) {
        clear_magic();
        stamp_note_ = QStringLiteral("Selection cleared.");
        if (param_canvas_) param_canvas_->update();
    } else if (action.startsWith(QLatin1String("export"))) export_channel(action.mid(6));
    else if (action == QLatin1String("denoise_open") || action == QLatin1String("denoiseOpen")) {
        const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("Bake"), {}, QStringLiteral("Images (*.png *.tga *.jpg *.jpeg *.bmp *.tif *.tiff)"));
        if (!path.isEmpty()) open_denoise_path(path);
    } else if (action == QLatin1String("denoise_run") || action == QLatin1String("denoiseRun")) start_denoise(-1);
    else if (action == QLatin1String("showOrig")) show_denoise(true);
    else if (action == QLatin1String("showWork")) show_denoise(false);
    else if (action == QLatin1String("denoise_revert") || action == QLatin1String("denoiseRevert")) show_denoise(true);
    else if (action == QLatin1String("denoise_save") || action == QLatin1String("denoiseSave")) save_denoise();
    emit changed();
}

void Texmesh::queue_remove() {
    const int row = param_queue_->currentRow();
    if (row >= 0) delete param_queue_->takeItem(row);
}
void Texmesh::queue_clear() {
    // Clear the table of the active page too, not just the parameter list.
    param_queue_->clear();
    if (page_ == QLatin1String("texture")) {
        tex_table_->setRowCount(0);
        static_cast<MapEditor*>(map_view_)->clear();
        primary_.clear();
        refresh_texture();
    } else if (page_ == QLatin1String("meshops")) {
        lm_table_->setRowCount(0);
    } else if (page_ == QLatin1String("parameter")) {
        param_image_ = QImage();
        param_original_ = QImage();
        param_path_.clear();
        undo_.clear();
        redo_.clear();
        magic_.clear();
        show_parameter();
    }
    emit changed();
}

QString Texmesh::texture_text() const {
    std::vector<std::pair<std::string, std::string>> keys{{"Primary", primary_.toStdString()}};
    if (alpha_on_ && !alpha_.isEmpty()) keys.emplace_back("Alpha", alpha_.toStdString());
    if (!compress_.isEmpty()) keys.emplace_back("Compression", compress_.toStdString());
    if (!normal_.isEmpty()) keys.emplace_back("NormalMapHint", normal_.toStdString());
    if (!tile_.isEmpty()) keys.emplace_back("Tile", tile_.toStdString());
    if (!usage_.isEmpty()) keys.emplace_back("UsageHint", usage_.toStdString());
    return QString::fromStdString(format_texture_txt(keys));
}

void Texmesh::refresh_texture() {
    tex_preview_->setPlainText(primary_.isEmpty() ? QStringLiteral("Primary=…") : texture_text());
}

void Texmesh::apply_role_hints(const QString& file_name) {
    const auto fam = material_family(file_name.toStdString());
    if (fam.second == "normal") {
        usage_ = QStringLiteral("normal");
        normal_ = QStringLiteral("normalmap");
    } else if (fam.second == "albedo" || fam.second == "parameter") {
        usage_ = QString::fromStdString(fam.second);
        if (normal_ == QLatin1String("normalmap")) normal_.clear();
    }
}

void Texmesh::add_images(const QStringList& paths) {
    QStringList images;
    for (const QString& path : paths)
        if (is_image(path)) images << path;
    if (images.isEmpty() && paths.isEmpty()) return;
    BusyToast busy(images, QStringLiteral("Loading textures…"));
    int done = 0;
    for (const QString& path : images) {
        busy.step(QStringLiteral("Loading ") + QFileInfo(path).fileName() + QStringLiteral("…"), done++);
        bool known = false;
        for (int row = 0; row < tex_table_->rowCount(); ++row) {
            auto* item = tex_table_->item(row, 0);
            if (item && item->data(Qt::UserRole).toString().compare(path, Qt::CaseInsensitive) == 0) known = true;
        }
        if (known) continue;
        const QFileInfo info(path);
        const auto fam = material_family(info.fileName().toStdString());
        QImageReader reader(path);
        const QSize size = reader.size();
        const QImage image = load_image(path);
        const int w = size.width() > 0 ? size.width() : image.width();
        const int h = size.height() > 0 ? size.height() : image.height();
        QString status = QStringLiteral("OK");
        if (w <= 0 || h <= 0) status = QStringLiteral("VE36");
        else if ((w & (w - 1)) || (h & (h - 1))) status = QStringLiteral("VE37");
        else if (w > 4096 || h > 4096) status = QStringLiteral("VE167");
        const int row = tex_table_->rowCount();
        tex_table_->insertRow(row);
        auto* name = new QTableWidgetItem(info.fileName());
        name->setData(Qt::UserRole, path);
        name->setData(Qt::UserRole + 1, QString::fromStdString(fam.first));
        name->setData(Qt::UserRole + 2, QString::fromStdString(fam.second));
        name->setToolTip(path + QStringLiteral("\n") + QString::fromStdString(fam.first) + QStringLiteral(" · ") + (fam.second.empty() ? QStringLiteral("plain") : QString::fromStdString(fam.second)));
        tex_table_->setItem(row, 0, name);
        tex_table_->setItem(row, 1, new QTableWidgetItem(w > 0 ? QString::number(w) + QStringLiteral("×") + QString::number(h) : QStringLiteral("—")));
        tex_table_->setItem(row, 2, new QTableWidgetItem(image.isNull() ? QStringLiteral("—") : QString::number(image.depth() / 8) + QStringLiteral("ch")));
        tex_table_->setItem(row, 3, new QTableWidgetItem(bytes_label(info.size())));
        tex_table_->setItem(row, 4, new QTableWidgetItem(status));
    }
        if (!images.isEmpty()) {
        primary_ = QFileInfo(images.first()).fileName();
        apply_role_hints(primary_);
        static_cast<MapEditor*>(map_view_)->open_path(images.first());
        rebuild_texture_table();
        status_ = QStringLiteral("Texture ← ") + QFileInfo(images.first()).fileName();
    }
    refresh_texture();
    emit changed();
}

void Texmesh::rebuild_texture_table() {
    struct Row { QString path, name, family, role, dims, ch, size, status; };
    std::vector<Row> rows;
    for (int i = 0; i < tex_table_->rowCount(); ++i) {
        auto* item = tex_table_->item(i, 0);
        if (item == nullptr) continue;
        rows.push_back({item->data(Qt::UserRole).toString(), item->text(), item->data(Qt::UserRole + 1).toString(), item->data(Qt::UserRole + 2).toString(), tex_table_->item(i, 1)->text(), tex_table_->item(i, 2)->text(), tex_table_->item(i, 3)->text(), tex_table_->item(i, 4)->text()});
    }
    std::map<QString, std::vector<std::string>> roles;
    for (const Row& row : rows) roles[row.family].push_back(row.role.toStdString());
    std::sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
        if (a.family != b.family) return a.family < b.family;
        return a.role < b.role;
    });
    tex_table_->setRowCount(0);
    for (const Row& row : rows) {
        const int i = tex_table_->rowCount();
        tex_table_->insertRow(i);
        auto* name = new QTableWidgetItem(row.name);
        name->setData(Qt::UserRole, row.path);
        name->setData(Qt::UserRole + 1, row.family);
        name->setData(Qt::UserRole + 2, row.role);
        name->setToolTip(row.path + QStringLiteral("\n") + row.family + QStringLiteral(" · ") + QString::fromStdString(pbr_set_label(roles[row.family])));
        tex_table_->setItem(i, 0, name);
        tex_table_->setItem(i, 1, new QTableWidgetItem(row.dims));
        tex_table_->setItem(i, 2, new QTableWidgetItem(row.ch));
        tex_table_->setItem(i, 3, new QTableWidgetItem(row.size));
        tex_table_->setItem(i, 4, new QTableWidgetItem(row.status));
    }
}

void Texmesh::select_texture_row(int row) {
    auto* item = tex_table_->item(row, 0);
    if (item == nullptr) return;
    primary_ = item->text();
    apply_role_hints(primary_);
    static_cast<MapEditor*>(map_view_)->open_path(item->data(Qt::UserRole).toString());
    refresh_texture();
    emit changed();
}

void Texmesh::log_texture(const QString& text) { tex_log_->setPlainText(text); }
void Texmesh::log_mesh(const QString& text) { lm_log_->setPlainText(text); }

void Texmesh::save_texture_one() {
    if (primary_.isEmpty()) return;
    QString dir;
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item && item->text() == primary_) dir = QFileInfo(item->data(Qt::UserRole).toString()).absolutePath();
    }
    QString path = QFileDialog::getSaveFileName(host_, QStringLiteral("Save texture.txt"), dir.isEmpty() ? primary_ + QStringLiteral(".texture.txt") : QDir(dir).filePath(QFileInfo(primary_).completeBaseName() + QStringLiteral(".texture.txt")), QStringLiteral("texture.txt (*.texture.txt)"));
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return;
    file.write(texture_text().toUtf8());
    status_ = QStringLiteral("Wrote ") + QFileInfo(path).fileName();
    log_texture(texture_text());
}

void Texmesh::save_texture_all() {
    int written = 0;
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item == nullptr) continue;
        const QFileInfo info(item->data(Qt::UserRole).toString());
        const auto keys = keys_for_image(info.fileName().toStdString(), "", tile_.toStdString(), compress_.toStdString());
        QFile file(info.dir().filePath(QString::fromStdString(texture_stem(info.fileName().toStdString())) + QStringLiteral(".texture.txt")));
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) continue;
        file.write(QString::fromStdString(format_texture_txt(keys)).toUtf8());
        ++written;
    }
    status_ = QStringLiteral("Wrote ") + QString::number(written) + QStringLiteral(" texture.txt");
    log_texture(status_);
}

void Texmesh::resize_prep() {
    if (!prep_on_) return;
    int written = 0;
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item == nullptr) continue;
        const QString path = item->data(Qt::UserRole).toString();
        QImage image = load_image(path);
        if (image.isNull()) continue;
        int w = image.width();
        int h = image.height();
        if (prep_resize_ == QLatin1String("%")) {
            w = std::max(1, int(std::lround(w * prep_pct_ / 100.0)));
            h = std::max(1, int(std::lround(h * prep_pct_ / 100.0)));
        } else if (prep_resize_ == QLatin1String("exact")) {
            w = std::max(1, prep_w_);
            h = std::max(1, prep_h_);
        } else if (prep_resize_ == QLatin1String("max")) {
            const int m = std::max(w, h);
            if (m > prep_max_) {
                const double s = double(prep_max_) / m;
                w = std::max(1, int(std::lround(w * s)));
                h = std::max(1, int(std::lround(h * s)));
            }
        } else {
            w = prep_pot_ ? pot_down(w) : pot_up(w);
            h = prep_pot_ ? pot_down(h) : pot_up(h);
        }
        image = image.scaled(w, h, Qt::IgnoreAspectRatio, prep_map_ == QLatin1String("parameter") ? Qt::FastTransformation : Qt::SmoothTransformation).convertToFormat(QImage::Format_RGBA8888);
        const QString role = prep_map_ == QLatin1String("auto") ? item->data(Qt::UserRole + 2).toString() : prep_map_;
        if (role == QLatin1String("normal") || prep_flip_) {
            for (int y = 0; y < image.height(); ++y) {
                uchar* rowp = image.scanLine(y);
                for (int x = 0; x < image.width(); ++x) {
                    float r = rowp[0] / 255.f * 2.f - 1.f;
                    float g = rowp[1] / 255.f * 2.f - 1.f;
                    float b = rowp[2] / 255.f * 2.f - 1.f;
                    if (prep_flip_ && role == QLatin1String("normal")) g = -g;
                    const float len = std::max(1e-5f, std::sqrt(r * r + g * g + b * b));
                    rowp[0] = static_cast<uchar>(std::clamp((r / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    rowp[1] = static_cast<uchar>(std::clamp((g / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    rowp[2] = static_cast<uchar>(std::clamp((b / len * 0.5f + 0.5f) * 255.f, 0.f, 255.f));
                    rowp += 4;
                }
            }
        }
        const QFileInfo info(path);
        QString ext = info.suffix();
        if (prep_fmt_ == QLatin1String("PNG")) ext = QStringLiteral("png");
        else if (prep_fmt_ == QLatin1String("TGA")) ext = QStringLiteral("tga");
        else if (prep_fmt_ == QLatin1String("JPG")) ext = QStringLiteral("jpg");
        const QString dest_dir = info.dir().filePath(QStringLiteral("_prep"));
        QDir().mkpath(dest_dir);
        const QString dest = QDir(dest_dir).filePath(info.completeBaseName() + QLatin1Char('.') + ext);
        if (image.save(dest)) ++written;
    }
    status_ = QStringLiteral("Prep wrote ") + QString::number(written);
    log_texture(status_);
}

void Texmesh::scan_texture_rules(bool fix) {
    QString report;
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item == nullptr) continue;
        const QString path = item->data(Qt::UserRole).toString();
        const QImage image = load_image(path);
        report += path + QLatin1Char('\n');
        if (image.isNull()) report += QStringLiteral("  VE36 could not read\n");
        else {
            const int w = image.width();
            const int h = image.height();
            if ((w & (w - 1)) || (h & (h - 1))) report += QStringLiteral("  VE37 %1x%2 not power-of-two\n").arg(w).arg(h);
            if (w > 4096 || h > 4096) report += QStringLiteral("  VE167 larger than 4096\n");
            if (fix && ((w & (w - 1)) || (h & (h - 1)))) {
                const QString bak = path + QStringLiteral(".bak");
                if (!QFileInfo::exists(bak)) QFile::copy(path, bak);
                image.scaled(pot_down(w), pot_down(h), Qt::IgnoreAspectRatio, Qt::SmoothTransformation).save(path);
                report += QStringLiteral("  fixed → %1x%2\n").arg(pot_down(w)).arg(pot_down(h));
            }
        }
    }
    if (report.isEmpty()) report = QStringLiteral("No images in the table.");
    log_texture(report);
    status_ = fix ? QStringLiteral("Rules fix done") : QStringLiteral("Rules scan done");
}

void Texmesh::scan_ve39(bool fix) {
    QString report;
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item == nullptr) continue;
        const QString path = item->data(Qt::UserRole).toString();
        QImage image = load_image(path).convertToFormat(QImage::Format_RGBA8888);
        if (image.isNull() || image.width() < 1) continue;
        const QRgb base = image.pixel(0, 0);
        bool uniform = true;
        for (int y = 0; y < image.height() && uniform; ++y)
            for (int x = 0; x < image.width(); ++x)
                if (std::abs(qRed(image.pixel(x, y)) - qRed(base)) > 2 || std::abs(qGreen(image.pixel(x, y)) - qGreen(base)) > 2 || std::abs(qBlue(image.pixel(x, y)) - qBlue(base)) > 2) uniform = false;
        report += path + (uniform ? QStringLiteral("  VE39 solid\n") : QStringLiteral("  ok\n"));
        if (uniform && fix) {
            const QString bak = path + QStringLiteral(".bak");
            if (!QFileInfo::exists(bak)) QFile::copy(path, bak);
            image.setPixelColor(0, 0, QColor(255 - qRed(base), 255 - qGreen(base), 255 - qBlue(base)));
            image.setPixelColor(std::min(2, image.width() - 1), std::min(2, image.height() - 1), QColor(255 - qRed(base), 255 - qGreen(base), 255 - qBlue(base)));
            image.save(path);
            report += QStringLiteral("  noise dots written\n");
        }
    }
    log_texture(report.isEmpty() ? QStringLiteral("No images.") : report);
    status_ = fix ? QStringLiteral("VE39 fix done") : QStringLiteral("VE39 scan done");
}

void Texmesh::check_texture_file() {
    const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("texture.txt"), {}, QStringLiteral("texture.txt (*.texture.txt *.txt)"));
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return;
    const QString text = QString::fromUtf8(file.readAll());
    const auto keys = parse_texture_txt(text.toStdString());
    QString primary;
    for (const auto& row : keys)
        if (row.first == "Primary") primary = QString::fromStdString(row.second);
    const QString image_path = QFileInfo(path).dir().filePath(primary);
    const QImage image = load_image(image_path);
    const TextureReport report = check_texture_txt(path.toStdString(), text.toStdString(), image.width(), image.height(), QFileInfo::exists(image_path));
    log_texture(QString::fromStdString(format_texture_report(report)));
    for (const auto& row : keys) {
        const QString val = QString::fromStdString(row.second);
        if (row.first == "Primary") primary_ = val;
        if (row.first == "Alpha") {
            alpha_ = val;
            alpha_on_ = !val.isEmpty();
        }
        if (row.first == "Tile") tile_ = val;
        if (row.first == "UsageHint") usage_ = val;
        if (row.first == "NormalMapHint") normal_ = val;
        if (row.first == "Compression") compress_ = val;
    }
    refresh_texture();
    status_ = QString::fromStdString(report.summary());
}

void Texmesh::scan_texture_folder() {
    const QString dir = QFileDialog::getExistingDirectory(host_, QStringLiteral("Scan folder"));
    if (dir.isEmpty()) return;
    QString report;
    const QFileInfoList files = QDir(dir).entryInfoList({QStringLiteral("*.texture.txt")}, QDir::Files);
    for (const QFileInfo& info : files) {
        QFile file(info.absoluteFilePath());
        if (!file.open(QIODevice::ReadOnly)) continue;
        const QString text = QString::fromUtf8(file.readAll());
        const TextureReport row = check_texture_txt(info.absoluteFilePath().toStdString(), text.toStdString(), 0, 0, true);
        report += QString::fromStdString(format_texture_report(row));
    }
    log_texture(report.isEmpty() ? QStringLiteral("No .texture.txt in that folder.") : report);
    status_ = QString::number(files.size()) + QStringLiteral(" texture.txt");
}

void Texmesh::add_meshes(const QStringList& paths) {
    QStringList meshes = paths;
    if (meshes.isEmpty()) meshes << QStringLiteral("mesh.im");
    for (const QString& path : meshes) {
        if (path != QLatin1String("mesh.im") && !is_mesh(path)) continue;
        if (path.toLower().endsWith(QLatin1String(".lm.txt")) || path.toLower().endsWith(QLatin1String(".lm"))) {
            QFile file(path);
            if (file.open(QIODevice::ReadOnly)) {
                const LmFile lm = parse_lm_txt(QString::fromUtf8(file.readAll()).toStdString());
                lm_offset_ = lm.offset;
                lm_calc_ = QString::fromStdString(lm.calc_point);
                lm_mult_ = lm.multiplier;
                lm_anim_ = lm.animation_cutoff;
                lm_render_ = lm.render_cutoff;
                lm_att_ = lm.attachment_cutoff;
                for (const LmMesh& mesh : lm.meshes) add_meshes({QFileInfo(path).dir().filePath(QString::fromStdString(mesh.name))});
            }
            continue;
        }
        const int row = lm_table_->rowCount();
        lm_table_->blockSignals(true);
        lm_table_->insertRow(row);
        auto* lod = new QTableWidgetItem();
        lod->setFlags(Qt::ItemIsUserCheckable | Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        lod->setCheckState(Qt::Unchecked);
        lm_table_->setItem(row, 0, lod);
        auto* width = new QTableWidgetItem(QStringLiteral("1"));
        lm_table_->setItem(row, 1, width);
        auto* name = new QTableWidgetItem(path == QLatin1String("mesh.im") ? path : QFileInfo(path).fileName());
        if (path != QLatin1String("mesh.im")) name->setData(Qt::UserRole, path);
        name->setToolTip(path);
        lm_table_->setItem(row, 2, name);
        lm_table_->blockSignals(false);
    }
    refresh_mesh();
    emit changed();
}

void Texmesh::refresh_mesh() {
    LmFile grouped;
    grouped.offset = lm_offset_;
    grouped.calc_point = lm_calc_.toStdString();
    grouped.multiplier = lm_mult_;
    grouped.animation_cutoff = lm_anim_;
    grouped.render_cutoff = lm_render_;
    grouped.attachment_cutoff = lm_att_;
    int solo = 0;
    QString sample;
    double sample_w = 1;
    for (int row = 0; row < lm_table_->rowCount(); ++row) {
        auto* width = lm_table_->item(row, 1);
        auto* name = lm_table_->item(row, 2);
        auto* lod = lm_table_->item(row, 0);
        if (width == nullptr || name == nullptr || name->text().isEmpty()) continue;
        bool ok = false;
        const double w = width->text().toDouble(&ok);
        const bool ticked = lod && lod->checkState() == Qt::Checked;
        if (ticked) grouped.meshes.push_back({ok ? w : 1, name->text().toStdString()});
        else {
            ++solo;
            if (sample.isEmpty()) {
                sample = name->text();
                sample_w = ok ? w : 1;
            }
        }
    }
    QString text;
    if (lm_table_->rowCount() == 0) text = QStringLiteral("Drop .trainzmesh / .im / .fbx — or Add mesh row.");
    else {
        if (!grouped.meshes.empty()) {
            try {
                text += QStringLiteral("# LOD group → one .lm.txt\n") + QString::fromStdString(format_lm_txt(grouped));
            } catch (const std::exception& error) {
                text += QString::fromUtf8(error.what());
            }
        }
        if (solo) {
            LmFile one = grouped;
            one.meshes = {{sample_w, sample.toStdString()}};
            text += QStringLiteral("\n# Save all → %1 individual .lm.txt\n").arg(solo);
            try {
                text += QString::fromStdString(format_lm_txt(one));
            } catch (const std::exception&) {
            }
        }
    }
    lm_preview_->setPlainText(text);
}

void Texmesh::scan_mesh_rules() {
    QString report;
    for (int row = 0; row < lm_table_->rowCount(); ++row) {
        auto* name = lm_table_->item(row, 2);
        if (name == nullptr) continue;
        const QString path = name->data(Qt::UserRole).toString();
        report += (path.isEmpty() ? name->text() : path) + QLatin1Char('\n');
        if (path.isEmpty() || !QFileInfo::exists(path)) {
            report += QStringLiteral("  file not on disk\n");
            continue;
        }
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) continue;
        const QByteArray bytes = file.readAll();
        if (path.endsWith(QLatin1String(".trainzmesh"), Qt::CaseInsensitive)) {
            try {
                const TrainzMesh mesh = parse_trainzmesh(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()));
                report += QStringLiteral("  trainzmesh parts %1\n").arg(mesh.submeshes.size());
            } catch (const std::exception& error) {
                report += QStringLiteral("  trainzmesh: %1\n").arg(QString::fromUtf8(error.what()));
            }
        }
        const auto names = list_material_names(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()));
        if (names.empty()) report += QStringLiteral("  no .m. material token\n");
        for (const std::string& mat : names) {
            const MatNameIssue issue = check_mat_name(mat);
            report += QStringLiteral("  ") + QString::fromStdString(issue.kind + " " + issue.name);
            if (!issue.suggested.empty()) report += QStringLiteral(" -> ") + QString::fromStdString(issue.suggested);
            report += QLatin1Char('\n');
        }
    }
    log_mesh(report.isEmpty() ? QStringLiteral("No mesh rows.") : report);
    status_ = QStringLiteral("Mesh rules scanned");
}

void Texmesh::scan_materials(bool fix) {
    QString report;
    int renamed = 0;
    for (int row = 0; row < lm_table_->rowCount(); ++row) {
        auto* name = lm_table_->item(row, 2);
        if (name == nullptr) continue;
        const QString path = name->data(Qt::UserRole).toString();
        if (path.isEmpty()) continue;
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) continue;
        QByteArray bytes = file.readAll();
        file.close();
        const auto names = list_material_names(reinterpret_cast<const uint8_t*>(bytes.constData()), size_t(bytes.size()));
        std::vector<MatNameIssue> issues;
        for (const std::string& mat : names) issues.push_back(check_mat_name(mat));
        report += QString::fromStdString(format_mat_report(path.toStdString(), issues));
        if (!fix) continue;
        for (const MatNameIssue& issue : issues) {
            if (!issue.needs_fix()) continue;
            const QByteArray from = QByteArray::fromStdString(issue.name);
            const QByteArray to = QByteArray::fromStdString(issue.suggested);
            if (from.size() != to.size() && bytes.contains('\0')) {
                report += QStringLiteral("  skip binary length change %1\n").arg(QString::fromStdString(issue.name));
                continue;
            }
            if (!bytes.contains(from)) continue;
            const QString bak = path + QStringLiteral(".bak");
            if (!QFileInfo::exists(bak)) QFile::copy(path, bak);
            bytes.replace(from, to);
            ++renamed;
        }
        if (renamed && file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(bytes);
    }
    if (fix) report += QStringLiteral("renamed %1\n").arg(renamed);
    log_mesh(report.isEmpty() ? QStringLiteral("No mesh files.") : report);
    status_ = fix ? QStringLiteral("Material names updated") : QStringLiteral("Materials scanned");
}

void Texmesh::load_lm() {
    const QString path = QFileDialog::getOpenFileName(host_, QStringLiteral("Load .lm.txt"), {}, QStringLiteral("LM (*.lm.txt *.lm)"));
    if (path.isEmpty()) return;
    add_meshes({path});
    status_ = QStringLiteral("Loaded ") + QFileInfo(path).fileName();
}

void Texmesh::save_meshes() {
    struct Row { bool lod; double width; QString name; QString source; };
    std::vector<Row> rows;
    for (int i = 0; i < lm_table_->rowCount(); ++i) {
        auto* name = lm_table_->item(i, 2);
        auto* width = lm_table_->item(i, 1);
        auto* lod = lm_table_->item(i, 0);
        if (name == nullptr || name->text().isEmpty()) continue;
        bool ok = false;
        rows.push_back({lod && lod->checkState() == Qt::Checked, width ? width->text().toDouble(&ok) : 1, name->text(), name->data(Qt::UserRole).toString()});
        if (!ok) rows.back().width = 1;
    }
    if (rows.empty()) return;
    QString folder;
    for (const Row& row : rows) {
        if (row.source.isEmpty()) continue;
        const QString parent = QFileInfo(row.source).absolutePath();
        if (folder.isEmpty()) folder = parent;
        else if (folder != parent) folder.clear();
    }
    if (folder.isEmpty()) folder = QFileDialog::getExistingDirectory(host_, QStringLiteral("Save .lm.txt"));
    if (folder.isEmpty()) return;
    auto write_one = [&](const std::vector<Row>& use, const QString& file_name) {
        LmFile lm;
        lm.offset = lm_offset_;
        lm.calc_point = lm_calc_.toStdString();
        lm.multiplier = lm_mult_;
        lm.animation_cutoff = lm_anim_;
        lm.render_cutoff = lm_render_;
        lm.attachment_cutoff = lm_att_;
        for (const Row& row : use) lm.meshes.push_back({row.width, row.name.toStdString()});
        QFile file(QDir(folder).filePath(file_name));
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return;
        file.write(QString::fromStdString(format_lm_txt(lm)).toUtf8());
    };
    std::vector<Row> lods;
    std::vector<Row> solos;
    for (const Row& row : rows) (row.lod ? lods : solos).push_back(row);
    int count = 0;
    if (!lods.empty()) {
        QString stem = QFileInfo(lods.front().name).completeBaseName();
        write_one(lods, stem + QStringLiteral(".lm.txt"));
        ++count;
    }
    for (const Row& row : solos) {
        write_one({row}, QFileInfo(row.name).completeBaseName() + QStringLiteral(".lm.txt"));
        ++count;
    }
    status_ = QStringLiteral("Wrote ") + QString::number(count) + QStringLiteral(" .lm.txt");
    log_mesh(status_ + QStringLiteral(" → ") + folder);
    refresh_mesh();
}

void Texmesh::open_parameter_path(const QString& path) {
    const QImage image = load_image(path);
    if (image.isNull()) return;
    param_path_ = path;
    param_original_ = image.convertToFormat(QImage::Format_RGBA8888);
    param_image_ = param_original_;
    std::fill(std::begin(ch_orig_), std::end(ch_orig_), true);
    undo_.clear();
    redo_.clear();
    magic_.clear();
    show_parameter();
    status_ = QFileInfo(path).fileName();
    emit changed();
}

void Texmesh::show_parameter() {
    if (param_canvas_) param_canvas_->update();
}

void Texmesh::push_undo() {
    if (param_image_.isNull()) return;
    // Every edit goes through here: channels it touches switch their preview to "Edited".
    const bool touched[4] = {ch_r_, ch_g_, ch_b_, ch_a_};
    for (int c = 0; c < 4; ++c)
        if (touched[c]) ch_orig_[c] = false;
    undo_.push_back(param_image_);
    if (undo_.size() > 32) undo_.erase(undo_.begin());
    redo_.clear();
}

void Texmesh::param_op(const QString& op) {
    if (param_image_.isNull()) return;
    push_undo();
    if (op == QLatin1String("doOffset")) mutate_channels(param_image_, ch_r_, ch_g_, ch_b_, ch_a_, [&](int v) { return v + p_offset_; });
    else if (op == QLatin1String("doScale")) mutate_channels(param_image_, ch_r_, ch_g_, ch_b_, ch_a_, [&](int v) { return int(std::lround(v * p_scale_)); });
    else if (op == QLatin1String("doFill")) mutate_channels(param_image_, ch_r_, ch_g_, ch_b_, ch_a_, [&](int) { return p_fill_; });
    else if (op == QLatin1String("doBc")) mutate_channels(param_image_, ch_r_, ch_g_, ch_b_, ch_a_, [&](int v) {
        return int(std::lround((v - 128) * p_contrast_ + 128 + p_bright_));
    });
    else if (op == QLatin1String("doMean")) {
        const bool use[4] = {ch_r_, ch_g_, ch_b_, ch_a_};
        for (int c = 0; c < 4; ++c) {
            if (!use[c]) continue;
            double sum = 0;
            const int n = param_image_.width() * param_image_.height();
            for (int y = 0; y < param_image_.height(); ++y) {
                const uchar* row = param_image_.constScanLine(y);
                for (int x = 0; x < param_image_.width(); ++x) sum += row[x * 4 + c];
            }
            const int delta = p_mean_ - int(std::lround(sum / std::max(1, n)));
            mutate_channels(param_image_, c == 0, c == 1, c == 2, c == 3, [&](int v) { return v + delta; });
        }
    } else if (op == QLatin1String("doInvert")) mutate_channels(param_image_, ch_r_, ch_g_, ch_b_, ch_a_, [](int v) { return 255 - v; });
    show_parameter();
}

void Texmesh::save_parameter() {
    if (param_path_.isEmpty() || param_image_.isNull()) return;
    const QString bak = param_path_ + QStringLiteral(".bak");
    if (!QFileInfo::exists(bak)) QFile::copy(param_path_, bak);
    param_image_.save(param_path_);
    status_ = QStringLiteral("Saved ") + QFileInfo(param_path_).fileName();
}

void Texmesh::export_channel(const QString& key) {
    if (param_image_.isNull() || key.isEmpty()) return;
    const QString path = QFileDialog::getSaveFileName(host_, QStringLiteral("Export ") + key, {}, QStringLiteral("PNG (*.png)"));
    if (path.isEmpty()) return;
    const int ch = channel_index(key.left(1));
    QImage out(param_image_.size(), QImage::Format_RGBA8888);
    const QImage src = param_image_.convertToFormat(QImage::Format_RGBA8888);
    const bool gray = export_tone_ != QLatin1String("Color") || key.startsWith(QLatin1Char('A'));
    for (int y = 0; y < src.height(); ++y) {
        const uchar* in = src.constScanLine(y);
        uchar* dst = out.scanLine(y);
        for (int x = 0; x < src.width(); ++x) {
            const int v = in[x * 4 + ch];
            dst[x * 4 + 0] = gray || ch == 0 ? uchar(v) : 0;
            dst[x * 4 + 1] = gray || ch == 1 ? uchar(v) : 0;
            dst[x * 4 + 2] = gray || ch == 2 ? uchar(v) : 0;
            dst[x * 4 + 3] = 255;
        }
    }
    out.save(path);
    status_ = QStringLiteral("Exported ") + key;
}

QImage Texmesh::param_view() const {
    if (param_image_.isNull()) return {};
    QImage out(param_image_.size(), QImage::Format_RGBA8888);
    param_view_rect(out, QRect(QPoint(0, 0), param_image_.size()));
    return out;
}

// Repaints only `area` of the colour view (a brush dab touches a few hundred pixels, not the whole map).
void Texmesh::param_view_rect(QImage& out, const QRect& area) const {
    const QImage src = param_image_.format() == QImage::Format_RGBA8888 ? param_image_ : param_image_.convertToFormat(QImage::Format_RGBA8888);
    const QRect box = area.intersected(QRect(QPoint(0, 0), src.size()));
    for (int y = box.top(); y <= box.bottom(); ++y) {
        const uchar* in = src.constScanLine(y);
        uchar* dst = out.scanLine(y);
        for (int x = box.left(); x <= box.right(); ++x) {
            float rgb[3] = {};
            if (ch_r_) rgb[0] = in[x * 4];
            if (ch_g_) rgb[1] = in[x * 4 + 1];
            if (ch_b_) rgb[2] = in[x * 4 + 2];
            if (ch_a_) {
                const float metal = in[x * 4 + 3] / 255.f * 0.55f;
                for (float& c : rgb) c += (255.f - c) * metal;
            }
            if (param_gray_) {
                const int yv = int(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]);
                rgb[0] = rgb[1] = rgb[2] = float(yv);
            }
            if (!magic_.empty()) {
                const size_t index = static_cast<size_t>(y * src.width() + x);
                if (index < magic_.size() && !magic_[index]) {
                    rgb[0] *= 0.35f;
                    rgb[1] *= 0.35f;
                    rgb[2] *= 0.35f;
                }
            }
            dst[x * 4] = uchar(std::clamp(rgb[0], 0.f, 255.f));
            dst[x * 4 + 1] = uchar(std::clamp(rgb[1], 0.f, 255.f));
            dst[x * 4 + 2] = uchar(std::clamp(rgb[2], 0.f, 255.f));
            dst[x * 4 + 3] = 255;
        }
    }
}

void Texmesh::open_denoise_path(const QString& path) {
    const QImage image = load_image(path);
    if (image.isNull()) return;
    denoise_path_ = path;
    denoise_orig_ = image.convertToFormat(QImage::Format_RGBA8888);
    denoise_work_ = {};
    show_work_ = false;
    denoise_prog_ = QFileInfo(path).fileName();
    show_denoise(true);
    emit changed();
}

void Texmesh::show_denoise(bool original) {
    show_work_ = !original && !denoise_work_.isNull();
    const QImage& image = show_work_ ? denoise_work_ : denoise_orig_;
    static_cast<ZoomLabel*>(denoise_view_)->set_image(image);
    denoise_view_->setText(image.isNull() ? QStringLiteral("Open a bake.") : QString());
}

// Pure compute (safe off the UI thread). Parameter names mirror the old members on purpose.
static QImage denoise_compute(const QImage& denoise_orig_, const QString& strength_, bool prefer_oidn_, bool lock_black_, int black_, QString& denoise_prog_, const std::function<void(int)>& report = {}) {
    const QString quality = strength_ == QLatin1String("light") ? QStringLiteral("balanced") : QStringLiteral("high");
    int radius = 4;
    int sigma = 60;
    double detail = 0.24;
    if (strength_ == QLatin1String("light")) {
        radius = 3;
        sigma = 40;
        detail = 0.28;
    } else if (strength_ == QLatin1String("heavy")) {
        radius = 6;
        sigma = 80;
        detail = 0.20;
    } else if (strength_ == QLatin1String("nuclear")) {
        radius = 6;
        sigma = 110;
        detail = 0;
    }
    // Several bilateral passes: one 13x13 pass barely touches real noise.
    const int passes = strength_ == QLatin1String("light") ? 1 : strength_ == QLatin1String("heavy") ? 3 : strength_ == QLatin1String("nuclear") ? 5 : 2;
    QImage work;
    const QString exe = oidn_exe();
    if (prefer_oidn_ && !exe.isEmpty()) {
        QTemporaryDir dir;
        const QString in_path = dir.filePath(QStringLiteral("in.pfm"));
        const QString out_path = dir.filePath(QStringLiteral("out.pfm"));
        denoise_prog_ = QStringLiteral("OIDN RTLightmap…");
        if (write_pfm(in_path, denoise_orig_)) {
            auto run = [&](const QString& filter) {
                QProcess proc;
                proc.setWorkingDirectory(QFileInfo(exe).absolutePath());
                QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
                env.insert(QStringLiteral("PATH"), QFileInfo(exe).absolutePath() + QLatin1Char(';') + env.value(QStringLiteral("PATH")));
                proc.setProcessEnvironment(env);
                proc.start(exe, {QStringLiteral("-f"), filter, QStringLiteral("-q"), quality, QStringLiteral("--ldr"), in_path, QStringLiteral("-o"), out_path});
                proc.waitForFinished(180000);
                return proc.exitStatus() == QProcess::NormalExit && proc.exitCode() == 0 && QFileInfo::exists(out_path);
            };
            if (!run(QStringLiteral("RTLightmap"))) run(QStringLiteral("RT"));
            work = read_pfm(out_path, denoise_orig_);
        }
        if (!work.isNull()) denoise_prog_ = QStringLiteral("OIDN ") + quality;
    }
    if (work.isNull()) {
        denoise_prog_ = exe.isEmpty() ? QStringLiteral("Bilateral fallback") : QStringLiteral("OIDN failed, bilateral fallback");
        work = denoise_orig_;
        for (int i = 0; i < passes; ++i)
            work = bilateral_rgb(work, std::min(radius, 6), sigma, [&, i](int p) { if (report) report((i * 100 + p) / passes); });
    }
    if (detail > 0) {
        const QImage blur = box_blur(work, 1);
        work = work.convertToFormat(QImage::Format_RGBA8888);
        const QImage soft = blur.convertToFormat(QImage::Format_RGBA8888);
        for (int y = 0; y < work.height(); ++y) {
            uchar* dst = work.scanLine(y);
            const uchar* src = soft.constScanLine(y);
            for (int x = 0; x < work.width(); ++x) {
                for (int c = 0; c < 3; ++c) {
                    const int sharp = int(std::lround(dst[c] * (1.0 + detail) - src[c] * detail));
                    dst[c] = static_cast<uchar>(std::clamp(sharp, 0, 255));
                }
                dst += 4;
                src += 4;
            }
        }
    }
    if (lock_black_) {
        const QImage src = denoise_orig_.convertToFormat(QImage::Format_RGBA8888);
        work = work.convertToFormat(QImage::Format_RGBA8888);
        for (int y = 0; y < work.height() && y < src.height(); ++y) {
            const uchar* in = src.constScanLine(y);
            uchar* out = work.scanLine(y);
            for (int x = 0; x < work.width() && x < src.width(); ++x)
                if (nearly_black(in + x * 4, black_)) std::memcpy(out + x * 4, in + x * 4, 4);
        }
    }
    return work;
}

void Texmesh::run_denoise() {
    if (denoise_orig_.isNull()) return;
    denoise_work_ = denoise_compute(denoise_orig_, strength_, prefer_oidn_, lock_black_, black_, denoise_prog_);
    show_denoise(false);
    status_ = denoise_prog_;
    emit changed();
}

// Send one channel to the Denoiser pipeline as a grey image, then write the result back into that channel.
void Texmesh::denoise_channel(int ch) {
    if (param_image_.isNull() || ch < 0 || ch > 3) return;
    const QImage src = param_image_.convertToFormat(QImage::Format_RGBA8888);
    QImage plane(src.size(), QImage::Format_RGBA8888);
    for (int y = 0; y < src.height(); ++y) {
        const uchar* in = src.constScanLine(y);
        uchar* out = plane.scanLine(y);
        for (int x = 0; x < src.width(); ++x) {
            out[x * 4] = out[x * 4 + 1] = out[x * 4 + 2] = in[x * 4 + ch];
            out[x * 4 + 3] = 255;
        }
    }
    if (denoise_busy_) {
        status_ = QStringLiteral("Denoise already running…");
        emit changed();
        return;
    }
    // Show the grey channel on the Denoiser page right away; the result lands there and in the channel.
    denoise_orig_ = plane;
    denoise_work_ = {};
    denoise_prog_ = QStringLiteral("Denoising channel ") + QStringLiteral("RGBA").mid(ch, 1) + QStringLiteral("…");
    show_denoise(true);
    emit pageRequested(QStringLiteral("denoise"));
    start_denoise(ch);
}

// Runs the denoiser on denoise_orig_ off the UI thread. ch >= 0 also writes the result back into that channel.
void Texmesh::start_denoise(int ch) {
    if (denoise_orig_.isNull() || denoise_busy_) return;
    // The heavy part (OIDN process / bilateral filter) runs on a worker so the window keeps responding.
    denoise_busy_ = true;
    const QString name = ch >= 0 ? QStringLiteral("RGBA").mid(ch, 1) : QStringLiteral("image");
    status_ = QStringLiteral("Denoising ") + name + QStringLiteral("…");
    StatusHub::instance()->progress(QStringLiteral("Denoise"), 0, status_);
    emit changed();
    const QImage plane = denoise_orig_;
    const QString strength = strength_;
    const bool prefer = prefer_oidn_, lock = lock_black_;
    const int black = black_;
    QPointer<Texmesh> self(this);
    QThread* thread = QThread::create([self, plane, strength, prefer, lock, black, ch, name] {
        QString prog;
        auto last = std::make_shared<std::atomic<int>>(-1);
        const QImage work = denoise_compute(plane, strength, prefer, lock, black, prog, [last, name](int pct) {
            // Called from worker threads; hop to the UI thread, and only on whole-percent changes.
            if (last->exchange(pct) == pct) return;
            QMetaObject::invokeMethod(qApp, [pct, name] { StatusHub::instance()->progress(QStringLiteral("Denoise"), pct, QStringLiteral("Denoising ") + name + QStringLiteral(" · %1%").arg(pct)); }, Qt::QueuedConnection);
        });
        if (!self) return;
        QMetaObject::invokeMethod(self.data(), [self, work, prog, ch, name] {
            if (!self) return;
            self->denoise_busy_ = false;
            self->denoise_work_ = work;
            self->denoise_prog_ = prog;
            self->show_denoise(false);
            if (self->property("dn_again").toBool()) {
                self->setProperty("dn_again", false);
                self->start_denoise(-1);
            }
            if (ch < 0 || work.isNull() || work.size() != self->param_image_.size()) {
                self->status_ = work.isNull() ? QStringLiteral("Denoise failed") : QStringLiteral("Denoised · ") + prog;
                StatusHub::instance()->finish(self->status_);
                emit self->changed();
                return;
            }
            self->push_undo();
            self->param_image_ = self->param_image_.convertToFormat(QImage::Format_RGBA8888);
            const QImage done = work.convertToFormat(QImage::Format_RGBA8888);
            for (int y = 0; y < self->param_image_.height(); ++y) {
                const uchar* in = done.constScanLine(y);
                uchar* out = self->param_image_.scanLine(y);
                for (int x = 0; x < self->param_image_.width(); ++x)
                    out[x * 4 + ch] = uchar((in[x * 4] + in[x * 4 + 1] + in[x * 4 + 2]) / 3);
            }
            self->ch_orig_[ch] = false;
            self->show_parameter();
            self->status_ = QStringLiteral("Denoised channel ") + name + QStringLiteral(" · ") + prog;
            StatusHub::instance()->finish(self->status_);
            emit self->changed();
        }, Qt::QueuedConnection);
    });
    connect(thread, &QThread::finished, thread, &QObject::deleteLater);
    thread->start();
}

void Texmesh::pick_magic(int x, int y) {
    if (param_image_.isNull()) return;
    const QImage src = param_image_.convertToFormat(QImage::Format_RGBA8888);
    std::vector<unsigned char> packed(static_cast<size_t>(src.width() * src.height() * 4));
    for (int row = 0; row < src.height(); ++row)
        std::memcpy(packed.data() + static_cast<size_t>(row * src.width() * 4), src.constScanLine(row), static_cast<size_t>(src.width() * 4));
    magic_ = magic_mask_of(packed.data(), src.width(), src.height(), x, y, tol_, contig_);
    ++view_rev_;
    const int count = int(std::count(magic_.begin(), magic_.end(), 1));
    stamp_note_ = QStringLiteral("Magic select %1 px").arg(count);
    status_ = stamp_note_;
    emit changed();
}

void Texmesh::clear_magic() {
    magic_.clear();
    ++view_rev_;
}

bool Texmesh::magic_allows(int x, int y) const {
    if (magic_.empty() || param_image_.isNull()) return true;
    if (x < 0 || y < 0 || x >= param_image_.width() || y >= param_image_.height()) return false;
    const size_t index = static_cast<size_t>(y * param_image_.width() + x);
    return index < magic_.size() && magic_[index];
}

QString Texmesh::path_for_role(const QString& family, const QString& role) const {
    for (int row = 0; row < tex_table_->rowCount(); ++row) {
        auto* item = tex_table_->item(row, 0);
        if (item == nullptr) continue;
        if (item->data(Qt::UserRole + 1).toString() == family && item->data(Qt::UserRole + 2).toString() == role)
            return item->data(Qt::UserRole).toString();
    }
    return {};
}

void Texmesh::save_denoise() {
    if (denoise_path_.isEmpty()) return;
    const QImage& image = denoise_work_.isNull() ? denoise_orig_ : denoise_work_;
    if (image.isNull()) return;
    const QString bak = denoise_path_ + QStringLiteral(".bak");
    if (!QFileInfo::exists(bak)) QFile::copy(denoise_path_, bak);
    image.save(denoise_path_);
    status_ = QStringLiteral("Saved ") + QFileInfo(denoise_path_).fileName();
}
