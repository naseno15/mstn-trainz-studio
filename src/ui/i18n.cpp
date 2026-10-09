#include "ui/i18n.h"

#include <QAbstractButton>
#include <QApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QQmlEngine>
#include <QQuickWidget>
#include <QRegularExpression>
#include <QSettings>
#include <QTableWidget>

namespace {

QString i18n_dir() {
#ifdef I18N_DIR
    return QStringLiteral(I18N_DIR);
#else
    return QCoreApplication::applicationDirPath() + QStringLiteral("/i18n");
#endif
}

// Text worth translating: has a letter, is not a path / KUID / number / file name.
bool worth_catalog(const QString& text) {
    if (text.size() < 2 || text.size() > 400) return false;
    static const QRegularExpression letter(QStringLiteral("[A-Za-z]"));
    static const QRegularExpression machine(QStringLiteral(R"(^(<kuid|kuid|[A-Za-z]:[\\/]|/|https?:)|^[\w.-]+\.\w{2,10}$|^[\d\s.,:%+-]+$)"), QRegularExpression::CaseInsensitiveOption);
    return text.contains(letter) && !machine.match(text.trimmed()).hasMatch();
}

template <typename W, typename Get, typename Set>
void swap_text(W* widget, const char* slot, Get get, Set set) {
    const QByteArray src_key = QByteArray("_i18n_src_") + slot;
    const QByteArray shown_key = QByteArray("_i18n_shown_") + slot;
    const QString now = get();
    QString src = widget->property(src_key.constData()).toString();
    // The page set new English text since the last pass — that becomes the source.
    if (src.isEmpty() || now != widget->property(shown_key.constData()).toString()) src = now;
    if (src.isEmpty()) return;
    const QString shown = ui_tr(src);
    widget->setProperty(src_key.constData(), src);
    widget->setProperty(shown_key.constData(), shown);
    if (shown != now) set(shown);
}

}  // namespace

UiLang* UiLang::instance() {
    static UiLang* lang = [] {
        auto* made = new UiLang(qApp);
        made->set_lang(QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).value(QStringLiteral("ui/lang"), QStringLiteral("en")).toString());
        return made;
    }();
    return lang;
}

void UiLang::set_lang(const QString& lang) {
    QHash<QString, QString> strings;
    if (lang != QLatin1String("en")) {
        QFile file(i18n_dir() + QLatin1Char('/') + lang + QStringLiteral(".json"));
        if (!file.open(QIODevice::ReadOnly)) {
            qWarning("i18n: no catalog for %s in %s", qPrintable(lang), qPrintable(i18n_dir()));
            return;
        }
        const QJsonObject map = QJsonDocument::fromJson(file.readAll()).object();
        for (auto it = map.begin(); it != map.end(); ++it) strings.insert(it.key(), it.value().toString());
    }
    lang_ = lang;
    strings_ = std::move(strings);
    QSettings(QStringLiteral("MSTN"), QStringLiteral("TrainzStudio")).setValue(QStringLiteral("ui/lang"), lang_);
    if (!qApp) return;
    QCoreApplication::removeTranslator(this);
    if (!strings_.isEmpty()) QCoreApplication::installTranslator(this);
    for (QWidget* widget : QApplication::allWidgets()) {
        if (auto* view = qobject_cast<QQuickWidget*>(widget)) view->engine()->retranslate();
    }
    for (QWidget* top : QApplication::topLevelWidgets()) retranslate_widgets(top);
    emit changed();
}

QString UiLang::lookup(const QString& english) const {
    if (strings_.isEmpty() || english.isEmpty()) return english;
    const auto it = strings_.constFind(english);
    if (it != strings_.constEnd() && !it->isEmpty()) return *it;
    note_miss(english);
    return english;
}

QString UiLang::translate(const char*, const char* source, const char*, int) const {
    if (strings_.isEmpty() || !source) return {};
    const QString key = QString::fromUtf8(source);
    const auto it = strings_.constFind(key);
    if (it != strings_.constEnd()) return *it;
    note_miss(key);
    return {};
}

void UiLang::note_miss(const QString& english) const {
    static const bool harvesting = qEnvironmentVariableIsSet("TS_I18N_HARVEST");
    if (harvesting && worth_catalog(english)) misses_.insert(english);
}

void UiLang::flush_harvest() const {
    const QString path = qEnvironmentVariable("TS_I18N_HARVEST");
    if (path.isEmpty()) return;
    QSet<QString> all = misses_;
    QFile old(path);
    if (old.open(QIODevice::ReadOnly)) {
        for (const auto& v : QJsonDocument::fromJson(old.readAll()).object().keys()) all.insert(v);
        old.close();
    }
    QJsonObject out;
    for (const QString& key : all) out.insert(key, QString());
    QFile file(path);
    if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(QJsonDocument(out).toJson());
}

QString ui_tr(const QString& english) { return UiLang::instance()->lookup(english); }

const QList<QPair<QString, QString>>& ui_languages() {
    static const QList<QPair<QString, QString>> list = {
        {QStringLiteral("en"), QStringLiteral("English")},
        {QStringLiteral("th"), QStringLiteral("ไทย")},
        {QStringLiteral("ja"), QStringLiteral("日本語")},
        {QStringLiteral("id"), QStringLiteral("Bahasa Indonesia")},
    };
    return list;
}

void retranslate_widgets(QWidget* root) {
    if (!root) return;
    QList<QWidget*> widgets = root->findChildren<QWidget*>();
    widgets.prepend(root);
    for (QWidget* widget : widgets) {
        if (qobject_cast<QQuickWidget*>(widget)) continue;
        if (auto* label = qobject_cast<QLabel*>(widget)) swap_text(label, "text", [label] { return label->text(); }, [label](const QString& t) { label->setText(t); });
        else if (auto* button = qobject_cast<QAbstractButton*>(widget)) swap_text(button, "text", [button] { return button->text(); }, [button](const QString& t) { button->setText(t); });
        else if (auto* line = qobject_cast<QLineEdit*>(widget)) swap_text(line, "ph", [line] { return line->placeholderText(); }, [line](const QString& t) { line->setPlaceholderText(t); });
        if (auto* table = qobject_cast<QTableWidget*>(widget)) {
            for (int c = 0; c < table->columnCount(); ++c) {
                QTableWidgetItem* head = table->horizontalHeaderItem(c);
                if (!head) continue;
                const QString src = head->data(Qt::UserRole + 77).toString().isEmpty() ? head->text() : head->data(Qt::UserRole + 77).toString();
                head->setData(Qt::UserRole + 77, src);
                head->setText(ui_tr(src));
            }
        }
        if (!widget->toolTip().isEmpty()) swap_text(widget, "tip", [widget] { return widget->toolTip(); }, [widget](const QString& t) { widget->setToolTip(t); });
    }
}
