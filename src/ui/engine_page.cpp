#include "engine_page.h"
#include "res_path.h"

#include "shell_window.h"

#include <algorithm>

#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlContext>
#include <QQmlError>
#include <QQuickWidget>
#include <QVBoxLayout>

namespace {

const char* kColors[] = {"#94a3b8", "#22c55e", "#84cc16", "#eab308", "#f59e0b", "#f97316", "#ef4444", "#ec4899", "#a855f7"};

QString qml_dir() {
return res_qml_dir();
}

bool parse_num(const QString& text, double& out) {
    bool ok = false;
    const double value = text.trimmed().replace(QLatin1Char(','), QString()).toDouble(&ok);
    if (!ok) return false;
    out = value;
    return true;
}

}  // namespace

EngineBridge::EngineBridge(QObject* parent) : QObject(parent) { refresh(); }

void EngineBridge::load_text(const QString& text, const QString& path) {
    spec_ = parse_enginespec(text.toStdString());
    spec_.path = path.toStdString();
    cdp_session_ = false;
    undo_.clear();
    redo_.clear();
    refresh();
}
QStringList EngineBridge::veContextPaths() const {
    const QString path = QString::fromStdString(spec_.path);
    return path.isEmpty() ? QStringList() : QStringList{path, QFileInfo(path).absolutePath()};
}

void EngineBridge::load_cdp_text(const QString& text) {
    spec_ = parse_enginespec(text.toStdString());
    spec_.path.clear();
    cdp_session_ = true;
    undo_.clear();
    redo_.clear();
    refresh();
}

QString EngineBridge::spec_text() const { return QString::fromStdString(write_enginespec(spec_)); }

void EngineBridge::refresh() {
    QJsonArray notches;
    for (int notch = 0; notch <= 8; ++notch) {
        QJsonArray points;
        const auto it = spec_.throttle.find(notch);
        if (it != spec_.throttle.end()) {
            for (const auto& point : it->second) {
                points.append(QJsonObject{
                    {QStringLiteral("kmh"), QString::fromStdString(fmt_kmh(point.first))},
                    {QStringLiteral("kn"), QString::fromStdString(fmt_kn(point.second))},
                });
            }
        }
        notches.append(QJsonObject{
            {QStringLiteral("n"), notch},
            {QStringLiteral("color"), QString::fromLatin1(kColors[notch])},
            {QStringLiteral("pts"), points},
        });
    }
    const auto rows = [](const std::map<std::string, double>* block) {
        QJsonArray out;
        if (!block) return out;
        for (const auto& [key, value] : *block) {
            out.append(QJsonObject{
                {QStringLiteral("k"), QString::fromStdString(key)},
                {QStringLiteral("v"), QString::fromStdString(fmt_native(value))},
            });
        }
        return out;
    };
    QJsonArray pressure;
    if (const auto* block = spec_.find_block("pressure")) {
        for (const auto& [key, value] : *block) {
            pressure.append(QJsonObject{
                {QStringLiteral("k"), QString::fromStdString(key)},
                {QStringLiteral("native"), QString::fromStdString(fmt_native(value))},
                {QStringLiteral("bar"), QString::fromStdString(fmt_bar(value))},
                {QStringLiteral("kpa"), QString::fromStdString(fmt_kpa(value))},
            });
        }
    }
    const QJsonObject bag{
        {QStringLiteral("path"), QString::fromStdString(spec_.path)},
        {QStringLiteral("resist"), resist_},
        {QStringLiteral("maxKmh"), max_kmh_},
        {QStringLiteral("maxKn"), max_kn_},
        {QStringLiteral("notches"), notches},
        {QStringLiteral("sim"),
         QJsonObject{
             {QStringLiteral("mass"), sim_[QStringLiteral("mass")]},
             {QStringLiteral("motors"), sim_[QStringLiteral("motors")]},
             {QStringLiteral("grade"), sim_[QStringLiteral("grade")]},
             {QStringLiteral("duration"), sim_[QStringLiteral("duration")]},
             {QStringLiteral("notch"), sim_[QStringLiteral("notch")]},
             {QStringLiteral("brake"), sim_[QStringLiteral("brake")]},
             {QStringLiteral("emergency"), sim_[QStringLiteral("emergency")]},
             {QStringLiteral("stats"), sim_[QStringLiteral("stats")]},
         }},
        {QStringLiteral("bags"),
         QJsonObject{
             {QStringLiteral("motor"), rows(spec_.find_block("motor"))},
             {QStringLiteral("mass"), rows(spec_.find_block("mass"))},
             {QStringLiteral("flowsize"), rows(spec_.find_block("flowsize"))},
             {QStringLiteral("volume"), rows(spec_.find_block("volume"))},
         }},
        {QStringLiteral("pressure"), pressure},
    };
    center_json_ = QString::fromUtf8(QJsonDocument(bag).toJson(QJsonDocument::Compact));
    emit changed();
}

