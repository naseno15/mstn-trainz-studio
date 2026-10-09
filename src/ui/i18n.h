#pragma once

#include <QHash>
#include <QSet>
#include <QString>
#include <QTranslator>

class QWidget;

// English source text is the key (same catalogs as trainz_studio/ui/i18n, exported by
// tools/export_i18n.py to assets/i18n/<lang>.json). QML reaches it through qsTr();
// C++ through ui_tr(); plain widgets through retranslate_widgets().
class UiLang : public QTranslator {
    Q_OBJECT

public:
    static UiLang* instance();

    QString lang() const { return lang_; }
    // Loads the catalog, swaps the app translator and re-evaluates every QML qsTr binding.
    void set_lang(const QString& lang);
    QString lookup(const QString& english) const;
    bool isEmpty() const override { return strings_.isEmpty(); }
    QString translate(const char* context, const char* source, const char* disambiguation, int n) const override;

    // TS_I18N_HARVEST=<file>: every displayed source text the catalog misses is appended there.
    void flush_harvest() const;

signals:
    void changed();

private:
    using QTranslator::QTranslator;
    void note_miss(const QString& english) const;

    QString lang_ = QStringLiteral("en");
    QHash<QString, QString> strings_;
    mutable QSet<QString> misses_;
};

QString ui_tr(const QString& english);
const QList<QPair<QString, QString>>& ui_languages();  // code → native name
void retranslate_widgets(QWidget* root);
