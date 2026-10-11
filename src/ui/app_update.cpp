#include "ui/app_update.h"

#include "ui/crash_report.h"
#include "ui/i18n.h"
#include "ui/res_path.h"
#include "ui/status_hub.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDialog>
#include <QDir>
#include <QEvent>
#include <QFile>
#include <QGuiApplication>
#include <QScreen>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QProcess>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlError>
#include <QQuickWidget>
#include <QStandardPaths>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>

namespace {

constexpr const char* kRepo = "naseno15/mstn-trainz-studio";

QVector<int> version_parts(QString text) {
    text = text.trimmed();
    if (text.startsWith(QLatin1Char('v'), Qt::CaseInsensitive)) text = text.mid(1);
    const int cut = text.indexOf(QLatin1Char('-'));
    if (cut >= 0) text = text.left(cut);
    QVector<int> parts;
    for (const QString& bit : text.split(QLatin1Char('.'))) {
        bool ok = false;
        const int n = bit.toInt(&ok);
        if (!ok) break;
        parts << n;
    }
    return parts;
}

QString pretty_version(QString tag) {
    tag = tag.trimmed();
    if (tag.startsWith(QLatin1Char('v'), Qt::CaseInsensitive)) tag = tag.mid(1);
    const int cut = tag.indexOf(QLatin1Char('-'));
    return cut >= 0 ? tag.left(cut) : tag;
}

QString update_repo() {
    const QString env = qEnvironmentVariable("TRAINZ_UPDATE_REPO");
    return env.isEmpty() ? QString::fromLatin1(kRepo) : env;
}

QString app_version() {
#ifdef TRAINZ_STUDIO_VERSION
    return QStringLiteral(TRAINZ_STUDIO_VERSION);
#else
    return QStringLiteral("0.0.0");
#endif
}

bool zip_magic(const QString& path);

QString iso_when(const QString& iso) {
    const QDateTime when = QDateTime::fromString(iso, Qt::ISODate);
    return when.isValid() ? when.toLocalTime().toString(QStringLiteral("d MMM yyyy HH:mm")) : iso;
}

QString release_zip(const QJsonObject& release, QString* name) {
    QString url;
    QString picked;
    for (const QJsonValue& value : release.value(QStringLiteral("assets")).toArray()) {
        const QJsonObject asset = value.toObject();
        const QString file = asset.value(QStringLiteral("name")).toString();
        if (!file.endsWith(QLatin1String(".zip"), Qt::CaseInsensitive)) continue;
        if (url.isEmpty()) {
            url = asset.value(QStringLiteral("browser_download_url")).toString();
            picked = file;
        }
        if (file.contains(QLatin1String("win64"), Qt::CaseInsensitive)) {
            url = asset.value(QStringLiteral("browser_download_url")).toString();
            picked = file;
            break;
        }
    }
    if (name) *name = picked;
    return url;
}

QVariantList notes_from_json(const QByteArray& json, const QString& current) {
    QVariantList rows;
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    const QJsonArray list = doc.isArray() ? doc.array() : QJsonArray{doc.object()};
    for (const QJsonValue& value : list) {
        if (!value.isObject()) continue;
        const QJsonObject release = value.toObject();
        if (release.value(QStringLiteral("draft")).toBool() || release.value(QStringLiteral("prerelease")).toBool()) continue;
        const QString version = pretty_version(release.value(QStringLiteral("tag_name")).toString());
        if (version.isEmpty()) continue;
        QString notes = release.value(QStringLiteral("body")).toString().trimmed();
        if (notes.size() > 2000) notes = notes.left(2000) + QStringLiteral("…");
        QString asset_name;
        QVariantMap row;
        row.insert(QStringLiteral("version"), version);
        row.insert(QStringLiteral("title"), release.value(QStringLiteral("name")).toString());
        row.insert(QStringLiteral("when"), iso_when(release.value(QStringLiteral("published_at")).toString()));
        row.insert(QStringLiteral("notes"), notes);
        row.insert(QStringLiteral("assetUrl"), release_zip(release, &asset_name));
        row.insert(QStringLiteral("assetName"), asset_name);
        row.insert(QStringLiteral("installed"), version == current);
        row.insert(QStringLiteral("newer"), version_is_newer(version, current));
        rows << row;
        if (rows.size() >= 6) break;
    }
    return rows;
}

bool commit_from_json(const QByteArray& json, QString* sha, QString* title, QString* when) {
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    const QJsonObject commit = doc.isArray() ? (doc.array().isEmpty() ? QJsonObject{} : doc.array().first().toObject()) : doc.object();
    const QString full = commit.value(QStringLiteral("sha")).toString();
    if (full.size() < 7) return false;
    const QJsonObject git = commit.value(QStringLiteral("commit")).toObject();
    const QString message = git.value(QStringLiteral("message")).toString().section(QLatin1Char('\n'), 0, 0).trimmed();
    if (sha) *sha = full.left(7);
    if (title) *title = message;
    if (when) *when = iso_when(git.value(QStringLiteral("author")).toObject().value(QStringLiteral("date")).toString());
    return true;
}

class UpdateController : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(bool toastOn READ toastOn NOTIFY changed)
    Q_PROPERTY(bool checking READ checking NOTIFY changed)
    Q_PROPERTY(bool newer READ newer NOTIFY changed)
    Q_PROPERTY(QString currentVersion READ currentVersion NOTIFY changed)
    Q_PROPERTY(QString version READ version NOTIFY changed)
    Q_PROPERTY(QString notes READ notes NOTIFY changed)
    Q_PROPERTY(QString folder READ folder NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString commitSha READ commitSha NOTIFY changed)
    Q_PROPERTY(QString commitTitle READ commitTitle NOTIFY changed)
    Q_PROPERTY(QString commitWhen READ commitWhen NOTIFY changed)
    Q_PROPERTY(QVariantList releases READ releases NOTIFY changed)
    Q_PROPERTY(int pct READ pct NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)

public:
    explicit UpdateController(QWidget* host) : QObject(host), host_(host), net_(new QNetworkAccessManager(this)) {
        connect(UiTheme::instance(), &UiTheme::changed, this, &UpdateController::changed);
        if (host_) host_->installEventFilter(this);
    }
    ~UpdateController() override { delete toast_; }