void EngineBridge::push_undo() {
    undo_.push_back(spec_);
    if (undo_.size() > 32) undo_.erase(undo_.begin());
    redo_.clear();
}

std::map<std::string, double>* EngineBridge::bag(const QString& name) {
    const std::string key = name.toStdString();
    if (key != "motor" && key != "mass" && key != "flowsize" && key != "volume" && key != "pressure") return nullptr;
    return &spec_.block(key);
}

void EngineBridge::setPage(const QString& page) {
    page_ = page;
    emit changed();
}

void EngineBridge::goHome() { emit homeRequested(); }
void EngineBridge::toggleAuto() {
    auto_on_ = !auto_on_;
    emit changed();
}
void EngineBridge::setSideW(double width) {
    const int next = std::max(280, std::min(520, static_cast<int>(width)));
    if (next == side_w_) return;
    side_w_ = next;
    emit layoutChanged();
}
void EngineBridge::setCloneFrom(int notch) {
    clone_from_ = std::max(0, std::min(8, notch));
    emit changed();
}
void EngineBridge::toggleTarget(int notch) {
    if (notch < 0 || notch > 8) return;
    targets_ ^= 1 << notch;
    emit changed();
}
void EngineBridge::openFile() {
    const QString path = QFileDialog::getOpenFileName(nullptr, QStringLiteral("Open enginespec"), {}, QStringLiteral("enginespec (*.txt);;All (*.*)"));
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return;
    load_text(QString::fromUtf8(file.readAll()), path);
}
void EngineBridge::saveFile() {
    if (cdp_session_) {
        emit cdpSaveRequested(spec_text());
        return;
    }
    if (spec_.path.empty()) return;
    QFile file(QString::fromStdString(spec_.path));
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return;
    file.write(spec_text().toUtf8());
}
void EngineBridge::saveFileAs() {
    const QString path = QFileDialog::getSaveFileName(nullptr, QStringLiteral("Save enginespec"), {}, QStringLiteral("enginespec (*.txt)"));
    if (path.isEmpty()) return;
    spec_.path = path.toStdString();
    saveFile();
    refresh();
}
void EngineBridge::undoEdit() {
    if (undo_.empty()) return;
    redo_.push_back(spec_);
    spec_ = undo_.back();
    undo_.pop_back();
    refresh();
}
void EngineBridge::redoEdit() {
    if (redo_.empty()) return;
    undo_.push_back(spec_);
    spec_ = redo_.back();
    redo_.pop_back();
    refresh();
}
void EngineBridge::goBack() { emit homeRequested(); }

void EngineBridge::doClone() {
    const auto src = spec_.throttle.find(clone_from_);
    if (src == spec_.throttle.end()) return;
    push_undo();
    for (int notch = 0; notch <= 8; ++notch) {
        if (notch == clone_from_ || (targets_ & (1 << notch)) == 0) continue;
        spec_.throttle[notch] = src->second;
    }
    refresh();
}

void EngineBridge::doCloneHigher() {
    const auto src = spec_.throttle.find(clone_from_);
    if (src == spec_.throttle.end() || clone_from_ >= 8) return;
    push_undo();
    for (int notch = clone_from_ + 1; notch <= 8; ++notch) spec_.throttle[notch] = src->second;
    refresh();
}

void EngineBridge::editPoint(int notch, int index, int column, const QString& text) {
    push_undo();
    if (!edit_throttle_point(spec_, notch, index, column, text.toStdString())) {
        undo_.pop_back();
        return;
    }
    notch_focus_ = notch;
    refresh();
}

void EngineBridge::addPoint(int notch) {
    push_undo();
    add_throttle_point(spec_, notch);
    notch_focus_ = notch;
    refresh();
}

void EngineBridge::delPoint(int notch, int index) {
    push_undo();
    delete_throttle_point(spec_, notch, index);
    notch_focus_ = notch;
    refresh();
}

