#include "assets_page.h"
#include "text_color.h"
#include "res_path.h"
#include "feedback.h"

#include "shell_window.h"

#include "io/tzarc.h"

#include <algorithm>

#include <functional>

#include "io/chump.h"
#include "io/enginespec.h"
#include "io/fbx.h"
#include "io/kuid.h"
#include "io/im_geom.h"
#include "io/trainzmesh.h"
#include "ui/mesh_view.h"

#include <QClipboard>
#include <QDialog>
#include <QDir>
#include <QDirIterator>
#include <QDragEnterEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFont>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QListWidget>
#include <QMap>
#include <QMimeData>
#include <QMessageBox>
#include "crash_report.h"
#include <QPixmap>
#include <QPlainTextEdit>
#include <QProcess>
#include <QPushButton>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QQuickTextDocument>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QSaveFile>
#include <QSettings>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QSyntaxHighlighter>
#include <QTableWidget>
#include <QTextCharFormat>
#include <QUrl>
#include <QVBoxLayout>

#include "ui/trainzutil_page.h"

#ifdef Q_OS_WIN
#include <windows.h>
#include <mmsystem.h>
#endif

namespace {

QString qml_dir() {
return res_qml_dir();
}

QString safe_kuid(const std::string& kuid) {
    QString text = QString::fromStdString(kuid);
    text.replace(QLatin1Char('<'), QString());
    text.replace(QLatin1Char('>'), QString());
    text.replace(QLatin1Char(':'), QLatin1Char('_'));
    return text;
}

const char* k_tool_style =
    "QTableWidget,QPlainTextEdit,QLineEdit,QLabel{background:#1a1e26;color:#f2f4f8;border:none;font:12px 'Segoe UI';}"
    "QHeaderView::section{background:#1a1e26;color:#8b93a1;border:none;padding:4px;}"
    "QPushButton{background:#2a3140;color:#f2f4f8;border:none;border-radius:8px;padding:4px 10px;}"
    "QTableWidget::item{padding:0 4px;}";

class QueueDrop : public QTableWidget {
public:
    std::function<void(const QStringList&)> on_drop;
    explicit QueueDrop(QWidget* parent) : QTableWidget(parent) {
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
        QStringList paths;
        for (const QUrl& url : event->mimeData()->urls()) {
            if (url.isLocalFile()) paths << url.toLocalFile();
        }
        if (on_drop) on_drop(paths);
        event->acceptProposedAction();
    }
};

void style_tool(QWidget* widget) {
    apply_themed_qss(widget, QLatin1String(k_tool_style));
    widget->setFont(QFont(QStringLiteral("Segoe UI"), 10));
}

QString bytes_label(qint64 size) {
    if (size < 0) return QStringLiteral("—");
    if (size < 1024) return QString::number(size) + QStringLiteral(" B");
    if (size < 1024 * 1024) return QString::number(size / 1024.0, 'f', 1) + QStringLiteral(" KB");
    return QString::number(size / (1024.0 * 1024.0), 'f', 1) + QStringLiteral(" MB");
}

void prep_table(QTableWidget* table, const QStringList& headers);


struct RemoveRow {
    QString name;
    QString where;
    qint64 bytes = 0;
};

// Our own frameless confirm: headline + table of exactly what will be removed.
bool confirm_remove(const QString& title, const QString& headline, const QList<RemoveRow>& rows) {
    QDialog dialog;
    make_borderless(&dialog);
    dialog.setMinimumSize(560, 140);
    dialog.resize(560, rows.size() > 6 ? 420 : 140 + 30 * static_cast<int>(rows.size()) + 90);
    auto* lay = new QVBoxLayout(&dialog);
    lay->setContentsMargins(18, 16, 18, 16);
    lay->setSpacing(10);
    auto* head = new QLabel(QStringLiteral("<b style='font-size:15px'>%1</b>").arg(title.toHtmlEscaped()), &dialog);
    lay->addWidget(head);
    lay->addWidget(new QLabel(headline, &dialog));
    auto* table = new QTableWidget(rows.size(), 3, &dialog);
    prep_table(table, {QStringLiteral("Name"), QStringLiteral("Folder"), QStringLiteral("Size")});
    table->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    table->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    table->setColumnWidth(2, 90);
    qint64 total = 0;
    for (int i = 0; i < rows.size(); ++i) {
        total += std::max<qint64>(0, rows[i].bytes);
        table->setItem(i, 0, new QTableWidgetItem(rows[i].name));
        table->setItem(i, 1, new QTableWidgetItem(rows[i].where));
        auto* size = new QTableWidgetItem(bytes_label(rows[i].bytes));
        size->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        table->setItem(i, 2, size);
    }
    lay->addWidget(table, 1);
    auto* foot = new QHBoxLayout;
    foot->addWidget(new QLabel(QStringLiteral("%1 item(s) · %2 · Save CDP to write the change.").arg(rows.size()).arg(bytes_label(total)), &dialog), 1);
    auto* cancel = new QPushButton(QStringLiteral("Cancel"), &dialog);
    auto* ok = new QPushButton(QStringLiteral("Remove"), &dialog);
    ok->setStyleSheet(QStringLiteral("QPushButton{background:#ff5a1f;color:#fff;}QPushButton:hover{background:#ff7a45;}"));
    cancel->setDefault(true);
    foot->addWidget(cancel);
    foot->addWidget(ok);
    lay->addLayout(foot);
    QObject::connect(cancel, &QPushButton::clicked, &dialog, &QDialog::reject);
    QObject::connect(ok, &QPushButton::clicked, &dialog, &QDialog::accept);
    apply_themed_qss(&dialog, QStringLiteral("QDialog{background:#12161c;border:1px solid #ff5a1f;border-radius:12px;}") + QLatin1String(k_tool_style));
    return dialog.exec() == QDialog::Accepted;
}

void finder_mark(const QString& kind, const QString& name, QString& badge, QString& color, QString& detail) {
    const QString low = name.toLower();
    const QString suf = QFileInfo(name).suffix().toLower();
    auto set = [&](const char* letter, const char* paint, const QString& line) {
        badge = QString::fromLatin1(letter);
        color = QString::fromLatin1(paint);
        detail = line;
    };
    if (kind == QLatin1String("dir")) {
        set("F", "#ff5a1f", QStringLiteral("Folder"));
        return;
    }
    if (kind == QLatin1String("asset")) {
        set("A", "#3d9cf0", detail.isEmpty() ? QStringLiteral("Asset") : detail);
        return;
    }
    if (low.endsWith(QLatin1String(".cdp"))) {
        set("C", "#e6a817", QStringLiteral("CDP package"));
        return;
    }
    if (low.endsWith(QLatin1String(".fbx"))) {
        set("X", "#ff9f0a", QStringLiteral("Mesh (fbx)"));
        return;
    }
    if (low == QLatin1String("config.txt") || low.endsWith(QLatin1String(".chump"))) {
        set("T", "#ffd60a", QStringLiteral("Trainz config"));
        return;
    }
    const QStringList images{QStringLiteral("png"), QStringLiteral("jpg"), QStringLiteral("jpeg"), QStringLiteral("bmp"), QStringLiteral("gif"), QStringLiteral("webp"), QStringLiteral("tga"), QStringLiteral("dds")};
    const QStringList audio{QStringLiteral("wav"), QStringLiteral("mp3"), QStringLiteral("ogg"), QStringLiteral("flac")};
    const QStringList text{QStringLiteral("txt"), QStringLiteral("gs"), QStringLiteral("gse"), QStringLiteral("cfg"), QStringLiteral("ini"), QStringLiteral("xml"), QStringLiteral("json"), QStringLiteral("md"), QStringLiteral("csv"), QStringLiteral("lm"), QStringLiteral("lua"), QStringLiteral("html"), QStringLiteral("css"), QStringLiteral("log")};
    if (images.contains(suf)) {
        set("I", "#30d158", QStringLiteral("Image (") + suf.toUpper() + QLatin1Char(')'));
        return;
    }
    if (suf == QLatin1String("im") || suf == QLatin1String("trainzmesh") || suf == QLatin1String("pm")) {
        set("X", "#ff9f0a", QStringLiteral("Mesh (") + suf + QLatin1Char(')'));
        return;
    }
    if (audio.contains(suf)) {
        set("S", "#64d2ff", QStringLiteral("Audio (") + suf + QLatin1Char(')'));
        return;
    }
    if (text.contains(suf)) {
        set("T", "#ffd60a", QStringLiteral("Text (") + suf + QLatin1Char(')'));
        return;
    }
    set("·", "#8e8e93", suf.isEmpty() ? QStringLiteral("File") : suf.toUpper());
}

}  // namespace

QString html_escape(QString text) {
    text.replace(QLatin1Char('&'), QStringLiteral("&amp;"));
    text.replace(QLatin1Char('<'), QStringLiteral("&lt;"));
    text.replace(QLatin1Char('>'), QStringLiteral("&gt;"));
    return text;
}

QString highlight_preview(const QString& text, int pt) {
    QString body = text;
    if (body.size() > 180000) body.truncate(180000);
    static const QStringList words{
        QStringLiteral("username"), QStringLiteral("kind"), QStringLiteral("kuid"), QStringLiteral("script"),
        QStringLiteral("class"), QStringLiteral("thread"), QStringLiteral("void"), QStringLiteral("int"),
        QStringLiteral("float"), QStringLiteral("bool"), QStringLiteral("string"), QStringLiteral("return"),
        QStringLiteral("if"), QStringLiteral("else"), QStringLiteral("for"), QStringLiteral("while"),
        QStringLiteral("include"), QStringLiteral("define"), QStringLiteral("public"), QStringLiteral("static"),
        QStringLiteral("inherited"), QStringLiteral("null"), QStringLiteral("true"), QStringLiteral("false"),
        QStringLiteral("version"), QStringLiteral("offset"), QStringLiteral("calcPoint"), QStringLiteral("multiplier"),
        QStringLiteral("animationCutOff"), QStringLiteral("renderCutOff"), QStringLiteral("attachmentCutOff"),
        QStringLiteral("mesh"), QStringLiteral("name"), QStringLiteral("Primary"), QStringLiteral("Alpha"),
        QStringLiteral("Tile"), QStringLiteral("UsageHint"), QStringLiteral("NormalMapHint"), QStringLiteral("Compression"),
    };
    QString html;
    html.reserve(body.size() + body.size() / 4);
    html += QStringLiteral("<pre style=\"font-family:Consolas,monospace;font-size:%1px;color:#D4D4D4;line-height:140%;\">").arg(pt + 2);
    const QStringList lines = body.split(QLatin1Char('\n'));
    const int limit = std::min(4000, static_cast<int>(lines.size()));
    for (int i = 0; i < limit; ++i) {
        const QString line = lines.at(i);
        html += QStringLiteral("<span style=\"color:#858585\">%1 </span>").arg(i + 1, 4);
        const QString trimmed = line.trimmed();
        if (trimmed.startsWith(QLatin1Char('#')) || trimmed.startsWith(QLatin1String("//"))) {
            html += QStringLiteral("<span style=\"color:#6A9955\">") + html_escape(line) + QStringLiteral("</span><br>");
            continue;
        }
        int at = 0;
        bool lead = true;
        while (at < line.size()) {
            if (lead && line.at(at).isSpace()) {
                html += html_escape(line.mid(at, 1));
                ++at;
                continue;
            }
            if (line.at(at).isDigit()) {
                int end = at + 1;
                while (end < line.size() && (line.at(end).isDigit() || line.at(end) == QLatin1Char('.'))) ++end;
                html += QStringLiteral("<span style=\"color:#B5CEA8\">") + html_escape(line.mid(at, end - at)) + QStringLiteral("</span>");
                at = end;
                lead = false;
                continue;
            }
            if (line.at(at) == QLatin1Char('"')) {
                int end = line.indexOf(QLatin1Char('"'), at + 1);
                if (end < 0) end = line.size() - 1;
                html += QStringLiteral("<span style=\"color:#CE9178\">") + html_escape(line.mid(at, end - at + 1)) + QStringLiteral("</span>");
                at = end + 1;
                lead = false;
                continue;
            }
            if (line.mid(at).startsWith(QLatin1String("<kuid"), Qt::CaseInsensitive)) {
                int end = line.indexOf(QLatin1Char('>'), at);
                if (end < 0) end = std::min(at + 40, static_cast<int>(line.size()) - 1);
                html += QStringLiteral("<span style=\"color:#4EC9B0\">") + html_escape(line.mid(at, end - at + 1)) + QStringLiteral("</span>");
                at = end + 1;
                lead = false;
                continue;
            }
            if (line.at(at).isLetter()) {
                int end = at;
                while (end < line.size() && (line.at(end).isLetter() || line.at(end) == QLatin1Char('_'))) ++end;
                const QString word = line.mid(at, end - at);
                if (lead || words.contains(word, Qt::CaseInsensitive)) html += QStringLiteral("<span style=\"color:#569CD6\">") + html_escape(word) + QStringLiteral("</span>");
                else html += html_escape(word);
                at = end;
                lead = false;
                continue;
            }
            html += html_escape(line.mid(at, 1));
            lead = false;
            ++at;
        }
        html += QStringLiteral("<br>");
    }
    if (lines.size() > limit) html += QStringLiteral("<span style=\"color:#858585\">…</span>");
    html += QStringLiteral("</pre>");
    return html;
}