    bool dark() const { return ui_dark(); }
    bool toastOn() const { return toast_on_; }
    bool checking() const { return checking_; }
    bool newer() const { return newer_; }
    QString currentVersion() const { return app_version(); }
    QString version() const { return version_; }
    QString notes() const { return notes_; }
    QString folder() const { return QCoreApplication::applicationDirPath(); }
    QString error() const { return error_; }
    QString commitSha() const { return commit_sha_; }
    QString commitTitle() const { return commit_title_; }
    QString commitWhen() const { return commit_when_; }
    QVariantList releases() const { return releases_; }
    int pct() const { return pct_; }
    bool busy() const { return busy_; }

    void check_now() {
        const bool open = dialog_ != nullptr;
        if (!open) create_dialog();
        inquire(true);
        if (open) return;
        dialog_->exec();
        dialog_ = nullptr;
        dialog_hold_->deleteLater();
        dialog_hold_ = nullptr;
        if (toast_on_) show_toast();
    }

    void inquire(bool asked) {
        asked_ = asked;
        if (check_reply_ || commit_reply_) return;
        ignore_check_ = false;
        releases_failed_ = false;
        checking_ = true;
        error_.clear();
        emit changed();
        pending_ = 2;
        releases_json_.clear();
        commit_json_.clear();
        check_reply_ = get_json(QStringLiteral("https://api.github.com/repos/%1/releases?per_page=6").arg(update_repo()));
        commit_reply_ = get_json(QStringLiteral("https://api.github.com/repos/%1/commits?per_page=1").arg(update_repo()));
        watch_check(check_reply_, &releases_json_);
        watch_check(commit_reply_, &commit_json_);
    }

    Q_INVOKABLE void dismiss() {
        toast_on_ = false;
        emit changed();
        if (toast_) toast_->hide();
    }

    Q_INVOKABLE void openDialog() { check_now(); }

