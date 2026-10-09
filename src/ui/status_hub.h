#pragma once

#include <QObject>
#include <QString>
#include <QStringList>

class QTimer;
class QWidget;

// Shell-wide status line: a ring log for the LOGS sheet plus one glass toast
// hanging under the title bar. Kinds: save · drop · progress · error · info.
class StatusHub : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString text READ text NOTIFY changed)
    Q_PROPERTY(QString textKind READ textKind NOTIFY changed)
    Q_PROPERTY(int logCount READ logCount NOTIFY changed)
    Q_PROPERTY(bool toastShown READ toastShown NOTIFY toastChanged)
    Q_PROPERTY(QString toastKind READ toastKind NOTIFY toastChanged)
    Q_PROPERTY(QString toastTitle READ toastTitle NOTIFY toastChanged)
    Q_PROPERTY(QString toastDetail READ toastDetail NOTIFY toastChanged)
    Q_PROPERTY(int toastPct READ toastPct NOTIFY toastChanged)
    Q_PROPERTY(QString veState READ veState NOTIFY changed)  // "" never scanned · bad · ok

public:
    static StatusHub* instance();

    QString text() const { return text_; }
    QString textKind() const { return text_kind_; }
    int logCount() const { return static_cast<int>(history_.size()); }
    QStringList history() const { return history_; }
    bool toastShown() const { return toast_shown_; }
    QString toastKind() const { return toast_kind_; }
    QString toastTitle() const { return toast_title_; }
    QString toastDetail() const { return toast_detail_; }
    int toastPct() const { return toast_pct_; }
    QString veState() const { return ve_state_; }
    void set_ve_state(const QString& state) {
        ve_state_ = state;
        emit changed();
    }

    // Classifies like the Python StudioStatusBar: "42%" → progress, saved/wrote → save,
    // failed/error → error, anything after a sticky progress closes it.
    Q_INVOKABLE void post(const QString& text);
    void notify(const QString& kind, const QString& title, const QString& detail = {}, int ms = 5000);
    void progress(const QString& title, int pct, const QString& detail = {});
    void finish(const QString& detail = {});
    void drop(const QStringList& paths);

    Q_INVOKABLE void openLog() { emit logRequested(); }
    Q_INVOKABLE void openVe() { emit veRequested(); }

signals:
    void changed();
    void toastChanged();
    void logRequested();
    void veRequested();

private:
    explicit StatusHub(QObject* parent = nullptr);
    void log(const QString& text, const QString& kind);
    void hide_toast();

    QStringList history_;
    QString text_;
    QString text_kind_ = QStringLiteral("info");
    bool toast_shown_ = false;
    QString toast_kind_ = QStringLiteral("info");
    QString toast_title_;
    QString toast_detail_;
    int toast_pct_ = -1;
    QString ve_state_;
    bool had_progress_ = false;
    qint64 last_prog_ms_ = 0;
    int last_prog_pct_ = -1;
    QTimer* hold_ = nullptr;
};

// App-wide light/dark flag. Every page bridge's dark() reads it; changed() re-binds their QML.
class UiTheme : public QObject {
    Q_OBJECT

public:
    static UiTheme* instance();
    bool dark() const { return dark_; }
    void set_dark(bool dark);

signals:
    void changed();

private:
    using QObject::QObject;
    bool dark_ = true;
};

inline bool ui_dark() { return UiTheme::instance()->dark(); }

// Widget stylesheets are authored in the dark palette (#12161c/#1a1e26/#2a3140 fills, #f2f4f8/#8b93a1 ink);
// themed_qss swaps those for their light twins. apply_themed_qss re-applies on every theme change.
QString themed_qss(const QString& dark_qss);
void apply_themed_qss(QWidget* widget, const QString& dark_qss);

bool is_save_notice(const QString& text);
bool is_error_notice(const QString& text);
int parse_progress_pct(const QString& text);  // -1 when none
QString short_progress_detail(const QString& title, const QString& detail);

inline void post_status(const QString& text) { StatusHub::instance()->post(text); }

// Posts `field` on scope exit when an action changed it (pages keep their own status_ string).
struct StatusWatch {
    explicit StatusWatch(const QString& field) : field_(field), before_(field) {}
    ~StatusWatch() {
        if (field_ != before_) post_status(field_);
    }
    const QString& field_;
    QString before_;
};