namespace {

class ConfigHighlighter final : public QSyntaxHighlighter {
public:
    explicit ConfigHighlighter(QTextDocument* document) : QSyntaxHighlighter(document) {}

protected:
    void highlightBlock(const QString& text) override {
        QTextCharFormat comments;
        comments.setForeground(QColor(QStringLiteral("#6A9955")));
        const int comment = text.indexOf(QRegularExpression(QStringLiteral(R"((#|//))")));
        if (comment >= 0) setFormat(comment, text.size() - comment, comments);

        QTextCharFormat strings;
        strings.setForeground(QColor(QStringLiteral("#CE9178")));
        auto quoted = QRegularExpression(QStringLiteral(R"("[^"]*")")).globalMatch(text);
        while (quoted.hasNext()) {
            const auto match = quoted.next();
            setFormat(match.capturedStart(), match.capturedLength(), strings);
        }

        QTextCharFormat kuids;
        kuids.setForeground(QColor(QStringLiteral("#4EC9B0")));
        auto kuid = QRegularExpression(QStringLiteral(R"(<kuid2?:[^>]+>)")).globalMatch(text);
        while (kuid.hasNext()) {
            const auto match = kuid.next();
            setFormat(match.capturedStart(), match.capturedLength(), kuids);
        }

        QTextCharFormat numbers;
        numbers.setForeground(QColor(QStringLiteral("#B5CEA8")));
        auto number = QRegularExpression(QStringLiteral(R"(\b\d+(?:\.\d+)?\b)")).globalMatch(text);
        while (number.hasNext()) {
            const auto match = number.next();
            setFormat(match.capturedStart(), match.capturedLength(), numbers);
        }

        QTextCharFormat keywords;
        keywords.setForeground(QColor(QStringLiteral("#569CD6")));
        keywords.setFontWeight(QFont::DemiBold);
        auto word = QRegularExpression(
                        QStringLiteral(
                            R"(\b(username|kind|kuid|script|class|thread|void|int|float|bool|string|return|if|else|for|while|include|define|public|static|inherited|null|true|false)\b)"))
                        .globalMatch(text);
        while (word.hasNext()) {
            const auto match = word.next();
            setFormat(match.capturedStart(), match.capturedLength(), keywords);
        }

        const auto first = QRegularExpression(QStringLiteral(R"(^\s*([A-Za-z_][\w-]*))")).match(text);
        if (first.hasMatch()) setFormat(first.capturedStart(1), first.capturedLength(1), keywords);
    }
};

QString cdp_filename(QString kuid) {
    kuid.remove(QLatin1Char('<')).remove(QLatin1Char('>'));
    kuid.replace(QRegularExpression(QStringLiteral("[^A-Za-z0-9]+")), QStringLiteral("_"));
    while (kuid.startsWith(QLatin1Char('_'))) kuid.remove(0, 1);
    while (kuid.endsWith(QLatin1Char('_'))) kuid.chop(1);
    if (kuid.isEmpty()) kuid = QStringLiteral("asset");
    return kuid + QStringLiteral(".cdp");
}

QStringList extract_kuids(const QString& text) {
    QStringList rows;
    QRegularExpression re(QStringLiteral("<kuid2?:\\d+:\\d+(?::\\d+)?>"));
    auto it = re.globalMatch(text);
    while (it.hasNext()) rows << it.next().captured(0);
    return rows;
}

void prep_table(QTableWidget* table, const QStringList& headers) {
    table->setColumnCount(headers.size());
    table->setHorizontalHeaderLabels(headers);
    table->horizontalHeader()->setStretchLastSection(true);
    table->horizontalHeader()->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    table->verticalHeader()->setVisible(false);
    table->verticalHeader()->setDefaultSectionSize(28);
    table->setShowGrid(false);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setSelectionMode(QAbstractItemView::ExtendedSelection);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->setAlternatingRowColors(true);
    table->setFocusPolicy(Qt::StrongFocus);
    style_tool(table);
}

}  // namespace

AssetsBridge::AssetsBridge(QObject* parent) : QObject(parent) {
    if (auto* host = qobject_cast<QWidget*>(parent)) {
        tex_ = new Texmesh(host);
        connect(tex_, &Texmesh::changed, this, &AssetsBridge::changed);
        connect(tex_, &Texmesh::pageRequested, this, &AssetsBridge::setPage);
        build_tools(host);
    }
}

QString AssetsBridge::footerJson() const {
    if (suite_ == QLatin1String("texmesh")) return QStringLiteral("[]");
    const QJsonArray rows{
        QJsonObject{{QStringLiteral("id"), QStringLiteral("open_cdp")}, {QStringLiteral("glyph"), material_glyph("file_open")}, {QStringLiteral("tip"), QStringLiteral("Open CDP")}, {QStringLiteral("accent"), true}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("extract_cdp")}, {QStringLiteral("glyph"), material_glyph("unarchive")}, {QStringLiteral("tip"), QStringLiteral("Extract CDP")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("open_tzarc")}, {QStringLiteral("glyph"), material_glyph("inventory_2")}, {QStringLiteral("tip"), QStringLiteral("Open TZarc")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("extract_tzarc")}, {QStringLiteral("glyph"), material_glyph("folder_zip")}, {QStringLiteral("tip"), QStringLiteral("Extract TZarc config")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("copy_pkg_kuids")}, {QStringLiteral("glyph"), material_glyph("content_copy")}, {QStringLiteral("tip"), QStringLiteral("Copy KUIDs")}, {QStringLiteral("accent"), false}},
    };
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::queueBtnJson() const {
    const QJsonArray rows{
        QJsonObject{{QStringLiteral("id"), QStringLiteral("remove")}, {QStringLiteral("glyph"), material_glyph("delete")}, {QStringLiteral("tip"), QStringLiteral("Remove")}, {QStringLiteral("accent"), false}},
        QJsonObject{{QStringLiteral("id"), QStringLiteral("clear")}, {QStringLiteral("glyph"), material_glyph("clear")}, {QStringLiteral("tip"), QStringLiteral("Clear queue")}, {QStringLiteral("accent"), false}},
    };
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::leftNavJson() const {
    if (suite_ == QLatin1String("texmesh"))
        return QStringLiteral(R"([{"key":"meshops","label":"Mesh\nLods","w":100},{"key":"texture","label":"Texture\nParams","w":116}])");
    return QStringLiteral(R"([{"key":"packages","label":"Packages","w":108},{"key":"config","label":"Config","w":100}])");
}

QString AssetsBridge::rightNavJson() const {
    if (suite_ == QLatin1String("texmesh"))
        return QStringLiteral(R"([{"key":"parameter","label":"Texture\nEditor","w":116},{"key":"denoise","label":"Texture\nDenoiser","w":128}])");
    return QStringLiteral(R"([{"key":"kuid","label":"KUID","w":96},{"key":"export","label":"Export","w":96}])");
}

QString AssetsBridge::centerKind() const {
    if (page_ == QLatin1String("meshops") || page_ == QLatin1String("texture")) return QStringLiteral("split");
    if (page_ == QLatin1String("parameter") || page_ == QLatin1String("denoise")) return QStringLiteral("canvas");
    return QStringLiteral("page");
}

bool AssetsBridge::viewFast() const {
    if (finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size())) return false;
    const QString suffix = QFileInfo(shown_[static_cast<size_t>(finder_sel_)].name).suffix().toLower();
    return suffix == QLatin1String("trainzmesh") || suffix == QLatin1String("im") ||
           suffix == QLatin1String("fbx") || suffix == QLatin1String("pm");
}

bool AssetsBridge::viewMesh() const { return viewFast(); }

bool AssetsBridge::viewEngine() const {
    if (!view_editor_ || finder_asset_ < 0 || finder_asset_ >= static_cast<int>(assets_.size())) return false;
    if (finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size())) return false;
    const FinderShown& entry = shown_[static_cast<size_t>(finder_sel_)];
    if (entry.rel != QLatin1String("__config__") &&
        entry.name.compare(QLatin1String("config.txt"), Qt::CaseInsensitive) != 0)
        return false;
    return looks_like_enginespec(preview_plain_.toStdString());
}

void AssetsBridge::set_suite(const QString& suite) {
    suite_ = suite == QLatin1String("texmesh") ? suite : QStringLiteral("assets");
    if (tex_) tex_->set_active(suite_ == QLatin1String("texmesh"));
    setPage(suite_ == QLatin1String("texmesh") ? QStringLiteral("meshops") : QStringLiteral("packages"));
}

void AssetsBridge::load_bytes(const QByteArray& bytes, const QString& path) {
    bytes_.assign(bytes.begin(), bytes.end());
    path_ = path;
    assets_.clear();
    asset_row_ = -1;
    try {
        if (path.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
            const auto config = read_tzarc_config(bytes_.data(), bytes_.size());
            CdpAssetEntry row;
            row.kuid = path.toStdString();
            row.files.push_back("config.txt");
            assets_.push_back(row);
            tzarc_text_ = QString::fromUtf8(reinterpret_cast<const char*>(config.data()), static_cast<int>(config.size()));
            view_hint_ = QStringLiteral("Select a file in Finder");
        } else {
            assets_ = list_cdp_assets(bytes_.data(), bytes_.size());
            tzarc_text_.clear();
            view_hint_ = QStringLiteral("Select a file in Finder");
        }
        center_tip_ = QString::number(assets_.size()) + QStringLiteral(" assets");
    } catch (const std::exception& error) {
        center_tip_ = QString::fromUtf8(error.what());
    }
        AssetQueueItem item;
        item.path = path;
        item.kind = path.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive) ? QStringLiteral("TZarc") : QStringLiteral("CDP");
        item.bytes = bytes;
        item.assets = assets_;
        item.size = bytes_label(bytes.size());
        item.info = QString::number(assets_.size()) + QStringLiteral(" assets");
        queue_.push_back(std::move(item));
        refresh_queue();
        select_queue(static_cast<int>(queue_.size()) - 1);
        emit changed();
}

QString AssetsBridge::cell(int row, int column) const {
    if (row < 0 || row >= static_cast<int>(assets_.size())) return {};
    const CdpAssetEntry& asset = assets_[static_cast<size_t>(row)];
    if (column == 0) return QString::fromStdString(asset.kuid);
    if (column == 1) return QString::fromStdString(asset.username);
    if (column == 2) return QString::fromStdString(asset.kind);
    return {};
}

QStringList AssetsBridge::files_of(int asset) const {
    if (asset < 0 || asset >= static_cast<int>(assets_.size())) return {};
    QStringList rows;
    for (const std::string& file : assets_[static_cast<size_t>(asset)].files) rows << QString::fromStdString(file);
    return rows;
}

QString AssetsBridge::file_text(int asset, const QString& rel) const {
    if (asset < 0 || asset >= static_cast<int>(assets_.size()) || bytes_.empty()) return {};
    if (path_.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive) && rel == QLatin1String("config.txt")) return tzarc_text_;
    try {
        const auto data = read_cdp_file(bytes_.data(), bytes_.size(), assets_[static_cast<size_t>(asset)].kuid, rel.toStdString());
        return QString::fromUtf8(reinterpret_cast<const char*>(data.data()), static_cast<int>(data.size()));
    } catch (const std::exception&) {
        return {};
    }
}

int AssetsBridge::extract_to(const QString& directory) const {
    int written = 0;
    QDir root(directory);
    if (path_.endsWith(QLatin1String(".tzarc"), Qt::CaseInsensitive)) {
        QFile file(root.filePath(QStringLiteral("config.txt")));
        if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            file.write(view_hint_.toUtf8());
            return 1;
        }
        return 0;
    }
    for (const CdpAssetEntry& asset : assets_) {
        const QString folder = root.filePath(safe_kuid(asset.kuid));
        QDir().mkpath(folder);
        for (const std::string& rel : asset.files) {
            if (rel.find("..") != std::string::npos) continue;
            const auto data = read_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, rel);
            const QString dest = QDir(folder).filePath(QString::fromStdString(rel));
            QDir().mkpath(QFileInfo(dest).path());
            QFile file(dest);
            if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) continue;
            file.write(reinterpret_cast<const char*>(data.data()), static_cast<qint64>(data.size()));
            ++written;
        }
    }
    return written;
}

void AssetsBridge::show_asset(int row) {
    asset_row_ = row;
    if (row < 0 || row >= static_cast<int>(assets_.size())) return;
    view_title_ = QString::fromStdString(assets_[static_cast<size_t>(row)].kuid);
    viewer_on_ = true;
}

void AssetsBridge::setPage(const QString& page) {
    page_ = page;
    const QString titles[][2] = {
        {QStringLiteral("packages"), QStringLiteral("Packages")},
        {QStringLiteral("config"), QStringLiteral("Config")},
        {QStringLiteral("kuid"), QStringLiteral("KUID")},
        {QStringLiteral("export"), QStringLiteral("Export")},
        {QStringLiteral("meshops"), QStringLiteral("Mesh Lods")},
        {QStringLiteral("texture"), QStringLiteral("Texture Params")},
        {QStringLiteral("parameter"), QStringLiteral("Texture Editor")},
        {QStringLiteral("denoise"), QStringLiteral("Texture Denoiser")},
    };
    page_title_ = page;
    center_title_ = page;
    for (const auto& row : titles) {
        if (row[0] != page) continue;
        page_title_ = row[1];
        center_title_ = row[1];
    }
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->set_page(page_);
        center_tip_ = tex_->center_tip();
        dock_w_ = tex_->dock_width();
        foot_note_ = tex_->foot_note();
    }
    sync_pages();
    emit changed();
}