    Q_INVOKABLE void later() {
        ignore_check_ = true;
        const auto stop = [](QNetworkReply*& reply) {
            if (!reply) return;
            reply->abort();
            reply->deleteLater();
            reply = nullptr;
        };
        stop(check_reply_);
        stop(commit_reply_);
        if (reply_) {
            reply_->abort();
            reply_->deleteLater();
            reply_ = nullptr;
            QFile::remove(zip_path_);
        }
        checking_ = false;
        busy_ = false;
        pct_ = -1;
        emit changed();
        if (dialog_) dialog_->reject();
    }

    Q_INVOKABLE void install() {
        if (busy_ || offer_.assetUrl.isEmpty()) return;
        const QString dest = folder();
        QFile probe(dest + QStringLiteral("/.trainz-update-write-probe"));
        if (!probe.open(QIODevice::WriteOnly)) {
            fail(QStringLiteral("This folder is not writable"));
            return;
        }
        probe.close();
        probe.remove();
        error_.clear();
        busy_ = true;
        pct_ = 0;
        emit changed();
        const QString dir = QDir(QStandardPaths::writableLocation(QStandardPaths::TempLocation)).filePath(QStringLiteral("TrainzStudio-update"));
        QDir().mkpath(dir);
        zip_path_ = QDir(dir).filePath(QStringLiteral("TrainzStudio-win64.zip"));
        QFile::remove(zip_path_);
        zip_.setFileName(zip_path_);
        if (!zip_.open(QIODevice::WriteOnly)) {
            fail(QStringLiteral("Could not update"));
            return;
        }
        QNetworkRequest req{QUrl(offer_.assetUrl)};
        req.setRawHeader("User-Agent", "MSTN-Trainz-Studio");
        req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
        reply_ = net_->get(req);
        connect(reply_, &QNetworkReply::downloadProgress, this, [this](qint64 got, qint64 total) {
            pct_ = total > 0 ? qBound(0, int(got * 100 / total), 100) : -1;
            emit changed();
        });
        connect(reply_, &QNetworkReply::readyRead, this, [this] {
            if (reply_) zip_.write(reply_->readAll());
        });
        connect(reply_, &QNetworkReply::finished, this, [this, dest] {
            QNetworkReply* reply = reply_;
            reply_ = nullptr;
            if (!reply) return;
            zip_.write(reply->readAll());
            zip_.close();
            const bool aborted = reply->error() == QNetworkReply::OperationCanceledError;
            const bool failed = reply->error() != QNetworkReply::NoError;
            reply->deleteLater();
            if (aborted) return;
            if (failed || !zip_magic(zip_path_)) {
                QFile::remove(zip_path_);
                fail(QStringLiteral("The download is not a zip archive"));
                return;
            }
            if (!launch_helper(dest)) {
                fail(QStringLiteral("Could not update"));
                return;
            }
            toast_on_ = false;
            QTimer::singleShot(0, qApp, [] { QCoreApplication::quit(); });
        });
    }

signals:
    void changed();

protected:
    bool eventFilter(QObject* watched, QEvent* event) override {
        if (watched != host_ || !toast_) return false;
        if (event->type() == QEvent::Move || event->type() == QEvent::Resize || event->type() == QEvent::Show) place_toast();
        else if (event->type() == QEvent::Hide || event->type() == QEvent::WindowStateChange) place_toast();
        return false;
    }

private:
    void fail(const QString& text) {
        busy_ = false;
        pct_ = -1;
        error_ = text;
        emit changed();
    }

    QNetworkReply* get_json(const QString& url) {
        QNetworkRequest req{QUrl(url)};
        req.setRawHeader("User-Agent", "MSTN-Trainz-Studio");
        req.setRawHeader("Accept", "application/vnd.github+json");
        req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
        return net_->get(req);
    }

    void watch_check(QNetworkReply* reply, QByteArray* into) {
        connect(reply, &QNetworkReply::finished, this, [this, reply, into] {
            const bool releases_reply = reply == check_reply_;
            if (releases_reply) check_reply_ = nullptr;
            if (reply == commit_reply_) commit_reply_ = nullptr;
            const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            const bool ok = reply->error() == QNetworkReply::NoError && status < 400;
            if (ok) *into = reply->readAll();
            else if (releases_reply) releases_failed_ = true;
            reply->deleteLater();
            if (ignore_check_) return;
            if (--pending_ > 0) return;
            apply_check();
        });
    }

