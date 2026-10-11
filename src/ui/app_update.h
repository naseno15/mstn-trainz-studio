#pragma once

#include <QByteArray>
#include <QString>
#include <QVariantList>

class QWidget;

struct UpdateOffer {
    QString version;
    QString notes;
    QString assetName;
    QString assetUrl;
};

// True when `remote` (a release tag, optional leading v) is a higher dotted version than `local`.
bool version_is_newer(const QString& remote, const QString& local);
// Latest GitHub release JSON. False when it is not newer than `current` or has no Windows zip.
bool parse_release_offer(const QByteArray& json, const QString& current, UpdateOffer* offer);

QString studio_version();
QString studio_repo_url();
// Release list JSON (array or one object). Each map: version, title, when, notes, assetUrl, installed.
QVariantList release_notes(const QByteArray& json, const QString& current);
// One commit object, or a one-element array from /commits?per_page=1.
bool parse_commit_summary(const QByteArray& json, QString* sha, QString* title, QString* when);
// After the window is up. Silent when offline, current, or TRAINZ_NO_UPDATE is set.
void start_update_check(QWidget* host);
// Help menu. Opens the install dialog when a newer release is already known.
void request_update_check();
// Loads the update toast and dialog. Empty when both compile clean.
QStringList load_update_qml();