void AssetsBridge::goHome() { emit homeRequested(); }
void AssetsBridge::setSideW(double width) {
    const int next = std::max(320, std::min(560, static_cast<int>(width)));
    if (next == side_w_) return;
    side_w_ = next;
    emit layoutChanged();
}
void AssetsBridge::setDockW(double width) {
    // QML caps the Packages viewer at half the width left after the queue column.
    const int next = std::max(280, std::min(4096, static_cast<int>(width)));
    if (next == dock_w_) return;
    dock_w_ = next;
    emit layoutChanged();
}

void AssetsBridge::runAction(const QString& action) {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->run_action(action);
        center_tip_ = tex_->center_tip();
        foot_note_ = tex_->foot_note();
        emit changed();
        return;
    }
    if (action == QLatin1String("open_cdp") || action == QLatin1String("open_tzarc")) {
        const QString filter = action == QLatin1String("open_tzarc") ? QStringLiteral("TZarc (*.tzarc)") : QStringLiteral("CDP (*.cdp)");
        const QString path = QFileDialog::getOpenFileName(nullptr, action, {}, filter);
        if (path.isEmpty()) return;
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return;
        load_bytes(file.readAll(), path);
        return;
    }
    if (action == QLatin1String("extract_cdp") || action == QLatin1String("extract_tzarc")) {
        const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Extract"));
        if (dir.isEmpty()) return;
        center_tip_ = QString::number(extract_to(dir)) + QStringLiteral(" files");
        emit changed();
        return;
    }
    if (action == QLatin1String("copy_pkg_kuids")) {
        QStringList rows;
        for (const CdpAssetEntry& asset : assets_) rows << QString::fromStdString(asset.kuid);
        if (QGuiApplication::clipboard()) QGuiApplication::clipboard()->setText(rows.join(QLatin1Char('\n')));
        return;
    }
    if (action == QLatin1String("open_chump")) {
        const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open config.chump"), {}, QStringLiteral("config.chump (*.chump);;All (*.*)"));
        if (path.isEmpty()) return;
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) return;
        const QByteArray bytes = file.readAll();
        try {
            const ChumpFile chump = read_chump(reinterpret_cast<const uint8_t*>(bytes.constData()), static_cast<size_t>(bytes.size()));
            config_edit_->setPlainText(QString::fromStdString(chump_to_text(chump)));
            config_path_ = path;
            center_tip_ = QFileInfo(path).fileName();
        } catch (const std::exception& error) {
            center_tip_ = QString::fromUtf8(error.what());
        }
        emit changed();
        return;
    }
    if (action == QLatin1String("save_chump") || action == QLatin1String("export_txt")) {
        if (config_edit_ == nullptr) return;
        try {
            if (action == QLatin1String("export_txt")) {
                const QString path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Export config.txt"), QStringLiteral("config.txt"), QStringLiteral("config.txt (*.txt)"));
                if (path.isEmpty()) return;
                QFile file(path);
                if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return;
                file.write(config_edit_->toPlainText().toUtf8());
                center_tip_ = QFileInfo(path).fileName();
            } else {
                const ChumpFile chump = text_to_chump(config_edit_->toPlainText().toStdString());
                const auto bytes = encode_chump(chump);
                QString path = config_path_;
                if (path.isEmpty()) path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Save config.chump"), QStringLiteral("config.chump"), QStringLiteral("config.chump (*.chump)"));
                if (path.isEmpty()) return;
                QFile file(path);
                if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return;
                file.write(reinterpret_cast<const char*>(bytes.data()), static_cast<qint64>(bytes.size()));
                config_path_ = path;
                center_tip_ = QStringLiteral("Saved ") + QFileInfo(path).fileName();
                post_status(center_tip_);
            }
        } catch (const std::exception& error) {
            center_tip_ = QString::fromUtf8(error.what());
            post_status(QStringLiteral("Save failed — ") + center_tip_);
        }
        emit changed();
        return;
    }
    if (action == QLatin1String("normalize")) {
        read_kuid_list();
        emit changed();
        return;
    }
    if (action == QLatin1String("copy_kuid")) {
        if (kuid_out_ && QGuiApplication::clipboard()) QGuiApplication::clipboard()->setText(kuid_out_->toPlainText());
        return;
    }
    if (action == QLatin1String("read_list")) {
        read_kuid_list();
        emit changed();
        return;
    }
    if (action == QLatin1String("export_each") || action == QLatin1String("export_one")) start_export(action == QLatin1String("export_one"));
}

void AssetsBridge::undoEdit() {
    if (suite_ == QLatin1String("texmesh") && tex_) tex_->run_action(QStringLiteral("param_undo"));
}
void AssetsBridge::redoEdit() {
    if (suite_ == QLatin1String("texmesh") && tex_) tex_->run_action(QStringLiteral("param_redo"));
}

void AssetsBridge::queueClear() {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->queue_clear();
        return;
    }
    queue_.clear();
    bytes_.clear();
    assets_.clear();
    path_.clear();
    queue_row_ = -1;
    finder_asset_ = -1;
    finder_parts_.clear();
    clear_preview();
    refresh_queue();
    refresh_finder();
    center_tip_ = QStringLiteral("Queue cleared");
    emit changed();
}

void AssetsBridge::queueRemove() {
    if (suite_ == QLatin1String("texmesh") && tex_) {
        tex_->queue_remove();
        return;
    }
    QList<int> rows;
    if (queue_row_ >= 0) rows << queue_row_;
    else if (!queue_.empty()) rows << static_cast<int>(queue_.size()) - 1;
    std::sort(rows.begin(), rows.end(), std::greater<int>());
    for (int row : rows) {
        if (row < 0 || row >= static_cast<int>(queue_.size())) continue;
        queue_.erase(queue_.begin() + row);
    }
    queue_row_ = queue_.empty() ? -1 : std::min(queue_row_, static_cast<int>(queue_.size()) - 1);
    if (queue_row_ >= 0) select_queue(queue_row_);
    else {
        assets_.clear();
        bytes_.clear();
        path_.clear();
        clear_preview();
        refresh_finder();
    }
    refresh_queue();
    emit changed();
}

