#include "ui/status_hub.h"

#include <QDateTime>
#include <QFileInfo>
#include <QRegularExpression>
#include <QTimer>
#include <QUrl>
#include <QWidget>

namespace {

constexpr int kLogCap = 400;
constexpr int kDoneMs = 2800;
constexpr int kErrorMs = 7000;

const QRegularExpression& pct_re() {
    static const QRegularExpression re(QStringLiteral(R"((\d{1,3})\s*%)"));
    return re;
}

QString one_line(const QString& text) { return text.simplified(); }

bool contains_any(const QString& low, std::initializer_list<const char*> words) {
    for (const char* word : words) {
        if (low.contains(QString::fromUtf8(word))) return true;
    }
    return false;
}

}  // namespace

bool is_error_notice(const QString& text) {
    const QString low = text.trimmed().toLower();
    return contains_any(low, {"failed", "error", "could not", "cannot", "unreadable", "ไม่สำเร็จ"});
}

bool is_save_notice(const QString& text) {
    const QString low = text.trimmed().toLower();
    if (low.isEmpty()) return false;
    // "saved" is a substring of "unsaved"; autosave is not a user save.
    if (contains_any(low, {"unsaved", "autosave", "failed", "error", "ไม่สำเร็จ", "needs", "to save", "to write"})) return false;
    if (contains_any(low, {"saved", "wrote ", "wrote\t", "exported", "บันทึกแล้ว", "บันทึกและ", "tersimpan", "保存しました", "保存完了"})) return true;
    return low.startsWith(QLatin1String("wrote"));
}

int parse_progress_pct(const QString& text) {
    const QRegularExpressionMatch m = pct_re().match(text);
    if (!m.hasMatch()) return -1;
    return qBound(0, m.captured(1).toInt(), 100);
}

QString short_progress_detail(const QString& title, const QString& detail) {
    const QString sub = one_line(detail);
    const QString head = one_line(title);
    if (sub.isEmpty() || sub == head) return {};
    if (parse_progress_pct(sub) < 0) return sub;
    static const QRegularExpression edge(QStringLiteral(R"(^[\s—·….%]+|[\s—·….%]+$)"));
    QString cleaned = one_line(QString(sub).remove(pct_re()));
    cleaned.remove(edge);
    const auto bare = [](QString s) { return s.remove(QChar(0x2026)).trimmed(); };
    if (cleaned.isEmpty() || cleaned == head || bare(cleaned) == bare(head)) return {};
    return cleaned;
}

UiTheme* UiTheme::instance() {
    static UiTheme* theme = new UiTheme;
    return theme;
}

void UiTheme::set_dark(bool dark) {
    if (dark_ == dark) return;
    dark_ = dark;
    emit changed();
}

QString themed_qss(const QString& dark_qss) {
    if (ui_dark()) return dark_qss;
    static const QList<QPair<QString, QString>> swap = {
        {QStringLiteral("#12161c"), QStringLiteral("#e9edf2")},
        {QStringLiteral("#1a1e26"), QStringLiteral("#f6f7f9")},
        {QStringLiteral("#2a3140"), QStringLiteral("#dde2ea")},
        {QStringLiteral("#f2f4f8"), QStringLiteral("#1d1d1f")},
        {QStringLiteral("#8b93a1"), QStringLiteral("#5c6570")},
    };
    QString out = dark_qss;
    for (const auto& pair : swap) out.replace(pair.first, pair.second, Qt::CaseInsensitive);
    return out;
}

void apply_themed_qss(QWidget* widget, const QString& dark_qss) {
    widget->setStyleSheet(themed_qss(dark_qss));
    QObject::connect(UiTheme::instance(), &UiTheme::changed, widget, [widget, dark_qss] { widget->setStyleSheet(themed_qss(dark_qss)); });
}

StatusHub* StatusHub::instance() {
    static StatusHub* hub = new StatusHub;
    return hub;
}

StatusHub::StatusHub(QObject* parent) : QObject(parent) {
    hold_ = new QTimer(this);
    hold_->setSingleShot(true);
    connect(hold_, &QTimer::timeout, this, &StatusHub::hide_toast);
}

