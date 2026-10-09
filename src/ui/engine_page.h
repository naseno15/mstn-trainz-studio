#pragma once

#include "ui/status_hub.h"

#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QWidget>

#include "ui/icons.h"

#include <map>
#include <string>
#include <vector>

#include "io/enginespec.h"

class QQuickWidget;

class EngineBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool dark READ dark NOTIFY changed)
    Q_PROPERTY(int sideW READ sideW NOTIFY changed)
    Q_PROPERTY(bool autoOn READ autoOn NOTIFY changed)
    Q_PROPERTY(bool sideLocked READ sideLocked NOTIFY changed)
    Q_PROPERTY(QString iconFontUrl READ iconFontUrl NOTIFY changed)
    Q_PROPERTY(QString iconFont READ iconFont NOTIFY changed)
    Q_PROPERTY(QString tuner READ tuner NOTIFY changed)
    Q_PROPERTY(QString simulation READ simulation NOTIFY changed)
    Q_PROPERTY(QString homeLabel READ homeLabel NOTIFY changed)
    Q_PROPERTY(QString parameters READ parameters NOTIFY changed)
    Q_PROPERTY(QString autoTune READ autoTune NOTIFY changed)
    Q_PROPERTY(QString page READ page NOTIFY changed)
    Q_PROPERTY(QString centerJson READ centerJson NOTIFY changed)
    Q_PROPERTY(int notchFocus READ notchFocus NOTIFY changed)
    Q_PROPERTY(QString fileTips READ fileTips NOTIFY changed)
    Q_PROPERTY(bool showBack READ showBack NOTIFY changed)
    Q_PROPERTY(QString backGlyph READ backGlyph NOTIFY changed)
    Q_PROPERTY(QString openGlyph READ openGlyph NOTIFY changed)
    Q_PROPERTY(QString saveGlyph READ saveGlyph NOTIFY changed)
    Q_PROPERTY(QString saveAsGlyph READ saveAsGlyph NOTIFY changed)
    Q_PROPERTY(bool saveAsOn READ saveAsOn NOTIFY changed)
    Q_PROPERTY(QString undoGlyph READ undoGlyph NOTIFY changed)
    Q_PROPERTY(QString redoGlyph READ redoGlyph NOTIFY changed)
    Q_PROPERTY(QString sideJson READ sideJson NOTIFY changed)
    Q_PROPERTY(int cloneFrom READ cloneFrom NOTIFY changed)
    Q_PROPERTY(int targets READ targets NOTIFY changed)
    Q_PROPERTY(QString autoJson READ autoJson NOTIFY changed)
    Q_PROPERTY(QString autoKind READ autoKind NOTIFY changed)
    Q_PROPERTY(int autoTab READ autoTab NOTIFY changed)
    Q_PROPERTY(QString autoSummary READ autoSummary NOTIFY changed)
    Q_PROPERTY(QStringList shapeNames READ shapeNames NOTIFY changed)