void AssetsBridge::placeQueue(double x, double y, double w, double h) {
    if (suite_ == QLatin1String("texmesh")) {
        if (tex_) tex_->place_queue(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
        place_widget(queue_table_, 0, 0, 0, 0, false);
        return;
    }
    if (tex_) tex_->place_queue(0, 0, 0, 0);
    const int next[4] = {static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)};
    if (next[0] == queue_at_[0] && next[1] == queue_at_[1] && next[2] == queue_at_[2] && next[3] == queue_at_[3]) return;
    queue_at_[0] = next[0];
    queue_at_[1] = next[1];
    queue_at_[2] = next[2];
    queue_at_[3] = next[3];
    place_widget(queue_table_, 0, 0, 0, 0, false);
}
void AssetsBridge::placeCenter(double x, double y, double w, double h) {
    const bool assets = suite_ != QLatin1String("texmesh");
    const int next[4] = {static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)};
    if (next[0] == center_at_[0] && next[1] == center_at_[1] && next[2] == center_at_[2] && next[3] == center_at_[3]) return;
    center_at_[0] = next[0];
    center_at_[1] = next[1];
    center_at_[2] = next[2];
    center_at_[3] = next[3];
    place_widget(finder_page_, 0, 0, 0, 0, false);
    place_widget(config_edit_, 0, 0, 0, 0, false);
    place_widget(kuid_page_, 0, 0, 0, 0, false);
    place_widget(export_page_, 0, 0, 0, 0, false);
    Q_UNUSED(assets);
    emit placeCenterRequested(next[0], next[1], next[2], next[3]);
}
void AssetsBridge::placePreview(double x, double y, double w, double h) {
    const int next[4] = {static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h)};
    if (next[0] == preview_at_[0] && next[1] == preview_at_[1] && next[2] == preview_at_[2] && next[3] == preview_at_[3]) return;
    preview_at_[0] = next[0];
    preview_at_[1] = next[1];
    preview_at_[2] = next[2];
    preview_at_[3] = next[3];
    place_widget(preview_, 0, 0, 0, 0, false);
    sync_mesh_view();
    emit placePreviewRequested(next[0], next[1], next[2], next[3]);
}
void AssetsBridge::placeDock(double, double, double, double) {}
void AssetsBridge::placeFormTool(double x, double y, double w, double h) {
    if (tex_) tex_->place_form_tool(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
}
void AssetsBridge::placeWell(const QString& key, double x, double y, double w, double h) {
    if (tex_) tex_->place_well(key, static_cast<int>(x), static_cast<int>(y), static_cast<int>(w), static_cast<int>(h));
}
void AssetsBridge::apply_edited_bytes(std::vector<uint8_t> bytes) {
    bytes_ = std::move(bytes);
    assets_ = list_cdp_assets(bytes_.data(), bytes_.size());
    if (queue_row_ >= 0 && queue_row_ < static_cast<int>(queue_.size())) {
        AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
        item.bytes = QByteArray(reinterpret_cast<const char*>(bytes_.data()), static_cast<int>(bytes_.size()));
        item.assets = assets_;
        item.size = bytes_label(static_cast<qint64>(bytes_.size()));
        item.info = QString::number(assets_.size()) + QStringLiteral(" assets");
    }
    cdp_dirty_ = true;
    refresh_queue();
    refresh_finder();
}
void AssetsBridge::sync_mesh_view() {
    if (mesh_view_ == nullptr) return;
    place_widget(mesh_view_, preview_at_[0], preview_at_[1], preview_at_[2], preview_at_[3], mesh_on_);
}
bool AssetsBridge::show_mesh_inline(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return false;
    const QByteArray bytes = file.readAll();
    const auto* data = reinterpret_cast<const uint8_t*>(bytes.constData());
    std::vector<ViewPart> parts;
    try {
        if (path.endsWith(QLatin1String(".im"), Qt::CaseInsensitive)) {
            for (const MeshPart& part : parse_im_view(data, static_cast<size_t>(bytes.size())).parts) {
                ViewPart row;
                row.name = QString::fromStdString(part.name);
                row.positions = part.positions;
                row.normals = part.normals;
                row.uvs = part.uvs;
                row.indices = part.indices;
                parts.push_back(std::move(row));
            }
        } else if (path.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) {
            for (const MeshPart& part : parse_fbx_parts(data, static_cast<size_t>(bytes.size()))) {
                ViewPart row;
                row.name = QString::fromStdString(part.name);
                row.positions = part.positions;
                row.normals = part.normals;
                row.uvs = part.uvs;
                row.indices = part.indices;
                parts.push_back(std::move(row));
            }
        } else {
            for (const SubMesh& part : parse_trainzmesh(data, static_cast<size_t>(bytes.size())).submeshes) {
                ViewPart row;
                row.name = QString::fromStdString(part.name);
                row.material = QString::fromStdString(part.material_type);
                row.positions = part.positions;
                row.normals = part.normals;
                row.uvs = part.uvs;
                row.indices = part.indices;
                parts.push_back(std::move(row));
            }
        }
    } catch (const std::exception&) {
        return false;
    }
    if (parts.empty()) return false;
    if (mesh_view_ == nullptr) mesh_view_ = new MeshView(qobject_cast<QWidget*>(parent()));
    mesh_view_->setParts(std::move(parts)); // ponytail: untextured on purpose (fast); Mesh Studio does PBR
    mesh_view_->resetCamera();
    mesh_on_ = true;
    sync_mesh_view();
    return true;
}
void AssetsBridge::clear_preview() {
    mesh_on_ = false;
    sync_mesh_view();
    finder_sel_ = -1;
    preview_body_.clear();
    preview_image_url_.clear();
    audioStop();
    preview_audio_ = false;
    preview_plain_.clear();
    preview_name_.clear();
    preview_on_ = false;
    preview_rich_ = false;
    view_editor_ = false;
    view_pane_ = 0;
    view_title_ = QStringLiteral("Viewer");
    view_hint_ = QStringLiteral("Select a file in Finder");
    current_edit_key_.clear();
    if (preview_text_ != nullptr) preview_text_->clear();
    if (preview_ != nullptr && preview_empty_ != nullptr) preview_->setCurrentWidget(preview_empty_);
}
QString AssetsBridge::stage_selected_asset() {
    if (finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size()) || finder_asset_ < 0) return {};
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) return {};
    const FinderShown entry = shown_[static_cast<size_t>(finder_sel_)];
    const AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    if (finder_asset_ >= static_cast<int>(item.assets.size())) return {};
    const CdpAssetEntry& asset = item.assets[static_cast<size_t>(finder_asset_)];
    const QString rel = entry.rel;
    if (rel.isEmpty()) return {};
    if (item.kind == QLatin1String("Folder"))
        return QDir(QString::fromStdString(asset.username)).filePath(rel);
    if (bytes_.empty()) return {};

    const QString root = QDir(QStandardPaths::writableLocation(QStandardPaths::TempLocation))
                             .filePath(QStringLiteral("mstn-trainz-studio/packages/") + safe_kuid(asset.kuid));
    QDir(root).removeRecursively();
    QDir().mkpath(root);
    QFile config(QDir(root).filePath(QStringLiteral("config.txt")));
    if (config.open(QIODevice::WriteOnly | QIODevice::Truncate))
        config.write(QByteArray::fromStdString(asset_config_text(bytes_.data(), bytes_.size(), asset.kuid)));
    for (const std::string& rel_raw : asset.files) {
        const QString rel = QString::fromStdString(rel_raw).replace(QLatin1Char('\\'), QLatin1Char('/'));
        if (rel.contains(QLatin1String("../")) || rel.startsWith(QLatin1Char('/'))) continue;
        const auto data = read_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, rel_raw);
        const QString destination = QDir(root).filePath(rel);
        QDir().mkpath(QFileInfo(destination).path());
        QFile file(destination);
        if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) continue;
        file.write(reinterpret_cast<const char*>(data.data()), static_cast<qint64>(data.size()));
    }
    return QDir(root).filePath(rel);
}
void AssetsBridge::refreshCenter() { emit changed(); }
void AssetsBridge::setViewerPane(int pane) {
    if (pane != 0 && pane != 1) return;
    if (pane == 1 && !view_editor_) return;
    if (pane == view_pane_) return;
    view_pane_ = pane;
    // The text well is one TextEdit. Viewer is that document locked; coloring is the highlighter.
    // Rebuilding an HTML copy here reparsed the whole file on the UI thread and hitch-ed the swap.
    const QString mode = view_pane_ == 1 ? QStringLiteral("Editor") : QStringLiteral("Viewer");
    view_title_ = preview_name_.isEmpty() ? mode : mode + QStringLiteral(" — ") + preview_name_;
    emit changed();
}
void AssetsBridge::setPreviewText(const QString& text) {
    if (view_pane_ != 1 || !view_editor_) return;
    preview_plain_ = text;
    preview_body_ = text;
    last_edit_committed_ = false;
    note_edit(text);
}
QString AssetsBridge::edit_key(int asset_index, const QString& rel) const {
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) return {};
    if (asset_index < 0 || asset_index >= static_cast<int>(queue_[static_cast<size_t>(queue_row_)].assets.size())) return {};
    const AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    const QString name = rel == QLatin1String("__config__") ? QStringLiteral("config.txt") : rel;
    return item.path + QLatin1Char('|') + QString::fromStdString(item.assets[static_cast<size_t>(asset_index)].kuid) + QLatin1Char('|') + name;
}
void AssetsBridge::note_edit(const QString& text) {
    if (current_edit_key_.isEmpty()) return;
    auto same = [](QString left, QString right) {
        if (left.endsWith(QLatin1Char('\n'))) left.chop(1);
        if (right.endsWith(QLatin1Char('\n'))) right.chop(1);
        if (left.endsWith(QLatin1Char('\r'))) left.chop(1);
        if (right.endsWith(QLatin1Char('\r'))) right.chop(1);
        return left == right;
    };
    const bool was = dirty_text_.contains(current_edit_key_);
    if (same(text, saved_baseline_.value(current_edit_key_))) dirty_text_.remove(current_edit_key_);
    else dirty_text_.insert(current_edit_key_, text);
    if (was == dirty_text_.contains(current_edit_key_)) return;
    refresh_finder();
    emit finderChanged();
}
void AssetsBridge::attachEditor(QObject* quickDocument) {
    auto* document = qobject_cast<QQuickTextDocument*>(quickDocument);
    if (document == nullptr || document->textDocument() == nullptr) return;
    editor_document_ = document->textDocument();
    if (document->textDocument()->property("mstnConfigHighlighter").toBool()) return;
    document->textDocument()->setProperty("mstnConfigHighlighter", true);
    new ConfigHighlighter(document->textDocument());
}
void AssetsBridge::audioPlay() {
#ifdef Q_OS_WIN
    if (preview_audio_path_.isEmpty()) return;
    mciSendStringW(L"close mstn_pkg_audio", nullptr, 0, nullptr);
    const QString open = QStringLiteral("open \"%1\" alias mstn_pkg_audio").arg(QDir::toNativeSeparators(preview_audio_path_));
    if (mciSendStringW(reinterpret_cast<LPCWSTR>(open.utf16()), nullptr, 0, nullptr) == 0)
        mciSendStringW(L"play mstn_pkg_audio from 0", nullptr, 0, nullptr);
#endif
}
void AssetsBridge::audioStop() {
#ifdef Q_OS_WIN
    mciSendStringW(L"stop mstn_pkg_audio", nullptr, 0, nullptr);
    mciSendStringW(L"close mstn_pkg_audio", nullptr, 0, nullptr);
#endif
}
void AssetsBridge::viewerFont(int delta) {
    preview_pt_ = std::max(8, std::min(28, preview_pt_ + delta));
    emit changed();
}
void AssetsBridge::viewerBack() {}
void AssetsBridge::viewerExpand() {
    viewer_expanded_ = !viewer_expanded_;
    emit changed();
}
void AssetsBridge::viewerSave() {
    if (saving_) return;
    struct Guard {
        bool& flag;
        explicit Guard(bool& flag) : flag(flag) { flag = true; }
        ~Guard() { flag = false; }
    } guard(saving_);
    last_edit_committed_ = false;
    if (!view_editor_ || finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size())) return;
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) return;
    const FinderShown entry = shown_[static_cast<size_t>(finder_sel_)];
    if (entry.kind != QLatin1String("file") || finder_asset_ < 0) return;
    AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    const CdpAssetEntry asset = item.assets[static_cast<size_t>(finder_asset_)];
    if (editor_document_ != nullptr) preview_plain_ = editor_document_->toPlainText();
    const QByteArray text = (preview_plain_.endsWith(QLatin1Char('\n')) ? preview_plain_ : preview_plain_ + QLatin1Char('\n')).toUtf8();
    try {
        if (item.kind == QLatin1String("Folder")) {
            const QString rel = entry.rel == QLatin1String("__config__") ? QStringLiteral("config.txt") : entry.rel;
            const QString dest = QDir(QString::fromStdString(asset.username)).filePath(rel);
            QFile file(dest);
            if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
                throw std::runtime_error("cannot write selected file");
            file.write(text);
            center_tip_ = QStringLiteral("Saved ") + QFileInfo(dest).fileName();
            post_status(center_tip_);
        } else if (entry.rel == QLatin1String("__config__")) {
            apply_edited_bytes(replace_asset_config(
                bytes_.data(), bytes_.size(), asset.kuid, preview_plain_.toStdString()));
            const std::string expected = chump_to_text(text_to_chump(preview_plain_.toStdString()));
            const std::string actual = asset_config_text(bytes_.data(), bytes_.size(), asset.kuid);
            if (actual != expected) throw std::runtime_error("config verification failed after repacking CDP");
            center_tip_ = QStringLiteral("Updated config.txt in CDP — use Save CDP to write it.");
        } else {
            apply_edited_bytes(replace_cdp_file(
                bytes_.data(), bytes_.size(), asset.kuid, entry.rel.toStdString(),
                reinterpret_cast<const uint8_t*>(text.constData()), static_cast<size_t>(text.size())));
            const auto actual = read_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, entry.rel.toStdString());
            if (actual.size() != static_cast<size_t>(text.size()) ||
                !std::equal(actual.begin(), actual.end(), reinterpret_cast<const uint8_t*>(text.constData())))
                throw std::runtime_error("file verification failed after repacking CDP");
            center_tip_ = QStringLiteral("Updated ") + entry.rel + QStringLiteral(" — use Save CDP to write it.");
        }
    } catch (const std::exception& error) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Save"), QString::fromUtf8(error.what()));
        return;
    }
    const QString key = edit_key(finder_asset_, entry.rel);
    current_edit_key_ = key;
    saved_baseline_.insert(key, preview_plain_);
    dirty_text_.remove(key);
    last_edit_committed_ = true;
    refresh_finder();
    emit changed();
}
void AssetsBridge::viewerEngine() {
    if (!viewEngine()) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral("Engine Tuner"), QStringLiteral("Select an enginespec config.txt first."));
        return;
    }
    emit engineRequested(
        preview_plain_,
        QFileInfo(path_).fileName() + QStringLiteral(" · ") +
            QString::fromStdString(assets_[static_cast<size_t>(finder_asset_)].kuid));
}
void AssetsBridge::applyEngineText(const QString& text) {
    view_editor_ = true;
    preview_plain_ = text;
    if (editor_document_) editor_document_->setPlainText(text);
    viewerSave();
}
void AssetsBridge::viewerFast() {
    const QString path = stage_selected_asset();
    if (path.isEmpty() || !QFileInfo::exists(path)) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Fast Preview"),
               QStringLiteral("The selected mesh could not be staged."));
        return;
    }
    if (!show_mesh_inline(path))
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Fast Preview"), QStringLiteral("The mesh could not be parsed."));
}
void AssetsBridge::viewerMesh() {
    const QString path = stage_selected_asset();
    if (path.isEmpty() || !QFileInfo::exists(path)) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Mesh Studio"), QStringLiteral("The selected mesh could not be staged."));
        return;
    }
    emit meshRequested(path);
}
void AssetsBridge::viewerReplace() {
    if (finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size()) || finder_asset_ < 0) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral("Replace"), QStringLiteral("Select a file in Finder."));
        return;
    }
    const FinderShown entry = shown_[static_cast<size_t>(finder_sel_)];
    if (entry.kind != QLatin1String("file") || entry.rel == QLatin1String("__config__")) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral("Replace"), QStringLiteral("Select a non-config file."));
        return;
    }
    const QString source = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Replace with file"), {}, QStringLiteral("All files (*.*)"));
    if (source.isEmpty()) return;
    QFile input(source);
    if (!input.open(QIODevice::ReadOnly)) return;
    const QByteArray replacement = input.readAll();
    AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    const CdpAssetEntry asset = item.assets[static_cast<size_t>(finder_asset_)];
    try {
        if (item.kind == QLatin1String("Folder")) {
            QFile output(QDir(QString::fromStdString(asset.username)).filePath(entry.rel));
            if (!output.open(QIODevice::WriteOnly | QIODevice::Truncate))
                throw std::runtime_error("cannot replace selected file");
            output.write(replacement);
            refresh_finder();
        } else {
            apply_edited_bytes(replace_cdp_file(
                bytes_.data(), bytes_.size(), asset.kuid, entry.rel.toStdString(),
                reinterpret_cast<const uint8_t*>(replacement.constData()), static_cast<size_t>(replacement.size())));
        }
    } catch (const std::exception& error) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Replace"), QString::fromUtf8(error.what()));
        return;
    }
    clear_preview();
    center_tip_ = QStringLiteral("Replaced ") + entry.rel + (item.kind == QLatin1String("Folder") ? QString() : QStringLiteral(" — use Save CDP."));
    emit changed();
}
void AssetsBridge::viewerDelete() {
    if (finder_sel_ < 0 || finder_sel_ >= static_cast<int>(shown_.size())) return;
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) return;
    const FinderShown entry = shown_[static_cast<size_t>(finder_sel_)];
    AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    if (item.kind == QLatin1String("Folder")) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral("Delete"), QStringLiteral("Disk mode does not delete source files."));
        return;
    }
    QList<RemoveRow> doomed;
    if (entry.kind == QLatin1String("asset")) {
        const CdpAssetEntry& asset = item.assets[static_cast<size_t>(entry.index)];
        for (size_t i = 0; i < asset.files.size(); ++i) {
            const QString rel = QString::fromStdString(asset.files[i]);
            doomed.push_back({QFileInfo(rel).fileName(), QFileInfo(rel).path() == QLatin1String(".") ? QString() : QFileInfo(rel).path(),
                              i < asset.sizes.size() ? static_cast<qint64>(asset.sizes[i]) : 0});
        }
    } else {
        doomed.push_back({entry.name, QFileInfo(entry.rel).path() == QLatin1String(".") ? QString() : QFileInfo(entry.rel).path(), entry.bytes});
    }
    if (!confirm_remove(QStringLiteral("Delete"),
            QStringLiteral("Remove <b>%1</b> from this CDP?").arg(entry.name.toHtmlEscaped()), doomed))
        return;
    try {
        if (entry.kind == QLatin1String("asset")) {
            const CdpAssetEntry asset = item.assets[static_cast<size_t>(entry.index)];
            finder_asset_ = -1;
            finder_parts_.clear();
            apply_edited_bytes(remove_cdp_asset(bytes_.data(), bytes_.size(), asset.kuid));
        } else {
            if (entry.rel == QLatin1String("__config__") || finder_asset_ < 0) return;
            const CdpAssetEntry asset = item.assets[static_cast<size_t>(finder_asset_)];
            apply_edited_bytes(remove_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, entry.rel.toStdString()));
        }
    } catch (const std::exception& error) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Delete"), QString::fromUtf8(error.what()));
        return;
    }
    clear_preview();
    center_tip_ = QStringLiteral("Removed ") + entry.name + QStringLiteral(" — use Save CDP.");
    emit changed();
}
void AssetsBridge::viewerSaveCdp() {
    if (view_editor_) {
        viewerSave();
        if (!last_edit_committed_) return;
    }
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size()) || bytes_.empty()) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral("Save CDP"), QStringLiteral("Open a CDP first."));
        return;
    }
    QString start = path_.isEmpty() ? QStringLiteral("edited.cdp") : path_;
    QString dest = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Save CDP"), start, QStringLiteral("Trainz CDP (*.cdp);;All files (*.*)"));
    if (dest.isEmpty()) return;
    if (!dest.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive)) dest += QStringLiteral(".cdp");
    QSaveFile file(dest);
    if (!file.open(QIODevice::WriteOnly)) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Save CDP"), QStringLiteral("Cannot write the selected path."));
        return;
    }
    const QByteArray output(reinterpret_cast<const char*>(bytes_.data()), static_cast<int>(bytes_.size()));
    if (file.write(output) != output.size() || !file.commit()) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral("Save CDP"), QStringLiteral("Writing the CDP failed."));
        return;
    }
    QFile verify(dest);
    if (!verify.open(QIODevice::ReadOnly) || verify.readAll() != output) {
        ui_box(QMessageBox::Critical, nullptr, QStringLiteral("Save CDP"), QStringLiteral("The saved CDP did not verify byte-for-byte."));
        return;
    }
    path_ = dest;
    queue_[static_cast<size_t>(queue_row_)].path = dest;
    cdp_dirty_ = false;
    refresh_queue();
    center_tip_ = QStringLiteral("Saved ") + QFileInfo(dest).fileName();
    post_status(center_tip_);
    emit changed();
}
void AssetsBridge::viewerDeleteFbx() {
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size()) || bytes_.empty()) return;
    const AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    QList<RemoveRow> doomed;
    for (const CdpAssetEntry& asset : item.assets)
        for (size_t i = 0; i < asset.files.size(); ++i) {
            const QString rel = QString::fromStdString(asset.files[i]);
            if (!rel.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) continue;
            const QString dir = QFileInfo(rel).path();
            doomed.push_back({QFileInfo(rel).fileName(), dir == QLatin1String(".") ? QString::fromStdString(asset.username) : QString::fromStdString(asset.username) + QLatin1Char('/') + dir,
                              i < asset.sizes.size() ? static_cast<qint64>(asset.sizes[i]) : 0});
        }
    const int count = static_cast<int>(doomed.size());
    if (count == 0) {
        ui_box(QMessageBox::Information, nullptr, QStringLiteral(".fbx"), QStringLiteral("No .fbx files were found."));
        return;
    }
    if (!confirm_remove(QStringLiteral("Delete all .fbx"),
            QStringLiteral("Remove <b>%1</b> .fbx file(s) from this CDP?").arg(count), doomed))
        return;
    try {
        std::vector<uint8_t> edited = bytes_;
        for (const CdpAssetEntry& asset : item.assets) {
            for (const std::string& rel : asset.files) {
                if (!QString::fromStdString(rel).endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) continue;
                edited = remove_cdp_file(edited.data(), edited.size(), asset.kuid, rel);
            }
        }
        apply_edited_bytes(std::move(edited));
    } catch (const std::exception& error) {
        ui_box(QMessageBox::Warning, nullptr, QStringLiteral(".fbx"), QString::fromUtf8(error.what()));
        return;
    }
    finder_fbx_ = true;
    clear_preview();
    refresh_finder();
    center_tip_ = QStringLiteral("Removed %1 .fbx file(s) — use Save CDP.").arg(count);
    emit changed();
}
void AssetsBridge::setFormTab(int tab) {
    if (tex_) tex_->set_form_tab(tab);
}
void AssetsBridge::setDockField(const QString& key, const QString& text) {
    if (tex_) tex_->set_field(key, text);
}
QStringList AssetsBridge::veContextPaths() const {
    QStringList out = suite_ == QLatin1String("texmesh") ? tex_->ve_paths() : QStringList();
    if (!config_path_.isEmpty() && QFileInfo(config_path_).isFile()) out << config_path_;
    return out;
}

