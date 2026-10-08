import QtQuick

// Raised glass button. Fields and tables use SunkField / a sunk well, not this.
Item {
    id: btn

    property string label: ""
    property string glyph: ""
    property string fontName: ""
    property bool accent: false
    property bool lit: false
    signal clicked()

    implicitWidth: 88
    implicitHeight: 36

    Repeater {
        model: 3
        delegate: Rectangle {
            required property int index
            property real t: (index + 1) / 3
            anchors.fill: parent
            anchors.leftMargin: 2 - t * 3
            anchors.rightMargin: 2 - t * 3
            anchors.topMargin: 2 + index
            anchors.bottomMargin: -t * 3
            radius: 12
            color: Qt.rgba(0, 0, 0, (btn.accent || btn.lit ? 0.28 : 0.18) * (1.05 - t))
        }
    }

    Rectangle {
        id: face
        anchors.fill: parent
        anchors.bottomMargin: 3
        radius: 10
        border.width: 1
        border.color: btn.accent || btn.lit
                      ? Qt.rgba(1, 0.75, 0.6, 0.28)
                      : Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: btn.accent || btn.lit ? "#e8683a" : (bridge.dark ? Qt.rgba(0.28, 0.31, 0.36, 0.96) : Qt.rgba(0.95, 0.96, 0.97, 0.96))
            }
            GradientStop {
                position: 0.40
                color: btn.accent || btn.lit ? "#d25424" : (bridge.dark ? Qt.rgba(0.18, 0.20, 0.24, 0.97) : Qt.rgba(0.88, 0.90, 0.93, 0.97))
            }
            GradientStop {
                position: 1.0
                color: btn.accent || btn.lit ? "#b84312" : (bridge.dark ? Qt.rgba(0.11, 0.12, 0.15, 0.98) : Qt.rgba(0.76, 0.79, 0.84, 0.98))
            }
        }
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 1
            height: parent.height * 0.45
            radius: 10
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, btn.accent || btn.lit ? 0.16 : (bridge.dark ? 0.08 : 0.35)) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
        Text {
            anchors.centerIn: parent
            text: btn.glyph.length > 0 ? btn.glyph : btn.label
            font.family: btn.glyph.length > 0 ? btn.fontName : ""
            font.pixelSize: btn.glyph.length > 0 ? 20 : 13
            font.bold: btn.glyph.length === 0
            color: btn.accent || btn.lit ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
        }
    }

    HoverHandler { id: hv }
    Rectangle {
        anchors.fill: face
        radius: 10
        color: hv.hovered ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
    }
    TapHandler { onTapped: if (btn.enabled) btn.clicked() }
}
