#pragma once

#include <QList>
#include <QString>
#include <QStringList>

// Trainz mesh/texture/config VE rules — local scan + safe auto-fixes (port of trainz_studio/io/ve_rules.py).
// File-local checks only: no Content Manager DB and no GameScript compile.

struct VeFinding {
    int code = 0;  // VE number; 0 = studio-only note
    QString level;  // error | warn | info
    QString path;
    QString message;
    bool fixable = false;
    QString fix_kind;  // ve39 | pot | texture_txt | mat_name | alpha_size
};

struct VeReport {
    QString path;
    QList<VeFinding> findings;
    QList<int> codes() const;
    QString status() const;  // compact Status-column text
    int error_count() const;
    int warn_count() const;
};

struct VeSummary {
    int hits = 0;
    int errors = 0;
    int warns = 0;
    int fixable = 0;
    QList<int> codes;
    QString line;
};

struct VeFix {
    VeFinding finding;
    bool ok = false;
    QString message;
};

VeReport ve_scan_image(const QString& path);
VeReport ve_scan_texture_txt(const QString& path);
VeReport ve_scan_mesh(const QString& path);
VeReport ve_scan_lm_txt(const QString& path);
VeReport ve_scan_config(const QString& path);
VeReport ve_scan_sound(const QString& path);
QList<VeReport> ve_scan_texture_folder(const QString& folder);
QList<VeReport> ve_scan_mesh_folder(const QString& folder);
QList<VeReport> ve_scan_asset_folder(const QString& folder);
QList<VeReport> ve_scan_paths(const QStringList& paths);

QStringList ve_attachment_names(const QString& path, QString* error = nullptr);

QPair<bool, QString> ve_fix_finding(const VeFinding& finding, bool bak = true);
QList<VeFix> ve_fix_reports(const QList<VeReport>& reports, bool bak = true);

VeSummary ve_summarize(const QList<VeReport>& reports);
QString ve_format_report(const VeReport& report);
QString ve_format_reports(const QList<VeReport>& reports);