    void apply_check() {
        checking_ = false;
        if (releases_failed_ || releases_json_.isEmpty()) {
            releases_failed_ = false;
            error_ = QStringLiteral("Could not check for updates");
            emit changed();
            if (!asked_) StatusHub::instance()->notify(QStringLiteral("error"), error_);
            return;
        }
        releases_failed_ = false;
        error_.clear();
        releases_ = notes_from_json(releases_json_, app_version());
        version_.clear();
        notes_.clear();
        offer_ = {};
        newer_ = false;
        if (!releases_.isEmpty()) {
            const QVariantMap first = releases_.first().toMap();
            version_ = first.value(QStringLiteral("version")).toString();
            notes_ = first.value(QStringLiteral("notes")).toString();
            for (const QVariant& value : releases_) {
                const QVariantMap row = value.toMap();
                if (!row.value(QStringLiteral("newer")).toBool()) break;
                const QString url = row.value(QStringLiteral("assetUrl")).toString();
                if (url.isEmpty()) continue;
                newer_ = true;
                offer_.version = row.value(QStringLiteral("version")).toString();
                offer_.notes = row.value(QStringLiteral("notes")).toString();
                offer_.assetName = row.value(QStringLiteral("assetName")).toString();
                offer_.assetUrl = url;
                break;
            }
        }
        commit_sha_.clear();
        commit_title_.clear();
        commit_when_.clear();
        commit_from_json(commit_json_, &commit_sha_, &commit_title_, &commit_when_);
        toast_on_ = newer_;
        emit changed();
        if (newer_ && !dialog_) show_toast();
    }