void EngineBridge::movePoint(int notch, int from, int to) {
    auto it = spec_.throttle.find(notch);
    if (it == spec_.throttle.end()) return;
    auto& points = it->second;
    if (from < 0 || to < 0 || from >= static_cast<int>(points.size()) || to >= static_cast<int>(points.size())) return;
    push_undo();
    std::swap(points[static_cast<size_t>(from)], points[static_cast<size_t>(to)]);
    std::sort(points.begin(), points.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    notch_focus_ = notch;
    refresh();
}

void EngineBridge::focusNotch(int notch) {
    notch_focus_ = notch;
    emit changed();
}

void EngineBridge::setResist(bool on) {
    resist_ = on;
    refresh();
}
void EngineBridge::setGraphMax(const QString& kmh, const QString& kn) {
    max_kmh_ = kmh;
    max_kn_ = kn;
    refresh();
}
void EngineBridge::fitGraph() {}
void EngineBridge::placeGraph(double, double, double, double) {}

void EngineBridge::setSim(const QString& key, const QString& text) {
    sim_[key] = text;
    refresh();
}

void EngineBridge::runSim() {
    sim_[QStringLiteral("stats")] = QStringLiteral("not in this build");
    refresh();
}

void EngineBridge::editParam(const QString& bag_name, const QString& key, int column, const QString& text) {
    auto* rows = bag(bag_name);
    if (!rows) return;
    const std::string name = key.toStdString();
    if (column == 0) {
        if (text.trimmed().isEmpty() || rows->find(name) == rows->end()) return;
        push_undo();
        const double value = (*rows)[name];
        rows->erase(name);
        (*rows)[text.trimmed().toStdString()] = value;
        refresh();
        return;
    }
    double value = 0;
    if (!parse_num(text, value) || rows->find(name) == rows->end()) return;
    push_undo();
    (*rows)[name] = value;
    refresh();
}

void EngineBridge::addParam(const QString& bag_name) {
    auto* rows = bag(bag_name);
    if (!rows) return;
    push_undo();
    std::string key = "new";
    for (int n = 2; rows->count(key); ++n) key = "new" + std::to_string(n);
    (*rows)[key] = 0;
    refresh();
}

void EngineBridge::delParam(const QString& bag_name, const QString& key) {
    auto* rows = bag(bag_name);
    if (!rows || rows->find(key.toStdString()) == rows->end()) return;
    push_undo();
    rows->erase(key.toStdString());
    refresh();
}

void EngineBridge::editPressure(const QString& key, int column, const QString& text) {
    auto* rows = bag(QStringLiteral("pressure"));
    if (!rows) return;
    const std::string name = key.toStdString();
    if (column == 0) {
        editParam(QStringLiteral("pressure"), key, 0, text);
        return;
    }
    double value = 0;
    if (!parse_num(text, value) || rows->find(name) == rows->end()) return;
    if (column == 2) value = native_from_bar(value);
    else if (column == 3) value = native_from_kpa(value);
    else if (column != 1) return;
    push_undo();
    (*rows)[name] = value;
    refresh();
}

void EngineBridge::addPressure() { addParam(QStringLiteral("pressure")); }
void EngineBridge::delPressure(const QString& key) { delParam(QStringLiteral("pressure"), key); }

void EngineBridge::setAutoTab(int tab) {
    auto_tab_ = tab;
    emit changed();
}
void EngineBridge::setAutoField(const QString&, const QString&) {}
void EngineBridge::previewAuto() {}
void EngineBridge::applyAuto() {}
void EngineBridge::cyclePowerUnit() {}
void EngineBridge::cyclePressUnit() {}
void EngineBridge::presetAir() {}

EngineTunerPage::EngineTunerPage(QWidget* parent) : QWidget(parent) {
    bridge_ = new EngineBridge(this);
    connect(bridge_, &EngineBridge::homeRequested, this, &EngineTunerPage::homeRequested);
    connect(bridge_, &EngineBridge::cdpSaveRequested, this, &EngineTunerPage::cdpSaveRequested);
    view_ = new QQuickWidget(this);
    view_->setResizeMode(QQuickWidget::SizeRootObjectToView);
    view_->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge_);
    view_->engine()->addImageProvider(QStringLiteral("mstnlogo"), new LogoProvider());
    view_->setClearColor(QColor(QStringLiteral("#12161c")));
    view_->setSource(res_url(qml_dir() + QStringLiteral("/EnginePage.qml")));
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addWidget(view_);
}

bool EngineTunerPage::qmlReady() const { return view_ && view_->status() == QQuickWidget::Ready; }

QStringList EngineTunerPage::qmlErrors() const {
    QStringList lines;
    if (!view_) return lines;
    for (const QQmlError& error : view_->errors()) lines << error.toString();
    return lines;
}

void EngineTunerPage::loadText(const QString& text) { bridge_->load_text(text); }
void EngineTunerPage::loadCdpText(const QString& text) { bridge_->load_cdp_text(text); }
QString EngineTunerPage::centerJson() const { return bridge_->centerJson(); }
QString EngineTunerPage::specText() const { return bridge_->spec_text(); }
bool EngineTunerPage::cdpSession() const { return bridge_->cdpSession(); }
QString EngineTunerPage::pageName() const { return bridge_->page(); }
void EngineTunerPage::editPoint(int notch, int index, int column, const QString& text) { bridge_->editPoint(notch, index, column, text); }
void EngineTunerPage::setPage(const QString& page) { bridge_->setPage(page); }