void StatusHub::log(const QString& text, const QString& kind) {
    history_ << QStringLiteral("[%1] %2").arg(QDateTime::currentDateTime().toString(QStringLiteral("HH:mm:ss")), text);
    if (history_.size() > kLogCap) history_ = history_.mid(history_.size() - kLogCap);
    text_ = one_line(text);
    text_kind_ = kind;
    emit changed();
}

void StatusHub::post(const QString& text) {
    const QString line = text.trimmed();
    if (line.isEmpty()) return;
    const int pct = parse_progress_pct(line);
    if (pct >= 0) {
        log(line, QStringLiteral("progress"));
        had_progress_ = true;
        QString title = one_line(QString(line).remove(pct_re()));
        title.remove(QRegularExpression(QStringLiteral(R"([\s—·]+$)")));
        progress(title.isEmpty() ? line : title, pct);
        return;
    }
    if (is_error_notice(line)) {
        log(line, QStringLiteral("error"));
        had_progress_ = false;
        notify(QStringLiteral("error"), line, {}, kErrorMs);
        return;
    }
    if (is_save_notice(line)) {
        log(line, QStringLiteral("save"));
        had_progress_ = false;
        notify(QStringLiteral("save"), QStringLiteral("Saved"), line);
        return;
    }
    log(line, QStringLiteral("info"));
    if (had_progress_) {
        // Loads can top out at 99% — the next plain line must close the sticky toast.
        had_progress_ = false;
        finish(line);
    }
}

void StatusHub::notify(const QString& kind, const QString& title, const QString& detail, int ms) {
    toast_kind_ = kind;
    toast_title_ = one_line(title);
    const QString sub = kind == QLatin1String("progress") ? short_progress_detail(title, detail) : one_line(detail);
    toast_detail_ = sub == toast_title_ ? QString() : sub;
    if (kind != QLatin1String("progress")) toast_pct_ = -1;
    toast_shown_ = true;
    hold_->stop();
    if (kind != QLatin1String("progress") && ms > 0) hold_->start(ms);
    emit toastChanged();
}

void StatusHub::progress(const QString& title, int pct, const QString& detail) {
    pct = qBound(0, pct, 100);
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    // ~12 Hz / every 2% keeps the chip cheap during long loads.
    if (pct < 100 && toast_kind_ == QLatin1String("progress") && toast_shown_ && pct - last_prog_pct_ < 2 && now - last_prog_ms_ < 80) return;
    last_prog_ms_ = now;
    last_prog_pct_ = pct;
    toast_pct_ = pct;
    notify(QStringLiteral("progress"), title, detail, 0);
    if (pct >= 100) finish(detail.isEmpty() ? title : detail);
}

void StatusHub::finish(const QString& detail) {
    last_prog_pct_ = -1;
    if (!toast_shown_ || toast_kind_ != QLatin1String("progress")) return;
    toast_pct_ = 100;
    emit toastChanged();
    QTimer::singleShot(180, this, [this, detail] {
        if (toast_kind_ != QLatin1String("progress")) return;
        notify(QStringLiteral("save"), QStringLiteral("Done"), short_progress_detail(QStringLiteral("Done"), detail), kDoneMs);
    });
}

void StatusHub::drop(const QStringList& paths) {
    if (paths.isEmpty()) return;
    QStringList names;
    for (const QString& path : paths.mid(0, 6)) {
        const QUrl url(path);
        names << QFileInfo(url.isLocalFile() ? url.toLocalFile() : path).fileName();
    }
    if (paths.size() > 6) names << QStringLiteral("+%1").arg(paths.size() - 6);
    const QString title = paths.size() == 1 ? QStringLiteral("Dropped") : QStringLiteral("Dropped files · %1").arg(paths.size());
    log(title + QStringLiteral(" — ") + names.join(QStringLiteral(", ")), QStringLiteral("drop"));
    notify(QStringLiteral("drop"), title, names.join(QStringLiteral(" · ")));
}

void StatusHub::hide_toast() {
    if (!toast_shown_) return;
    toast_shown_ = false;
    emit toastChanged();
}
