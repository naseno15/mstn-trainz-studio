#pragma once

#include <QList>
#include <QString>
#include <QStringList>
#include <QVector>

// Trainz config.txt (ACS text). One tree for every kind: containers stay containers,
// and a tag's editor comes from its parent names plus the tag name.

struct AcsNode {
    QString name;
    QString value;
    bool quoted = false;
    bool box = false;
    int begin = 0;
    int end = 0;
    QVector<AcsNode> kids;
};

struct AcsFile {
    AcsNode root;
    bool ok = true;
    QString error;
};

struct AcsHint {
    QString editor;  // text, number, bool, kuid, file, enum, alias, container
    QString filter;  // category-class codes for the library picker, comma separated
    QString unit;
    bool multi = false;
    QStringList options;
};

AcsFile parse_acs(const QString& text);
const AcsNode* acs_at(const AcsNode& root, const QList<int>& path);
AcsHint acs_hint(const QStringList& parents, const QString& name, const QString& value, bool box);
QString acs_format(const QString& editor, const QString& raw, bool quoted);
QString acs_menu_text(const QString& raw, const QStringList& pairs);
QStringList acs_parents(const AcsNode& root, const QList<int>& path);