void AssetsBridge::runDock(const QString& id) {
    if (suite_ == QLatin1String("texmesh") && tex_) tex_->run_action(id);
}

QString AssetsBridge::brand() const { return suite_ == QLatin1String("texmesh") ? QStringLiteral("Texture & Mesh Lods") : QStringLiteral("Assets Tools"); }
QString AssetsBridge::blurb() const {
    if (suite_ == QLatin1String("texmesh") && tex_) return tex_->blurb();
    if (page_ == QLatin1String("config")) return QStringLiteral("Edit config.chump as text, then save the binary or export config.txt.");
    if (page_ == QLatin1String("kuid")) return QStringLiteral("Paste CM text. Normalize writes the KUID, hex, and hash-XX folder.");
    if (page_ == QLatin1String("export")) return QStringLiteral("Paste KUIDs. Export each writes one CDP. Export one puts the checked rows in a single CDP.");
    return QStringLiteral("Left: drop CDP or a folder. Center: Finder. Right: preview.");
}
QString AssetsBridge::actionsJson() const {
    if (suite_ == QLatin1String("texmesh") && tex_) return tex_->actions_json();
    const auto row = [](const char* id, const char* label, bool accent) {
        return QJsonObject{{QStringLiteral("id"), QString::fromLatin1(id)}, {QStringLiteral("label"), QString::fromLatin1(label)}, {QStringLiteral("accent"), accent}};
    };
    QJsonArray rows;
    if (page_ == QLatin1String("config")) {
        rows = {row("open_chump", "Open config.chump", false), row("save_chump", "Save config.chump", true), row("export_txt", "Export config.txt", false)};
    } else if (page_ == QLatin1String("kuid")) {
        rows = {row("normalize", "Normalize list", true), row("copy_kuid", "Copy output", false)};
    } else if (page_ == QLatin1String("export")) {
        rows = {row("read_list", "Read list", true), row("export_each", "Export each", false), row("export_one", "Export one CDP", false)};
    }
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}
QString AssetsBridge::footerCap() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->footer_cap() : QStringLiteral("CDP / TZarc"); }
QString AssetsBridge::footNote() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->foot_note() : foot_note_; }
bool AssetsBridge::showQueue() const { return suite_ == QLatin1String("texmesh") ? page_ == QLatin1String("parameter") : page_ == QLatin1String("packages"); }
bool AssetsBridge::formOn() const { return suite_ == QLatin1String("texmesh") && tex_ && tex_->form_on(); }
QString AssetsBridge::formTitle() const { return formOn() ? tex_->form_title() : QString(); }
QString AssetsBridge::formTabs() const { return formOn() ? tex_->form_tabs() : QStringLiteral("[]"); }
int AssetsBridge::formTab() const { return formOn() ? tex_->form_tab() : 0; }
bool AssetsBridge::formTool() const { return formOn() && tex_->form_tool(); }
QString AssetsBridge::formBlocks() const { return formOn() ? tex_->form_blocks() : QStringLiteral("[]"); }
QString AssetsBridge::centerList() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->center_list() : QString(); }
QString AssetsBridge::centerPrev() const { return suite_ == QLatin1String("texmesh") && tex_ ? tex_->center_prev() : QString(); }

QString AssetsBridge::queueJson() const {
    QJsonArray rows;
    for (int i = 0; i < static_cast<int>(queue_.size()); ++i) {
        const AssetQueueItem& item = queue_[static_cast<size_t>(i)];
        rows.append(QJsonObject{
            {QStringLiteral("row"), i},
            {QStringLiteral("kind"), item.kind},
            {QStringLiteral("name"), QFileInfo(item.path).fileName()},
            {QStringLiteral("size"), item.size},
            {QStringLiteral("info"), item.info},
            {QStringLiteral("on"), i == queue_row_},
        });
    }
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::configText() const { return config_edit_ == nullptr ? QString() : config_edit_->toPlainText(); }
void AssetsBridge::setConfigText(const QString& text) {
    if (config_edit_ == nullptr || config_edit_->toPlainText() == text) return;
    config_edit_->setPlainText(text);
}
QString AssetsBridge::kuidIn() const { return kuid_in_ == nullptr ? QString() : kuid_in_->toPlainText(); }
void AssetsBridge::setKuidIn(const QString& text) {
    if (kuid_in_ == nullptr || kuid_in_->toPlainText() == text) return;
    kuid_in_->setPlainText(text);
}
QString AssetsBridge::kuidOut() const { return kuid_out_ == nullptr ? QString() : kuid_out_->toPlainText(); }
QString AssetsBridge::exportIn() const { return export_in_ == nullptr ? QString() : export_in_->toPlainText(); }
void AssetsBridge::setExportIn(const QString& text) {
    if (export_in_ == nullptr || export_in_->toPlainText() == text) return;
    export_in_->setPlainText(text);
}
QString AssetsBridge::exportJson() const {
    QJsonArray rows;
    if (export_table_ != nullptr) {
        for (int i = 0; i < export_table_->rowCount(); ++i) {
            QTableWidgetItem* check = export_table_->item(i, 0);
            QTableWidgetItem* kuid = export_table_->item(i, 1);
            QTableWidgetItem* status = export_table_->item(i, 2);
            rows.append(QJsonObject{
                {QStringLiteral("row"), i},
                {QStringLiteral("on"), check != nullptr && check->checkState() == Qt::Checked},
                {QStringLiteral("kuid"), kuid == nullptr ? QString() : kuid->text()},
                {QStringLiteral("status"), status == nullptr ? QString() : status->text()},
            });
        }
    }
    return QString::fromUtf8(QJsonDocument(rows).toJson(QJsonDocument::Compact));
}

QString AssetsBridge::tableJson() const { return suite_ == QLatin1String("texmesh") && tex_ != nullptr ? tex_->table_json() : QStringLiteral("[]"); }
QString AssetsBridge::paramQueueJson() const { return suite_ == QLatin1String("texmesh") && tex_ != nullptr ? tex_->queue_json() : QStringLiteral("[]"); }
QString AssetsBridge::wellLeft() const { return suite_ == QLatin1String("texmesh") && tex_ != nullptr ? tex_->well_left() : QString(); }
QString AssetsBridge::wellRight() const { return suite_ == QLatin1String("texmesh") && tex_ != nullptr ? tex_->well_right() : QString(); }

void AssetsBridge::dropCenter(const QStringList& paths) {
    if (suite_ == QLatin1String("texmesh") && tex_ != nullptr) tex_->drop_paths(paths);
}
void AssetsBridge::pickCenter(int row) {
    if (suite_ == QLatin1String("texmesh") && tex_ != nullptr) tex_->pick_row(row);
}
void AssetsBridge::setMeshLod(int row, bool on) {
    if (suite_ == QLatin1String("texmesh") && tex_ != nullptr) tex_->set_mesh_lod(row, on);
}
void AssetsBridge::setMeshWidth(int row, const QString& text) {
    if (suite_ == QLatin1String("texmesh") && tex_ != nullptr) tex_->set_mesh_width(row, text);
}

void AssetsBridge::dropPaths(const QStringList& paths) {
    QStringList local;
    for (const QString& path : paths) {
        const QUrl url(path);
        local << (url.isLocalFile() ? url.toLocalFile() : path);
    }
    add_paths(local);
}
void AssetsBridge::pickQueue(int row) {
    select_queue(row);
    emit changed();
}
void AssetsBridge::openFinder(int row) { enter_finder(row); }
void AssetsBridge::pickFinder(int row) { preview_file(row); }
void AssetsBridge::finderUp() {
    if (finder_fbx_) {
        finder_fbx_ = false;
    } else if (!finder_parts_.isEmpty()) {
        finder_parts_.removeLast();
    } else {
        finder_asset_ = -1;
    }
    clear_preview();
    refresh_finder();
    emit changed();
}
void AssetsBridge::jumpCrumb(int depth) {
    finder_fbx_ = false;
    if (depth <= 0) {
        finder_asset_ = -1;
        finder_parts_.clear();
    } else if (depth == 1) {
        finder_parts_.clear();
    } else {
        while (finder_parts_.size() > depth - 1) finder_parts_.removeLast();
    }
    clear_preview();
    refresh_finder();
    emit changed();
}
void AssetsBridge::toggleFbx() {
    finder_fbx_ = !finder_fbx_;
    finder_sel_ = -1;
    refresh_finder();
    emit changed();
}
void AssetsBridge::openFolder() {
    const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Open folder"));
    if (!dir.isEmpty()) add_paths({dir});
}
void AssetsBridge::setFinderQuery(const QString& text) {
    if (finder_filter_ == nullptr) return;
    finder_filter_->setText(text);
    emit changed();
}
void AssetsBridge::setFinderSort(const QString& column) {
    static const QStringList columns{QStringLiteral("name"), QStringLiteral("type"), QStringLiteral("size"), QStringLiteral("modified")};
    if (!columns.contains(column)) return;
    if (finder_sort_ == column) finder_sort_ascending_ = !finder_sort_ascending_;
    else {
        finder_sort_ = column;
        finder_sort_ascending_ = column != QLatin1String("modified");
    }
    refresh_finder();
    emit changed();
}

void AssetsBridge::place_widget(QWidget* widget, int x, int y, int w, int h, bool show) {
    if (widget == nullptr) return;
    if (!show || w < 8 || h < 8) {
        widget->hide();
        return;
    }
    widget->setAttribute(Qt::WA_NativeWindow, true);
    widget->setGeometry(x, y, w, h);
    widget->show();
    widget->raise();
}

void AssetsBridge::build_tools(QWidget* host) {
    auto* drop = new QueueDrop(host);
    drop->on_drop = [this](const QStringList& paths) { add_paths(paths); };
    prep_table(drop, {QStringLiteral("Kind"), QStringLiteral("Name"), QStringLiteral("Size"), QStringLiteral("Info")});
    drop->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    drop->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    drop->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    drop->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    queue_table_ = drop;
    connect(drop, &QTableWidget::itemSelectionChanged, this, [this] {
        if (queue_table_ != nullptr && queue_table_->currentRow() >= 0) select_queue(queue_table_->currentRow());
    });

    finder_page_ = new QWidget(host);
    auto* finder_lay = new QVBoxLayout(finder_page_);
    finder_lay->setContentsMargins(0, 0, 0, 0);
    finder_lay->setSpacing(8);
    auto* bar = new QHBoxLayout();
    finder_up_ = new QPushButton(QStringLiteral("Up"), finder_page_);
    auto* open_folder = new QPushButton(QStringLiteral("Open folder…"), finder_page_);
    finder_filter_ = new QLineEdit(finder_page_);
    finder_filter_->setPlaceholderText(QStringLiteral("Search this list…"));
    finder_up_->setFixedHeight(32);
    open_folder->setFixedHeight(32);
    finder_filter_->setFixedHeight(32);
    style_tool(finder_up_);
    style_tool(open_folder);
    style_tool(finder_filter_);
    bar->addWidget(finder_up_);
    bar->addWidget(open_folder);
    bar->addWidget(finder_filter_, 1);
    finder_lay->addLayout(bar);
    finder_table_ = new QTableWidget(finder_page_);
    prep_table(finder_table_, {QStringLiteral("Name"), QStringLiteral("Size")});
    finder_table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    finder_table_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Fixed);
    finder_table_->setColumnWidth(1, 108);
    finder_table_->verticalHeader()->setDefaultSectionSize(36);
    finder_lay->addWidget(finder_table_, 1);
    connect(finder_up_, &QPushButton::clicked, this, [this] {
        finder_asset_ = -1;
        finder_parts_.clear();
        refresh_finder();
    });
    connect(open_folder, &QPushButton::clicked, this, [this] {
        const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Open folder"));
        if (!dir.isEmpty()) add_paths({dir});
    });
    connect(finder_filter_, &QLineEdit::textChanged, this, [this] { refresh_finder(); });
    connect(finder_table_, &QTableWidget::itemSelectionChanged, this, [this] { preview_file(finder_table_->currentRow()); });
    connect(finder_table_, &QTableWidget::cellDoubleClicked, this, [this](int row, int) { enter_finder(row); });

    preview_ = new QStackedWidget(host);
    preview_empty_ = new QLabel(QStringLiteral("Select a file in Finder"), preview_);
    preview_empty_->setAlignment(Qt::AlignCenter);
    preview_empty_->setWordWrap(true);
    preview_text_ = new QPlainTextEdit(preview_);
    preview_text_->setReadOnly(true);
    preview_text_->setFont(QFont(QStringLiteral("Consolas"), 11));
    preview_image_ = new QLabel(preview_);
    preview_image_->setAlignment(Qt::AlignCenter);
    preview_->addWidget(preview_empty_);
    preview_->addWidget(preview_text_);
    preview_->addWidget(preview_image_);
    style_tool(preview_empty_);
    style_tool(preview_text_);
    style_tool(preview_image_);

    config_edit_ = new QPlainTextEdit(host);
    config_edit_->setPlaceholderText(QStringLiteral("Open config.chump — edit like config.txt\nusername  \"My Asset\"\nkind  \"traincar\"\nkuid  <kuid:1:2>"));
    config_edit_->setFont(QFont(QStringLiteral("Consolas"), 11));
    style_tool(config_edit_);

    kuid_page_ = new QWidget(host);
    auto* kuid_lay = new QVBoxLayout(kuid_page_);
    kuid_lay->setContentsMargins(0, 0, 0, 0);
    kuid_lay->setSpacing(8);
    kuid_in_ = new QPlainTextEdit(kuid_page_);
    kuid_in_->setPlaceholderText(QStringLiteral("Paste KUIDs or CM dependency text…"));
    kuid_out_ = new QPlainTextEdit(kuid_page_);
    kuid_out_->setReadOnly(true);
    kuid_out_->setPlaceholderText(QStringLiteral("Normalized / hash output…"));
    kuid_count_ = new QLabel(QStringLiteral("0 KUIDs"), kuid_page_);
    for (QWidget* widget : {static_cast<QWidget*>(kuid_in_), static_cast<QWidget*>(kuid_out_), static_cast<QWidget*>(kuid_count_)}) style_tool(widget);
    kuid_in_->setFont(QFont(QStringLiteral("Consolas"), 11));
    kuid_out_->setFont(QFont(QStringLiteral("Consolas"), 11));
    kuid_lay->addWidget(kuid_in_, 1);
    kuid_lay->addWidget(kuid_count_);
    kuid_lay->addWidget(kuid_out_, 1);

    export_page_ = new QWidget(host);
    auto* export_lay = new QVBoxLayout(export_page_);
    export_lay->setContentsMargins(0, 0, 0, 0);
    export_lay->setSpacing(8);
    export_in_ = new QPlainTextEdit(export_page_);
    export_in_->setPlaceholderText(QStringLiteral("<kuid:1125787:100058>, <kuid:1144998:100002>\n<kuid:972300:100075>"));
    export_in_->setFixedHeight(140);
    export_in_->setFont(QFont(QStringLiteral("Consolas"), 11));
    export_count_ = new QLabel(QStringLiteral("0 KUIDs"), export_page_);
    export_table_ = new QTableWidget(export_page_);
    prep_table(export_table_, {QString(), QStringLiteral("KUID"), QStringLiteral("Status")});
    export_table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Fixed);
    export_table_->setColumnWidth(0, 36);
    export_table_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    style_tool(export_in_);
    style_tool(export_count_);
    export_lay->addWidget(export_in_);
    export_lay->addWidget(export_count_);
    export_lay->addWidget(export_table_, 1);

    export_proc_ = new QProcess(this);
    connect(export_proc_, &QProcess::finished, this, [this](int, QProcess::ExitStatus) { finish_export(); });

    for (QWidget* widget : {static_cast<QWidget*>(queue_table_), static_cast<QWidget*>(finder_page_), static_cast<QWidget*>(preview_), static_cast<QWidget*>(config_edit_), static_cast<QWidget*>(kuid_page_), static_cast<QWidget*>(export_page_)}) widget->hide();
    view_title_ = QStringLiteral("Viewer");
    view_hint_ = QStringLiteral("Select a file in Finder");
    sync_pages();
}