public:
    explicit EngineBridge(QObject* parent = nullptr);

    bool dark() const { return ui_dark(); }
    int sideW() const { return side_w_; }
    bool autoOn() const { return auto_on_; }
    bool sideLocked() const { return false; }
    bool cdpSession() const { return cdp_session_; }
    QString iconFontUrl() const { return material_icon_url(); }
    QString iconFont() const { return material_icon_family(); }
    QString tuner() const { return QStringLiteral("Tuner"); }
    QString simulation() const { return QStringLiteral("Simulation"); }
    QString homeLabel() const { return material_glyph("home"); }
    QString parameters() const { return QStringLiteral("Parameters"); }
    QString autoTune() const { return QStringLiteral("Auto Tune"); }
    QString page() const { return page_; }
    QString centerJson() const { return center_json_; }
    int notchFocus() const { return notch_focus_; }
    QString fileTips() const { return file_tips_; }
    bool showBack() const { return cdp_session_; }
    QString backGlyph() const { return material_glyph("arrow_back"); }
    QString openGlyph() const { return material_glyph("file_open"); }
    QString saveGlyph() const { return material_glyph("save"); }
    QString saveAsGlyph() const { return material_glyph("save_as"); }
    bool saveAsOn() const { return true; }
    QString undoGlyph() const { return material_glyph("undo"); }
    QString redoGlyph() const { return material_glyph("redo"); }
    QString sideJson() const { return QStringLiteral("[]"); }
    int cloneFrom() const { return clone_from_; }
    int targets() const { return targets_; }
    QString autoJson() const { return QStringLiteral("{}"); }
    QString autoKind() const { return QStringLiteral("engine"); }
    int autoTab() const { return auto_tab_; }
    QString autoSummary() const { return QStringLiteral("Auto Tune is not in this build"); }
    QStringList shapeNames() const { return {}; }

    void load_text(const QString& text, const QString& path = {});
    void load_cdp_text(const QString& text);
    QString spec_text() const;

    Q_INVOKABLE void setPage(const QString& page);
    Q_INVOKABLE void goHome();
    Q_INVOKABLE void toggleAuto();
    Q_INVOKABLE void setSideW(double width);
    Q_INVOKABLE void setCloneFrom(int notch);
    Q_INVOKABLE void toggleTarget(int notch);
    Q_INVOKABLE void openFile();
    Q_INVOKABLE QStringList veContextPaths() const;
    Q_INVOKABLE void saveFile();
    Q_INVOKABLE void saveFileAs();
    Q_INVOKABLE void undoEdit();
    Q_INVOKABLE void redoEdit();
    Q_INVOKABLE void goBack();
    Q_INVOKABLE void doClone();
    Q_INVOKABLE void doCloneHigher();
    Q_INVOKABLE void editPoint(int notch, int index, int column, const QString& text);
    Q_INVOKABLE void addPoint(int notch);
    Q_INVOKABLE void delPoint(int notch, int index);
    Q_INVOKABLE void movePoint(int notch, int from, int to);
    Q_INVOKABLE void focusNotch(int notch);
    Q_INVOKABLE void setResist(bool on);
    Q_INVOKABLE void setGraphMax(const QString& kmh, const QString& kn);
    Q_INVOKABLE void fitGraph();
    Q_INVOKABLE void placeGraph(double x, double y, double w, double h);
    Q_INVOKABLE void setSim(const QString& key, const QString& text);
    Q_INVOKABLE void runSim();
    Q_INVOKABLE void editParam(const QString& bag, const QString& key, int column, const QString& text);
    Q_INVOKABLE void addParam(const QString& bag);
    Q_INVOKABLE void delParam(const QString& bag, const QString& key);
    Q_INVOKABLE void editPressure(const QString& key, int column, const QString& text);
    Q_INVOKABLE void addPressure();
    Q_INVOKABLE void delPressure(const QString& key);
    Q_INVOKABLE void setAutoTab(int tab);
    Q_INVOKABLE void setAutoField(const QString& key, const QString& text);
    Q_INVOKABLE void previewAuto();
    Q_INVOKABLE void applyAuto();
    Q_INVOKABLE void cyclePowerUnit();
    Q_INVOKABLE void cyclePressUnit();
    Q_INVOKABLE void presetAir();

signals:
    void changed();
    void homeRequested();
    void cdpSaveRequested(const QString& text);

private:
    void refresh();
    void push_undo();
    std::map<std::string, double>* bag(const QString& name);

    EngineSpec spec_;
    std::vector<EngineSpec> undo_;
    std::vector<EngineSpec> redo_;
    QString page_ = QStringLiteral("tuner");
    QString center_json_ = QStringLiteral("{}");
    QString file_tips_ = QStringLiteral(R"({"open":"Open","back":"Back","save":"Save","saveAs":"Save as","undo":"Undo","redo":"Redo"})");
    QString max_kmh_ = QStringLiteral("120.00");
    QString max_kn_ = QStringLiteral("80.00");
    std::map<QString, QString> sim_{
        {QStringLiteral("mass"), QStringLiteral("40")},
        {QStringLiteral("motors"), QStringLiteral("1")},
        {QStringLiteral("grade"), QStringLiteral("0")},
        {QStringLiteral("duration"), QStringLiteral("60")},
        {QStringLiteral("notch"), QStringLiteral("8")},
        {QStringLiteral("brake"), QStringLiteral("0")},
        {QStringLiteral("emergency"), QStringLiteral("0")},
        {QStringLiteral("stats"), QString()},
    };
    int side_w_ = 280;
    int notch_focus_ = -1;
    int clone_from_ = 1;
    int targets_ = 0;
    int auto_tab_ = 0;
    bool auto_on_ = false;
    bool resist_ = false;
    bool cdp_session_ = false;
};

class EngineTunerPage : public QWidget {
    Q_OBJECT

public:
    explicit EngineTunerPage(QWidget* parent = nullptr);

    bool qmlReady() const;
    QStringList qmlErrors() const;
    void loadText(const QString& text);
    void loadCdpText(const QString& text);
    QString centerJson() const;
    QString specText() const;
    bool cdpSession() const;
    QString pageName() const;
    void editPoint(int notch, int index, int column, const QString& text);
    void setPage(const QString& page);

signals:
    void homeRequested();
    void cdpSaveRequested(const QString& text);

private:
    EngineBridge* bridge_ = nullptr;
    QQuickWidget* view_ = nullptr;
};