    void create_dialog() {
        auto* dialog = new QDialog(host_);
        dialog->setWindowFlags(Qt::Dialog | Qt::FramelessWindowHint);
        dialog->setAttribute(Qt::WA_TranslucentBackground, true);
        dialog->setWindowTitle(QStringLiteral("Trainz Studio"));
        const QWidget* anchor = host_ && host_->isVisible() ? host_ : QApplication::activeWindow();
        const QScreen* screen = anchor && anchor->screen() ? anchor->screen() : QGuiApplication::primaryScreen();
        dialog->setGeometry(screen ? screen->availableGeometry() : QRect(0, 0, 640, 560));
        auto* view = new QQuickWidget(dialog);
        view->setResizeMode(QQuickWidget::SizeRootObjectToView);
        view->setAttribute(Qt::WA_AlwaysStackOnTop, true);
        view->setClearColor(Qt::transparent);
        view->engine()->rootContext()->setContextProperty(QStringLiteral("upd"), this);
        view->engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), this);
        view->setSource(res_url(res_qml_dir() + QStringLiteral("/UpdateDialog.qml")));
        auto* lay = new QVBoxLayout(dialog);
        lay->setContentsMargins(0, 0, 0, 0);
        lay->addWidget(view);
        dialog_hold_ = dialog;
        dialog_ = dialog;
        if (toast_) toast_->hide();
        dialog->show();
        dialog->raise();
        dialog->activateWindow();
    }

    void show_toast() {
        if (!toast_on_ || !host_ || !host_->isVisible() || host_->isMinimized()) return;
        if (!toast_) {
            toast_ = new QQuickWidget;
            toast_->setWindowFlags(Qt::Tool | Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint | Qt::WindowStaysOnTopHint);
            toast_->setAttribute(Qt::WA_TranslucentBackground, true);
            toast_->setAttribute(Qt::WA_ShowWithoutActivating, true);
            toast_->setAttribute(Qt::WA_QuitOnClose, false);
            toast_->setClearColor(Qt::transparent);
            toast_->setResizeMode(QQuickWidget::SizeRootObjectToView);
            toast_->engine()->rootContext()->setContextProperty(QStringLiteral("upd"), this);
            toast_->setSource(res_url(res_qml_dir() + QStringLiteral("/UpdateToast.qml")));
            toast_->resize(380, 88);
        }
        place_toast();
        toast_->show();
        toast_->raise();
    }

    void place_toast() {
        if (!toast_ || !host_) return;
        if (!toast_on_ || !host_->isVisible() || host_->isMinimized() || dialog_) {
            toast_->hide();
            return;
        }
        constexpr int margin = 16;
        const QPoint corner = host_->mapToGlobal(QPoint(host_->width() - toast_->width() - margin, host_->height() - toast_->height() - 30 - margin));
        toast_->setGeometry(corner.x(), corner.y(), toast_->width(), toast_->height());
        if (!toast_->isVisible()) toast_->show();
    }

    bool launch_helper(const QString& dest) {
        const QString dir = QFileInfo(zip_path_).absolutePath();
        const QString script_path = QDir(dir).filePath(QStringLiteral("apply-update.ps1"));
        QFile script(script_path);
        if (!script.open(QIODevice::WriteOnly | QIODevice::Truncate)) return false;
        script.write("\xEF\xBB\xBF");
        script.write(R"ps(
param(
  [Parameter(Mandatory)][int]$WaitPid,
  [Parameter(Mandatory)][string]$Zip,
  [Parameter(Mandatory)][string]$Dest,
  [Parameter(Mandatory)][string]$ExeName
)
$ErrorActionPreference = 'Stop'
$log = Join-Path $env:TEMP 'TrainzStudio-update.log'
function Log($m) { Add-Content -LiteralPath $log -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $m) }
try {
  Log "wait $WaitPid"
  for ($i = 0; $i -lt 150; $i++) {
    if (-not (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 200
  }
  $locked = Join-Path $Dest $ExeName
  for ($i = 0; $i -lt 50; $i++) {
    try {
      $fs = [System.IO.File]::Open($locked, 'Open', 'ReadWrite', 'None')
      $fs.Close()
      break
    } catch { Start-Sleep -Milliseconds 200 }
  }
  $stage = Join-Path $env:TEMP ("TrainzStudio-stage-" + $WaitPid)
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
  New-Item -ItemType Directory -Path $stage | Out-Null
  Expand-Archive -LiteralPath $Zip -DestinationPath $stage -Force
  $hit = Get-ChildItem -LiteralPath $stage -Recurse -Filter $ExeName -File | Select-Object -First 1
  if (-not $hit) { throw "archive has no $ExeName" }
  & robocopy $hit.DirectoryName $Dest /E /R:2 /W:1 /NFL /NDL /NJH /NJS
  if ($LASTEXITCODE -ge 8) { throw "robocopy $LASTEXITCODE" }
  Start-Process -FilePath (Join-Path $Dest $ExeName)
  Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
  Log 'ok'
} catch {
  Log $_.Exception.Message
  $fallback = Join-Path $Dest $ExeName
  if (Test-Path -LiteralPath $fallback) { Start-Process -FilePath $fallback }
}
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
)ps");
        script.close();
        const QString ps = QDir(qEnvironmentVariable("SystemRoot")).filePath(QStringLiteral("System32/WindowsPowerShell/v1.0/powershell.exe"));
        const QString exe_name = QFileInfo(QCoreApplication::applicationFilePath()).fileName();
        const QStringList args = {
            QStringLiteral("-NoProfile"), QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"), QStringLiteral("-WindowStyle"), QStringLiteral("Hidden"),
            QStringLiteral("-File"), script_path,
            QStringLiteral("-WaitPid"), QString::number(QCoreApplication::applicationPid()),
            QStringLiteral("-Zip"), zip_path_,
            QStringLiteral("-Dest"), dest,
            QStringLiteral("-ExeName"), exe_name,
        };
        return QProcess::startDetached(ps, args);
    }

    QWidget* host_ = nullptr;
    QNetworkAccessManager* net_ = nullptr;
    QNetworkReply* reply_ = nullptr;
    QNetworkReply* check_reply_ = nullptr;
    QNetworkReply* commit_reply_ = nullptr;
    QDialog* dialog_hold_ = nullptr;
    bool asked_ = false;
    bool ignore_check_ = false;
    bool checking_ = false;
    bool newer_ = false;
    bool releases_failed_ = false;
    int pending_ = 0;
    QByteArray releases_json_;
    QByteArray commit_json_;
    QString commit_sha_;
    QString commit_title_;
    QString commit_when_;
    QVariantList releases_;
    QQuickWidget* toast_ = nullptr;
    QDialog* dialog_ = nullptr;
    QFile zip_;
    QString zip_path_;
    UpdateOffer offer_;
    QString version_;
    QString notes_;
    QString error_;
    bool toast_on_ = false;
    bool busy_ = false;
    int pct_ = -1;
};