void AssetsBridge::sync_pages() {
    const bool packages = suite_ != QLatin1String("texmesh") && page_ == QLatin1String("packages");
    viewer_on_ = packages;
    if (packages) {
        if (view_title_.isEmpty()) view_title_ = QStringLiteral("Viewer");
        if (view_hint_.isEmpty()) view_hint_ = QStringLiteral("Select a file in Finder");
        center_tip_ = queue_.empty() ? QStringLiteral("Drop a CDP or a folder on the left queue.") : QString::number(queue_.size()) + QStringLiteral(" in the queue. Double-click an asset to list its files.");
        foot_note_ = QStringLiteral("Drop a CDP or a folder on the left queue.");
        place_widget(queue_table_, 0, 0, 0, 0, false);
        place_widget(finder_page_, 0, 0, 0, 0, false);
        place_widget(preview_, 0, 0, 0, 0, false);
        place_widget(config_edit_, 0, 0, 0, 0, false);
        place_widget(kuid_page_, 0, 0, 0, 0, false);
        place_widget(export_page_, 0, 0, 0, 0, false);
        return;
    }
    place_widget(queue_table_, 0, 0, 0, 0, false);
    place_widget(finder_page_, 0, 0, 0, 0, false);
    place_widget(preview_, 0, 0, 0, 0, false);
    const bool assets = suite_ != QLatin1String("texmesh");
    place_widget(config_edit_, 0, 0, 0, 0, false);
    place_widget(kuid_page_, 0, 0, 0, 0, false);
    place_widget(export_page_, 0, 0, 0, 0, false);
    if (!assets) return;
    foot_note_ = QStringLiteral("Drop a CDP or a folder on the left queue.");
    if (page_ == QLatin1String("config")) center_tip_ = QStringLiteral("Open config.chump, edit the text, then save.");
    else if (page_ == QLatin1String("kuid")) center_tip_ = QStringLiteral("Paste CM text, then Normalize list.");
    else if (page_ == QLatin1String("export")) center_tip_ = QStringLiteral("Paste a KUID list. TrainzUtil createCDP writes the CDP.");
}

void AssetsBridge::add_paths(const QStringList& paths) {
    bool queued_folder = false;
    BusyToast busy(paths, QStringLiteral("Adding assets…"));
    int done = 0;
    for (const QString& raw : paths) {
        QFileInfo info(raw);
        busy.step(QStringLiteral("Reading ") + info.fileName() + QStringLiteral("…"), done++);
        if (info.isFile() && info.fileName().compare(QLatin1String("config.txt"), Qt::CaseInsensitive) == 0) info.setFile(info.dir().absolutePath());
        if (info.isDir()) {
            AssetQueueItem item;
            item.path = info.absoluteFilePath();
            item.kind = QStringLiteral("Folder");
            qint64 bytes = 0;
            QDirIterator it(item.path, QDir::Files, QDirIterator::Subdirectories);
            while (it.hasNext()) {
                it.next();
                bytes += it.fileInfo().size();
                if (it.fileName().compare(QLatin1String("config.txt"), Qt::CaseInsensitive) != 0) continue;
                CdpAssetEntry row;
                const QString dir = it.fileInfo().dir().absolutePath();
                row.username = dir.toStdString();
                row.kuid = it.fileInfo().dir().dirName().toStdString();
                row.kind = "folder";
                for (const QFileInfo& file : QDir(dir).entryInfoList(QDir::Files)) row.files.push_back(file.fileName().toStdString());
                item.assets.push_back(std::move(row));
            }
            item.size = bytes_label(bytes);
            item.info = QString::number(item.assets.size()) + QStringLiteral(" config.txt");
            queue_.push_back(std::move(item));
            queued_folder = true;
            continue;
        }
        const QString suffix = info.suffix().toLower();
        if (suffix != QLatin1String("cdp") && suffix != QLatin1String("tzarc") && suffix != QLatin1String("zip")) continue;
        QFile file(info.absoluteFilePath());
        if (!file.open(QIODevice::ReadOnly)) continue;
        load_bytes(file.readAll(), info.absoluteFilePath());
    }
    if (!queued_folder) return;
    refresh_queue();
    select_queue(static_cast<int>(queue_.size()) - 1);
    emit changed();
}

void AssetsBridge::refresh_queue() {
    if (queue_table_ == nullptr) return;
    queue_table_->blockSignals(true);
    queue_table_->setRowCount(0);
    for (int i = 0; i < static_cast<int>(queue_.size()); ++i) {
        const AssetQueueItem& item = queue_[static_cast<size_t>(i)];
        queue_table_->insertRow(i);
        queue_table_->setItem(i, 0, new QTableWidgetItem(item.kind));
        queue_table_->setItem(i, 1, new QTableWidgetItem(QFileInfo(item.path).fileName()));
        queue_table_->setItem(i, 2, new QTableWidgetItem(item.size));
        queue_table_->setItem(i, 3, new QTableWidgetItem(item.info));
    }
    if (queue_row_ >= 0 && queue_row_ < queue_table_->rowCount()) queue_table_->selectRow(queue_row_);
    queue_table_->blockSignals(false);
}

void AssetsBridge::select_queue(int row) {
    if (row < 0 || row >= static_cast<int>(queue_.size())) return;
    queue_row_ = row;
    finder_asset_ = -1;
    finder_parts_.clear();
    const AssetQueueItem& item = queue_[static_cast<size_t>(row)];
    bytes_.assign(item.bytes.begin(), item.bytes.end());
    assets_ = item.assets;
    path_ = item.path;
    center_tip_ = item.kind + QLatin1Char(' ') + QFileInfo(item.path).fileName() + QStringLiteral(" — ") + item.info;
    preview_body_.clear();
    preview_image_url_.clear();
    audioStop();
    preview_audio_ = false;
    preview_plain_.clear();
    preview_name_.clear();
    preview_on_ = false;
    preview_rich_ = false;
    view_editor_ = false;
    view_pane_ = 0;
    view_title_ = QStringLiteral("Viewer");
    refresh_finder();
    if (preview_ != nullptr) preview_->setCurrentWidget(preview_empty_);
    view_hint_ = QStringLiteral("Double-click an asset. Click a file to preview.");
}

