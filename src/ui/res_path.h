#pragma once
// Resources: embedded (:/studio/...) in the release exe, else the on-disk dev tree (QML_DIR / I18N_DIR).
#include <QFile>
#include <QString>
#include <QUrl>

inline bool res_embedded() { return QFile::exists(QStringLiteral(":/studio/qml/HomePage.qml")); }

inline QString res_qml_dir() {
    if (res_embedded()) return QStringLiteral(":/studio/qml");
#ifdef QML_DIR
    return QStringLiteral(QML_DIR);
#else
    return {};
#endif
}

inline QString res_i18n_dir() {
    if (res_embedded()) return QStringLiteral(":/studio/i18n");
#ifdef I18N_DIR
    return QStringLiteral(I18N_DIR);
#else
    return {};
#endif
}

inline QString res_icon_font() {
    if (res_embedded()) return QStringLiteral(":/studio/fonts/MaterialIcons-Regular.ttf");
#ifdef QML_DIR
    return QStringLiteral(QML_DIR "/../assets/fonts/MaterialIcons-Regular.ttf");
#else
    return {};
#endif
}

inline QUrl res_url(const QString& path) {
    return path.startsWith(QLatin1String(":/")) ? QUrl(QStringLiteral("qrc") + path) : QUrl::fromLocalFile(path);
}