#include "app_update.moc"

bool zip_magic(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return false;
    const QByteArray sig = file.read(4);
    return sig.size() == 4 && sig[0] == 'P' && sig[1] == 'K';
}

QStringList qml_errors(const QString& file, QObject* bridge) {
    QQuickWidget view;
    view.engine()->rootContext()->setContextProperty(QStringLiteral("upd"), bridge);
    view.engine()->rootContext()->setContextProperty(QStringLiteral("bridge"), bridge);
    view.setSource(res_url(res_qml_dir() + QLatin1Char('/') + file));
    QStringList lines;
    for (const QQmlError& error : view.errors()) lines << error.toString();
    if (view.status() != QQuickWidget::Ready && lines.isEmpty()) lines << file + QStringLiteral(" did not load");
    return lines;
}

}  // namespace

bool version_is_newer(const QString& remote, const QString& local) {
    const QVector<int> next = version_parts(remote);
    const QVector<int> have = version_parts(local);
    if (next.isEmpty() || have.isEmpty()) return false;
    const int n = qMax(next.size(), have.size());
    for (int i = 0; i < n; ++i) {
        const int a = i < next.size() ? next[i] : 0;
        const int b = i < have.size() ? have[i] : 0;
        if (a != b) return a > b;
    }
    return false;
}

bool parse_release_offer(const QByteArray& json, const QString& current, UpdateOffer* offer) {
    if (!offer) return false;
    const QJsonObject root = QJsonDocument::fromJson(json).object();
    const QString tag = root.value(QStringLiteral("tag_name")).toString();
    if (!version_is_newer(tag, current)) return false;
    QJsonObject chosen;
    for (const QJsonValue& value : root.value(QStringLiteral("assets")).toArray()) {
        const QJsonObject asset = value.toObject();
        const QString name = asset.value(QStringLiteral("name")).toString();
        if (!name.endsWith(QLatin1String(".zip"), Qt::CaseInsensitive)) continue;
        if (chosen.isEmpty()) chosen = asset;
        if (name.contains(QLatin1String("win64"), Qt::CaseInsensitive)) {
            chosen = asset;
            break;
        }
    }
    const QString url = chosen.value(QStringLiteral("browser_download_url")).toString();
    if (url.isEmpty()) return false;
    offer->version = pretty_version(tag);
    offer->assetName = chosen.value(QStringLiteral("name")).toString();
    offer->assetUrl = url;
    QString notes = root.value(QStringLiteral("body")).toString().trimmed();
    if (notes.size() > 1200) notes = notes.left(1200) + QStringLiteral("…");
    offer->notes = notes;
    return true;
}

static UpdateController* updates_ = nullptr;

QString studio_version() { return app_version(); }

QString studio_repo_url() { return QStringLiteral("https://github.com/%1").arg(update_repo()); }

QVariantList release_notes(const QByteArray& json, const QString& current) { return notes_from_json(json, current); }

bool parse_commit_summary(const QByteArray& json, QString* sha, QString* title, QString* when) {
    return commit_from_json(json, sha, title, when);
}

void start_update_check(QWidget* host) {
    updates_ = new UpdateController(host);
    if (qEnvironmentVariableIsSet("TRAINZ_NO_UPDATE")) return;
    QTimer::singleShot(1200, updates_, [] { if (updates_) updates_->inquire(false); });
}

void request_update_check() {
    if (updates_) updates_->check_now();
}

QStringList load_update_qml() {
    auto* bridge = new UpdateController(nullptr);
    QStringList lines = qml_errors(QStringLiteral("UpdateToast.qml"), bridge);
    lines << qml_errors(QStringLiteral("UpdateDialog.qml"), bridge);
    delete bridge;
    return lines;
}