void AssetsBridge::refresh_finder() {
    if (finder_table_ == nullptr) return;
    const QString filter = finder_filter_ == nullptr ? QString() : finder_filter_->text().trimmed().toLower();
    if (finder_up_ != nullptr) finder_up_->setEnabled(finder_asset_ >= 0 || finder_fbx_);
    QString selected_key;
    if (finder_sel_ >= 0 && finder_sel_ < static_cast<int>(shown_.size())) {
        const FinderShown& selected = shown_[static_cast<size_t>(finder_sel_)];
        selected_key = selected.kind + QLatin1Char('|') +
            (selected.rel.isEmpty() ? QString::number(selected.index) : selected.rel);
    }
    shown_.clear();
    finder_meta_.clear();
    crumbs_json_ = QStringLiteral("[]");
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) {
        finder_json_ = QStringLiteral("[]");
        if (finder_table_ != nullptr) finder_table_->setRowCount(0);
        return;
    }
    const AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    const QString pack = QFileInfo(item.path).fileName();
    const QDateTime package_modified = QFileInfo(item.path).lastModified();
    auto push = [&](FinderShown row) {
        const QString hay = (row.name + QLatin1Char(' ') + row.detail + QLatin1Char(' ') + row.rel).toLower();
        if (!filter.isEmpty() && !hay.contains(filter)) return;
        if (finder_fbx_ && !row.name.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) return;
        QString badge;
        QString color;
        QString detail = row.detail;
        finder_mark(row.kind, row.name, badge, color, detail);
        if (row.kind == QLatin1String("asset") && !row.detail.isEmpty()) detail = row.detail;
        row.badge = badge;
        row.color = color;
        row.detail = detail;
        row.type_label = row.kind == QLatin1String("asset")
            ? (row.detail.section(QStringLiteral(" · "), 0, 0).isEmpty() ? QStringLiteral("Asset") : row.detail.section(QStringLiteral(" · "), 0, 0))
            : (row.kind == QLatin1String("dir") ? QStringLiteral("Folder") : row.detail);
        if (!row.modified.isValid()) row.modified = package_modified;
        row.modified_label = row.modified.isValid()
            ? QLocale().toString(row.modified.toLocalTime(), QStringLiteral("d MMM yyyy, HH:mm"))
            : QStringLiteral("—");
        if (row.size_label.isEmpty()) row.size_label = bytes_label(row.bytes);
        shown_.push_back(std::move(row));
    };
    qint64 total = 0;
    if (finder_asset_ < 0) {
        for (int i = 0; i < static_cast<int>(item.assets.size()); ++i) {
            const CdpAssetEntry& asset = item.assets[static_cast<size_t>(i)];
            FinderShown row;
            row.kind = QStringLiteral("asset");
            row.index = i;
            row.name = QString::fromStdString(asset.username);
            if (item.kind == QLatin1String("Folder")) row.name = QFileInfo(row.name).fileName();
            if (row.name.isEmpty()) row.name = QString::fromStdString(asset.kuid);
            qint64 bytes = 0;
            for (uint64_t size : asset.sizes) bytes += static_cast<qint64>(size);
            row.bytes = bytes;
            total += bytes;
            QString kind = QString::fromStdString(asset.kind);
            row.detail = kind.isEmpty() ? QString::fromStdString(asset.kuid) : kind + QStringLiteral(" · ") + QString::fromStdString(asset.kuid);
            if (item.kind == QLatin1String("Folder")) row.modified = QFileInfo(QString::fromStdString(asset.username)).lastModified();
            push(std::move(row));
        }
        finder_meta_ = QString::number(item.assets.size()) + QStringLiteral(" asset(s) · ") + bytes_label(total);
        crumbs_json_ = QString::fromUtf8(QJsonDocument(QJsonArray{QJsonObject{{QStringLiteral("label"), pack}, {QStringLiteral("depth"), -1}, {QStringLiteral("hot"), true}}}).toJson(QJsonDocument::Compact));
    } else if (finder_asset_ < static_cast<int>(item.assets.size())) {
        const CdpAssetEntry& asset = item.assets[static_cast<size_t>(finder_asset_)];
        QString uname = QString::fromStdString(asset.username);
        if (uname.isEmpty()) uname = QString::fromStdString(asset.kuid);
        const QString prefix = finder_parts_.isEmpty() ? QString() : finder_parts_.join(QLatin1Char('/')) + QLatin1Char('/');
        if (!finder_fbx_ && finder_parts_.isEmpty()) {
            QString cfg;
            if (item.kind == QLatin1String("Folder")) {
                QFile config(QDir(QString::fromStdString(asset.username)).filePath(QStringLiteral("config.txt")));
                if (config.open(QIODevice::ReadOnly)) cfg = QString::fromUtf8(config.readAll());
            } else if (!bytes_.empty()) {
                cfg = QString::fromStdString(asset_config_text(bytes_.data(), bytes_.size(), asset.kuid));
            }
            FinderShown row;
            row.kind = QStringLiteral("file");
            row.index = -1;
            row.rel = QStringLiteral("__config__");
            row.name = QStringLiteral("config.txt");
            row.bytes = cfg.toUtf8().size();
            row.detail = QStringLiteral("Trainz config");
            if (item.kind == QLatin1String("Folder"))
                row.modified = QFileInfo(QDir(QString::fromStdString(asset.username)).filePath(QStringLiteral("config.txt"))).lastModified();
            total += row.bytes;
            push(std::move(row));
        }
        QMap<QString, qint64> folders;
        for (int i = 0; i < static_cast<int>(asset.files.size()); ++i) {
            QString rel = QString::fromStdString(asset.files[static_cast<size_t>(i)]);
            rel.replace(QLatin1Char('\\'), QLatin1Char('/'));
            if (finder_fbx_) {
                if (!rel.endsWith(QLatin1String(".fbx"), Qt::CaseInsensitive)) continue;
            } else {
                if (!rel.startsWith(prefix, Qt::CaseInsensitive)) continue;
                const QString rest = rel.mid(prefix.size());
                const int slash = rest.indexOf(QLatin1Char('/'));
                if (slash >= 0) {
                    qint64 size = i < static_cast<int>(asset.sizes.size())
                                      ? static_cast<qint64>(asset.sizes[static_cast<size_t>(i)])
                                      : 0;
                    folders[rest.left(slash)] += std::max<qint64>(0, size);
                    continue;
                }
            }
            FinderShown row;
            row.kind = QStringLiteral("file");
            row.index = i;
            row.rel = rel;
            row.name = QFileInfo(row.rel).fileName();
            if (row.name.isEmpty()) row.name = row.rel;
            if (i < static_cast<int>(asset.sizes.size())) row.bytes = static_cast<qint64>(asset.sizes[static_cast<size_t>(i)]);
            if (item.kind == QLatin1String("Folder")) {
                const QFileInfo info(QDir(QString::fromStdString(asset.username)).filePath(row.rel));
                if (info.exists()) {
                    row.bytes = info.size();
                    row.modified = info.lastModified();
                }
            }
            total += std::max<qint64>(0, row.bytes);
            push(std::move(row));
        }
        for (auto it = folders.cbegin(); it != folders.cend(); ++it) {
            FinderShown row;
            row.kind = QStringLiteral("dir");
            row.name = it.key();
            row.rel = prefix + it.key();
            row.bytes = it.value();
            row.detail = QStringLiteral("Folder");
            if (item.kind == QLatin1String("Folder"))
                row.modified = QFileInfo(QDir(QString::fromStdString(asset.username)).filePath(row.rel)).lastModified();
            total += row.bytes;
            push(std::move(row));
        }
        finder_meta_ = finder_fbx_
            ? QString::number(shown_.size()) + QStringLiteral(" × .fbx · ") + bytes_label(total)
            : QStringLiteral("This folder · ") + bytes_label(total);
        QJsonArray crumbs{
            QJsonObject{{QStringLiteral("label"), pack}, {QStringLiteral("depth"), 0}, {QStringLiteral("hot"), false}},
            QJsonObject{{QStringLiteral("label"), uname}, {QStringLiteral("depth"), finder_parts_.isEmpty() ? -1 : 1}, {QStringLiteral("hot"), finder_parts_.isEmpty()}},
        };
        for (int i = 0; i < finder_parts_.size(); ++i)
            crumbs.append(QJsonObject{
                {QStringLiteral("label"), finder_parts_[i]},
                {QStringLiteral("depth"), i + 1 == finder_parts_.size() ? -1 : i + 2},
                {QStringLiteral("hot"), i + 1 == finder_parts_.size()},
            });
        crumbs_json_ = QString::fromUtf8(QJsonDocument(crumbs).toJson(QJsonDocument::Compact));
    }
    std::stable_sort(shown_.begin(), shown_.end(), [this](const FinderShown& a, const FinderShown& b) {
        const auto folder = [](const FinderShown& row) {
            return row.kind == QLatin1String("dir") || row.kind == QLatin1String("asset");
        };
        const bool af = folder(a);
        const bool bf = folder(b);
        if (af != bf) return af;
        int order = 0;
        if (finder_sort_ == QLatin1String("size")) order = a.bytes < b.bytes ? -1 : (a.bytes > b.bytes ? 1 : 0);
        else if (finder_sort_ == QLatin1String("modified")) order = a.modified < b.modified ? -1 : (a.modified > b.modified ? 1 : 0);
        else {
            const QString av = finder_sort_ == QLatin1String("type") ? a.type_label : a.name;
            const QString bv = finder_sort_ == QLatin1String("type") ? b.type_label : b.name;
            order = av.compare(bv, Qt::CaseInsensitive);
        }
        if (order == 0) order = a.name.compare(b.name, Qt::CaseInsensitive);
        return finder_sort_ascending_ ? order < 0 : order > 0;
    });
    if (!selected_key.isEmpty()) {
        finder_sel_ = -1;
        for (int i = 0; i < static_cast<int>(shown_.size()); ++i) {
            const FinderShown& row = shown_[static_cast<size_t>(i)];
            const QString key = row.kind + QLatin1Char('|') + (row.rel.isEmpty() ? QString::number(row.index) : row.rel);
            if (key == selected_key) { finder_sel_ = i; break; }
        }
    }
    if (finder_sel_ >= static_cast<int>(shown_.size())) finder_sel_ = -1;
    bool any_folder = false;
    bool any_file = false;
    for (const FinderShown& row : shown_) {
        const bool folder = row.kind == QLatin1String("dir") || row.kind == QLatin1String("asset");
        any_folder = any_folder || folder;
        any_file = any_file || !folder;
    }
    const bool split_groups = any_folder && any_file;
    QJsonArray found;
    finder_table_->blockSignals(true);
    finder_table_->setRowCount(0);
    for (int i = 0; i < static_cast<int>(shown_.size()); ++i) {
        const FinderShown& row = shown_[static_cast<size_t>(i)];
        found.append(QJsonObject{
            {QStringLiteral("row"), i},
            {QStringLiteral("name"), row.name},
            {QStringLiteral("size"), row.size_label},
            {QStringLiteral("kind"), row.kind},
            {QStringLiteral("detail"), row.detail},
            {QStringLiteral("type"), row.type_label},
            {QStringLiteral("modified"), row.modified_label},
            {QStringLiteral("badge"), row.badge},
            {QStringLiteral("color"), row.color},
            {QStringLiteral("on"), i == finder_sel_},
            {QStringLiteral("dirty"), row.kind == QLatin1String("file") && dirty_text_.contains(edit_key(finder_asset_, row.rel))},
            {QStringLiteral("group"), split_groups
                ? ((row.kind == QLatin1String("dir") || row.kind == QLatin1String("asset"))
                    ? QStringLiteral("Folders")
                    : QStringLiteral("Files"))
                : QString()},
        });
        finder_table_->insertRow(i);
        auto* cell = new QTableWidgetItem(row.name);
        cell->setData(Qt::UserRole, row.kind);
        cell->setData(Qt::UserRole + 1, row.index);
        cell->setData(Qt::UserRole + 2, row.rel);
        finder_table_->setItem(i, 0, cell);
        auto* size_cell = new QTableWidgetItem(row.size_label);
        size_cell->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        finder_table_->setItem(i, 1, size_cell);
    }
    finder_table_->blockSignals(false);
    finder_json_ = QString::fromUtf8(QJsonDocument(found).toJson(QJsonDocument::Compact));
}

void AssetsBridge::enter_finder(int row) {
    if (row < 0 || row >= static_cast<int>(shown_.size())) return;
    const FinderShown& entry = shown_[static_cast<size_t>(row)];
    if (entry.kind == QLatin1String("dir")) {
        finder_parts_ << QFileInfo(entry.rel).fileName();
        finder_sel_ = -1;
        refresh_finder();
        emit changed();
        return;
    }
    if (entry.kind != QLatin1String("asset")) {
        preview_file(row);
        if (viewFast()) viewerFast(); // double-click a mesh = open the 3D preview
        return;
    }
    finder_asset_ = entry.index;
    finder_parts_.clear();
    finder_sel_ = -1;
    finder_fbx_ = false;
    refresh_finder();
    preview_body_.clear();
    preview_image_url_.clear();
    audioStop();
    preview_audio_ = false;
    preview_plain_.clear();
    preview_name_.clear();
    preview_on_ = false;
    preview_rich_ = false;
    view_editor_ = false;
    view_pane_ = 0;
    view_title_ = QStringLiteral("Viewer");
    view_hint_ = QStringLiteral("Click a file to preview it. Up returns to the asset list.");
    emit changed();
}

void AssetsBridge::preview_file(int row) {
    if (row < 0 || row >= static_cast<int>(shown_.size())) return;
    mesh_on_ = false;
    sync_mesh_view();
    finder_sel_ = row;
    const FinderShown entry = shown_[static_cast<size_t>(row)];
    refresh_finder();
    if (entry.kind != QLatin1String("file")) {
        emit changed();
        return;
    }
    if (queue_row_ < 0 || queue_row_ >= static_cast<int>(queue_.size())) return;
    const AssetQueueItem& item = queue_[static_cast<size_t>(queue_row_)];
    if (finder_asset_ < 0 || finder_asset_ >= static_cast<int>(item.assets.size())) return;
    const CdpAssetEntry& asset = item.assets[static_cast<size_t>(finder_asset_)];
    QByteArray data;
    QString shown = entry.name;
    if (entry.rel == QLatin1String("__config__")) {
        if (item.kind == QLatin1String("Folder")) {
            QFile file(QDir(QString::fromStdString(asset.username)).filePath(QStringLiteral("config.txt")));
            if (file.open(QIODevice::ReadOnly)) data = file.readAll();
        } else if (!bytes_.empty()) {
            data = QByteArray::fromStdString(asset_config_text(bytes_.data(), bytes_.size(), asset.kuid));
        }
    } else if (item.kind == QLatin1String("Folder")) {
        QFile file(QDir(QString::fromStdString(asset.username)).filePath(entry.rel));
        if (file.open(QIODevice::ReadOnly)) data = file.readAll();
    } else if (item.kind == QLatin1String("TZarc")) {
        data = tzarc_text_.toUtf8();
    } else {
        try {
            const auto raw = read_cdp_file(bytes_.data(), bytes_.size(), asset.kuid, entry.rel.toStdString());
            data = QByteArray(reinterpret_cast<const char*>(raw.data()), static_cast<int>(raw.size()));
        } catch (const std::exception& error) {
            preview_plain_.clear();
            preview_name_ = shown;
            preview_body_ = html_escape(QString::fromUtf8(error.what()));
            preview_on_ = true;
            preview_rich_ = false;
            view_editor_ = false;
            view_pane_ = 0;
            view_title_ = QStringLiteral("Viewer — ") + shown;
            view_hint_.clear();
            emit changed();
            return;
        }
    }
    preview_name_ = shown;
    preview_image_url_.clear();
    audioStop();
    preview_audio_ = false;
    view_hint_.clear();
    const QString suffix = QFileInfo(entry.rel == QLatin1String("__config__") ? shown : entry.rel).suffix().toLower();
    if (suffix == QLatin1String("chump") || entry.rel.endsWith(QLatin1String("config.chump"), Qt::CaseInsensitive)) {
        try {
            const ChumpFile chump = read_chump(reinterpret_cast<const uint8_t*>(data.constData()), static_cast<size_t>(data.size()));
            data = QByteArray::fromStdString(chump_to_text(chump));
        } catch (const std::exception&) {
        }
    }
    const QStringList audio_suffixes{
        QStringLiteral("wav"), QStringLiteral("mp3"), QStringLiteral("ogg"),
        QStringLiteral("flac"), QStringLiteral("m4a"), QStringLiteral("aiff"), QStringLiteral("aif")};
    if (audio_suffixes.contains(suffix)) {
        const QString dir = QDir(QStandardPaths::writableLocation(QStandardPaths::TempLocation))
                                .filePath(QStringLiteral("mstn-trainz-studio/audio"));
        QDir().mkpath(dir);
        preview_audio_path_ = QDir(dir).filePath(QStringLiteral("preview.") + suffix);
        QFile audio(preview_audio_path_);
        if (audio.open(QIODevice::WriteOnly | QIODevice::Truncate)) audio.write(data);
        preview_body_ = shown + QStringLiteral("\nAudio (") + suffix.toUpper() +
                        QStringLiteral(") · ") + bytes_label(data.size());
        preview_on_ = true;
        preview_rich_ = false;
        view_editor_ = false;
        view_pane_ = 0;
        view_title_ = QStringLiteral("Viewer — ") + shown;
        preview_audio_ = true;
        emit changed();
        return;
    }
    QPixmap picture;
    if (picture.loadFromData(data) && !picture.isNull()) {
        QString mime = QStringLiteral("image/") + suffix;
        if (suffix == QLatin1String("jpg")) mime = QStringLiteral("image/jpeg");
        preview_image_url_ = QStringLiteral("data:") + mime + QStringLiteral(";base64,") +
                             QString::fromLatin1(data.toBase64());
        preview_plain_.clear();
        preview_body_ = QStringLiteral("Image  ") + shown + QStringLiteral("  ") + bytes_label(data.size());
        preview_on_ = true;
        preview_rich_ = false;
        view_editor_ = false;
        view_pane_ = 0;
        view_title_ = QStringLiteral("Viewer — ") + shown;
        if (preview_text_ != nullptr) preview_text_->setPlainText(preview_body_);
        if (preview_image_ != nullptr) preview_image_->setPixmap(picture);
        if (preview_ != nullptr) preview_->setCurrentWidget(preview_image_);
        emit changed();
        return;
    }
    if (data.left(4096).contains('\0')) {
        // Binary (fbx / trainzmesh / ...): garbled text is useless, point at the 3D preview instead.
        preview_plain_.clear();
        preview_body_ = shown + QStringLiteral("\nBinary · ") + bytes_label(data.size()) +
                        (viewFast() ? QStringLiteral("\n\nDouble-click to open in 3D preview.") : QString());
        preview_on_ = true;
        preview_rich_ = false;
        view_editor_ = false;
        view_pane_ = 0;
        view_title_ = QStringLiteral("Viewer — ") + shown;
        emit changed();
        return;
    }
    current_edit_key_ = edit_key(finder_asset_, entry.rel);
    QString plain = QString::fromUtf8(data);
    if (dirty_text_.contains(current_edit_key_)) plain = dirty_text_.value(current_edit_key_);
    else saved_baseline_.insert(current_edit_key_, plain);
    preview_plain_ = plain;
    view_editor_ = true;
    preview_on_ = true;
    preview_body_.clear();
    preview_rich_ = false;
    view_title_ = (view_pane_ == 1 ? QStringLiteral("Editor — ") : QStringLiteral("Viewer — ")) + shown;
    if (preview_text_ != nullptr) {
        preview_text_->setPlainText(plain);
        if (preview_ != nullptr) preview_->setCurrentWidget(preview_text_);
    }
    emit changed();
}

void AssetsBridge::read_kuid_list() {
    if (page_ == QLatin1String("export")) {
        if (export_in_ == nullptr || export_table_ == nullptr) return;
        const QStringList kuids = extract_kuids(export_in_->toPlainText());
        export_table_->setRowCount(0);
        for (int i = 0; i < kuids.size(); ++i) {
            export_table_->insertRow(i);
            auto* check = new QTableWidgetItem();
            check->setFlags(Qt::ItemIsUserCheckable | Qt::ItemIsEnabled | Qt::ItemIsSelectable);
            check->setCheckState(Qt::Checked);
            export_table_->setItem(i, 0, check);
            export_table_->setItem(i, 1, new QTableWidgetItem(kuids[i]));
            export_table_->setItem(i, 2, new QTableWidgetItem(QStringLiteral("—")));
        }
        if (export_count_ != nullptr) export_count_->setText(QString::number(kuids.size()) + (kuids.size() == 1 ? QStringLiteral(" KUID") : QStringLiteral(" KUIDs")));
        center_tip_ = export_count_ == nullptr ? QString() : export_count_->text();
        return;
    }
    if (kuid_in_ == nullptr || kuid_out_ == nullptr) return;
    const QStringList kuids = extract_kuids(kuid_in_->toPlainText());
    QString out;
    for (const QString& kuid : kuids) {
        out += kuid + QLatin1Char('\n');
        const auto raw = parse_kuid_string(kuid.toStdString());
        if (!raw) {
            out += QStringLiteral("  bad kuid\n");
            continue;
        }
        QString hex;
        for (uint8_t byte : *raw) hex += QStringLiteral("%1").arg(byte, 2, 16, QLatin1Char('0'));
        out += QStringLiteral("  hex:  ") + hex + QLatin1Char('\n');
        out += QStringLiteral("  map:  ") + QString::fromStdString(hash_folder(raw->data(), raw->size())) + QLatin1Char('\n');
    }
    if (kuids.isEmpty()) out = QStringLiteral("No KUID found\n");
    kuid_out_->setPlainText(out);
    if (kuid_count_ != nullptr) kuid_count_->setText(QString::number(kuids.size()) + (kuids.size() == 1 ? QStringLiteral(" KUID") : QStringLiteral(" KUIDs")));
    center_tip_ = kuid_count_ == nullptr ? QString() : kuid_count_->text();
}

void AssetsBridge::start_export(bool one_file) {
    if (export_proc_ != nullptr && export_proc_->state() != QProcess::NotRunning) {
        center_tip_ = QStringLiteral("Export is still running");
        emit changed();
        return;
    }
    if (export_table_ == nullptr || export_table_->rowCount() == 0) read_kuid_list();
    QStringList kuids;
    QList<int> rows;
    if (export_table_ != nullptr) {
        for (int i = 0; i < export_table_->rowCount(); ++i) {
            QTableWidgetItem* check = export_table_->item(i, 0);
            QTableWidgetItem* kuid = export_table_->item(i, 1);
            if (check == nullptr || kuid == nullptr || check->checkState() != Qt::Checked) continue;
            kuids << kuid->text();
            rows << i;
        }
    }
    if (kuids.isEmpty()) {
        center_tip_ = QStringLiteral("Read a list and check at least one KUID");
        emit changed();
        return;
    }
    export_exe_ = find_trainzutil(QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).value(QStringLiteral("trainzutil/exe")).toString());
    if (export_exe_.isEmpty()) {
        center_tip_ = QStringLiteral("TrainzUtil.exe not found — set it on the TrainzUtil page");
        emit changed();
        return;
    }
    export_dest_.clear();
    export_kuids_.clear();
    export_rows_.clear();
    if (one_file) {
        const QString dest = QFileDialog::getSaveFileName(nullptr, QStringLiteral("One CDP for the checked assets"), QStringLiteral("assets.cdp"), QStringLiteral("CDP (*.cdp)"));
        if (dest.isEmpty()) return;
        export_dest_ << (dest.endsWith(QLatin1String(".cdp"), Qt::CaseInsensitive) ? dest : dest + QStringLiteral(".cdp"));
        export_kuids_ << kuids;
        export_rows_ << rows.value(0);
    } else {
        const QString dir = QFileDialog::getExistingDirectory(nullptr, QStringLiteral("Folder for one CDP per asset"));
        if (dir.isEmpty()) return;
        for (int i = 0; i < kuids.size(); ++i) {
            export_dest_ << QDir(dir).filePath(cdp_filename(kuids[i]));
            export_kuids_ << QStringList{kuids[i]};
            export_rows_ << rows[i];
        }
    }
    export_at_ = 0;
    const QString dest = export_dest_.first();
    QDir().mkpath(QFileInfo(dest).absolutePath());
    QFile::remove(dest);
    center_tip_ = QStringLiteral("createCDP ") + QFileInfo(dest).fileName();
    emit changed();
    export_proc_->start(export_exe_, QStringList{QStringLiteral("createCDP"), dest} + export_kuids_.first());
}

void AssetsBridge::finish_export() {
    if (export_at_ < 0 || export_at_ >= export_dest_.size()) return;
    const QString dest = export_dest_[export_at_];
    const QString log = QString::fromLocal8Bit(export_proc_->readAllStandardOutput() + export_proc_->readAllStandardError());
    const bool ok = QFileInfo(dest).size() > 0 && log.contains(QStringLiteral("0 Errors"));
    const QString status = ok ? QStringLiteral("Wrote ") + QFileInfo(dest).fileName() : QStringLiteral("createCDP failed");
    post_status(ok ? status : status + QStringLiteral(" — ") + QFileInfo(dest).fileName());
    const int row = export_rows_.value(export_at_);
    if (export_table_ != nullptr) {
        if (export_kuids_.value(export_at_).size() > 1) {
            for (int i = 0; i < export_table_->rowCount(); ++i) {
                if (export_table_->item(i, 2) != nullptr) export_table_->item(i, 2)->setText(status);
            }
        } else if (row >= 0 && row < export_table_->rowCount() && export_table_->item(row, 2) != nullptr) {
            export_table_->item(row, 2)->setText(status);
        }
    }
    ++export_at_;
    if (export_at_ >= export_dest_.size()) {
        center_tip_ = QStringLiteral("Export finished");
        emit changed();
        return;
    }
    const QString next = export_dest_[export_at_];
    QDir().mkpath(QFileInfo(next).absolutePath());
    QFile::remove(next);
    center_tip_ = QStringLiteral("createCDP ") + QFileInfo(next).fileName();
    emit changed();
    export_proc_->start(export_exe_, QStringList{QStringLiteral("createCDP"), next} + export_kuids_[export_at_]);
}

AssetsPage::AssetsPage(QWidget* parent) : QWidget(parent) {
    bridge_ = new AssetsBridge(this);
    connect(bridge_, &AssetsBridge::homeRequested, this, &AssetsPage::homeRequested);
    connect(bridge_, &AssetsBridge::meshRequested, this, &AssetsPage::meshRequested);
    connect(bridge_, &AssetsBridge::engineRequested, this, &AssetsPage::engineRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setAttribute(Qt::WA_AlwaysStackOnTop, true);
    view_->setSource(res_url(qml_dir() + QStringLiteral("/AssetsPage.qml")));
    view_->raise();
}

void AssetsPage::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    if (view_) {
        view_->setGeometry(rect());
        view_->raise();
    }
}

bool AssetsPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList AssetsPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void AssetsPage::loadBytes(const QByteArray& bytes, const QString& path) { bridge_->load_bytes(bytes, path); }
int AssetsPage::assetCount() const { return bridge_->asset_count(); }
QString AssetsPage::cell(int row, int column) const { return bridge_->cell(row, column); }
QString AssetsPage::fileText(int asset, const QString& rel) const { return bridge_->file_text(asset, rel); }
int AssetsPage::extractTo(const QString& directory) const { return bridge_->extract_to(directory); }
QString AssetsPage::pageName() const { return bridge_->page(); }
bool AssetsPage::formOn() const { return bridge_->formOn(); }
QString AssetsPage::centerList() const { return bridge_->centerList(); }
void AssetsPage::setPage(const QString& page) { bridge_->setPage(page); }
void AssetsPage::openPaths(const QStringList& paths) { bridge_->dropPaths(paths); }
void AssetsPage::setSuite(const QString& suite) { bridge_->set_suite(suite); }
void AssetsPage::applyEngineText(const QString& text) {
    bridge_->applyEngineText(text);
}
